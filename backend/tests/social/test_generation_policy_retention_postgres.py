"""Actual PostgreSQL downgrade retention at the destructive DDL boundary."""
import importlib.util
import os
from uuid import uuid4
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from test_domain_postgres import migration as domain_migration


def owned_url(raw):
    try:
        url = make_url(raw)
        valid = (isinstance(raw, str) and '?' not in raw
                 and url.drivername in {'postgresql', 'postgresql+psycopg2'}
                 and url.host == '127.0.0.1' and url.port == 55410
                 and url.database == 'b15_retention_test' and not url.query)
    except Exception:
        valid = False
    if not valid:
        raise ValueError('Requires owned127.0.0.1:55410/b15_retention_test without options')
    return url.set(drivername='postgresql+psycopg2', query={'hostaddr': '127.0.0.1'})


def test_retention_fixture_refuses_foreign_database_targets():
    for raw in (None, 'postgresql://fixture@remote:55410/b15_retention_test',
                'postgresql://fixture@127.0.0.1:5432/b15_retention_test',
                'postgresql://fixture@127.0.0.1:55410/production',
                'postgresql://fixture@127.0.0.1:55410/b15_retention_test?host=remote'):
        with pytest.raises(ValueError):
            owned_url(raw)


@pytest.fixture
def pg_engine():
    raw = os.getenv('B15_RETENTION_TEST_DATABASE_URL')
    if not raw:
        pytest.skip('Requires assigned owned PostgreSQL retention fixture')
    url = owned_url(raw)
    schema = 'retention_' + uuid4().hex
    admin = create_engine(url, pool_size=1, max_overflow=0)
    with admin.begin() as conn:
        conn.execute(text('CREATE SCHEMA ' + schema))
    engine = create_engine(url, pool_size=3, max_overflow=0,
                           connect_args={'options': '-csearch_path=' + schema})
    try:
        apply(engine, domain_migration(), 'upgrade')
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text('DROP SCHEMA ' + schema + ' CASCADE'))
        admin.dispose()



RULE = "INSERT INTO social_automation_rule_versions(id,rule_id,version,definition,definition_hash,created_by) VALUES('00000000-0000-4000-8000-000000000031','00000000-0000-4000-8000-000000000032',1,'{}','inert-rule','00000000-0000-4000-8000-000000000033')"
EVIDENCE = "INSERT INTO social_policy_operating_evidence(id,rule_version_id,evidence,evidence_hash,approved_by) VALUES('00000000-0000-4000-8000-000000000034','00000000-0000-4000-8000-000000000031','{}','inert-evidence','00000000-0000-4000-8000-000000000033')"
SNAPSHOT = "INSERT INTO social_authorized_policy_snapshots(id,rule_version_id,operating_evidence_id,version,snapshot,snapshot_hash,approved_by,valid_until) VALUES('00000000-0000-4000-8000-000000000035','00000000-0000-4000-8000-000000000031','00000000-0000-4000-8000-000000000034',1,'{}','inert-snapshot','00000000-0000-4000-8000-000000000033',now()+interval '1 hour')"


def migration(revision):
    files = list((Path(__file__).resolve().parents[2] / 'alembic/versions').glob(revision + '_*.py'))
    if len(files) != 1:
        raise RuntimeError('Expected one source migration')
    spec = importlib.util.spec_from_file_location('retention_' + revision, files[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def apply(engine, module, operation):
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        getattr(module, operation)()


def generation(engine):
    module = migration('a704b15a0001')
    apply(engine, module, 'upgrade')
    return module


def policy(engine):
    generation(engine)
    module = migration('a706b15a0001')
    apply(engine, module, 'upgrade')
    return module


def test_generation_downgrade_retains_immutable_rule_without_publication(pg_engine):
    module = generation(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text(RULE))
    with pytest.raises(RuntimeError, match='Generation history/controls prevent downgrade'):
        apply(pg_engine, module, 'downgrade')
    with pg_engine.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM social_automation_rule_versions')) == 1
        assert all(inspect(conn).has_table(table) for table in module.TABLES)


@pytest.mark.parametrize('with_snapshot', [False, True])
def test_policy_downgrade_retains_approved_evidence_without_publication(pg_engine, with_snapshot):
    module = policy(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text(RULE))
        conn.execute(text(EVIDENCE))
        if with_snapshot:
            conn.execute(text(SNAPSHOT))
        assert conn.scalar(text('SELECT count(*) FROM social_publications')) == 0
    with pytest.raises(RuntimeError, match='Policy history/controls prevent downgrade'):
        apply(pg_engine, module, 'downgrade')
    with pg_engine.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM social_policy_operating_evidence')) == 1
        assert conn.scalar(text('SELECT count(*) FROM social_authorized_policy_snapshots')) == int(with_snapshot)
        assert all(inspect(conn).has_table(table) for table in module.TABLES)


@pytest.mark.parametrize('revision', ['a704b15a0001', 'a706b15a0001'])
def test_empty_generation_policy_downgrade_still_allowed(pg_engine, revision):
    module = generation(pg_engine) if revision == 'a704b15a0001' else policy(pg_engine)
    apply(pg_engine, module, 'downgrade')
    with pg_engine.connect() as conn:
        assert not any(inspect(conn).has_table(table) for table in module.TABLES)
        assert inspect(conn).has_table('social_posts')


def test_policy_downgrade_retains_selection_even_when_unselected(pg_engine):
    module = policy(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text('INSERT INTO social_policy_selection(id,snapshot_id) VALUES(1,NULL)'))
    with pytest.raises(RuntimeError, match='Policy history/controls prevent downgrade'):
        apply(pg_engine, module, 'downgrade')


@pytest.mark.parametrize('revision', ['a704b15a0001', 'a706b15a0001'])
def test_downgrade_serializes_retention_check_with_competing_writer(pg_engine, revision):
    """Hold actual DDL transaction open; a late insert must wait for its lock."""
    module = generation(pg_engine) if revision == 'a704b15a0001' else policy(pg_engine)
    table = module.TABLES[0]
    with pg_engine.begin() as blocker:
        blocker.execute(text('LOCK TABLE ' + table + ' IN ROW EXCLUSIVE MODE'))
        # Source downgrade uses its own bounded2s lock wait. No artificial sleep
        # or scheduler-dependent assertion is needed for this refusal control.
        from sqlalchemy.exc import DBAPIError
        with pytest.raises(DBAPIError) as error:
            apply(pg_engine, module, 'downgrade')
        assert error.value.orig.pgcode == '55P03'
    with pg_engine.connect() as conn:
        assert all(inspect(conn).has_table(name) for name in module.TABLES)


@pytest.mark.parametrize('revision', ['a704b15a0001', 'a706b15a0001'])
def test_old_repeatable_read_snapshot_cannot_discard_later_committed_history(pg_engine, revision):
    module = generation(pg_engine) if revision == 'a704b15a0001' else policy(pg_engine)
    if revision == 'a706b15a0001':
        with pg_engine.begin() as writer:
            writer.execute(text(RULE))
    with pg_engine.connect().execution_options(isolation_level='REPEATABLE READ') as stale:
        with stale.begin():
            # Establish an actual old snapshot before the other transaction
            # commits retained history. Its table lock permits that INSERT.
            assert stale.scalar(text('SELECT count(*) FROM ' + module.TABLES[0])) == 0
            with pg_engine.begin() as writer:
                if revision == 'a704b15a0001':
                    writer.execute(text("INSERT INTO social_generation_controls(id,version,source_allowlist,targets) VALUES(1,1,'[]','[]')"))
                else:
                    writer.execute(text(EVIDENCE))
            assert stale.scalar(text('SELECT count(*) FROM ' + module.TABLES[0])) == 0
            with pytest.raises(RuntimeError, match='READ COMMITTED'):
                with Operations.context(MigrationContext.configure(stale)):
                    module.downgrade()
    with pg_engine.connect() as fresh:
        assert fresh.scalar(text('SELECT count(*) FROM ' + module.TABLES[0])) == 1
        assert all(inspect(fresh).has_table(table) for table in module.TABLES)


def report_boundary(engine):
    """Isolate708's retained column/drop identities; source view SQL is separate."""
    generation(engine)
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE social_source_cursors ADD COLUMN report_state JSONB'))
        conn.execute(text('CREATE VIEW social_report_source_authority AS SELECT 1 AS inert_identity'))
        conn.execute(text('CREATE VIEW social_report_source_authority_snapshot AS SELECT 1 AS inert_identity'))
        conn.execute(text("INSERT INTO social_source_cursors(id,source_type,source_key,detector_version,evidence_version,sequence,fingerprint) VALUES('00000000-0000-4000-8000-000000000036','inert','retention-test',1,1,0,'inert')"))
    return migration('a708b15a0001')


def test_report_downgrade_cannot_erase_history_committed_after_its_census(pg_engine, monkeypatch):
    module = report_boundary(pg_engine)
    outcome = []
    from sqlalchemy.exc import DBAPIError
    with pg_engine.connect() as conn:
        with conn.begin() as transaction:
            execute = conn.execute
            def after_census(statement, *args, **kwargs):
                result = execute(statement, *args, **kwargs)
                if 'WHERE report_state IS NOT NULL LIMIT 1' in str(statement):
                    try:
                        with pg_engine.begin() as writer:
                            writer.execute(text("SET LOCAL lock_timeout='100ms'"))
                            writer.execute(text("UPDATE social_source_cursors SET report_state='{}'::jsonb"))
                        outcome.append('committed')
                    except DBAPIError as error:
                        if error.orig.pgcode != '55P03':
                            raise
                        outcome.append('blocked')
                return result
            monkeypatch.setattr(conn, 'execute', after_census)
            with Operations.context(MigrationContext.configure(conn)):
                module.downgrade()
            assert outcome == ['blocked'], 'Report history committed after census and its column was dropped'
            transaction.rollback()
    # After releasing the guard, the writer can commit; a new downgrade must
    # see that retained baseline and refuse, preserving its column and views.
    with pg_engine.begin() as writer:
        writer.execute(text("UPDATE social_source_cursors SET report_state='{}'::jsonb"))
    with pytest.raises(RuntimeError, match='Retain report release history'):
        apply(pg_engine, module, 'downgrade')


@pytest.mark.parametrize('isolation', ['REPEATABLE READ', 'SERIALIZABLE'])
def test_report_downgrade_refuses_incompatible_snapshot(pg_engine, isolation):
    module = report_boundary(pg_engine)
    with pg_engine.connect().execution_options(isolation_level=isolation) as conn:
        with conn.begin(), pytest.raises(RuntimeError, match='READ COMMITTED'):
            conn.execute(text('SELECT count(*) FROM social_source_cursors'))
            with Operations.context(MigrationContext.configure(conn)):
                module.downgrade()
