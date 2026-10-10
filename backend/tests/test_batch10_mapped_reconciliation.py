"""Real fenced PostgreSQL reconciliation for every retained dispatch mapping."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from admin_etl_dispatch import SOURCE_DOMAINS, TriggerBody, accept
from admin_etl_dispatch_worker import claim, register_worker
from models import IngestionJob, IngestionStatus
from seeding.exclusion import DomainExecution, dispatch_scope, enter_domain
from seeding.reconciliation import ReconciliationRefused, apply_plan, make_plan
from seeding.registries import REGISTRY, load_builtin_domains
from test_batch9_reconciliation import owned, read, resign, signed

MAPPINGS = tuple(SOURCE_DOMAINS.items())
NEW_MAPPINGS = tuple(pair for pair in MAPPINGS if pair[0] != "oag")
TABLES = ("admin_audit_log", "seeding_domain_claims", "etl_dispatch_commands",
          "etl_dispatch_domains", "ingestion_jobs")


@pytest.fixture(autouse=True)
def inert_registry(monkeypatch):
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "true")
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_SOURCES", ",".join(SOURCE_DOMAINS))
    def forbidden(*args, **kwargs):
        raise AssertionError("Reconciliation fixture must never execute a financial handler")
    load_builtin_domains()
    monkeypatch.setattr(REGISTRY, "_handlers", {domain: forbidden for domain in SOURCE_DOMAINS.values()})


def retained(db, source, domain, dry_run=False, generation=None):
    generation = generation or register_worker(db.factory)
    with db.factory() as session:
        accepted = accept(session, SimpleNamespace(id="operator", email="owned@example.invalid"), source,
                          TriggerBody(dispatch_generation=str(generation), dry_run=dry_run), str(uuid4()))
    command_id, token = claim(db.factory, generation)
    assert command_id == accepted.command.id
    with db.factory.begin() as session:
        session.execute(text("UPDATE etl_dispatch_commands SET execution_started=true WHERE id=:id"), {"id": command_id})
    execution = DomainExecution(db.factory, domain, token, command_id, generation)
    execution.open()
    try:
        with dispatch_scope(execution):
            assert enter_domain(db.factory, domain, dry_run) is execution
        with db.factory.begin() as session:
            session.add(IngestionJob(domain=domain, dry_run=dry_run, status=IngestionStatus.RUNNING,
                started_at=datetime.now(timezone.utc), errors=["original retained observation"],
                meta={"seeding_claim_id": str(token), "dispatch_command_id": str(command_id),
                      "dispatch_claim_token": str(token), "original": "preserved"}))
    finally:
        execution.close()
    return {"domain": domain, "claim_id": str(token), "legacy_job_ids": []}, generation


def stop(db):
    with db.factory.begin() as session:
        session.execute(text("UPDATE etl_dispatch_worker SET ready=false"))


def rows(db):
    return {name: read(db, "SELECT * FROM " + name + " ORDER BY 1") for name in TABLES}


@pytest.mark.parametrize("source,domain", MAPPINGS)
@pytest.mark.parametrize("dry_run", [False, True])
def test_mapped_retained_owner_reconciles_atomically_and_allows_successor(owned, source, domain, dry_run):
    selected, generation = retained(owned, source, domain, dry_run)
    # A separately retained domain must survive release of the selected owner.
    other_source, other_domain = next(pair for pair in MAPPINGS if pair[1] != domain)
    other, _ = retained(owned, other_source, other_domain, generation=generation)
    stop(owned)
    before = rows(owned)
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    assert rows(owned) == before  # Planning cannot release ownership.
    assert apply_plan(owned.connection, policy, evidence, plan)["status"] == "applied"
    after = rows(owned)
    selected_claim = next(row for row in after["seeding_domain_claims"] if str(row["id"]) == selected["claim_id"])
    assert selected_claim["released_at"] and selected_claim["reconciled_by"] == "operator"
    original_claim = next(row for row in before["seeding_domain_claims"] if row["id"] == selected_claim["id"])
    for field in ("id", "domain", "kind", "command_id", "acquired_at", "entered_at", "entry_id", "returned_at", "job_id"):
        assert selected_claim[field] == original_claim[field]
    selected_domain = next(row for row in after["etl_dispatch_domains"] if row["domain"] == domain)
    assert selected_domain["command_id"] is None and selected_domain["claim_token"] is None
    command = next(row for row in after["etl_dispatch_commands"] if row["id"] == original_claim["command_id"])
    assert command["status"] == "interrupted" and command["outcome"] == "execution_unverified"
    job = next(row for row in after["ingestion_jobs"] if row["domain"] == domain)
    assert job["status"] == "FAILED" and job["metadata"]["original"] == "preserved"
    assert job["metadata"]["seeding_claim_id"] == selected["claim_id"]
    assert job["errors"][0] == "original retained observation"
    assert next(row for row in after["seeding_domain_claims"] if str(row["id"]) == other["claim_id"])["released_at"] is None
    for table, predicate in (("etl_dispatch_domains", lambda r: r["domain"] == other_domain),
                             ("etl_dispatch_commands", lambda r: r["id"] != command["id"]),
                             ("ingestion_jobs", lambda r: r["domain"] == other_domain)):
        assert [row for row in after[table] if predicate(row)] == [row for row in before[table] if predicate(row)]
    assert len(after["admin_audit_log"]) == len(before["admin_audit_log"]) + 1
    owned.admission(True)
    new_generation = register_worker(owned.factory)
    with owned.factory() as session:
        successor = accept(session, SimpleNamespace(id="operator", email="owned@example.invalid"), source,
                           TriggerBody(dispatch_generation=str(new_generation)), str(uuid4()))
    successor_id, successor_token = claim(owned.factory, new_generation)
    assert successor_id == successor.command.id and str(successor_token) != selected["claim_id"]


@pytest.mark.parametrize("source,domain", NEW_MAPPINGS)
@pytest.mark.parametrize("table", TABLES)
def test_mapped_release_failure_rolls_back_every_owned_row(owned, source, domain, table):
    selected, _ = retained(owned, source, domain)
    stop(owned)
    before = rows(owned)
    with owned.connection.begin():
        owned.connection.execute(text("CREATE FUNCTION batch10_reject_release() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'owned mapped rollback control'; END $$"))
        event = "INSERT" if table == "admin_audit_log" else "UPDATE"
        owned.connection.execute(text(f"CREATE TRIGGER batch10_reject_release BEFORE {event} ON {table} FOR EACH ROW EXECUTE FUNCTION batch10_reject_release()"))
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    with pytest.raises(DBAPIError, match="owned mapped rollback control"):
        apply_plan(owned.connection, policy, evidence, plan)
    assert rows(owned) == before


@pytest.mark.parametrize("source,domain", NEW_MAPPINGS)
@pytest.mark.parametrize("mutation", ["domain_token", "command_token", "missing_domain", "job_token", "job_dry_run", "source_domain"])
def test_mapped_correlation_refusal_preserves_retained_ownership(owned, source, domain, mutation):
    selected, _ = retained(owned, source, domain)
    stop(owned)
    with owned.connection.begin():
        if mutation == "domain_token":
            owned.connection.execute(text("UPDATE etl_dispatch_domains SET claim_token=:token WHERE domain=:domain"), {"token": uuid4(), "domain": domain})
        elif mutation == "command_token":
            owned.connection.execute(text("UPDATE etl_dispatch_commands SET claim_token=:token"), {"token": uuid4()})
        elif mutation == "missing_domain":
            owned.connection.execute(text("DELETE FROM etl_dispatch_domains WHERE domain=:domain"), {"domain": domain})
        elif mutation == "job_token":
            owned.connection.execute(text("UPDATE ingestion_jobs SET metadata=metadata || jsonb_build_object('dispatch_claim_token',:token)"), {"token": str(uuid4())})
        elif mutation == "job_dry_run":
            owned.connection.execute(text("UPDATE ingestion_jobs SET dry_run=true"))
        else:
            owned.connection.execute(text("ALTER TABLE etl_dispatch_commands DROP CONSTRAINT ck_etl_dispatch_mapping"))
            owned.connection.execute(text("UPDATE etl_dispatch_commands SET source='oag'"))
    before = rows(owned)
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    with pytest.raises(ReconciliationRefused, match="correlation"):
        make_plan(owned.connection, policy, evidence)
    assert rows(owned) == before


@pytest.mark.parametrize("source,domain", MAPPINGS)
@pytest.mark.parametrize("table", TABLES)
def test_mapped_suppressed_release_is_refused_and_rolled_back(owned, source, domain, table):
    selected, _ = retained(owned, source, domain)
    stop(owned)
    before = rows(owned)
    with owned.connection.begin():
        owned.connection.execute(text("CREATE FUNCTION batch10_suppress_release() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END $$"))
        event = "INSERT" if table == "admin_audit_log" else "UPDATE"
        owned.connection.execute(text(f"CREATE TRIGGER batch10_suppress_release BEFORE {event} ON {table} FOR EACH ROW EXECUTE FUNCTION batch10_suppress_release()"))
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    with pytest.raises(ReconciliationRefused, match="was not"):
        apply_plan(owned.connection, policy, evidence, plan)
    assert rows(owned) == before


@pytest.mark.parametrize("source,domain", MAPPINGS)
@pytest.mark.parametrize("table", TABLES)
def test_mapped_required_values_are_read_back_before_commit(owned, source, domain, table):
    selected, _ = retained(owned, source, domain)
    stop(owned)
    before = rows(owned)
    changed = {
        "admin_audit_log": "NEW.payload := jsonb_build_object('tampered',true);",
        "seeding_domain_claims": "NEW.released_at := OLD.released_at; NEW.reconciled_by := OLD.reconciled_by; NEW.reconciliation := OLD.reconciliation;",
        "etl_dispatch_commands": "NEW.status := OLD.status; NEW.finished_at := OLD.finished_at; NEW.outcome := OLD.outcome;",
        "etl_dispatch_domains": "NEW.command_id := OLD.command_id; NEW.claim_token := OLD.claim_token;",
        "ingestion_jobs": "NEW.status := OLD.status; NEW.finished_at := OLD.finished_at;",
    }[table]
    with owned.connection.begin():
        owned.connection.execute(text("CREATE FUNCTION batch10_change_release() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN " + changed + " RETURN NEW; END $$"))
        event = "INSERT" if table == "admin_audit_log" else "UPDATE"
        owned.connection.execute(text(f"CREATE TRIGGER batch10_change_release BEFORE {event} ON {table} FOR EACH ROW EXECUTE FUNCTION batch10_change_release()"))
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    with pytest.raises(ReconciliationRefused, match="readback"):
        apply_plan(owned.connection, policy, evidence, plan)
    assert rows(owned) == before


@pytest.mark.parametrize("source,domain", MAPPINGS)
def test_mapped_deferred_release_change_is_checked_before_commit(owned, source, domain):
    selected, _ = retained(owned, source, domain)
    stop(owned)
    before = rows(owned)
    with owned.connection.begin():
        owned.connection.execute(text("CREATE FUNCTION batch10_defer_release() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN UPDATE seeding_domain_claims SET released_at=NULL,reconciled_by=NULL,reconciliation=NULL WHERE id=NEW.id; RETURN NEW; END $$"))
        owned.connection.execute(text("CREATE CONSTRAINT TRIGGER batch10_defer_release AFTER UPDATE ON seeding_domain_claims DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.released_at IS NOT NULL) EXECUTE FUNCTION batch10_defer_release()"))
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    with pytest.raises(ReconciliationRefused, match="readback"):
        apply_plan(owned.connection, policy, evidence, plan)
    assert rows(owned) == before


@pytest.mark.parametrize("source,domain", MAPPINGS)
def test_mapped_audit_readback_preserves_exact_json_types(owned, source, domain):
    selected, _ = retained(owned, source, domain)
    stop(owned)
    before = rows(owned)
    with owned.connection.begin():
        owned.connection.execute(text("CREATE FUNCTION batch10_change_audit_type() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN NEW.payload := jsonb_set(NEW.payload,'{version}','true'::jsonb); RETURN NEW; END $$"))
        owned.connection.execute(text("CREATE TRIGGER batch10_change_audit_type BEFORE INSERT ON admin_audit_log FOR EACH ROW EXECUTE FUNCTION batch10_change_audit_type()"))
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    with pytest.raises(ReconciliationRefused, match="readback"):
        apply_plan(owned.connection, policy, evidence, plan)
    assert rows(owned) == before


@pytest.mark.parametrize("source,domain", NEW_MAPPINGS)
@pytest.mark.parametrize("fence", ["open_admission", "live_writer", "ready_worker"])
def test_mapped_release_requires_every_existing_writer_fence(owned, source, domain, fence):
    selected, _ = retained(owned, source, domain)
    stop(owned)
    if fence == "ready_worker":
        with owned.factory.begin() as session:
            session.execute(text("UPDATE etl_dispatch_worker SET ready=true"))
    before = rows(owned)
    policy, evidence, keys = signed(owned, selected)
    if fence == "live_writer":
        evidence["statements"][0]["payload"]["writers"]["dedicated_adapter_orphans"] = "live"
        resign(evidence, keys)
    if fence != "open_admission":
        owned.admission(False)
    with pytest.raises(ReconciliationRefused):
        make_plan(owned.connection, policy, evidence)
    assert rows(owned) == before


@pytest.mark.parametrize("source,domain", NEW_MAPPINGS)
@pytest.mark.parametrize("field", ["claim_token", "generation"])
def test_mapped_command_drift_after_plan_cannot_release(owned, source, domain, field):
    selected, _ = retained(owned, source, domain)
    stop(owned)
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    with owned.connection.begin():
        owned.connection.execute(text(f"UPDATE etl_dispatch_commands SET {field}=:value"), {"value": uuid4()})
    before = rows(owned)
    with pytest.raises(ReconciliationRefused, match="correlation|changed since plan"):
        apply_plan(owned.connection, policy, evidence, plan)
    assert rows(owned) == before


@pytest.mark.parametrize("source,domain", NEW_MAPPINGS)
def test_mapped_backend_loss_during_release_retains_all_ownership(owned, source, domain):
    selected, _ = retained(owned, source, domain)
    stop(owned)
    before = rows(owned)
    with owned.connection.begin():
        owned.connection.execute(text("CREATE FUNCTION batch10_lose_backend() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_terminate_backend(pg_backend_pid()); RETURN NEW; END $$"))
        owned.connection.execute(text("CREATE TRIGGER batch10_lose_backend BEFORE UPDATE ON seeding_domain_claims FOR EACH ROW EXECUTE FUNCTION batch10_lose_backend()"))
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    with pytest.raises(DBAPIError):
        apply_plan(owned.connection, policy, evidence, plan)
    owned.admission(True)
    # Observe committed state through a fresh actual backend after termination.
    lost_connection = owned.connection
    with owned.engine.connect() as connection:
        owned.connection = connection
        try:
            assert rows(owned) == before
        finally:
            owned.connection = lost_connection
