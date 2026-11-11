"""Mounted admin API -> durable intent -> adapter -> CLI -> fenced finish.

Requires an explicitly supplied owned PostgreSQL fixture. No consumer process is
started. Auth-provider responses and the domain handler are inert boundaries;
all acceptance, claim, adapter, CLI, job and finish transactions are real.
"""
from datetime import timedelta
import os
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

import database
import supabase_auth
from admin_etl_dispatch_adapter import execute
from admin_etl_dispatch_worker import claim, finish
from models import (AdminAuditLog, Base, EtlDispatchCommand, EtlDispatchDomain,
                    EtlDispatchWorker, IngestionJob, IngestionStatus, SeedingDomainClaim)
from routers import etl_admin
from seeding import freshness
from seeding.registries import REGISTRY
from seeding.types import DomainRunResult

URL = os.environ.get("CLI_RESULT_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Explicit isolated PostgreSQL fixture required")
TABLES = [m.__table__ for m in (IngestionJob, AdminAuditLog, EtlDispatchCommand,
                               EtlDispatchDomain, EtlDispatchWorker, SeedingDomainClaim)]


@pytest.fixture
def pg(monkeypatch, tmp_path):
    if URL != "postgresql+psycopg2://postgres@127.0.0.1:62124/social_domain_test":
        pytest.fail("Unknown PostgreSQL target refused")
    schema = "cli_result_" + uuid4().hex
    admin_engine = create_engine(URL)
    with admin_engine.begin() as conn:
        assert conn.scalar(text("SELECT current_database()")) == "social_domain_test"
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(URL, connect_args={"options": f"-csearch_path={schema}"})
    Base.metadata.create_all(engine, tables=TABLES)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "true")  # owned fixture only
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_SOURCES", "oag")
    for flag in ("SOCIAL_GENERATION_HOOK_ENABLED", "SOCIAL_REPORT_GENERATION_ENABLED"):
        monkeypatch.setenv(flag, "false")
    monkeypatch.setenv("SEED_STORAGE_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("SEED_CACHE_PATH", str(tmp_path / "cache"))
    monkeypatch.setattr(supabase_auth, "_decode_supabase_jwt", lambda token: {"sub": token})
    monkeypatch.setattr(supabase_auth, "_fetch_roles", lambda _uid: ("fixture@example.invalid", ["admin"]))
    app = FastAPI()
    app.include_router(etl_admin.router)
    generation = uuid4()
    with factory.begin() as db:
        now = db.scalar(text("SELECT clock_timestamp()"))
        db.add(EtlDispatchWorker(id=1, generation=generation, ready=True,
                               last_seen_at=now, expires_at=now + timedelta(seconds=30)))
        db.add(EtlDispatchDomain(domain="audits", ready=True))
    try:
        with TestClient(app) as client:
            yield client, factory, engine, generation
    finally:
        engine.dispose()
        with admin_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


def accepted(pg):
    client, factory, _engine, generation = pg
    key = str(uuid4())
    response = client.post('/api/v1/admin/etl/trigger/oag',
        json={"dry_run": False, "dispatch_generation": str(generation)},
        headers={"Authorization": "Bearer fixture-admin", "Idempotency-Key": key})
    assert response.status_code == 202, response.text
    command_id = UUID(response.json()["command"]["id"])
    # Observe durability through another session before claiming.
    with factory() as db:
        assert db.get(EtlDispatchCommand, command_id).status == "queued"
    selected_id, token = claim(factory, generation)
    assert selected_id == command_id
    return command_id, token, key


@pytest.mark.parametrize("outcome", ["none", "empty", "wrong-domain", "bool-counter", "overcount", "exception", "valid", "unchanged", "partial-errors"])
@pytest.mark.parametrize("early_commit", [False, True])
def test_admin_command_cannot_finish_green_for_bad_handler_result(pg, monkeypatch, outcome, early_commit):
    client, factory, engine, generation = pg
    def handler(session, context, **_kwargs):
        freshness.mark_live("audits")
        session.add(AdminAuditLog(actor_id="fixture-effect", action="fixture.effect", payload={}))
        session.flush()
        if early_commit:
            session.commit()
        if outcome == "exception":
            raise RuntimeError("fixture handler failed")
        if outcome == "none":
            return None
        result = DomainRunResult(domain="audits", items_processed=2,
                                 items_created=0 if outcome == "unchanged" else 1)
        if outcome == "empty":
            return DomainRunResult(domain="audits")
        return result.model_copy(update={
            "wrong-domain": {"domain": "population"}, "bool-counter": {"items_processed": True},
            "overcount": {"items_created": 2, "items_updated": 1},
            "partial-errors": {"errors": ["known partial acquisition"]},
        }.get(outcome, {}))
    # Actual audits module is imported before replacing its registry handler.
    from seeding.domains.audits import scope  # noqa: F401
    monkeypatch.setattr(REGISTRY, "_handlers", {"audits": handler})
    command_id, token, key = accepted(pg)
    rc = execute(factory, engine, command_id, token, generation)
    valid = outcome in {"valid", "unchanged", "partial-errors"}
    assert rc == (0 if valid else 1)
    assert finish(factory, generation, command_id, token, rc) is True
    # A replay is a readback of the original command, never a second handler.
    replay = client.post('/api/v1/admin/etl/trigger/oag',
        json={"dry_run": False, "dispatch_generation": str(generation)},
        headers={"Authorization": "Bearer fixture-admin", "Idempotency-Key": key})
    assert replay.status_code == 202 and replay.json()["replayed"] is True
    with factory() as db:
        job = db.scalars(select(IngestionJob)).one()
        command = db.get(EtlDispatchCommand, command_id)
        completed = outcome in {"valid", "unchanged"}
        assert command.status == command.outcome == ("completed" if completed else "failed")
        assert command.job_id == job.id and job.finished_at is not None
        assert job.status == (IngestionStatus.COMPLETED_WITH_ERRORS if outcome == "partial-errors" else
                              IngestionStatus.COMPLETED if completed else IngestionStatus.FAILED)
        assert job.items_processed == (2 if valid else 0)
        assert bool(job.errors) is (not completed)
        assert db.query(AdminAuditLog).filter_by(action="fixture.effect").count() == int(valid or early_commit)
        ownership = db.get(SeedingDomainClaim, token)
        assert ownership.returned_at is not None and ownership.released_at is not None
        assert db.get(EtlDispatchDomain, "audits").command_id is None


def test_cancellation_keeps_durable_command_and_ownership_uncertain(pg, monkeypatch):
    _client, factory, engine, generation = pg
    held = []
    def handler(session, **_kwargs):
        held.append(session)
        session.add(AdminAuditLog(actor_id="fixture-effect", action="fixture.effect", payload={}))
        session.flush()
        raise KeyboardInterrupt("fixture cancellation")
    from seeding.domains.audits import scope  # noqa: F401
    monkeypatch.setattr(REGISTRY, "_handlers", {"audits": handler})
    command_id, token, _ = accepted(pg)
    with pytest.raises(KeyboardInterrupt):
        execute(factory, engine, command_id, token, generation)
    # Even a caller trying to commit the returned session cannot save the effect.
    held[0].commit()
    assert finish(factory, generation, command_id, token, 0) is False
    with factory() as db:
        assert db.query(AdminAuditLog).filter_by(action="fixture.effect").count() == 0
        assert db.get(EtlDispatchCommand, command_id).status == "interrupted"
        assert db.get(EtlDispatchDomain, "audits").command_id == command_id
        ownership = db.get(SeedingDomainClaim, token)
        assert ownership.returned_at is None and ownership.released_at is None
        assert db.scalars(select(IngestionJob)).one().status == IngestionStatus.RUNNING


@pytest.mark.parametrize("fault", ["reject", "rewrite"])
def test_terminal_persistence_failure_retains_authority_and_cannot_finish_green(pg, monkeypatch, fault):
    _client, factory, engine, generation = pg
    held = []
    def handler(session, **_kwargs):
        held.append(session)
        freshness.mark_live("audits")
        session.add(AdminAuditLog(actor_id="fixture-effect", action="fixture.effect", payload={}))
        return DomainRunResult(domain="audits", items_processed=1, items_created=1)
    from seeding.domains.audits import scope  # noqa: F401
    monkeypatch.setattr(REGISTRY, "_handlers", {"audits": handler})
    command_id, token, _ = accepted(pg)
    with engine.begin() as conn:
        body = ("RAISE EXCEPTION 'fixture terminal refusal';" if fault == "reject" else
                "NEW.status := 'RUNNING'; RETURN NEW;")
        conn.execute(text("CREATE FUNCTION fixture_terminal_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN " + body + " END $$"))
        conn.execute(text("CREATE TRIGGER fixture_terminal_fault BEFORE UPDATE ON ingestion_jobs FOR EACH ROW EXECUTE FUNCTION fixture_terminal_fault()"))
    assert execute(factory, engine, command_id, token, generation) == 1
    held[0].commit()
    assert finish(factory, generation, command_id, token, 0) is False
    with factory() as db:
        assert db.scalars(select(IngestionJob)).one().status == IngestionStatus.RUNNING
        assert db.get(EtlDispatchCommand, command_id).status == "interrupted"
        assert db.get(EtlDispatchDomain, "audits").command_id == command_id
        ownership = db.get(SeedingDomainClaim, token)
        assert ownership.returned_at is None and ownership.released_at is None
        # Rewritten successful commits may retain effects. A rejected commit
        # cannot; neither case authorizes a successful command or claim release.
        assert db.query(AdminAuditLog).filter_by(action="fixture.effect").count() == int(fault == "rewrite")
