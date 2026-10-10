"""Execute real interrupted CLI and startup; providers alone are inert."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
import select
import signal
import subprocess
import sys

from sqlalchemy import text
from database import engine, SessionLocal
from models import Base, IngestionJob, IngestionStatus
import bootstrap
import main

Base.metadata.create_all(engine)
mode = sys.argv[1]
effects = []


async def scheduler():
    effects.append("scheduler")


main._setup_etl_scheduler = scheduler


def snapshot():
    with engine.connect() as db:
        return {
            "tables": {t: db.scalar(text(f"SELECT count(*) FROM {t}")) for t in (
                "countries", "fiscal_periods", "entities", "gdp_data", "loans",
                "budget_lines", "source_documents", "economic_indicators", "poverty_indices")},
            "jobs": [list(map(str, r)) for r in db.execute(text(
                "SELECT id,domain,status,started_at,finished_at,metadata FROM ingestion_jobs ORDER BY id"))],
            "claims": [list(map(str, r)) for r in db.execute(text(
                "SELECT * FROM seeding_domain_claims ORDER BY id"))],
        }


def writer():
    child = subprocess.Popen(
        [sys.executable, "-m", "seeding.cli", "seed", "--domain", "audits", "--no-dry-run"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, start_new_session=True, env={k: os.environ[k] for k in (
            "PATH", "DATABASE_URL", "PYTHONPATH", "PYTHON_DOTENV_DISABLED",
            "PYTHONDONTWRITEBYTECODE", "BATCH11_BOOTSTRAP_INERT", "JWT_SECRET_KEY",
            "AUTO_SEEDER_ENABLED", "AUTO_WARMUP_ENABLED", "SEED_STORAGE_PATH")},
    )
    try:
        while True:
            if not select.select([child.stdout], [], [], 15)[0]:
                raise RuntimeError("Actual CLI entry barrier timed out")
            line = child.stdout.readline()
            print("WRITER_LOG", line.rstrip(), flush=True)
            if line.strip() == "WRITER_ENTERED":
                return child
            if not line:
                raise RuntimeError(f"Actual CLI exited before barrier: {child.wait(timeout=5)}")
    except BaseException:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
        raise


class ElapsedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime.now(tz) + (timedelta(hours=2) if
            sys._getframe(1).f_code.co_name == "_seed_run_in_flight" else timedelta())


child = None
try:
    if mode in {"bootstrap_block", "bootstrap_committed_block"}:
        def before_effect(*args, **kwargs):
            print("BOOTSTRAP_ENTERED", flush=True)
            if sys.stdin.readline().strip() != "complete":
                raise RuntimeError("Bootstrap barrier not released")
            return original(*args, **kwargs)
        if mode == "bootstrap_block":
            original = bootstrap._ensure_country
            bootstrap._ensure_country = before_effect
        else:
            from seeding.exclusion import DomainExecutionSet
            original = DomainExecutionSet.acknowledge
            DomainExecutionSet.acknowledge = before_effect
        bootstrap.initialize_reference_data()
        print("BOOTSTRAP_RETURNED", flush=True)
        raise SystemExit(0)
    if mode.startswith("retained") or mode == "completed" or mode == "active_ready":
        if mode == "active_ready":
            from services.county_identity import OFFICIAL_COUNTY_CODES
            from models import Country, Entity, EntityType
            with SessionLocal.begin() as db:
                country = Country(name="Kenya", iso_code="KEN", currency="KES", timezone="Africa/Nairobi", default_locale="en_KE")
                db.add(country)
                db.flush()
                for code, name in OFFICIAL_COUNTY_CODES.items():
                    db.add(Entity(country_id=country.id, canonical_name=name + " County", slug="owned-" + code, type=EntityType.COUNTY))
        child = writer()
        before = snapshot()
        if mode.startswith("retained"):
            os.killpg(child.pid, signal.SIGKILL)
            child.communicate(timeout=5)
            if child.returncode != -9 or snapshot() != before:
                raise RuntimeError("Interrupted CLI did not retain exact ownership")
        elif mode == "completed":
            output, _ = child.communicate("complete\n", timeout=15)
            print("WRITER_RETURN", child.returncode, output)
            if child.returncode != 0:
                raise RuntimeError("Actual CLI completion failed")
            before = snapshot()
    elif mode == "untagged":
        with SessionLocal.begin() as db:
            db.add(IngestionJob(domain="audits", status=IngestionStatus.RUNNING, dry_run=False,
                started_at=datetime.now(timezone.utc) - timedelta(days=365)))
        before = snapshot()
    elif mode == "schema_failure":
        with engine.begin() as db:
            db.execute(text("DROP INDEX uq_seeding_active_domain"))
        before = snapshot()
    elif mode == "query_failure":
        with engine.begin() as db:
            db.execute(text("ALTER TABLE ingestion_jobs RENAME TO inaccessible_jobs"))
        before = None
    else:
        before = snapshot()
    if mode in {"race", "race_force"}:
        original_probe = bootstrap._seed_run_in_flight
        def interleaving(db):
            global child, before
            verdict = original_probe(db)
            if verdict is not None:
                raise RuntimeError("Race fixture initial probe was not empty")
            # This query forces a physical PG transaction for the initial probe.
            print("INITIAL_PROBE_XID", db.scalar(text("SELECT txid_current()")), flush=True)
            child = writer()
            before = snapshot()
            return verdict
        bootstrap._seed_run_in_flight = interleaving
        if mode == "race_force":
            original_initialize = main.initialize_reference_data
            main.initialize_reference_data = lambda: original_initialize(force=True)
    if mode in {"retained_stale", "restart_stale"}:
        bootstrap.datetime = ElapsedClock
    asyncio.run(main._startup_sequence())
    after = snapshot() if mode != "query_failure" else None
    result = dict(mode=mode, before=before, after=after, ready=main._app_ready.is_set(),
        reason=main._app_readiness_reason, startup_effects=effects,
        writer_exit=child.returncode if child else None)
    print("ADMISSION_RESULT " + json.dumps(result), flush=True)
finally:
    if child is not None and child.poll() is None:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=5)
    engine.dispose()
