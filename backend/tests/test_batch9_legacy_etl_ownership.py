"""Actual loader/native CLI/dedicated worker interleavings on owned PostgreSQL."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

URL_OVERRIDE = os.getenv("BATCH9_LEGACY_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "backend/tests/batch9_legacy_fixture"
sys.path.insert(0, str(FIXTURE))
from batch9_legacy_target import validate_target, connect_args, DEFAULT_URL, OWNED_PORT, owned_postgres_fixture
URL = URL_OVERRIDE or DEFAULT_URL

def wait_for(read, predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = read()
        if predicate(value):
            return value
        time.sleep(.04)
    raise AssertionError(f"Owned control timeout: last={value}")

@pytest.fixture
def db(owned_database):
    engine = create_engine(validate_target(URL), connect_args=connect_args())
    factory = sessionmaker(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE countries,seeding_domain_claims,etl_dispatch_worker,etl_dispatch_commands,ingestion_jobs,admin_audit_log RESTART IDENTITY CASCADE"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS batch9_legacy_control(writer text PRIMARY KEY,mode text NOT NULL)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS batch9_legacy_markers(stage text,writer text,pid integer)"))
        conn.execute(text("TRUNCATE batch9_legacy_control,batch9_legacy_markers"))
        conn.execute(text("INSERT INTO batch9_legacy_control VALUES ('native','normal'),('legacy','normal')"))
        conn.execute(text("INSERT INTO countries (id,iso_code,name,currency,timezone,default_locale) VALUES (1,'KEN','Inert Kenya','KES','UTC','en')"))
        conn.execute(text("INSERT INTO entities(id,country_id,type,canonical_name,slug) VALUES(1,1,'AGENCY','Inert entity','inert-entity')"))
        conn.execute(text("INSERT INTO fiscal_periods(id,country_id,label,start_date,end_date) VALUES(1,1,'INERT BASE','2024-01-01','2024-12-31')"))
        conn.execute(text("INSERT INTO source_documents(id,country_id,publisher,title,url,doc_type,fetch_date,last_seen_at,status) VALUES(1,1,'Inert fixture','Owned base','https://fixture.invalid/base.pdf','AUDIT',now(),now(),'AVAILABLE')"))
        for table in ('countries','entities','fiscal_periods','source_documents'):
            conn.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}','id'),1)"))
    yield engine, factory
    engine.dispose()


@pytest.fixture(scope="session")
def owned_database(tmp_path_factory):
    with owned_postgres_fixture(URL_OVERRIDE, ROOT, tmp_path_factory.mktemp("batch9-review-596-resources")) as url:
        yield url

def env(tmp_path, domain="audits", dispatch=True):
    storage = tmp_path / "storage"
    storage.mkdir(exist_ok=True)
    return {"PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin", "PYTHON_DOTENV_DISABLED": "1", "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(FIXTURE) + os.pathsep + str(ROOT / "backend") + os.pathsep + str(ROOT),
            "DATABASE_URL": URL, "BATCH9_LEGACY_INERT": "true", "BATCH9_NATIVE_DOMAIN": domain,
            "BATCH9_LEGACY_FIXTURE_PORT": str(OWNED_PORT),
            "ADMIN_ETL_DISPATCH_ENABLED": "true" if dispatch else "false", "BACKFILL_STORAGE": str(storage),
            "SEED_STORAGE_PATH": str(storage), "SEED_CACHE_PATH": str(storage / "cache"), "SEED_LOG_PATH": str(tmp_path / "seed.jsonl")}

def start(tmp_path, kind, domain="audits", extra=None):
    child_env = env(tmp_path, domain)
    child_env.update({k: v for k, v in (extra or {}).items() if v is not None})
    for key, value in (extra or {}).items():
        if value is None:
            child_env.pop(key, None)
    args = {"native": ["-m", "seeding.cli", "seed", "--domain", domain, "--no-dry-run"],
            "dispatch": ["-m", "admin_etl_dispatch_worker"], "worker": ["-m", "etl.worker"],
            "backfill": ["-m", "etl.backfill"]}.get(kind, [str(FIXTURE / "entry.py"), kind])
    output = open(tmp_path / f"{kind}-{time.monotonic_ns()}.txt", "w")
    proc = subprocess.Popen([sys.executable, *args], cwd=ROOT / "backend", env=child_env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
    proc._batch9_output = output
    return proc

def stop(proc):
    # Always stop the group: killing the scheduling parent can leave a live child.
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait(timeout=5)
    proc._batch9_output.close()

def scalar(engine, sql, **params):
    with engine.connect() as conn:
        return conn.scalar(text(sql), params)

def mode(engine, writer, value):
    with engine.begin() as conn:
        conn.execute(text("UPDATE batch9_legacy_control SET mode=:mode WHERE writer=:writer"), {"mode": value, "writer": writer})

def entered(engine, writer, stage="entered"):
    return wait_for(lambda: scalar(engine, "SELECT count(*) FROM batch9_legacy_markers WHERE writer=:w AND stage=:s", w=writer, s=stage), lambda n: n == 1)

def effects(engine):
    return scalar(engine, "SELECT count(*) FROM audits")

def retained(engine):
    return scalar(engine, "SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NULL")

def queue(factory):
    from admin_etl_dispatch import accept, TriggerBody
    from models import EtlDispatchWorker
    from supabase_auth import AdminUser
    from uuid import uuid4
    generation = wait_for(lambda: _generation(factory), lambda g: g is not None)
    with factory() as session:
        return accept(session, AdminUser(id="inert-admin", email="inert@example.invalid", roles=["admin"]), "oag", TriggerBody(dispatch_generation=str(generation)), str(uuid4())).command.id

def _generation(factory):
    from models import EtlDispatchWorker
    with factory() as session:
        row = session.get(EtlDispatchWorker, 1)
        return row.generation if row else None

@pytest.mark.parametrize("native_kind", ["native", "dispatch"])
def test_legacy_first_blocks_native_or_dispatch_then_next_run(db, tmp_path, native_kind, monkeypatch):
    engine, factory = db
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "true")
    mode(engine, "legacy", "before")
    legacy = start(tmp_path, "document")
    other = None
    try:
        entered(engine, "legacy")
        with engine.connect() as connection:
            legacy_claim_ids = connection.execute(text(
                "SELECT id::text FROM seeding_domain_claims WHERE released_at IS NULL"
            )).scalars().all()
        assert len(legacy_claim_ids) == 13
        if native_kind == "dispatch":
            # A queued successor may acquire ownership as soon as legacy exits.
            # Hold its real handler before effects to observe that transfer.
            mode(engine, "native", "before")
        other = start(tmp_path, native_kind)
        if native_kind == "native":
            assert other.wait(timeout=15) == 1, "Conflicting native CLI ran while legacy owned writes"
        else:
            identity = queue(factory)
            time.sleep(.6)
            assert scalar(engine, "SELECT status FROM etl_dispatch_commands WHERE id=:i", i=identity) == "queued"
        assert effects(engine) == 0
        mode(engine, "legacy", "normal")
        assert legacy.wait(timeout=20) == 0
        assert scalar(engine, "SELECT count(*) FROM seeding_domain_claims "
                      "WHERE id=ANY(CAST(:claim_ids AS uuid[])) AND released_at IS NULL",
                      claim_ids=legacy_claim_ids) == 0
        if native_kind == "native":
            assert effects(engine) == 1 and retained(engine) == 0
            stop(other)
            other = start(tmp_path, "native")
            assert other.wait(timeout=15) == 0
        else:
            entered(engine, "native")
            assert effects(engine) == 1 and retained(engine) == 1
            assert scalar(engine, "SELECT count(*) FROM seeding_domain_claims "
                          "WHERE kind='dispatch' AND released_at IS NULL") == 1
            mode(engine, "native", "normal")
            wait_for(lambda: scalar(engine, "SELECT status FROM etl_dispatch_commands WHERE id=:i", i=identity), lambda s: s == "completed")
        assert effects(engine) == 2 and retained(engine) == 0
    finally:
        stop(legacy)
        if other:
            stop(other)


def test_real_backfill_default_concurrency_completes_two_documents(db, tmp_path):
    engine, factory = db
    proc = start(tmp_path, "backfill", extra={"BATCH9_DOCUMENT_COUNT": "2", "BACKFILL_SOURCES": "oag", "BACKFILL_CONCURRENCY": "3"})
    try:
        assert proc.wait(timeout=30) == 0
        assert effects(engine) == 2
        assert retained(engine) == 0
        import json
        summary = json.loads((tmp_path / "storage/backfill_summary.json").read_text())
        assert summary["queued_unique"] == summary["succeeded"] == 2
        assert summary["failed"] == 0
    finally:
        stop(proc)

@pytest.mark.parametrize("native_kind", ["native", "dispatch"])
@pytest.mark.parametrize("legacy_entry", ["document", "pipeline", "backfill", "worker-once", "scheduler-once", "session", "country", "entity", "period"])
def test_native_or_dispatch_first_refuses_every_legacy_boundary(db, tmp_path, native_kind, legacy_entry, monkeypatch):
    engine, factory = db
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "true")
    mode(engine, "native", "before")
    owner = start(tmp_path, native_kind)
    other = None
    try:
        if native_kind == "dispatch":
            queue(factory)
        entered(engine, "native")
        other = start(tmp_path, legacy_entry)
        assert other.wait(timeout=20) != 0, "Legacy boundary bypassed native/dispatch ownership"
        assert effects(engine) == 0
        assert scalar(engine, "SELECT count(*) FROM entities") == 1
        assert scalar(engine, "SELECT count(*) FROM fiscal_periods") == 1
        assert scalar(engine, "SELECT count(*) FROM countries") == 1
        assert scalar(engine, "SELECT count(*) FROM source_documents") == 1
        mode(engine, "native", "normal")
        if native_kind == "native":
            assert owner.wait(timeout=15) == 0
        else:
            wait_for(lambda: retained(engine), lambda n: n == 0)
        assert effects(engine) == 1
    finally:
        stop(owner)
        if other:
            stop(other)

@pytest.mark.parametrize("phase,expected", [("before", 0), ("after", 1)])
def test_legacy_death_retains_authority_and_restart_cannot_add_effect(db, tmp_path, phase, expected):
    engine, _ = db
    mode(engine, "legacy", phase)
    legacy = start(tmp_path, "document")
    other = None
    try:
        entered(engine, "legacy", "entered" if phase == "before" else "committed")
        stop(legacy)
        mode(engine, "legacy", "normal")
        other = start(tmp_path, "native")
        assert other.wait(timeout=15) == 1
        assert effects(engine) == expected and retained(engine) > 0
        stop(other)
        other = start(tmp_path, "document")
        assert other.wait(timeout=15) != 0
        assert effects(engine) == expected
    finally:
        stop(legacy)
        if other:
            stop(other)

def test_simultaneous_starts_have_one_effect(db, tmp_path):
    engine, _ = db
    mode(engine, "legacy", "before")
    mode(engine, "native", "before")
    with ThreadPoolExecutor(2) as pool:
        runners = list(pool.map(lambda kind: start(tmp_path, kind), ["document", "native"]))
    try:
        wait_for(lambda: [p.poll() for p in runners], lambda codes: sum(c is not None for c in codes) == 1)
        assert effects(engine) == 0
        mode(engine, "legacy", "normal")
        mode(engine, "native", "normal")
        assert sorted(p.wait(timeout=20) for p in runners) == [0, 1]
        assert effects(engine) == 1 and retained(engine) == 0
    finally:
        for runner in runners:
            stop(runner)


@pytest.mark.parametrize("domain", ["counties_budget", "county_officials", "debt_timeline", "economic_indicators", "fiscal_summary", "national_budget", "national_debt", "national_gdp", "pending_bills", "population", "revenue_by_source", "stalled_projects"])
@pytest.mark.parametrize("first", ["legacy", "native"])
def test_shared_references_exclude_other_native_domains_in_both_orders(db, tmp_path, domain, first):
    engine, _ = db
    writer = "legacy" if first == "legacy" else "native"
    mode(engine, writer, "before")
    owner = start(tmp_path, "document" if first == "legacy" else "native", domain)
    other = None
    try:
        entered(engine, writer)
        other = start(tmp_path, "native" if first == "legacy" else "entity", domain)
        assert other.wait(timeout=15) == 1
        assert effects(engine) == 0 and scalar(engine, "SELECT count(*) FROM entities") == 1
        mode(engine, writer, "normal")
        assert owner.wait(timeout=20) == 0
        assert effects(engine) == 1 and retained(engine) == 0
    finally:
        stop(owner)
        if other:
            stop(other)


def test_scheduling_parent_death_does_not_release_live_writing_child(db, tmp_path):
    engine, _ = db
    mode(engine, "legacy", "before")
    cfg = tmp_path / "schedule.yaml"
    cfg.write_text("countries:\n  KE:\n    sources:\n      oag: {interval_hours: 24}\n")
    # psycopg2 scheduler consumes a DBAPI URL, as the deployed worker does.
    parent = start(tmp_path, "worker", extra={"ETL_SCHEDULE_CONFIG": str(cfg), "DATABASE_URL": URL.replace("+psycopg2", "")})
    other = None
    try:
        entered(engine, "legacy")
        os.kill(parent.pid, signal.SIGKILL)
        parent.wait(timeout=5)
        assert retained(engine) == 13
        other = start(tmp_path, "native")
        assert other.wait(timeout=15) == 1 and effects(engine) == 0
        mode(engine, "legacy", "normal")
        wait_for(lambda: effects(engine), lambda n: n == 1)
        wait_for(lambda: retained(engine), lambda n: n == 0)
        stop(other)
        other = start(tmp_path, "native")
        assert other.wait(timeout=15) == 0 and effects(engine) == 2
    finally:
        stop(parent)
        if other:
            stop(other)


def test_legacy_lock_backend_death_retains_all_claims(db, tmp_path):
    engine, _ = db
    mode(engine, "legacy", "before")
    owner = start(tmp_path, "document")
    other = None
    try:
        entered(engine, "legacy")
        with engine.begin() as conn:
            pids = conn.scalars(text("SELECT DISTINCT pid FROM pg_locks WHERE locktype='advisory' AND granted")).all()
            assert len(pids) == 13
            assert conn.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": pids[0]}) is True
        other = start(tmp_path, "native")
        assert other.wait(timeout=15) == 1
        mode(engine, "legacy", "normal")
        assert owner.wait(timeout=20) == 1
        assert effects(engine) == 1 and retained(engine) == 13
    finally:
        stop(owner)
        if other:
            stop(other)


@pytest.mark.parametrize("entry", ["document", "pipeline", "backfill", "worker-once", "scheduler-once", "session"])
def test_legacy_success_and_normal_release_allow_native_next_run(db, tmp_path, entry):
    engine, _ = db
    first = start(tmp_path, entry)
    second = None
    try:
        assert first.wait(timeout=20) == 0
        assert effects(engine) == 1 and retained(engine) == 0
        assert scalar(engine, "SELECT count(*) FROM audits WHERE publishable") == 0
        second = start(tmp_path, "native")
        assert second.wait(timeout=15) == 0
        assert effects(engine) == 2 and retained(engine) == 0
    finally:
        stop(first)
        if second:
            stop(second)


def ownership_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("batch9_ownership_probe", ROOT / "etl/writer_ownership.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_invalid_then_valid_receipt_preserves_lock_and_releases(db):
    engine, _ = db
    ownership = ownership_module()
    with ownership.writer_scope(engine) as scope:
        execution = scope.executions[0]
        with pytest.raises(ownership.DomainOwnershipError):
            execution.acknowledge(scope.jobs[execution.domain])
        assert execution.continuous() is True and retained(engine) == 13
    assert retained(engine) == 0


def test_manual_session_transaction_failure_retains_on_close(db):
    engine, _ = db
    ownership = ownership_module()
    session = ownership.OwnedSession(bind=engine)
    try:
        with pytest.raises(Exception):
            with session.begin():
                # Flush/commit error even when bypassing Session.commit().
                session.execute(text("INSERT INTO countries(iso_code) VALUES ('BAD')"))
    finally:
        with pytest.raises(ownership.DomainOwnershipError):
            session.close()
    assert retained(engine) == 13


@pytest.mark.parametrize("ambient", [None, "false", "different-inert-value"])
def test_dispatch_remains_off_without_explicit_true(db, tmp_path, ambient):
    engine, _ = db
    worker = start(tmp_path, "dispatch", extra={"ADMIN_ETL_DISPATCH_ENABLED": ambient})
    try:
        assert worker.wait(timeout=15) == 1
        assert scalar(engine, "SELECT count(*) FROM etl_dispatch_worker") == 0
        assert effects(engine) == retained(engine) == 0
    finally:
        stop(worker)
