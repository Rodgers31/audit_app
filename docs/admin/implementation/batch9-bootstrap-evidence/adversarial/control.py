"""Independent executable controls for bootstrap ownership; no remote sources."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import traceback
from uuid import uuid4

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "backend/tests/batch9_bootstrap_fixture"))
from owned_database import owned_engine, owned_url, schema_url

BASE_URL = os.environ.get("BATCH9_BOOTSTRAP_POSTGRES_URL", "postgresql+psycopg2://batch9_bootstrap:batch9-inert-local@127.0.0.1:55492/batch9-bootstrap-1183")


def inert_env(url):
    return {"PATH": os.environ["PATH"], "PYTHONPATH": str(ROOT / "backend"),
            "PYTHON_DOTENV_DISABLED": "1", "PYTHONDONTWRITEBYTECODE": "1",
            "DATABASE_URL": url, "AUTO_SEEDER_ENABLED": "false",
            "AUTO_WARMUP_ENABLED": "false", "ENABLE_ETL_SCHEDULER": "false",
            "JWT_SECRET_KEY": "batch9-adversarial-inert-key"}


def child(mode):
    # Guard before importing any product entry point. Psycopg2 uses its own
    # transport; its URL is separately checked and supplied by this driver.
    target = owned_url(os.environ["DATABASE_URL"], allow_schema=True)
    original = socket.socket.connect

    def local_only(sock, address):
        if not isinstance(address, tuple) or address[:2] != ("127.0.0.1", target.port):
            raise RuntimeError("Adversarial fixture forbids external transport")
        return original(sock, address)

    socket.socket.connect = local_only
    import sqlalchemy
    sqlalchemy.create_engine = lambda url, **kwargs: owned_engine(url, allow_schema=True, **kwargs)
    from sqlalchemy import event, text
    from sqlalchemy.orm import sessionmaker
    import bootstrap
    import database
    from seeding.exclusion import DomainExecution, DomainOwnershipError
    from seeding.registries import REGISTRY, load_builtin_domains
    from seeding.types import DomainRunResult

    load_builtin_domains()
    REGISTRY._handlers.clear()

    def handler(session, settings, context):
        assert settings.live_pdf_fetch_enabled is False
        assert context.dry_run is False and type(context.job_id) is int
        session.execute(text("DELETE FROM budget_lines"))
        session.execute(text("INSERT INTO adversarial_effects VALUES ('budget-write')"))
        valid = dict(domain="national_budget", dry_run=False, items_processed=1,
                     items_created=1, items_updated=0, errors=[], metadata={})
        if mode == "none":
            return None
        if mode == "empty_dict":
            return {}
        if mode == "truthy_failure":
            return type("Failure", (), {"success": False})()
        if mode == "exception":
            raise RuntimeError("inert failure after destructive write")
        changes = {
            "bool_count": {"items_processed": True},
            "negative_count": {"items_created": -1},
            "overflow_count": {"items_updated": 2147483648},
            "nan_count": {"items_processed": float("nan")},
            "inf_count": {"items_processed": float("inf")},
            "wrong_domain": {"domain": "audits"},
            "dry_run": {"dry_run": True},
            "string_dry_run": {"dry_run": "false"},
            "errors": {"errors": ["inert returned failure"]},
            "errors_shape": {"errors": "failure"},
            "metadata_none": {"metadata": None},
        }
        if mode in changes:
            return DomainRunResult.model_construct(**(valid | changes[mode]))
        return DomainRunResult(**valid)

    REGISTRY.register("national_budget", handler)

    if mode == "reference_failure":
        real = bootstrap._seed_national_data

        def failure(session, **kwargs):
            real(session, **kwargs)
            raise RuntimeError("inert reference error before budget handler")

        bootstrap._seed_national_data = failure

    connection = None
    if mode == "factory_connection":
        connection = database.engine.connect()
        bootstrap.SessionLocal = sessionmaker(bind=connection)

    if mode == "invalid_then_valid":
        real_ack = DomainExecution.acknowledge

        def acknowledge(self, job_id):
            try:
                real_ack(self, -1)
            except DomainOwnershipError:
                print("CONTROL_INVALID_RECEIPT_REJECTED", flush=True)
            else:
                raise AssertionError("Invalid receipt was accepted")
            assert self.continuous(), "Invalid receipt ended continuity transaction"
            real_ack(self, job_id)
            print("CONTROL_VALID_RECEIPT_ACCEPTED", flush=True)

        DomainExecution.acknowledge = acknowledge

    def terminate_owned(pid):
        admin = owned_engine(os.environ["DATABASE_URL"], allow_schema=True)
        with admin.begin() as db:
            assert db.scalar(text("SELECT count(*) FROM pg_stat_activity "
                                  "WHERE pid=:pid AND datname=current_database()"), {"pid": pid}) == 1
            assert db.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}) is True
        admin.dispose()
        print("CONTROL_TERMINATED_OWNED_BACKEND", pid, flush=True)

    if mode == "loss_after_proof":
        real_continuous = DomainExecution.continuous
        calls = 0

        def continuous(self):
            nonlocal calls
            value = real_continuous(self)
            calls += 1
            # open(), bootstrap helper, acknowledge() prove the same backend.
            if calls == 3 and value:
                terminate_owned(self.pid)
            return value

        DomainExecution.continuous = continuous

    if mode == "loss_during_release":
        @event.listens_for(database.engine, "after_cursor_execute")
        def after_release(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().startswith("UPDATE seeding_domain_claims SET") and "returned_at" in statement:
                pid = conn.scalar(text("SELECT pg_backend_pid()"))
                terminate_owned(pid)

    try:
        bootstrap.initialize_reference_data(force=True)
    finally:
        if connection is not None:
            connection.close()
        database.engine.dispose()


def snapshot(engine):
    from sqlalchemy import text
    with engine.connect() as db:
        return {
            "active_claims": db.scalar(text("SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NULL")),
            "released_claims": db.scalar(text("SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NOT NULL")),
            "budget_effects": db.scalar(text("SELECT count(*) FROM adversarial_effects")),
            "sentinel_budget_rows": db.scalar(text("SELECT count(*) FROM budget_lines WHERE category='adversarial-sentinel'")),
            "county_entities": db.scalar(text("SELECT count(*) FROM entities WHERE type='COUNTY'")),
            "national_jobs": [dict(r._mapping) for r in db.execute(text(
                "SELECT status, items_processed, metadata, errors FROM ingestion_jobs WHERE domain='national_budget' ORDER BY id"))],
            "bootstrap_jobs": [dict(r._mapping) for r in db.execute(text(
                "SELECT status, metadata FROM ingestion_jobs WHERE domain='bootstrap_reference_data' ORDER BY id"))],
        }


def provision(engine, mode):
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from models import (Base, BudgetLine, Country, DocumentType, Entity, EntityType,
                        FiscalPeriod, IngestionJob, IngestionStatus, SourceDocument)
    Base.metadata.create_all(engine)
    with engine.begin() as db:
        db.execute(text("CREATE TABLE adversarial_effects(effect text NOT NULL)"))
    with Session(engine) as db:
        country = Country(iso_code="ADV", name="Inert adversarial fixture", currency="KES",
                          timezone="UTC", default_locale="en")
        db.add(country)
        db.flush()
        entity = Entity(country_id=country.id, type=EntityType.NATIONAL,
                        canonical_name="Inert sentinel", slug="inert-adversarial-sentinel")
        period = FiscalPeriod(country_id=country.id, label="INERT",
                              start_date=datetime(2000, 1, 1), end_date=datetime(2000, 12, 31))
        document = SourceDocument(country_id=country.id, publisher="Owned inert control",
                                  title="Owned inert control", fetch_date=datetime(2000, 1, 1),
                                  doc_type=DocumentType.BUDGET)
        db.add_all([entity, period, document])
        db.flush()
        db.add(BudgetLine(entity_id=entity.id, period_id=period.id,
                          source_document_id=document.id, category="adversarial-sentinel", currency="KES"))
        if mode == "legacy_running":
            db.add(IngestionJob(domain="national_budget", status=IngestionStatus.RUNNING,
                                started_at=datetime.now(timezone.utc) - timedelta(days=365), meta={}))
        db.commit()


def run(name):
    assert name.replace("-", "").isalnum()
    output_path, receipt_path = HERE / f"{name}.txt", HERE / f"{name}.json"
    assert not output_path.exists() and not receipt_path.exists(), "Append-only receipts"
    os.environ.update(inert_env(BASE_URL))
    sys.path.insert(0, str(ROOT / "backend"))
    import pydantic
    import sqlalchemy
    from sqlalchemy import text

    info = {
        "generated_by": str(Path(__file__).relative_to(ROOT)),
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, str(Path(__file__)), "--run", name],
        "cwd": str(ROOT), "runtime": {"python": platform.python_version(),
                                        "sqlalchemy": sqlalchemy.__version__, "pydantic": pydantic.__version__},
        "target_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in [ROOT / "backend/bootstrap.py", ROOT / "backend/seeding/exclusion.py",
                                    ROOT / "backend/seeding/types.py"]},
        "cases": [], "limitations": ["Local owned PostgreSQL only; no hosted CI or production claim.",
            "Registry handler is intentionally inert; bootstrap and claim/release paths are actual product code."]}
    admin = owned_engine(BASE_URL, isolation_level="AUTOCOMMIT")
    owned_name = owned_url(BASE_URL).database + "-a-" + uuid4().hex[:12]
    db_created = False
    failure = None
    with output_path.open("w") as log:
        log.write(json.dumps(info, indent=2) + "\n")
        log.flush()
        try:
            with admin.connect() as db:
                db.execute(text(f'CREATE DATABASE "{owned_name}"'))
            db_created = True
            database_url = str(owned_url(BASE_URL).set(database=owned_name).render_as_string(hide_password=False))
            info["owned_database"] = owned_name
            modes = ["normal", "none", "empty_dict", "truthy_failure", "exception", "bool_count",
                     "negative_count", "overflow_count", "nan_count", "inf_count", "wrong_domain",
                     "dry_run", "string_dry_run", "errors", "errors_shape", "metadata_none",
                     "reference_failure", "legacy_running", "factory_connection", "invalid_then_valid",
                     "loss_after_proof", "loss_during_release"]
            for mode in modes:
                schema = "adversarial_" + uuid4().hex
                owner = owned_engine(database_url)
                with owner.begin() as db:
                    db.execute(text(f'CREATE SCHEMA "{schema}"'))
                url = schema_url(database_url, schema).render_as_string(hide_password=False)
                engine = owned_engine(url, allow_schema=True)
                try:
                    provision(engine, mode)
                    command = [sys.executable, str(Path(__file__)), "--child", mode]
                    env = inert_env(url)
                    log.write(f"\nCASE {mode}\nCOMMAND {json.dumps(command)}\nENV {json.dumps(env)}\n")
                    log.flush()
                    proc = subprocess.run(command, cwd=ROOT / "backend", env=env,
                                          stdout=log, stderr=subprocess.STDOUT, timeout=30)
                    state = snapshot(engine)
                    case = {"mode": mode, "command": command, "environment": env,
                            "exit_code": proc.returncode, "state": state}
                    if mode in {"normal", "factory_connection", "invalid_then_valid"}:
                        expected = {"exit_code": 0, "active_claims": 0, "released_claims": 1,
                                    "budget_effects": 1, "sentinel_budget_rows": 0, "county_entities": 47}
                    elif mode in {"loss_after_proof", "loss_during_release"}:
                        expected = {"active_claims": 1, "released_claims": 0, "budget_effects": 1,
                                    "sentinel_budget_rows": 0, "county_entities": 47}
                        assert proc.returncode != 0, case
                    elif mode == "reference_failure":
                        expected = {"active_claims": 1, "released_claims": 0, "budget_effects": 0,
                                    "sentinel_budget_rows": 1, "county_entities": 0}
                        assert proc.returncode != 0, case
                    elif mode == "legacy_running":
                        expected = {"exit_code": 0, "active_claims": 0, "released_claims": 0,
                                    "budget_effects": 0, "sentinel_budget_rows": 1, "county_entities": 47}
                    else:
                        expected = {"exit_code": 0, "active_claims": 1, "released_claims": 0,
                                    "budget_effects": 0, "sentinel_budget_rows": 1, "county_entities": 47}
                    observed = state | {"exit_code": proc.returncode}
                    case["expected"] = expected
                    case["passed"] = all(observed[k] == v for k, v in expected.items())
                    if mode not in {"normal", "factory_connection", "invalid_then_valid", "reference_failure",
                                    "legacy_running", "loss_after_proof", "loss_during_release"}:
                        case["passed"] &= state["national_jobs"][0]["status"] == "FAILED"
                        case["passed"] &= state["national_jobs"][0]["metadata"].get("ownership_retained") is True
                    info["cases"].append(case)
                    log.write("RESULT " + json.dumps(case, sort_keys=True) + "\n")
                    log.flush()
                finally:
                    engine.dispose()
                    with owner.begin() as db:
                        db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
                    owner.dispose()
        except BaseException as exc:
            failure = repr(exc)
            traceback.print_exc(file=log)
        finally:
            if db_created:
                with admin.connect() as db:
                    count = db.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=:name"), {"name": owned_name})
                    assert count == 0, f"Owned processes remain in {owned_name}: {count}"
                    db.execute(text(f'DROP DATABASE "{owned_name}"'))
            admin.dispose()
    info["setup_error"] = failure
    info["passed"] = sum(bool(c["passed"]) for c in info["cases"])
    info["failed"] = sum(not c["passed"] for c in info["cases"])
    info["skipped"] = 0
    info["exit_code"] = 0 if failure is None and info["failed"] == 0 and len(info["cases"]) == 22 else 1
    info["verdict"] = "PASSED" if info["exit_code"] == 0 else "FAILED"
    info["output_sha256"] = hashlib.sha256(output_path.read_bytes()).hexdigest()
    receipt_path.write_text(json.dumps(info, indent=2) + "\n")
    check = json.loads(receipt_path.read_text())
    assert check["generator_sha256"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    assert check["exit_code"] == info["exit_code"] and check["cases"] == info["cases"]
    print(json.dumps({"receipt": str(receipt_path), "verdict": check["verdict"],
                      "passed": check["passed"], "failed": check["failed"], "setup_error": failure}))
    raise SystemExit(info["exit_code"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run")
    parser.add_argument("--child")
    args = parser.parse_args()
    if args.child:
        child(args.child)
    else:
        run(args.run)
