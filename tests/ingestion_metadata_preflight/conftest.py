"""Explicit owned PostgreSQL contract; no production credentials or app fixtures."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/verification"))
import ingestion_metadata_preflight as tool


@pytest.fixture(scope="session")
def owner():
    if os.environ.get("B71_PREFLIGHT_OWNED_PG") != "56972":
        pytest.fail(
            "Explicit cached owned PG17 on 127.0.0.1:56972 required; never skip"
        )
    import psycopg2

    params = dict(
        host="127.0.0.1",
        port=56972,
        user="postgres",
        password="b66-owned-only",
        connect_timeout=2,
    )
    admin = psycopg2.connect(dbname="postgres", **params)
    admin.autocommit = True
    with admin.cursor() as c:
        c.execute("CREATE DATABASE b66_preflight_metadata")
        c.execute("CREATE ROLE b71_preflight_reader LOGIN PASSWORD 'owned-reader-only'")
    db = psycopg2.connect(dbname="b66_preflight_metadata", **params)
    db.autocommit = True
    with db.cursor() as c:
        c.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        c.execute("CREATE TABLE alembic_version(version_num varchar(32))")
        c.execute("INSERT INTO alembic_version VALUES ('b71fixture01')")
        c.execute("CREATE TABLE seeding_domain_claims(released_at timestamptz)")
        c.execute(
            "CREATE TABLE etl_dispatch_domains(command_id uuid,claim_token uuid,ready boolean)"
        )
        c.execute("CREATE TABLE etl_dispatch_worker(ready boolean)")
        c.execute("CREATE TABLE etl_dispatch_commands(status varchar(20))")
        c.execute("CREATE TABLE ingestion_jobs(status varchar(40))")
        c.execute("CREATE TABLE private_sentinel(secret text)")
        c.execute("INSERT INTO private_sentinel VALUES ('PRIVATE-RECORD-NEVER-RETURN')")
        for name in tool.v1.TABLES:
            c.execute("ALTER TABLE public." + name + " ENABLE ROW LEVEL SECURITY")
            c.execute(
                "CREATE POLICY hidden ON public." + name + " FOR SELECT USING(false)"
            )
        c.execute(tool.contract.installation_sql("b71_preflight_reader"))
    try:
        yield db
    finally:
        db.close()
        with admin.cursor() as c:
            c.execute("DROP DATABASE b66_preflight_metadata")
            c.execute("DROP ROLE b71_preflight_reader")
        admin.close()


@pytest.fixture
def config(owner):
    with owner.cursor() as c:
        c.execute("SELECT oid FROM pg_database WHERE datname=current_database()")
        oid = c.fetchone()[0]
        c.execute("SELECT oid FROM pg_roles WHERE rolname='b71_preflight_reader'")
        role = c.fetchone()[0]
        c.execute(tool.SCHEMA_SQL, (list(tool.v1.TABLES),))
        schema = c.fetchall()
        c.execute(
            tool.contract.INTERFACE_SQL, tool.contract.interface_parameters(role, None)
        )
        interface = c.fetchone()
    return dict(
        version=2,
        mode="owned-local",
        accepted=True,
        profile=tool.PROFILE,
        source_kind="git-checkout",
        source_manifest_sha256=None,
        execution_head=subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        source_files={
            n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest()
            for n in tool.SOURCE_FILES
        },
        database=dict(
            host="127.0.0.1",
            port=56972,
            name="b66_preflight_metadata",
            oid=oid,
            role="b71_preflight_reader",
            role_oid=role,
            login_user="b71_preflight_reader",
            tls="disable",
            rootcert=None,
            rootcert_sha256=None,
            temporary=True,
        ),
        schema_sha256=tool.budget.content_hash(schema),
        revision="b71fixture01",
        receipt_authority=dict(state="accepted", identity_sha256="1" * 64),
        interface=dict(
            namespace_oid=interface[0],
            function_oid=interface[1],
            owner_oid=interface[2],
            body_sha256=tool.contract.BODY_SHA256,
            role_profile=None,
        ),
    )


@pytest.fixture
def credential():
    return "postgresql://b71_preflight_reader:owned-reader-only@127.0.0.1:56972/b66_preflight_metadata"


@pytest.fixture
def connection(credential):
    import psycopg2

    c = psycopg2.connect(credential, connect_timeout=2)
    c.autocommit = True
    try:
        yield c
    finally:
        c.rollback()
        c.close()


@pytest.fixture
def records(config, connection):
    observed, rows = tool.inspect(connection, config)
    connection.rollback()
    return rows


@pytest.fixture(autouse=True)
def no_ambient_libpq(monkeypatch):
    for key in list(os.environ):
        if key.startswith("PG"):
            monkeypatch.delenv(key)
