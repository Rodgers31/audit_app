"""Facebook Page Reels: durable session, exact bytes, status-bound resume.

The July 30, 2026 Reels guide documents upload/publication status, not a
complete public-accessibility proof. Acceptance therefore remains Processing;
no status boolean or authenticated owner read is promoted to public visibility.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from ..contracts import Hash, NonPublicContinuationProof, OperationResult, ReconciliationResult, StrictModel, canonical_hash
from .common import caption, verify_bytes
from .meta_http import MetaHTTPFailure, remote_id
from .meta_validation import REEL_MAX_BYTES


class ReelCheckpoint(StrictModel):
    schema_version: Literal[1]
    adapter: Literal['facebook_reels-v1']
    account_id: UUID
    external_account_id: str
    content_hash: Hash
    phase: Literal['creation_uncertain', 'session_created', 'upload_uncertain', 'uploaded',
                   'publish_ready', 'publication_uncertain', 'publication_accepted']
    video_id: str | None = None
    offset: int = Field(strict=True, ge=0, le=REEL_MAX_BYTES)
    upload_count: int = Field(strict=True, ge=0, le=5)
    last_upload_operation_id: UUID | None = None
    poll_count: int = Field(strict=True, ge=0, le=5)

    @field_validator('schema_version', mode='before')
    @classmethod
    def strict_schema(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError('Invalid reel checkpoint version')
        return value

    @field_validator('video_id', 'external_account_id')
    @classmethod
    def numeric(cls, value):
        return remote_id(value) if value is not None else None


def checkpoint(payload, value):
    if value == {}:
        return None
    state = ReelCheckpoint.model_validate(value)
    if (state.account_id != payload.account_id or state.external_account_id != payload.external_account_id
            or state.content_hash != payload.content_hash or payload.platform != 'facebook' or payload.format != 'reel'
            or (state.video_id is None) != (state.phase == 'creation_uncertain')
            or len(payload.assets) != 1 or state.offset > payload.assets[0].byte_size
            or state.phase in {'uploaded', 'publish_ready', 'publication_uncertain', 'publication_accepted'}
                and state.offset != payload.assets[0].byte_size):
        raise ValueError('Reel checkpoint differs from approved payload')
    return state


class FacebookReels:
    """A scoped workflow on the existing adapter/transport and admission gates."""
    def __init__(self, adapter):
        self.adapter = adapter

    def state(self, payload, phase, *, previous=None, **changes):
        value = previous.model_dump(mode='json') if previous else dict(
            schema_version=1, adapter='facebook_reels-v1', account_id=str(payload.account_id),
            external_account_id=payload.external_account_id, content_hash=payload.content_hash,
            offset=0, upload_count=0, poll_count=0)
        value.update(phase=phase, **changes)
        # Validate on every output as well as every restart input.
        return checkpoint(payload, value).model_dump(mode='json')

    def next_operation(self, payload, value):
        state = checkpoint(payload, value)
        operation = 'create_container' if state is None else (
            'upload' if state.phase == 'session_created' and state.upload_count < 5 else
            'publish' if state.phase == 'publish_ready' else 'poll')
        return self.adapter._plan(operation, value)

    @staticmethod
    def success(value, response):
        return OperationResult(outcome='confirmed_success', checkpoint=value,
            remote_refs={'video_id': value['video_id']}, http_status=response.http_status,
            next_action_at=response.next_action_at)

    async def execute(self, payload, operation, credential, media_access):
        owner = self.adapter
        try:
            material, state = owner._admission(payload, operation, credential)
        except MetaHTTPFailure as error:
            return owner._failure(error, operation.checkpoint)
        if operation.operation == 'poll':
            return await self.poll(payload, state, material)
        value = operation.checkpoint
        if operation.operation == 'create_container':
            uncertain = self.state(payload, 'creation_uncertain')
            try:
                response = await owner.http.request('POST', material.page_id, token=material.page_access_token,
                    edge='video_reels', data={'upload_phase': 'start'})
                video_id = remote_id(response.value.get('video_id'))
                # Never send credentials to a provider-supplied arbitrary URL.
                # Accept only the two paths present in Meta's own guide/sample.
                allowed = {f'https://rupload.facebook.com/video-upload/{video_id}',
                    f'https://rupload.facebook.com/video-upload/{owner.config.graph_version}/{video_id}'}
                if response.value.get('upload_url') not in allowed:
                    raise ValueError('Untrusted upload URL')
                value = self.state(payload, 'session_created', video_id=video_id)
                return self.success(value, response)
            except MetaHTTPFailure as error:
                return owner._failure(error, uncertain if error.ambiguous else value)
            except (ValueError, TypeError):
                return owner._failure(MetaHTTPFailure('REEL_SESSION_UNCERTAIN', ambiguous=True), uncertain)
        if operation.operation == 'upload':
            try:
                if media_access is None:
                    raise MetaHTTPFailure('MEDIA_ACCESS_UNAVAILABLE', retry_safe=True)
                asset = payload.assets[0]
                content = verify_bytes(asset, await media_access.read_bytes(asset, REEL_MAX_BYTES), REEL_MAX_BYTES)
            except MetaHTTPFailure as error:
                return owner._failure(error, value)
            except Exception:
                return owner._failure(MetaHTTPFailure('MEDIA_ACCESS_UNAVAILABLE', retry_safe=True), value)
            uncertain = self.state(payload, 'upload_uncertain', previous=state,
                upload_count=state.upload_count + 1, last_upload_operation_id=str(operation.operation_id))
            try:
                response = await owner.http.upload_reel(state.video_id, token=material.page_access_token,
                    content=content, offset=state.offset)
                if response.value.get('success') is not True:
                    raise ValueError('Upload response did not attest success')
                value = self.state(payload, 'uploaded', previous=checkpoint(payload, uncertain), offset=asset.byte_size)
                return self.success(value, response)
            except MetaHTTPFailure as error:
                # Even a rejected resume must re-read offset before retry. A
                # prior partial request may have advanced the remote session.
                return owner._failure(error, uncertain)
            except (ValueError, TypeError):
                return owner._failure(MetaHTTPFailure('REEL_UPLOAD_UNCERTAIN', ambiguous=True), uncertain)
        if operation.operation == 'publish':
            uncertain = self.state(payload, 'publication_uncertain', previous=state, poll_count=0)
            try:
                response = await owner.http.request('POST', material.page_id, token=material.page_access_token,
                    edge='video_reels', data={'upload_phase': 'finish', 'video_id': state.video_id,
                        'video_state': 'PUBLISHED', 'description': caption(payload)})
                if response.value.get('success') is not True:
                    raise ValueError('Publication response did not attest acceptance')
                return self.success(self.state(payload, 'publication_accepted', previous=state, poll_count=0), response)
            except MetaHTTPFailure as error:
                return owner._failure(error, uncertain if error.ambiguous else value)
            except (ValueError, TypeError):
                return owner._failure(MetaHTTPFailure('REEL_PUBLICATION_UNCERTAIN', ambiguous=True), uncertain)
        raise ValueError('Unsupported Reels operation')

    async def poll(self, payload, state, material):
        owner = self.adapter
        value = state.model_dump(mode='json') if state else {}
        if state is None or state.video_id is None or state.poll_count >= 5 or state.upload_count >= 5 and state.phase == 'session_created':
            return owner._failure(MetaHTTPFailure('REEL_VERIFICATION_REQUIRED', ambiguous=True), value)
        value = self.state(payload, state.phase, previous=state, poll_count=state.poll_count + 1)
        try:
            response = await owner.http.request('GET', state.video_id, token=material.page_access_token, fields='id,status')
            raw = response.value
            status = raw.get('status')
            if raw.get('id') != state.video_id or not isinstance(status, dict):
                raise ValueError('Status identity missing')
            phases = [status.get(key) for key in ('uploading_phase', 'processing_phase', 'publishing_phase')]
            if any(not isinstance(p, dict) or p.get('status') not in {'not_started', 'in_progress', 'complete', 'error'} for p in phases):
                raise ValueError('Invalid status phases')
            upload, process, publish = phases
            if any(p.get('error') is not None or p['status'] == 'error' for p in phases):
                # Failure does not establish absence of a public side effect.
                raise ValueError('Provider processing error requires review')
            if state.phase in {'publication_accepted', 'publication_uncertain'}:
                return owner._processing(value, code='PUBLIC_VISIBILITY_UNCONFIRMED' if publish['status'] == 'complete' else 'REEL_PUBLICATION_PENDING')
            if publish['status'] != 'not_started':
                raise ValueError('Unexpected remote publication before permit')
            size = payload.assets[0].byte_size
            # Meta spells this field bytes_transfered for Facebook, whereas
            # Instagram's separate protocol uses bytes_transferred.
            offset = upload.get('bytes_transfered')
            if offset is not None and (type(offset) is not int or not state.offset <= offset <= size):
                raise ValueError('Upload offset regressed or exceeded approved size')
            if upload['status'] == 'complete':
                if offset is not None and offset != size:
                    raise ValueError('Contradictory upload completion')
                value = self.state(payload, 'publish_ready', previous=checkpoint(payload, value), offset=size, poll_count=0)
                return self.success(value, response)
            if state.phase in {'session_created', 'upload_uncertain'} and upload['status'] in {'not_started', 'in_progress'} and offset is not None and offset < size and state.upload_count < 5:
                value = self.state(payload, 'session_created', previous=checkpoint(payload, value), offset=offset)
                return self.success(value, response)
            return owner._processing(value, code='REEL_UPLOAD_PENDING')
        except MetaHTTPFailure as error:
            if error.code in {'TOKEN_REVOKED', 'TOKEN_EXPIRED', 'PERMISSION_DENIED'}:
                return owner._failure(error, value)
            return owner._processing(value, code='REEL_STATUS_UNAVAILABLE', next_action_at=error.next_action_at,
                http_status=error.http_status)
        except (ValueError, TypeError):
            return owner._failure(MetaHTTPFailure('REEL_STATUS_PROOF_INVALID', ambiguous=True), value)

    async def reconcile(self, payload, value, attempt, credential):
        owner = self.adapter
        try:
            material = owner._material(payload, credential)
            state = checkpoint(payload, value)
            if canonical_hash(payload.model_dump(mode='json', exclude={'content_hash'})) != payload.content_hash:
                raise ValueError('Changed immutable payload')
        except (MetaHTTPFailure, ValueError, TypeError):
            return ReconciliationResult(outcome='unknown', evidence={'code': 'REEL_RECONCILIATION_UNAVAILABLE'})
        if state is None or state.video_id is None:
            return ReconciliationResult(outcome='unknown', evidence={'code': 'REEL_IDENTITY_UNAVAILABLE'})
        # A persisted pre-call checkpoint may be all a crashed process left.
        # Never replay a publication; never upload again without fresh status.
        if attempt and attempt.get('operation') == 'publish':
            value = self.state(payload, 'publication_uncertain', previous=state, poll_count=state.poll_count)
            state = checkpoint(payload, value)
        elif attempt and attempt.get('operation') == 'upload' and attempt.get('operation_id'):
            # The committed intent survives even when the response checkpoint
            # does not. Count that UUID once, including a partial accepted body.
            operation_id = UUID(str(attempt['operation_id']))
            if state.last_upload_operation_id != operation_id:
                if state.upload_count >= 5:
                    return ReconciliationResult(outcome='unknown', evidence={'code':'REEL_UPLOAD_LIMIT'})
                value = self.state(payload, state.phase, previous=state,
                    upload_count=state.upload_count+1, last_upload_operation_id=str(operation_id))
                state = checkpoint(payload, value)
        result = await self.poll(payload, state, material)
        proof = None
        if (result.outcome == 'confirmed_success' and attempt and attempt.get('operation') == 'upload'
                and attempt.get('operation_id') and attempt.get('request_fingerprint')):
            proof = NonPublicContinuationProof(kind='provider_nonpublic_checkpoint', account_id=payload.account_id,
                operation_id=attempt['operation_id'], content_hash=payload.content_hash,
                request_fingerprint=attempt['request_fingerprint'], checkpoint_hash=canonical_hash(result.checkpoint))
        return ReconciliationResult(outcome='still_processing' if result.outcome in {'processing', 'confirmed_success'} else 'unknown',
            result=result, next_action_at=result.next_action_at, continuation_proof=proof,
            evidence={'code': result.error_code or 'REEL_REMOTE_STATUS_VERIFIED'})
