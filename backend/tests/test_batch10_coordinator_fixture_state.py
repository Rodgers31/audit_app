"""Actual PostgreSQL fixture snapshots retain every domain in a stable order.

Execute the fixture_state body verbatim, without importing the fixed-port HTTP
fixture or rewriting its SQL. This proves the snapshot seam; the unchanged
browser suite separately proves the full HTTP/UI/native-worker interaction.
"""
import ast
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from admin_etl_dispatch import TriggerBody, accept, command_detail
from admin_etl_dispatch_worker import claim, register_worker
from models import IngestionJob, IngestionStatus
from seeding.exclusion import DomainExecution, dispatch_scope, enter_domain
from test_batch9_reconciliation import owned, read

FIXTURE = Path(__file__).with_name("batch7_coordinator_integration_fixture.py")
DOMAINS = ("audits", "counties_budget", "fiscal_summary", "population")
TABLES = ("etl_dispatch_commands", "etl_dispatch_domains", "seeding_domain_claims",
          "admin_audit_log", "ingestion_jobs", "batch7_coordinator_effects")


def actual_fixture_state(factory):
    tree = ast.parse(FIXTURE.read_text(), filename=str(FIXTURE))
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name == "fixture_state"]
    assert len(functions) == 1
    function = functions[0]
    function.decorator_list = []  # The same body; no HTTP registration/import.
    module = ast.Module(body=[function], type_ignores=[])
    namespace = {"SessionLocal": factory, "text": text, "workers": []}
    exec(compile(module, str(FIXTURE), "exec"), namespace)
    return namespace["fixture_state"]()


def stored(owned):
    return {table: read(owned, "SELECT * FROM " + table + " ORDER BY 1")
            for table in TABLES}


@pytest.mark.parametrize("insertion_order", [DOMAINS, tuple(reversed(DOMAINS))],
                         ids=["audits-inserted-first", "audits-inserted-last"])
@pytest.mark.parametrize("extra_updates", [0, 2], ids=["claimed-once", "updated-again"])
def test_four_domain_snapshot_preserves_interrupted_owner_independent_of_tuple_order(
        owned, monkeypatch, insertion_order, extra_updates):
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "true")
    monkeypatch.setattr("admin_etl_dispatch_adapter.ready_domains", lambda: set(DOMAINS))
    generation = register_worker(owned.factory)
    with owned.factory.begin() as db:
        db.execute(text("DELETE FROM etl_dispatch_domains"))
        for domain in insertion_order:
            db.execute(text("INSERT INTO etl_dispatch_domains(domain,ready) VALUES (:domain,true)"),
                       {"domain": domain})
        db.execute(text("CREATE TABLE IF NOT EXISTS batch7_coordinator_effects "
                        "(job_id integer NOT NULL REFERENCES ingestion_jobs(id))"))
        db.execute(text("CREATE TABLE IF NOT EXISTS batch7_coordinator_markers "
                        "(stage text NOT NULL,job_id integer NOT NULL REFERENCES ingestion_jobs(id))"))
    with owned.factory() as db:
        accepted = accept(db, SimpleNamespace(id="owned-operator", email="owned@example.invalid"),
                          "oag", TriggerBody(dispatch_generation=str(generation)), str(uuid4()))
    command_id, token = claim(owned.factory, generation)
    assert command_id == accepted.command.id
    with owned.factory.begin() as db:
        db.execute(text("UPDATE etl_dispatch_commands SET execution_started=true WHERE id=:id"),
                   {"id": command_id})
    execution = DomainExecution(owned.factory, "audits", token, command_id, generation)
    execution.open()
    try:
        with dispatch_scope(execution):
            assert enter_domain(owned.factory, "audits", False) is execution
        with owned.factory.begin() as db:
            job = IngestionJob(domain="audits", dry_run=False, status=IngestionStatus.RUNNING,
                started_at=datetime.now(timezone.utc), errors=[],
                meta={"seeding_claim_id": str(token), "dispatch_command_id": str(command_id),
                      "dispatch_claim_token": str(token)})
            db.add(job)
            db.flush()
            db.execute(text("INSERT INTO batch7_coordinator_effects(job_id) VALUES (:job)"),
                       {"job": job.id})
            for _ in range(extra_updates):
                db.execute(text("UPDATE etl_dispatch_domains SET ready=true WHERE domain='audits'"))
            db.execute(text("UPDATE etl_dispatch_worker SET "
                "last_seen_at=clock_timestamp()-interval '2 seconds',"
                "expires_at=clock_timestamp()-interval '1 second'"))
    finally:
        execution.close()
    with owned.factory() as db:
        receipt = command_detail(db, str(command_id))
    assert receipt.status == "interrupted" and receipt.outcome == "execution_unverified"
    before = stored(owned)
    actual = actual_fixture_state(owned.factory)
    assert stored(owned) == before, "Snapshot changed durable ownership or observations"
    assert actual["counts"] == {"commands": 1, "audits": 1, "jobs": 1, "effects": 1}
    assert len(actual["domains"]) == 4
    indexed = {row["domain"]: row for row in actual["domains"]}
    assert set(indexed) == set(DOMAINS)
    assert indexed["audits"] == {"domain": "audits", "command_id": str(command_id),
                                "claim_token": str(token)}
    assert all(indexed[name]["command_id"] is None and indexed[name]["claim_token"] is None
               for name in DOMAINS if name != "audits")
    ownership = before["seeding_domain_claims"]
    assert len(ownership) == 1 and ownership[0]["id"] == token
    assert ownership[0]["command_id"] == command_id and ownership[0]["released_at"] is None
    # Preserve the original browser assertion, with the full identity contract.
    assert actual["domains"][0]["command_id"] == str(command_id), actual["domains"]
    assert [row["domain"] for row in actual["domains"]] == list(DOMAINS)
