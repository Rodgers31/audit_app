"""Independent inert execution checks; no author fixtures or shared-table writes."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

import dotenv
dotenv.load_dotenv = lambda *a, **k: False
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
import sqlalchemy
from models import (Base, AdminAuditLog, EtlDispatchCommand, EtlDispatchDomain,
                    EtlDispatchWorker, IngestionJob, IngestionStatus, SeedingDomainClaim)
from seeding import cli
from seeding.config import SeedingSettings
from seeding.registries import DomainRegistry
from seeding.types import DomainRunResult
from seeding.exclusion import (DomainExecution, DomainOwnershipError, clock,
                               dispatch_scope, enter_domain, reserve, terminal_observation)
from admin_etl_dispatch_worker import finish

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "batch8_adversarial_" + uuid4().hex
SCHEMAS = [SCHEMA]
URL = "postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55485/batch7_etl_worker"
admin = create_engine(URL)
with admin.begin() as conn:
    conn.execute(text("CREATE SCHEMA " + SCHEMA))
engine = create_engine(URL, connect_args={"options": "-csearch_path=" + SCHEMA})
factory = sessionmaker(bind=engine)
ENGINES = [engine]
Base.metadata.create_all(engine, tables=[AdminAuditLog.__table__, IngestionJob.__table__,
    EtlDispatchCommand.__table__, EtlDispatchDomain.__table__, EtlDispatchWorker.__table__,
    SeedingDomainClaim.__table__])
with engine.begin() as conn:
    conn.execute(text("CREATE TABLE inert_effects(id bigserial PRIMARY KEY, label text NOT NULL)"))
cli.SessionLocal = factory
cli.REGISTRY = DomainRegistry()
cli.load_builtin_domains = lambda: None
settings = SeedingSettings(log_path=None, log_level="ERROR", total_timeout_seconds=0)
results = []

def record(name, expected, actual, **details):
    result = {"name": name, "expected": expected, "actual": actual,
              "passed": expected == actual, **details}
    results.append(result)
    print(json.dumps(result, default=str), flush=True)

def effects():
    with engine.connect() as conn:
        return conn.scalar(text("SELECT count(*) FROM inert_effects"))

def handler(*, session, settings, context):
    session.execute(text("INSERT INTO inert_effects(label) VALUES ('inert')"))
    return DomainRunResult(domain="audits", items_processed=1, items_created=1,
                           dry_run=context.dry_run)

cli.REGISTRY.register("audits", handler)

def run(dry=False, **extra):
    args = argparse.Namespace(domain=["audits"], all=False, since=None,
                              dry_run=dry, audits_source_manifest=None,
                              audits_observe_listing=False, **extra)
    return cli.run_seed_command(args, settings)

def native_claim(domain="audits"):
    identity = uuid4()
    with factory.begin() as db:
        assert reserve(db, domain, identity)
    return identity

def job_for(identity, domain="audits", **values):
    now = datetime.now(timezone.utc)
    fields = dict(domain=domain, status=IngestionStatus.COMPLETED, dry_run=False,
                  started_at=now, finished_at=now, items_processed=1,
                  items_created=1, items_updated=0, errors=[],
                  meta={"seeding_claim_id": str(identity)})
    fields.update(values)
    with factory.begin() as db:
        job = IngestionJob(**fields)
        db.add(job)
        db.flush()
        return job.id

def active(identity):
    with factory() as db:
        row = db.get(SeedingDomainClaim, identity)
        return row.released_at is None

def acknowledge_outcome(execution, job_id):
    try:
        execution.acknowledge(job_id)
        return "accepted"
    except Exception as exc:
        return type(exc).__name__

def new_scenario(label):
    global engine, factory
    schema = "batch8_adversarial_" + label + "_" + uuid4().hex
    SCHEMAS.append(schema)
    with admin.begin() as conn:
        conn.execute(text("CREATE SCHEMA " + schema))
    engine = create_engine(URL, connect_args={"options": "-csearch_path=" + schema})
    ENGINES.append(engine)
    factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine, tables=[AdminAuditLog.__table__, IngestionJob.__table__,
        EtlDispatchCommand.__table__, EtlDispatchDomain.__table__, EtlDispatchWorker.__table__,
        SeedingDomainClaim.__table__])
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE inert_effects(id bigserial PRIMARY KEY, label text NOT NULL)"))
    cli.SessionLocal = factory
    (Path(__file__).parent / "schema.txt").write_text("\n".join(SCHEMAS) + "\n")

def make_dispatch():
    generation, command_id, token = uuid4(), uuid4(), uuid4()
    with factory.begin() as db:
        now = clock(db)
        audit = AdminAuditLog(actor_id="inert", action="etl.trigger", payload={})
        db.add(audit); db.flush()
        db.add(EtlDispatchWorker(id=1, generation=generation, ready=True,
                                last_seen_at=now, expires_at=now+timedelta(minutes=10)))
        db.add(EtlDispatchCommand(id=command_id, actor_id="inert", idempotency_key=uuid4(),
            source="oag", domain="audits", dry_run=False, generation=generation,
            claim_token=token, execution_started=True, status="running", version=2,
            created_at=now, updated_at=now, started_at=now, audit_id=audit.id))
        db.flush()
        db.add(EtlDispatchDomain(domain="audits", command_id=command_id, claim_token=token))
        assert reserve(db, "audits", token, command_id)
    return generation, command_id, token

print(json.dumps({"schema": SCHEMA, "python": platform.python_version(),
                  "sqlalchemy": sqlalchemy.__version__, "platform": platform.platform(),
                  "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  "tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip()}), flush=True)
(Path(__file__).parent / "schema.txt").write_text(SCHEMA + "\n")

# Actual native runner positive controls; no exclusion seam is patched.
code = run()
record("actual_native_positive", [0, 1], [code, effects()])
code = run(dry=True)
record("actual_native_dry_run_rolls_back", [0, 1], [code, effects()])

# Direct reserve rejects malformed request shapes before persistence.
bad = [None, True, False, 0, -1, float("nan"), float("inf"), [], {}, "", "x" * 101]
for value in bad:
    try:
        with factory.begin() as db:
            accepted = reserve(db, value, uuid4())
        outcome = "accepted" if accepted else "rejected"
    except Exception as exc:
        outcome = type(exc).__name__
    record("reserve_domain_" + repr(value), "DomainOwnershipError", outcome)
for value in bad + ["00000000-0000-0000-0000-000000000000"]:
    try:
        with factory.begin() as db:
            accepted = reserve(db, "shape_" + uuid4().hex, value)
        outcome = "accepted" if accepted else "rejected"
    except Exception as exc:
        outcome = type(exc).__name__
    record("reserve_identity_" + repr(value), "DomainOwnershipError", outcome)

# Hostile receipt inputs against real ORM records and direct helper calls.
identity = native_claim("shape_receipts")
job_id = job_for(identity, "shape_receipts")
with factory() as db:
    claim_row = db.get(SeedingDomainClaim, identity)
    for value in bad + ["1", 2147483647]:
        try:
            output = terminal_observation(db, claim_row, value)
            verdict = output is not None
        except Exception:
            verdict = False
        record("terminal_job_id_" + repr(value), False, verdict)
    record("terminal_valid_positive", True, terminal_observation(db, claim_row, job_id) is not None)
    job = db.get(IngestionJob, job_id)
    for errors in (None, {}, "", True, ["unexpected"]):
        job.errors = errors
        with db.no_autoflush:
            record("terminal_completed_errors_" + repr(errors), False,
                   terminal_observation(db, claim_row, job_id) is not None)
    db.rollback()
    job = db.get(IngestionJob, job_id)
    for metadata in (None, {}, [], {"seeding_claim_id": str(uuid4())}):
        job.meta = metadata
        with db.no_autoflush:
            record("terminal_metadata_" + repr(metadata), False,
                   terminal_observation(db, claim_row, job_id) is not None)
    db.rollback()
    for value in (None, True, False, float("nan"), float("inf"), -1, 2147483648, [], {}, "1"):
        job = db.get(IngestionJob, job_id)
        job.items_processed = value
        with db.no_autoflush:
            record("terminal_items_processed_" + repr(value), False,
                   terminal_observation(db, claim_row, job_id) is not None)
        db.rollback()

# Retained claim baseline must deny the actual CLI without handler entry.
orphan = native_claim()
before = effects()
code = run(dispatch_claim_token=str(orphan), skip_ownership=True)
record("flags_cannot_impersonate_retained_claim", [1, before, True],
       [code, effects(), active(orphan)])
with factory.begin() as db:
    record("duplicate_reserve_rejected", False, reserve(db, "audits", uuid4()))

# An uncorrelated scope must not substitute for authenticated adapter ownership.
# This uses a retained NATIVE claim, never calls execute(), and never marks a
# command execution_started. It should be refused before entering the handler.
execution = DomainExecution(factory, "audits", orphan)
try:
    execution.open()
    try:
        with dispatch_scope(execution):
            code = run()
    except DomainOwnershipError:
        code = 1
    record("uncorrelated_native_scope_cannot_run", [1, before, True],
           [code, effects(), active(orphan)],
           call="DomainExecution(factory,'audits',retained_native_id).open(); with dispatch_scope(execution): cli.run_seed_command(args, settings)")
finally:
    execution.close()

# Unknown scope shapes must fail before any handler starts.
for value in (True, {}, [], SimpleNamespace(engine=engine, domain="audits", entered=False)):
    before_shape = effects()
    try:
        with dispatch_scope(value):
            code = run()
    except Exception:
        code = 1
    record("malformed_scope_" + repr(value), [1, before_shape], [code, effects()])

# A live lock for B does not prove continuity for retained writer A. A direct
# acknowledgement must bind the object's domain/entry to the durable claim.
other = native_claim("retained_domain_a")
receipt_id = job_for(other, "retained_domain_a")
execution = DomainExecution(factory, "unrelated_domain_b", other)
try:
    execution.open()
    outcome = acknowledge_outcome(execution, receipt_id)
    record("wrong_domain_acknowledge_cannot_release", ["DomainOwnershipError", True],
           [outcome, active(other)], entered=execution.entered,
           call="DomainExecution(factory,'unrelated_domain_b',retained_A_id).open(); execution.acknowledge(A_terminal_job_id)")
finally:
    execution.close()

# Independent schema ensures prior native retained claims remain undisturbed.
new_scenario("finish")
# A forged terminal observation alone must never certify a dispatch child return.
generation, command_id, token = make_dispatch()
fake_job = job_for(token, meta={"seeding_claim_id": str(token),
    "dispatch_command_id": str(command_id), "dispatch_claim_token": str(token)})
outcome = finish(factory, generation, command_id, token, 0)
with factory() as db:
    command = db.get(EtlDispatchCommand, command_id)
    record("fake_terminal_without_return_rejected", [False, "interrupted", True],
           [outcome, command.status, active(token)])

for exit_code in (None, True, False, float("nan"), float("inf"), "0", {}, []):
    with factory.begin() as db:
        command = db.get(EtlDispatchCommand, command_id)
        command.status = "running"; command.finished_at = None; command.outcome = None
    try:
        output = finish(factory, generation, command_id, token, exit_code)
    except Exception:
        output = False
    record("finish_bad_exit_code_" + repr(exit_code), [False, True], [output, active(token)])
for wrong_generation, wrong_id, wrong_token in ((uuid4(), command_id, token),
        (generation, uuid4(), token), (generation, command_id, uuid4())):
    record("finish_stale_correlation", [False, True],
           [finish(factory, wrong_generation, wrong_id, wrong_token, 0), active(token)])

# Positive adapter + native entry + supervisor return. Real adapter supplies its
# own correlation listener; the inert handler/registry remain the only replacements.
new_scenario("adapter")
generation, command_id, token = make_dispatch()
with factory.begin() as db:
    db.get(EtlDispatchCommand, command_id).execution_started = False
os.environ["ADMIN_ETL_DISPATCH_ENABLED"] = "true"
from admin_etl_dispatch_adapter import execute
for bad_id in (None, True, "", str(command_id), float("nan"), float("inf"), {}, []):
    record("adapter_bad_command_id_" + repr(bad_id), [1, 0],
           [execute(factory, engine, bad_id, token, generation), effects()])
record("adapter_wrong_correlation", [1, 0],
       [execute(factory, engine, command_id, uuid4(), generation), effects()])
record("adapter_positive", [0, 1, True],
       [execute(factory, engine, command_id, token, generation), effects(), active(token)])
record("duplicate_adapter_rejected", [1, 1, True],
       [execute(factory, engine, command_id, token, generation), effects(), active(token)])
record("supervisor_positive_finish", [True, False],
       [finish(factory, generation, command_id, token, 0), active(token)])
record("next_native_after_dispatch_normal_return", [0, 2], [run(), effects()])

# Loss of only our own advisory-lock connection must retain authority, even
# after a coherent inert terminal observation is present.
new_scenario("lockloss")
execution = enter_domain(factory, "audits")
receipt_id = job_for(execution.identity)
with admin.begin() as conn:
    terminated = conn.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": execution.pid})
record("owned_lock_connection_terminated", True, terminated)
try:
    outcome = acknowledge_outcome(execution, receipt_id)
    record("lost_lock_acknowledge_rejected", [True, True],
           [outcome != "accepted", active(execution.identity)], observed_exception=outcome)
    record("lost_lock_blocks_next_native", [1, 0, True],
           [run(), effects(), active(execution.identity)])
finally:
    execution.close()

new_scenario("uncertain")
execution = enter_domain(factory, "audits")
receipt_id = job_for(execution.identity)
execution.uncertain = True
try:
    record("uncertainty_acknowledge_rejected", ["DomainOwnershipError", True],
           [acknowledge_outcome(execution, receipt_id), active(execution.identity)])
finally:
    execution.close()
record("uncertainty_blocks_next_native", [1, 0, True],
       [run(), effects(), active(execution.identity)])

new_scenario("lease")
generation, command_id, token = make_dispatch()
with factory.begin() as db:
    db.get(EtlDispatchCommand, command_id).execution_started = False
record("adapter_before_lease_loss", [0, 1],
       [execute(factory, engine, command_id, token, generation), effects()])
with factory.begin() as db:
    now = clock(db)
    worker = db.get(EtlDispatchWorker, 1)
    worker.last_seen_at = now-timedelta(seconds=2)
    worker.expires_at = now-timedelta(seconds=1)
record("stale_lease_cannot_finish_or_release", [False, True],
       [finish(factory, generation, command_id, token, 0), active(token)])
record("stale_lease_retains_native_exclusion", [1, 1, True],
       [run(), effects(), active(token)])

summary = {"schemas": SCHEMAS, "checks": len(results),
           "passed": sum(r["passed"] for r in results),
           "failed": sum(not r["passed"] for r in results), "results": results}
(Path(__file__).parent / "results.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
print(json.dumps({k:v for k,v in summary.items() if k != "results"}), flush=True)
for owned_engine in ENGINES:
    owned_engine.dispose()
admin.dispose()
sys.exit(1 if summary["failed"] else 0)
