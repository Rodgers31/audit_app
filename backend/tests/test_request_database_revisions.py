"""Owned loopback PostgreSQL regressions for #815 database/audit feedback."""
import os
from time import monotonic
from types import SimpleNamespace

import pytest
import psycopg2.extensions
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import TimeoutError


@pytest.fixture
def pg_url():
    value = os.environ.get('B91_PG_URL')
    if value != 'postgresql+psycopg2://postgres@127.0.0.1:55867/postgres':
        pytest.skip('Requires the explicitly owned B91 sandbox PostgreSQL')
    return value


def test_audit_commit_has_independent_capacity_and_deadline(pg_url, monkeypatch):
    import database
    import request_database as policy
    import admin_users_provider
    from utils.audit import record_admin_action
    from models import AdminAuditLog
    from middleware.request_resources import request_deadline
    monkeypatch.setattr(policy, 'POOL_SIZE', 1)
    monkeypatch.setattr(policy, 'POOL_TIMEOUT', .025)
    request_engine = policy.create_request_engine(pg_url, {})
    audit_engine = getattr(policy, 'create_audit_engine', policy.create_request_engine)(pg_url, {})
    owner = create_engine(pg_url)
    AdminAuditLog.__table__.create(owner)
    monkeypatch.setattr(database, 'RequestSessionLocal', sessionmaker(bind=request_engine))
    monkeypatch.setattr(database, 'AuditSessionLocal', sessionmaker(bind=audit_engine), raising=False)
    actor = SimpleNamespace(id='owned-local-admin', email=None)
    try:
        with request_engine.connect():
            token = request_deadline.set(monotonic() - 1)
            try:
                record_admin_action(None, actor=actor, action='etl.trigger')
                accepted = admin_users_provider.record_admin_action(None, actor=actor, action='users.delete')
            finally:
                request_deadline.reset(token)
        with owner.connect() as conn:
            count = conn.execute(text('SELECT count(*) FROM admin_audit_log')).scalar_one()
        assert accepted is True and count == 2
        assert audit_engine.pool.size() <= 2 and audit_engine.pool._max_overflow == 0
    finally:
        AdminAuditLog.__table__.drop(owner)
        request_engine.dispose()
        audit_engine.dispose()
        owner.dispose()


@pytest.mark.parametrize('mode', ['dependency', 'wrapped_by_route'])
def test_mounted_pool_saturation_is_retryable_503(client, monkeypatch, mode):
    import main
    import database
    class Busy:
        def query(self, *args):
            raise TimeoutError('Owned local checkout budget exhausted')
    def unavailable():
        if mode == 'dependency':
            raise TimeoutError('Owned local checkout budget exhausted')
        return Busy()
    monkeypatch.setitem(main.app.dependency_overrides, database.get_db, unavailable)
    monkeypatch.setattr(main, 'redis_cache', SimpleNamespace(get=lambda _: None, set=lambda *a, **k: None))
    response = client.get('/api/v1/debt/top-loans?limit=97')
    assert response.status_code == 503, response.text
    assert response.headers['retry-after'] == '1'
    assert response.headers['cache-control'] == 'no-store'


def test_statement_policy_is_once_per_transaction_and_resets(pg_url):
    from request_database import create_request_engine
    calls = []
    class CountingCursor(psycopg2.extensions.cursor):
        def execute(self, query, *args, **kwargs):
            calls.append(str(query))
            return super().execute(query, *args, **kwargs)
    engine = create_request_engine(pg_url, {'cursor_factory': CountingCursor})
    try:
        with engine.connect() as conn:
            calls.clear()
            for _ in range(5):
                assert conn.exec_driver_sql('SELECT 1').scalar_one() == 1
            settings = [q for q in calls if "set_config('statement_timeout'" in q]
            assert len(settings) == 1, settings
            conn.rollback()
            calls.clear()
            conn.exec_driver_sql('SELECT 2')
            assert len([q for q in calls if "set_config('statement_timeout'" in q]) == 1
    finally:
        engine.dispose()


def test_stale_owned_connection_reconnects_without_hidden_reader_transaction(pg_url, monkeypatch):
    import request_database as policy
    monkeypatch.setattr(policy, 'POOL_SIZE', 1)
    engine = policy.create_request_engine(pg_url, {})
    owner = create_engine(pg_url)
    try:
        with engine.connect() as conn:
            pid = conn.exec_driver_sql('SELECT pg_backend_pid()').scalar_one()
            conn.commit()
        with owner.connect() as conn:
            assert conn.exec_driver_sql('SELECT pg_terminate_backend(%s)', (pid,)).scalar_one() is True
        with engine.connect() as conn:
            assert conn.connection.driver_connection.get_transaction_status() == psycopg2.extensions.TRANSACTION_STATUS_IDLE
            conn.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            assert conn.exec_driver_sql('SELECT pg_backend_pid()').scalar_one() != pid
    finally:
        engine.dispose()
        owner.dispose()


def test_ping_caps_are_local_and_reader_starts_idle(pg_url, monkeypatch):
    import request_database as policy
    monkeypatch.setattr(policy, 'POOL_SIZE', 1)
    observed = []
    class InspectingCursor(psycopg2.extensions.cursor):
        def execute(self, query, *args, **kwargs):
            observed.append(str(query))
            return super().execute(query, *args, **kwargs)
    engine = policy.create_request_engine(pg_url, {'cursor_factory': InspectingCursor})
    legacy = create_engine(pg_url)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SET LOCAL statement_timeout='45ms'")
            conn.exec_driver_sql("SET LOCAL lock_timeout='25ms'")
            conn.rollback()
        observed.clear()
        with engine.connect() as conn:
            assert len(observed) == 1 and observed[0] == policy._PING_SQL
            assert conn.connection.driver_connection.get_transaction_status() == psycopg2.extensions.TRANSACTION_STATUS_IDLE
            conn.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            driver = conn.connection.driver_connection
            with driver.cursor() as cursor:
                cursor.execute("SELECT current_setting('statement_timeout'),current_setting('lock_timeout')")
                assert cursor.fetchone() == ('2s', '500ms')
            conn.rollback()
        assert getattr(engine.dialect.do_ping, '__func__', engine.dialect.do_ping) is not legacy.dialect.do_ping.__func__
    finally:
        engine.dispose()
        legacy.dispose()


@pytest.mark.parametrize('operation,code', [('readonly', '25006'), ('timeout', '57014')])
def test_ping_batch_enforces_readonly_and_local_timeout_then_restores_defaults(pg_url, monkeypatch, operation, code):
    import request_database as policy
    monkeypatch.setattr(policy, 'STATEMENT_MS', 25)
    engine = policy.create_request_engine(pg_url, {})
    owner = create_engine(pg_url)
    try:
        with owner.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE owned_ping_write (id int)')
        raw = engine.raw_connection()
        try:
            driver = raw.driver_connection
            command = 'INSERT INTO owned_ping_write VALUES(1)' if operation == 'readonly' else 'SELECT pg_sleep(0.1)'
            monkeypatch.setattr(policy, '_PING_SQL', policy._PING_SQL.replace('SELECT 1; ROLLBACK', command + '; ROLLBACK'))
            started = monotonic()
            with pytest.raises(psycopg2.Error) as failure:
                engine.dialect.do_ping(driver)
            assert failure.value.pgcode == code
            assert monotonic() - started < .5
            assert driver.get_transaction_status() == psycopg2.extensions.TRANSACTION_STATUS_IDLE
            with driver.cursor() as cursor:
                cursor.execute("SELECT current_setting('statement_timeout'),current_setting('lock_timeout')")
                assert cursor.fetchone() == ('2s', '500ms')
            driver.rollback()
        finally:
            raw.close()
        with owner.connect() as conn:
            assert conn.exec_driver_sql('SELECT count(*) FROM owned_ping_write').scalar_one() == 0
    finally:
        with owner.begin() as conn:
            conn.exec_driver_sql('DROP TABLE IF EXISTS owned_ping_write')
        owner.dispose()
        engine.dispose()


def test_cached_limits_tighten_for_final_deadline_and_expire_before_cursor(pg_url, monkeypatch):
    import request_database as policy
    from middleware.request_resources import request_deadline
    now = [100.0]
    monkeypatch.setattr(policy, 'monotonic', lambda: now[0])
    engine = policy.create_request_engine(pg_url, {})
    token = request_deadline.set(102.0)
    try:
        with engine.connect() as conn:
            assert conn.exec_driver_sql("SHOW statement_timeout").scalar_one() == '2s'
            now[0] = 101.98
            value = conn.exec_driver_sql("SHOW statement_timeout").scalar_one()
            assert value in {'19ms', '20ms'}
            now[0] = 103
            with pytest.raises(TimeoutError, match='Request database time budget exceeded'):
                conn.exec_driver_sql('SELECT pg_sleep(1)')
    finally:
        request_deadline.reset(token)
        engine.dispose()


def test_real_pool_exhaustion_through_mounted_top_loans_is_503(pg_url, client, monkeypatch):
    import database
    import main
    import request_database as policy
    monkeypatch.setattr(policy, 'POOL_SIZE', 1)
    monkeypatch.setattr(policy, 'POOL_TIMEOUT', .025)
    engine = policy.create_request_engine(pg_url, {})
    monkeypatch.setattr(database, 'RequestSessionLocal', sessionmaker(bind=engine))
    monkeypatch.delitem(main.app.dependency_overrides, database.get_db)
    monkeypatch.setattr(main, 'redis_cache', SimpleNamespace(get=lambda _: None, set=lambda *a, **k: None))
    try:
        with engine.connect():
            response = client.get('/api/v1/debt/top-loans?limit=96')
        assert response.status_code == 503, response.text
        assert response.headers['retry-after'] == '1'
        assert response.headers['cache-control'] == 'no-store'
    finally:
        engine.dispose()


def test_explicit_settings_change_invalidates_cached_limits(pg_url):
    from request_database import create_request_engine
    engine = create_request_engine(pg_url, {})
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql('SELECT 1')
            conn.exec_driver_sql('/* owned settings control */ SET LOCAL statement_timeout=0')
            # A deliberate loosening cannot leave the previous cached policy
            # claiming the following statement is still bounded.
            assert conn.exec_driver_sql('SHOW statement_timeout').scalar_one() == '5s'
            conn.exec_driver_sql("SELECT set_config('statement_timeout','45ms',true)")
            assert conn.exec_driver_sql('SHOW statement_timeout').scalar_one() == '45ms'
    finally:
        engine.dispose()


def test_savepoint_rollback_cannot_restore_a_looser_cached_deadline(pg_url, monkeypatch):
    import request_database as policy
    from middleware.request_resources import request_deadline
    now = [100.0]
    monkeypatch.setattr(policy, 'monotonic', lambda: now[0])
    engine = policy.create_request_engine(pg_url, {})
    token = request_deadline.set(102.0)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql('SELECT 1')
            nested = conn.begin_nested()
            now[0] = 101.9
            assert conn.exec_driver_sql('SHOW statement_timeout').scalar_one() in {'99ms', '100ms'}
            nested.rollback()
            assert conn.exec_driver_sql('SHOW statement_timeout').scalar_one() in {'99ms', '100ms'}
    finally:
        request_deadline.reset(token)
        engine.dispose()


@pytest.mark.parametrize('expired', [False, True])
def test_aborted_savepoint_cleanup_survives_tightened_or_expired_deadline(pg_url, monkeypatch, expired):
    import request_database as policy
    from middleware.request_resources import request_deadline
    from sqlalchemy.exc import DBAPIError
    now = [100.0]
    monkeypatch.setattr(policy, 'monotonic', lambda: now[0])
    engine = policy.create_request_engine(pg_url, {})
    token = request_deadline.set(104.0)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql('SELECT 1')
            nested = conn.begin_nested()
            with pytest.raises(DBAPIError) as failure:
                conn.exec_driver_sql('SELECT 1/0')
            assert failure.value.orig.pgcode == '22012'
            now[0] = 105.0 if expired else 103.0
            nested.rollback()
            if expired:
                with pytest.raises(TimeoutError, match='Request database time budget exceeded'):
                    conn.exec_driver_sql('SELECT 1')
            else:
                assert conn.exec_driver_sql('SHOW statement_timeout').scalar_one() == '1s'
                assert conn.exec_driver_sql('SELECT 1').scalar_one() == 1
    finally:
        request_deadline.reset(token)
        engine.dispose()


def test_cleanup_exception_does_not_admit_a_following_work_statement(pg_url, monkeypatch):
    import request_database as policy
    from middleware.request_resources import request_deadline
    engine = policy.create_request_engine(pg_url, {})
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql('SELECT 1')
            token = request_deadline.set(monotonic()-1)
            try:
                with pytest.raises(TimeoutError, match='Request database time budget exceeded'):
                    conn.exec_driver_sql('ROLLBACK; SELECT pg_sleep(1)')
            finally:
                request_deadline.reset(token)
    finally:
        engine.dispose()
