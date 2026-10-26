"""Private loopback PostgreSQL only; no shared/hosted database or target fixtures."""
import os
from time import monotonic

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError, TimeoutError


@pytest.fixture
def url():
    value = os.getenv('B91_PG_URL')
    if not value:
        pytest.skip('Requires the owned no-network B91 PostgreSQL sandbox')
    assert value == 'postgresql+psycopg2://postgres@127.0.0.1:55867/postgres'
    return value


def test_postgres_readonly_preamble_preserves_stricter_limits_and_rollback(url):
    from request_database import create_request_engine
    from middleware.request_resources import request_deadline
    engine = create_request_engine(url,{})
    token = request_deadline.set(monotonic()+2)
    try:
        with engine.connect() as connection:
            with pytest.raises(DBAPIError) as failure:
                with connection.begin():
                    connection.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                    connection.exec_driver_sql("SET LOCAL statement_timeout='45ms'")
                    connection.exec_driver_sql("SET LOCAL lock_timeout='25ms'")
                    row = connection.exec_driver_sql("SELECT current_setting('transaction_isolation'),current_setting('transaction_read_only'),current_setting('statement_timeout'),current_setting('lock_timeout')").one()
                    assert row == ('repeatable read','on','45ms','25ms')
                    started = monotonic()
                    connection.exec_driver_sql('SELECT pg_sleep(0.15)')
            assert failure.value.orig.pgcode == '57014'
            assert monotonic()-started < .4
            # Bypass only the test's event hook to inspect the same physical
            # connection after rollback: transaction-local policy did not leak.
            driver = connection.connection.driver_connection
            with driver.cursor() as cursor:
                cursor.execute('SHOW statement_timeout')
                assert cursor.fetchone() == ('2s',)
                cursor.execute('SHOW lock_timeout')
                assert cursor.fetchone() == ('500ms',)
            driver.rollback()
    finally:
        request_deadline.reset(token)
        engine.dispose()


def test_private_postgres_pool_refuses_checkout_without_overflow(url,monkeypatch):
    import request_database as policy
    monkeypatch.setattr(policy,'POOL_SIZE',1)
    monkeypatch.setattr(policy,'POOL_TIMEOUT',.05)
    engine = policy.create_request_engine(url,{})
    try:
        with engine.connect():
            started = monotonic()
            with pytest.raises(TimeoutError):
                engine.connect()
            assert monotonic()-started < .3
    finally:
        engine.dispose()


def test_private_postgres_lock_wait_obeys_request_budget(url,monkeypatch):
    import request_database as policy
    monkeypatch.setattr(policy,'STATEMENT_MS',200)
    monkeypatch.setattr(policy,'LOCK_MS',40)
    request_engine = policy.create_request_engine(url,{})
    owner = create_engine(url,pool_size=1,max_overflow=0)
    try:
        with owner.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE b91_owned_request_lock (id int)')
        with owner.begin() as locked:
            locked.exec_driver_sql('LOCK TABLE b91_owned_request_lock IN ACCESS EXCLUSIVE MODE')
            started = monotonic()
            with pytest.raises(DBAPIError) as failure:
                with request_engine.begin() as blocked:
                    blocked.exec_driver_sql('SELECT count(*) FROM b91_owned_request_lock')
            assert failure.value.orig.pgcode == '55P03'
            assert monotonic()-started < .4
    finally:
        with owner.begin() as connection:
            connection.exec_driver_sql('DROP TABLE IF EXISTS b91_owned_request_lock')
        request_engine.dispose()
        owner.dispose()


def test_postgres_negative_limit_is_an_error_not_an_unbounded_read(url):
    engine = create_engine(url)
    try:
        with pytest.raises(DBAPIError) as failure:
            with engine.begin() as connection:
                connection.exec_driver_sql('SELECT * FROM generate_series(1,2) LIMIT -1')
        assert failure.value.orig.pgcode == '2201W'
    finally:
        engine.dispose()
