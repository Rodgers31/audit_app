"""Real PostgreSQL role installation and denied authority; no provider/network IO."""
import os
import time
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from local_postgres import local_postgres_url
from social.models import SocialControls, SocialPostTarget
from social.worker.role_contract import install_worker_role, verify_worker_role, WorkerRoleError
from test_connections_migration_postgres import upgrade
from test_connections_support import config
from test_domain_postgres import migration
from test_native_meta_adapters import Graph
from test_native_worker_postgres import prepare, step, due
from test_queue_postgres import repository
from current_social_schema import add_current_worker_policy


@pytest.fixture
def role_database():
    dsn = os.environ.get('SOCIAL_ROLE_TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('Set SOCIAL_ROLE_TEST_DATABASE_URL to the disposable local social_domain_test database')
    url = local_postgres_url(dsn, 'social_domain_test')
    schema, role = 'role_test_' + uuid4().hex, 'worker_test_' + uuid4().hex
    admin = create_engine(url, pool_size=1, max_overflow=0)
    owner = create_engine(url, connect_args={'options': '-csearch_path=' + schema})
    worker = create_engine(url.set(username=role, password=None), pool_size=2, max_overflow=0,
                          connect_args={'options': '-csearch_path=' + schema})
    with admin.begin() as conn:
        conn.execute(text('CREATE SCHEMA ' + schema))
        conn.execute(text('CREATE ROLE ' + role + ' LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2'))
    try:
        with owner.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration().upgrade()
        upgrade(owner, current=True)
        add_current_worker_policy(owner)
        with Session(owner) as db:
            db.add(SocialControls(id=1, publishing_enabled=False)); db.commit()
        yield owner, worker, schema, role
    finally:
        worker.dispose(); owner.dispose()
        # Separate commits: a leftover role dependency must not also keep the schema.
        with admin.begin() as conn: conn.execute(text('DROP SCHEMA ' + schema + ' CASCADE'))
        with admin.begin() as conn: conn.execute(text('DROP ROLE ' + role))
        admin.dispose()


def test_install_is_atomic_idempotent_and_verifies_actual_login(role_database):
    owner, worker, schema, role = role_database
    with pytest.raises(WorkerRoleError): verify_worker_role(worker, role, schema)
    install_worker_role(owner, role, schema)
    install_worker_role(owner, role, schema)
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany): statements.append(statement)
    event.listen(worker, 'before_cursor_execute', capture)
    try: verify_worker_role(worker, role, schema)
    finally: event.remove(worker, 'before_cursor_execute', capture)
    assert len(statements) < 30
    with pytest.raises(WorkerRoleError): verify_worker_role(owner, role, schema)
    with worker.begin() as conn:
        assert conn.execute(text('SELECT id FROM social_controls FOR UPDATE')).scalar() == 1
        assert conn.execute(text('SELECT current_user')).scalar() == role
    with owner.begin() as conn:
        assert conn.execute(text('SELECT current_user')).scalar() != role


@pytest.mark.parametrize('platform,image', [('facebook',False),('facebook',True),('instagram',True)])
def test_complete_native_pipeline_and_forbidden_mutations(role_database, config, monkeypatch, platform, image):
    owner, worker, schema, role = role_database
    graph = Graph(); storage, target = prepare(owner, config, graph, monkeypatch, platform=platform, image=image)
    install_worker_role(owner, role, schema); verify_worker_role(worker, role, schema)
    repo = repository(worker); repo.validate_schema(); repo.recover_expired(); repo.next_due_delay(1)
    repo.heartbeat(state='idle', active_claims=0, scanned=True)
    for _ in range(8):
        due(owner, target); step(worker, config, storage, graph)
        with Session(owner) as db: state = db.get(SocialPostTarget, target).state
        if state == 'published': break
    assert state == 'published'
    with worker.begin() as conn:
        assert conn.execute(text('SELECT count(*) FROM social_publish_attempts WHERE completed_at IS NOT NULL')).scalar() > 0
        assert conn.execute(text('UPDATE social_publish_attempts SET outcome=outcome')).rowcount == 0
    repo.heartbeat(state='stopped', active_claims=0)
    denied = [
        'UPDATE social_accounts SET publishing_enabled=false',
        "UPDATE social_post_targets SET payload_hash=repeat('a',64)",
        'UPDATE social_controls SET id=id', 'UPDATE social_publications SET id=id',
        'UPDATE social_credentials SET id=id', 'DELETE FROM social_publish_attempts',
        'DELETE FROM social_audit_events', 'UPDATE social_post_revisions SET content_hash=content_hash',
        'UPDATE social_media_assets SET storage_key=storage_key', 'SELECT * FROM social_oauth_flows',
        'SELECT * FROM social_privacy_ownership', 'TRUNCATE social_post_targets',
        "INSERT INTO social_audit_events(id,actor_kind,action) VALUES(gen_random_uuid(),'admin','forged')",
    ]
    for sql in denied:
        with pytest.raises(Exception) as stopped:
            with worker.begin() as conn: conn.execute(text(sql))
        assert getattr(stopped.value.orig, 'pgcode', None) == '42501', sql


@pytest.mark.parametrize('widen', [
    'ALTER ROLE {role} BYPASSRLS', 'ALTER ROLE {role} INHERIT',
    'ALTER ROLE {role} CONNECTION LIMIT -1', 'GRANT pg_read_all_data TO {role}',
    'GRANT SELECT ON social_oauth_flows TO {role}',
    'GRANT UPDATE(publishing_enabled) ON social_accounts TO {role}',
    'GRANT SELECT ON social_accounts TO {role} WITH GRANT OPTION',
    'GRANT SELECT ON social_oauth_flows TO PUBLIC',
    'CREATE POLICY unexpected_public ON social_controls FOR UPDATE TO PUBLIC USING(true) WITH CHECK(true)',
    'ALTER TABLE social_controls DISABLE ROW LEVEL SECURITY',
])
def test_authority_drift_refuses_readiness(role_database, widen):
    owner, worker, schema, role = role_database
    install_worker_role(owner, role, schema)
    with owner.begin() as conn: conn.execute(text(widen.format(role=role)))
    try:
        with pytest.raises(WorkerRoleError): verify_worker_role(worker, role, schema)
    finally:
        if 'PUBLIC' in widen and widen.startswith('GRANT'):
            with owner.begin() as conn: conn.execute(text('REVOKE SELECT ON social_oauth_flows FROM PUBLIC'))
        if 'pg_read_all_data' in widen:
            with owner.begin() as conn: conn.execute(text('REVOKE pg_read_all_data FROM ' + role))


def test_restrictive_lock_fence_survives_new_public_permissive_policy(role_database):
    owner, worker, schema, role = role_database
    install_worker_role(owner, role, schema)
    with owner.begin() as conn:
        conn.execute(text('CREATE POLICY broad_public ON social_controls FOR UPDATE TO PUBLIC USING(true) WITH CHECK(true)'))
    with pytest.raises(WorkerRoleError): verify_worker_role(worker, role, schema)
    with pytest.raises(Exception) as stopped:
        with worker.begin() as conn: conn.execute(text('UPDATE social_controls SET id=id'))
    assert stopped.value.orig.pgcode == '42501'


def test_install_refuses_prior_authority_without_partial_grants(role_database):
    owner, worker, schema, role = role_database
    with owner.begin() as conn: conn.execute(text('GRANT SELECT ON social_oauth_flows TO ' + role))
    with pytest.raises(WorkerRoleError): install_worker_role(owner, role, schema)
    with owner.connect() as conn:
        assert not conn.execute(text("SELECT has_table_privilege(:role,'social_controls','SELECT')"), {'role':role}).scalar()
        assert conn.execute(text("SELECT count(*) FROM pg_policy WHERE polname LIKE 'scw_%'")).scalar() == 0


def test_missing_controls_refuses_and_rolls_back_installation(role_database):
    owner, worker, schema, role = role_database
    with owner.begin() as conn: conn.execute(text('DELETE FROM social_controls'))
    with pytest.raises(WorkerRoleError): install_worker_role(owner, role, schema)
    with owner.connect() as conn:
        assert not conn.execute(text("SELECT has_schema_privilege(:role,:schema,'USAGE')"), {'role':role, 'schema':schema}).scalar()


@pytest.mark.parametrize('widen', ['GRANT MAINTAIN ON social_accounts TO {role}',
                                   "ALTER ROLE {role} SET session_replication_role='replica'"])
def test_install_refuses_prior_maintain_or_login_default_without_partial_grants(role_database, widen):
    owner, worker, schema, role = role_database
    with owner.begin() as conn: conn.execute(text(widen.format(role=role)))
    with pytest.raises(WorkerRoleError): install_worker_role(owner, role, schema)
    with owner.connect() as conn:
        assert not conn.execute(text("SELECT has_table_privilege(:role,'social_controls','SELECT')"), {'role':role}).scalar()
        assert conn.execute(text("SELECT count(*) FROM pg_policy WHERE polname LIKE 'scw_%'")).scalar() == 0


def _fresh_replica(worker, values):
    worker.dispose()
    with worker.connect() as conn: return conn.execute(text('SHOW session_replication_role')).scalar() == 'replica'


def _startup_option(option):
    # A connection-start setting needs SET authority before any SQL runs.
    def probe(worker, values):
        engine = create_engine(worker.url, connect_args={'options': option})
        try:
            with engine.connect(): return True
        finally: engine.dispose()
    return probe


def _worker_alter_system(worker, values):
    # Written and reset at once without a reload, so the server never applies it.
    with worker.connect() as conn:
        conn = conn.execution_options(isolation_level='AUTOCOMMIT')
        conn.execute(text("ALTER SYSTEM SET work_mem='5MB'")); conn.execute(text('ALTER SYSTEM RESET work_mem'))
    return True


def _reloaded(name, value):
    def wait(conn, values):
        conn.execute(text('SELECT pg_reload_conf()'))
        # This backend sees the file only after the postmaster has reloaded it.
        for _ in range(200):
            if conn.execute(text('SELECT current_setting(:name)'), {'name': name}).scalar() == value: return
            time.sleep(0.025)
        raise AssertionError('server configuration was not reloaded')
    return wait


def _run(owner, statements, values, *, best_effort=False):
    failure = None
    with owner.connect() as conn:
        conn = conn.execution_options(isolation_level='AUTOCOMMIT')
        for statement in statements:
            try:
                if callable(statement): statement(conn, values)
                else: conn.execute(text(statement.format(**values)))
            except Exception as error:
                if not best_effort: raise
                failure = failure or error
    if failure is not None: raise failure


AUDIT_PROBE = (["INSERT INTO social_audit_events(id,actor_kind,action,details,request_id,created_at) "
                "VALUES(gen_random_uuid(),'worker','inert_probe','{{}}','inert',now())"],
               'SELECT updated_by IS NOT NULL FROM social_controls')
LARGE_OBJECT = ["SELECT lo_from_bytea({lo},convert_to('INERT_LARGE_OBJECT','UTF8'))"]
UNLINK = ['SELECT lo_unlink(oid) FROM pg_largeobject_metadata WHERE oid={lo}']
FDW = ['CREATE FOREIGN DATA WRAPPER {u} NO HANDLER']
SERVER = FDW + ['CREATE SERVER {u}_server FOREIGN DATA WRAPPER {u}']
DROP_FDW = ['DROP FOREIGN DATA WRAPPER IF EXISTS {u} CASCADE']
# name: (harmless owner setup that must still qualify, owner widening, owner
# restoration, worker probe that fails after setup and succeeds after widening,
# or None where refusal is deliberately conservative).
AUTHORITY = {
    'maintain_table': ([], ['GRANT MAINTAIN ON social_accounts TO {role}'], [],
                       'LOCK TABLE social_accounts IN ACCESS EXCLUSIVE MODE'),
    # Counts only; no credential-bearing row or value is read.
    'catalog_relation_grant': ([], ['GRANT SELECT ON pg_catalog.pg_authid TO {role}'],
                               ['REVOKE SELECT ON pg_catalog.pg_authid FROM {role}'],
                               'SELECT count(*) FROM pg_catalog.pg_authid'),
    'catalog_relation_public': ([], ['GRANT SELECT ON pg_catalog.pg_authid TO PUBLIC'],
                                ['REVOKE SELECT ON pg_catalog.pg_authid FROM PUBLIC'],
                                'SELECT count(*) FROM pg_catalog.pg_authid'),
    # PUBLIC may read pg_description; MAINTAIN adds LOCK in any mode.
    'catalog_beyond_public_privilege': ([], ['GRANT MAINTAIN ON pg_catalog.pg_description TO {role}'],
                                        ['REVOKE MAINTAIN ON pg_catalog.pg_description FROM {role}'],
                                        'LOCK TABLE pg_catalog.pg_description IN EXCLUSIVE MODE'),
    'information_schema_internal': ([], ['GRANT SELECT ON information_schema._pg_user_mappings TO {role}'],
                                    ['REVOKE SELECT ON information_schema._pg_user_mappings FROM {role}'],
                                    'SELECT count(*) FROM information_schema._pg_user_mappings'),
    'information_schema_write': ([], ['GRANT DELETE ON information_schema.sql_parts TO {role}'],
                                 ['REVOKE DELETE ON information_schema.sql_parts FROM {role}'],
                                 'DELETE FROM information_schema.sql_parts'),
    'catalog_function': ([], ['GRANT EXECUTE ON FUNCTION pg_catalog.pg_ls_dir(text) TO {role}'],
                         ['REVOKE EXECUTE ON FUNCTION pg_catalog.pg_ls_dir(text) FROM {role}'],
                         "SELECT count(*) FROM pg_catalog.pg_ls_dir('.')"),
    'catalog_definer': (["CREATE FUNCTION pg_catalog.{u}() RETURNS name LANGUAGE sql SECURITY DEFINER "
                         "SET search_path=pg_catalog AS 'SELECT current_user'",
                         'REVOKE EXECUTE ON FUNCTION pg_catalog.{u}() FROM PUBLIC'],
                        ['GRANT EXECUTE ON FUNCTION pg_catalog.{u}() TO {role}'],
                        ['DROP FUNCTION IF EXISTS pg_catalog.{u}()'], 'SELECT pg_catalog.{u}()'),
    'hidden_schema_definer': (['CREATE SCHEMA {u}',
                               "CREATE FUNCTION {u}.reader() RETURNS name LANGUAGE sql SECURITY DEFINER "
                               "SET search_path=pg_catalog AS 'SELECT current_user'",
                               'REVOKE EXECUTE ON FUNCTION {u}.reader() FROM PUBLIC',
                               'CREATE FUNCTION {schema}.{u}_wrapper() RETURNS name LANGUAGE sql RETURN {u}.reader()'],
                              ['GRANT EXECUTE ON FUNCTION {u}.reader() TO PUBLIC'],
                              ['DROP SCHEMA IF EXISTS {u} CASCADE'], 'SELECT {schema}.{u}_wrapper()'),
    'owned_guard_function': ([], ['ALTER FUNCTION {schema}.social_deny_history_mutation() OWNER TO {role}'],
                             ['ALTER FUNCTION {schema}.social_deny_history_mutation() OWNER TO CURRENT_USER'],
                             'DROP FUNCTION social_deny_history_mutation() CASCADE'),
    'owned_type': (["CREATE TYPE {schema}.{u} AS ENUM ('inert')"], ['ALTER TYPE {schema}.{u} OWNER TO {role}'],
                   ['DROP TYPE IF EXISTS {schema}.{u}'], "ALTER TYPE {schema}.{u} RENAME VALUE 'inert' TO 'changed'"),
    'large_object': (LARGE_OBJECT, ['GRANT SELECT ON LARGE OBJECT {lo} TO {role}'], UNLINK, 'SELECT lo_get({lo})'),
    'large_object_public': (LARGE_OBJECT, ['GRANT SELECT ON LARGE OBJECT {lo} TO PUBLIC'], UNLINK, 'SELECT lo_get({lo})'),
    'large_object_owner': (LARGE_OBJECT, ['ALTER LARGE OBJECT {lo} OWNER TO {role}'], UNLINK, 'SELECT lo_get({lo})'),
    'large_object_compat_server_wide': (LARGE_OBJECT,
                                        ['ALTER SYSTEM SET lo_compat_privileges=on', _reloaded('lo_compat_privileges', 'on')],
                                        ['ALTER SYSTEM RESET lo_compat_privileges', _reloaded('lo_compat_privileges', 'off')] + UNLINK,
                                        'SELECT lo_get({lo})'),
    'fdw_usage': (FDW, ['GRANT USAGE ON FOREIGN DATA WRAPPER {u} TO {role}'], DROP_FDW,
                  'CREATE SERVER {u}_probe FOREIGN DATA WRAPPER {u}'),
    'server_usage': (SERVER, ['GRANT USAGE ON FOREIGN SERVER {u}_server TO {role}'], DROP_FDW,
                     'CREATE USER MAPPING FOR CURRENT_USER SERVER {u}_server'),
    'user_mapping': (SERVER, ['CREATE USER MAPPING FOR {role} SERVER {u}_server'], DROP_FDW, None),
    'parameter_superuser': ([], ['GRANT SET ON PARAMETER session_replication_role TO {role}'],
                            ['REVOKE SET ON PARAMETER session_replication_role FROM {role}'],
                            'SET LOCAL session_replication_role=replica'),
    'parameter_public': ([], ['GRANT SET ON PARAMETER session_replication_role TO PUBLIC'],
                         ['REVOKE SET ON PARAMETER session_replication_role FROM PUBLIC'],
                         'SET LOCAL session_replication_role=replica'),
    # pg_settings hides this superuser parameter from the worker; an empty list loads nothing.
    'parameter_hidden_from_worker': ([], ['GRANT SET ON PARAMETER session_preload_libraries TO {role}'],
                                     ['REVOKE SET ON PARAMETER session_preload_libraries FROM {role}'],
                                     _startup_option('-csession_preload_libraries=')),
    'parameter_superuser_backend': ([], ['GRANT SET ON PARAMETER log_disconnections TO {role}'],
                                    ['REVOKE SET ON PARAMETER log_disconnections FROM {role}'],
                                    _startup_option('-clog_disconnections=on')),
    'parameter_alter_system': ([], ['GRANT ALTER SYSTEM ON PARAMETER work_mem TO {role}'],
                               ['REVOKE ALTER SYSTEM ON PARAMETER work_mem FROM {role}'], _worker_alter_system),
    'parameter_placeholder': ([], ['GRANT SET ON PARAMETER {u}.flag TO {role}'],
                              ['REVOKE SET ON PARAMETER {u}.flag FROM {role}'], None),
    'role_login_default': ([], ["ALTER ROLE {role} SET session_replication_role='replica'"],
                           ['ALTER ROLE {role} RESET ALL'], _fresh_replica),
    'role_any_login_default': ([], ["ALTER ROLE {role} SET statement_timeout='5s'"], ['ALTER ROLE {role} RESET ALL'], None),
    'database_login_default': ([], ["ALTER DATABASE social_domain_test SET session_replication_role='replica'"],
                               ['ALTER DATABASE social_domain_test RESET session_replication_role'], _fresh_replica),
    # The operator's own override hides it from every session-state check the installer could make.
    'database_default_masked_for_operator': (LARGE_OBJECT,
        ['ALTER ROLE ALL IN DATABASE social_domain_test SET lo_compat_privileges=on',
         'ALTER ROLE CURRENT_USER IN DATABASE social_domain_test SET lo_compat_privileges=off'],
        ['ALTER ROLE ALL IN DATABASE social_domain_test RESET lo_compat_privileges',
         'ALTER ROLE CURRENT_USER IN DATABASE social_domain_test RESET lo_compat_privileges'] + UNLINK,
        'SELECT lo_get({lo})'),
    # Hidden from the worker's pg_settings; the value is the server default, so logins still work.
    'database_default_hidden_parameter': ([], ["ALTER DATABASE social_domain_test SET dynamic_library_path='$libdir'"],
                                          ['ALTER DATABASE social_domain_test RESET dynamic_library_path'], None),
    # Extension settings change installed code, e.g. how the plpgsql guards resolve names.
    'database_default_extension_parameter': ([], ["ALTER DATABASE social_domain_test SET plpgsql.variable_conflict='use_column'"],
                                             ['ALTER DATABASE social_domain_test RESET plpgsql.variable_conflict'], None),
    'disabled_trigger': ([], ['ALTER TABLE social_audit_events DISABLE TRIGGER social_audit_immutable'], [], None),
    'replica_only_trigger': ([], ['ALTER TABLE social_audit_events ENABLE REPLICA TRIGGER social_audit_immutable'], [], None),
    'column_filtered_trigger': ([], ['DROP TRIGGER social_target_payload_immutable ON social_post_targets',
                                     'CREATE TRIGGER social_target_payload_immutable BEFORE UPDATE OF created_at '
                                     'ON social_post_targets FOR EACH ROW EXECUTE FUNCTION social_guard_target_payload()'],
                                [], None),
    # Trigger functions need no EXECUTE by the firing role; rules run as the table owner.
    'definer_trigger': ([], ["CREATE FUNCTION {u}() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog "
                             "AS 'BEGIN UPDATE {schema}.social_controls SET updated_by=NEW.id; RETURN NEW; END'",
                             'REVOKE ALL ON FUNCTION {u}() FROM PUBLIC',
                             'CREATE TRIGGER {u} BEFORE INSERT ON social_audit_events FOR EACH ROW EXECUTE FUNCTION {u}()'],
                        [], AUDIT_PROBE),
    'rewrite_rule': ([], ['CREATE RULE {u} AS ON INSERT TO social_audit_events DO ALSO UPDATE social_controls SET updated_by=NEW.id'],
                     [], AUDIT_PROBE),
}


def _achieved(worker, probe, values):
    if callable(probe):
        try: return probe(worker, values) is True
        except Exception: return False
    statements, check = ([probe], None) if isinstance(probe, str) else probe
    with worker.connect() as conn:
        transaction = conn.begin()
        try:
            for statement in statements: conn.execute(text(statement.format(**values)))
            return True if check is None else conn.execute(text(check)).scalar() is True
        except Exception: return False
        finally: transaction.rollback()


@pytest.mark.parametrize('case', sorted(AUTHORITY))
def test_authority_outside_table_grants_refuses_install_verify_and_native_cli(role_database, monkeypatch, case):
    import social.worker.__main__ as cli
    owner, worker, schema, role = role_database
    setup, widen, restore, probe = AUTHORITY[case]
    values = {'role': role, 'schema': schema, 'u': 'inert_' + uuid4().hex[:16],
              'lo': 3000000000 + int(uuid4().hex[:6], 16)}
    install_worker_role(owner, role, schema); verify_worker_role(worker, role, schema)
    try:
        _run(owner, setup, values); owner.dispose(); worker.dispose()
        # The setup alone is harmless: the login still qualifies and lacks the authority.
        verify_worker_role(worker, role, schema)
        if probe is not None: assert not _achieved(worker, probe, values)
        _run(owner, widen, values); owner.dispose(); worker.dispose()
        if probe is not None: assert _achieved(worker, probe, values), 'widening must grant real authority'
        with pytest.raises(WorkerRoleError): verify_worker_role(worker, role, schema)
        with pytest.raises(WorkerRoleError): install_worker_role(owner, role, schema)
        def forbidden(*args, **kwargs): pytest.fail('Queue/provider constructed for an unqualified login')
        monkeypatch.setattr(cli, 'QueueRepository', forbidden)
        monkeypatch.setattr(cli, 'native_runtime', forbidden)
        assert cli.main(['--database-url', worker.url.render_as_string(hide_password=False), '--worker-role', role,
                         '--database-schema', schema, '--native-meta', '--once']) == 1
    finally:
        _run(owner, restore, values, best_effort=True)


@pytest.mark.parametrize('setting,reset', [
    ("ALTER DATABASE social_domain_test SET statement_timeout='60s'", 'ALTER DATABASE social_domain_test RESET statement_timeout'),
    ("ALTER DATABASE social_domain_test SET app.settings_inert='x'", 'ALTER DATABASE social_domain_test RESET app.settings_inert'),
    # Applies only to another database.
    ("ALTER ROLE {role} IN DATABASE postgres SET statement_timeout='5s'", 'ALTER ROLE {role} IN DATABASE postgres RESET ALL'),
])
def test_benign_login_defaults_still_qualify(role_database, setting, reset):
    owner, worker, schema, role = role_database
    install_worker_role(owner, role, schema)
    values = {'role': role}
    try:
        _run(owner, [setting], values); owner.dispose(); worker.dispose()
        verify_worker_role(worker, role, schema); install_worker_role(owner, role, schema)
    finally:
        _run(owner, [reset], values, best_effort=True)


def test_extension_default_is_refused_even_where_its_library_is_loaded(role_database):
    owner, worker, schema, role = role_database
    install_worker_role(owner, role, schema)
    # plpgsql.check_asserts is a user-context setting, visible only once plpgsql loads.
    operator = create_engine(owner.url, pool_size=1, max_overflow=0, connect_args={'options': '-csearch_path=' + schema})
    try:
        _run(owner, ["ALTER DATABASE social_domain_test SET plpgsql.check_asserts=off"], {}); worker.dispose()
        for engine, sessions in ((worker, 2), (operator, 1)):
            connections = [engine.connect() for _ in range(sessions)]
            for conn in connections: conn.execute(text('DO $$BEGIN END$$')); conn.close()
            with engine.connect() as conn:
                assert conn.execute(text("SELECT context FROM pg_settings WHERE name='plpgsql.check_asserts'")).scalar() == 'user'
        with pytest.raises(WorkerRoleError): verify_worker_role(worker, role, schema)
        with pytest.raises(WorkerRoleError): install_worker_role(operator, role, schema)
    finally:
        operator.dispose()
        _run(owner, ['ALTER DATABASE social_domain_test RESET plpgsql.check_asserts'], {}, best_effort=True)


def test_temporary_table_cannot_hide_catalog_rows_from_the_checks(role_database):
    owner, worker, schema, role = role_database
    install_worker_role(owner, role, schema)
    # Unless the path lists pg_temp, PostgreSQL searches it before pg_catalog.
    single = create_engine(worker.url, pool_size=1, max_overflow=0, connect_args={'options': '-csearch_path=' + schema})
    try:
        _run(owner, ["ALTER ROLE {role} SET statement_timeout='5s'"], {'role': role})
        with single.begin() as conn:
            conn.execute(text('CREATE TEMP TABLE pg_db_role_setting AS SELECT * FROM pg_catalog.pg_db_role_setting WHERE false'))
            assert conn.execute(text('SELECT count(*) FROM pg_db_role_setting')).scalar() == 0
        with pytest.raises(WorkerRoleError): verify_worker_role(single, role, schema)
    finally:
        single.dispose()
        _run(owner, ['ALTER ROLE {role} RESET ALL'], {'role': role}, best_effort=True)


def test_unpinned_engine_keeps_the_login_search_path(role_database):
    from social.worker.config import WorkerConfig, create_worker_engine
    owner, worker, schema, role = role_database
    # Media maintenance and plain scans pass no schema and keep base behaviour.
    plain = create_worker_engine(WorkerConfig(owner.url.render_as_string(hide_password=False)))
    try:
        with plain.connect() as conn: assert conn.execute(text('SHOW search_path')).scalar() == '"$user", public'
    finally: plain.dispose()


@pytest.mark.parametrize('role,schema', [(None,'public'), ('','public'), ('postgres','public'),
    ('worker; DROP TABLE x','public'), ('worker','public;set role postgres'), ('worker',None)])
def test_direct_guards_fail_with_fixed_private_diagnostic(role, schema):
    for function in (verify_worker_role, install_worker_role):
        with pytest.raises(WorkerRoleError, match='^WORKER_ROLE_UNAVAILABLE$') as stopped:
            function(None, role, schema)
        assert stopped.value.__context__ is None


def test_operator_entrypoint_executes_install_and_actual_login_verification(role_database, monkeypatch, capsys):
    from social.worker.role_admin import main
    from social.worker.config import WorkerConfig, create_worker_engine
    owner, worker, schema, role = role_database
    monkeypatch.setenv('INERT_ROLE_OWNER_DSN', owner.url.render_as_string(hide_password=False))
    monkeypatch.setenv('INERT_ROLE_WORKER_DSN', worker.url.render_as_string(hide_password=False))
    assert main(['--database-url-env','INERT_ROLE_OWNER_DSN','--role',role,'--schema',schema,'--install']) == 0
    assert main(['--database-url-env','INERT_ROLE_WORKER_DSN','--role',role,'--schema',schema,'--verify']) == 0
    assert '"status":"ok"' in capsys.readouterr().out
    worker.dispose()
    runtime = create_worker_engine(WorkerConfig(worker.url.render_as_string(hide_password=False), database_schema=schema))
    try:
        # Both connections and a replacement must retain the explicit path.
        with runtime.connect() as first, runtime.connect() as second:
            for conn in (first, second):
                assert conn.execute(text('SHOW search_path')).scalar().replace(' ', '') == 'pg_catalog,' + schema + ',pg_temp'
        runtime.dispose()
        verify_worker_role(runtime, role, schema)
    finally: runtime.dispose()


OWNED_TEMPORARY = """
    SELECT d.classid::regclass::text,n.nspname FROM pg_shdepend d
    LEFT JOIN pg_class c ON d.classid='pg_class'::regclass AND c.oid=d.objid
    LEFT JOIN pg_type t ON d.classid='pg_type'::regclass AND t.oid=d.objid
    LEFT JOIN pg_proc p ON d.classid='pg_proc'::regclass AND p.oid=d.objid
    JOIN pg_namespace n ON n.oid=coalesce(c.relnamespace,t.typnamespace,p.pronamespace)
    WHERE d.refobjid=CAST(:role AS regrole) AND d.deptype='o'
      AND d.dbid=(SELECT oid FROM pg_database WHERE datname=current_database())
"""


def test_own_temporary_objects_in_both_pooled_sessions_still_qualify(role_database):
    owner, worker, schema, role = role_database
    install_worker_role(owner, role, schema)
    sessions = [worker.connect() for _ in range(2)]
    try:
        for conn in sessions:
            with conn.begin():
                # A text column also gives the temporary table a temporary TOAST relation.
                conn.execute(text('CREATE TEMP TABLE inert_scratch(id int, note text)'))
                conn.execute(text('CREATE TYPE pg_temp.inert_scratch_row AS (id int)'))
                conn.execute(text("CREATE FUNCTION pg_temp.inert_scratch_fn() RETURNS int LANGUAGE sql AS 'SELECT 1'"))
        backends = {conn.execute(text('SELECT pg_backend_pid()')).scalar() for conn in sessions}
        assert len(backends) == 2
    finally:
        for conn in sessions: conn.close()
    with owner.connect() as conn:
        owned = conn.execute(text(OWNED_TEMPORARY), {'role': role}).all()
    # Each session: the table, a composite type and the function. A table's row type depends on the table.
    assert sorted(classid for classid, _ in owned) == ['pg_class'] * 2 + ['pg_proc'] * 2 + ['pg_type'] * 2
    assert len({namespace for _, namespace in owned}) == 2
    assert all(namespace.startswith('pg_temp_') for _, namespace in owned)
    for _ in range(2):
        verify_worker_role(worker, role, schema)
    install_worker_role(owner, role, schema)
    verify_worker_role(worker, role, schema)


def test_ownership_held_in_another_database_refuses(role_database):
    owner, worker, schema, role = role_database
    install_worker_role(owner, role, schema)
    # The other assigned disposable database on the same loopback server.
    other = create_engine(owner.url.set(database='social_worker_test'), pool_size=1, max_overflow=0)
    table = 'public.inert_owned_' + uuid4().hex[:16]
    try:
        with other.begin() as conn:
            conn.execute(text('CREATE TABLE ' + table + '(id int)'))
            conn.execute(text('ALTER TABLE ' + table + ' OWNER TO ' + role))
        # Nothing in the verified database changed.
        with owner.connect() as conn:
            assert conn.execute(text(OWNED_TEMPORARY), {'role': role}).all() == []
        with pytest.raises(WorkerRoleError): verify_worker_role(worker, role, schema)
        with pytest.raises(WorkerRoleError): install_worker_role(owner, role, schema)
    finally:
        with other.begin() as conn: conn.execute(text('DROP TABLE IF EXISTS ' + table))
        other.dispose()
    verify_worker_role(worker, role, schema)


def test_loaded_module_default_with_non_user_context_is_refused(role_database):
    owner, worker, schema, role = role_database
    install_worker_role(owner, role, schema)
    # auto_explain is a module, not an extension: no prefix refusal applies. Its
    # parameters are superuser context; until loaded they are inert placeholders.
    operator = create_engine(owner.url, pool_size=1, max_overflow=0, connect_args={'options': '-csearch_path=' + schema})
    try:
        _run(owner, ["ALTER DATABASE social_domain_test SET auto_explain.log_analyze=off"], {}); worker.dispose()
        with operator.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM pg_extension WHERE extname='auto_explain'")).scalar() == 0
            assert conn.execute(text("SELECT count(*) FROM pg_settings WHERE name='auto_explain.log_analyze'")).scalar() == 0
        install_worker_role(operator, role, schema)
        operator.dispose()
        with operator.connect() as conn:
            conn.execute(text("LOAD 'auto_explain'")); conn.commit()
            assert conn.execute(text("SELECT context FROM pg_settings WHERE name='auto_explain.log_analyze'")).scalar() == 'superuser'
        with pytest.raises(WorkerRoleError): install_worker_role(operator, role, schema)
    finally:
        operator.dispose()
        _run(owner, ['ALTER DATABASE social_domain_test RESET auto_explain.log_analyze'], {}, best_effort=True)


def test_mixed_case_user_setting_default_is_judged_case_insensitively(role_database):
    owner, worker, schema, role = role_database
    install_worker_role(owner, role, schema)
    try:
        _run(owner, ["ALTER DATABASE social_domain_test SET \"TimeZone\"='UTC'"], {}); owner.dispose(); worker.dispose()
        with owner.connect() as conn:
            stored = conn.execute(text("""
                SELECT c FROM pg_db_role_setting d CROSS JOIN LATERAL unnest(d.setconfig) c
                WHERE d.setrole=0 AND d.setdatabase=(SELECT oid FROM pg_database WHERE datname=current_database())""")).scalars().all()
            assert 'TimeZone=UTC' in stored
            assert conn.execute(text("SELECT context FROM pg_settings WHERE name='TimeZone'")).scalar() == 'user'
        verify_worker_role(worker, role, schema); install_worker_role(owner, role, schema)
    finally:
        _run(owner, ['ALTER DATABASE social_domain_test RESET "TimeZone"'], {}, best_effort=True)
