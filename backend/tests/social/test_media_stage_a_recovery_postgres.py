"""Actual PG row closure/restore; explicitly inert inspector, no codec acceptance."""
from contextlib import contextmanager
import hashlib
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from social.media.config import MediaConfig
from social.media.inspection import InspectedMedia, LocalInspector
from social.media.recovery import MODELS, capture_stage_a_rows, encode_rows, restore_stage_a_rows, RecoveryScopeError
from social.models import SocialAccount
from social.media.recovery_packet import publish_stage_a_packet, read_stage_a_packet
from social.media.runtime import MediaRuntime
from social.media.service import MediaService
from current_social_schema import upgrade_current_social_runtime
from test_domain_postgres import owned_domain_engine
from test_media_stage_a_recovery import intake
from test_media_support import ACTOR, ENDPOINT, FakeStorage
from test_media_recovery_packet import CONTEXT


@contextmanager
def target():
    with owned_domain_engine() as engine:
        upgrade_current_social_runtime(engine)
        yield engine


@pytest.fixture
def packet_source(monkeypatch):
    # Isolate data/transaction contracts from the emulated child-decoder limit.
    def inspect(self, path, mime, size):
        return InspectedMedia(mime, size, hashlib.sha256(path.read_bytes()).hexdigest(),
            1080, 1080, None, None, {})
    monkeypatch.setattr(LocalInspector, 'inspect', inspect)
    with target() as engine, Session(engine, expire_on_commit=False) as db:
        config = MediaConfig(enabled=True, endpoint=ENDPOINT, bucket='media-test', access_key='fixture', secret_key='fixture')
        svc = MediaService(db, MediaRuntime(config, FakeStorage(), LocalInspector(config)))
        io, _, asset, post = intake((svc, None), monkeypatch)
        try: yield svc, asset, post
        finally: io.sdk.close()


def capture(svc, asset, post, *, row_security='off'):
    with svc.db.begin():
        svc.db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        svc.db.execute(text('SET LOCAL row_security = ' + row_security))
        return encode_rows(capture_stage_a_rows(svc.db, ACTOR, asset, post))


def test_real_pg_capture_refuses_rls_filtered_snapshot(packet_source):
    svc, asset, post = packet_source
    with pytest.raises(RecoveryScopeError): capture(svc, asset, post, row_security='on')


def test_actual_cross_schema_incoming_history_refuses_capture(packet_source):
    svc, asset, post = packet_source
    outside = 'capsule_dependency_' + uuid4().hex
    try:
        with svc.db.begin():
            schema = svc.db.scalar(text('SELECT current_schema()'))
            svc.db.execute(text('CREATE SCHEMA ' + outside))
            svc.db.execute(text(f'CREATE TABLE {outside}.history(post_id uuid REFERENCES {schema}.social_posts(id))'))
            svc.db.execute(text(f'INSERT INTO {outside}.history VALUES (:post)'), {'post': post})
        with pytest.raises(RecoveryScopeError): capture(svc, asset, post)
    finally:
        with svc.db.begin(): svc.db.execute(text('DROP SCHEMA ' + outside + ' CASCADE'))


def test_nonempty_migrated_pg_capsule_restores_exact_rows(packet_source):
    svc, asset, post = packet_source
    raw = capture(svc, asset, post)
    with target() as engine:
        with engine.begin() as connection:
            connection.execute(text('SET LOCAL row_security=off'))
            restore_stage_a_rows(connection, raw)
        with Session(engine) as db:
            restored = MediaService(db, svc.runtime)
            assert capture(restored, asset, post) == raw
        # Restore cannot overwrite an existing target, even with identical input.
        with engine.begin() as connection, pytest.raises(RecoveryScopeError):
            connection.execute(text('SET LOCAL row_security=off'))
            restore_stage_a_rows(connection, raw)


def test_pg_packet_binds_the_actual_read_only_snapshot(packet_source, tmp_path):
    svc, asset, post = packet_source
    root = tmp_path / 'approved-existing'; root.mkdir(mode=0o700)
    custody = uuid4()
    with svc.db.begin():
        svc.db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        svc.db.execute(text('SET LOCAL row_security=off'))
        digest = publish_stage_a_packet(svc.db, svc.runtime.storage, ACTOR, asset, post, root, custody, CONTEXT)
    _, _, manifest = read_stage_a_packet(root, custody, digest)
    snapshot = manifest['source_snapshot']
    assert snapshot['dialect'] == 'postgresql' and snapshot['read_only'] is True
    assert snapshot['isolation'] == 'repeatable read' and snapshot['row_security'] == 'off'
    assert snapshot['snapshot'] and snapshot['transaction_started_at'] and snapshot['observed_at']


@pytest.mark.parametrize('existing', ['account', 'unknown_history', 'unknown_empty'])
def test_pg_restore_refuses_unrelated_target_state_without_losing_it(packet_source, existing):
    svc, asset, post = packet_source
    raw = capture(svc, asset, post)
    with target() as engine:
        with engine.begin() as connection:
            if existing == 'account':
                connection.execute(SocialAccount.__table__.insert().values(
                    id=uuid4(), platform='facebook', api_product='facebook_pages',
                    connection_method='manual', external_account_id='913',
                    display_name='Inert existing account', publishing_enabled=False))
            else:
                connection.exec_driver_sql('CREATE TABLE unrelated_history(value TEXT)')
                if existing == 'unknown_history':
                    connection.exec_driver_sql("INSERT INTO unrelated_history VALUES ('preserve')")
        with engine.begin() as connection:
            connection.execute(text('SET LOCAL row_security=off'))
            with pytest.raises(RecoveryScopeError):
                restore_stage_a_rows(connection, raw)
            # Catch then deliberately commit: even unadmitted/unknown history
            # stays intact and not one capsule insert can escape the savepoint.
            for model in MODELS:
                assert connection.exec_driver_sql('SELECT count(*) FROM ' + model.__tablename__).scalar_one() == 0
            if existing == 'account':
                assert connection.exec_driver_sql('SELECT count(*) FROM social_accounts').scalar_one() == 1
            else:
                assert connection.exec_driver_sql('SELECT count(*) FROM unrelated_history').scalar_one() == (1 if existing == 'unknown_history' else 0)


def test_pg_restore_accepts_only_current_metadata_in_empty_owned_target(packet_source):
    svc, asset, post = packet_source
    raw = capture(svc, asset, post)
    with target() as engine:
        with engine.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE alembic_version(version_num VARCHAR(32) PRIMARY KEY)')
            connection.exec_driver_sql("INSERT INTO alembic_version VALUES ('a756b20a0001')")
            connection.execute(text('SET LOCAL row_security=off'))
            restore_stage_a_rows(connection, raw)
            assert connection.exec_driver_sql('SELECT count(*) FROM social_media_assets').scalar_one() == 1
            assert connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one() == 'a756b20a0001'


@pytest.mark.parametrize('visibility', ['not_owned', 'owner_forced_rls'])
def test_pg_restore_refuses_unproven_owner_or_rls_visibility(packet_source, visibility):
    svc, asset, post = packet_source
    raw = capture(svc, asset, post)
    role = 'recovery_refusal_' + uuid4().hex
    with svc.db.begin():
        svc.db.execute(text('CREATE ROLE ' + role + ' NOLOGIN NOSUPERUSER NOBYPASSRLS'))
    try:
        with target() as engine:
            with engine.begin() as connection:
                schema = connection.scalar(text('SELECT current_schema()'))
                if visibility == 'owner_forced_rls':
                    # The non-bypass owner has complete catalog visibility, but
                    # FORCE RLS makes even its empty-count observation unsafe.
                    from sqlalchemy import inspect
                    connection.exec_driver_sql('ALTER SCHEMA ' + schema + ' OWNER TO ' + role)
                    for name in inspect(connection).get_table_names(schema=schema):
                        connection.exec_driver_sql('ALTER TABLE ' + schema + '.' + name + ' OWNER TO ' + role)
                    connection.exec_driver_sql('ALTER TABLE social_accounts FORCE ROW LEVEL SECURITY')
                connection.exec_driver_sql('SET LOCAL ROLE ' + role)
                connection.execute(text('SET LOCAL row_security=off'))
                with pytest.raises(RecoveryScopeError):
                    restore_stage_a_rows(connection, raw)
                connection.exec_driver_sql('RESET ROLE')
                for model in MODELS:
                    assert connection.exec_driver_sql('SELECT count(*) FROM ' + model.__tablename__).scalar_one() == 0
    finally:
        with svc.db.begin():
            svc.db.execute(text('DROP ROLE ' + role))


@pytest.mark.parametrize('existing', ['temporary_history', 'temporary_view',
    'temporary_sequence', 'external_inherited_child', 'unknown_view', 'unknown_sequence',
    'called_expected_sequence'])
def test_pg_restore_refuses_uninventoried_relations_and_preserves_history(packet_source, existing):
    svc, asset, post = packet_source
    raw = capture(svc, asset, post)
    outside = 'recovery_relation_' + uuid4().hex
    with target() as engine:
        try:
            with engine.begin() as connection:
                if existing == 'temporary_history':
                    connection.exec_driver_sql('CREATE TEMP TABLE private_history(value TEXT) ON COMMIT PRESERVE ROWS')
                    connection.exec_driver_sql("INSERT INTO private_history VALUES ('preserve')")
                elif existing == 'temporary_view':
                    connection.exec_driver_sql('CREATE TEMP VIEW private_view AS SELECT 1 AS value')
                elif existing == 'temporary_sequence':
                    connection.exec_driver_sql('CREATE TEMP SEQUENCE private_sequence')
                elif existing == 'external_inherited_child':
                    schema = connection.scalar(text('SELECT current_schema()'))
                    connection.exec_driver_sql('CREATE SCHEMA ' + outside)
                    connection.exec_driver_sql('CREATE TABLE ' + outside + '.history () INHERITS (' + schema + '.social_accounts)')
                elif existing == 'unknown_view':
                    connection.exec_driver_sql('CREATE VIEW private_view AS SELECT 1 AS value')
                elif existing == 'called_expected_sequence':
                    connection.exec_driver_sql("SELECT nextval('social_generation_controls_id_seq')")
                else:
                    connection.exec_driver_sql('CREATE SEQUENCE private_sequence')
            with engine.begin() as connection:
                connection.execute(text('SET LOCAL row_security=off'))
                with pytest.raises(RecoveryScopeError):
                    restore_stage_a_rows(connection, raw)
                assert connection.exec_driver_sql('SELECT count(*) FROM social_media_assets').scalar_one() == 0
                if existing == 'temporary_history':
                    assert connection.exec_driver_sql('SELECT value FROM pg_temp.private_history').scalar_one() == 'preserve'
                elif existing == 'called_expected_sequence':
                    assert connection.exec_driver_sql('SELECT last_value,is_called FROM social_generation_controls_id_seq').one() == (1, True)
            with engine.connect() as connection:
                assert connection.exec_driver_sql('SELECT count(*) FROM social_media_assets').scalar_one() == 0
        finally:
            if existing == 'external_inherited_child':
                with engine.begin() as connection:
                    connection.exec_driver_sql('DROP SCHEMA IF EXISTS ' + outside + ' CASCADE')


def test_pg_restore_rechecks_inheritance_after_acquiring_target_locks(packet_source):
    from sqlalchemy import event
    svc, asset, post = packet_source
    raw = capture(svc, asset, post)
    outside = 'recovery_late_' + uuid4().hex
    with target() as engine:
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql('CREATE SCHEMA ' + outside)
                connection.exec_driver_sql('CREATE TABLE ' + outside + '.sentinel(value TEXT)')
                connection.exec_driver_sql("INSERT INTO " + outside + ".sentinel VALUES ('preserve')")
            with engine.begin() as connection:
                schema = connection.scalar(text('SELECT current_schema()'))
                changed = False
                def interleave(conn, cursor, statement, parameters, context, executemany):
                    nonlocal changed
                    if statement.startswith('LOCK TABLE ONLY') and not changed:
                        changed = True
                        conn.exec_driver_sql('CREATE TABLE ' + outside + '.history () INHERITS (' + schema + '.social_accounts)')
                event.listen(connection, 'before_cursor_execute', interleave)
                connection.execute(text('SET LOCAL row_security=off'))
                with pytest.raises(RecoveryScopeError):
                    restore_stage_a_rows(connection, raw)
                event.remove(connection, 'before_cursor_execute', interleave)
                assert changed
                assert connection.exec_driver_sql('SELECT count(*) FROM social_media_assets').scalar_one() == 0
                assert connection.exec_driver_sql('SELECT value FROM ' + outside + '.sentinel').scalar_one() == 'preserve'
        finally:
            with engine.begin() as connection:
                connection.exec_driver_sql('DROP SCHEMA IF EXISTS ' + outside + ' CASCADE')
