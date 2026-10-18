from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select, text

from ..contracts import canonical_hash
from ..models import SocialPost, SocialPostRevision, SocialPostTarget, SocialPublication
from ..service import SocialError, iso, utc
from .contracts import Approval, Composition
from .models import RenderJob
from .integrity import bound_composition
from .runtime import verified_bytes


def studio_lock(db):
    if db.bind.dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(705150001)'))
    elif db.bind.dialect.name == 'sqlite':
        raw = db.connection().connection.driver_connection
        if raw.in_transaction:
            raise SocialError('STUDIO_TRANSACTION_REFUSED', 'Studio writes require a fresh owned SQLite transaction.')
        db.execute(text('BEGIN IMMEDIATE'))
    else:
        raise SocialError('STUDIO_DATABASE_UNSUPPORTED', 'This database cannot fence studio mutations.', 503)


def job_dto(row):
    return {'id': str(row.id), 'revision_id': str(row.revision_id), 'state': row.state,
            'version': row.version, 'composition': row.composition, 'input_hash': row.input_hash,
            'sha256': row.sha256, 'inspection': row.inspection, 'safe_error': row.safe_error,
            'approved_sha256': row.approved_sha256, 'created_at': iso(row.created_at),
            'started_at': iso(row.started_at), 'finished_at': iso(row.finished_at),
            'runtime_hash': row.runtime_hash, 'cancel_requested': bool(row.cancel_requested),
            'attempt': row.attempt, 'retry_of_id': str(row.retry_of_id) if row.retry_of_id else None}


class StudioService:
    def __init__(self, social, runtime):
        self.social, self.db, self.runtime = social, social.db, runtime

    def get(self, job_id, *, lock=False):
        query = select(RenderJob).where(RenderJob.id == job_id).execution_options(populate_existing=True)
        row = self.db.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise SocialError('NOT_FOUND', 'Render job not found.', 404)
        return row

    def create(self, body):
        self.runtime.require()
        studio_lock(self.db)
        return self._enqueue(body)

    def _enqueue(self, body, retry=None):
        body = Composition.model_validate(body)
        revision = self.db.get(SocialPostRevision, body.revision_id)
        if revision is None:
            raise SocialError('NOT_FOUND', 'Source revision not found.', 404)
        post = self.db.get(SocialPost, revision.post_id)
        if post.current_revision_id != revision.id:
            raise SocialError('VERSION_CONFLICT', 'Render the current source revision.')
        # Source identity is checked here; editorial approval still attests truth.
        references = {r['url'] for r in revision.evidence_snapshot.get('references', [])}
        if not references or any(f.source_url not in references for f in body.facts):
            raise SocialError('RENDER_EVIDENCE_REQUIRED', 'Every fact must cite evidence on the source revision.', 422)
        value = body.model_dump(mode='json')
        digest = canonical_hash({'composition': value, 'revision_hash': revision.content_hash})
        attempt = retry.attempt + 1 if retry else 1
        existing = self.db.scalar(select(RenderJob).where(RenderJob.actor_id == self.social.actor, RenderJob.input_hash == digest, RenderJob.attempt == attempt))
        if existing:
            return job_dto(existing)
        # Hard retained inventory bound. No automatic removal of reviewed bytes.
        if self.db.scalar(select(func.count()).select_from(RenderJob)) >= 20:
            raise SocialError('RENDER_QUOTA', 'The retained local render inventory is full; request reviewed archival.', 429)
        row = RenderJob(id=uuid4(), revision_id=revision.id, actor_id=self.social.actor, composition=value, input_hash=digest, attempt=attempt, retry_of_id=retry.id if retry else None)
        self.db.add(row)
        bound_composition(self.db, row)
        self.social.audit('render.queued', post=post, details={'job_id': str(row.id), 'input_hash': digest})
        self.db.flush()
        return job_dto(row)

    def retry(self, job_id, expected_version):
        from ..service import require_positive_version
        require_positive_version(expected_version)
        self.runtime.require()
        studio_lock(self.db)
        row = self.get(job_id, lock=True)
        bound_composition(self.db, row)
        if row.version != expected_version or row.state not in {'failed', 'cancelled'} or row.attempt != 1 or row.actor_id != self.social.actor:
            raise SocialError('RENDER_RETRY_REFUSED', 'Only the creator can retry a terminal first attempt once. Refresh before continuing.')
        result = self._enqueue(row.composition, retry=row)
        self.social.audit('render.retry_created', details={'job_id': result['id'], 'retry_of_id': str(row.id), 'attempt': 2})
        return result

    def cancel(self, job_id, expected_version):
        from ..service import require_positive_version
        require_positive_version(expected_version)
        studio_lock(self.db)
        row = self.get(job_id, lock=True)
        if row.version != expected_version:
            raise SocialError('VERSION_CONFLICT', 'Refresh the render job before cancelling.')
        if row.state not in {'queued', 'running'}:
            raise SocialError('RENDER_TERMINAL', 'This render has already finished.')
        row.cancel_requested = 1
        if row.state == 'queued':
            row.state, row.finished_at = 'cancelled', self.social.now()
        row.version += 1
        self.social.audit('render.cancel_requested', details={'job_id': str(row.id)})
        self.db.flush()
        return job_dto(row)

    def approve(self, job_id, body):
        body = Approval.model_validate(body)
        studio_lock(self.db)
        row = self.get(job_id, lock=True)
        bound_composition(self.db, row)
        if row.version != body.expected_version or row.state != 'ready' or row.sha256 != body.sha256 or row.approved_sha256:
            raise SocialError('VERSION_CONFLICT', 'Review the current inspected bytes before approving.')
        revision = self.db.get(SocialPostRevision, row.revision_id)
        post = self.db.scalar(select(SocialPost).where(SocialPost.id == revision.post_id).with_for_update().execution_options(populate_existing=True))
        if post.current_revision_id != row.revision_id:
            raise SocialError('VERSION_CONFLICT', 'Source content changed; render and review its new revision.')
        verified_bytes(self.runtime, row)
        row.approved_sha256, row.approved_by, row.approved_at = body.sha256, self.social.actor, self.social.now()
        row.version += 1
        self.social.audit('render.approved', post=post, details={'job_id': str(row.id), 'sha256': body.sha256, 'input_hash': row.input_hash, 'review_attestation': body.review_attestation.model_dump(mode='json')})
        self.db.flush()
        return job_dto(row)

    def attach(self, job_id, asset_id, expected_version):
        """Bridge the existing inspected media intake; never upload from the renderer."""
        from ..contracts import PatchPost, PostDocument
        from ..models import SocialMediaAsset
        studio_lock(self.db)
        row = self.get(job_id, lock=True)
        bound_composition(self.db, row)
        if row.state != 'ready' or row.approved_sha256 != row.sha256 or not row.approved_sha256:
            raise SocialError('RENDER_APPROVAL_REQUIRED', 'Approve the inspected derivative before adding it to a draft.')
        revision = self.db.get(SocialPostRevision, row.revision_id)
        post, current, publication = self.social._locked(revision.post_id, expected_version)
        if post.current_revision_id != row.revision_id:
            raise SocialError('VERSION_CONFLICT', 'The source revision changed; review a new render.')
        asset = self.db.scalar(select(SocialMediaAsset).where(SocialMediaAsset.id == asset_id).with_for_update().execution_options(populate_existing=True))
        if not asset or asset.state != 'ready' or asset.deleted_at or asset.sha256 != row.approved_sha256 or asset.mime_type != row.inspection['mime_type'] or asset.byte_size != row.inspection['byte_size']:
            raise SocialError('RENDER_INTEGRITY', 'Select the inspected media asset with the exact approved checksum.')
        value = dict(revision.document)
        value['master'] = {**value['master'], 'media': [*value['master']['media'], {'asset_id': str(asset.id), 'alt_text': ' '.join(f['text'] for f in row.composition['facts']) if asset.mime_type.startswith('image/') else None, 'caption_asset_id': None}]}
        result = self.social.patch(post.id, PatchPost(expected_version=expected_version, document=PostDocument.model_validate(value)))
        self.social.audit('render.attached', post=post, details={'job_id': str(row.id), 'asset_id': str(asset.id), 'sha256': row.approved_sha256, 'source_revision_id': str(row.revision_id), 'new_revision_id': result['revision_id']})
        return result


def calendar(db, start, end, page):
    if start.tzinfo is None or end.tzinfo is None or not 0 < (end - start).total_seconds() <= 31 * 86400 or type(page) is not int or page < 1:
        raise SocialError('INVALID_REQUEST', 'Use a timezone-aware calendar interval of at most 31 days.', 422)
    rows = db.execute(select(SocialPublication.id, SocialPublication.post_id, SocialPost.title,
        SocialPublication.revision_id, SocialPublication.scheduled_for, SocialPublication.schedule_timezone,
        SocialPublication.cancel_requested_at, SocialPublication.revoked_at).join(SocialPost, SocialPost.id == SocialPublication.post_id)
        .where(SocialPublication.scheduled_for >= start, SocialPublication.scheduled_for < end)
        .order_by(SocialPublication.scheduled_for, SocialPublication.id).offset((page - 1) * 50).limit(51)).all()
    return {'items': [{'publication_id': str(r.id), 'post_id': str(r.post_id), 'title': r.title, 'revision_id': str(r.revision_id), 'scheduled_for': iso(r.scheduled_for), 'timezone': r.schedule_timezone, 'cancel_requested': r.cancel_requested_at is not None, 'revoked': r.revoked_at is not None} for r in rows[:50]], 'page': page, 'has_more': len(rows) > 50}
