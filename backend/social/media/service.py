"""Bounded admin media commands. SQL transactions never encompass storage I/O."""
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
from uuid import UUID, uuid4

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..contracts import canonical_hash
from ..models import SocialAuditEvent, SocialMediaAsset, SocialRevisionAsset
from ..service import SocialError, SocialService, utc, require_positive_version
from .contracts import MaintenanceBacklog, MediaAssetDTO, MediaCapabilities, MediaLibrary, MediaPreview, UploadAuthorization, UploadIntent
from .inspection import InspectionFailure
from .models import SocialMediaBudget, SocialMediaUpload
from .storage import ObjectSnapshot, StorageFailure
from .reconciliation import ReconcileUpload, WriteQuiescenceEvidence, WriteQuiescenceScope


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

    def initiate(self, actor, key, body, request_id, *, _grant_retries=0):
        if type(_grant_retries) is not int or not 0 <= _grant_retries <= 2:
            raise SocialError('INVALID_REQUEST', 'Local grant retries must be bounded.', 422)
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
                if utc(upload.grant_renewal_deadline) <= now:
                    raise SocialError('UPLOAD_GRANT_EXPIRED', 'The original upload authorization window has ended.', 410)
            else:
                reservation = 2 * body.declared_size
                if budgets[0].bytes_used + reservation > self.config.total_quota_bytes or budgets[1].bytes_used + reservation > self.config.actor_quota_bytes or budgets[1].pending_count >= self.config.max_pending:
                    raise SocialError('MEDIA_QUOTA_EXCEEDED', 'The media budget or pending-upload limit has been reached.', 429)
                identity = uuid4()
                asset = SocialMediaAsset(id=identity, storage_provider=storage.provider, bucket=storage.bucket, storage_key=f'ready/{identity}/original', original_filename=body.filename, default_alt_text=body.alt_text, created_by=actor, state='pending', lease_epoch=0, codec_metadata={})
                upload = SocialMediaUpload(asset_id=identity, actor_id=actor, initiation_key=key, request_hash=digest, quarantine_key=f'quarantine/{actor}/{identity}/source', declared_mime_type=body.declared_mime_type, declared_size=body.declared_size, reserved_bytes=reservation, expires_at=now + timedelta(hours=self.config.orphan_hours), grant_renewal_deadline=now + timedelta(seconds=self.config.upload_ttl), grant_epoch=0, grant_settled_epoch=0, pending_released=0, version=1, reservation_released=0, finalization_settled=0)
                self.db.add(asset); self.db.flush(); self.db.add(upload)
                for budget in budgets:
                    budget.bytes_used += reservation; budget.pending_count += 1
                self._audit(actor, request_id, asset, 'media.upload_initiated', None)
                self.db.flush()
            quarantine = upload.quarantine_key
            ttl = min(self.config.upload_ttl, int((utc(upload.grant_renewal_deadline) - now).total_seconds()))
            if ttl < 1:
                raise SocialError('UPLOAD_GRANT_EXPIRED', 'The original upload authorization window has ended.', 410)
            # Commit uncertainty before signing. A signer crash, or an earlier
            # bearer used by another browser, cannot silently discard a hazard.
            upload.grant_epoch += 1
            upload.grant_expires_at = None
            upload.write_quiescence_receipt_hash = None
            identity, epoch, version = asset.id, upload.grant_epoch, upload.version
        try:
            access = storage.authorize_upload(quarantine, body.declared_size, body.declared_mime_type, ttl)
        except StorageFailure:
            raise SocialError('MEDIA_STORAGE_UNAVAILABLE', 'Storage upload authorization is unavailable. Retry the same command.', 503, retryable=True) from None
        if not isinstance(access.expires_at, datetime) or access.expires_at.tzinfo is None or access.expires_at.utcoffset() is None:
            raise SocialError('MEDIA_STORAGE_UNAVAILABLE', 'Storage did not confirm the upload signature expiration.', 503)
        with self.db.begin():
            self._budgets(actor)
            asset, upload = self._rows(identity)
            now = self.now()
            if asset.state != 'pending' or upload.version != version:
                raise SocialError('MEDIA_GRANT_FENCED', 'This authorization changed before it could be returned. Retry the original command.', retryable=True)
            superseded = upload.grant_epoch != epoch
            expiry = utc(access.expires_at)
            if expiry <= now or expiry > utc(upload.grant_renewal_deadline) or utc(upload.grant_renewal_deadline) <= now:
                raise SocialError('UPLOAD_GRANT_EXPIRED', 'The signed authorization exceeded the original upload window.', 410)
            if not superseded:
                upload.grant_expires_at = expiry
                dto = self._dto(asset, upload)
        if superseded:
            # Concurrent same-intent retries may supersede a local signer. Its
            # unreturned URL never escapes; resubmit the same durable intent a
            # bounded number of times, without creating a second reservation.
            if _grant_retries >= 2:
                raise SocialError('MEDIA_GRANT_FENCED', 'Another authorization is being issued. Retry the original command.', retryable=True)
            return self.initiate(actor, key, body, request_id, _grant_retries=_grant_retries + 1)
        return UploadAuthorization(asset=dto, method='PUT', url=access.url, headers=access.headers, expires_at=expiry)

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
                # Ready bytes do not prove an earlier browser PUT has stopped.
                # Pending capacity remains until write quiescence and cleanup.
                if upload.grant_settled_epoch == upload.grant_epoch:
                    self._release_pending(upload, budgets)
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
                    if upload.grant_settled_epoch == upload.grant_epoch:
                        self._release_pending(upload, budgets)
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
            dto = self._dto(asset, self.db.get(SocialMediaUpload, asset.id)); key = asset.storage_key
        try:
            if storage.head(key) != expected:
                raise StorageFailure('Asset identity changed')
            access = storage.preview(key, expected, self.config.preview_ttl)
        except StorageFailure:
            raise SocialError('MEDIA_STORAGE_UNAVAILABLE', 'Verified private media preview is unavailable.', 503, retryable=True) from None
        if not isinstance(access.expires_at, datetime) or access.expires_at.tzinfo is None or access.expires_at.utcoffset() is None:
            raise SocialError('MEDIA_STORAGE_UNAVAILABLE', 'Storage did not confirm the preview signature expiration.', 503)
        return MediaPreview(asset=dto, url=access.url, expires_at=access.expires_at)

    def _release_pending(self, upload, budgets):
        if not upload.pending_released:
            for budget in budgets:
                budget.pending_count -= 1
            upload.pending_released = 1

    @staticmethod
    def _scope(asset, upload):
        return WriteQuiescenceScope(asset_id=asset.id, storage_provider=asset.storage_provider, bucket=asset.bucket, upload_version=upload.version, grant_epoch=upload.grant_epoch, grant_expires_at=utc(upload.grant_expires_at) if upload.grant_expires_at else None, finalization_epoch=upload.finalization_epoch)

    def _referenced(self, identity):
        return self.db.scalar(select(SocialRevisionAsset.asset_id).where(SocialRevisionAsset.asset_id == identity).limit(1)) is not None

    def reconcile(self, actor, asset_id, body, request_id):
        """Freeze renewal; accept only an injected verifier's scoped evidence.

        A failed verification leaves renewal frozen and quota reserved. The
        returned asset/version permits an operator to inspect/retry explicitly;
        no known outcome is converted into automatic grant renewal or reupload.
        """
        if not all(isinstance(value, UUID) for value in (actor, asset_id, request_id)):
            raise SocialError('INVALID_REQUEST', 'Valid operator and media identities are required.', 422)
        body = ReconcileUpload.model_validate(body)
        self._storage()
        with self.db.begin():
            self._budgets(self._upload_actor(asset_id))
            asset, upload = self._rows(asset_id)
            if upload.version != body.expected_version or upload.grant_epoch != body.expected_grant_epoch or upload.finalization_epoch != body.expected_finalization_epoch:
                raise SocialError('VERSION_CONFLICT', 'This media upload changed before reconciliation.')
            now = self.now()
            # A legacy ready cleanup can precede the end of an admitted PUT.
            # Its old delete marker cannot prove the quarantine stayed absent.
            legacy_ready_cleanup = bool(upload.quarantine_cleaned and asset.state == 'ready')
            recoverable_ready_cleanup = legacy_ready_cleanup and (
                upload.grant_settled_epoch < upload.grant_epoch
                or (upload.finalization_epoch is not None and not upload.finalization_settled)
                or not upload.pending_released)
            if upload.reservation_released or (upload.quarantine_cleaned and not recoverable_ready_cleanup):
                raise SocialError('UPLOAD_NOT_PENDING', 'This upload has already been cleaned.')
            if asset.lease_expires_at and utc(asset.lease_expires_at) > now:
                raise SocialError('MEDIA_INSPECTION_BUSY', 'A media operation is still active.', retryable=True)
            if asset.state != 'ready' and self._referenced(asset.id):
                raise SocialError('MEDIA_REFERENCED', 'Historical revision evidence protects this original.')
            previous = asset.state
            upload.grant_renewal_deadline = min(utc(upload.grant_renewal_deadline), now)
            upload.version += 1
            token = uuid4()
            asset.lease_token = token
            asset.lease_epoch += 1
            asset.lease_expires_at = now + timedelta(seconds=self.config.lease_seconds)
            scope, epoch, uploader = self._scope(asset, upload), asset.lease_epoch, upload.actor_id
            self._audit(actor, request_id, asset, 'media.reconciliation_started', previous)
        try:
            evidence = self.runtime.write_quiescence_verifier.verify(scope, body.receipt)
            if not isinstance(evidence, WriteQuiescenceEvidence):
                raise SocialError('MEDIA_WRITE_QUIESCENCE_UNCONFIRMED', 'Trusted evidence that all outstanding writes stopped is unavailable.', 503)
            evidence = WriteQuiescenceEvidence.model_validate(evidence)
            if evidence.scope != scope or evidence.receipt != body.receipt:
                raise SocialError('MEDIA_WRITE_QUIESCENCE_UNCONFIRMED', 'Trusted evidence that all outstanding writes stopped is unavailable.', 503)
            with self.db.begin():
                self._budgets(uploader)
                asset, upload = self._rows(asset_id)
                current = self.now()
                if self._scope(asset, upload) != scope or asset.state != previous or asset.lease_token != token or asset.lease_epoch != epoch or asset.lease_expires_at is None or utc(asset.lease_expires_at) <= current:
                    raise SocialError('MEDIA_RECONCILIATION_FENCED', 'This media reconciliation no longer owns the current state.')
                # SQLite fixtures expose second-precision time; PostgreSQL
                # production comparisons retain their precise database clock.
                clock_precision = timedelta(seconds=1) if self.db.bind.dialect.name == 'sqlite' else timedelta(0)
                if evidence.verified_at < now or evidence.verified_at > current + clock_precision:
                    raise SocialError('MEDIA_WRITE_QUIESCENCE_UNCONFIRMED', 'Write settlement evidence is stale or future dated.', 503)
                if asset.state != 'ready' and self._referenced(asset.id):
                    raise SocialError('MEDIA_REFERENCED', 'Historical revision evidence protects this original.')
                upload.grant_settled_epoch = upload.grant_epoch
                if upload.finalization_epoch is not None:
                    upload.finalization_settled = 1
                upload.write_quiescence_receipt_hash = body.receipt.evidence_hash
                if legacy_ready_cleanup:
                    # Scoped quiescence permits another DELETE, not a release
                    # based on a historical acknowledgement. Ledger stays held.
                    upload.quarantine_cleaned = 0
                if asset.state != 'ready':
                    asset.state = 'archived'
                asset.lease_token, asset.lease_expires_at = None, None
                self.db.add(SocialAuditEvent(actor_id=actor, actor_kind='admin', action='media.writes_reconciled', previous_state=previous, new_state=asset.state, details={'asset_id': str(asset.id), 'grant_epoch': scope.grant_epoch, 'finalization_epoch': scope.finalization_epoch, 'receipt_id': str(body.receipt.receipt_id), 'evidence_hash': body.receipt.evidence_hash}, request_id=str(request_id)))
                return self._dto(asset, upload)
        except Exception as error:
            with self.db.begin():
                self._budgets(uploader)
                asset, upload = self._rows(asset_id)
                if asset.lease_token == token and asset.lease_epoch == epoch:
                    asset.lease_token, asset.lease_expires_at = None, None
            if isinstance(error, SocialError):
                raise
            raise SocialError('MEDIA_WRITE_QUIESCENCE_UNCONFIRMED', 'Trusted write settlement verification failed. Quota remains reserved.', 503) from None

    def _upload_actor(self, asset_id):
        actor = self.db.scalar(select(SocialMediaUpload.actor_id).where(SocialMediaUpload.asset_id == asset_id))
        if actor is None:
            raise SocialError('NOT_FOUND', 'This media upload was not found.', 404)
        return actor

    def _cleanup_conditions(self, now):
        referenced = exists(select(SocialRevisionAsset.asset_id).where(SocialRevisionAsset.asset_id == SocialMediaUpload.asset_id))
        return [SocialMediaUpload.expires_at <= now, SocialMediaUpload.reservation_released == 0, SocialMediaUpload.quarantine_cleaned == 0, SocialMediaUpload.grant_settled_epoch == SocialMediaUpload.grant_epoch, or_(SocialMediaUpload.finalization_epoch.is_(None), SocialMediaUpload.finalization_settled == 1), or_(SocialMediaAsset.lease_expires_at.is_(None), SocialMediaAsset.lease_expires_at <= now), or_(SocialMediaAsset.state == 'ready', ~referenced)]

    def backlog(self):
        """One aggregate and one compact ledger read; no keys, grants or bodies."""
        with self.db.begin():
            now = self.now()
            referenced = exists(select(SocialRevisionAsset.asset_id).where(SocialRevisionAsset.asset_id == SocialMediaUpload.asset_id))
            storage = self.runtime.storage
            eligible = self._cleanup_conditions(now) + ([SocialMediaAsset.storage_provider == storage.provider, SocialMediaAsset.bucket == storage.bucket] if self.config.enabled and storage is not None else [False])
            counts = self.db.execute(select(
                func.coalesce(func.sum(case((and_(*eligible), 1), else_=0)), 0),
                func.coalesce(func.sum(case((SocialMediaUpload.grant_settled_epoch < SocialMediaUpload.grant_epoch, 1), else_=0)), 0),
                func.coalesce(func.sum(case((and_(SocialMediaUpload.finalization_epoch.is_not(None), SocialMediaUpload.finalization_settled == 0), 1), else_=0)), 0),
                func.coalesce(func.sum(case((SocialMediaAsset.lease_expires_at > now, 1), else_=0)), 0),
                func.coalesce(func.sum(case((referenced, 1), else_=0)), 0),
                func.min(case((and_(SocialMediaUpload.expires_at <= now, SocialMediaUpload.reservation_released == 0, SocialMediaUpload.quarantine_cleaned == 0), SocialMediaUpload.expires_at), else_=None)),
            ).select_from(SocialMediaUpload).join(SocialMediaAsset, SocialMediaAsset.id == SocialMediaUpload.asset_id)).one()
            ledger = self.db.get(SocialMediaBudget, 'global')
            return MaintenanceBacklog(eligible_cleanup=int(counts[0]), unknown_browser_writes=int(counts[1]), unknown_finalizations=int(counts[2]), active_leases=int(counts[3]), protected_references=int(counts[4]), reserved_bytes=ledger.bytes_used if ledger else 0, pending_uploads=ledger.pending_count if ledger else 0, oldest_orphan_at=utc(counts[5]) if counts[5] else None)

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
            candidates = self.db.execute(select(SocialMediaUpload.asset_id, SocialMediaUpload.actor_id).join(SocialMediaAsset, SocialMediaAsset.id == SocialMediaUpload.asset_id).where(*self._cleanup_conditions(now), SocialMediaAsset.storage_provider == storage.provider, SocialMediaAsset.bucket == storage.bucket).order_by(SocialMediaUpload.expires_at, SocialMediaUpload.asset_id).limit(limit)).all()
        cleaned = 0
        for identity, actor in candidates:
            with self.db.begin():
                self._budgets(actor)
                asset, upload = self._rows(identity)
                # Candidate lists are snapshots. Another cleanup or completion
                # may have settled this reservation before these locks arrived.
                if upload.reservation_released or upload.quarantine_cleaned or utc(upload.expires_at) > self.now(): continue
                if upload.finalization_epoch is not None and not upload.finalization_settled: continue
                if upload.grant_settled_epoch != upload.grant_epoch: continue
                if asset.storage_provider != storage.provider or asset.bucket != storage.bucket: continue
                if asset.lease_expires_at and utc(asset.lease_expires_at) > self.now(): continue
                # Ready originals retain their budget. Only quarantine can be
                # deleted for ready rows; repeat DELETE is safely idempotent.
                ready = asset.state == 'ready'
                if not ready and self._referenced(identity): continue
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
                    self._release_pending(upload, budgets)
                    for budget in budgets: budget.bytes_used -= upload.reserved_bytes
                    upload.reserved_bytes = 0
                    upload.reservation_released = 1
                    upload.version += 1; asset.deleted_at = self.now()
                else:
                    # Legacy ready cleanup may already have released the
                    # quarantine copy. Never subtract its original a second time.
                    released_bytes = min(upload.declared_size, max(0, upload.reserved_bytes - upload.declared_size))
                    for budget in budgets: budget.bytes_used -= released_bytes
                    upload.reserved_bytes -= released_bytes
                    self._release_pending(upload, budgets)
                self._audit(None, uuid4(), asset, 'media.quarantine_cleaned' if ready else 'media.orphan_cleaned', 'ready' if ready else 'archived')
                cleaned += 1
        return cleaned
