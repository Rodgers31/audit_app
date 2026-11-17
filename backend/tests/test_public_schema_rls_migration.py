"""Exercise #953 against isolated PostgreSQL databases built by the CI job."""

import os
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import psycopg2
import pytest
from sqlalchemy.engine import make_url


def fixture_url():
    raw = os.environ.get("PUBLIC_SCHEMA_MIGRATION_TEST_URL")
    if not raw:
        pytest.skip("Requires the dedicated disposable schema migration databases")
    url = make_url(raw)
    if (
        url.drivername != "postgresql"
        or url.host != "127.0.0.1"
        or url.port != 55497
        or url.database != "auditgava_schema_fresh"
        or not url.username
        or url.query
    ):
        raise ValueError("Use the dedicated loopback schema migration database")
    return url


def connect_fixture(url):
    return psycopg2.connect(
        host="127.0.0.1", hostaddr="127.0.0.1", port=55497,
        dbname=url.database, user=url.username, password=url.password or "",
        passfile="/nonexistent-schema-migration-passfile", connect_timeout=3,
        sslmode="disable", gssencmode="disable", options="-c search_path=pg_catalog",
    )


def assert_protected_schema(cursor, *, allowed_sequence=None):
    cursor.execute("""
        SELECT relname FROM pg_class
        WHERE relnamespace = 'public'::regnamespace AND relkind IN ('r', 'p', 'f') AND NOT relrowsecurity
        ORDER BY relname
    """)
    assert cursor.fetchall() == []
    cursor.execute("""
        SELECT r.rolname, c.relname
        FROM pg_roles AS r CROSS JOIN pg_class AS c
        WHERE r.rolname IN ('anon', 'authenticated')
          AND c.relnamespace = 'public'::regnamespace AND c.relkind = 'S'
          AND (has_sequence_privilege(r.oid, c.oid, 'SELECT, UPDATE, USAGE WITH GRANT OPTION')
               OR (has_sequence_privilege(r.oid, c.oid, 'USAGE')
                   AND NOT (r.rolname = 'authenticated' AND c.relname IS NOT DISTINCT FROM %s)))
    """, (allowed_sequence,))
    assert cursor.fetchall() == []


def upgrade_database(url, revision="head"):
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=Path(__file__).resolve().parents[1],
        env={
            "PATH": os.environ["PATH"],
            "PYTHON_DOTENV_DISABLED": "1",
            "DATABASE_URL": url.set(query={"hostaddr": "127.0.0.1"}).render_as_string(hide_password=False),
        },
        capture_output=True,
        text=True,
        timeout=90,
    )


def test_fresh_replay_protects_public_tables_and_sequences():
    url = fixture_url()
    result = upgrade_database(url)
    assert result.returncode == 0, result.stderr
    with closing(connect_fixture(url)) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version_num FROM public.alembic_version")
        assert cursor.fetchall() == [("b953a11e0001",)]
        assert_protected_schema(cursor)


def test_upgrade_removes_browser_grants_and_preserves_authorized_writes():
    url = fixture_url().set(database="auditgava_schema_upgrade")
    result = upgrade_database(url, "a756b20a0001")
    assert result.returncode == 0, result.stderr
    with closing(connect_fixture(url)) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT current_database(), version_num FROM public.alembic_version")
        assert cursor.fetchall() == [("auditgava_schema_upgrade", "a756b20a0001")]
        cursor.execute("""
            INSERT INTO public.users (email, password_hash)
            VALUES ('rls-one@example.invalid', 'fixture'), ('rls-two@example.invalid', 'fixture');
            INSERT INTO public.debt_instruments (isin, issue_no, instrument_type, face_value, maturity_date)
            VALUES ('952-DEBT', 'fixture', 'bond', 100, '2030-01-01');
            INSERT INTO public.watchlist_items (user_id, item_type, item_id, label)
            SELECT id, 'county', '1', email FROM public.users;
            ALTER TABLE public.watchlist_items ENABLE ROW LEVEL SECURITY;
            CREATE POLICY fixture_own_watchlist ON public.watchlist_items
                TO authenticated USING (user_id::text = current_setting('request.jwt.claim.sub', true))
                WITH CHECK (user_id::text = current_setting('request.jwt.claim.sub', true));
            GRANT SELECT, UPDATE, DELETE ON public.watchlist_items TO authenticated;
            GRANT INSERT (user_id, item_type, item_id, label) ON public.watchlist_items TO authenticated;
            GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated, service_role;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO anon, authenticated;
            GRANT SELECT ON public.debt_instruments TO anon;
            GRANT INSERT (isin, issue_no, instrument_type, face_value, maturity_date)
                ON public.debt_instruments TO authenticated;
            GRANT SELECT, INSERT, UPDATE, DELETE ON public.debt_instruments TO service_role;
        """)
        cursor.execute("SELECT relrowsecurity FROM pg_class WHERE oid='public.debt_instruments'::regclass")
        assert cursor.fetchone() == (False,)
        cursor.execute("SELECT has_sequence_privilege('anon', 'public.debt_instruments_id_seq', 'USAGE')")
        assert cursor.fetchone() == (True,)
        cursor.execute("""
            CREATE ROLE schema_guard_inherited_reader;
            GRANT SELECT (isin) ON public.debt_instruments TO schema_guard_inherited_reader;
            GRANT schema_guard_inherited_reader TO authenticated;
        """)
        connection.commit()
        result = upgrade_database(url)
        assert result.returncode != 0
        assert "Unexpected public table boundary for authenticated on debt_instruments (SELECT)" in result.stderr
        cursor.execute("SELECT version_num FROM public.alembic_version")
        assert cursor.fetchall() == [("a756b20a0001",)]
        cursor.execute("SELECT relrowsecurity FROM pg_class WHERE oid='public.debt_instruments'::regclass")
        assert cursor.fetchone() == (False,)
        cursor.execute("SELECT has_column_privilege('authenticated', 'public.debt_instruments', 'isin', 'SELECT')")
        assert cursor.fetchone() == (True,)
        cursor.execute("""
            REVOKE schema_guard_inherited_reader FROM authenticated;
            REVOKE SELECT (isin) ON public.debt_instruments FROM schema_guard_inherited_reader;
            DROP ROLE schema_guard_inherited_reader;
        """)
        connection.commit()

        result = upgrade_database(url)
        assert result.returncode == 0, result.stderr
        cursor.execute(
            "SELECT version_num FROM public.alembic_version"
        )
        assert cursor.fetchall() == [("b953a11e0001",)]
        cursor.execute("CREATE SEQUENCE public.schema_migration_later_seq")
        assert_protected_schema(cursor, allowed_sequence="watchlist_items_id_seq")

        cursor.execute("SELECT id FROM public.users WHERE email = 'rls-one@example.invalid'")
        actor, = cursor.fetchone()
        for role in ("anon", "authenticated"):
            cursor.execute(f"SET LOCAL ROLE {role}")
            for statement in (
                "SELECT * FROM public.debt_instruments",
                "UPDATE public.debt_instruments SET face_value = 500",
                "SELECT nextval('public.debt_instruments_id_seq')",
            ):
                cursor.execute("SAVEPOINT guard_refusal")
                with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                    cursor.execute(statement)
                cursor.execute("ROLLBACK TO guard_refusal")
            cursor.execute("RESET ROLE")

        cursor.execute("SELECT set_config('request.jwt.claim.sub', %s, true)", (str(actor),))
        cursor.execute("SET LOCAL ROLE authenticated")
        cursor.execute("SELECT DISTINCT user_id FROM public.watchlist_items")
        assert cursor.fetchall() == [(actor,)]
        cursor.execute("""
            INSERT INTO public.watchlist_items (user_id, item_type, item_id, label)
            VALUES (%s, 'county', '2', 'owned row') RETURNING user_id
        """, (actor,))
        assert cursor.fetchone() == (actor,)
        cursor.execute("RESET ROLE")
        cursor.execute("SET LOCAL ROLE service_role")
        cursor.execute("SELECT face_value FROM public.debt_instruments WHERE isin = '952-DEBT'")
        assert cursor.fetchone() == (100,)
        cursor.execute("""
            INSERT INTO public.debt_instruments (isin, issue_no, instrument_type, face_value, maturity_date)
            VALUES ('952-SERVICE', 'fixture', 'bond', 200, '2030-01-01') RETURNING face_value
        """)
        assert cursor.fetchone() == (200,)
        cursor.execute("RESET ROLE")
        cursor.execute("SELECT count(*) FROM public.debt_instruments")
        assert cursor.fetchone() == (2,)
