"""Owned PostgreSQL full-chain replay. No SQLite concurrency substitutes."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text, select, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError

from social.models import SocialPost, SocialPostRevision, SocialPublication, SocialPostTarget
from social.generation.models import SourceEvent, SourceCursor
from test_generation import configure, consume
from test_b83_generation_postgres import pg as current_schema_pg
from current_source_workflow_fixture import current_source_engine, observation, current_rule


def owned_url(value):
    message = 'Use only b15_generation_test on 127.0.0.1:55400 without query options'
    if not isinstance(value, str) or '?' in value:
        raise ValueError(message)
    try:
        url = make_url(value)
        valid = url.drivername in {'postgresql', 'postgresql+psycopg2'} and url.host == '127.0.0.1' and url.port == 55400 and url.database == 'b15_generation_test' and not url.query
    except Exception as error:
        raise ValueError(message) from error
    if not valid:
        raise ValueError(message)
    return url.set(drivername='postgresql+psycopg2', query={'hostaddr': '127.0.0.1'})


@pytest.fixture
def pg_engine():
    dsn = os.getenv('B15_GENERATION_TEST_DB_URL')
    if not dsn:
        pytest.skip('Requires owned b15-generation fixture with the complete Alembic chain')
    engine = create_engine(owned_url(dsn), pool_size=8, max_overflow=0)
    with engine.begin() as conn:
        if conn.scalar(text('select current_database()')) != 'b15_generation_test':
            raise RuntimeError('Owned database identity mismatch')
        if conn.scalar(text('select version_num from alembic_version')) != 'a704b15a0001':
            raise RuntimeError('Replay the complete frozen-base migration chain first')
        tables = conn.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname=current_schema() AND tablename LIKE 'social_%'" )).all()
        conn.execute(text('TRUNCATE ' + ','.join('"' + t + '"' for t in tables) + ' CASCADE'))
    try:
        yield engine
    finally:
        engine.dispose()


def test_owned_url_rejects_remote_query_and_wrong_resources():
    for value in (None, 'postgresql://postgres@remote:55400/b15_generation_test', 'postgresql://postgres@127.0.0.1:5432/b15_generation_test', 'postgresql://postgres@127.0.0.1:55400/production', 'postgresql://postgres@127.0.0.1:55400/b15_generation_test?host=remote'):
        with pytest.raises(ValueError, match='Use only'):
            owned_url(value)


def test_real_postgres_replay_race_one_draft_and_aba(current_source_engine):
    with Session(current_source_engine, expire_on_commit=False) as db:
        configure(db)
        assert consume(db, observation(current_source_engine))['status'] == 'baseline'
    start = Barrier(8)
    def run(_):
        start.wait(timeout=10)
        with Session(current_source_engine, expire_on_commit=False) as db:
            return consume(db, observation(current_source_engine, 2, '456.78'))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run, range(8)))
    assert [r['status'] for r in results].count('draft_created') == 1
    assert [r['status'] for r in results].count('unchanged') == 7
    with Session(current_source_engine, expire_on_commit=False) as db:
        assert db.scalar(select(func.count()).select_from(SourceEvent)) == 1
        assert db.scalar(select(func.count()).select_from(SocialPost)) == 1
        assert db.scalar(select(func.count()).select_from(SocialPostRevision)) == 1
        assert db.scalar(select(func.count()).select_from(SocialPublication)) == 0
        assert db.scalar(select(func.count()).select_from(SocialPostTarget)) == 0
        db.rollback()
        assert consume(db, observation(current_source_engine, 3, '123.45'))['sequence'] == 2
        assert db.scalar(select(func.count()).select_from(SourceEvent)) == 2
        assert db.scalar(select(func.count()).select_from(SocialPost)) == 2


def test_pg_immutable_events_rules_decisions_and_legacy_off(current_source_engine):
    from test_domain_support import account
    from test_generation import rule, evaluate
    from social.service import SocialService
    with Session(current_source_engine, expire_on_commit=False) as db:
        a = account(db)
        configure(db, [a])
        created = consume(db, observation(current_source_engine, report=True), backfill=True)
        post = SocialService(db).detail(UUID(created['post_id']))
        db.rollback()
        policy = current_rule(db, [a])
        decision = evaluate(db, post, policy)
        assert decision['outcome'] == 'would_allow'
    statements = ["UPDATE social_source_events SET fingerprint='altered'", "DELETE FROM social_source_events", "UPDATE social_automation_rule_versions SET definition='{}'", "DELETE FROM social_shadow_decisions", "INSERT INTO social_controls(id,version,generation_enabled,auto_approve_enabled,auto_schedule_enabled,auto_publish_enabled,publishing_enabled,platform_controls,budget_controls) VALUES (1,1,true,false,false,false,false,'{}','{}')"]
    for statement in statements:
        with pytest.raises(DBAPIError):
            with current_source_engine.begin() as conn:
                conn.execute(text(statement))
    with current_source_engine.connect() as conn:
        assert conn.scalar(text("select count(*) from pg_class where relnamespace=current_schema()::regnamespace and relname in ('social_generation_controls','social_source_events','social_source_cursors','social_automation_rule_versions','social_shadow_decisions') and relrowsecurity")) == 5


def test_pg_failed_draft_rolls_back_and_replay_is_admitted(current_source_engine):
    from social.service import SocialError
    with Session(current_source_engine, expire_on_commit=False) as db:
        configure(db)
        consume(db, observation(current_source_engine))
        with pytest.raises(SocialError, match='UNRESOLVED_TEMPLATE'):
            consume(db, observation(current_source_engine, 2, '500', title='[TODO]'))
    with Session(current_source_engine, expire_on_commit=False) as fresh:
        assert fresh.scalar(select(SourceCursor)).sequence == 0
        assert fresh.scalar(select(func.count()).select_from(SourceEvent)) == 0
        fresh.rollback()
        assert consume(fresh, observation(current_source_engine, 2, '500'))['status'] == 'draft_created'


def prepared_post(engine, *, dispatch=False):
    from test_domain_support import account, call
    from social.models import SocialControls
    from social.service import SocialService
    from social.contracts import PublishCommand, ApproveCommand
    with Session(engine, expire_on_commit=False) as db:
        a = account(db)
        configure(db, [a])
        created = consume(db, observation(engine), backfill=True)
        if dispatch:
            db.get(SocialControls, 1).publishing_enabled = True
            db.commit()
        post = SocialService(db).detail(UUID(created['post_id']))
        db.rollback()
    return post


def test_generated_human_review_uses_actual_worker_pipeline(current_source_engine):
    import asyncio
    from social.contracts import PublishCommand, OperationPlan, OperationResult, CapabilitySet, ValidationResult
    from social.worker.runner import SocialWorker
    from test_queue_postgres import repository
    from test_domain_support import call
    post = prepared_post(current_source_engine, dispatch=True)
    with Session(current_source_engine, expire_on_commit=False) as db:
        body = PublishCommand(expected_version=post['version'], revision_id=post['revision_id'], review_attestation={'facts_checked': True, 'sources_checked': True})
        accepted = call(db, body, lambda s: s.publish(UUID(post['id']), body))[1]
        assert accepted['status'] == 'queued'
    class FactualFake:
        calls = 0
        def capabilities(self, account):
            return CapabilitySet.model_validate(account['capability_snapshot'])
        def validate(self, payload, capabilities):
            return ValidationResult(valid=True)
        def next_operation(self, payload, checkpoint):
            return OperationPlan(operation_id=uuid4(), operation='publish', publication_capable=True, safe_replay_class='requires_reconciliation', checkpoint=checkpoint)
        async def execute(self, payload, operation, credential, media_access):
            assert 'about KSh 123.5 million' in payload.text
            self.calls += 1
            return OperationResult(outcome='confirmed_success', primary_remote_id='owned-fake-post', visibility_state='public', confirmation_kind='owned-fixture-receipt')
    adapter = FactualFake()
    async def run():
        repo = repository(current_source_engine)
        worker = SocialWorker(repo, adapters={('facebook', 'fixture'): adapter})
        try:
            claims = await worker.db(repo.claim_due, 1)
            assert len(claims) == 1
            await worker.process(claims[0])
        finally:
            await worker.close()
    asyncio.run(run())
    with Session(current_source_engine) as db:
        assert db.scalar(select(SocialPostTarget)).state == 'published'
        assert db.scalar(select(SocialPublication)).authorization_kind == 'human'
    assert adapter.calls == 1


def test_correction_cancels_unsent_and_retains_claim_before_permit(current_source_engine):
    from social.contracts import PublishCommand
    from social.service import SocialService
    from test_domain_support import call
    from test_queue_postgres import repository
    post = prepared_post(current_source_engine, dispatch=True)
    with Session(current_source_engine, expire_on_commit=False) as db:
        body = PublishCommand(expected_version=post['version'], revision_id=post['revision_id'], review_attestation={'facts_checked': True, 'sources_checked': True})
        call(db, body, lambda s: s.publish(UUID(post['id']), body))
    repo = repository(current_source_engine)
    claim = repo.claim_due(1)[0]
    with Session(current_source_engine, expire_on_commit=False) as db:
        consume(db, observation(current_source_engine, 2, '500'))
        old = db.get(SocialPost, UUID(post['id']))
        publication = SocialService(db)._publication(old)
        assert publication.cancel_requested_at is not None
        target = db.scalar(select(SocialPostTarget).where(SocialPostTarget.publication_id == publication.id))
        assert target.lease_token is not None and str(target.lease_token) == claim.token
        assert target.state == 'claimed'  # ownership retained for worker acknowledgement
    intent = repo.begin_operation(claim, operation_id=uuid4(), operation='publish', publication_capable=True, mutating=True, request_fingerprint='a'*64, checkpoint_input={}, safe_replay_class='requires_reconciliation')
    assert intent is None
    with Session(current_source_engine) as db:
        assert db.scalar(select(func.count()).select_from(__import__('social.models', fromlist=['SocialPublishAttempt']).SocialPublishAttempt)) == 0


def test_approval_and_correction_are_serialized(current_source_engine, monkeypatch):
    from threading import Event
    from social.contracts import ApproveCommand
    from social.service import SocialService
    import social.generation.service as generation
    from test_domain_support import call
    post = prepared_post(current_source_engine)
    checked, release, correction_started = Event(), Event(), Event()
    original = generation.verify_generated_revision
    def paused(db, old_post, revision):
        original(db, old_post, revision)
        checked.set()
        if not release.wait(timeout=10):
            raise RuntimeError('Owned barrier timed out')
    monkeypatch.setattr(generation, 'verify_generated_revision', paused)
    def approve():
        with Session(current_source_engine, expire_on_commit=False) as db:
            body = ApproveCommand(expected_version=post['version'], revision_id=post['revision_id'], review_attestation={'facts_checked': True, 'sources_checked': True})
            return call(db, body, lambda s: s.approve(UUID(post['id']), body))[1]
    def correct():
        correction_started.set()
        with Session(current_source_engine, expire_on_commit=False) as db:
            return consume(db, observation(current_source_engine, 2, '500'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        approval = pool.submit(approve)
        assert checked.wait(timeout=10)
        correction = pool.submit(correct)
        assert correction_started.wait(timeout=10)
        # pg_locks proves a conflicting transaction actually waits; no sleep race.
        from time import monotonic
        with current_source_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
            deadline = monotonic() + 5
            while monotonic() < deadline:
                waiting = conn.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock'"))
                if waiting:
                    break
            else:
                raise AssertionError('Correction never reached the blocked database boundary')
        release.set()
        approval.result(timeout=10)
        correction.result(timeout=10)
    with Session(current_source_engine) as db:
        publication = SocialService(db)._publication(db.get(SocialPost, UUID(post['id'])))
        assert publication.cancel_requested_at is not None
        assert db.scalar(select(SocialPostTarget).where(SocialPostTarget.publication_id == publication.id)).state == 'cancelled'


def test_detect_does_not_hold_request_connection_during_committed_read(current_source_engine, monkeypatch):
    """Two occupied request connections must not starve their fresh readers."""
    from seeding import source_observations
    from test_api_admin import make_client, key
    start = Barrier(2)
    qualified = observation(current_source_engine)
    record = int(qualified.source_key.split(':')[1])
    job = int(qualified.ingestion_id)
    original_read = source_observations.read_county_budget_observation
    def read(factory, **kwargs):
        start.wait(timeout=5)
        return original_read(factory, **kwargs)
    monkeypatch.setattr(source_observations, 'read_county_budget_observation', read)
    with Session(current_source_engine, expire_on_commit=False) as db:
        configure(db)
    small = create_engine(current_source_engine.url, pool_size=2, max_overflow=0, pool_timeout=.3)
    def request(_):
        with make_client(small) as client:
            return client.post('/api/v1/admin/social/generation/detect', json={'record_ids':[record], 'ingestion_id':job, 'backfill':True, 'reason':'Bounded fresh reader regression'}, headers=key())
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(request, range(2)))
        assert [r.status_code for r in responses] == [200,200], [r.text for r in responses]
        assert sorted(r.json()['results'][0]['status'] for r in responses) == ['draft_created','unchanged']
    finally:
        small.dispose()


def test_hook_sql_limits_preserve_stricter_timeouts_and_are_local(pg_engine):
    import time
    from social.generation.integration import _transaction_limits
    with Session(pg_engine) as db:
        with db.begin():
            db.execute(text("SET LOCAL statement_timeout='50ms'"))
            db.execute(text("SET LOCAL lock_timeout='25ms'"))
            _transaction_limits(db, time.monotonic()+30)
            settings = dict(db.execute(text("SELECT name, setting::int FROM pg_settings WHERE name IN ('statement_timeout','lock_timeout')")).all())
            assert settings == {'statement_timeout': 50, 'lock_timeout': 25}
            with pytest.raises(DBAPIError):
                db.execute(text('SELECT pg_sleep(0.15)'))
    with Session(pg_engine) as db:
        settings = dict(db.execute(text("SELECT name, setting::int FROM pg_settings WHERE name IN ('statement_timeout','lock_timeout')")).all())
        assert settings == {'statement_timeout': 0, 'lock_timeout': 0}


def test_historical_generation_schema_retains_pinned_ddl(pg_engine):
    """The original a704 lane is a DDL contract, not a current ORM database."""
    with pg_engine.connect() as conn:
        assert conn.scalar(text('SELECT version_num FROM alembic_version')) == 'a704b15a0001'
        assert conn.scalar(text("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='social_source_cursors' AND column_name='report_state'")) == 0
        assert conn.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid='social_source_events'::regclass")) is True
