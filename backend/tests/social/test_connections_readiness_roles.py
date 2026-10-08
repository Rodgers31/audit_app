"""Current-main migration/role evidence on a process owned by this test module.

This never reads an environment DSN or connects to a shared fixture. Local roles
are synthetic: their results do not establish the deployed API/worker identity,
browser memberships, Supabase grants, or the privacy session's future policies.
"""
import importlib.util
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError


MIGRATIONS = (
    "f38c61a9d203_social_manual_domain_queue.py",
    "c96d13e2f411_social_meta_credentials.py",
    "a42b86e1d310_social_private_media_intake.py",
    "b73e19a4f602_social_media_write_settlement.py",
)
SCHEMA = "readiness_local"
ROLE_NAMES = ("readiness_owner", "anon", "authenticated", "readiness_backend", "readiness_browser_parent")


def migration(filename):
    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location("readiness_" + filename[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def readiness_postgres():
    """Own cached-image container, loopback port, tmpfs and unconditional stop."""
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("Disposable local role execution requires Docker and cached postgres:17")
    environment = {"PATH": os.defpath, "LC_ALL": "C", "TZ": "UTC"}
    image = subprocess.run([docker, "image", "inspect", "postgres:17", "--format", "{{.Id}}"],
                           env=environment, capture_output=True, timeout=15)
    if image.returncode:
        pytest.skip("Disposable local role execution requires a cached postgres:17; no image is downloaded")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    assert port != 62124, "Refusing coordinator PostgreSQL port"
    run_id = uuid4().hex
    container = "meta-readiness-roles-" + run_id
    engine = None
    try:
        # --pull=never reuses an installed dependency only. A race for the port
        # fails startup, never adopts another server. No persistent volume.
        subprocess.run([docker, "run", "--pull=never", "--name", container,
                        "--label", "auditgava.meta-readiness.run=" + run_id,
                        "-p", "127.0.0.1:" + str(port) + ":5432",
                        "--tmpfs", "/var/lib/postgresql/data:rw,mode=700",
                        "-e", "POSTGRES_USER=readiness_admin", "-e", "POSTGRES_DB=postgres",
                        "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "-d", image.stdout.decode().strip()],
                       env=environment, check=True, capture_output=True, timeout=25)
        deadline = time.monotonic() + 15
        while True:
            ready = subprocess.run([docker, "exec", container, "pg_isready", "-h", "127.0.0.1", "-U", "readiness_admin", "-d", "postgres"],
                                   env=environment, capture_output=True, timeout=5)
            if ready.returncode == 0:
                break
            assert time.monotonic() < deadline, "Owned PostgreSQL container did not become ready"
            time.sleep(0.1)
        binding = subprocess.run([docker, "container", "inspect", container, "--format",
                                  '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostIp}} {{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}'],
                                 env=environment, check=True, capture_output=True, timeout=10)
        assert binding.stdout.decode().strip() == "127.0.0.1 " + str(port)
        engine = create_engine(URL.create("postgresql+psycopg2", username="readiness_admin", host="127.0.0.1",
                                          port=port, database="postgres"), pool_size=1, max_overflow=0)
        with engine.begin() as connection:
            assert connection.execute(text("SHOW data_directory")).scalar() == "/var/lib/postgresql/data"
            assert connection.execute(text("SELECT current_user")).scalar() == "readiness_admin"
            for role in ROLE_NAMES:
                connection.execute(text("CREATE ROLE " + role + " NOLOGIN NOSUPERUSER NOBYPASSRLS"))
            connection.execute(text("CREATE SCHEMA " + SCHEMA + " AUTHORIZATION readiness_owner"))
            connection.execute(text("GRANT USAGE ON SCHEMA " + SCHEMA + " TO anon, authenticated, readiness_backend, readiness_browser_parent"))
            connection.execute(text("SET LOCAL ROLE readiness_owner"))
            connection.execute(text("SET LOCAL search_path TO " + SCHEMA))
            # Positive precondition: emulate provider schema defaults that grant
            # browser access, so the real migration REVOKE must remove it.
            connection.execute(text("ALTER DEFAULT PRIVILEGES IN SCHEMA " + SCHEMA + " GRANT ALL ON TABLES TO anon, authenticated"))
            connection.execute(text("CREATE TABLE readiness_grant_control (value INTEGER)"))
            connection.execute(text("INSERT INTO readiness_grant_control VALUES (9)"))
            for role in ("anon", "authenticated"):
                connection.execute(text("SET LOCAL ROLE " + role))
                assert connection.execute(text("SELECT value FROM readiness_grant_control")).scalar() == 9
            connection.execute(text("SET LOCAL ROLE readiness_owner"))
            connection.execute(text("DROP TABLE readiness_grant_control"))
            with Operations.context(MigrationContext.configure(connection)):
                for filename in MIGRATIONS:
                    migration(filename).upgrade()
            connection.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA " + SCHEMA + " TO readiness_backend"))
            connection.execute(text("INSERT INTO social_credentials (id,provider,credential_kind,encrypted_bundle,key_version) "
                                    "VALUES ('00000000-0000-0000-0000-000000000001','meta','facebook_user',:bundle,'fixture-v1')"),
                               {"bundle": b"inert-envelope-fixture"})
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        # Only this UUID-named container is removed, including failed setup.
        owned = subprocess.run([docker, "container", "inspect", container, "--format", '{{index .Config.Labels "auditgava.meta-readiness.run"}}'],
                               env=environment, capture_output=True, timeout=10)
        if owned.returncode == 0:
            assert owned.stdout.decode().strip() == run_id, "Refusing to remove a container not owned by this fixture"
            subprocess.run([docker, "rm", "--force", "--volumes", container],
                           env=environment, check=True, capture_output=True, timeout=25)


def table_names(engine):
    with engine.connect() as connection:
        return inspect(connection).get_table_names(schema=SCHEMA)


def test_current_migrations_enable_rls_and_revoke_seeded_browser_defaults(readiness_postgres, record_property):
    with readiness_postgres.begin() as connection:
        record_property("postgres_server_version", connection.execute(text("SHOW server_version")).scalar())
        record_property("owned_loopback_port", readiness_postgres.url.port)
        record_property("container_server_port", connection.execute(text("SELECT inet_server_port()")).scalar())
        local_roles = connection.execute(text("SELECT rolname,rolsuper,rolbypassrls,rolcanlogin FROM pg_roles "
                                              "WHERE rolname IN ('readiness_owner','anon','authenticated','readiness_backend','readiness_browser_parent')")).all()
        assert len(local_roles) == 5 and all(not superuser and not bypass and not login for _, superuser, bypass, login in local_roles)
        rows = connection.execute(text("SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,r.rolname "
                                       "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                                       "JOIN pg_roles r ON r.oid=c.relowner "
                                       "WHERE n.nspname=:schema AND c.relkind='r' ORDER BY c.relname"), {"schema": SCHEMA}).all()
        assert len(rows) == 16
        assert all(rls and not forced and owner == "readiness_owner" for _, rls, forced, owner in rows)
        assert connection.execute(text("SELECT count(*) FROM pg_policies WHERE schemaname=:schema"), {"schema": SCHEMA}).scalar() == 0
        defaults = connection.execute(text("SELECT count(*) FROM pg_default_acl d,LATERAL aclexplode(d.defaclacl) a "
                                           "WHERE d.defaclnamespace=CAST(:schema AS regnamespace) "
                                           "AND a.grantee IN ('anon'::regrole,'authenticated'::regrole)"), {"schema": SCHEMA}).scalar()
        assert defaults > 0, "Browser-grant positive precondition was not installed"
        for table, _, _, _ in rows:
            for role in ("anon", "authenticated"):
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
                    assert connection.execute(text("SELECT has_table_privilege(:role,:table,:privilege)"),
                                              {"role": role, "table": SCHEMA + "." + table, "privilege": privilege}).scalar() is False
        for table in ("social_credentials", "social_oauth_flows", "social_media_uploads", "social_media_budgets"):
            assert connection.execute(text("SELECT count(*) FROM pg_class c,LATERAL "
                                           "aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a "
                                           "WHERE c.oid=CAST(:table AS regclass) AND a.grantee=0"),
                                      {"table": SCHEMA + "." + table}).scalar() == 0


@pytest.mark.parametrize("role", ["anon", "authenticated"])
@pytest.mark.parametrize("command", ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"])
def test_actual_browser_role_commands_are_denied_on_every_current_social_table(readiness_postgres, role, command):
    for table in table_names(readiness_postgres):
        with readiness_postgres.connect() as connection:
            column = inspect(connection).get_columns(table, schema=SCHEMA)[0]["name"]
            statements = {
                "SELECT": "SELECT * FROM " + SCHEMA + "." + table,
                "INSERT": "INSERT INTO " + SCHEMA + "." + table + " DEFAULT VALUES",
                "UPDATE": "UPDATE " + SCHEMA + "." + table + " SET " + column + "=" + column + " WHERE false",
                "DELETE": "DELETE FROM " + SCHEMA + "." + table + " WHERE false",
                "TRUNCATE": "TRUNCATE " + SCHEMA + "." + table,
            }
            with pytest.raises(DBAPIError) as denial:
                with connection.begin_nested():
                    connection.execute(text("SET LOCAL ROLE " + role))
                    assert connection.execute(text("SELECT current_user")).scalar() == role
                    connection.execute(text(statements[command]))
            assert denial.value.orig.pgcode == "42501", "Expected actual privilege denial"


def test_owner_positive_control_reads_fixture_but_unprivileged_backend_requires_policy_acceptance(readiness_postgres):
    with readiness_postgres.begin() as connection:
        connection.execute(text("SET LOCAL search_path TO " + SCHEMA))
        connection.execute(text("SET LOCAL ROLE readiness_owner"))
        assert connection.execute(text("SELECT count(*) FROM social_credentials")).scalar() == 1
        assert bytes(connection.execute(text("SELECT encrypted_bundle FROM social_credentials")).scalar()) == b"inert-envelope-fixture"
        connection.execute(text("SET LOCAL ROLE readiness_backend"))
        assert connection.execute(text("SELECT has_table_privilege(current_user,'social_credentials','SELECT')")).scalar() is True
        assert connection.execute(text("SELECT count(*) FROM social_credentials")).scalar() == 0
        with pytest.raises(DBAPIError) as denial:
            with connection.begin_nested():
                connection.execute(text("INSERT INTO social_credentials (id,provider,credential_kind,encrypted_bundle,key_version) "
                                        "VALUES ('00000000-0000-0000-0000-000000000002','meta','facebook_user',:bundle,'fixture-v1')"),
                                   {"bundle": b"inert-second-envelope"})
        assert denial.value.orig.pgcode == "42501"


def test_inherited_grants_require_exact_role_metadata_pending_role_gate(readiness_postgres):
    """Revoked direct ACLs cannot certify unknown inherited browser roles."""
    with readiness_postgres.begin() as connection:
        connection.execute(text("GRANT SELECT ON " + SCHEMA + ".social_credentials TO readiness_browser_parent"))
        connection.execute(text("GRANT readiness_browser_parent TO authenticated"))
        assert connection.execute(text("SELECT pg_has_role('authenticated','readiness_browser_parent','USAGE')")).scalar() is True
        assert connection.execute(text("SELECT has_table_privilege('authenticated',:table,'SELECT')"),
                                  {"table": SCHEMA + ".social_credentials"}).scalar() is True
        connection.execute(text("SET LOCAL ROLE authenticated"))
        assert connection.execute(text("SELECT count(*) FROM " + SCHEMA + ".social_credentials")).scalar() == 0
        # Roll back this synthetic hostile grant to preserve other local cases.
        connection.rollback()
