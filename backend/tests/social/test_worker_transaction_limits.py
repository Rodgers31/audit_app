"""Real PostgreSQL controls for poolers that discard startup options."""
import time

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

from social.worker.config import WorkerConfig, create_worker_engine
from worker_ownership_support import role_database


def pooled_engine(owner, schema):
    engine = create_worker_engine(WorkerConfig(
        owner.url.render_as_string(hide_password=False), database_schema=schema))

    @event.listens_for(engine, 'do_connect')
    def discard_startup_options(dialect, record, args, params):
        # Simulates the observed pooler boundary while executing every query
        # against real PostgreSQL. It does not replace the engine or SQL result.
        params.pop('options', None)
    return engine


def effective(connection, schema):
    row = connection.execute(text("SELECT current_setting('statement_timeout'),"
        "current_setting('lock_timeout'),current_setting('search_path')")).one()
    assert tuple(row[:2]) == ('5s', '2s')
    assert row[2].replace(' ', '') == 'pg_catalog,' + schema + ',pg_temp'


def test_limits_and_schema_survive_missing_startup_options_reuse_and_replacement(role_database):
    owner, _, schema, _ = role_database
    engine = pooled_engine(owner, schema)
    try:
        with engine.connect() as first, engine.connect() as second:
            for connection in (first, second):
                effective(connection, schema)
                connection.commit()
                # Emulate a pooler resetting session settings between work.
                raw = connection.connection.driver_connection
                raw.autocommit = True
                try:
                    with raw.cursor() as cursor:
                        cursor.execute("SET statement_timeout='2min'; SET lock_timeout='0'; SET search_path=public")
                finally:
                    raw.autocommit = False
                effective(connection, schema)
                connection.rollback()
        with engine.connect() as reused:
            effective(reused, schema)
            reused.rollback()
        engine.dispose()
        with engine.connect() as replacement:
            effective(replacement, schema)
    finally:
        engine.dispose()


def test_unpinned_maintenance_can_choose_read_only_repeatable_read(role_database):
    owner, _, _, _ = role_database
    engine = pooled_engine(owner, None)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            row = connection.execute(text("SELECT current_setting('statement_timeout'),"
                "current_setting('lock_timeout'),current_setting('search_path'),"
                "current_setting('transaction_isolation'),current_setting('transaction_read_only')")).one()
            assert row == ('5s', '2s', '"$user", public', 'repeatable read', 'on')
    finally:
        engine.dispose()


def test_effective_statement_deadline_cancels_actual_query(role_database):
    owner, _, schema, _ = role_database
    engine = pooled_engine(owner, schema)
    try:
        with engine.connect() as connection:
            started = time.monotonic()
            with pytest.raises(DBAPIError) as error:
                connection.execute(text('SELECT pg_sleep(10)'))
            assert error.value.orig.pgcode == '57014'
            assert 4 <= time.monotonic() - started < 9
            connection.rollback()
            effective(connection, schema)
    finally:
        engine.dispose()


def test_effective_lock_deadline_cancels_actual_wait(role_database):
    owner, _, schema, _ = role_database
    engine = pooled_engine(owner, schema)
    try:
        with owner.begin() as blocker:
            blocker.execute(text('LOCK TABLE ' + schema + '.social_controls IN ACCESS EXCLUSIVE MODE'))
            with engine.connect() as connection:
                started = time.monotonic()
                with pytest.raises(DBAPIError) as error:
                    connection.execute(text('SELECT id FROM ' + schema + '.social_controls'))
                assert error.value.orig.pgcode == '55P03'
                assert 1.5 <= time.monotonic() - started < 4.5
                connection.rollback()
                # Inspection is safe while the unrelated table remains locked.
                effective(connection, schema)
    finally:
        engine.dispose()
