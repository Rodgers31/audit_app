"""Bounded admin media commands. SQL transactions never encompass storage I/O."""
from datetime import timedelta
from pathlib import Path
import tempfile
from uuid import UUID, uuid4

from sqlalchemy import exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..contracts import canonical_hash
from ..models import SocialAuditEvent, SocialMediaAsset, SocialRevisionAsset
from ..service import SocialError, SocialService, utc, require_positive_version
from .contracts import MediaAssetDTO, MediaCapabilities, MediaLibrary, MediaPreview, UploadAuthorization, UploadIntent
from .inspection import InspectionFailure
from .models import SocialMediaBudget, SocialMediaUpload
from .storage import ObjectSnapshot, StorageFailure


class MediaService:
    def __init__(self, db, runtime):
        self.db, self.runtime, self.config = db, runtime, runtime.config.validate()

    def now(self):
        return SocialService(self.db).now()

    def capabilities(self):
        allowed = self.runtime.available_mimes()
        return MediaCapabilities(upload_available=bool(allowed), library_available=True, allowed_mime_types=allowed, max_image_bytes=self.config.max_image_bytes, max_video_bytes=self.config.max_video_bytes, unavailable_reason=None if allowed else self.runtime.unavailable_reason or 'Required media inspectors are unavailable.')

    def _storage(self):
        if not self.config.enabled or self.runtime.storage is None:
            raise SocialError('MEDIA_UNAVAILABLE', 'Private media storage is unavailable.', 503)
        return self.runtime.storage

    def _budgets(self, actor):
        # All mutations acquire global, actor, then asset/upload in this order.
        dialect = self.db.bind.dialect.name
        insert = pg_insert if dialect == 'postgresql' else sqlite_insert if dialect == 'sqlite' else None
        if insert is None:
            raise SocialError('MEDIA_UNAVAILABLE', 'The media database dialect is unsupported.', 503)
        scopes = ['global', 'actor:' + str(actor)]
        for scope in scopes:
            self.db.execute(insert(SocialMediaBudget).values(scope=scope, bytes_used=0, pending_count=0).on_conflict_do_nothing(index_elements=['scope']))
        return [self.db.scalar(select(SocialMediaBudget).where(SocialMediaBudget.scope == scope).with_for_update().execution_options(populate_existing=True)) for scope in scopes]

    def _rows(self, asset_id):
        asset = self.db.scalar(select(SocialMediaAsset).where(SocialMediaAsset.id == asset_id).with_for_update().execution_options(populate_existing=True))
        upload = self.db.scalar(select(SocialMediaUpload).where(SocialMediaUpload.asset_id == asset_id).with_for_update().execution_options(populate_existing=True))
        if asset is None or upload is None:
            raise SocialError('NOT_FOUND', 'This media upload was not found.', 404)
        return asset, upload

    def _audit(self, actor, request_id, asset, action, previous):
        self.db.add(SocialAuditEvent(actor_id=actor, actor_kind='admin' if actor else 'worker', action=action, previous_state=previous, new_state=asset.state, details={'asset_id': str(asset.id), 'lease_epoch': asset.lease_epoch}, request_id=str(request_id)))

    def _dto(self, asset, upload=None):
        return MediaAssetDTO(id=asset.id, version=upload.version if upload else 1, filename=asset.original_filename, state=asset.state, mime_type=asset.mime_type if asset.mime_type in {'image/jpeg', 'image/png', 'video/mp4'} else None, byte_size=asset.byte_size, sha256=asset.sha256, width=asset.width, height=asset.height, duration_ms=asset.duration_ms, default_alt_text=asset.default_alt_text, safe_error=asset.inspection_error, created_at=utc(asset.created_at))

    def initiate(self, actor, key, body, request_id):
        if not isinstance(actor, UUID) or not isinstance(key, UUID):
            raise SocialError('INVALID_REQUEST', 'Valid administrator and command identities are required.', 422)
        body = UploadIntent.model_validate(body)
        storage = self._storage()
        if body.declared_mime_type not in self.runtime.available_mimes():
            raise SocialError('MEDIA_INSPECTOR_UNAVAILABLE', 'An inspector for this media format is unavailable.', 503)
        maximum = self.config.max_video_bytes if body.declared_mime_type == 'video/mp4' else self.config.max_image_bytes
        if body.declared_size > maximum:
            raise SocialError('MEDIA_TOO_LARGE', 'This file exceeds the supported upload limit.', 422)
        digest = canonical_hash(body.model_dump(mode='json'))
        with self.db.begin():
            budgets = self._budgets(actor)
            upload = self.db.scalar(select(SocialMediaUpload).where(SocialMediaUpload.actor_id == actor, SocialMediaUpload.initiation_key == key))
            now = self.now()
            if upload:
                if upload.request_hash != digest:
                    raise SocialError('IDEMPOTENCY_CONFLICT', 'This upload command was already used with different content.')
                asset, upload = self._rows(upload.asset_id)
                if asset.state != 'pending' or utc(upload.expires_at) <= now:
                    raise SocialError('UPLOAD_NOT_PENDING', 'This upload has completed, failed or expired.')
            else:
                reservation = 2 * body.declared_size
                if budgets[0].bytes_used + reservation > self.config.total_quota_bytes or budgets[1].bytes_used + reservation > self.config.actor_quota_bytes or budgets[1].pending_count >= self.config.max_pending:
                    raise SocialError('MEDIA_QUOTA_EXCEEDED', 'The media budget or pending-upload limit has been reached.', 429)
                identity = uuid4()
                asset = SocialMediaAsset(id=identity, storage_provider=storage.provider, bucket=storage.bucket, storage_key=f'ready/{identity}/original', original_filename=body.filename, default_alt_text=body.alt_text, created_by=actor, state='pending', lease_epoch=0, codec_metadata={})
                upload = SocialMediaUpload(asset_id=identity, actor_id=actor, initiation_key=key, request_hash=digest, quarantine_key=f'quarantine/{actor}/{identity}/source', declared_mime_type=body.declared_mime_type, declared_size=body.declared_size, reserved_bytes=reservation, expires_at=now + timedelta(hours=self.config.orphan_hours), version=1, reservation_released=0, finalization_settled=0)
                self.db.add(asset); self.db.flush(); self.db.add(upload)
                for budget in budgets:
                    budget.bytes_used += reservation; budget.pending_count += 1
                self._audit(actor, request_id, asset, 'media.upload_initiated', None)
                self.db.flush()
            dto, quarantine, expiry = self._dto(asset, upload), upload.quarantine_key, utc(upload.expires_at)
            ttl = max(1, min(self.config.upload_ttl, int((expiry - now).total_seconds())))
        try:
            access = storage.authorize_upload(quarantine, body.declared_size, body.declared_mime_type, ttl)
        except StorageFailure:
            raise SocialError('MEDIA_STORAGE_UNAVAILABLE', 'Storage upload authorization is unavailable. Retry the same command.', 503, retryable=True) from None
        return UploadAuthorization(asset=dto, method='PUT', url=access.url, headers=access.headers, expires_at=now + timedelta(seconds=ttl))

    def complete(self, actor, asset_id, key, version, request_id):
        require_positive_version(version)
        if not all(isinstance(value, UUID) for value in (actor, asset_id, key)):
            raise SocialError('INVALID_REQUEST', 'Valid upload and command identities are required.', 422)
        storage = self._storage()
        digest = canonical_hash({'expected_version': version})
        with self.db.begin():
            self._budgets(actor)
            asset, upload = self._rows(asset_id)
            if upload.actor_id != actor:
                raise SocialError('PERMISSION_DENIED', 'Only the initiating administrator may complete this upload.', 403)
            if upload.completion_key is not None and (upload.completion_key != key or upload.completion_hash != digest):
                raise SocialError('IDEMPOTENCY_CONFLICT', 'Use the original completion command for this upload.')
            if asset.state == 'ready' and upload.completion_key == key:
                return self._dto(asset, upload)
            if upload.finalization_epoch is not None and not upload.finalization_settled:
                if asset.lease_expires_at and utc(asset.lease_expires_at) > self.now():
                    raise SocialError('MEDIA_INSPECTION_BUSY', 'This upload is being inspected. Retry the same command.', 409, retryable=True)
                raise SocialError('MEDIA_FINALIZATION_UNKNOWN', 'A storage creation could not be confirmed. Its quota remains reserved. Ask an administrator to reconcile this upload.', 503)
            if asset.state in {'failed', 'archived'}:
                raise SocialError('MEDIA_INSPECTION_FAILED' if asset.state == 'failed' else 'UPLOAD_EXPIRED', asset.inspection_error or 'This upload is no longer usable.', 422)
            if upload.version != version:
                raise SocialError('VERSION_CONFLICT', 'This media upload changed. Refresh before continuing.')
            now = self.now()
            if utc(upload.expires_at) <= now:
                raise SocialError('UPLOAD_EXPIRED', 'This media upload has expired.', 410)
            if asset.lease_expires_at and utc(asset.lease_expires_at) > now:
                raise SocialError('MEDIA_INSPECTION_BUSY', 'This upload is being inspected. Retry the same command.', 409, retryable=True)
            if upload.declared_mime_type not in self.runtime.available_mimes():
                raise SocialError('MEDIA_INSPECTOR_UNAVAILABLE', 'The required media inspector is unavailable.', 503)
            token = uuid4(); previous = asset.state
            upload.completion_key, upload.completion_hash = key, digest
            asset.state, asset.lease_token = 'inspecting', token
            asset.lease_epoch += 1
            asset.lease_expires_at = now + timedelta(seconds=self.config.lease_seconds)
            self._audit(actor, request_id, asset, 'media.inspection_started', previous)
            quarantine, final_key = upload.quarantine_key, asset.storage_key
            size, mime, epoch = upload.declared_size, upload.declared_mime_type, asset.lease_epoch
        try:
            with tempfile.TemporaryDirectory(prefix='social-media-') as directory:
                path = Path(directory) / 'original'
                snapshot = storage.head(quarantine)
                if snapshot.size != size:
                    raise InspectionFailure('Uploaded file length does not match the bounded intent.')
                storage.download(quarantine, snapshot, path, size)
                inspected = self.runtime.inspector.inspect(path, mime, size)
                # Fence immediately before external creation. An expired worker
                # may create an orphan, but cannot overwrite or mark it ready.
                with self.db.begin():
                    asset, upload = self._rows(asset_id)
                    self._fence(asset, token, epoch)
                    upload.finalization_epoch = epoch
                    upload.finalization_settled = 0
                final = storage.finalize(path, final_key, inspected.byte_size, inspected.mime_type, inspected.sha256)
                # Record known completion even when this worker lost its lease.
                # Cleanup cannot interpret expiry as proof remote I/O stopped.
                with self.db.begin():
                    asset, upload = self._rows(asset_id)
                    if upload.finalization_epoch == epoch:
                        upload.finalization_settled = 1
            with self.db.begin():
                budgets = self._budgets(actor)
                asset, upload = self._rows(asset_id)
                self._fence(asset, token, epoch)
                if upload.finalization_epoch == epoch and not upload.finalization_settled:
                    raise SocialError('MEDIA_FINALIZATION_UNKNOWN', 'A storage creation could not be confirmed. Its quota remains reserved. Ask an administrator to reconcile this upload.', 503) from None
                if final.size != inspected.byte_size or final.sha256 != inspected.sha256 or final.mime_type != inspected.mime_type or not final.etag:
                    raise StorageFailure('Finalized object identity is unconfirmed')
                for name in ('mime_type', 'byte_size', 'sha256', 'width', 'height', 'duration_ms', 'frame_rate'):
                    setattr(asset, name, getattr(inspected, name))
                asset.codec_metadata = {**inspected.codec_metadata, 'storage_etag': final.etag, 'storage_version': final.version}
                asset.state, asset.lease_token, asset.lease_expires_at = 'ready', None, None
                upload.version += 1
                for budget in budgets: budget.pending_count -= 1
                self._audit(actor, request_id, asset, 'media.inspection_ready', 'inspecting')
                result = self._dto(asset, upload)
            # Quarantine remains until bounded cleanup; its grant cannot address
            # the finalized key. Never let cleanup failure undo ready evidence.
            return result
        except (InspectionFailure, StorageFailure) as error:
            terminal = isinstance(error, InspectionFailure)
            with self.db.begin():
                budgets = self._budgets(actor)
                asset, upload = self._rows(asset_id)
                self._fence(asset, token, epoch)
                if upload.finalization_epoch == epoch and not upload.finalization_settled:
                    raise SocialError('MEDIA_FINALIZATION_UNKNOWN', 'A storage creation could not be confirmed. Its quota remains reserved. Ask an administrator to reconcile this upload.', 503) from None
                asset.state = 'failed' if terminal else 'pending'
                asset.inspection_error = 'Uploaded media failed byte, format or resource inspection.' if terminal else None
                asset.lease_token, asset.lease_expires_at = None, None
                if terminal:
                    upload.version += 1
                    for budget in budgets: budget.pending_count -= 1
                self._audit(actor, request_id, asset, 'media.inspection_failed' if terminal else 'media.storage_retry', 'inspecting')
            raise SocialError('MEDIA_INSPECTION_FAILED' if terminal else 'MEDIA_STORAGE_UNAVAILABLE', 'Uploaded media failed byte, format or resource inspection.' if terminal else 'Storage is unavailable. Retry the same completion command.', 422 if terminal else 503, retryable=not terminal) from None

    def _fence(self, asset, token, epoch):
        if asset.state != 'inspecting' or asset.lease_token != token or asset.lease_epoch != epoch or asset.lease_expires_at is None or utc(asset.lease_expires_at) <= self.now():
            raise SocialError('MEDIA_LEASE_LOST', 'Inspection ownership expired or changed. Retry the original completion command.', retryable=True)

    def library(self, page=1, page_size=20, query='', kind=None):
        if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 50 or not isinstance(query, str) or len(query) > 100 or kind not in {None, 'image', 'video'}:
            raise SocialError('INVALID_REQUEST', 'Invalid media library filters.', 422)
        with self.db.begin():
            conditions = [SocialMediaAsset.state == 'ready', SocialMediaAsset.deleted_at.is_(None), SocialMediaAsset.mime_type.in_(['image/jpeg', 'image/png', 'video/mp4'])]
            if query: conditions.append(SocialMediaAsset.original_filename.ilike('%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%', escape='\\'))
            if kind: conditions.append(SocialMediaAsset.mime_type.like(kind + '/%'))
            total = self.db.scalar(select(func.count()).select_from(SocialMediaAsset).where(*conditions))
            rows = self.db.execute(select(SocialMediaAsset, SocialMediaUpload).outerjoin(SocialMediaUpload, SocialMediaUpload.asset_id == SocialMediaAsset.id).where(*conditions).order_by(SocialMediaAsset.created_at.desc(), SocialMediaAsset.id).offset((page - 1) * page_size).limit(page_size)).all()
            return MediaLibrary(assets=tuple(self._dto(a, u) for a, u in rows), total=total, page=page, page_size=page_size, has_more=page * page_size < total)

    def preview(self, asset_id):
        storage = self._storage()
        with self.db.begin():
            asset = self.db.get(SocialMediaAsset, asset_id)
            if asset is None or asset.state != 'ready' or asset.deleted_at is not None:
                raise SocialError('NOT_FOUND', 'Ready media was not found.', 404)
            if asset.storage_provider != storage.provider or asset.bucket != storage.bucket:
                raise SocialError('MEDIA_UNAVAILABLE', 'This asset storage provider is unavailable.', 503)
            metadata = asset.codec_metadata or {}
            expected = ObjectSnapshot(asset.byte_size, metadata.get('storage_etag'), metadata.get('storage_version'), asset.sha256, asset.mime_type)
            if not expected.etag:
                raise SocialError('MEDIA_UNAVAILABLE', 'This asset has no verified immutable storage identity.', 503)
            dto = self._dto(asset, self.db.get(SocialMediaUpload, asset.id)); key = asset.storage_key; now = self.now()
        try:
            if storage.head(key) != expected:
                raise StorageFailure('Asset identity changed')
            access = storage.preview(key, expected, self.config.preview_ttl)
        except StorageFailure:
            raise SocialError('MEDIA_STORAGE_UNAVAILABLE', 'Verified private media preview is unavailable.', 503, retryable=True) from None
        return MediaPreview(asset=dto, url=access.url, expires_at=now + timedelta(seconds=self.config.preview_ttl))

    def cleanup(self, limit=20):
        """Scheduler port: remove expired quarantine/orphans, never ready originals.

        Ready retention requires a shared reference/deletion lock in the domain
        service. Until that is integrated, quota bounds total ready storage and
        ready originals are retained even when currently unreferenced.
        """
        if type(limit) is not int or not 1 <= limit <= 20:
            raise SocialError('INVALID_REQUEST', 'Cleanup batch must be between one and twenty.', 422)
        storage = self._storage()
        with self.db.begin():
            now = self.now()
            referenced = exists(select(SocialRevisionAsset.asset_id).where(SocialRevisionAsset.asset_id == SocialMediaUpload.asset_id))
            candidates = self.db.execute(select(SocialMediaUpload.asset_id, SocialMediaUpload.actor_id).join(SocialMediaAsset, SocialMediaAsset.id == SocialMediaUpload.asset_id).where(SocialMediaUpload.expires_at <= now, SocialMediaUpload.reservation_released == 0, SocialMediaUpload.quarantine_cleaned == 0, or_(SocialMediaUpload.finalization_epoch.is_(None), SocialMediaUpload.finalization_settled == 1), or_(SocialMediaAsset.lease_expires_at.is_(None), SocialMediaAsset.lease_expires_at <= now), or_(SocialMediaAsset.state == 'ready', ~referenced)).order_by(SocialMediaUpload.expires_at).limit(limit)).all()
        cleaned = 0
        for identity, actor in candidates:
            with self.db.begin():
                self._budgets(actor)
                asset, upload = self._rows(identity)
                # Candidate lists are snapshots. Another cleanup or completion
                # may have settled this reservation before these locks arrived.
                if upload.reservation_released or upload.quarantine_cleaned or utc(upload.expires_at) > self.now(): continue
                if upload.finalization_epoch is not None and not upload.finalization_settled: continue
                if asset.lease_expires_at and utc(asset.lease_expires_at) > self.now(): continue
                # Ready originals retain their budget. Only quarantine can be
                # deleted for ready rows; repeat DELETE is safely idempotent.
                ready = asset.state == 'ready'
                if not ready and self.db.scalar(select(SocialRevisionAsset.asset_id).where(SocialRevisionAsset.asset_id == identity).limit(1)) is not None: continue
                token = uuid4(); asset.lease_token = token; asset.lease_epoch += 1
                asset.lease_expires_at = self.now() + timedelta(seconds=self.config.lease_seconds)
                epoch = asset.lease_epoch
                keys = [upload.quarantine_key] if ready else [upload.quarantine_key, asset.storage_key]
                if not ready: asset.state = 'archived'
            try:
                for key in keys: storage.delete(key)
            except StorageFailure:
                continue
            with self.db.begin():
                budgets = self._budgets(actor)
                asset, upload = self._rows(identity)
                if upload.reservation_released or upload.quarantine_cleaned or asset.lease_token != token or asset.lease_epoch != epoch or asset.lease_expires_at is None or utc(asset.lease_expires_at) <= self.now(): continue
                asset.lease_token, asset.lease_expires_at = None, None
                upload.quarantine_cleaned = 1
                if not ready:
                    # pending_count may include crashed inspections; failed rows
                    # were already released on their terminal inspection.
                    if upload.version == 1:
                        for budget in budgets: budget.pending_count -= 1
                    for budget in budgets: budget.bytes_used -= upload.reserved_bytes
                    upload.reserved_bytes = 0
                    upload.reservation_released = 1
                    upload.version += 1; asset.deleted_at = self.now()
                else:
                    for budget in budgets: budget.bytes_used -= upload.declared_size
                    upload.reserved_bytes -= upload.declared_size
                self._audit(None, uuid4(), asset, 'media.quarantine_cleaned' if ready else 'media.orphan_cleaned', 'ready' if ready else 'archived')
                cleaned += 1
        return cleaned
