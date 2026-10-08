"""Deterministic claim/action interleavings on isolated actual PostgreSQL DDL.

Uses the random-schema domain fixture; never truncates the shared worker schema.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from uuid import UUID, uuid4

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from social.models import SocialPostTarget, SocialPublication, SocialPublishAttempt
from social.service import SocialService, utc
from social.worker.config import WorkerConfig
from social.worker.repository import QueueRepository
from test_domain_postgres import pg_engine
from test_schedule_management import scheduled_fixture, command_body


def prepared(engine):
    with Session(engine, expire_on_commit=False) as db:
        client, base, post, accounts = scheduled_fixture(db)
        target = db.get(SocialPostTarget, UUID(post['targets'][0]['id']))
        pub = db.get(SocialPublication, UUID(post['publication']['id']))
        now = SocialService(db).now()
        target.next_action_at = pub.scheduled_for = now - timedelta(seconds=1)
        pub.start_deadline, pub.retry_deadline = now + timedelta(hours=1), now + timedelta(hours=24)
        db.commit()
    repo = QueueRepository(engine, WorkerConfig(engine.url.render_as_string(hide_password=False)), uuid4())
    return client, base, client.get(base).json(), repo


def future_body(post):
    due = datetime.now(timezone.utc) + timedelta(days=1)
    return {**command_body(post), 'schedule': {'local_time': due.replace(tzinfo=None).isoformat(), 'timezone': 'UTC', 'utc_offset': '+00:00'}}


def test_pg_claim_commits_while_action_waits_then_action_conflicts(pg_engine):
    client, base, post, repo = prepared(pg_engine)
    claim_updated, target_lock_requested, release_claim = Event(), Event(), Event()
    def after(conn, cursor, statement, parameters, context, many):
        if 'WITH due AS' in statement:
            claim_updated.set()
            assert release_claim.wait(5), 'Claim fixture was not released'
    def before(conn, cursor, statement, parameters, context, many):
        if 'social_post_targets' in statement and 'FOR UPDATE' in statement and 'WITH due AS' not in statement:
            target_lock_requested.set()
    event.listen(pg_engine, 'after_cursor_execute', after)
    event.listen(pg_engine, 'before_cursor_execute', before)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            claim_future = pool.submit(repo.claim_due)
            assert claim_updated.wait(5)
            action = pool.submit(client.post, base + '/reschedule', json=future_body(post), headers={'Idempotency-Key': str(uuid4())})
            try:
                assert target_lock_requested.wait(5)
                assert not action.done()
            finally:
                release_claim.set()
            claim = claim_future.result(timeout=5)[0]
            response = action.result(timeout=5)
        assert response.status_code == 409, response.text
        assert response.json()['detail']['code'] == 'TARGET_BUSY'
        with Session(pg_engine) as db:
            target = db.get(SocialPostTarget, UUID(claim.target_id))
            assert target.state == 'claimed' and str(target.lease_token) == claim.token and target.lease_epoch == claim.epoch
            assert db.scalar(select(SocialPublishAttempt.id)) is None
    finally:
        release_claim.set()
        event.remove(pg_engine, 'after_cursor_execute', after)
        event.remove(pg_engine, 'before_cursor_execute', before)


def test_pg_action_locks_target_before_claim_then_future_due_is_unclaimable(pg_engine):
    client, base, post, repo = prepared(pg_engine)
    updated, release = Event(), Event()
    def after(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().startswith('UPDATE social_post_targets'):
            updated.set()
            assert release.wait(5), 'Schedule fixture was not released'
    event.listen(pg_engine, 'after_cursor_execute', after)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            action = pool.submit(client.post, base + '/reschedule', json=future_body(post), headers={'Idempotency-Key': str(uuid4())})
            try:
                assert updated.wait(5)
                assert repo.claim_due() == []  # SKIP LOCKED cannot claim a moving schedule.
            finally:
                release.set()
            response = action.result(timeout=5)
        assert response.status_code == 200, response.text
        assert repo.claim_due() == []  # Committed future due is no longer actionable.
        with Session(pg_engine) as db:
            target = db.get(SocialPostTarget, UUID(post['targets'][0]['id']))
            assert target.lease_epoch == 0 and target.lease_token is None
            assert utc(target.next_action_at) > SocialService(db).now()
    finally:
        release.set()
        event.remove(pg_engine, 'after_cursor_execute', after)


def begin(repo, claim):
    return repo.begin_operation(claim, operation_id=uuid4(), operation='publish', publication_capable=True, mutating=True, safe_replay_class='requires_reconciliation', request_fingerprint='a'*64, checkpoint_input={})


def test_pg_cancel_retains_claim_until_worker_acknowledges(pg_engine):
    client, base, post, repo = prepared(pg_engine)
    claim = repo.claim_due()[0]
    response = client.post(base + '/cancel', json={'expected_version': post['version']}, headers={'Idempotency-Key': str(uuid4())})
    assert response.status_code == 200, response.text
    assert response.json()['targets'][0]['state'] == 'claimed'
    assert response.json()['cancellation']['in_flight_target_ids'] == [claim.target_id]
    assert begin(repo, claim) is None  # Fresh admission sees cancellation and acknowledges.
    with Session(pg_engine) as db:
        target = db.get(SocialPostTarget, UUID(claim.target_id))
        assert target.state == 'cancelled' and target.lease_token is None
        assert db.scalar(select(SocialPublishAttempt.id)) is None


def test_pg_durable_intent_before_cancel_keeps_remote_outcome_authoritative(pg_engine):
    client, base, post, repo = prepared(pg_engine)
    claim = repo.claim_due()[0]
    intent = begin(repo, claim)
    assert intent is not None
    response = client.post(base + '/cancel', json={'expected_version': post['version']}, headers={'Idempotency-Key': str(uuid4())})
    assert response.status_code == 200, response.text
    assert response.json()['targets'][0]['state'] == 'dispatching'
    assert response.json()['cancellation']['in_flight_target_ids'] == [claim.target_id]
    assert repo.finish(claim, intent, state='published', outcome='confirmed_success', checkpoint={}, remote_refs={}, remote_id='confirmed-fixture', remote_url='https://example.org/confirmed-fixture', visibility_state='public', confirmation_kind='fixture-receipt', receipt={'fixture': 'confirmed'})
    with Session(pg_engine) as db:
        target = db.get(SocialPostTarget, UUID(claim.target_id))
        assert target.state == 'published' and target.published_at is not None
        assert db.get(SocialPublication, target.publication_id).cancel_requested_at is not None
        attempt = db.scalar(select(SocialPublishAttempt))
        assert str(attempt.operation_id) == intent.operation_id and attempt.outcome == 'confirmed_success'
