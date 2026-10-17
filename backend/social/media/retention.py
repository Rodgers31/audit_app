"""Retained create-only fencing, never write-drain evidence or deletion authority.

R2 evaluates If-None-Match at commit. Both committed keys stay present and their
full two-copy reservation stays charged. Cleanup may never remove either key
after this marker is committed. No timestamp or negative HEAD settles a write.
"""
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import tempfile
from uuid import UUID, uuid4

from ..contracts import canonical_hash
from ..service import SocialError, require_positive_version, utc
from .reconciliation import ReconciliationModel, Epoch
from ..contracts import PositiveVersion

MARKER = 'retained_write_fence_v1'


class RetainedRecovery(ReconciliationModel):
    expected_version: PositiveVersion
    expected_grant_epoch: Epoch
    expected_finalization_epoch: PositiveVersion | None


def scope(asset, upload):
    return canonical_hash({'asset': str(asset.id), 'actor': str(upload.actor_id),
        'provider': asset.storage_provider, 'bucket': asset.bucket,
        'quarantine': upload.quarantine_key, 'original': asset.storage_key,
        'version': upload.version, 'grant_epoch': upload.grant_epoch,
        'finalization_epoch': upload.finalization_epoch, 'size': asset.byte_size,
        'mime': asset.mime_type, 'sha256': asset.sha256,
        'etag': asset.codec_metadata.get('storage_etag'),
        'storage_version': asset.codec_metadata.get('storage_version'),
        'reserved_bytes': upload.reserved_bytes, 'declared_size': upload.declared_size,
        'finalization_settled': upload.finalization_settled})


def retain_ready(service, actor, asset_id, version, request_id):
    require_positive_version(version)
    if not all(type(x) is UUID for x in (actor, asset_id, request_id)):
        raise SocialError('INVALID_REQUEST', 'Valid operator and asset identities are required.', 422)
    storage = service._storage()
    if not service.config.retained_writes_enabled or getattr(storage, 'retained_create_only', None) is not True:
        raise SocialError('MEDIA_RECOVERY_UNAVAILABLE', 'Retained create-only recovery is unavailable.', 503)
    with service.db.begin():
        budgets = service._budgets(service._upload_actor(asset_id))
        asset, upload = service._rows(asset_id)
        if upload.actor_id != actor:
            raise SocialError('PERMISSION_DENIED', 'Only the initiating administrator may retain this upload.', 403)
        if upload.version != version:
            raise SocialError('VERSION_CONFLICT', 'This media upload changed.')
        if upload.fenced_copies:
            # Completed quarantine retirement supersedes retained-copy byte
            # verification. Its permanent marker and ledger must survive replay.
            from sqlalchemy import select
            from .models import SocialMediaDeletion
            completed = service.db.scalar(select(SocialMediaDeletion.operation_id).where(
                SocialMediaDeletion.asset_id == asset_id, SocialMediaDeletion.state == 'complete',
                SocialMediaDeletion.mode == 'quarantine'))
            if asset.state == 'ready' and upload.fenced_copies == 1 and completed:
                return service._dto(asset, upload)
            raise SocialError('MEDIA_RETENTION_INVALID', 'Payload retirement requires its original operation.', 409)
        if (asset.state != 'ready' or not upload.finalization_settled
                or not isinstance(asset.codec_metadata, dict)
                or upload.reservation_released or upload.quarantine_cleaned
                or upload.reserved_bytes < 2 * upload.declared_size
                or asset.byte_size != upload.declared_size
                or (asset.storage_provider, asset.bucket) != (storage.provider, storage.bucket)
                or upload.quarantine_key != f'quarantine/{actor}/{asset_id}/source'
                or asset.storage_key != f'ready/{asset_id}/original'):
            raise SocialError('MEDIA_RETENTION_INVALID', 'Verified originals and both-copy accounting are required.', 409)
        expected = scope(asset, upload)
        if any(b.bytes_used < upload.reserved_bytes for b in budgets):
            raise SocialError('MEDIA_RETENTION_INVALID', 'The upload ledger requires operator review.', 409)
        if upload.retained_write_fence is not None:
            try:
                marker = json.loads(upload.retained_write_fence)
            except (ValueError, TypeError):
                marker = None
            if (type(marker) is dict and set(marker) == {'version', 'scope_hash', 'quarantine_etag', 'original_etag'}
                    and type(marker.get('version')) is int and marker['version'] == 1
                    and marker.get('scope_hash') == expected
                    and type(marker.get('quarantine_etag')) is str and marker['quarantine_etag']
                    and marker.get('original_etag') == asset.codec_metadata.get('storage_etag')
                    and upload.pending_released):
                return service._dto(asset, upload)
            raise SocialError('MEDIA_RETENTION_INVALID', 'The retained fence requires operator review.', 409)
        now = service.now()
        if asset.lease_expires_at and utc(asset.lease_expires_at) > now:
            raise SocialError('MEDIA_INSPECTION_BUSY', 'A media operation is still active.', 409, retryable=True)
        # Previously settled/cleaned history is not silently reclassified.
        if upload.grant_epoch < 1 or upload.grant_settled_epoch >= upload.grant_epoch or upload.pending_released:
            raise SocialError('MEDIA_RETENTION_INVALID', 'This historical upload requires separate inventory review.', 409)
        if any(b.pending_count < 1 or b.bytes_used < upload.reserved_bytes for b in budgets):
            raise SocialError('MEDIA_RETENTION_INVALID', 'The upload ledger requires operator review.', 409)
        upload.grant_renewal_deadline = min(utc(upload.grant_renewal_deadline), now)
        token = uuid4(); asset.lease_token = token; asset.lease_epoch += 1
        asset.lease_expires_at = now + timedelta(seconds=service.config.lease_seconds)
        epoch = asset.lease_epoch
        keys, size, digest, mime = (upload.quarantine_key, asset.storage_key), asset.byte_size, asset.sha256, asset.mime_type
        original_etag = asset.codec_metadata.get('storage_etag')
        original_version = asset.codec_metadata.get('storage_version')
        service._audit(actor, request_id, asset, 'media.retention_verification_started', 'ready')
    failure = None
    try:
        snapshots = []
        with tempfile.TemporaryDirectory(prefix='social-retention-') as directory:
            for index, key in enumerate(keys):
                snapshot = storage.head(key)
                if snapshot.size != size or snapshot.mime_type != mime or not snapshot.etag:
                    raise ValueError()
                if index == 1 and (snapshot.etag != original_etag or snapshot.version != original_version or snapshot.sha256 != digest):
                    raise ValueError()
                path = Path(directory) / str(index)
                storage.download(key, snapshot, path, size)
                if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    raise ValueError()
                snapshots.append(snapshot)
        with service.db.begin():
            budgets = service._budgets(actor)
            asset, upload = service._rows(asset_id)
            if (asset.state != 'ready' or not isinstance(asset.codec_metadata, dict)
                    or scope(asset, upload) != expected or asset.lease_token != token
                    or asset.lease_epoch != epoch or asset.lease_expires_at is None
                    or utc(asset.lease_expires_at) <= service.now()
                    or upload.quarantine_cleaned or upload.reservation_released
                    or upload.retained_write_fence is not None):
                raise SocialError('MEDIA_RETENTION_FENCED', 'This verification no longer owns the current upload.', 409)
            if any(b.pending_count < 1 or b.bytes_used < upload.reserved_bytes for b in budgets):
                raise SocialError('MEDIA_RETENTION_INVALID', 'The upload ledger changed during verification.', 409)
            upload.retained_write_fence = json.dumps({'version': 1,
                'scope_hash': expected, 'quarantine_etag': snapshots[0].etag,
                'original_etag': snapshots[1].etag}, sort_keys=True, separators=(',', ':'))
            service._release_pending(upload, budgets)
            asset.lease_token, asset.lease_expires_at = None, None
            service._audit(actor, request_id, asset, 'media.retained_fence_verified', 'ready')
            return service._dto(asset, upload)
    except Exception as error:
        failure = error if isinstance(error, SocialError) else None
    with service.db.begin():
        service._budgets(actor)
        asset, upload = service._rows(asset_id)
        if asset.lease_token == token and asset.lease_epoch == epoch:
            asset.lease_token, asset.lease_expires_at = None, None
    if failure is not None:
        raise failure
    raise SocialError('MEDIA_RETENTION_UNCONFIRMED', 'Retained copies could not be verified. Capacity remains held.', 503)


def recover_retained(service, actor, asset_id, body, request_id):
    body = RetainedRecovery.model_validate(body)
    if not service.config.retained_writes_enabled:
        raise SocialError('MEDIA_RECOVERY_UNAVAILABLE', 'Retained create-only recovery is unavailable.', 503)
    with service.db.begin():
        service._budgets(service._upload_actor(asset_id))
        asset, upload = service._rows(asset_id)
        if (upload.version, upload.grant_epoch, upload.finalization_epoch) != (body.expected_version, body.expected_grant_epoch, body.expected_finalization_epoch):
            raise SocialError('VERSION_CONFLICT', 'This recovery scope changed.')
        ready = asset.state == 'ready'
        key = upload.completion_key
        if key is None or (asset.state != 'ready' and
                (upload.finalization_epoch is None or upload.finalization_settled)):
            raise SocialError('MEDIA_RECOVERY_UNAVAILABLE', 'An existing unknown finalization is required.', 409)
    if ready:
        return retain_ready(service, actor, asset_id, body.expected_version, request_id)
    result = service._complete(actor, asset_id, key, body.expected_version, request_id,
        recover_unknown=True, recovery_scope=body)
    return retain_ready(service, actor, asset_id, result.version, request_id)
