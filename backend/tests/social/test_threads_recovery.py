"""Inert operator recovery fixtures: no provider, storage, or worker process."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select

from social.contracts import ApproveCommand
from social.models import SocialAccount, SocialControls, SocialPostTarget, SocialPublication, SocialPublishAttempt
from test_api_admin import make_client, key
from test_domain_support import ACTOR, account, call, db, draft_body

REVIEWER = UUID('72400000-0000-4000-8000-000000000002')


def pending(db, *, owner_id=None, product='fixture'):
    a = account(db, 'threads')
    a.external_account_id = owner_id or str(uuid4().int)[:20]
    a.api_product = product
    db.commit()
    body = draft_body((a,))
    _, post = call(db, body, lambda s: s.create(body))
    approve = ApproveCommand(expected_version=1, revision_id=post['revision_id'])
    _, post = call(db, approve, lambda s: s.approve(UUID(post['id']), approve))
    target = db.get(SocialPostTarget, UUID(post['targets'][0]['id']))
    target.state = 'outcome_unknown'
    target.submit_count = 1
    target.primary_remote_id = '9001'
    target.remote_refs = {'post_id': '9001', 'container_id': '8001'}
    now = datetime.now(timezone.utc)
    db.add(SocialPublishAttempt(target_id=target.id, sequence=1, operation_id=uuid4(), operation='publish',
        request_fingerprint='a'*64, lease_epoch=0, dispatch_started_at=now, completed_at=now,
        outcome='ambiguous', receipt={'intent': {'publication_capable': True, 'mutating': True, 'safe_replay_class': 'requires_reconciliation'}}))
    a = db.get(SocialAccount, a.id)
    a.hold_reason = 'RECONCILIATION_REQUIRED:' + str(target.id)
    if db.get(SocialControls, 1) is None:
        db.add(SocialControls(id=1, publishing_enabled=False))
    db.commit()
    return target.id


def observation(context, capture='a'):
    return dict(method='anonymous_browser', visibility='public', observed_at=(datetime.now(timezone.utc)-timedelta(seconds=2)).isoformat(),
        capture_sha256=capture*64, custody_reference=str(uuid4()),
        external_account_id=context['external_account_id'], remote_id='9001',
        remote_url='https://www.threads.com/@fixture/post/AbCd1',
        text=context['caption'], asset_sha256=context['asset_sha256'],
        account_identity_basis='Observed numeric owner identity cross-checked with retained owned-post receipt.',
        review_notes='Anonymous fresh browser without login displayed exact full post and account; compared approved text and media.')


def test_two_independent_admin_observations_settle_exact_target(db):
    target_id = pending(db)
    client = make_client(db.bind)
    url = f'/api/v1/admin/social/targets/{target_id}'
    context = client.get(url + '/public-proof').json()
    assert 'binding_hash' in context, context
    proposal = {'expected_publication_version': context['publication_version'], 'binding_hash': context['binding_hash'],
                'observation': observation(context), 'reason': 'Resolve retained ambiguous send using independently reviewed public capture.'}
    headers = key()
    response = client.post(url + '/public-proof', json=proposal, headers=headers)
    assert response.status_code == 201, response.text
    assert client.post(url + '/public-proof', json=proposal, headers=headers).json() == response.json()
    proof = response.json()
    reviewer = make_client(db.bind, actor=REVIEWER)
    body = {'expected_publication_version': context['publication_version'], 'proof_id': proof['proof_id'],
            'observation': observation(context, 'b'), 'reason': 'Independent second anonymous review agrees with retained evidence.'}
    headers = key()
    result = reviewer.post(url + '/record-existing', json=body, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()['state'] == 'published'
    assert reviewer.post(url + '/record-existing', json=body, headers=headers).json() == result.json()
    db.expire_all()
    target = db.get(SocialPostTarget, target_id)
    assert target.state == 'published' and target.visibility_state == 'public'
    assert target.submit_count == 1 and target.remote_refs == {'post_id': '9001', 'container_id': '8001'}
    assert db.get(SocialAccount, target.account_id).hold_reason is None
    assert db.get(SocialControls, 1).publishing_enabled is False
    assert db.get(SocialPublication, target.publication_id).version == context['publication_version'] + 1


def proposal(db):
    target_id = pending(db)
    client = make_client(db.bind)
    url = f'/api/v1/admin/social/targets/{target_id}'
    context = client.get(url + '/public-proof').json()
    body = dict(expected_publication_version=context['publication_version'], binding_hash=context['binding_hash'],
        observation=observation(context), reason='Retained anonymous public observation for independent review.')
    response = client.post(url + '/public-proof', json=body, headers=key())
    assert response.status_code == 201, response.text
    admission = dict(expected_publication_version=context['publication_version'], proof_id=response.json()['proof_id'],
        observation=observation(context, 'b'), reason='Independent public review against immutable approved revision.')
    return target_id, url, context, body, admission


import pytest
from pydantic import ValidationError
from social.models import SocialAuditEvent, SocialCommandReceipt
from social.service import SocialError
from social.threads_recovery import ThreadsRecoveryService, RecordExisting, ProposePublicProof, PublicObservation


@pytest.mark.parametrize('field,value,status', [
    ('visibility', 'private', 422), ('visibility', 'unknown', 422), ('method', 'authenticated_api', 422),
    ('external_account_id', '11111', 409), ('remote_id', '11111', 409),
    ('text', 'Changed text', 409), ('asset_sha256', ['c'*64], 409),
    ('remote_url', 'https://threads.com.evil.test/@fixture/post/AbCd1', 422),
    ('remote_url', 'https://threads.com/@fixture/post/AbCd1?login=1', 422),
    ('remote_url', 'https://threads.com/@fixture/post/Other', 409),
    ('observed_at', '2000-01-01T00:00:00Z', 409), ('observed_at', '2099-01-01T00:00:00Z', 409),
    ('capture_sha256', 'a'*64, 409), ('capture_sha256', {}, 422), ('review_notes', '', 422),
])
def test_refused_evidence_never_settles(db, field, value, status):
    target_id, url, context, first, body = proposal(db)
    body['observation'][field] = value
    response = make_client(db.bind, actor=REVIEWER).post(url + '/record-existing', json=body, headers=key())
    assert response.status_code == status, response.text
    db.expire_all()
    target = db.get(SocialPostTarget, target_id)
    assert target.state == 'outcome_unknown' and target.visibility_state == 'unknown'
    assert target.submit_count == 1 and db.get(SocialAccount, target.account_id).hold_reason.endswith(str(target_id))
    assert list(db.scalars(select(SocialAuditEvent).where(SocialAuditEvent.action == 'threads.public_proof_admitted'))) == []


@pytest.mark.parametrize('change', ['version', 'checkpoint', 'lease', 'account_lease', 'pending_attempt', 'published', 'unknown_shape'])
def test_worker_changes_invalidate_or_block_pending_proof(db, change):
    target_id, url, context, first, body = proposal(db)
    target = db.get(SocialPostTarget, target_id)
    if change == 'version':
        db.get(SocialPublication, target.publication_id).version += 1
    elif change == 'checkpoint':
        target.remote_refs = {**target.remote_refs, 'additional_evidence': 'late'}
    elif change == 'lease':
        target.lease_token = uuid4()
    elif change == 'account_lease':
        db.get(SocialAccount, target.account_id).publish_lease_token = uuid4()
    elif change == 'pending_attempt':
        db.get(SocialPublishAttempt, db.scalar(select(SocialPublishAttempt.id))).completed_at = None
    elif change == 'unknown_shape':
        target.checkpoint = ['garbage']
    else:
        target.state = 'failed'
    db.commit()
    response = make_client(db.bind, actor=REVIEWER).post(url + '/record-existing', json=body, headers=key())
    assert response.status_code == 409, response.text
    db.expire_all()
    assert db.get(SocialPostTarget, target_id).state != 'published'


def test_independence_auth_idempotency_and_unrelated_hold(db):
    target_id, url, context, first, body = proposal(db)
    client = make_client(db.bind)
    assert client.post(url+'/record-existing', json=body, headers=key()).status_code == 403
    assert make_client(db.bind, authenticated=False).post(url+'/record-existing', json=body, headers=key()).status_code == 401
    assert make_client(db.bind, authenticated=False).get(url+'/public-proof').status_code == 401
    assert make_client(db.bind, actor=REVIEWER).post(url+'/record-existing', json=body).status_code == 422
    target = db.get(SocialPostTarget, target_id)
    a = db.get(SocialAccount, target.account_id)
    a.hold_reason = 'PRIVACY_REVIEW_REQUIRED'
    db.commit()
    reviewer = make_client(db.bind, actor=REVIEWER)
    headers = key()
    result = reviewer.post(url+'/record-existing', json=body, headers=headers)
    assert result.status_code == 200, result.text
    changed = {**body, 'reason': 'Different content under the same idempotency key.'}
    assert reviewer.post(url+'/record-existing', json=changed, headers=headers).json()['detail']['code'] == 'IDEMPOTENCY_CONFLICT'
    assert reviewer.post(url+'/record-existing', json=body, headers=key()).status_code == 409
    db.expire_all()
    assert db.get(SocialAccount, a.id).hold_reason == 'PRIVACY_REVIEW_REQUIRED'


def test_helpers_without_command_and_malformed_internal_models_refuse(db):
    target_id, url, context, first, body = proposal(db)
    svc = ThreadsRecoveryService(db)
    for operation, value in [(svc.propose, first), (svc.record_existing, body)]:
        with pytest.raises(SocialError, match='OPERATOR_COMMAND_REQUIRED'):
            operation(target_id, value)
    db.rollback()
    # model_construct bypasses Pydantic at the caller; service revalidates.
    invalid = RecordExisting.model_construct(**{**body, 'expected_publication_version': True})
    with pytest.raises(ValidationError):
        svc.command(actor=REVIEWER, route='internal', key=uuid4(), body=body, request_id=uuid4(),
            action=lambda: svc.record_existing(target_id, invalid))
    assert db.get(SocialPostTarget, target_id).state == 'outcome_unknown'


def test_proof_expiry_and_cross_target_replay(db, monkeypatch):
    target_id, url, context, first, body = proposal(db)
    original_now = ThreadsRecoveryService.now
    monkeypatch.setattr(ThreadsRecoveryService, 'now', lambda self: original_now(self)+timedelta(hours=1))
    response = make_client(db.bind, actor=REVIEWER).post(url+'/record-existing', json=body, headers=key())
    assert response.json()['detail']['code'] == 'PROOF_EXPIRED'
    monkeypatch.undo()
    body['proof_id'] = str(uuid4())
    assert make_client(db.bind, actor=REVIEWER).post(url+'/record-existing', json=body, headers=key()).json()['detail']['code'] == 'PROOF_MISMATCH'


def test_capture_replay_under_new_key_refused_and_proposal_is_durable(db):
    target_id, url, context, first, body = proposal(db)
    response = make_client(db.bind).post(url+'/public-proof', json=first, headers=key())
    assert response.json()['detail']['code'] == 'PROOF_REPLAY'
    db.expire_all()
    audit = db.get(SocialAuditEvent, UUID(body['proof_id']))
    assert audit.details['binding']['payload_hash'] == context['payload_hash']
    assert audit.details['observation'] == PublicObservation.model_validate(first['observation']).model_dump(mode='json')
    assert audit.actor_id == ACTOR and audit.target_id == target_id
