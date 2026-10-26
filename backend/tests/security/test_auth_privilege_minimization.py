"""Actual PostgreSQL proof for the scoped auth-project privilege repair.

The caller must supply an owned, isolated loopback PostgreSQL fixture. A normal
application DATABASE_URL is never read. No hosted account or record is used.
"""

import os
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import psycopg2
import pytest
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]
REPAIR = ROOT / "supabase/migrations/20261026_browser_privilege_minimization.sql"
A = "00000000-0000-4000-8000-000000000001"
B = "00000000-0000-4000-8000-000000000002"
TABLES = ("profiles", "watchlist_items", "data_alerts")
HELPERS = ("audit_log_capture", "audit_log_immutable", "audit_log_identity",
           "handle_new_user", "set_updated_at", "protect_profile_roles")


@pytest.fixture(scope="module")
def cluster():
    raw = os.environ.get("B91_PG_URL")
    if not raw:
        pytest.skip("Requires the explicitly owned B91 PostgreSQL sandbox")
    u = make_url(raw)
    if (u.drivername != "postgresql+psycopg2" or u.host != "127.0.0.1"
            or u.port != 55867 or u.database != "postgres" or u.username != "postgres"
            or u.password or u.query):
        raise ValueError("Use only the owned B91 PostgreSQL sandbox")
    def connect():
        return psycopg2.connect(host=u.host, port=u.port, user=u.username,
            dbname=u.database, connect_timeout=2,
            options="-c statement_timeout=2000 -c lock_timeout=500")
    with closing(connect()) as db, db, db.cursor() as c:
        c.execute("CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS; CREATE ROLE audit_log_reader;")
        # Mirror the observed postgres public defaults and explicit legacy ACLs.
        c.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO anon,authenticated,service_role")
        c.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon,authenticated,service_role")
        c.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO service_role")
        c.execute("CREATE SCHEMA auth; CREATE TABLE auth.users(id uuid PRIMARY KEY,email text,raw_user_meta_data jsonb)")
        c.execute("CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$")
        c.execute((ROOT / "supabase/migrations/20260227_user_features.sql").read_text())
        c.execute((ROOT / "supabase/migrations/20261024_profile_and_subscriber_boundaries.sql").read_text())
        c.execute("GRANT USAGE ON SCHEMA public,auth TO anon,authenticated,service_role,audit_log_reader")
        c.execute("GRANT ALL ON profiles,watchlist_items,data_alerts TO anon,authenticated,service_role")
        c.execute("GRANT REFERENCES(id) ON profiles TO PUBLIC,anon,authenticated")
        c.execute("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon,authenticated,service_role")
        c.execute("INSERT INTO auth.users VALUES (%s,'a@example.invalid','{}'),(%s,'b@example.invalid','{}')", (A,B))
        c.execute("INSERT INTO newsletter_subscribers(email) VALUES ('private@example.invalid')")
        # Real bodies are replayed from the frozen migration, including the
        # security-definer capture context and the actual control-file reader.
        import importlib.util
        path = ROOT / "backend/alembic/versions/a611b12a0001_durable_admin_audit.py"
        spec = importlib.util.spec_from_file_location("b91_audit_migration", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        c.execute("CREATE TABLE admin_audit_log(id integer PRIMARY KEY); CREATE TABLE admin_audit_provenance(audit_id integer,root_xid xid8,incarnation uuid); CREATE TABLE admin_audit_storage(singleton boolean,incarnation uuid)")
        c.execute("INSERT INTO admin_audit_storage VALUES(true,%s)", (str(uuid4()),))
        for name, body, language, returns in (
            ("audit_log_capture", module.CAPTURE_BODY,"plpgsql","trigger"),
            ("audit_log_immutable", module.IMMUTABLE_BODY,"plpgsql","trigger"),
            ("audit_log_identity", module.IDENTITY_BODY,"sql","TABLE(system_identifier text,database_oid oid,timeline integer,in_recovery boolean)"),
        ):
            security = "INVOKER" if name == "audit_log_immutable" else "DEFINER"
            c.execute(f"CREATE FUNCTION public.{name}() RETURNS {returns} LANGUAGE {language} SECURITY {security} SET search_path=pg_catalog AS $body$ {body} $body$")
        c.execute("GRANT EXECUTE ON FUNCTION audit_log_identity() TO audit_log_reader")
        c.execute("CREATE TRIGGER audit_log_capture AFTER INSERT ON admin_audit_log FOR EACH ROW EXECUTE FUNCTION audit_log_capture()")
        # RED replay intentionally leaves the old grants when repair is absent.
        if REPAIR.exists():
            c.execute(REPAIR.read_text())
            c.execute(REPAIR.read_text())  # safe repeat does not restore grants
    yield connect


@pytest.mark.parametrize("role", ["anon", "authenticated"])
@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("privilege", ["TRUNCATE", "REFERENCES", "TRIGGER", "MAINTAIN"])
def test_browser_has_no_table_wide_authority(cluster, role, table, privilege):
    with closing(cluster()) as db, db, db.cursor() as c:
        c.execute("SELECT has_table_privilege(%s,%s,%s)", (role,"public."+table,privilege))
        assert c.fetchone()[0] is False


@pytest.mark.parametrize("role", ["anon", "authenticated"])
@pytest.mark.parametrize("function", HELPERS)
def test_internal_helpers_cannot_be_called_as_browser(cluster, role, function):
    with closing(cluster()) as db, db, db.cursor() as c:
        c.execute("SELECT has_function_privilege(%s,%s,'EXECUTE')", (role,"public."+function+"()"))
        assert c.fetchone()[0] is False


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_browser_truncate_is_actually_refused(cluster, role):
    with closing(cluster()) as db, db, db.cursor() as c:
        c.execute("SET ROLE " + role)
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            c.execute("TRUNCATE data_alerts")
        db.rollback()


def test_legitimate_profile_and_watchlist_operations_preserve_rls(cluster):
    with closing(cluster()) as db, db, db.cursor() as c:
        c.execute("SET ROLE authenticated")
        c.execute("SELECT set_config('request.jwt.claim.sub',%s,true)", (A,))
        c.execute("UPDATE profiles SET display_name='Ordinary edit' WHERE id=%s RETURNING roles", (A,))
        assert c.fetchone()[0] == ["citizen"]
        c.execute("SELECT id FROM profiles ORDER BY id")
        assert c.fetchall() == [(A,)]
        c.execute("UPDATE profiles SET display_name='Cannot edit another user' WHERE id=%s", (B,))
        assert c.rowcount == 0
        c.execute("INSERT INTO watchlist_items(user_id,item_type,item_id,label) VALUES (%s,'county','1','Owned') RETURNING id",(A,))
        item = c.fetchone()[0]
        c.execute("UPDATE watchlist_items SET label='Updated' WHERE id=%s", (item,))
        assert c.rowcount == 1
        c.execute("DELETE FROM watchlist_items WHERE id=%s", (item,))
        assert c.rowcount == 1
        db.rollback()


def test_role_and_subscriber_repair_still_protects_records(cluster):
    with closing(cluster()) as db, db, db.cursor() as c:
        c.execute("SET ROLE authenticated")
        c.execute("SELECT set_config('request.jwt.claim.sub',%s,true)",(A,))
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            c.execute("UPDATE profiles SET roles=ARRAY['admin'] WHERE id=%s",(A,))
        db.rollback()
        c.execute("SET ROLE authenticated")
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            c.execute("SELECT email FROM newsletter_subscribers")
        db.rollback()


def test_audit_reader_and_trigger_and_server_paths_survive(cluster):
    with closing(cluster()) as db, db, db.cursor() as c:
        c.execute("SET ROLE audit_log_reader")
        c.execute("SELECT * FROM audit_log_identity()")
        row = c.fetchone()
        assert len(row) == 4 and row[0].isdigit() and row[3] is False
        c.execute("RESET ROLE; INSERT INTO admin_audit_log VALUES (91)")
        c.execute("SELECT audit_id FROM admin_audit_provenance WHERE audit_id=91")
        assert c.fetchone() == (91,)
        c.execute("SET ROLE service_role")
        c.execute("UPDATE profiles SET roles=ARRAY['admin'] WHERE id=%s",(A,))
        assert c.rowcount == 1
        c.execute("SELECT email FROM newsletter_subscribers")
        assert c.fetchall() == [("private@example.invalid",)]
        db.rollback()


def test_new_postgres_helpers_and_sequences_start_private(cluster):
    with closing(cluster()) as db, db, db.cursor() as c:
        c.execute("CREATE FUNCTION public.b91_future_helper() RETURNS int LANGUAGE sql AS $$ SELECT 1 $$")
        c.execute("CREATE SEQUENCE public.b91_future_sequence")
        for role in ("anon","authenticated"):
            c.execute("SELECT has_function_privilege(%s,'public.b91_future_helper()','EXECUTE'),has_sequence_privilege(%s,'public.b91_future_sequence','USAGE,SELECT,UPDATE')",(role,role))
            assert c.fetchone() == (False,False)
        c.execute("SELECT has_function_privilege('service_role','public.b91_future_helper()','EXECUTE'),has_sequence_privilege('service_role','public.b91_future_sequence','USAGE')")
        assert c.fetchone() == (True,True)
        db.rollback()


def test_column_reference_authority_is_removed(cluster):
    with closing(cluster()) as db, db, db.cursor() as c:
        for role in ("anon","authenticated"):
            c.execute("SELECT has_column_privilege(%s,'profiles','id','REFERENCES')",(role,))
            assert c.fetchone()[0] is False


def test_existing_auth_helper_remains_usable(cluster):
    with closing(cluster()) as db, db, db.cursor() as c:
        c.execute("SET ROLE authenticated")
        c.execute("SELECT set_config('request.jwt.claim.sub',%s,true)",(A,))
        c.execute("SELECT auth.uid()")
        assert str(c.fetchone()[0]) == A
        db.rollback()
