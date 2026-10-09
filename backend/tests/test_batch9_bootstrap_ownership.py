"""#582: actual bootstrap/native processes against one owned PostgreSQL."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import uuid4
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from batch9_bootstrap_fixture.owned_database import owned_engine, owned_url, schema_url

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name("batch9_bootstrap_fixture")
URL = os.environ.get("BATCH9_BOOTSTRAP_POSTGRES_URL", "")


def wait_for(probe, predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = probe()
        if predicate(value):
            return value
        time.sleep(0.05)
    raise AssertionError(f"Process control did not arrive; last value: {value}")


@pytest.fixture(scope="module")
def bootstrap_postgres_url():
    if URL:
        owned_url(URL)
        yield URL
    else:
        from batch9_bootstrap_fixture.owned_postgres import postgres
        with postgres() as url:
            yield url


@pytest.fixture
def owned_pg(tmp_path, bootstrap_postgres_url):
    url = bootstrap_postgres_url
    owned_url(url)
    from models import Base
    admin = owned_engine(url)
    schema = "bootstrap_" + uuid4().hex
    with admin.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped_url = schema_url(url, schema).render_as_string(hide_password=False)
    engine = owned_engine(scoped_url, allow_schema=True)
    Base.metadata.create_all(engine)
    with engine.begin() as db:
        db.execute(text("CREATE TABLE batch9_control(mode text NOT NULL)"))
        db.execute(text("INSERT INTO batch9_control VALUES ('normal')"))
        db.execute(text("CREATE TABLE batch9_markers(pid integer,stage text,job_id integer,live_fetch boolean,dry_run boolean)"))
        db.execute(text("CREATE TABLE batch9_effects(pid integer)"))
    env = {"PATH": os.environ["PATH"], "DATABASE_URL": scoped_url,
           "BATCH9_BOOTSTRAP_INERT": "true", "PYTHON_DOTENV_DISABLED": "1",
           "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONPATH": f"{FIXTURE}:{ROOT / 'backend'}",
           "AUTO_SEEDER_ENABLED": "false", "AUTO_WARMUP_ENABLED": "false",
           "ENABLE_ETL_SCHEDULER": "false", "SEED_STORAGE_PATH": str(tmp_path),
           "JWT_SECRET_KEY": "batch9-bootstrap-inert-startup-key"}
    processes = []

    def launch(kind, *args, extra=None):
        if kind == "native":
            command = [sys.executable, "-m", "seeding.cli", "seed", *args]
        elif kind == "startup":
            command = [sys.executable, "-c", "import asyncio, main; asyncio.run(main._startup_sequence()); "
                       "print('BOOTSTRAP_READY', main._app_ready.is_set()); "
                       "raise SystemExit(0 if main._app_ready.is_set() else 2)"]
        else:
            # Weekly workflow uses this exact import/call; manual force is explicit.
            code = "from bootstrap import initialize_reference_data; initialize_reference_data(" + (
                "force=True" if kind == "force" else "") + ")"
            command = [sys.executable, "-c", code]
        stream = (tmp_path / f"{len(processes)}-{kind}.txt").open("w")
        child_env = {**env, **(extra or {})}
        child_env = {key: value for key, value in child_env.items() if value is not None}
        proc = subprocess.Popen(command, cwd=ROOT / "backend", env=child_env,
                                stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        stream.close()
        processes.append(proc)
        return proc

    try:
        yield engine, launch, tmp_path
    finally:
        for proc in processes:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
        for path in tmp_path.glob("*-*.txt"):
            print(f"PROCESS OUTPUT {path.name}\n{path.read_text()}")
        engine.dispose()
        with admin.begin() as db:
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def scalar(engine, sql):
    with engine.connect() as db:
        return db.scalar(text(sql))


def set_mode(engine, value):
    with engine.begin() as db:
        db.execute(text("UPDATE batch9_control SET mode=:mode"), {"mode": value})


def entered(engine, n=1):
    wait_for(lambda: scalar(engine, "SELECT count(*) FROM batch9_markers WHERE stage='entered'"), lambda x: x == n)


def claims(engine):
    with engine.connect() as db:
        return tuple(db.execute(text("SELECT count(*) FILTER (WHERE released_at IS NULL), "
                                     "count(*) FILTER (WHERE released_at IS NOT NULL) FROM seeding_domain_claims")).one())


def budget_sentinel(engine):
    from models import BudgetLine, Country, DocumentType, Entity, EntityType, FiscalPeriod, SourceDocument
    from sqlalchemy.orm import sessionmaker
    with sessionmaker(bind=engine).begin() as db:
        country = Country(name="Kenya", iso_code="KEN", currency="KES", timezone="Africa/Nairobi", default_locale="en_KE")
        db.add(country)
        db.flush()
        entity = Entity(country_id=country.id, type=EntityType.NATIONAL, canonical_name="Owned sentinel", slug="owned-sentinel")
        period = FiscalPeriod(country_id=country.id, label="FY2025/26", start_date=datetime(2025, 7, 1), end_date=datetime(2026, 6, 30))
        doc = SourceDocument(country_id=country.id, title="Owned sentinel", publisher="Inert fixture",
                             doc_type=DocumentType.BUDGET, fetch_date=datetime.now(timezone.utc))
        db.add_all([entity, period, doc])
        db.flush()
        db.add(BudgetLine(entity_id=entity.id, period_id=period.id, source_document_id=doc.id,
                          category="owned-preserved-budget", allocated_amount=123, currency="KES"))


@pytest.mark.parametrize("arguments", [("--domain", "national_budget", "--no-dry-run"), ("--all", "--no-dry-run")])
@pytest.mark.parametrize("kind", ["force", "weekly", "startup"])
def test_native_first_bootstrap_skips_budget_and_preserves_reference_work(owned_pg, arguments, kind):
    engine, launch, _ = owned_pg
    budget_sentinel(engine)
    set_mode(engine, "before")
    native = launch("native", *arguments)
    entered(engine)
    bootstrap = launch(kind)
    assert bootstrap.wait(timeout=15) == 0
    assert scalar(engine, "SELECT count(*) FROM batch9_markers WHERE stage='entered'") == 1
    assert scalar(engine, "SELECT count(*) FROM batch9_effects") == 0
    assert scalar(engine, "SELECT count(*) FROM budget_lines WHERE category='owned-preserved-budget'") == 1
    assert scalar(engine, "SELECT count(*) FROM entities WHERE type='COUNTY'") == 47
    assert scalar(engine, "SELECT count(*) FROM ingestion_jobs WHERE domain='national_budget' "
                  "AND metadata->>'ownership_refused'='true'") == 1
    assert claims(engine) == (1, 0)
    set_mode(engine, "normal")
    assert native.wait(timeout=15) == 0
    assert claims(engine) == (0, 1)


@pytest.mark.parametrize("kind", ["weekly", "startup"])
@pytest.mark.parametrize("arguments", [("--domain", "national_budget", "--no-dry-run"), ("--all", "--no-dry-run")])
def test_bootstrap_first_blocks_native_then_completion_allows_next(owned_pg, kind, arguments):
    engine, launch, _ = owned_pg
    set_mode(engine, "before")
    bootstrap = launch(kind)
    entered(engine)
    native = launch("native", *arguments)
    assert native.wait(timeout=15) == 1
    assert scalar(engine, "SELECT count(*) FROM batch9_markers WHERE stage='entered'") == 1
    assert claims(engine) == (1, 0)
    set_mode(engine, "normal")
    assert bootstrap.wait(timeout=15) == 0
    assert claims(engine) == (0, 1)
    assert scalar(engine, "SELECT count(*) FROM batch9_markers WHERE live_fetch=false AND dry_run=false") == 1
    after = launch("native", *arguments)
    assert after.wait(timeout=15) == 0
    assert claims(engine) == (0, 2)


@pytest.mark.parametrize("ambient", [None, "different-inert-startup-value"])
def test_startup_scopes_its_configuration_with_absent_or_different_ambient(owned_pg, ambient):
    engine, launch, _ = owned_pg
    assert launch("startup", extra={"JWT_SECRET_KEY": ambient}).wait(timeout=15) == 0
    assert scalar(engine, "SELECT count(*) FROM entities WHERE type='COUNTY'") == 47
    assert claims(engine) == (0, 1)


def test_empty_then_current_superseded_database_startup_keeps_readiness_and_provenance(owned_pg):
    engine, launch, _ = owned_pg
    assert scalar(engine, "SELECT count(*) FROM entities") == 0
    assert launch("startup").wait(timeout=15) == 0
    first = scalar(engine, "SELECT string_agg(id::text,',' ORDER BY id) FROM entities WHERE type='COUNTY'")
    assert scalar(engine, "SELECT count(*) FROM entities WHERE type='COUNTY'") == 47
    assert launch("startup").wait(timeout=15) == 0
    assert scalar(engine, "SELECT string_agg(id::text,',' ORDER BY id) FROM entities WHERE type='COUNTY'") == first
    assert scalar(engine, "SELECT count(*) FROM ingestion_jobs WHERE domain='bootstrap_reference_data' "
                  "AND metadata->>'source_fallback_reason'='fixture_superseded'") == 2
    assert scalar(engine, "SELECT count(*) FROM ingestion_jobs WHERE domain='bootstrap_reference_data' "
                  "AND metadata->'national_budget'->>'status'='completed'") == 2
    assert claims(engine) == (0, 2)
    assert scalar(engine, "SELECT count(*) FROM batch9_effects") == 2


@pytest.mark.parametrize("phase", ["before", "afterwrite", "outer_commit"])
def test_bootstrap_kill_retains_uncertain_claim_across_restart(owned_pg, phase):
    engine, launch, _ = owned_pg
    set_mode(engine, "afterwrite" if phase == "afterwrite" else "before")
    if phase == "outer_commit":
        set_mode(engine, "commit_gate")
    bootstrap = launch("weekly", extra={"BATCH9_BOOTSTRAP_COMMIT_GATE": "true"} if phase == "outer_commit" else None)
    stage = {"before": "entered", "afterwrite": "written", "outer_commit": "outer_committed"}[phase]
    wait_for(lambda: scalar(engine, f"SELECT count(*) FROM batch9_markers WHERE stage='{stage}'"), lambda x: x == 1)
    os.killpg(bootstrap.pid, signal.SIGKILL)
    bootstrap.wait(timeout=5)
    assert claims(engine) == (1, 0)
    set_mode(engine, "normal")
    assert launch("native", "--all", "--no-dry-run").wait(timeout=15) == 1
    assert launch("force").wait(timeout=15) == 0
    assert scalar(engine, "SELECT count(*) FROM batch9_markers WHERE stage='entered'") == 1
    assert claims(engine) == (1, 0)
    assert scalar(engine, "SELECT count(*) FROM batch9_effects") == (1 if phase == "outer_commit" else 0)


def test_bootstrap_connection_death_retains_claim_even_after_writer_commit(owned_pg):
    engine, launch, _ = owned_pg
    set_mode(engine, "before")
    bootstrap = launch("weekly")
    entered(engine)
    with engine.begin() as db:
        pids = db.scalars(text("SELECT DISTINCT pid FROM pg_locks WHERE locktype='advisory' AND granted "
                              "AND database=(SELECT oid FROM pg_database WHERE datname=current_database())")).all()
        assert len(pids) == 1
        assert db.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": pids[0]}) is True
    assert launch("native", "--all", "--no-dry-run").wait(timeout=15) == 1
    set_mode(engine, "normal")
    assert bootstrap.wait(timeout=15) != 0
    assert scalar(engine, "SELECT count(*) FROM batch9_effects") == 1
    assert claims(engine) == (1, 0)
    assert launch("native", "--domain", "national_budget").wait(timeout=15) == 1


@pytest.mark.parametrize("failure", ["failure", "errors"])
def test_failed_bootstrap_budget_rolls_back_budget_retains_claim_and_keeps_references(owned_pg, failure):
    engine, launch, _ = owned_pg
    set_mode(engine, failure)
    assert launch("weekly").wait(timeout=15) == 0
    assert claims(engine) == (1, 0)
    assert scalar(engine, "SELECT count(*) FROM batch9_effects") == 0
    assert scalar(engine, "SELECT count(*) FROM entities WHERE type='COUNTY'") == 47
    assert scalar(engine, "SELECT count(*) FROM ingestion_jobs WHERE domain='national_budget' AND status='FAILED'") == 1
    set_mode(engine, "normal")
    assert launch("native", "--all", "--no-dry-run").wait(timeout=15) == 1


def test_native_dry_run_excludes_bootstrap_and_rolls_back_before_next_owner(owned_pg):
    engine, launch, _ = owned_pg
    set_mode(engine, "before")
    native = launch("native", "--domain", "national_budget", "--dry-run")
    entered(engine)
    assert launch("force").wait(timeout=15) == 0
    assert scalar(engine, "SELECT count(*) FROM batch9_markers WHERE stage='entered'") == 1
    set_mode(engine, "normal")
    assert native.wait(timeout=15) == 0
    assert scalar(engine, "SELECT count(*) FROM batch9_effects") == 0
    assert claims(engine) == (0, 1)
    assert launch("weekly").wait(timeout=15) == 0
    assert scalar(engine, "SELECT count(*) FROM batch9_effects") == 1
    assert claims(engine) == (0, 2)
