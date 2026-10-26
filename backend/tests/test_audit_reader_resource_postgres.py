"""Actual restricted reader, checkout exhaustion and transaction-local reset.

This does not certify the hosted audit URL, its grants, or storage incarnation.
The unchanged durable-audit catalog admission remains independently mandatory.
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, TimeoutError
from sqlalchemy.orm import Session

from services import admin_audit_storage as storage


@pytest.fixture
def restricted_reader():
    url = os.getenv('B91_PG_URL')
    if url is None:
        pytest.skip('Requires the owned no-network PostgreSQL sandbox')
    assert url == 'postgresql+psycopg2://postgres@127.0.0.1:55867/postgres'
    owner = create_engine(url)
    name = 'resource_reader_' + uuid4().hex
    engine = None
    try:
        with owner.begin() as db:
            db.exec_driver_sql(f'CREATE ROLE "{name}" LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB NOREPLICATION')
            db.exec_driver_sql(f'CREATE SCHEMA "{name}"')
            db.exec_driver_sql(f'CREATE TABLE "{name}".observations (id int)')
            db.exec_driver_sql(f'INSERT INTO "{name}".observations VALUES (7)')
            db.exec_driver_sql(f'GRANT USAGE ON SCHEMA "{name}" TO "{name}"')
            db.exec_driver_sql(f'GRANT SELECT ON "{name}".observations TO "{name}"')
        restricted_url = make_url(url).set(username=name).render_as_string(hide_password=False)
        storage.reader_engine.cache_clear()
        engine = storage.reader_engine(restricted_url)
        yield owner, engine, name
    finally:
        if engine is not None:
            engine.dispose()
        storage.reader_engine.cache_clear()
        with owner.begin() as db:
            db.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
            db.exec_driver_sql(f'DROP ROLE IF EXISTS "{name}"')
        owner.dispose()


def test_restricted_reader_profile_and_no_session_timeout_leak(restricted_reader):
    owner, engine, name = restricted_reader
    with engine.connect() as db:
        assert db.exec_driver_sql('SELECT current_user').scalar() == name
        row = db.exec_driver_sql("SELECT rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,rolreplication FROM pg_roles WHERE rolname=current_user").one()
        assert tuple(row) == (False,) * 5
        assert db.exec_driver_sql(f'SELECT id FROM "{name}".observations').scalar() == 7
        assert db.exec_driver_sql('SHOW transaction_isolation').scalar() == 'repeatable read'
        assert db.exec_driver_sql('SHOW statement_timeout').scalar() == '2s'  # stricter server ceiling
        assert db.exec_driver_sql('SHOW lock_timeout').scalar() == '500ms'
        db.exec_driver_sql("SET LOCAL statement_timeout='35ms'")
        with pytest.raises(DBAPIError) as failed:
            db.exec_driver_sql('SELECT pg_sleep(.15)')
        assert failed.value.orig.pgcode == '57014'
        db.rollback()
        # Direct driver inspection bypasses only the policy hook to detect leakage.
        driver = db.connection.driver_connection
        with driver.cursor() as cur:
            cur.execute("SELECT current_setting('statement_timeout'),current_setting('lock_timeout')")
            assert cur.fetchone() == ('2s', '500ms')
        driver.rollback()
        with pytest.raises(DBAPIError) as denied:
            db.exec_driver_sql(f'DELETE FROM "{name}".observations')
        assert denied.value.orig.pgcode == '42501'
        db.rollback()
    # Reuse runs the actual bounded pre-ping and retains the reader isolation.
    with engine.connect() as db:
        assert db.exec_driver_sql('SHOW transaction_isolation').scalar() == 'repeatable read'
        assert db.exec_driver_sql(f'SELECT id FROM "{name}".observations').scalar() == 7


def test_reader_pool_exhaustion_preserves_independent_request_reserve(restricted_reader):
    owner, engine, name = restricted_reader
    borrowed = engine.connect()
    pool = ThreadPoolExecutor(max_workers=1)
    def checkout():
        started = time.monotonic()
        try:
            with engine.connect() as db:
                db.exec_driver_sql('SELECT 1')
            return 'admitted', time.monotonic() - started
        except TimeoutError:
            return 'refused', time.monotonic() - started
    future = pool.submit(checkout)
    try:
        outcome, elapsed = future.result(timeout=1.2)
        assert outcome == 'refused', 'audit reader admitted overflow beyond its one-slot reserve'
        assert .4 <= elapsed < 1.0
        with owner.connect() as db:
            assert db.execute(text('SELECT 1')).scalar() == 1
    finally:
        borrowed.close()
        pool.shutdown(wait=True)
    assert engine.pool.checkedout() == 0


def test_dependency_selects_restricted_engine_without_changing_writer(restricted_reader, monkeypatch):
    owner, engine, name = restricted_reader
    monkeypatch.setenv('ADMIN_AUDIT_DATABASE_URL', engine.url.render_as_string(hide_password=False))
    with Session(owner) as writer:
        dependency = storage.get_audit_db(writer)
        reader = next(dependency)
        try:
            assert reader.get_bind() is engine
            assert reader.execute(text('SELECT current_user')).scalar() == name
            assert writer.get_bind() is owner and not writer.in_transaction()
        finally:
            dependency.close()
    assert engine.pool.checkedout() == 0
