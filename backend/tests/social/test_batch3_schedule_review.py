"""Independent batch-three queue review; SQLite and random-schema PostgreSQL only."""
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from social.models import SocialCommandReceipt, SocialPostTarget, SocialPublication
from social.service import SocialError, SocialService
from test_api_admin import key, make_client
from test_domain_support import db
from test_domain_postgres import pg_engine
from test_schedule_management import command_body, scheduled_fixture
from test_schedule_management import test_global_filters_precede_pagination_and_mixed_posts_overlap as check_global_filters


@pytest.mark.parametrize('field,value', [
    ('page', True), ('page', False), ('page', 0), ('page', -1),
    ('page', 1.5), ('page', '1'), ('page', None),
    ('page_size', True), ('page_size', 0), ('page_size', -1),
    ('page_size', 101), ('page_size', 1.5), ('page_size', '20'),
])
def test_direct_pagination_rejects_hostile_inputs_before_sql(db, field, value):
    with pytest.raises(SocialError) as raised:
        SocialService(db).posts(**{field: value})
    assert raised.value.code == 'INVALID_REQUEST' and raised.value.status == 422


def test_http_huge_page_cannot_overflow_database_offset(db):
    response = make_client(db.bind).get('/api/v1/admin/social/posts', params={'page': str(10 ** 100)})
    assert response.status_code in {200, 422}, response.text
    if response.status_code == 200:
        assert response.json()['posts'] == [] and response.json()['total'] == 0
    assert response.headers['cache-control'] == 'private, no-store'


def test_reschedule_unrepresentable_deadlines_is_safe_and_atomic(db):
    client, base, post, _ = scheduled_fixture(db)
    body = {**command_body(post), 'schedule': {
        'local_time': '9999-12-31T23:30:00', 'timezone': 'UTC', 'utc_offset': '+00:00'}}
    response = client.post(base + '/reschedule', json=body, headers=key())
    assert client.get(base).json() == post
    assert response.status_code in {409, 422}, response.text


@pytest.mark.parametrize('field,value', [
    ('expected_version', '2'), ('expected_version', 2.0),
    ('expected_publication_version', '2'), ('expected_publication_version', 2.0),
    ('reason', '  '), ('reason', 123), ('publication_id', True),
    ('acknowledged_warning_codes', ['accepted', 42]), ('surprise', 'extra'),
])
def test_schedule_http_body_is_strict_without_side_effects(db, field, value):
    client, base, post, _ = scheduled_fixture(db)
    response = client.post(base + '/publish-now', json={**command_body(post), field: value}, headers=key())
    assert response.status_code == 422, response.text
    assert client.get(base).json() == post


@pytest.mark.parametrize('schedule', [
    {'local_time': '2027-03-14T02:30:00', 'timezone': 'America/New_York', 'utc_offset': '-05:00'},
    {'local_time': '2027-11-07T01:30:00', 'timezone': 'America/New_York', 'utc_offset': '-03:00'},
    {'local_time': '2030-01-01T12:00:00Z', 'timezone': 'UTC', 'utc_offset': '+00:00'},
    {'local_time': '2030-01-01T12:00:00', 'timezone': '../UTC', 'utc_offset': '+00:00'},
])
def test_schedule_civil_time_boundary_is_atomic(db, schedule):
    client, base, post, _ = scheduled_fixture(db)
    response = client.post(base + '/reschedule', json={**command_body(post), 'schedule': schedule}, headers=key())
    assert response.status_code == 422, response.text
    assert client.get(base).json() == post


def test_schedule_verifies_completed_frozen_payload_too(db):
    client, base, post, _ = scheduled_fixture(db, 2)
    completed = db.get(SocialPostTarget, UUID(post['targets'][0]['id']))
    completed.state, completed.submit_count = 'published', 1
    completed.primary_remote_id, completed.confirmation_kind = 'independent-proof', 'fixture'
    completed.visibility_state, completed.published_at = 'public', SocialService(db).now()
    db.commit()
    # SQLite raw corruption bypasses the existing ORM immutable-payload guard;
    # production PostgreSQL also blocks it with a database trigger.
    db.execute(update(SocialPostTarget).where(SocialPostTarget.id == completed.id).values(
        resolved_payload={**completed.resolved_payload, 'content_hash': '0' * 64}))
    db.commit()
    before = client.get(base).json()
    response = client.post(base + '/publish-now', json=command_body(before), headers=key())
    assert response.status_code == 503 and response.json()['detail']['code'] == 'REVISION_INTEGRITY_FAILED', response.text
    assert client.get(base).json() == before


def test_original_content_validity_equal_to_due_does_not_extend_authorization(db):
    client, base, post, _ = scheduled_fixture(db)
    pub = db.get(SocialPublication, UUID(post['publication']['id']))
    deadline = SocialService(db).now() + timedelta(hours=4)
    pub.content_valid_until = deadline
    db.commit()
    body = {**command_body(post), 'schedule': {
        'local_time': deadline.replace(tzinfo=None).isoformat(), 'timezone': 'UTC', 'utc_offset': '+00:00'}}
    response = client.post(base + '/reschedule', json=body, headers=key())
    assert response.status_code == 409 and response.json()['detail']['code'] == 'AUTHORIZATION_EXPIRED', response.text
    assert client.get(base).json() == post


def test_mounted_controls_reply_matches_committed_idempotent_receipt(db):
    client = make_client(db.bind)
    headers = key()
    body = {'expected_version': 1, 'publishing_enabled': True, 'reason': 'Explicit fixture gate'}
    response = client.patch('/api/v1/admin/social/controls', json=body, headers=headers)
    assert response.status_code == 200, response.text
    first = response.json()
    assert first['publishing_enabled'] is True
    assert all(first[field] is False for field in ('generation_enabled', 'auto_approve_enabled', 'auto_schedule_enabled', 'auto_publish_enabled'))
    assert client.patch('/api/v1/admin/social/controls', json=body, headers=headers).json() == first
    db.expire_all()
    receipt = db.scalar(select(SocialCommandReceipt).where(SocialCommandReceipt.idempotency_key == UUID(headers['Idempotency-Key'])))
    assert receipt.response == first and receipt.http_status == 200


def test_cancel_retains_attempted_queued_work_and_remote_fields(db):
    client, base, post, _ = scheduled_fixture(db)
    target = db.get(SocialPostTarget, UUID(post['targets'][0]['id']))
    target.submit_count = 1
    target.checkpoint, target.remote_refs = {'operation': 'uncertain'}, {'container_id': 'opaque'}
    db.commit()
    before = client.get(base).json()
    response = client.post(base + '/cancel', json={'expected_version': post['version']}, headers=key())
    assert response.status_code == 200, response.text
    assert response.json()['targets'] == before['targets']
    assert response.json()['cancellation']['in_flight_target_ids'] == [str(target.id)]
    db.expire_all()
    kept = db.get(SocialPostTarget, target.id)
    assert kept.checkpoint == {'operation': 'uncertain'} and kept.remote_refs == {'container_id': 'opaque'}


def test_pg_global_queue_filters_use_counts_before_pagination(pg_engine):
    with Session(pg_engine, expire_on_commit=False) as session:
        check_global_filters(session)


def test_edit_retains_cancelled_delivery_in_global_history(db):
    client, base, original, _ = scheduled_fixture(db)
    response = client.patch(base, json={"expected_version": original["version"], "title": "Revised draft"}, headers=key())
    assert response.status_code == 200, response.text
    edited = response.json()
    assert edited["revision_id"] != original["revision_id"]
    assert edited["publication"] is None
    db.expire_all()
    assert db.get(SocialPublication, UUID(original["publication"]["id"])).revoked_at is not None
    assert db.get(SocialPostTarget, UUID(original["targets"][0]["id"])).state == "cancelled"
    history = client.get("/api/v1/admin/social/posts", params={"delivery_filter": "history"}).json()
    assert history["total"] == 1
    row = history["posts"][0]
    assert row["id"] == original["id"]
    assert row["publication"] is None  # Old authorization must not bind new draft.
