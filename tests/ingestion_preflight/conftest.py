"""Owned fixture only. No shared backend conftest or production configuration."""
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/verification"))
import ingestion_preflight as tool


@pytest.fixture(scope="session")
def pg():
    if os.environ.get("B66_PREFLIGHT_OWNED_PG") != "56972":
        pytest.fail(
            "Set B66_PREFLIGHT_OWNED_PG=56972 after preparing the explicitly owned fixture; integration may not silently skip"
        )
    import psycopg2

    connection = psycopg2.connect(
        host="127.0.0.1",
        port=56972,
        dbname="b66_preflight_owned",
        user="postgres",
        password="b66-owned-only",
        connect_timeout=2,
    )
    connection.autocommit = True
    with connection.cursor() as c:
        c.execute("CREATE ROLE b66_preflight_reader LOGIN PASSWORD 'owned-reader-only'")
        c.execute("GRANT pg_read_all_stats TO b66_preflight_reader")
        c.execute("REVOKE CREATE,TEMP ON DATABASE b66_preflight_owned FROM PUBLIC")
        c.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        # Small realistic contract, not migrations or certification of the full app.
        c.execute(
            "CREATE TABLE public.alembic_version (version_num varchar(32) PRIMARY KEY)"
        )
        c.execute("INSERT INTO public.alembic_version VALUES ('b66fixture01')")
        c.execute(
            "CREATE TABLE public.seeding_domain_claims (id uuid PRIMARY KEY, domain varchar(100), released_at timestamptz, entered_at timestamptz, returned_at timestamptz, reconciliation text)"
        )
        c.execute(
            "CREATE TABLE public.etl_dispatch_domains (domain varchar(100) PRIMARY KEY, ready boolean NOT NULL DEFAULT false, command_id uuid, claim_token uuid)"
        )
        c.execute(
            "CREATE TABLE public.etl_dispatch_worker (id integer PRIMARY KEY CHECK (id=1), ready boolean NOT NULL, generation uuid, expires_at timestamptz)"
        )
        c.execute(
            "CREATE TABLE public.etl_dispatch_commands (id uuid PRIMARY KEY, status varchar(20) NOT NULL, execution_started boolean NOT NULL DEFAULT false)"
        )
        c.execute(
            "CREATE TABLE public.ingestion_jobs (id integer PRIMARY KEY, status varchar(20), domain varchar(100), metadata jsonb)"
        )
        c.execute(
            "CREATE TABLE public.private_sentinel (id integer PRIMARY KEY, secret_value text NOT NULL)"
        )
        c.execute(
            "INSERT INTO public.private_sentinel VALUES (1,'PRIVATE-RECORD-MUST-NOT-APPEAR')"
        )
        c.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO b66_preflight_reader")
    try:
        yield connection
    finally:
        with connection.cursor() as c:
            for name in (*tool.TABLES, "private_sentinel"):
                c.execute("DROP TABLE public." + name)
            c.execute("DROP OWNED BY b66_preflight_reader")
            c.execute("DROP ROLE b66_preflight_reader")
        connection.close()


@pytest.fixture
def config(pg):
    with pg.cursor() as c:
        c.execute("SELECT oid FROM pg_database WHERE datname=current_database()")
        oid = c.fetchone()[0]
        c.execute("SELECT oid FROM pg_roles WHERE rolname='b66_preflight_reader'")
        role_oid = c.fetchone()[0]
        c.execute(tool.SCHEMA_SQL, (list(tool.TABLES),))
        schema = c.fetchall()
    # Expected schema is prepared by the fixture OWNER, independently of run().
    # A hosted expectation may not be discovered/learned by the inspector.
    return {
        "version": 1,
        "mode": "owned-local",
        "accepted": True,
        "execution_head": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "source_files": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in tool.SOURCE_FILES
        },
        "database": {
            "host": "127.0.0.1",
            "port": 56972,
            "name": "b66_preflight_owned",
            "oid": oid,
            "role": "b66_preflight_reader",
            "role_oid": role_oid,
            "tls": "disable",
        },
        "schema_sha256": tool.budget.content_hash(schema),
        "revision": "b66fixture01",
        "receipt_authority": {"state": "accepted", "identity_sha256": "1" * 64},
    }


@pytest.fixture
def credential():
    return "postgresql://b66_preflight_reader:owned-reader-only@127.0.0.1:56972/b66_preflight_owned"


@pytest.fixture(autouse=True)
def no_libpq(monkeypatch):
    for key in os.environ:
        if key.startswith("PG"):
            monkeypatch.delenv(key)
