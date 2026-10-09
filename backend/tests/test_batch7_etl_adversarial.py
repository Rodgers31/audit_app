"""Independent executable boundary attacks; owned PostgreSQL schema only.

Reviewed author SHA e98a4be3998f7da4e2326a068802a879e393fb97. No product
lifespan, primary dotenv, public-schema writes, or native source transport.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import os

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from admin_etl_dispatch import Command, TriggerBody, accept, capability, command_history
from admin_etl_dispatch_worker import claim, finish, heartbeat, register_worker
from models import AdminAuditLog, Base, EtlDispatchCommand, EtlDispatchDomain, EtlDispatchWorker, IngestionJob, IngestionStatus

URL = "postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55481/batch7_etl_worker"
SCHEMA = "batch7_adversarial"
ACTOR = SimpleNamespace(id="batch7-adversarial-admin", email="inert@example.invalid")
pytestmark = pytest.mark.skipif(os.environ.get("BATCH7_ETL_ADVERSARIAL_DATABASE_URL") != URL, reason="Explicit owned PostgreSQL required")


@pytest.fixture(scope="module")
def isolated_engine():
    engine = create_engine(URL, connect_args={"options": "-c search_path=" + SCHEMA})
    with engine.begin() as db:
        db.execute(text("CREATE SCHEMA batch7_adversarial"))
    Base.metadata.create_all(engine, tables=[AdminAuditLog.__table__, IngestionJob.__table__, EtlDispatchCommand.__table__, EtlDispatchWorker.__table__, EtlDispatchDomain.__table__])
    try:
        yield engine
    finally:
        with engine.begin() as db:
            db.execute(text("DROP SCHEMA batch7_adversarial CASCADE"))
        engine.dispose()


@pytest.fixture
def pg(isolated_engine, monkeypatch):
    with isolated_engine.begin() as db:
        db.execute(text("TRUNCATE etl_dispatch_domains, etl_dispatch_commands, etl_dispatch_worker, admin_audit_log, ingestion_jobs RESTART IDENTITY CASCADE"))
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "true")
    yield sessionmaker(bind=isolated_engine), isolated_engine


def accepted(factory, generation, dry_run=False, key=None):
    key = key or uuid4()
    with factory() as db:
        receipt = accept(db, ACTOR, "oag", TriggerBody(dry_run=dry_run, dispatch_generation=str(generation)), str(key))
    return receipt.command.id, key


def running(pg):
    factory, engine = pg
    generation = register_worker(factory)
    identity, key = accepted(factory, generation)
    claimed = claim(factory, generation)
    assert claimed and claimed[0] == identity
    return factory, engine, generation, identity, claimed[1], key


def observation(factory, command_id, token, **changes):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    payload = dict(domain="audits", status=IngestionStatus.COMPLETED, dry_run=False,
        started_at=now, finished_at=now, items_processed=1, items_created=1, items_updated=0,
        errors=[], meta={"dispatch_command_id": str(command_id), "dispatch_claim_token": str(token)})
    payload.update(changes)
    with factory.begin() as db:
        db.get(EtlDispatchCommand, command_id).execution_started = True
        row = IngestionJob(**payload)
        db.add(row)
        db.flush()
        identity = row.id
    return identity


def test_capability_storage_commit_failure_is_unavailable(pg, monkeypatch):
    factory, _ = pg
    register_worker(factory)
    with factory() as db:
        def failed_commit():
            raise RuntimeError("INERT_PRIVATE_STORAGE_FAILURE")
        monkeypatch.setattr(db, "commit", failed_commit)
        receipt = capability(db)
    assert receipt.available is False
    assert receipt.generation is None and receipt.worker.status == "unavailable"
    assert receipt.worker.last_seen_at is None and receipt.worker.expires_at is None
    assert all(source.available is False for source in receipt.sources.values())


@pytest.mark.parametrize("dry_run,bad", [(False, 0), (False, 0.0), (True, 1), (True, 1.0)])
def test_direct_replay_rejects_nonboolean_semantic_intent(pg, dry_run, bad):
    factory, _ = pg
    generation = register_worker(factory)
    _, key = accepted(factory, generation, dry_run=dry_run)
    with factory() as db:
        with pytest.raises(HTTPException) as failure:
            accept(db, ACTOR, "oag", SimpleNamespace(dry_run=bad, dispatch_generation=None), str(key))
    assert failure.value.status_code == 422


@pytest.mark.parametrize("change", [
    {"domain": "other"}, {"dry_run": True}, {"status": IngestionStatus.RUNNING},
    {"finished_at": None}, {"finished_at": datetime(2000, 1, 1)},
    {"meta": {}}, {"meta": None}, {"meta": []}, {"meta": {"dispatch_command_id": "unknown"}},
])
def test_finish_rejects_missing_mismatched_or_unfinished_observation(pg, change):
    factory, _, generation, identity, token, _ = running(pg)
    observation(factory, identity, token, **change)
    assert finish(factory, generation, identity, token, 0) is False
    with factory() as db:
        command = db.get(EtlDispatchCommand, identity)
        assert command.status == "interrupted" and command.job_id is None
        assert db.get(EtlDispatchDomain, "audits").command_id == identity


@pytest.mark.parametrize("change", [
    {"status": IngestionStatus.FAILED}, {"status": IngestionStatus.COMPLETED_WITH_ERRORS},
])
def test_truthy_failed_observation_cannot_complete(pg, change):
    factory, _, generation, identity, token, _ = running(pg)
    job_id = observation(factory, identity, token, **change)
    assert finish(factory, generation, identity, token, 0) is True
    with factory() as db:
        command = db.get(EtlDispatchCommand, identity)
        assert command.status == command.outcome == "failed" and command.job_id == job_id


@pytest.mark.parametrize("change", [
    {"started_at": datetime(2100, 1, 1), "finished_at": datetime(2100, 1, 2)},
    {"started_at": datetime(2000, 1, 1), "finished_at": datetime(2000, 1, 2)},
    {"errors": ["INERT_PRIVATE_FAILURE"]}, {"items_processed": -1},
])
def test_finish_rejects_incoherent_correlated_completed_observation(pg, change):
    factory, _, generation, identity, token, _ = running(pg)
    observation(factory, identity, token, **change)
    result = finish(factory, generation, identity, token, 0)
    with factory() as db:
        command = db.get(EtlDispatchCommand, identity)
        assert result is False
        assert command.status == "interrupted" and command.outcome == "execution_unverified" and command.job_id is None
        assert db.get(EtlDispatchDomain, "audits").command_id == identity


@pytest.mark.parametrize("bad", [None, False, True, 0.0, float("nan"), float("inf"), -1, "0", {}, []])
def test_bad_exit_code_cannot_report_completed(pg, bad):
    factory, _, generation, identity, token, _ = running(pg)
    observation(factory, identity, token)
    finish(factory, generation, identity, token, bad)
    with factory() as db:
        assert db.get(EtlDispatchCommand, identity).status != "completed"


@pytest.mark.parametrize("bad", [None, uuid4(), "unknown", False, {}, []])
def test_unknown_generation_token_does_not_claim_or_finish(pg, bad):
    factory, _, generation, identity, token, _ = running(pg)
    observation(factory, identity, token)
    assert heartbeat(factory, bad) is False
    assert claim(factory, bad) is None
    assert finish(factory, generation, identity, bad, 0) is False
    assert finish(factory, bad, identity, token, 0) is False
    with factory() as db:
        assert db.get(EtlDispatchCommand, identity).status == "running"


@pytest.mark.parametrize("lease", ["stale", "future"])
def test_stale_or_future_lease_does_not_claim_complete_or_execute(pg, lease, monkeypatch):
    from admin_etl_dispatch_adapter import execute
    factory, engine, generation, identity, token, _ = running(pg)
    observation(factory, identity, token)
    with factory.begin() as db:
        offset = "- interval '60 second'" if lease == "stale" else "+ interval '60 second'"
        db.execute(text("UPDATE etl_dispatch_worker SET last_seen_at=clock_timestamp() " + offset + ", expires_at=clock_timestamp() " + offset + " + interval '30 second'"))
    monkeypatch.setattr("admin_etl_dispatch_adapter.supported_registry", lambda: True)
    assert heartbeat(factory, generation) is False
    assert claim(factory, generation) is None
    assert execute(factory, engine, identity, token, generation) == 1
    assert finish(factory, generation, identity, token, 0) is False
    with factory() as db:
        assert db.get(EtlDispatchCommand, identity).status == "interrupted"
        assert db.get(EtlDispatchDomain, "audits").command_id == identity


@pytest.mark.parametrize("page,size", [(None, 1), ([], 1), ({}, 1), (True, 1), (0, 1), (-1, 1), (float("nan"), 1), (float("inf"), 1), (1, False), (1, 0), (1, 51)])
def test_direct_history_bounds_do_not_return_success(pg, page, size):
    factory, _ = pg
    with factory() as db, pytest.raises(HTTPException) as error:
        command_history(db, page, size)
    assert error.value.status_code == 422


@pytest.mark.parametrize("field,bad", [
    ("dry_run", None), ("dry_run", 0), ("dry_run", "false"), ("version", True),
    ("version", 0), ("version", -1), ("version", float("nan")), ("version", float("inf")),
    ("status", "unknown"), ("source", "other"), ("job_id", True), ("job_id", 0),
    ("created_at", None), ("created_at", []), ("updated_at", "2020-01-01T00:00:00Z"),
])
def test_receipt_projection_rejects_hostile_shapes(field, bad):
    now = datetime.now(timezone.utc)
    data = dict(id=uuid4(), source="oag", dry_run=False, status="queued", version=1,
        created_at=now, updated_at=now, started_at=None, finished_at=None, job_id=None, outcome=None)
    data[field] = bad
    with pytest.raises(ValidationError):
        Command.model_validate(data)


def inert_adapter(monkeypatch, tmp_path):
    """Run the unchanged CLI with one registered inert domain and no transport."""
    import socket
    from seeding.registries import REGISTRY
    from seeding.types import DomainRunResult

    original_connect = socket.socket.connect
    def local_only(sock, address):
        if not isinstance(address, tuple) or address[:2] != ("127.0.0.1", 55481):
            raise RuntimeError("External transport blocked in adversarial fixture")
        return original_connect(sock, address)
    monkeypatch.setattr(socket.socket, "connect", local_only)
    monkeypatch.setenv("SEED_STORAGE_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("SEED_CACHE_PATH", str(tmp_path / "cache"))
    # Import the unchanged CLI's mandatory audits scope before replacing the
    # registered handler; its package initializer registers the native domain.
    from seeding.domains.audits import scope  # noqa: F401
    monkeypatch.setattr("seeding.registries.load_builtin_domains", lambda: None)
    monkeypatch.setattr("seeding.cli.load_builtin_domains", lambda: None)
    calls = []

    def handler(session, settings, context):
        calls.append(context.job_id)
        session.add(AdminAuditLog(actor_id="inert-handler", action="inert.adversarial.effect", payload={}))
        return DomainRunResult(domain="audits", dry_run=context.dry_run, items_processed=1, items_created=1)
    monkeypatch.setattr(REGISTRY, "_handlers", {"audits": handler})
    return calls


@pytest.mark.parametrize("dry_run,expected_effects", [(False, 1), (True, 0)])
def test_actual_adapter_duplicate_invocation_and_real_dry_writes(pg, monkeypatch, tmp_path, dry_run, expected_effects):
    from admin_etl_dispatch_adapter import execute
    factory, engine = pg
    calls = inert_adapter(monkeypatch, tmp_path)
    generation = register_worker(factory)
    identity, _ = accepted(factory, generation, dry_run=dry_run)
    _, token = claim(factory, generation)
    assert execute(factory, engine, identity, token, generation) == 0
    assert execute(factory, engine, identity, token, generation) == 1
    assert len(calls) == 1
    assert finish(factory, generation, identity, token, 0) is True
    with factory() as db:
        command = db.get(EtlDispatchCommand, identity)
        assert command.status == "completed" and command.job_id == calls[0]
        jobs = db.query(IngestionJob).all()
        assert len(jobs) == 1 and jobs[0].dry_run is dry_run
        assert jobs[0].meta["dispatch_command_id"] == str(identity)
        assert jobs[0].meta["dispatch_claim_token"] == str(token)
        assert db.query(AdminAuditLog).filter_by(action="inert.adversarial.effect").count() == expected_effects
        assert db.get(EtlDispatchDomain, "audits").command_id is None


@pytest.mark.parametrize("which", ["command", "token", "generation"])
def test_actual_adapter_unknown_identity_never_invokes_runner(pg, monkeypatch, tmp_path, which):
    from admin_etl_dispatch_adapter import execute
    factory, engine, generation, identity, token, _ = running(pg)
    calls = inert_adapter(monkeypatch, tmp_path)
    args = [identity, token, generation]
    args[{"command": 0, "token": 1, "generation": 2}[which]] = uuid4()
    assert execute(factory, engine, *args) == 1
    assert calls == []
    with factory() as db:
        assert db.query(IngestionJob).count() == 0
        assert db.get(EtlDispatchCommand, identity).execution_started is False


def test_actual_adapter_empty_registry_never_invokes_runner(pg, monkeypatch, tmp_path):
    from admin_etl_dispatch_adapter import execute
    from seeding.registries import REGISTRY
    factory, engine, generation, identity, token, _ = running(pg)
    calls = inert_adapter(monkeypatch, tmp_path)
    monkeypatch.setattr(REGISTRY, "_handlers", {})
    assert execute(factory, engine, identity, token, generation) == 1
    assert calls == []
    with factory() as db:
        assert db.query(IngestionJob).count() == 0
        assert db.get(EtlDispatchCommand, identity).execution_started is False
