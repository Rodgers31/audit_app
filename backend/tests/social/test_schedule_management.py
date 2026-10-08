"""Global queue membership and unchanged authorization schedule commands."""
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select

from social.models import SocialAuditEvent, SocialPostTarget, SocialPublication, SocialPublishAttempt
from social.service import SocialService, utc
from test_api_admin import make_client, key
from test_domain_commands import enable
from test_domain_support import ACTOR, account, db, draft_body


def scheduled_fixture(db, count=1):
    accounts = [account(db) for _ in range(count)]
    enable(db)
    client = make_client(db.bind, adapters=('facebook',))
    created = client.post('/api/v1/admin/social/posts', json=draft_body(accounts).model_dump(mode='json'), headers=key()).json()
    base = '/api/v1/admin/social/posts/' + created['id']
    due = SocialService(db).now() + timedelta(days=2)
    body = {'expected_version': 1, 'revision_id': created['revision_id'], 'schedule': {'local_time': due.replace(tzinfo=None).isoformat(), 'timezone': 'UTC', 'utc_offset': '+00:00'}}
    response = client.post(base + '/schedule', json=body, headers=key())
    assert response.status_code == 202, response.text
    return client, base, client.get(base).json(), accounts


def command_body(post):
    return {'expected_version': post['version'], 'publication_id': post['publication']['id'], 'expected_publication_version': post['publication']['version'], 'reason': 'Adjust unchanged reviewed delivery'}


def test_global_filters_precede_pagination_and_mixed_posts_overlap(db):
    client, base, original, accounts = scheduled_fixture(db, 2)
    first = db.get(SocialPostTarget, UUID(original['targets'][0]['id']))
    first.state, first.primary_remote_id, first.confirmation_kind = 'published', 'remote-1', 'fixture'
    first.visibility_state, first.published_at, first.remote_url = 'public', SocialService(db).now(), 'https://example.org/posts/remote-1'
    db.commit()
    # Unrelated more-recent drafts must not consume either filtered page.
    for index in range(7):
        response = client.post('/api/v1/admin/social/posts', json=draft_body(title=f'Draft {index}').model_dump(mode='json'), headers=key())
        assert response.status_code == 201
    for delivery in ('scheduled', 'history'):
        response = client.get('/api/v1/admin/social/posts', params={'delivery_filter': delivery, 'page_size': 1})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['total'] == 1
        assert data['posts'][0]['id'] == original['id']
        assert data['has_more'] is False
        assert client.get('/api/v1/admin/social/posts', params={'delivery_filter': delivery, 'page_size': 1, 'page': 2}).json()['posts'] == []
    assert client.get('/api/v1/admin/social/posts', params={'delivery_filter': 'history', 'editorial_state': 'draft'}).json()['total'] == 0
    assert client.get('/api/v1/admin/social/posts', params={'delivery_filter': 'invented'}).status_code == 422


def test_compact_schedule_metadata_and_list_projection(db):
    client, base, post, accounts = scheduled_fixture(db)
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    event.listen(db.bind, 'before_cursor_execute', record)
    try:
        listing = client.get('/api/v1/admin/social/posts', params={'delivery_filter': 'scheduled'}).json()['posts'][0]
        summary = client.get(base + '/status').json()
    finally:
        event.remove(db.bind, 'before_cursor_execute', record)
    for result in (listing, summary):
        assert result['publication'] == post['publication']
        assert result['publication']['approved_by'] == str(ACTOR)
        assert result['publication']['schedule_timezone'] == 'UTC'
        assert 'document' not in result and 'references' not in result
    assert not any(any(column in sql for column in ('resolved_payload', 'evidence_snapshot', 'checkpoint', 'receipt', 'social_post_revisions')) for sql in statements)


def test_reschedule_replay_changes_only_unsent_operational_fields(db):
    client, base, post, accounts = scheduled_fixture(db, 2)
    targets = list(db.scalars(select(SocialPostTarget).order_by(SocialPostTarget.id)))
    frozen = [(t.id, t.payload_hash, t.resolved_payload) for t in targets]
    pub = db.get(SocialPublication, UUID(post['publication']['id']))
    immutable = (pub.revision_id, pub.approved_by, pub.approved_at, pub.approved_hash, pub.content_valid_until)
    due = SocialService(db).now() + timedelta(days=3)
    body = {**command_body(post), 'schedule': {'local_time': due.replace(tzinfo=None).isoformat(), 'timezone': 'UTC', 'utc_offset': '+00:00'}}
    headers = key()
    response = client.post(base + '/reschedule', json=body, headers=headers)
    assert response.status_code == 200, response.text
    changed = response.json()
    assert changed['version'] == post['version'] + 1
    assert changed['publication']['version'] == post['publication']['version'] + 1
    assert utc(datetime.fromisoformat(changed['publication']['scheduled_for'].replace('Z', '+00:00'))) == due
    assert client.post(base + '/reschedule', json=body, headers=headers).json() == changed
    conflict = client.post(base + '/reschedule', json={**body, 'reason': 'Different'}, headers=headers)
    assert conflict.status_code == 409 and conflict.json()['detail']['code'] == 'IDEMPOTENCY_CONFLICT'
    db.expire_all()
    pub = db.get(SocialPublication, pub.id)
    assert (pub.revision_id, pub.approved_by, pub.approved_at, pub.approved_hash, pub.content_valid_until) == immutable
    assert [(t.id, t.payload_hash, t.resolved_payload) for t in db.scalars(select(SocialPostTarget).order_by(SocialPostTarget.id))] == frozen
    assert len(list(db.scalars(select(SocialAuditEvent).where(SocialAuditEvent.action == 'post.rescheduled')))) == 1


def test_publish_now_preserves_completed_disconnected_target(db):
    client, base, post, accounts = scheduled_fixture(db, 2)
    target = db.get(SocialPostTarget, UUID(post['targets'][0]['id']))
    account_row = next(a for a in accounts if a.id == target.account_id)
    account_row.connection_state = 'disconnected'
    target.state, target.primary_remote_id, target.confirmation_kind = 'published', 'remote-2', 'fixture'
    target.visibility_state, target.published_at, target.remote_url = 'public', SocialService(db).now(), 'https://example.org/posts/remote-2'
    target.submit_count = 1
    db.commit()
    current = client.get(base).json()
    response = client.post(base + '/publish-now', json=command_body(current), headers=key())
    assert response.status_code == 202, response.text
    changed = response.json()
    assert next(t for t in changed['targets'] if t['id'] == str(target.id)) == next(t for t in current['targets'] if t['id'] == str(target.id))
    unsent = next(t for t in changed['targets'] if t['id'] != str(target.id))
    assert unsent['state'] == 'queued'
    assert unsent['next_action_at'] == changed['publication']['scheduled_for']


@pytest.mark.parametrize('field,value', [('expected_version', True), ('expected_publication_version', True), ('expected_publication_version', 0), ('reason', ''), ('publication_id', 'bad')])
def test_schedule_commands_require_strict_versions_identity_reason(db, field, value):
    client, base, post, _ = scheduled_fixture(db)
    response = client.post(base + '/publish-now', json={**command_body(post), field: value}, headers=key())
    assert response.status_code == 422, response.text


@pytest.mark.parametrize('mutation,code', [('lease', 'TARGET_BUSY'), ('checkpoint', 'INVALID_STATE'), ('attempt', 'INVALID_STATE'), ('expired', 'AUTHORIZATION_EXPIRED'), ('validity', 'AUTHORIZATION_EXPIRED'), ('version', 'VERSION_CONFLICT')])
def test_schedule_edit_fails_closed_without_mutation(db, mutation, code):
    client, base, post, _ = scheduled_fixture(db)
    target = db.get(SocialPostTarget, UUID(post['targets'][0]['id']))
    pub = db.get(SocialPublication, UUID(post['publication']['id']))
    if mutation == 'lease':
        target.state, target.lease_token, target.lease_owner = 'claimed', uuid4(), 'fixture-worker'
        target.lease_expires_at = SocialService(db).now() + timedelta(minutes=1)
    elif mutation == 'checkpoint': target.checkpoint = {'container_id': 'unresolved'}
    elif mutation == 'attempt':
        db.add(SocialPublishAttempt(target_id=target.id, sequence=1, operation_id=uuid4(), operation='create_container', request_fingerprint='f'*64, lease_epoch=1, outcome="intent"))
    elif mutation == 'expired': pub.start_deadline = SocialService(db).now() - timedelta(seconds=1)
    elif mutation == 'validity': pub.content_valid_until = SocialService(db).now() - timedelta(seconds=1)
    elif mutation == 'version': pub.version += 1
    db.commit()
    before = client.get(base).json()
    response = client.post(base + '/publish-now', json=command_body(post), headers=key())
    assert response.status_code == 409, response.text
    assert response.json()['detail']['code'] == code
    assert client.get(base).json() == before


def test_cancel_keeps_claim_and_unresolved_intent_and_reports_ids(db):
    client, base, post, _ = scheduled_fixture(db)
    target = db.get(SocialPostTarget, UUID(post['targets'][0]['id']))
    token = uuid4()
    target.state, target.lease_token, target.lease_owner = 'claimed', token, 'fixture-worker'
    target.lease_expires_at = SocialService(db).now() + timedelta(minutes=1)
    db.commit()
    response = client.post(base + '/cancel', json={'expected_version': post['version']}, headers=key())
    assert response.status_code == 200, response.text
    cancelled = response.json()
    assert cancelled['targets'][0]['state'] == 'claimed'
    assert cancelled['cancellation']['in_flight_target_ids'] == [str(target.id)]
    db.expire_all()
    assert db.get(SocialPostTarget, target.id).lease_token == token


def test_global_membership_across_several_pages_attention_and_cancelled_schedule(db):
    client, base, original, accounts = scheduled_fixture(db, 2)
    expected = {'scheduled': set(), 'history': set(), 'needs_attention': set()}
    scenarios = [
        (('published', 'queued'), ('scheduled', 'history'), False),
        (('queued', 'queued'), ('scheduled',), False),
        (('failed', 'cancelled'), ('history', 'needs_attention'), False),
        (('blocked', 'reconciling'), ('needs_attention',), False),
        (('outcome_unknown', 'queued'), ('scheduled', 'history', 'needs_attention'), False),
        (('queued', 'queued'), (), True),
    ]
    due = SocialService(db).now() + timedelta(days=1)
    for index, (states, memberships, cancelled) in enumerate(scenarios):
        created = client.post('/api/v1/admin/social/posts', json=draft_body(accounts, title=f'Scenario {index}').model_dump(mode='json'), headers=key()).json()
        route = '/api/v1/admin/social/posts/' + created['id']
        response = client.post(route + '/schedule', json={'expected_version': 1, 'revision_id': created['revision_id'], 'schedule': {'local_time': due.replace(tzinfo=None).isoformat(), 'timezone': 'UTC', 'utc_offset': '+00:00'}}, headers=key())
        assert response.status_code == 202
        current = client.get(route).json()
        for row, state in zip(current['targets'], states):
            target = db.get(SocialPostTarget, UUID(row['id']))
            target.state = state
            if state == 'published':
                target.primary_remote_id, target.confirmation_kind, target.visibility_state, target.published_at = str(uuid4()), 'fixture', 'public', SocialService(db).now()
        if cancelled:
            db.get(SocialPublication, UUID(current['publication']['id'])).cancel_requested_at = SocialService(db).now()
        db.commit()
        for membership in memberships: expected[membership].add(created['id'])
    expected['scheduled'].add(original['id'])
    for delivery, ids in expected.items():
        collected = []
        for page in range(1, 5):
            result = client.get('/api/v1/admin/social/posts', params={'delivery_filter': delivery, 'page_size': 2, 'page': page}).json()
            assert result['total'] == len(ids)
            assert result['has_more'] == (page * 2 < len(ids))
            collected.extend(p['id'] for p in result['posts'])
        assert len(collected) == len(set(collected)) and set(collected) == ids


def test_reschedule_caps_deadlines_at_original_validity_and_refuses_due_after_it(db):
    client, base, post, _ = scheduled_fixture(db)
    pub = db.get(SocialPublication, UUID(post['publication']['id']))
    now = SocialService(db).now()
    validity, due = now + timedelta(hours=4), now + timedelta(hours=3, minutes=30)
    pub.content_valid_until = validity
    db.commit()
    body = {**command_body(post), 'schedule': {'local_time': due.replace(tzinfo=None).isoformat(), 'timezone': 'UTC', 'utc_offset': '+00:00'}}
    response = client.post(base + '/reschedule', json=body, headers=key())
    assert response.status_code == 200, response.text
    db.expire_all()
    pub = db.get(SocialPublication, pub.id)
    assert utc(pub.content_valid_until) == validity
    assert utc(pub.start_deadline) == validity and utc(pub.retry_deadline) == validity
    current = response.json()
    past_validity = validity + timedelta(seconds=1)
    refused = client.post(base + '/reschedule', json={**command_body(current), 'schedule': {**body['schedule'], 'local_time': past_validity.replace(tzinfo=None).isoformat()}}, headers=key())
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'AUTHORIZATION_EXPIRED'
    assert client.get(base).json() == current


@pytest.mark.parametrize('change,code', [('pause', 'PUBLISHING_PAUSED'), ('disconnect', 'TARGET_VALIDATION_FAILED'), ('caps', 'REVISION_INTEGRITY_FAILED'), ('cancelled', 'INVALID_STATE')])
def test_schedule_changes_recheck_current_gates_and_keep_authorization(db, change, code):
    from social.models import SocialControls
    client, base, post, accounts = scheduled_fixture(db)
    if change == 'pause': db.get(SocialControls, 1).publishing_enabled = False
    elif change == 'disconnect': accounts[0].connection_state = 'disconnected'
    elif change == 'caps':
        accounts[0].capability_snapshot = {**accounts[0].capability_snapshot, 'rules_version': 'new-rules'}
    elif change == 'cancelled':
        db.get(SocialPublication, UUID(post['publication']['id'])).cancel_requested_at = SocialService(db).now()
    db.commit()
    before = client.get(base).json()
    response = client.post(base + '/publish-now', json=command_body(post), headers=key())
    assert response.status_code == (422 if change == 'disconnect' else 409), response.text
    assert response.json()['detail']['code'] == code
    assert client.get(base).json() == before


def test_scheduling_mixed_unresolved_container_never_reuses_or_mutates_its_intent(db):
    client, base, post, _ = scheduled_fixture(db, 2)
    target = db.get(SocialPostTarget, UUID(post['targets'][0]['id']))
    target.state, target.checkpoint = 'outcome_unknown', {'container_id': 'unresolved-container'}
    attempt = SocialPublishAttempt(id=uuid4(), target_id=target.id, sequence=1, operation_id=uuid4(), operation='create_container', request_fingerprint='f'*64, lease_epoch=1, outcome='ambiguous', receipt={'intent': {'mutating': True}}, dispatch_started_at=SocialService(db).now())
    db.add(attempt)
    db.commit()
    before = client.get(base).json()
    response = client.post(base + '/publish-now', json=command_body(post), headers=key())
    assert response.status_code == 202, response.text
    assert next(t for t in response.json()['targets'] if t['id'] == str(target.id)) == next(t for t in before['targets'] if t['id'] == str(target.id))
    db.expire_all()
    assert db.get(SocialPostTarget, target.id).checkpoint == {'container_id': 'unresolved-container'}
    assert db.get(SocialPublishAttempt, attempt.id).outcome == 'ambiguous'
