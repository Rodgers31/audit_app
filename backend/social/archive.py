"""Soft archive retains business evidence; cancellation is an independent command."""
from sqlalchemy import select, text

from .models import SocialAuditEvent, SocialPost, SocialPostTarget, SocialPublication, SocialPublishAttempt
from .service import SocialError, iso
from .contracts import canonical_hash

EDITORIAL_STATES = frozenset({'draft', 'pending_review', 'approved', 'rejected'})
TERMINAL_TARGET_STATES = frozenset({'published', 'failed', 'cancelled'})
RETAINED_MESSAGE = 'Archived history is retained read-only. Duplicate as a new manual draft to recover content; fresh review and authorization are required. No remote post was deleted.'
ACTIVE_MESSAGE = 'Delivery work is active or unresolved. Use the independent cancellation or reconciliation workflow, then refresh before archiving. Archive does not cancel or delete remote posts.'


def archive_status(db, post, *, lock=False):
    """Inspect ALL authorizations, including superseded delivery history.

    Archive holds the command lock order (controls/accounts/publication/targets/post)
    before these reads. Target locks also serialize the worker's narrow claim path,
    which deliberately does not lock controls. No delivery record is changed here.
    """
    publications = select(SocialPublication).where(SocialPublication.post_id == post.id).order_by(SocialPublication.id)
    if lock:
        publications = publications.with_for_update().execution_options(populate_existing=True)
    publications = list(db.scalars(publications))
    publication_ids = [p.id for p in publications]
    targets = select(SocialPostTarget).where(SocialPostTarget.publication_id.in_(publication_ids)).order_by(SocialPostTarget.id)
    if lock:
        targets = targets.with_for_update().execution_options(populate_existing=True)
    targets = list(db.scalars(targets)) if publication_ids else []
    incomplete = db.scalar(select(SocialPublishAttempt.id).where(
        SocialPublishAttempt.target_id.in_([t.id for t in targets]),
        SocialPublishAttempt.completed_at.is_(None)).limit(1)) if targets else None
    active = incomplete is not None or any(
        t.state not in TERMINAL_TARGET_STATES or t.next_action is not None or t.next_action_at is not None
        or t.lease_token is not None or t.lease_owner is not None or t.lease_expires_at is not None
        for t in targets)
    # An empty authorization is not evidence of delivery completion.
    targeted = {t.publication_id for t in targets}
    active = active or any(p.revoked_at is None and p.cancel_requested_at is None and p.id not in targeted for p in publications)
    archived = post.editorial_state == 'archived' or post.archived_at is not None
    eligible = not archived and post.editorial_state in EDITORIAL_STATES and not active
    return {'eligible': eligible, 'archived_at': iso(post.archived_at),
            'message': RETAINED_MESSAGE if archived else ACTIVE_MESSAGE if active else
            'Archive keeps revisions, sources, approvals and delivery evidence. The original becomes read-only; recover content by duplicating a new draft. No remote post is deleted.'}


def archive_post(svc, post_id, body):
    post, revision, _ = svc._locked(post_id, body.expected_version)
    status = archive_status(svc.db, post, lock=True)
    if not status['eligible']:
        raise SocialError('ARCHIVE_DELIVERY_ACTIVE', status['message'])
    previous = post.editorial_state
    post.editorial_state = 'archived'
    post.archived_at = svc.now()
    svc._touch(post)
    audit = svc.audit('post.archived', post=post, previous=previous, new='archived', details={
        'revision_id': str(revision.id), 'content_hash': revision.content_hash,
        'archived_at': iso(post.archived_at), 'recovery': 'duplicate_manual_draft',
        'remote_deletion_requested': False})
    svc.db.flush()
    if svc.db.bind.dialect.name == "postgresql":
        svc.db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    # Flush can succeed when a database BEFORE trigger suppresses an INSERT.
    # Read actual stored rows, bypassing the ORM identity map, before success.
    stored_audit = svc.db.execute(select(SocialAuditEvent.__table__).where(SocialAuditEvent.id == audit.id)).mappings().first()
    audit_fields = ('post_id', 'actor_id', 'actor_kind', 'action', 'previous_state', 'new_state', 'request_id')
    audit_matches = stored_audit is not None and all(stored_audit[name] == getattr(audit, name) for name in audit_fields)
    audit_matches = audit_matches and canonical_hash(stored_audit['details']) == canonical_hash(audit.details)
    stored_post = svc.db.execute(select(SocialPost.editorial_state, SocialPost.row_version, SocialPost.archived_at, SocialPost.current_revision_id).where(SocialPost.id == post.id)).one()
    post_matches = (stored_post.editorial_state == 'archived' and stored_post.row_version == post.row_version
        and iso(stored_post.archived_at) == iso(post.archived_at) and stored_post.current_revision_id == revision.id)
    if not audit_matches or not post_matches:
        raise SocialError('ARCHIVE_AUDIT_FAILED', 'Archive could not confirm its durable state and audit. The transaction was rolled back; refresh before retrying.', 503)
    return svc.detail(post.id)
