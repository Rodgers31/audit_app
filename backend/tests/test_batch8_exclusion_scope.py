"""Execution-scope and acknowledgement binding (#572 review findings 1-2).

Scopes are process-local, so these call the real CLI and the real dispatch
adapter in-process against the owned PostgreSQL fixture. Only the registry
holds an inert handler; ownership, adapter and worker code run unchanged.
Forgeries use the public constructor plus plain attribute assignment, i.e.
exactly what an arbitrary in-process caller can do without the adapter.
"""
import argparse
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from test_batch7_etl_postgres import pg, post, URL
from test_batch7_etl_process import process_pg
from admin_etl_dispatch_worker import claim, finish, register_worker
import admin_etl_dispatch_adapter as adapter
from models import IngestionJob, IngestionStatus
from seeding import cli, registries
import seeding.domains.audits.scope  # noqa: F401  registers the real handler once, before patching
from seeding.config import SeedingSettings
from seeding.exclusion import DomainExecution, DomainOwnershipError, dispatch_scope, enter_domain, reserve
from seeding.types import DomainRunResult

pytestmark = pytest.mark.skipif(not URL, reason="Owned PostgreSQL required")


@pytest.fixture
def inert(process_pg, monkeypatch):
    client, factory, engine = process_pg
    calls = []

    def handler(session, settings, context):
        calls.append(context.job_id)
        session.execute(text("INSERT INTO batch7_effects(job_id) VALUES (:job)"), {"job": context.job_id})
        return DomainRunResult(domain="audits", dry_run=context.dry_run, items_processed=1, items_created=1)

    monkeypatch.setattr(registries.REGISTRY, "_handlers", {"audits": handler})
    monkeypatch.setattr(registries, "load_builtin_domains", lambda: None)
    monkeypatch.setattr(cli, "load_builtin_domains", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", factory)
    return client, factory, engine, calls


def run(dry_run=False):
    args = argparse.Namespace(domain=["audits"], all=False, since=None, dry_run=dry_run,
        audits_source_manifest=None, audits_observe_listing=False)
    return cli.run_seed_command(args, SeedingSettings(log_path=None, total_timeout_seconds=0))


def effects(engine):
    with engine.connect() as conn:
        return conn.scalar(text("SELECT count(*) FROM batch7_effects"))


def jobs(engine):
    """Observations of runs that started; a refusal is recorded separately."""
    with engine.connect() as conn:
        return conn.scalar(text("SELECT count(*) FROM ingestion_jobs WHERE metadata->>'ownership_refused' IS NULL"))


def refused(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*), bool_and(status::text='FAILED') FROM ingestion_jobs"
            " WHERE metadata->>'ownership_refused'='true'")).one()


def claims(engine):
    with engine.connect() as conn:
        return {row[0]: tuple(row[1:]) for row in conn.execute(text(
            "SELECT id::text, domain, kind, returned_at IS NOT NULL, released_at IS NOT NULL FROM seeding_domain_claims"))}


def retained_native(factory, domain="audits"):
    identity = uuid4()
    with factory.begin() as db:
        assert reserve(db, domain, identity)
    return identity


def terminal_job(factory, identity, domain):
    now = datetime.now(timezone.utc)
    with factory.begin() as db:
        job = IngestionJob(domain=domain, status=IngestionStatus.COMPLETED, dry_run=False,
            started_at=now, finished_at=now, items_processed=1, items_created=1, items_updated=0,
            errors=[], meta={"seeding_claim_id": str(identity)})
        db.add(job)
        db.flush()
        return job.id


def forged_run(factory, domain, identity, **attributes):
    execution = DomainExecution(factory, domain, identity)
    for name, value in attributes.items():
        setattr(execution, name, value)
    execution.open()
    try:
        with dispatch_scope(execution):
            return run()
    finally:
        execution.close()


def dispatched(client, factory):
    generation = register_worker(factory)
    identity = post(client, generation).json()["command"]["id"]
    command_id, token = claim(factory, generation)
    assert str(command_id) == identity
    return generation, command_id, token


def test_scope_without_any_durable_claim_starts_no_work(inert):
    _, factory, engine, calls = inert
    before = claims(engine)
    assert forged_run(factory, "audits", uuid4()) == 1
    assert calls == [] and effects(engine) == 0 and jobs(engine) == 0 and tuple(refused(engine)) == (1, True)
    assert claims(engine) == before


def test_scope_reusing_retained_native_claim_starts_no_work_and_keeps_it(inert):
    _, factory, engine, calls = inert
    retained = retained_native(factory)
    before = claims(engine)
    assert forged_run(factory, "audits", retained) == 1
    assert calls == [] and effects(engine) == 0 and jobs(engine) == 0 and tuple(refused(engine)) == (1, True)
    assert claims(engine) == before and before[str(retained)] == ("audits", "native", False, False)
    # The ordinary CLI is still excluded by the untouched retained claim.
    assert run() == 1 and calls == []


def test_scope_with_dispatch_token_but_no_adapter_entry_starts_no_work(inert):
    client, factory, engine, calls = inert
    generation, command_id, token = dispatched(client, factory)
    before = claims(engine)
    assert forged_run(factory, "audits", token, command_id=command_id, generation=generation) == 1
    assert calls == [] and effects(engine) == 0 and jobs(engine) == 0 and tuple(refused(engine)) == (1, True)
    assert claims(engine) == before and before[str(token)] == ("audits", "dispatch", False, False)


@pytest.mark.parametrize("field", ["command_id", "generation", "domain", "dry_run"])
def test_scope_with_mismatched_correlation_starts_no_work(inert, field):
    client, factory, engine, calls = inert
    generation, command_id, token = dispatched(client, factory)
    with factory.begin() as db:
        db.execute(text("UPDATE etl_dispatch_commands SET execution_started=true WHERE id=:id"), {"id": command_id})
    values = {"command_id": command_id, "generation": generation, "domain": "audits"}
    if field != "dry_run":
        values[field] = "counties_budget" if field == "domain" else uuid4()
    domain = values.pop("domain")
    before = claims(engine)
    execution = DomainExecution(factory, "audits", token)
    for name, value in values.items():
        setattr(execution, name, value)
    execution.domain = domain
    execution.open()
    try:
        with dispatch_scope(execution):
            # The command was accepted as a real run; a dry-run CLI must not enter.
            assert run(dry_run=field == "dry_run") == 1
    finally:
        execution.close()
    assert calls == [] and effects(engine) == 0 and jobs(engine) == 0 and tuple(refused(engine)) == (1, True)
    assert claims(engine) == before


def test_legitimate_adapter_scope_is_one_use(inert):
    client, factory, engine, calls = inert
    generation, command_id, token = dispatched(client, factory)
    assert adapter.execute(factory, engine, command_id, token, generation) == 0
    assert len(calls) == 1 and effects(engine) == 1
    assert claims(engine)[str(token)] == ("audits", "dispatch", True, False)
    # A second adapter launch and a replayed scope with the same identifiers
    # both start no work; neither changes the retained receipt.
    assert adapter.execute(factory, engine, command_id, token, generation) == 1
    assert forged_run(factory, "audits", token, command_id=command_id, generation=generation, entered=False) == 1
    assert len(calls) == 1 and effects(engine) == 1 and jobs(engine) == 1 and refused(engine)[0] == 1
    assert claims(engine)[str(token)] == ("audits", "dispatch", True, False)
    assert finish(factory, generation, command_id, token, 0) is True
    assert claims(engine)[str(token)] == ("audits", "dispatch", True, True)
    assert run() == 0 and len(calls) == 2


def test_acknowledgement_cannot_release_another_domains_claim(inert):
    _, factory, engine, _ = inert
    other = retained_native(factory, "retained_domain_a")
    job_id = terminal_job(factory, other, "retained_domain_a")
    execution = DomainExecution(factory, "unrelated_domain_b", other)
    execution.open()
    try:
        with pytest.raises(DomainOwnershipError):
            execution.acknowledge(job_id)
    finally:
        execution.close()
    assert claims(engine)[str(other)] == ("retained_domain_a", "native", False, False)


def test_acknowledgement_requires_an_execution_that_entered(inert):
    _, factory, engine, _ = inert
    retained = retained_native(factory)
    job_id = terminal_job(factory, retained, "audits")
    # Same domain and claim; the in-process flag alone must not stand in for
    # the durable entry this object never performed.
    execution = DomainExecution(factory, "audits", retained)
    execution.open()
    execution.entered = True
    try:
        with pytest.raises(DomainOwnershipError):
            execution.acknowledge(job_id)
    finally:
        execution.close()
    assert claims(engine)[str(retained)] == ("audits", "native", False, False)
    assert run() == 1


def test_native_acknowledgement_after_entry_releases_once(inert):
    _, factory, engine, calls = inert
    assert run() == 0 and run() == 0
    assert len(calls) == 2 and effects(engine) == 2
    assert sorted(claims(engine).values()) == [("audits", "native", True, True)] * 2
    assert run(dry_run=True) == 0 and len(calls) == 3 and effects(engine) == 2


def entered_native(factory, domain="audits"):
    identity, entry = uuid4(), uuid4()
    with factory.begin() as db:
        assert reserve(db, domain, identity, entry=entry)
    return identity, entry


@pytest.mark.parametrize("change", [None, "wrong_entry", "other_domain", "dispatch_kind"])
def test_acknowledgement_rejects_each_mismatched_binding(inert, change):
    _, factory, engine, _ = inert
    identity, entry = entered_native(factory, "retained_domain_a")
    job_id = terminal_job(factory, identity, "retained_domain_a")
    # Every other binding is correct, so each guard is the only one that can refuse.
    execution = DomainExecution(factory, "retained_domain_a", identity)
    execution.entered, execution.entry = True, entry
    if change == "wrong_entry":
        execution.entry = uuid4()
    elif change == "other_domain":
        execution.domain = "unrelated_domain_b"
    elif change == "dispatch_kind":
        execution.command_id = uuid4()
    execution.open()
    try:
        if change is None:  # control: the same object with every binding intact
            execution.acknowledge(job_id)
        else:
            with pytest.raises(DomainOwnershipError):
                execution.acknowledge(job_id)
    finally:
        execution.close()
    released = change is None
    assert claims(engine)[str(identity)] == ("retained_domain_a", "native", released, released)


def entered_dispatch(client, factory):
    generation, command_id, token = dispatched(client, factory)
    with factory.begin() as db:
        db.execute(text("UPDATE etl_dispatch_commands SET execution_started=true WHERE id=:id"), {"id": command_id})
    first = DomainExecution(factory, "audits", token, command_id, generation)
    first.open()
    with dispatch_scope(first):
        assert enter_domain(factory, "audits", False) is first
    return generation, command_id, token, first


def test_entered_dispatch_claim_cannot_be_entered_again_after_lock_loss(inert):
    client, factory, engine, calls = inert
    generation, command_id, token, first = entered_dispatch(client, factory)
    first.close()  # the first entrant's lock connection is gone; its claim is not
    assert forged_run(factory, "audits", token, command_id=command_id, generation=generation) == 1
    assert calls == [] and effects(engine) == 0 and jobs(engine) == 0
    assert claims(engine)[str(token)] == ("audits", "dispatch", False, False)


def test_dispatch_acknowledgement_requires_its_own_command(inert):
    client, factory, engine, _ = inert
    generation, command_id, token, first = entered_dispatch(client, factory)
    job_id = terminal_job(factory, token, "audits")
    try:
        first.command_id = uuid4()
        with pytest.raises(DomainOwnershipError):
            first.acknowledge(job_id)
        first.command_id = command_id  # control: the correct command acknowledges
        first.acknowledge(job_id)
    finally:
        first.close()
    assert claims(engine)[str(token)] == ("audits", "dispatch", True, False)


def test_entry_copied_from_the_claim_row_cannot_acknowledge(inert):
    # Adversarial round 3: reading entry_id from the database used to be enough.
    _, factory, engine, _ = inert
    identity, _ = entered_native(factory, "retained_domain_a")
    job_id = terminal_job(factory, identity, "retained_domain_a")
    with engine.connect() as conn:
        stored = conn.scalar(text("SELECT entry_id FROM seeding_domain_claims WHERE id=:id"), {"id": str(identity)})
    forged = DomainExecution(factory, "retained_domain_a", identity)
    forged.entered, forged.entry = True, stored
    forged.open()
    try:
        with pytest.raises(DomainOwnershipError):
            forged.acknowledge(job_id)
    finally:
        forged.close()
    assert claims(engine)[str(identity)] == ("retained_domain_a", "native", False, False)


@pytest.mark.parametrize("tagged", [False, True])
def test_only_running_rows_outside_the_seam_refuse_native_entry(inert, tagged):
    _, factory, engine, calls = inert
    meta = {"seeding_claim_id": str(uuid4())} if tagged else {"since": None}
    with factory.begin() as db:
        db.add(IngestionJob(domain="audits", status=IngestionStatus.RUNNING, dry_run=False,
            started_at=datetime.now(timezone.utc), items_processed=0, items_created=0, items_updated=0,
            errors=[], meta=meta))
    # An absent claim does not prove ownership, even when the tag parses as a
    # UUID. Both observations may be live out-of-seam writers, with no age limit.
    assert run() == 1
    assert calls == []
    assert refused(engine)[0] == 1


def test_autocommit_engine_cannot_hold_the_continuity_lock(inert):
    _, factory, engine, _ = inert
    autocommit = engine.execution_options(isolation_level="AUTOCOMMIT")
    execution = DomainExecution(sessionmaker(bind=autocommit), "adv_autocommit", uuid4())
    with pytest.raises(DomainOwnershipError):
        execution.open()
    assert execution.connection is None
