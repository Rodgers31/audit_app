"""Real native/dispatch entry refuses incomplete shared ownership storage (#594).

Only the registered handler is inert. Admission, CLI transactions, dispatch
correlation and acknowledgement remain the product implementations. PostgreSQL
is enabled only for either the established owned fixture or this repair's DB.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker

import admin_etl_dispatch_adapter as adapter
from admin_etl_dispatch import accept, TriggerBody
from admin_etl_dispatch_worker import claim, finish, register_worker
from models import Base, EtlDispatchCommand, IngestionJob, IngestionStatus, SeedingDomainClaim
from seeding import cli, registries
import seeding.domains.audits.scope  # noqa: F401  register before replacing the inert registry
from seeding.config import SeedingSettings
from seeding.exclusion import DomainExecution, DomainOwnershipError, dispatch_scope, enter_domain, reserve
from seeding.types import DomainRunResult
from supabase_auth import AdminUser

OWNED_URLS = (
    "postgresql+psycopg2://batch9_readiness:batch9-inert-local@127.0.0.1:55495/batch9_native_readiness",
    "postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55485/batch7_etl_worker",
)
PG_URL = os.environ.get("BATCH9_NATIVE_READINESS_DATABASE_URL") or os.environ.get("BATCH7_ETL_TEST_DATABASE_URL")


@pytest.fixture(scope="module")
def readiness_pg_engine():
    if not PG_URL:
        pytest.skip("Owned PostgreSQL required")
    assert PG_URL in OWNED_URLS, "Never run destructive fixtures on an unowned target"
    engine = create_engine(PG_URL)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(params=["sqlite", "postgresql"])
def readiness_store(request, tmp_path, monkeypatch):
    if request.param == "postgresql":
        engine = request.getfixturevalue("readiness_pg_engine")
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE seeding_domain_claims, etl_dispatch_domains, etl_dispatch_commands, "
                "etl_dispatch_worker, admin_audit_log, ingestion_jobs RESTART IDENTITY CASCADE"))
        # Every malformed-index/column case starts again from the real model.
        SeedingDomainClaim.__table__.drop(engine)
        SeedingDomainClaim.__table__.create(engine)
    else:
        engine = create_engine(f"sqlite:///{tmp_path / 'owned.sqlite'}")
        Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS batch9_readiness_effects (value integer)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS batch9_readiness_markers (stage text)"))
        conn.execute(text("DELETE FROM batch9_readiness_effects"))
        conn.execute(text("DELETE FROM batch9_readiness_markers"))
    factory, calls = sessionmaker(bind=engine), []

    def handler(session, settings, context):
        calls.append(context.job_id)
        session.execute(text("INSERT INTO batch9_readiness_effects VALUES (1)"))
        return DomainRunResult(domain="audits", dry_run=context.dry_run, items_created=1)

    monkeypatch.setattr(registries.REGISTRY, "_handlers", {"audits": handler})
    monkeypatch.setattr(registries, "load_builtin_domains", lambda: None)
    monkeypatch.setattr(cli, "load_builtin_domains", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", factory)
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "true")
    yield factory, engine, calls
    if request.param == "sqlite":
        engine.dispose()


def run(*, dry_run=False, all_domains=False):
    args = argparse.Namespace(domain=None if all_domains else ["audits"], all=all_domains,
        since=None, dry_run=dry_run, audits_source_manifest=None, audits_observe_listing=False)
    return cli.run_seed_command(args, SeedingSettings(log_path=None, total_timeout_seconds=0))


def effects(engine):
    with engine.connect() as conn:
        return conn.scalar(text("SELECT count(*) FROM batch9_readiness_effects"))


def claims(factory):
    with factory() as db:
        return {row.id: (row.domain, row.entered_at, row.entry_id, row.returned_at, row.released_at)
            for row in db.query(SeedingDomainClaim).all()}


def corrupt_index(engine, shape):
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX uq_seeding_active_domain"))
        definitions = {
            "wrong_key": "CREATE UNIQUE INDEX uq_seeding_active_domain ON seeding_domain_claims(id) WHERE released_at IS NULL",
            "multiple_keys": "CREATE UNIQUE INDEX uq_seeding_active_domain ON seeding_domain_claims(domain,id) WHERE released_at IS NULL",
            "wrong_predicate": "CREATE UNIQUE INDEX uq_seeding_active_domain ON seeding_domain_claims(domain) WHERE released_at IS NOT NULL",
            "narrow_predicate": "CREATE UNIQUE INDEX uq_seeding_active_domain ON seeding_domain_claims(domain) WHERE released_at IS NULL AND kind='dispatch'",
            "not_partial": "CREATE UNIQUE INDEX uq_seeding_active_domain ON seeding_domain_claims(domain)",
            "not_unique": "CREATE INDEX uq_seeding_active_domain ON seeding_domain_claims(domain) WHERE released_at IS NULL",
        }
        if shape != "missing":
            conn.execute(text(definitions[shape]))


@pytest.mark.parametrize("shape", ["missing", "wrong_key", "multiple_keys", "wrong_predicate",
    "narrow_predicate", "not_partial", "not_unique"])
@pytest.mark.parametrize("all_domains", [False, True])
def test_real_cli_refuses_bad_index_without_effect_or_retained_claim_change(readiness_store, shape, all_domains):
    factory, engine, calls = readiness_store
    owner = enter_domain(factory, "audits", False)
    owner.close()  # entered ownership survives normal connection close
    before = claims(factory)
    corrupt_index(engine, shape)
    assert run(all_domains=all_domains) == 1
    assert calls == [] and effects(engine) == 0
    assert claims(factory) == before


@pytest.mark.parametrize("shape", ["missing", "wrong_predicate", "not_unique"])
def test_empty_storage_is_not_permission_to_run_without_atomic_index(readiness_store, shape):
    factory, engine, calls = readiness_store
    corrupt_index(engine, shape)
    assert run() == 1
    assert calls == [] and effects(engine) == 0 and claims(factory) == {}


@pytest.mark.parametrize("shape", ["missing_table", "missing_column", "view"])
def test_real_cli_refuses_incomplete_storage(readiness_store, shape):
    factory, engine, calls = readiness_store
    owner = enter_domain(factory, "audits", False)
    owner.close()
    before = claims(factory)
    with engine.begin() as conn:
        if shape == "missing_column":
            conn.execute(text("ALTER TABLE seeding_domain_claims RENAME COLUMN entry_id TO hidden_entry_id"))
        else:
            conn.execute(text("ALTER TABLE seeding_domain_claims RENAME TO hidden_claims"))
            if shape == "view":
                conn.execute(text("CREATE VIEW seeding_domain_claims AS SELECT * FROM hidden_claims"))
    try:
        assert run() == 1
        assert calls == [] and effects(engine) == 0
    finally:
        with engine.begin() as conn:
            if shape == "missing_column":
                conn.execute(text("ALTER TABLE seeding_domain_claims RENAME COLUMN hidden_entry_id TO entry_id"))
            else:
                if shape == "view":
                    conn.execute(text("DROP VIEW seeding_domain_claims"))
                conn.execute(text("ALTER TABLE hidden_claims RENAME TO seeding_domain_claims"))
    assert claims(factory) == before


def queued(factory):
    generation = register_worker(factory)
    actor = AdminUser(id="batch9-inert-admin", email="inert@example.invalid", roles=["admin"])
    with factory() as db:
        result = accept(db, actor, "oag", TriggerBody(dispatch_generation=str(generation), dry_run=False), str(uuid4()))
    return generation, result.command.id


def postgres_only(store):
    if store[1].dialect.name != "postgresql":
        pytest.skip("Actual dispatch supports PostgreSQL only")
    return store


@pytest.mark.parametrize("shape", ["missing", "wrong_key", "wrong_predicate", "not_unique"])
@pytest.mark.parametrize("readiness_store", ["postgresql"], indirect=True)
def test_worker_cannot_acquire_without_atomic_index(readiness_store, shape):
    factory, engine, calls = postgres_only(readiness_store)
    generation, command_id = queued(factory)
    corrupt_index(engine, shape)
    with pytest.raises(DomainOwnershipError):
        claim(factory, generation)
    assert calls == [] and effects(engine) == 0 and claims(factory) == {}
    with factory() as db:
        command = db.get(EtlDispatchCommand, command_id)
        assert command.status == "queued" and command.claim_token is None


@pytest.mark.parametrize("shape", ["missing", "wrong_key", "wrong_predicate", "not_unique"])
@pytest.mark.parametrize("readiness_store", ["postgresql"], indirect=True)
def test_real_dispatch_adapter_refuses_schema_drift_after_claim(readiness_store, shape):
    factory, engine, calls = postgres_only(readiness_store)
    generation, command_id = queued(factory)
    assert (claimed := claim(factory, generation)) is not None
    before = claims(factory)
    corrupt_index(engine, shape)
    assert adapter.execute(factory, engine, *claimed, generation) == 1
    assert calls == [] and effects(engine) == 0 and claims(factory) == before
    with factory() as db:
        assert db.get(EtlDispatchCommand, command_id).execution_started is False


@pytest.mark.parametrize("readiness_store", ["postgresql"], indirect=True)
def test_postgres_invalid_index_is_not_authority(readiness_store):
    factory, engine, calls = postgres_only(readiness_store)
    owner = enter_domain(factory, "audits", False)
    owner.close()
    corrupt_index(engine, "missing")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO seeding_domain_claims(id,domain,kind,acquired_at,entered_at,entry_id) "
            "VALUES (:id,'audits','native',now(),now(),:entry)"), {"id": uuid4(), "entry": uuid4()})
    before = claims(factory)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        with pytest.raises(IntegrityError):
            conn.execute(text("CREATE UNIQUE INDEX CONCURRENTLY uq_seeding_active_domain "
                "ON seeding_domain_claims(domain) WHERE released_at IS NULL"))
        assert conn.scalar(text("SELECT indisvalid FROM pg_index WHERE indexrelid='uq_seeding_active_domain'::regclass")) is False
    assert run() == 1
    assert calls == [] and effects(engine) == 0 and claims(factory) == before


def test_normal_dry_run_release_and_equivalent_index_name(readiness_store):
    factory, engine, calls = readiness_store
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX uq_seeding_active_domain"))
        conn.execute(text('CREATE UNIQUE INDEX batch9_equivalent_active_domain ON seeding_domain_claims(domain) WHERE ("released_at" IS NULL)'))
    assert run(dry_run=True) == 0 and effects(engine) == 0
    assert run() == 0 and run() == 0 and effects(engine) == 2
    assert len(calls) == 3 and len(claims(factory)) == 3
    assert all(row[3] is not None and row[4] is not None for row in claims(factory).values())


@pytest.mark.parametrize("first", ["native", "dispatch"])
@pytest.mark.parametrize("readiness_store", ["postgresql"], indirect=True)
def test_healthy_acquisition_orders_keep_one_owner_and_allow_next_after_return(readiness_store, first):
    factory, engine, calls = postgres_only(readiness_store)
    generation, command_id = queued(factory)
    if first == "native":
        native = enter_domain(factory, "audits", False)
        try:
            assert claim(factory, generation) is None
            now = datetime.now(timezone.utc)
            with factory.begin() as db:
                job = IngestionJob(domain="audits", status=IngestionStatus.COMPLETED,
                    dry_run=False, started_at=now, finished_at=now, items_processed=0,
                    items_created=0, items_updated=0, errors=[], meta={"seeding_claim_id": str(native.identity)})
                db.add(job)
                db.flush()
                job_id = job.id
            native.acknowledge(job_id)
        finally:
            native.close()
        claimed = claim(factory, generation)
    else:
        claimed = claim(factory, generation)
        assert run() == 1 and calls == [] and effects(engine) == 0
    assert claimed is not None and claimed[0] == command_id
    assert adapter.execute(factory, engine, *claimed, generation) == 0
    assert finish(factory, generation, *claimed, 0) is True
    assert run() == 0 and effects(engine) == 2
    assert all(row[4] is not None for row in claims(factory).values())


@pytest.mark.parametrize("readiness_store", ["postgresql"], indirect=True)
def test_dispatch_scope_rechecks_schema_at_actual_cli_entry(readiness_store):
    factory, engine, calls = postgres_only(readiness_store)
    generation, command_id = queued(factory)
    claimed = claim(factory, generation)
    execution = DomainExecution(factory, "audits", claimed[1], command_id, generation)
    execution.open()
    # Model an admitted adapter in the actual shared connection context. Its
    # claim is still unentered; every public CLI entry must verify readiness.
    with factory.begin() as db:
        db.get(EtlDispatchCommand, command_id).execution_started = True
    before = claims(factory)
    def drop_concurrently():
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("SET statement_timeout=10000"))
            conn.execute(text("DROP INDEX CONCURRENTLY uq_seeding_active_domain"))
    with ThreadPoolExecutor(1) as pool:
        dropped = pool.submit(drop_concurrently)
        try:
            # Concurrent DROP first invalidates, then waits for this execution's
            # table-read transaction. Observe that exact intermediate state.
            deadline = time.monotonic() + 5
            with engine.connect() as conn:
                while conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_index WHERE "
                        "indexrelid=to_regclass('uq_seeding_active_domain') AND indisvalid)")):
                    assert time.monotonic() < deadline
                    time.sleep(0.01)
            with dispatch_scope(execution):
                assert run() == 1
            assert calls == [] and effects(engine) == 0 and claims(factory) == before
        finally:
            execution.close()
        dropped.result(timeout=10)


def subprocess_entry(engine, tmp_path, arguments):
    root = Path(__file__).resolve().parents[1]
    url = engine.url.render_as_string(hide_password=False)
    assert url in OWNED_URLS
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHON_DOTENV_DISABLED": "1", "PYTHONPATH": str(root / "tests/batch9_native_readiness_fixture") + os.pathsep + str(root),
        "DATABASE_URL": url, "ADMIN_ETL_DISPATCH_ENABLED": "true", "BATCH9_NATIVE_READINESS_INERT_PROCESS": "true",
        "SEED_STORAGE_PATH": str(tmp_path / "storage"), "SEED_CACHE_PATH": str(tmp_path / "cache"),
        "SEED_LOG_PATH": str(tmp_path / "native.jsonl")}
    return subprocess.run([sys.executable, "-m", *arguments], env=env, cwd=root,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=15)


@pytest.mark.parametrize("readiness_store", ["postgresql"], indirect=True)
@pytest.mark.parametrize("entry", ["native", "dispatch"])
def test_actual_module_process_refuses_missing_index_without_handler_entry(readiness_store, tmp_path, entry):
    factory, engine, _ = readiness_store
    if entry == "native":
        owner = enter_domain(factory, "audits", False)
        owner.close()
        arguments = ["seeding.cli", "seed", "--domain", "audits", "--no-dry-run"]
    else:
        generation, _ = queued(factory)
        command_id, token = claim(factory, generation)
        arguments = ["admin_etl_dispatch_adapter", str(command_id), str(token), str(generation)]
    before = claims(factory)
    corrupt_index(engine, "missing")
    result = subprocess_entry(engine, tmp_path, arguments)
    assert result.returncode == 1, result.stdout
    assert effects(engine) == 0 and claims(factory) == before
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM batch9_readiness_markers")) == 0


@pytest.mark.parametrize("readiness_store", ["postgresql"], indirect=True)
@pytest.mark.parametrize("dry_run", [False, True])
def test_actual_module_process_healthy_return_releases_and_allows_next(readiness_store, tmp_path, dry_run):
    factory, engine, _ = readiness_store
    arguments = ["seeding.cli", "seed", "--domain", "audits", "--dry-run" if dry_run else "--no-dry-run"]
    result = subprocess_entry(engine, tmp_path, arguments)
    assert result.returncode == 0, result.stdout
    assert effects(engine) == (0 if dry_run else 1)
    result = subprocess_entry(engine, tmp_path, arguments)
    assert result.returncode == 0, result.stdout
    assert len(claims(factory)) == 2 and all(row[4] is not None for row in claims(factory).values())


@pytest.mark.parametrize("readiness_store", ["postgresql"], indirect=True)
@pytest.mark.parametrize("fault", ["after_continuity", "before_commit", "none"])
def test_readiness_preserves_lock_transaction_release_atomicity(readiness_store, monkeypatch, fault):
    factory, engine, _ = readiness_store
    execution = enter_domain(factory, "audits", False)
    now = datetime.now(timezone.utc)
    with factory.begin() as db:
        job = IngestionJob(domain="audits", status=IngestionStatus.COMPLETED,
            dry_run=False, started_at=now, finished_at=now, items_processed=0,
            items_created=0, items_updated=0, errors=[], meta={"seeding_claim_id": str(execution.identity)})
        db.add(job)
        db.flush()
        job_id = job.id
    terminated, commit_pids = [], []

    def terminate():
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as killer:
            assert killer.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": execution.pid}) is True
        terminated.append(execution.pid)

    original = execution.continuous

    def proof_then_loss():
        result = original()
        if result:
            terminate()
        return result

    def committing(connection):
        commit_pids.append(connection.scalar(text("SELECT pg_backend_pid()")))
        if fault == "before_commit" and not terminated:
            terminate()

    if fault == "after_continuity":
        monkeypatch.setattr(execution, "continuous", proof_then_loss)
    event.listen(engine, "commit", committing)
    try:
        if fault == "none":
            execution.acknowledge(job_id)
            assert commit_pids == [execution.pid]
        else:
            with pytest.raises(DBAPIError):
                execution.acknowledge(job_id)
            assert terminated == [execution.pid]
    finally:
        event.remove(engine, "commit", committing)
        try:
            execution.close()
        except DBAPIError:
            pass  # deliberately terminated backend cannot accept rollback
    retained = claims(factory)[execution.identity]
    assert (retained[3] is not None) is (fault == "none")
    assert (retained[4] is not None) is (fault == "none")
    assert run() == (0 if fault == "none" else 1)


@pytest.mark.parametrize("readiness_store", ["sqlite"], indirect=True)
def test_sqlite_temp_shadow_cannot_use_main_index_as_ownership_proof(readiness_store, monkeypatch):
    factory, engine, calls = readiness_store
    with engine.connect() as conn:
        conn.execute(text("CREATE TEMP TABLE seeding_domain_claims AS SELECT * FROM main.seeding_domain_claims WHERE 0"))
        conn.commit()
        monkeypatch.setattr(cli, "SessionLocal", sessionmaker(bind=conn))
        try:
            assert run() == 1
            assert calls == []
            assert conn.scalar(text("SELECT count(*) FROM temp.seeding_domain_claims")) == 0
            assert conn.scalar(text("SELECT count(*) FROM main.seeding_domain_claims")) == 0
        finally:
            conn.execute(text("DROP TABLE temp.seeding_domain_claims"))
            conn.commit()
    assert claims(factory) == {} and effects(engine) == 0


@pytest.mark.parametrize("readiness_store", ["postgresql"], indirect=True)
def test_checked_postgres_table_transaction_blocks_ordinary_schema_replacement(readiness_store):
    factory, engine, _ = readiness_store
    execution = enter_domain(factory, "audits", False)
    before = claims(factory)
    try:
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL lock_timeout=100"))
            with pytest.raises(DBAPIError) as error:
                conn.execute(text("DROP INDEX uq_seeding_active_domain"))
            assert error.value.orig.pgcode == "55P03"
        assert claims(factory) == before
    finally:
        execution.close()
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX uq_seeding_active_domain"))
    assert run() == 1 and effects(engine) == 0 and claims(factory) == before


@pytest.mark.parametrize("readiness_store", ["postgresql"], indirect=True)
def test_postgres_checks_the_actual_search_path_table_not_public_index(readiness_store, monkeypatch):
    factory, engine, calls = readiness_store
    schema = "batch9_readiness_private"
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA batch9_readiness_private"))
        conn.execute(text("CREATE TABLE batch9_readiness_private.seeding_domain_claims "
            "(LIKE public.seeding_domain_claims INCLUDING ALL)"))
    private = create_engine(engine.url, connect_args={"options": "-c search_path=batch9_readiness_private,public"})
    private_factory = sessionmaker(bind=private)
    monkeypatch.setattr(cli, "SessionLocal", private_factory)
    try:
        assert run() == 0 and effects(engine) == 1
        before = claims(private_factory)
        assert len(before) == 1 and claims(factory) == {}
        with private.begin() as conn:
            index = conn.scalar(text("SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid "
                "WHERE i.indrelid=to_regclass('seeding_domain_claims') AND pg_get_expr(i.indpred,i.indrelid)='(released_at IS NULL)'"))
            assert index is not None
            quote = conn.dialect.identifier_preparer.quote
            conn.execute(text("DROP INDEX " + quote(schema) + "." + quote(index)))
        # The public table still has its valid arbiter. It cannot protect the
        # private table selected by this connection's actual search_path.
        assert run() == 1 and effects(engine) == 1 and len(calls) == 1
        assert claims(private_factory) == before and claims(factory) == {}
    finally:
        private.dispose()
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA batch9_readiness_private CASCADE"))


@pytest.mark.parametrize("readiness_store", ["sqlite"], indirect=True)
@pytest.mark.parametrize("table_name", ["SEEDING_DOMAIN_CLAIMS", "Seeding_Domain_Claims"])
@pytest.mark.parametrize("entry", ["cli", "reserve"])
def test_sqlite_ascii_case_temp_shadow_refuses_entry_and_preserves_main_claim(readiness_store, monkeypatch, table_name, entry):
    factory, engine, calls = readiness_store
    owner = enter_domain(factory, "audits", False)
    owner.close()
    before = claims(factory)
    assert len(before) == 1 and before[owner.identity][4] is None
    with engine.connect() as conn:
        conn.execute(text("CREATE TEMP TABLE " + table_name + " AS SELECT * FROM main.seeding_domain_claims WHERE 0"))
        conn.commit()
        bound = sessionmaker(bind=conn)
        monkeypatch.setattr(cli, "SessionLocal", bound)
        try:
            if entry == "cli":
                refused = run() == 1
            else:
                refused = False
                try:
                    with bound.begin() as db:
                        reserve(db, "audits", uuid4())
                except DomainOwnershipError:
                    refused = True
            temporary = conn.scalar(text("SELECT count(*) FROM temp.seeding_domain_claims"))
            main = conn.scalar(text("SELECT count(*) FROM main.seeding_domain_claims WHERE released_at IS NULL"))
            effect_count = conn.scalar(text("SELECT count(*) FROM batch9_readiness_effects"))
            assert refused, {"temporary_claims": temporary, "main_retained": main, "effects": effect_count}
            assert temporary == 0 and main == 1 and effect_count == 0 and calls == []
            assert conn.exec_driver_sql("PRAGMA temp.index_list(seeding_domain_claims)").all() == []
        finally:
            conn.execute(text("DROP TABLE temp.seeding_domain_claims"))
            conn.commit()
    assert claims(factory) == before and effects(engine) == 0


@pytest.mark.parametrize("readiness_store", ["sqlite"], indirect=True)
@pytest.mark.parametrize("table_name", ["SEEDING_DOMAIN_CLAIMS", "Seeding_Domain_Claims"])
def test_sqlite_ascii_case_main_table_with_real_index_allows_normal_release(readiness_store, table_name):
    factory, engine, _ = readiness_store
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE seeding_domain_claims RENAME TO batch9_case_rename"))
        conn.execute(text("ALTER TABLE batch9_case_rename RENAME TO " + table_name))
    assert run() == 0 and run() == 0 and effects(engine) == 2
    assert len(claims(factory)) == 2 and all(row[4] is not None for row in claims(factory).values())
