"""Copilot review regressions, bounded to inert storage and native handlers."""
from datetime import datetime, timedelta, timezone
import os
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Uuid, create_engine, event, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable

import database
from admin_etl_dispatch import TriggerBody, accept
from admin_etl_dispatch_worker import claim, finish, register_worker
from models import (
    AdminAuditLog, Base, EtlDispatchCommand, EtlDispatchDomain, EtlDispatchWorker,
    IngestionJob, SeedingDomainClaim,
)
from routers import etl_admin
from supabase_auth import AdminUser, require_admin

ACTOR = AdminUser(id="batch7-review-admin", email="inert@example.invalid", roles=["admin"])
URL = "postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55485/batch7_etl_worker"
SCHEMA = "batch7_review_worker"


class UntouchedDatabase:
    def __getattr__(self, name):
        raise AssertionError("Disabled acceptance touched database: " + name)


@pytest.mark.parametrize("key", [None, str(uuid4()), "malformed"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_disabled_trigger_rejects_every_key_without_database_access(monkeypatch, key, dry_run):
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "false")
    with pytest.raises(HTTPException) as failure:
        accept(UntouchedDatabase(), ACTOR, "oag", TriggerBody(dry_run=dry_run), key)
    assert failure.value.status_code == 503
    assert failure.value.detail["code"] == "manual_dispatch_unavailable"
    assert "no-store" in failure.value.headers["Cache-Control"]


@pytest.mark.parametrize("source,body,status", [
    ("unknown", TriggerBody(), 404),
    ("oag", TriggerBody.model_construct(dry_run=1), 422),
    ("oag", TriggerBody.model_construct(dispatch_generation="malformed"), 422),
])
def test_disabled_validation_precedes_storage_and_preserves_contract(monkeypatch, source, body, status):
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "false")
    with pytest.raises(HTTPException) as failure:
        accept(UntouchedDatabase(), ACTOR, source, body, str(uuid4()))
    assert failure.value.status_code == status


def test_shared_sqlite_metadata_and_uuid_roundtrip(db_session):
    # Uses the repository's real Base fixture and its existing JSONB compile shim.
    engine = db_session.get_bind()
    assert set(inspect(engine).get_table_names()) == set(Base.metadata.tables)
    generation = uuid4()
    now = datetime.now(timezone.utc)
    row = EtlDispatchWorker(id=1, generation=generation, last_seen_at=now,
                            expires_at=now + timedelta(seconds=30), ready=True)
    db_session.add(row)
    db_session.flush()
    db_session.expire_all()
    loaded = db_session.get(EtlDispatchWorker, 1)
    assert type(loaded.generation) is UUID and loaded.generation == generation


@pytest.mark.parametrize("model", [EtlDispatchCommand, EtlDispatchWorker, EtlDispatchDomain])
def test_dispatch_uuid_columns_retain_native_postgres_ddl(model):
    ddl = str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
    assert "UUID" in ddl
    for column in model.__table__.columns:
        if isinstance(column.type, Uuid):
            assert str(column.type.compile(dialect=postgresql.dialect())) == "UUID"


@pytest.fixture
def review_pg(monkeypatch):
    if os.environ.get("BATCH7_ETL_REVIEW_DATABASE_URL") != URL:
        pytest.skip("Explicit owned review PostgreSQL required")
    engine = create_engine(URL, connect_args={"options": "-c search_path=" + SCHEMA})
    with engine.begin() as connection:
        connection.execute(text("CREATE SCHEMA " + SCHEMA))
    tables = [AdminAuditLog.__table__, IngestionJob.__table__, EtlDispatchCommand.__table__,
              EtlDispatchWorker.__table__, EtlDispatchDomain.__table__, SeedingDomainClaim.__table__]
    Base.metadata.create_all(engine, tables=tables)
    factory = sessionmaker(bind=engine)
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "true")
    monkeypatch.setattr(database, "SessionLocal", factory)
    app = FastAPI()
    app.include_router(etl_admin.router)
    app.dependency_overrides[require_admin] = lambda: ACTOR
    try:
        with TestClient(app) as client:
            yield client, factory, engine
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA " + SCHEMA + " CASCADE"))
        engine.dispose()


def post(client, generation, key, dry_run=False):
    return client.post("/api/v1/admin/etl/trigger/oag",
        json={"dry_run": dry_run, "dispatch_generation": str(generation)},
        headers={"Idempotency-Key": str(key)})


@pytest.mark.parametrize("replay", [False, True])
@pytest.mark.parametrize("dry_run", [False, True])
def test_disabled_keyed_http_request_preserves_running_receipt_and_audit(review_pg, monkeypatch, replay, dry_run):
    client, factory, engine = review_pg
    generation, original_key = register_worker(factory), uuid4()
    accepted = post(client, generation, original_key, dry_run)
    assert accepted.status_code == 202, accepted.text
    claimed = claim(factory, generation)
    assert claimed is not None
    with factory.begin() as db:
        db.execute(text("UPDATE etl_dispatch_worker SET last_seen_at=clock_timestamp()-interval '2 seconds', expires_at=clock_timestamp()-interval '1 second'"))
    with engine.connect() as connection:
        before = connection.execute(text("SELECT row_to_json(c)::text FROM etl_dispatch_commands c")).scalar_one()
        before_audit = connection.execute(text("SELECT row_to_json(a)::text FROM admin_audit_log a")).scalar_one()
    observed_sql = []
    observed_connections = []
    def sql(connection, cursor, statement, parameters, context, executemany):
        observed_sql.append(statement)
    def checkout(connection, record, proxy):
        observed_connections.append(connection)
    event.listen(engine, "before_cursor_execute", sql)
    event.listen(engine, "checkout", checkout)
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "false")
    try:
        result = post(client, generation, original_key if replay else uuid4(), dry_run)
    finally:
        event.remove(engine, "before_cursor_execute", sql)
        event.remove(engine, "checkout", checkout)
    with engine.connect() as connection:
        after = connection.execute(text("SELECT row_to_json(c)::text FROM etl_dispatch_commands c")).scalar_one()
        after_audit = connection.execute(text("SELECT row_to_json(a)::text FROM admin_audit_log a")).scalar_one()
    assert result.status_code == 503, result.text
    assert result.json()["detail"]["code"] == "manual_dispatch_unavailable"
    assert "no-store" in result.headers["cache-control"] and result.headers["vary"] == "Authorization"
    assert not observed_sql and not observed_connections
    assert after == before and after_audit == before_audit
    with factory() as db:
        assert db.get(EtlDispatchCommand, claimed[0]).status == "running"
        assert db.query(EtlDispatchCommand).count() == db.query(AdminAuditLog).count() == 1
        assert db.query(IngestionJob).count() == 0
    # Re-enabling recovers the original despite its expired worker generation.
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "true")
    recovered = post(client, uuid4(), original_key, dry_run)
    assert recovered.status_code == 202 and recovered.json()["replayed"] is True
    assert recovered.json()["command"]["id"] == accepted.json()["command"]["id"]
    assert recovered.json()["command"]["status"] == "interrupted"


@pytest.mark.parametrize("zone", ["UTC", "Africa/Nairobi"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_actual_adapter_observation_finishes_under_session_timezone(review_pg, monkeypatch, tmp_path, zone, dry_run):
    from admin_etl_dispatch_adapter import execute
    from seeding import cli
    from seeding.registries import REGISTRY, load_builtin_domains
    from seeding.types import DomainRunResult

    client, _, original_engine = review_pg
    offset_engine = create_engine(URL, connect_args={
        "options": "-c search_path=" + SCHEMA + " -c timezone=" + zone,
    })
    factory = sessionmaker(bind=offset_engine)
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setenv("SEED_STORAGE_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("SEED_CACHE_PATH", str(tmp_path / "cache"))
    load_builtin_domains()
    monkeypatch.setattr("seeding.registries.load_builtin_domains", lambda: None)
    monkeypatch.setattr(cli, "load_builtin_domains", lambda: None)
    monkeypatch.setattr(REGISTRY, "_handlers", {})
    with original_engine.begin() as connection:
        connection.execute(text("CREATE TABLE batch7_review_effects(value integer)"))
    def inert_audits(session, settings, context):
        session.execute(text("INSERT INTO batch7_review_effects VALUES (1)"))
        return DomainRunResult(domain="audits", dry_run=context.dry_run, items_processed=1, items_created=1)
    REGISTRY.register("audits", inert_audits)
    try:
        generation = register_worker(factory)
        result = post(client, generation, uuid4(), dry_run)
        assert result.status_code == 202, result.text
        claimed = claim(factory, generation)
        assert claimed is not None
        exit_code = execute(factory, offset_engine, *claimed, generation)
        assert exit_code == 0
        assert finish(factory, generation, *claimed, exit_code) is True
        with factory() as db:
            command = db.get(EtlDispatchCommand, claimed[0])
            assert command.status == command.outcome == "completed" and command.job_id is not None
            job = db.get(IngestionJob, command.job_id)
            assert job.dry_run is dry_run and job.meta["dispatch_command_id"] == str(command.id)
            assert db.scalar(text("SELECT count(*) FROM batch7_review_effects")) == (0 if dry_run else 1)
            assert db.scalar(text("SHOW TimeZone")) == zone
    finally:
        offset_engine.dispose()
