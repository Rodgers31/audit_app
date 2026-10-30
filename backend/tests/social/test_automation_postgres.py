"""Assigned local PostgreSQL only; full migration and forced ordering proofs."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Barrier
from uuid import UUID, uuid4
import pytest
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, DBAPIError
from social.models import SocialControls, SocialPublication, SocialPostTarget
from social.service import SocialService, SocialError
from social.automation.models import PolicyDecision
from social.automation.service import worker_gate
from test_domain_support import account, call
from test_generation import rule
from test_automation import authorize, schedule
from test_b83_generation_postgres import pg as current_schema_pg
from current_source_workflow_fixture import (current_source_engine,
    accepted_current_snapshot as accepted_snapshot, current_candidate as candidate)


def owned_url(value):
    try:
        url = make_url(value)
        valid = url.drivername in {'postgresql', 'postgresql+psycopg2'} and url.host == '127.0.0.1' and url.port == 55406 and url.database == 'b15_policy_test' and not url.query
    except Exception:
        valid = False
    if not valid:
        raise ValueError('Requires owned 127.0.0.1:55406/b15_policy_test without options')
    return url.set(drivername='postgresql+psycopg2', query={'hostaddr':'127.0.0.1'})


@pytest.fixture
def pg_engine():
    dsn = os.getenv('B15_POLICY_TEST_DB_URL')
    if not dsn:
        pytest.skip('Requires assigned owned PostgreSQL with full a706b15a0001 chain')
    engine = create_engine(owned_url(dsn), pool_size=4, max_overflow=0, connect_args={'options':'-clock_timeout=3000 -cstatement_timeout=5000'})
    with engine.begin() as conn:
        if conn.scalar(text('select current_database()')) != 'b15_policy_test' or conn.scalar(text('select version_num from alembic_version')) != 'a706b15a0001':
            raise RuntimeError('Owned database/full migration head mismatch')
        tables = conn.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname=current_schema() AND tablename LIKE 'social_%'")).all()
        conn.execute(text('TRUNCATE '+','.join('"'+t+'"' for t in tables)+' CASCADE'))
    try:
        yield engine
    finally:
        engine.dispose()


def test_policy_fixture_url_guard():
    for value in (None, 'postgresql://postgres@remote:55406/b15_policy_test', 'postgresql://postgres@127.0.0.1:5432/b15_policy_test', 'postgresql://postgres@127.0.0.1:55406/production', 'postgresql://postgres@127.0.0.1:55406/b15_policy_test?host=remote'):
        with pytest.raises(ValueError): owned_url(value)


def test_pg_exact_authority_race_and_immutable_history(current_source_engine, monkeypatch):
    with Session(current_source_engine, expire_on_commit=False) as db:
        a = account(db)
        snapshot, _, _ = accepted_snapshot(db, a, monkeypatch)
        post = candidate(db)
    start = Barrier(2)
    def run(_):
        with Session(current_source_engine, expire_on_commit=False) as db:
            start.wait(timeout=5)
            try: return authorize(db, post, snapshot)['publication']['id']
            except SocialError as error: return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert results.count('VERSION_CONFLICT') == 1
    with Session(current_source_engine, expire_on_commit=False) as db:
        assert db.scalar(select(func.count()).select_from(PolicyDecision)) == 1
        pub = db.scalar(select(SocialPublication).where(SocialPublication.authorization_kind=='policy'))
        post = SocialService(db).detail(pub.post_id)
        db.rollback()
        schedule(db, post)
        pub = db.get(SocialPublication, pub.id)
        pub_id, account_id, now = pub.id, a.id, SocialService(db).now()
        db.rollback()
        with current_source_engine.begin() as conn:
            # Actual shared worker admission runs against a real borrowed ORM
            # transaction. No provider adapter, credential or external effect.
            conn.execute(text('SELECT id FROM social_controls WHERE id=1 FOR UPDATE'))
            assert worker_gate(conn, pub_id, account_id, 'facebook', now, public=True) is None
        db.rollback()
        with pytest.raises(DBAPIError):
            with current_source_engine.begin() as conn:
                conn.execute(text('UPDATE social_policy_decisions SET decision_hash=:hash'), {'hash':'0'*64})
        with pytest.raises(DBAPIError):
            with current_source_engine.begin() as conn:
                conn.execute(text('UPDATE social_publications SET policy_decision_id=:other WHERE id=:id'), {'id':pub.id, 'other':uuid4()})


def test_pg_rule_version_writer_waits_for_policy_dispatch_ordering(current_source_engine, monkeypatch):
    """Force newer disabled rule to compete with the final policy permit lock."""
    from social.generation.contracts import RuleCommand
    from social.generation.service import GenerationService
    with Session(current_source_engine, expire_on_commit=False) as db:
        a = account(db)
        snapshot, policy, _ = accepted_snapshot(db, a, monkeypatch)
    entered, completed = Event(), Event()
    body = RuleCommand.model_validate({'expected_version':1, **{**policy['definition'], 'mode':'disabled'}})
    def writer():
        with Session(current_source_engine, expire_on_commit=False) as db:
            entered.set()
            call(db, body, lambda svc: GenerationService(svc).save_rule(UUID(policy['id']), body))
        completed.set()
    with current_source_engine.begin() as permit:
        permit.execute(text('SELECT id FROM social_controls WHERE id=1 FOR UPDATE'))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(writer)
            assert entered.wait(2)
            # Query real pg_stat_activity for the blocked writer, not a sleep or
            # scheduler race: before fix it commits without this lock.
            from time import monotonic
            end = monotonic()+2
            waiting = False
            while monotonic() < end and not completed.is_set():
                with current_source_engine.connect() as observer:
                    waiting = bool(observer.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query ILIKE '%social_controls%FOR UPDATE%'")))
                if waiting: break
            assert waiting and not completed.is_set(), 'New rule committed across final policy ordering lock'
            permit.commit()
            future.result(timeout=5)
    assert completed.is_set()


def test_pg_storage_refuses_unbacked_nullable_authority(pg_engine):
    from test_automation import test_storage_refuses_null_policy_version_and_missing_authority
    with Session(pg_engine, expire_on_commit=False) as db:
        test_storage_refuses_null_policy_version_and_missing_authority(db)


def test_historical_policy_schema_retains_pinned_ddl(pg_engine):
    with pg_engine.connect() as conn:
        assert conn.scalar(text('SELECT version_num FROM alembic_version')) == 'a706b15a0001'
        assert conn.scalar(text("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='social_source_cursors' AND column_name='report_state'")) == 0
        assert conn.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid='social_authorized_policy_snapshots'::regclass")) is True
