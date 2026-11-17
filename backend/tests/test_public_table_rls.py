"""Check the migrated public schema on a disposable CI PostgreSQL database."""

import os
from contextlib import closing

import psycopg2
import pytest
from sqlalchemy.engine import make_url


BROWSER_OPERATIONS = {
    ("authenticated", "profiles"): {"SELECT", "INSERT", "UPDATE"},
    ("authenticated", "watchlist_items"): {"SELECT", "INSERT", "UPDATE", "DELETE"},
    ("authenticated", "data_alerts"): {"SELECT", "UPDATE"},
}

INSPECT_TABLES = """
WITH public_tables AS (
    SELECT c.oid, c.relname::text, c.relrowsecurity
    FROM pg_catalog.pg_class AS c
    JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'f')
),
browser_roles AS (
    SELECT oid, rolname::text
    FROM pg_catalog.pg_roles
    WHERE rolname IN ('anon', 'authenticated')
)
SELECT t.relname, 'rls' AS problem, NULL AS role, NULL AS operation
FROM public_tables AS t
WHERE NOT t.relrowsecurity
UNION ALL
SELECT t.relname, 'privilege', r.rolname, p.operation
FROM public_tables AS t
CROSS JOIN browser_roles AS r
CROSS JOIN unnest(%s::text[]) AS p(operation)
WHERE pg_catalog.has_table_privilege(r.oid, t.oid, p.operation)
   OR CASE WHEN p.operation IN ('SELECT', 'INSERT', 'UPDATE', 'REFERENCES',
                                'SELECT WITH GRANT OPTION', 'INSERT WITH GRANT OPTION',
                                'UPDATE WITH GRANT OPTION', 'REFERENCES WITH GRANT OPTION')
           THEN pg_catalog.has_any_column_privilege(r.oid, t.oid, p.operation)
           ELSE false END
"""


def schema_violations(cursor):
    cursor.execute("SHOW server_version_num")
    operations = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"]
    if int(cursor.fetchone()[0]) >= 170000:
        operations.append("MAINTAIN")
    cursor.execute(INSPECT_TABLES, (operations + [f"{operation} WITH GRANT OPTION"
                                                  for operation in operations],))
    return [
        (table, problem, role, operation)
        for table, problem, role, operation in cursor
        if problem == "rls" or operation not in BROWSER_OPERATIONS.get((role, table), set())
    ]


@pytest.fixture
def guard_cursor():
    raw = os.environ.get("PUBLIC_SCHEMA_GUARD_CI_URL")
    if not raw:
        pytest.skip("Requires the migrated disposable CI database")
    url = make_url(raw)
    if (url.drivername != "postgresql" or url.host != "127.0.0.1"
            or url.port != 55498 or url.database != "auditgava_schema_guard"
            or not url.username or url.query):
        raise ValueError("The schema guard requires the dedicated loopback CI database")
    # Supplying the numeric address separately prevents libpq from supplying
    # its own hostaddr from the connection environment.
    with closing(psycopg2.connect(
        host="127.0.0.1", hostaddr="127.0.0.1", port=55498,
        dbname="auditgava_schema_guard", user=url.username, password=url.password or "",
        passfile="/nonexistent-schema-guard-passfile", connect_timeout=3,
        sslmode="disable", gssencmode="disable", options="-c search_path=pg_catalog",
    )) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT current_database(), to_regclass('public.alembic_version') IS NOT NULL")
        assert cursor.fetchone() == ("auditgava_schema_guard", True)
        cursor.execute("SELECT count(*) FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
        assert cursor.fetchone() == (2,)
        yield cursor


def test_security_guard_rls_on_every_public_table(guard_cursor):
    violations = schema_violations(guard_cursor)
    missing_rls = sum(problem == "rls" for _, problem, _, _ in violations)
    unexpected_grants = len(violations) - missing_rls
    pytest_assertion = (
        f"Public schema guard found {missing_rls} RLS and {unexpected_grants} privilege violations"
    )
    if violations:
        pytest.fail(pytest_assertion, pytrace=False)


@pytest.mark.parametrize("port", ["", ":5432"])
def test_guard_refuses_other_ports_before_connecting(monkeypatch, port):
    monkeypatch.setenv("PUBLIC_SCHEMA_GUARD_CI_URL", f"postgresql://postgres@127.0.0.1{port}/auditgava_schema_guard")
    monkeypatch.setattr(psycopg2, "connect", lambda *_a, **_kw: pytest.fail("Unexpected connection"))
    with pytest.raises(ValueError, match="dedicated loopback CI database"):
        next(guard_cursor.__wrapped__())


def test_guard_pins_driver_address_despite_pg_environment(monkeypatch):
    monkeypatch.setenv("PUBLIC_SCHEMA_GUARD_CI_URL", "postgresql://postgres@127.0.0.1:55498/auditgava_schema_guard")
    monkeypatch.setenv("PGHOSTADDR", "192.0.2.10")
    monkeypatch.setenv("PGPORT", "5432")

    class StopBeforeConnect(Exception):
        pass

    def connect(*args, **kwargs):
        assert not args
        assert kwargs["host"] == kwargs["hostaddr"] == "127.0.0.1"
        assert kwargs["port"] == 55498
        assert kwargs["dbname"] == "auditgava_schema_guard"
        raise StopBeforeConnect

    monkeypatch.setattr(psycopg2, "connect", connect)
    with pytest.raises(StopBeforeConnect):
        next(guard_cursor.__wrapped__())


def test_guard_detects_disabled_rls_and_inherited_column_privilege(guard_cursor):
    guard_cursor.execute("""
        CREATE TABLE public.schema_guard_probe (id integer);
        CREATE ROLE schema_guard_probe_reader;
        GRANT SELECT (id) ON public.schema_guard_probe TO schema_guard_probe_reader;
        GRANT schema_guard_probe_reader TO anon;
    """)
    def get_probe_violations():
        return {
            (problem, role, operation)
            for table, problem, role, operation in schema_violations(guard_cursor)
            if table == "schema_guard_probe"
        }
    assert get_probe_violations() == {("rls", None, None), ("privilege", "anon", "SELECT")}
    guard_cursor.execute("""
        ALTER TABLE public.schema_guard_probe ENABLE ROW LEVEL SECURITY;
        REVOKE schema_guard_probe_reader FROM anon;
    """)
    assert not get_probe_violations()
