"""Bounded read-only database observations for preparing media reconciliation.

No object I/O, receipt verification, quota repair or settlement is performed.
Each page uses one repeatable-read transaction on PostgreSQL. Pages are separate
observations; versions must be rechecked by the existing reconciliation port.
"""
from datetime import datetime
from typing import Annotated, Literal, Optional
from uuid import UUID

from pydantic import Field
from sqlalchemy import String, and_, case, cast, exists, func, or_, select, text

from ..contracts import StrictModel
from ..models import SocialMediaAsset, SocialRevisionAsset
from ..service import SocialError, utc
from .models import SocialMediaBudget, SocialMediaUpload

Count = Annotated[int, Field(strict=True, ge=0)]


class UploadObservation(StrictModel):
    asset_id: UUID
    upload_version: int
    grant_epoch: int
    grant_settled_epoch: int
    finalization_epoch: Optional[int]
    finalization_settled: bool
    grant_expires_at: Optional[datetime]
    grant_renewal_deadline: datetime
    orphan_expires_at: datetime
    lease_epoch: int
    lease_expires_at: Optional[datetime]
    state: str
    storage_provider: str
    bucket: str
    declared_size: Count
    reserved_bytes: Count
    pending_held: bool
    quarantine_cleaned: bool
    reservation_released: bool
    historically_referenced: bool
    actor_ledger_present: bool
    actor_ledger_bytes: Count
    actor_ledger_pending: Count
    actor_upload_reserved_bytes: Count
    actor_upload_pending: Count
    reason_codes: tuple[str, ...]


class OperatorReport(StrictModel):
    purpose: Literal['social_media_490'] = 'social_media_490'
    observation_scope: Literal['database_only'] = 'database_only'
    observed_at: datetime
    global_ledger_present: bool
    ledger_reserved_bytes: Count
    ledger_pending_uploads: Count
    upload_reserved_bytes: Count
    upload_pending_held: Count
    actor_ledger_discrepancies: Count
    assets_without_upload_ledger: Count
    legacy_released_write_hazards: Count
    total_quota_bytes: Count
    actor_quota_bytes: Count
    max_actor_pending: Count
    reason_codes: tuple[str, ...]
    uploads: Annotated[tuple[UploadObservation, ...], Field(max_length=20)]
    next_after_asset_id: Optional[UUID]
    write_quiescence_proven: Literal[False] = False
    quota_release_authorized: Literal[False] = False
    ready_original_deletion_authorized: Literal[False] = False


def _actor_match(scope, actor, dialect):
    # UUID storage is hyphenated on PostgreSQL and hex-only on SQLite fixtures.
    identity = cast(actor, String)
    if dialect == 'sqlite':
        identity = func.substr(identity, 1, 8) + '-' + func.substr(identity, 9, 4) + '-' + func.substr(identity, 13, 4) + '-' + func.substr(identity, 17, 4) + '-' + func.substr(identity, 21, 12)
    return scope == 'actor:' + identity


def prepare_reconciliation(service, *, limit=20, after_asset_id=None):
    if type(limit) is not int or not 1 <= limit <= 20 or (after_asset_id is not None and type(after_asset_id) is not UUID):
        raise SocialError('INVALID_REQUEST', 'Use a batch of one to twenty and an optional UUID cursor.', 422)
    db = service.db
    if db.new or db.dirty or db.deleted:
        raise SocialError('INVALID_REQUEST', 'Read-only preparation requires a clean session.', 422)
    dialect = db.bind.dialect.name
    with db.begin():
        if db.bind.dialect.name == 'postgresql':
            db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
            db.execute(text("SET LOCAL statement_timeout = '5s'"))
        now = service.now()
        pending = case((SocialMediaUpload.pending_released == 0, 1), else_=0)
        expected = select(
            SocialMediaUpload.actor_id.label('actor'),
            func.sum(SocialMediaUpload.reserved_bytes).label('bytes'),
            func.sum(pending).label('pending'),
        ).group_by(SocialMediaUpload.actor_id).subquery()
        matched = _actor_match(SocialMediaBudget.scope, expected.c.actor, dialect)
        missing_or_wrong = select(func.count()).select_from(expected).outerjoin(SocialMediaBudget, matched).where(or_(
            SocialMediaBudget.scope.is_(None), SocialMediaBudget.bytes_used != expected.c.bytes,
            SocialMediaBudget.pending_count != expected.c.pending,
        )).scalar_subquery()
        surplus = select(func.count()).select_from(SocialMediaBudget).where(
            SocialMediaBudget.scope != 'global',
            ~exists(select(expected.c.actor).where(matched)),
        ).scalar_subquery()
        ledger = select(SocialMediaBudget.bytes_used, SocialMediaBudget.pending_count).where(SocialMediaBudget.scope == 'global').subquery()
        unknown = or_(SocialMediaUpload.grant_settled_epoch < SocialMediaUpload.grant_epoch,
                      and_(SocialMediaUpload.finalization_epoch.is_not(None), SocialMediaUpload.finalization_settled == 0))
        totals = db.execute(select(
            func.coalesce(func.sum(SocialMediaUpload.reserved_bytes), 0),
            func.coalesce(func.sum(pending), 0),
            func.coalesce(func.sum(case((and_(unknown, or_(SocialMediaUpload.reservation_released == 1,
                SocialMediaUpload.pending_released == 1, SocialMediaUpload.reserved_bytes < 2 * SocialMediaUpload.declared_size)), 1), else_=0)), 0),
            missing_or_wrong + surplus,
            select(func.count()).select_from(SocialMediaAsset).where(~exists(select(SocialMediaUpload.asset_id).where(
                SocialMediaUpload.asset_id == SocialMediaAsset.id))).scalar_subquery(),
            select(ledger.c.bytes_used).scalar_subquery(),
            select(ledger.c.pending_count).scalar_subquery(),
        ).select_from(SocialMediaUpload)).one()
        reasons = []
        if totals[5] is None:
            reasons.append('GLOBAL_LEDGER_MISSING')
        if totals[0] != (totals[5] or 0) or totals[1] != (totals[6] or 0):
            reasons.append('GLOBAL_LEDGER_MISMATCH')
        if totals[3]: reasons.append('ACTOR_LEDGER_MISMATCH')
        if totals[2]: reasons.append('LEGACY_WRITE_ACCOUNTING_GAP')
        if totals[4]: reasons.append('ASSETS_WITHOUT_UPLOAD_LEDGER')
        if (totals[5] or 0) > service.config.total_quota_bytes: reasons.append('GLOBAL_QUOTA_EXCEEDED')
        referenced = exists(select(SocialRevisionAsset.asset_id).where(SocialRevisionAsset.asset_id == SocialMediaUpload.asset_id))
        query = select(SocialMediaAsset, SocialMediaUpload, referenced,
                       SocialMediaBudget.scope, SocialMediaBudget.bytes_used, SocialMediaBudget.pending_count,
                       expected.c.bytes, expected.c.pending).join(
            SocialMediaUpload, SocialMediaAsset.id == SocialMediaUpload.asset_id).join(
            expected, expected.c.actor == SocialMediaUpload.actor_id).outerjoin(
            SocialMediaBudget, _actor_match(SocialMediaBudget.scope, SocialMediaUpload.actor_id, dialect)
        ).order_by(SocialMediaUpload.asset_id).limit(limit + 1).execution_options(populate_existing=True)
        if after_asset_id is not None: query = query.where(SocialMediaUpload.asset_id > after_asset_id)
        rows = db.execute(query).all()
        uploads = []
        for asset, upload, protected, actor_scope, actor_bytes, actor_pending, expected_bytes, expected_pending in rows[:limit]:
            codes = []
            storage = service.runtime.storage
            if not service.config.enabled or storage is None: codes.append('STORAGE_UNAVAILABLE')
            elif (asset.storage_provider, asset.bucket) != (storage.provider, storage.bucket): codes.append('STORAGE_TARGET_MISMATCH')
            if actor_scope is None or (actor_bytes, actor_pending) != (expected_bytes, expected_pending): codes.append('ACTOR_LEDGER_MISMATCH')
            if (actor_bytes or 0) > service.config.actor_quota_bytes or (actor_pending or 0) > service.config.max_pending: codes.append('ACTOR_QUOTA_EXCEEDED')
            if asset.lease_expires_at and utc(asset.lease_expires_at) > now: codes.append('ACTIVE_LEASE')
            if protected and asset.state != 'ready': codes.append('HISTORICAL_REFERENCE_PROTECTED')
            if upload.grant_settled_epoch < upload.grant_epoch: codes.append('BROWSER_WRITE_PROOF_REQUIRED')
            if upload.finalization_epoch is not None and not upload.finalization_settled: codes.append('SERVER_WRITE_PROOF_REQUIRED')
            if upload.reservation_released and ('BROWSER_WRITE_PROOF_REQUIRED' in codes or 'SERVER_WRITE_PROOF_REQUIRED' in codes): codes.append('LEGACY_RELEASED_WRITE_HAZARD')
            if utc(upload.expires_at) > now: codes.append('ORPHAN_DEADLINE_NOT_REACHED')
            if upload.quarantine_cleaned or upload.reservation_released: codes.append('PRIOR_CLEANUP_REQUIRES_INVENTORY')
            if not codes: codes.append('SETTLED_QUARANTINE_CLEANUP_CANDIDATE' if asset.state == 'ready' else 'SETTLED_ORPHAN_CLEANUP_CANDIDATE')
            uploads.append(UploadObservation(
                asset_id=asset.id, upload_version=upload.version, grant_epoch=upload.grant_epoch,
                grant_settled_epoch=upload.grant_settled_epoch, finalization_epoch=upload.finalization_epoch,
                finalization_settled=bool(upload.finalization_settled), grant_expires_at=utc(upload.grant_expires_at) if upload.grant_expires_at else None,
                grant_renewal_deadline=utc(upload.grant_renewal_deadline), orphan_expires_at=utc(upload.expires_at),
                lease_epoch=asset.lease_epoch, lease_expires_at=utc(asset.lease_expires_at) if asset.lease_expires_at else None,
                state=asset.state, storage_provider=asset.storage_provider, bucket=asset.bucket,
                declared_size=upload.declared_size, reserved_bytes=upload.reserved_bytes, pending_held=not upload.pending_released,
                quarantine_cleaned=bool(upload.quarantine_cleaned), reservation_released=bool(upload.reservation_released),
                historically_referenced=bool(protected), actor_ledger_present=actor_scope is not None,
                actor_ledger_bytes=actor_bytes or 0, actor_ledger_pending=actor_pending or 0,
                actor_upload_reserved_bytes=int(expected_bytes), actor_upload_pending=int(expected_pending), reason_codes=tuple(codes),
            ))
        return OperatorReport(observed_at=now, global_ledger_present=totals[5] is not None,
            ledger_reserved_bytes=totals[5] or 0, ledger_pending_uploads=totals[6] or 0,
            upload_reserved_bytes=int(totals[0]), upload_pending_held=int(totals[1]),
            legacy_released_write_hazards=int(totals[2]), actor_ledger_discrepancies=int(totals[3]),
            assets_without_upload_ledger=int(totals[4]), total_quota_bytes=service.config.total_quota_bytes,
            actor_quota_bytes=service.config.actor_quota_bytes, max_actor_pending=service.config.max_pending,
            reason_codes=tuple(reasons), uploads=tuple(uploads),
            next_after_asset_id=uploads[-1].asset_id if len(rows) > limit else None)
