"""Archive contract, retention and closed admission; no provider operations."""
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select

from social.contracts import ApproveCommand, PatchPost, ScheduleEditCommand, VersionCommand
from social.models import SocialAuditEvent, SocialCommandReceipt, SocialPost, SocialPostRevision, SocialPostTarget, SocialPublication
from social.service import SocialError, SocialService
from test_domain_support import account, call, db, draft_body
from test_api_admin import make_client, key


def create(db, with_account=False):
    body = draft_body((account(db),) if with_account else (), references=[{'url': 'https://example.org/evidence', 'label': 'Retain me'}])
    return call(db, body, lambda s: s.create(body), route='create')[1]


def archive(db, post, *, version=None, command_key=None):
    body = VersionCommand(expected_version=version or post['version'])
    return call(db, body, lambda s: s.archive(UUID(post['id']), body), route='archive/' + post['id'], key=command_key)[1]


def test_archive_replay_retains_revision_references_and_recovery(db):
    post = create(db)
    patch = PatchPost(expected_version=1, title='Edited before archive')
    post = call(db, patch, lambda s: s.patch(UUID(post['id']), patch), route='patch')[1]
    command_key = uuid4()
    result = archive(db, post, command_key=command_key)
    assert result['editorial_state'] == 'archived' and result['version'] == 3
    assert result['revision_id'] == post['revision_id'] and result['references'] == post['references']
    assert result['archive']['archived_at'] and result['archive']['eligible'] is False
    assert archive(db, post, command_key=command_key) == result
    with pytest.raises(SocialError, match='IDEMPOTENCY_CONFLICT'):
        archive(db, post, version=3, command_key=command_key)
    with pytest.raises(SocialError, match='VERSION_CONFLICT'):
        archive(db, post)
    with pytest.raises(SocialError, match='POST_ARCHIVED'):
        archive(db, result)
    # Fresh service reads durable retained state, rather than a command's in-memory copy.
    db.expire_all()
    svc = SocialService(db)
    assert svc.detail(UUID(post['id'])) == result
    assert svc.posts(editorial_state='archived')['total'] == 1
    assert db.scalar(select(func.count()).select_from(SocialPostRevision)) == 2
    assert db.scalar(select(func.count()).select_from(SocialAuditEvent).where(SocialAuditEvent.action == 'post.archived')) == 1
    body = VersionCommand(expected_version=3)
    recovered = call(db, body, lambda s: s.duplicate(UUID(post['id']), body), route='duplicate')[1]
    assert recovered['id'] != post['id'] and recovered['editorial_state'] == 'draft'
    assert recovered['publication'] is None and recovered['targets'] == []
    assert recovered['references'] == post['references']


@pytest.mark.parametrize('state', ['draft', 'pending_review', 'approved', 'rejected'])
def test_eligible_editorial_states(db, state):
    post = create(db)
    row = db.get(SocialPost, UUID(post['id'])); row.editorial_state = state; db.commit()
    assert archive(db, post)['editorial_state'] == 'archived'


def test_archived_post_blocks_patch_and_all_versioned_admission(db):
    post = archive(db, create(db))
    svc = SocialService(db)
    for action in ('patch', 'submit', 'approve', 'reject', 'publish', 'cancel', 'resume', 'edit_schedule'):
        body = PatchPost(expected_version=post['version'], title='Must not reopen') if action == 'patch' else VersionCommand(expected_version=post['version'])
        if action == 'edit_schedule':
            body = ScheduleEditCommand(expected_version=post['version'], expected_publication_version=1, publication_id=uuid4(), reason='fixture')
        with pytest.raises(SocialError, match='POST_ARCHIVED'):
            call(db, body, lambda s: getattr(s, action)(UUID(post['id']), body), route=action)
    assert svc.detail(UUID(post['id']))['editorial_state'] == 'archived'


def test_failed_audit_rolls_back_archive_version_timestamp_and_receipt(db):
    post = create(db)
    def reject_archive(mapper, connection, target):
        if target.action == 'post.archived':
            raise RuntimeError('injected audit failure')
    event.listen(SocialAuditEvent, 'before_insert', reject_archive)
    try:
        with pytest.raises(RuntimeError, match='injected audit failure'):
            archive(db, post)
    finally:
        event.remove(SocialAuditEvent, 'before_insert', reject_archive)
    db.expire_all()
    row = db.get(SocialPost, UUID(post['id']))
    assert row.editorial_state == 'draft' and row.row_version == 1 and row.archived_at is None
    assert db.scalar(select(func.count()).select_from(SocialCommandReceipt)) == 1


@pytest.mark.parametrize('state', ['ready','queued','claimed','dispatching','processing','retry_wait','reconciling','blocked','outcome_unknown'])
def test_archive_refuses_active_delivery_without_mutation(db, state):
    post = create(db, True)
    body = ApproveCommand(expected_version=1, revision_id=post['revision_id'])
    post = call(db, body, lambda s: s.approve(UUID(post['id']), body), route='approve')[1]
    target = db.get(SocialPostTarget, UUID(post['targets'][0]['id'])); target.state = state; db.commit()
    with pytest.raises(SocialError, match='ARCHIVE_DELIVERY_ACTIVE'):
        archive(db, post)
    assert db.get(SocialPost, UUID(post['id'])).archived_at is None
    assert db.get(SocialPostTarget, target.id).state == state


def test_independent_cancel_then_archive_preserves_authorization(db):
    post = create(db, True)
    body = ApproveCommand(expected_version=1, revision_id=post['revision_id'])
    post = call(db, body, lambda s: s.approve(UUID(post['id']), body), route='approve')[1]
    body = VersionCommand(expected_version=2)
    cancelled = call(db, body, lambda s: s.cancel(UUID(post['id']), body), route='cancel')[1]
    result = archive(db, cancelled)
    assert result['publication'] == cancelled['publication'] and result['targets'] == cancelled['targets']
    assert db.get(SocialPublication, UUID(post['publication']['id'])).revoked_at is None


def test_archive_http_auth_strict_version_and_retry(db):
    client = make_client(db.bind)
    post = client.post('/api/v1/admin/social/posts', json=draft_body().model_dump(mode='json'), headers=key()).json()
    path = '/api/v1/admin/social/posts/' + post['id'] + '/archive'
    for bad in (None, True, 0, -1, 1.5, '1', {}, []):
        response = client.post(path, json={'expected_version': bad}, headers=key())
        assert response.status_code == 422
    response = make_client(db.bind, authenticated=False).post(path, json={'expected_version':1}, headers=key())
    assert response.status_code == 401
    assert response.headers['cache-control'] == 'private, no-store'
    headers = key()
    response = client.post(path, json={'expected_version':1}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'private, no-store'
    assert client.post(path, json={'expected_version':1}, headers=headers).json() == response.json()


def test_retained_archived_row_cannot_be_reopened_by_patch(db):
    """Regression independent of the new archive entry point."""
    from datetime import datetime, timezone
    post = create(db)
    row = db.get(SocialPost, UUID(post['id']))
    row.editorial_state, row.archived_at = 'archived', datetime.now(timezone.utc)
    db.commit()
    body = PatchPost(expected_version=1, title='Must remain archived')
    with pytest.raises(SocialError, match='POST_ARCHIVED'):
        call(db, body, lambda s: s.patch(UUID(post['id']), body), route='patch')


def test_archived_generated_post_denies_policy_authorize_and_schedule(db, monkeypatch):
    from social.automation.contracts import AuthorizePolicyCommand, SchedulePolicyCommand
    from social.automation.service import AutomationService
    from test_generation import configure, consume, observation
    configure(db)
    result = consume(db, observation(), backfill=True)
    post = SocialService(db).detail(UUID(result['post_id']))
    post = archive(db, post)
    monkeypatch.setenv('SOCIAL_POLICY_AUTOMATION_ENABLED', 'true')
    revision = db.get(SocialPostRevision, UUID(post['revision_id']))
    values = dict(expected_version=post['version'], revision_id=post['revision_id'], content_hash=revision.content_hash, snapshot_id=uuid4())
    for action, body in [('authorize', AuthorizePolicyCommand(**values)), ('schedule', SchedulePolicyCommand(**values, publication_id=uuid4(), expected_publication_version=1))]:
        with pytest.raises(SocialError, match='POST_ARCHIVED'):
            call(db, body, lambda s: getattr(AutomationService(s), action)(UUID(post['id']), body), route=action)
    assert db.scalar(select(func.count()).select_from(SocialPublication)) == 0


@pytest.mark.parametrize('state', ['published','failed','cancelled'])
def test_terminal_delivery_evidence_unchanged_and_retry_closed(db, state):
    from datetime import datetime, timezone
    from social.contracts import RetryCommand
    from social.models import SocialPublishAttempt
    post = create(db, True)
    body = ApproveCommand(expected_version=1, revision_id=post['revision_id'])
    post = call(db, body, lambda s: s.approve(UUID(post['id']), body), route='approve')[1]
    target = db.get(SocialPostTarget, UUID(post['targets'][0]['id']))
    target.state, target.submit_count = state, 1
    target.checkpoint, target.remote_refs = {'retained': 'checkpoint'}, {'retained': 'reference'}
    if state == 'published':
        target.primary_remote_id, target.confirmation_kind, target.published_at, target.visibility_state = 'owned-remote-proof', 'fixture', datetime.now(timezone.utc), 'public'
    attempt = SocialPublishAttempt(target_id=target.id, sequence=1, operation_id=uuid4(), operation='publish', request_fingerprint='e'*64, lease_epoch=1, outcome='confirmed_success' if state == 'published' else 'definite_failure', completed_at=datetime.now(timezone.utc), receipt={'retained': 'receipt'})
    db.add(attempt); db.commit(); db.expire_all()
    before = {c.name: getattr(target, c.name) for c in target.__table__.columns}
    post = archive(db, post)
    db.expire_all()
    target = db.get(SocialPostTarget, target.id)
    assert {c.name: getattr(target, c.name) for c in target.__table__.columns} == before
    assert db.get(SocialPublishAttempt, attempt.id).receipt == {'retained':'receipt'}
    assert db.get(SocialPublication, UUID(post['publication']['id'])).approved_hash
    body = RetryCommand(reason='Must stay read-only')
    with pytest.raises(SocialError, match='POST_ARCHIVED'):
        call(db, body, lambda s: s.retry(target.id, body), route='retry')


def test_archive_refuses_historical_work_and_unfinished_attempt(db):
    from social.models import SocialPublishAttempt
    post = create(db, True)
    body = ApproveCommand(expected_version=1, revision_id=post['revision_id'])
    post = call(db, body, lambda s: s.approve(UUID(post['id']), body), route='approve')[1]
    publication = db.get(SocialPublication, UUID(post['publication']['id']))
    publication.revoked_at = SocialService(db).now()
    db.commit()
    with pytest.raises(SocialError, match='ARCHIVE_DELIVERY_ACTIVE'): archive(db, post)
    target = db.get(SocialPostTarget, UUID(post['targets'][0]['id'])); target.state = 'cancelled'
    db.add(SocialPublishAttempt(target_id=target.id, sequence=1, operation_id=uuid4(), operation='publish', request_fingerprint='a'*64, lease_epoch=1, outcome='pending'))
    db.commit()
    with pytest.raises(SocialError, match='ARCHIVE_DELIVERY_ACTIVE'): archive(db, post)


def test_preexisting_command_receipt_remains_replayable_without_archive_metadata(db):
    # Receipts created by the accepted baseline lack this additive detail field.
    client = make_client(db.bind)
    headers, body = key(), draft_body().model_dump(mode='json')
    response = client.post('/api/v1/admin/social/posts', json=body, headers=headers)
    assert response.status_code == 201
    receipt = db.scalar(select(SocialCommandReceipt))
    old = {k:v for k,v in receipt.response.items() if k != 'archive'}
    receipt.response = old; db.commit()
    replay = client.post('/api/v1/admin/social/posts', json=body, headers=headers)
    assert replay.status_code == 201 and replay.json() == old


def test_new_source_version_survives_archived_cancelled_predecessor(db, monkeypatch):
    from unit_source_authority_fixture import install_unit_source_authority
    install_unit_source_authority(monkeypatch, db)
    from test_generation import configure, consume, observation
    a = account(db)
    configure(db, [a])
    created = consume(db, observation(), backfill=True)
    post = call(db, observation(), lambda s: s.detail(UUID(created['post_id'])))[1]
    approve = ApproveCommand(expected_version=post['version'], revision_id=post['revision_id'], review_attestation={'facts_checked': True, 'sources_checked': True})
    post = call(db, approve, lambda s: s.approve(UUID(post['id']), approve))[1]
    cancel = VersionCommand(expected_version=post['version'])
    post = call(db, cancel, lambda s: s.cancel(UUID(post['id']), cancel))[1]
    old = archive(db, post)
    result = consume(db, observation(2, '999.99'))
    assert result['status'] == 'draft_created'
    assert result['post_id'] != old['id']
    assert SocialService(db).detail(UUID(old['id'])) == old
