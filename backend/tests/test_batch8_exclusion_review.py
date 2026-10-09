"""Coordinator regressions for PR #584, on the explicitly owned local fixture.

Use the actual CLI, worker, durable claims and PostgreSQL transactions. The
registry handler alone is inert. Faults target only this test's lock backend.
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

from admin_etl_dispatch_worker import claim, finish, register_worker
import admin_etl_dispatch_adapter as adapter
from models import EtlDispatchDomain, IngestionJob, IngestionStatus, SeedingDomainClaim
from seeding import exclusion
from seeding.exclusion import DomainOwnershipError, enter_domain, reserve, unclaimed_running
from test_batch7_etl_postgres import expire, pg, post, URL
from test_batch7_etl_process import process_pg
from test_batch8_exclusion_scope import inert, effects, run, terminal_job

pytestmark = pytest.mark.skipif(not URL, reason="Owned PostgreSQL required")


def test_actual_cli_boolean_refusal_permits_never_entered_finish(inert, monkeypatch):
    client, factory, engine, calls = inert
    generation = register_worker(factory)
    assert post(client, generation).status_code == 202
    command_id, token = claim(factory, generation)

    def refuse_entry(*args, **kwargs):
        raise DomainOwnershipError("Inert entry refusal")

    # Only entry is refused. The actual adapter, CLI refusal insertion and
    # dispatch correlation run normally, producing the accepted shape.
    with monkeypatch.context() as patch:
        patch.setattr(exclusion, "enter_domain", refuse_entry)
        assert adapter.execute(factory, engine, command_id, token, generation) == 1
    with factory() as db:
        job = db.query(IngestionJob).one()
        assert job.status == IngestionStatus.FAILED
        assert job.meta["ownership_refused"] is True
        assert job.meta["dispatch_command_id"] == str(command_id)
        assert job.meta["dispatch_claim_token"] == str(token)
    assert finish(factory, generation, command_id, token, 1) is True
    assert calls == [] and effects(engine) == 0
    assert run() == 0


@pytest.mark.parametrize("shape", [
    "missing", "null", "bool", "number", "list", "object", "empty", "garbage",
    "absent_uuid", "released_uuid", "other_domain_uuid", "active_uuid",
])
def test_running_tag_requires_an_active_claim_for_its_domain(inert, shape):
    client, factory, engine, calls = inert
    values = {"null": None, "bool": True, "number": 1, "list": [], "object": {},
        "empty": "", "garbage": "not-a-uuid", "absent_uuid": str(uuid4())}
    if shape == "released_uuid":
        execution = enter_domain(factory, "audits", False)
        try:
            execution.acknowledge(terminal_job(factory, execution.identity, "audits"))
        finally:
            execution.close()
        tag = str(execution.identity)
    elif shape in ("other_domain_uuid", "active_uuid"):
        identity = uuid4()
        with factory.begin() as db:
            assert reserve(db, "audits" if shape == "active_uuid" else "other_domain", identity)
        tag = str(identity)
    else:
        tag = values.get(shape)
    meta = {} if shape == "missing" else {"seeding_claim_id": tag}
    with factory.begin() as db:
        db.add(IngestionJob(domain="audits", status=IngestionStatus.RUNNING, dry_run=False,
            started_at=datetime.now(timezone.utc), items_processed=0, items_created=0,
            items_updated=0, errors=[], meta=meta))
    with factory() as db:
        assert unclaimed_running(db, "audits") is (shape != "active_uuid")
    assert run() == 1
    assert calls == [] and effects(engine) == 0
    generation = register_worker(factory)
    assert post(client, generation).status_code == 202
    assert claim(factory, generation) is None


def test_restart_preserves_even_a_never_entered_claim(inert):
    """Recorded policy: restart is uncertainty, not operational reconciliation."""
    client, factory, engine, calls = inert
    old_generation = register_worker(factory)
    assert post(client, old_generation).status_code == 202
    command_id, token = claim(factory, old_generation)
    expire(factory)
    new_generation = register_worker(factory)
    assert new_generation != old_generation
    # Even an original child arriving late is fenced before its actual CLI
    # entry. Restart does not replace explicit reconciliation of retained state.
    assert adapter.execute(factory, engine, command_id, token, old_generation) == 1
    with factory() as db:
        ownership = db.get(SeedingDomainClaim, token)
        assert ownership.entered_at is None and ownership.returned_at is None
        assert ownership.released_at is None
        assert db.get(EtlDispatchDomain, "audits").command_id == command_id
    assert run() == 1 and calls == [] and effects(engine) == 0
    assert claim(factory, new_generation) is None


@pytest.mark.parametrize("fault", ["after_continuity", "before_commit", "none"])
def test_acknowledgement_commit_is_fenced_by_its_lock_connection(inert, monkeypatch, fault):
    _, factory, engine, _ = inert
    execution = enter_domain(factory, "audits", False)
    job_id = terminal_job(factory, execution.identity, "audits")
    terminated, commit_pids = [], []

    def terminate_lock():
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as killer:
            assert killer.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": execution.pid}) is True
        terminated.append(execution.pid)

    original = execution.continuous

    def continuous_then_loss():
        result = original()
        if result:
            terminate_lock()
        return result

    def before_commit(connection):
        commit_pids.append(connection.scalar(text("SELECT pg_backend_pid()")))
        if fault == "before_commit" and not terminated:
            terminate_lock()

    if fault == "after_continuity":
        monkeypatch.setattr(execution, "continuous", continuous_then_loss)
    event.listen(engine, "commit", before_commit)
    try:
        if fault == "none":
            execution.acknowledge(job_id)
            assert commit_pids == [execution.pid]
        else:
            with pytest.raises(DBAPIError):
                execution.acknowledge(job_id)
            assert terminated == [execution.pid]
    finally:
        event.remove(engine, "commit", before_commit)
        try:
            execution.close()
        except DBAPIError:
            # The intentionally terminated backend cannot accept a rollback.
            pass
    with factory() as db:
        ownership = db.get(SeedingDomainClaim, execution.identity)
        assert (ownership.returned_at is not None) is (fault == "none")
        assert (ownership.released_at is not None) is (fault == "none")
    # A failed acknowledgement retains authority and refuses the actual CLI.
    assert run() == (0 if fault == "none" else 1)
