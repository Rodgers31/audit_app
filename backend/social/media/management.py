"""Metadata-only library archive. Never calls storage or releases accounting."""
from uuid import UUID

from sqlalchemy import func, select, text

from ..contracts import canonical_hash
from ..models import SocialAuditEvent, SocialMediaAsset, SocialPost, SocialPostRevision, SocialRevisionAsset
from ..service import SocialError, SocialService
from .contracts import ArchiveMedia, MediaAssetDTO, MediaReference, MediaUsage
from .models import SocialMediaDeletion, SocialMediaUpload, SocialMediaWriteOwner


def _reason(svc, asset, upload, references):
    if references:
        return 'Historical revisions reference this asset. Their evidence must be retained.'
    if svc.db.scalar(select(SocialMediaAsset.id).where(SocialMediaAsset.parent_asset_id == asset.id).limit(1)) is not None:
        return 'Derived assets still depend on this original.'
    if asset.state != 'ready' or asset.deleted_at is not None:
        return 'Only ready, retained assets can be archived.'
    if (asset.lease_token is not None or asset.lease_expires_at is not None or
            upload.finalization_settled != 1 or
            upload.grant_settled_epoch != upload.grant_epoch or not upload.write_quiescence_receipt_hash):
        return 'Upload or write ownership remains unsettled. Use the existing recovery workflow first.'
    if svc.db.scalar(select(SocialMediaWriteOwner.asset_id).where(
            SocialMediaWriteOwner.asset_id == asset.id, SocialMediaWriteOwner.state != 'settled').limit(1)) is not None:
        return 'Write ownership remains unsettled.'
    if svc.db.scalar(select(SocialMediaDeletion.operation_id).where(
            SocialMediaDeletion.asset_id == asset.id, SocialMediaDeletion.state != 'complete').limit(1)) is not None:
        return 'A privacy retirement operation remains unsettled.'
    return None


def asset_usage(svc, identity, page=1, page_size=20):
    if not isinstance(identity, UUID) or not identity.int or type(page) is not int or not 1 <= page <= 1_000_000 or type(page_size) is not int or not 1 <= page_size <= 50:
        raise SocialError('INVALID_REQUEST', 'Valid media identity and bounded pagination are required.', 422)
    with svc.db.begin():
        # Reference creation holds this same asset lock before inserting edges.
        asset, upload = svc._rows(identity)
        total = svc.db.scalar(select(func.count()).select_from(SocialRevisionAsset).where(SocialRevisionAsset.asset_id == identity))
        rows = svc.db.execute(select(SocialPost.id, SocialPost.title, SocialPostRevision.id.label('revision_id'), SocialPostRevision.revision_no)
            .join(SocialPostRevision, SocialPostRevision.post_id == SocialPost.id)
            .join(SocialRevisionAsset, SocialRevisionAsset.revision_id == SocialPostRevision.id)
            .where(SocialRevisionAsset.asset_id == identity)
            .order_by(SocialPostRevision.created_at.desc(), SocialPostRevision.id)
            .offset((page - 1) * page_size).limit(page_size)).all()
        reason = _reason(svc, asset, upload, total)
        return MediaUsage(asset=svc._dto(asset, upload), references=tuple(MediaReference(
            post_id=r.id, title=r.title, revision_id=r.revision_id, revision_no=r.revision_no) for r in rows),
            total=total, page=page, page_size=page_size, has_more=page * page_size < total,
            archive_eligible=reason is None, archive_reason=reason or 'Unused asset can be hidden from the library. Objects, quota and history remain retained.')


def archive_asset(svc, actor, identity, key, body, request_id):
    if any(not isinstance(v, UUID) or not v.int for v in (actor, identity, key, request_id)):
        raise SocialError('INVALID_REQUEST', 'Valid administrator, media and command identities are required.', 422)
    body = ArchiveMedia.model_validate(body)
    commands = SocialService(svc.db)

    def mutate():
        asset, upload = svc._rows(identity)
        if upload.version != body.expected_version:
            raise SocialError('VERSION_CONFLICT', 'This media changed. Refresh before archiving.')
        reason = _reason(svc, asset, upload, svc._referenced(identity))
        if reason:
            raise SocialError('MEDIA_ARCHIVE_BLOCKED', reason)
        asset.state = 'archived'
        upload.version += 1
        audit = commands.audit('media.asset_archived', previous='ready', new='archived', reason=body.reason,
            details={'asset_id': str(identity), 'version': upload.version, 'objects_retained': True, 'quota_released': False})
        svc.db.flush()
        if svc.db.bind.dialect.name == 'postgresql':
            svc.db.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
        stored = svc.db.execute(select(SocialAuditEvent.__table__).where(SocialAuditEvent.id == audit.id)).mappings().first()
        fields = ('actor_id', 'actor_kind', 'action', 'previous_state', 'new_state', 'reason', 'request_id')
        state = svc.db.execute(select(SocialMediaAsset.state, SocialMediaUpload.version)
            .join(SocialMediaUpload,
                SocialMediaUpload.asset_id == SocialMediaAsset.id)
            .where(SocialMediaAsset.id == identity)).one()
        if (stored is None or any(stored[f] != getattr(audit, f) for f in fields) or
                canonical_hash(stored['details']) != canonical_hash(audit.details) or state != ('archived', upload.version)):
            raise SocialError('MEDIA_ARCHIVE_AUDIT_FAILED', 'Archive could not confirm durable state and audit. Nothing was archived; refresh before retrying.', 503)
        return svc._dto(asset, upload).model_dump(mode='json')

    _, result = commands.command(actor=actor, route='media.archive:' + str(identity), key=key,
        body=body.model_dump(mode='json'), request_id=request_id, action=mutate)
    return MediaAssetDTO.model_validate(result)
