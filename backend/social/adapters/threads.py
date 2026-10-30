"""Threads v1.0 durable containers; one bounded provider request per step."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from pydantic import Field, field_validator

from ..contracts import (CapabilitySet, Hash, OperationPlan, OperationResult,
    ReconciliationResult, StrictModel, ValidationResult, canonical_hash)
from ..native_admission import native_capability_matches
from ..worker.materials import ProviderFetchURL, WorkerCredentialMaterial
from .common import caption, issue
from .meta_http import MetaHTTPFailure, remote_id, _no_duplicates
from .platform_http import parse_retry_after


@dataclass(frozen=True)
class ThreadsAdapterConfig:
    api_version: str = 'v1.0'
    enabled: bool = False
    operational_gates_verified: bool = False
    media_uploads_enabled: bool = False

    def __post_init__(self):
        if self.api_version != 'v1.0' or any(type(v) is not bool for v in (self.enabled, self.operational_gates_verified, self.media_uploads_enabled)):
            raise ValueError('Threads requires explicit versioned boolean gates')

    @property
    def ready(self):
        return self.enabled and self.operational_gates_verified


class ThreadsCheckpoint(StrictModel):
    schema_version: Literal[1] = 1
    adapter: Literal['threads-v1.0-2026-10-16'] = 'threads-v1.0-2026-10-16'
    account_id: UUID
    external_account_id: str
    content_hash: Hash
    phase: Literal['quota_checked', 'child_created', 'container_created', 'container_ready', 'publish_ready', 'creation_uncertain', 'publication_uncertain', 'post_created']
    children: tuple[str, ...] = Field(default=(), max_length=20)
    container_id: str | None = None
    post_id: str | None = None
    poll_count: int = Field(default=0, strict=True, ge=0, le=5)

    @field_validator('schema_version', mode='before')
    @classmethod
    def strict_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError('Invalid checkpoint version')
        return value

    @field_validator('external_account_id', 'container_id', 'post_id')
    @classmethod
    def identities(cls, value):
        return remote_id(value) if value is not None else None

    @field_validator('children')
    @classmethod
    def child_ids(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('Duplicate child containers')
        return tuple(remote_id(item) for item in value)


def threads_caption(payload):
    # Topic tags are sent through the documented native field, not duplicated
    # as an unrelated block of hashtags in the caption.
    return caption(payload.model_copy(update={'hashtags': ()}))


class ThreadsAdapter:
    platform = 'threads'
    product = 'threads'
    formats = ('text', 'image', 'carousel', 'video')
    scopes = ('threads_basic', 'threads_content_publish')
    source_links = ('https://developers.facebook.com/documentation/threads/create-posts',
        'https://developers.facebook.com/documentation/threads/posts',
        'https://www.postman.com/meta/threads/request/ohuldvi/check-container-s-publishing-status',
        'https://www.postman.com/meta/threads/request/7evieur/retrieve-publishing-quota-limit')
    limits = {'max_text_length': 500, 'max_media_count': 20, 'max_publications_24h': 250,
              'max_image_bytes': 8000000, 'max_alt_text_length': 1000, 'max_hashtags': 1}

    def __init__(self, config, *, transport, now=None):
        if not isinstance(config, ThreadsAdapterConfig) or not isinstance(transport, httpx.AsyncBaseTransport):
            raise ValueError('Explicit Threads configuration and transport required')
        self.config, self.now = config, now or (lambda: datetime.now(timezone.utc))
        self.client = httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(15, connect=5),
            follow_redirects=False, trust_env=False)

    async def close(self):
        await self.client.aclose()

    def capabilities(self, account):
        scopes = account.get('granted_scopes', ())
        if not isinstance(scopes, (tuple, list)) or any(not isinstance(v, str) for v in scopes):
            scopes = ()
        prior = account.get('capability_snapshot', {})
        eligible = bool(isinstance(prior, dict) and prior.get('eligible') is True
            and account.get('platform') == self.platform and account.get('api_product') == self.product
            and account.get('connection_state') == 'connected' and set(self.scopes) <= set(scopes))
        return CapabilitySet(provider_api_version=self.config.api_version, eligible=eligible,
            adapter_available=self.config.ready, supported_formats=self.formats,
            feature_states={'publishing': 'supported' if self.config.ready and eligible else 'restricted',
                'media_upload': 'supported' if self.config.media_uploads_enabled else 'restricted'},
            required_scopes=self.scopes, granted_scopes=tuple(sorted(set(scopes))),
            price_class='free', limits=self.limits, source_links=self.source_links,
            verified_at=datetime(2026, 10, 16, tzinfo=timezone.utc))

    def validate(self, payload, capabilities):
        errors = []
        if not self.config.ready or not capabilities.adapter_available or not capabilities.eligible:
            errors.append(issue('ADAPTER_NOT_AVAILABLE', 'capabilities', 'Threads requires verified server and account access.'))
        if payload.platform != 'threads' or payload.api_product != self.product:
            errors.append(issue('ACCOUNT_PRODUCT_MISMATCH', 'account_id', 'Use a Threads OAuth account.'))
        if not set(self.scopes) <= set(capabilities.granted_scopes):
            errors.append(issue('PERMISSION_DENIED', 'scopes', 'Threads publishing permissions are missing.'))
        if canonical_hash(payload.model_dump(mode='json', exclude={'content_hash'})) != payload.content_hash:
            errors.append(issue('PAYLOAD_HASH_MISMATCH', 'content_hash', 'The approved payload changed.'))
        if payload.format not in {'text', 'image', 'carousel', 'video'}:
            errors.append(issue('UNSUPPORTED_FORMAT', 'format', 'Select a supported Threads format.'))
        # The current official contract counts emoji UTF-8 bytes. A bounded
        # UTF-8 ceiling is conservative for other non-ASCII text as well.
        if len(payload.hashtags) > 1:
            errors.append(issue('HASHTAG_LIMIT', 'hashtags', 'Threads supports one selected topic per post.'))
        if len(threads_caption(payload).encode('utf-8')) > 500:
            errors.append(issue('TEXT_TOO_LONG', 'text', 'The full Threads text exceeds the 500-byte application ceiling.'))
        links = set(re.findall(r'(?:https?://|www\.)[^\s]+', threads_caption(payload)))
        if len(links) > 5:
            errors.append(issue('TOO_MANY_LINKS', 'text', 'Threads permits at most five unique links.'))
        if payload.format == 'text' and (payload.assets or not threads_caption(payload).strip()) or payload.format in {'image','video'} and len(payload.assets) != 1 or payload.format == 'carousel' and not 2 <= len(payload.assets) <= 20:
            errors.append(issue('FORMAT_MEDIA_MISMATCH', 'assets', 'Select the required inspected media.'))
        if payload.assets and not self.config.media_uploads_enabled:
            errors.append(issue('MEDIA_UPLOADS_DISABLED', 'assets', 'Provider media transfer is disabled.'))
        if payload.disclosures or payload.tiktok_options is not None:
            errors.append(issue('UNSUPPORTED_DISCLOSURE', 'disclosures', 'These provider options are unsupported on Threads.'))
        try:
            remote_id(payload.external_account_id)
        except ValueError:
            errors.append(issue('ACCOUNT_ID_INVALID', 'account_id', 'Invalid Threads account identity.'))
        for asset in payload.assets:
            video = asset.mime_type == 'video/mp4'
            if asset.mime_type not in {'image/jpeg','image/png','video/mp4'} or payload.format == 'image' and video or payload.format == 'video' and not video:
                errors.append(issue('UNSUPPORTED_MEDIA', 'assets', 'Use inspected JPEG, PNG or MP4 appropriate to this format.'))
            if asset.width is None or asset.height is None or video and (asset.duration_ms is None or not 1000 <= asset.duration_ms <= 300000):
                errors.append(issue('MEDIA_INSPECTION_REQUIRED', 'assets', 'Inspected dimensions and supported video duration are required.'))
            elif not video and not (320 <= asset.width <= 1440 and asset.width <= 10 * asset.height):
                errors.append(issue('IMAGE_DIMENSIONS', 'assets', 'Use width 320–1440 and aspect ratio at most 10:1.'))
            elif video and (asset.width > 1920 or not 0.01 <= asset.width / asset.height <= 10 or asset.frame_rate_milli_fps is None or not 23000 <= asset.frame_rate_milli_fps <= 60000):
                errors.append(issue('VIDEO_DIMENSIONS', 'assets', 'Use a supported video size, aspect ratio and inspected 23–60 FPS.'))
            if (video and asset.byte_size > 100000000) or (not video and asset.byte_size > 8000000):
                errors.append(issue('MEDIA_TOO_LARGE', 'assets', 'The asset exceeds the application transfer ceiling.'))
            if asset.caption_asset_id or asset.caption_sha256 or asset.alt_text and len(asset.alt_text) > 1000:
                errors.append(issue('UNSUPPORTED_MEDIA_OPTIONS', 'assets', 'Use alt text up to 1000 characters and burned-in video captions.'))
        return ValidationResult(valid=not errors, errors=tuple(errors))

    @staticmethod
    def _checkpoint(payload, value):
        if value == {}:
            return None
        state = ThreadsCheckpoint.model_validate(value)
        if state.account_id != payload.account_id or state.external_account_id != payload.external_account_id or state.content_hash != payload.content_hash:
            raise ValueError('Checkpoint identity differs from approved payload')
        has_container = state.phase in {'container_created','container_ready','publish_ready','publication_uncertain','post_created'}
        if bool(state.container_id) != has_container or bool(state.post_id) != (state.phase == 'post_created') or state.post_id == state.container_id and state.post_id is not None:
            raise ValueError('Inconsistent container checkpoint')
        if payload.format != 'carousel' and state.children or len(state.children) > len(payload.assets) or state.phase == 'child_created' and not state.children:
            raise ValueError('Inconsistent carousel checkpoint')
        if payload.format == 'carousel' and has_container and len(state.children) != len(payload.assets):
            raise ValueError('Incomplete carousel')
        return state

    def _state(self, payload, phase, previous=None, **changes):
        value = previous.model_dump(mode='json') if previous else dict(account_id=payload.account_id,
            external_account_id=payload.external_account_id, content_hash=payload.content_hash)
        return ThreadsCheckpoint.model_validate({**value, 'phase': phase, **changes}).model_dump(mode='json')

    def next_operation(self, payload, checkpoint):
        state = self._checkpoint(payload, checkpoint)
        phase = state.phase if state else None
        operation = ('create_container' if phase in {'quota_checked','child_created'} else
            'publish' if phase == 'publish_ready' else 'poll')
        return OperationPlan(operation_id=uuid4(), operation=operation, publication_capable=operation == 'publish',
            safe_replay_class='read_only' if operation == 'poll' else 'requires_reconciliation',
            checkpoint=checkpoint, timeout_seconds=25)

    def validate_mutation_admission(self, payload, account):
        caps = self.capabilities(account)
        if not native_capability_matches(account.get('capability_snapshot'), caps):
            return ValidationResult(valid=False, errors=(issue('ACCOUNT_INELIGIBLE','capabilities','Reverify the Threads admission snapshot.'),))
        return self.validate(payload, caps)

    def _material(self, payload, credential):
        if not self.config.ready or not isinstance(credential, WorkerCredentialMaterial) or (credential.account_id, credential.platform, credential.api_product, credential.external_account_id, credential.page_id) != (payload.account_id, 'threads', self.product, payload.external_account_id, payload.external_account_id):
            raise MetaHTTPFailure('AUTHORIZATION_REQUIRED', retry_safe=True)
        if type(credential.credential_version) is not int or credential.credential_version < 1 or not isinstance(credential.credential_id, UUID) or not set(self.scopes) <= set(credential.granted_scopes):
            raise MetaHTTPFailure('PERMISSION_DENIED', retry_safe=True)
        if not isinstance(credential.page_access_token, str) or not 1 <= len(credential.page_access_token) <= 16384 or any(ord(c) < 33 or ord(c) > 126 for c in credential.page_access_token):
            raise MetaHTTPFailure('AUTHORIZATION_REQUIRED', retry_safe=True)
        if credential.access_expires_at is None or credential.access_expires_at.tzinfo is None or credential.access_expires_at <= self.now():
            raise MetaHTTPFailure('TOKEN_EXPIRED', retry_safe=True)
        if credential.data_access_expires_at is not None and (not isinstance(credential.data_access_expires_at, datetime)
                or credential.data_access_expires_at.tzinfo is None or credential.data_access_expires_at <= self.now()):
            raise MetaHTTPFailure('TOKEN_EXPIRED', retry_safe=True)
        return credential

    async def _request(self, method, node, material, *, edge=None, fields=None, data=None, metrics=None, maximum_bytes=65536):
        remote_id(node)
        if (type(maximum_bytes) is not int or not 1 <= maximum_bytes <= 65536
                or (metrics is not None and (edge != 'insights' or method != 'GET' or fields is not None or data is not None
                    or metrics != 'views,likes,replies,reposts,quotes,shares'))
                or (edge == 'insights' and metrics is None)):
            raise ValueError('Invalid bounded insights request')
        if edge not in {None, 'threads', 'threads_publish', 'threads_publishing_limit', 'insights'}:
            raise ValueError('Unsupported Threads endpoint')
        response = None
        try:
            request = self.client.build_request(method, f'https://graph.threads.com/{self.config.api_version}/{node}' + ('/' + edge if edge else ''),
                params={'metric': metrics} if metrics else {'fields': fields} if fields else None, data=data,
                headers={'Authorization':'Bearer ' + material.page_access_token,'Accept-Encoding':'identity'})
            response = await self.client.send(request, stream=True)
            if metrics is not None and response.status_code == 429:
                # A read throttle is authoritative even with malformed error JSON.
                raise MetaHTTPFailure('RATE_LIMITED', http_status=429,
                    next_action_at=parse_retry_after(response.headers.get('retry-after'), self.now()))
            if response.headers.get('content-encoding','identity') != 'identity':
                raise ValueError('Compressed response')
            body = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=16384):
                body.extend(chunk)
                if len(body) > maximum_bytes:
                    raise ValueError('Response exceeds bound')
            value = json.loads(body, object_pairs_hook=_no_duplicates,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(value, dict):
                raise ValueError('Invalid response')
        except (httpx.HTTPError, ValueError, TypeError, RecursionError):
            raise MetaHTTPFailure('PROVIDER_OUTCOME_UNCERTAIN', ambiguous=True) from None
        finally:
            if response is not None:
                await response.aclose()
        if response.status_code >= 300 or 'error' in value:
            error = value.get('error')
            code = error.get('code') if isinstance(error, dict) else None
            if response.status_code < 400 or response.status_code >= 500 or type(code) is not int or 'id' in value:
                raise MetaHTTPFailure('PROVIDER_OUTCOME_UNCERTAIN', ambiguous=True)
            safe = 'TOKEN_REVOKED' if code == 190 else 'PERMISSION_DENIED' if code in {10,200} else 'RATE_LIMITED' if code in {4,17,32,613} else 'PROVIDER_REJECTED'
            next_at=parse_retry_after(response.headers.get('retry-after'),self.now())
            raise MetaHTTPFailure(safe, retry_safe=safe!='RATE_LIMITED' or next_at is not None, http_status=response.status_code,
                next_action_at=next_at)
        return value

    @staticmethod
    def _failure(error, checkpoint):
        return OperationResult(outcome='ambiguous' if error.ambiguous else 'definite_failure',
            error_code=error.code, retry_safe=error.retry_safe, http_status=error.http_status,
            next_action_at=error.next_action_at, checkpoint=checkpoint)

    def _continued(self, checkpoint, *, processing=False):
        return OperationResult(outcome='processing' if processing else 'confirmed_success', checkpoint=checkpoint,
            next_action_at=self.now() + timedelta(seconds=60) if processing else None)

    async def execute(self, payload, operation, credential, media_access):
        checkpoint = operation.checkpoint
        try:
            material = self._material(payload, credential)
            state = self._checkpoint(payload, checkpoint)
            expected = self.next_operation(payload, checkpoint)
            if (operation.operation,operation.publication_capable,operation.safe_replay_class) != (expected.operation,expected.publication_capable,expected.safe_replay_class):
                raise ValueError('Operation does not match checkpoint')
            caps = self.capabilities({'platform':'threads','api_product':self.product,'connection_state':'connected',
                'granted_scopes':material.granted_scopes,'capability_snapshot':{'eligible':True}})
            if operation.safe_replay_class != 'read_only' and not native_capability_matches(material.capability_admission, caps):
                raise MetaHTTPFailure('ACCOUNT_INELIGIBLE', retry_safe=True)
            if not self.validate(payload, caps).valid:
                raise MetaHTTPFailure('INVALID_PUBLISHING_PAYLOAD', retry_safe=True)
            if operation.operation == 'poll':
                if state is None or state.phase == 'container_ready':
                    value = await self._request('GET', payload.external_account_id, material, edge='threads_publishing_limit', fields='quota_usage,config')
                    rows = value.get('data')
                    if not isinstance(rows,list) or len(rows) != 1 or not isinstance(rows[0],dict) or 'paging' in value:
                        raise ValueError('Invalid quota')
                    usage, config = rows[0].get('quota_usage'), rows[0].get('config')
                    if type(usage) is not int or usage < 0 or not isinstance(config,dict) or type(config.get('quota_total')) is not int or not 0 < config['quota_total'] <= 250 or type(config.get('quota_duration')) is not int or config['quota_duration'] != 86400:
                        raise ValueError('Unverified quota')
                    if usage >= config['quota_total']:
                        return OperationResult(outcome='definite_failure', error_code='RATE_LIMITED', retry_safe=True, checkpoint=checkpoint, next_action_at=self.now()+timedelta(hours=1))
                    return self._continued(self._state(payload,'publish_ready' if state else 'quota_checked',state))
                if state.phase == 'post_created':
                    return await self._post(payload,state,material)
                if state.phase in {'container_created','publication_uncertain'}:
                    return await self._container(payload,state,material)
                return OperationResult(outcome='ambiguous',error_code='REMOTE_IDENTITY_REQUIRED',checkpoint=checkpoint)
            uncertain = self._state(payload,'publication_uncertain',state) if operation.operation == 'publish' else self._state(payload,'creation_uncertain',state,container_id=None,post_id=None)
            if operation.operation == 'publish':
                value = await self._request('POST',payload.external_account_id,material,edge='threads_publish',data={'creation_id':state.container_id})
                post_id = remote_id(value.get('id'))
                if post_id == state.container_id:
                    raise ValueError('Container is not a published identity')
                return self._continued(self._state(payload,'post_created',state,post_id=post_id,poll_count=0))
            data = {'text':threads_caption(payload), 'media_type':'TEXT', 'auto_publish_text':'false'}
            child = payload.format == 'carousel' and len(state.children) < len(payload.assets)
            if payload.format == 'carousel' and not child:
                data = {'media_type':'CAROUSEL','text':threads_caption(payload),'children':','.join(state.children)}
            elif payload.assets:
                asset = payload.assets[len(state.children) if child else 0]
                if media_access is None:
                    raise MetaHTTPFailure('MEDIA_ACCESS_UNAVAILABLE',retry_safe=True)
                access = await media_access.provider_fetch_url(asset,120)
                if not isinstance(access,ProviderFetchURL) or access.asset_id != asset.asset_id or access.sha256 != asset.sha256 or access.expires_at.tzinfo is None or access.expires_at < self.now()+timedelta(seconds=120):
                    raise MetaHTTPFailure('MEDIA_ACCESS_UNAVAILABLE',retry_safe=True)
                parsed = urlsplit(access.url)
                if len(access.url)>8000 or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or '\\' in access.url or any(c.isspace() for c in access.url):
                    raise MetaHTTPFailure('MEDIA_ACCESS_UNAVAILABLE',retry_safe=True)
                video = asset.mime_type == 'video/mp4'
                data = {'media_type':'VIDEO' if video else 'IMAGE', 'video_url' if video else 'image_url':access.url,'alt_text':asset.alt_text or ''}
                if child:
                    data['is_carousel_item'] = 'true'
                else:
                    data['text'] = threads_caption(payload)
            if payload.hashtags and not child:
                data['topic_tag'] = payload.hashtags[0].removeprefix('#')
            value = await self._request('POST',payload.external_account_id,material,edge='threads',data=data)
            container = remote_id(value.get('id'))
            if child:
                return self._continued(self._state(payload,'child_created',state,children=(*state.children,container)))
            return self._continued(self._state(payload,'container_created',state,container_id=container,poll_count=0))
        except MetaHTTPFailure as error:
            return self._failure(error, uncertain if error.ambiguous and 'uncertain' in locals() else checkpoint)
        except (ValueError, TypeError, AttributeError):
            return OperationResult(outcome='ambiguous',error_code='PROVIDER_PROOF_INVALID',checkpoint=uncertain if 'uncertain' in locals() else checkpoint)

    async def _container(self,payload,state,material):
        checkpoint = state.model_dump(mode='json')
        if state.poll_count >= 5:
            return OperationResult(outcome='ambiguous',error_code='STATUS_CHECK_LIMIT',checkpoint=checkpoint)
        value = await self._request('GET',state.container_id,material,fields='id,status')
        if value.get('id') != state.container_id or value.get('status') not in {'IN_PROGRESS','FINISHED','PUBLISHED','ERROR','EXPIRED'}:
            raise ValueError('Invalid container status')
        checkpoint = self._state(payload,state.phase,state,poll_count=state.poll_count+1)
        if state.phase == 'publication_uncertain' or value['status'] == 'PUBLISHED':
            return OperationResult(outcome='ambiguous',error_code='NO_PROVIDER_COMPLETE_PUBLICATION_PROOF',checkpoint=self._state(payload,'publication_uncertain',state,poll_count=state.poll_count+1),receipt={'container_status':value['status']})
        if value['status'] == 'IN_PROGRESS':
            return self._continued(checkpoint,processing=True)
        if value['status'] == 'FINISHED':
            return self._continued(self._state(payload,'container_ready',state,poll_count=0))
        return OperationResult(outcome='definite_failure',error_code='CONTAINER_PROCESSING_FAILED',checkpoint=checkpoint)

    async def _post(self,payload,state,material):
        checkpoint=state.model_dump(mode='json')
        if state.poll_count >= 5:
            return OperationResult(outcome='ambiguous',error_code='STATUS_CHECK_LIMIT',checkpoint=checkpoint)
        value=await self._request('GET',state.post_id,material,fields='id,owner,username,text,media_type,media_product_type,permalink,shortcode,is_quote_post')
        owner=value.get('owner')
        expected_type={'text':'TEXT_POST','image':'IMAGE','video':'VIDEO','carousel':'CAROUSEL_ALBUM'}[payload.format]
        if value.get('id') != state.post_id or not isinstance(owner,dict) or owner.get('id') != payload.external_account_id or value.get('text','') != threads_caption(payload) or value.get('media_type') != expected_type or value.get('media_product_type') != 'THREADS' or value.get('is_quote_post') is not False:
            raise ValueError('Publication identity or content differs')
        username,shortcode,url=value.get('username'),value.get('shortcode'),value.get('permalink')
        if not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9_.]{1,64}',username) or not isinstance(shortcode,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',shortcode) or not isinstance(url,str):
            raise ValueError('Invalid publication permalink')
        parsed=urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname not in {'threads.com','www.threads.com','threads.net','www.threads.net'} or parsed.port not in {None,443} or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path.rstrip('/') != '/@'+username+'/post/'+shortcode:
            raise ValueError('Permalink does not identify publication')
        checkpoint = self._state(payload, state.phase, state, poll_count=state.poll_count + 1)
        # Authenticated media retrieval also works for private Threads profiles.
        # A permalink proves identity, never anonymous public availability.
        return OperationResult(outcome='processing',primary_remote_id=state.post_id,remote_url=url,
            visibility_state='unknown',confirmation_kind='threads_owned_post_read',checkpoint=checkpoint,
            remote_refs={'container_id':state.container_id,'post_id':state.post_id},
            error_code='PUBLIC_VISIBILITY_UNVERIFIED', next_action_at=self.now()+timedelta(seconds=60),
            receipt={'provider_api_version':'v1.0','owner_verified':True,'content_hash':payload.content_hash})

    async def reconcile(self,payload,checkpoint,attempt,credential,media_access):
        try:
            material=self._material(payload,credential)
            state=self._checkpoint(payload,checkpoint)
            if canonical_hash(payload.model_dump(mode='json',exclude={'content_hash'})) != payload.content_hash:
                raise ValueError('Payload changed')
            if state and state.phase == 'post_created':
                result=await self._post(payload,state,material)
                if result.visibility_state == 'public':
                    return ReconciliationResult(outcome='confirmed_published',result=result,evidence={'owner_verified':True,'post_id':state.post_id})
            elif state and state.container_id:
                # A lost publish response never re-enters container-ready, even
                # if a stale provider read still says FINISHED.
                if attempt and attempt.get('operation') == 'publish':
                    state=self._checkpoint(payload,self._state(payload,'publication_uncertain',state))
                result=await self._container(payload,state,material)
            else:
                return ReconciliationResult(outcome='unknown',evidence={'code':'REMOTE_IDENTITY_REQUIRED'})
            return ReconciliationResult(outcome='still_processing' if result.outcome in {'processing','confirmed_success'} else 'unknown',result=result,next_action_at=result.next_action_at,evidence={'code':result.error_code or 'KNOWN_CONTAINER_PENDING'})
        except (MetaHTTPFailure,ValueError,TypeError,AttributeError):
            return ReconciliationResult(outcome='unknown',evidence={'code':'PUBLICATION_PROOF_UNAVAILABLE'})
