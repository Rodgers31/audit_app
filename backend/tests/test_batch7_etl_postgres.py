"""Native PostgreSQL acceptance/lease interleavings on an explicitly owned DB."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import database
import supabase_auth
from admin_etl_dispatch import accept, command_history, TriggerBody
from admin_etl_dispatch_worker import claim, finish, heartbeat, register_worker
from models import AdminAuditLog, EtlDispatchCommand, EtlDispatchDomain, EtlDispatchWorker, IngestionJob, IngestionStatus
from routers import etl_admin

URL = os.environ.get("BATCH7_ETL_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Owned PostgreSQL required")
AUTH = {"Authorization": "Bearer admin"}


@pytest.fixture
def pg(monkeypatch):
    assert URL == "postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55481/batch7_etl_worker"
    engine = create_engine(URL)
    factory = sessionmaker(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE etl_dispatch_domains, etl_dispatch_commands, etl_dispatch_worker, admin_audit_log, ingestion_jobs RESTART IDENTITY CASCADE"))
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "true")
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr(supabase_auth, "_decode_supabase_jwt", lambda token: {"sub": token})
    monkeypatch.setattr(supabase_auth, "_fetch_roles", lambda uid: ("inert@example.invalid", ["admin"] if uid in ("admin", "admin2") else ["user"]))
    app = FastAPI()
    app.include_router(etl_admin.router)
    with TestClient(app) as client:
        yield client, factory, engine
    engine.dispose()


def post(client, generation, key=None, dry_run=False, source="oag", actor="admin"):
    return client.post("/api/v1/admin/etl/trigger/" + source,
        json={"dry_run": dry_run, "dispatch_generation": str(generation)},
        headers={"Authorization": "Bearer " + actor, "Idempotency-Key": str(key or uuid4())})


def expire(factory):
    with factory.begin() as db:
        db.execute(text("UPDATE etl_dispatch_worker SET expires_at=clock_timestamp()-interval '1 second', last_seen_at=clock_timestamp()-interval '2 seconds'"))


def test_acceptance_is_durable_and_replay_survives_lost_ack_expiry(pg):
    client, factory, _ = pg
    generation = register_worker(factory)
    key = uuid4()
    first = post(client, generation, key)
    assert first.status_code == 202, first.text
    command = first.json()["command"]
    assert command["status"] == "queued" and command["version"] == 1
    # The caller loses the response after commit, then retries after lease loss.
    expire(factory)
    second = post(client, generation, key)
    assert second.status_code == 202 and second.json()["replayed"] is True
    assert second.json()["command"] == command
    assert post(client, generation, key, dry_run=True).status_code == 409
    assert post(client, generation, key, source="knbs").status_code == 409
    assert post(client, generation).status_code == 503
    with factory() as db:
        assert db.query(EtlDispatchCommand).count() == db.query(AdminAuditLog).count() == 1
        assert db.query(IngestionJob).count() == 0
        audit = db.query(AdminAuditLog).one()
        assert audit.action == "etl.trigger" and audit.target_id == command["id"]
        assert audit.payload == {"dry_run": False}


def test_two_duplicate_accepts_and_actor_isolation(pg):
    client, factory, _ = pg
    generation = register_worker(factory)
    barrier, key = Barrier(2), uuid4()
    actor = supabase_auth.AdminUser(id="admin", email="inert@example.invalid", roles=["admin"])
    def competing():
        barrier.wait(timeout=5)
        with factory() as db:
            return accept(db, actor, "oag", TriggerBody(dispatch_generation=str(generation)), str(key))
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: competing(), range(2)))
    assert {r.replayed for r in results} == {True, False}
    assert results[0].command.id == results[1].command.id
    other = post(client, generation, key, actor="admin2")
    assert other.status_code == 202 and other.json()["command"]["id"] != str(results[0].command.id)
    with factory() as db:
        assert db.query(AdminAuditLog).count() == db.query(EtlDispatchCommand).count() == 2


def test_atomic_audit_failure_has_no_command_or_success(pg):
    client, factory, engine = pg
    generation = register_worker(factory)
    with engine.begin() as conn:
        conn.execute(text("CREATE FUNCTION batch7_reject_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'INERT_PRIVATE_DIAGNOSTIC'; END $$"))
        conn.execute(text("CREATE TRIGGER batch7_reject_audit BEFORE INSERT ON admin_audit_log FOR EACH ROW EXECUTE FUNCTION batch7_reject_audit()"))
    try:
        result = post(client, generation)
        assert result.status_code == 503 and "INERT_PRIVATE_DIAGNOSTIC" not in result.text
        with factory() as db:
            assert db.query(AdminAuditLog).count() == db.query(EtlDispatchCommand).count() == 0
    finally:
        with engine.begin() as conn:
            conn.execute(text("DROP TRIGGER batch7_reject_audit ON admin_audit_log"))
            conn.execute(text("DROP FUNCTION batch7_reject_audit()"))


def test_two_consumers_never_claim_same_domain_and_restart_fences_old(pg):
    client, factory, _ = pg
    generation = register_worker(factory)
    first = post(client, generation).json()["command"]["id"]
    second = post(client, generation).json()["command"]["id"]
    barrier = Barrier(2)
    def competing():
        barrier.wait(timeout=5)
        return claim(factory, generation)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: competing(), range(2)))
    owned = next(value for value in results if value)
    assert sum(value is not None for value in results) == 1
    assert str(owned[0]) == first
    assert heartbeat(factory, generation) is True
    expire(factory)
    assert heartbeat(factory, generation) is False
    restarted = register_worker(factory)
    assert restarted != generation and finish(factory, generation, *owned, 0) is False
    assert claim(factory, restarted) is None
    receipt = client.get("/api/v1/admin/etl/commands/" + first, headers=AUTH).json()
    assert receipt["status"] == "interrupted" and receipt["outcome"] == "execution_unverified"
    assert client.get("/api/v1/admin/etl/commands/" + second, headers=AUTH).json()["status"] == "queued"
    with factory() as db:
        assert db.get(EtlDispatchDomain, "audits").command_id == owned[0]


def test_generation_strict_inputs_privacy_auth_and_history(pg):
    client, factory, _ = pg
    generation = register_worker(factory)
    ready = client.get("/api/v1/admin/etl/dispatch", headers=AUTH).json()
    assert ready["available"] is True and ready["generation"] == str(generation)
    assert ready["sources"]["oag"]["available"] is True
    assert sum(value["available"] for value in ready["sources"].values()) == 1
    assert post(client, uuid4()).status_code == 409
    assert post(client, generation, source="knbs").status_code == 503
    for path in ("dispatch", "commands", "commands/" + str(uuid4())):
        assert client.get("/api/v1/admin/etl/" + path).status_code == 401
        assert client.get("/api/v1/admin/etl/" + path, headers={"Authorization": "Bearer user"}).status_code == 403
    for body in ({"dry_run": 1}, {"dry_run": "false"}, {"extra": "INERT_PRIVATE_DIAGNOSTIC"}, {"dispatch_generation": {}}, {"dispatch_generation": str(generation).upper()}):
        result = client.post("/api/v1/admin/etl/trigger/oag", json=body, headers=AUTH)
        assert result.status_code == 422 and "INERT_PRIVATE_DIAGNOSTIC" not in result.text
    assert client.post("/api/v1/admin/etl/trigger/oag", json={}, headers=AUTH).status_code == 422
    identifiers = [post(client, generation, dry_run=bool(n % 2)).json()["command"]["id"] for n in range(3)]
    result = client.get("/api/v1/admin/etl/commands?page_size=2", headers=AUTH)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["total"] == 3 and body["has_more"] is True
    assert [row["id"] for row in body["entries"]] == identifiers[::-1][:2]
    assert client.get("/api/v1/admin/etl/commands?page=2&page_size=2", headers=AUTH).json()["entries"][0]["id"] == identifiers[0]
    assert client.get("/api/v1/admin/etl/commands?status=completed", headers=AUTH).json()["total"] == 0
    assert client.get("/api/v1/admin/etl/commands?page=10000", headers=AUTH).json()["total"] == 3
    for query in ("page=0", "page_size=51", "source=other", "status=secret", "page=true"):
        response = client.get("/api/v1/admin/etl/commands?" + query, headers=AUTH)
        assert response.status_code == 422 and response.headers["vary"] == "Authorization"


def test_storage_failures_do_not_fabricate_empty_history(pg):
    client, _, engine = pg
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE etl_dispatch_commands RENAME TO batch7_hidden_commands"))
    try:
        response = client.get("/api/v1/admin/etl/commands", headers=AUTH)
        assert response.status_code == 503 and response.json() == {"detail": "Operations data unavailable"}
    finally:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE batch7_hidden_commands RENAME TO etl_dispatch_commands"))


def test_lease_expiry_polling_interrupts_without_clearing_exclusion(pg):
    client, factory, _ = pg
    generation = register_worker(factory)
    identity = post(client, generation).json()["command"]["id"]
    claimed = claim(factory, generation)
    expire(factory)
    final = client.get("/api/v1/admin/etl/commands/" + identity, headers=AUTH).json()
    assert final["status"] == "interrupted" and final["version"] == 3
    assert finish(factory, generation, *claimed, 0) is False
    with factory() as db:
        assert str(db.get(EtlDispatchDomain, "audits").command_id) == identity


def test_exit_zero_without_matching_runner_observation_is_uncertain(pg):
    client, factory, _ = pg
    generation = register_worker(factory)
    identity = post(client, generation).json()["command"]["id"]
    claimed = claim(factory, generation)
    assert finish(factory, generation, *claimed, 0) is False
    final = client.get("/api/v1/admin/etl/commands/" + identity, headers=AUTH).json()
    assert final["status"] == "interrupted" and final["job_id"] is None
    assert claim(factory, generation) is None


@pytest.mark.parametrize("page,size", [(True, 20), (1, False), (1, 51), (0, 20), (float('nan'), 20), (float('inf'), 20), (None, 20)])
def test_direct_history_call_cannot_bypass_bounds(pg, page, size):
    from fastapi import HTTPException
    _, factory, _ = pg
    with factory() as db, pytest.raises(HTTPException) as failure:
        command_history(db, page, size)
    assert failure.value.status_code == 422


def test_empty_registry_cannot_run_native_adapter(pg, monkeypatch):
    from admin_etl_dispatch_adapter import execute
    from seeding.registries import REGISTRY
    client, factory, engine = pg
    generation = register_worker(factory)
    identity = post(client, generation).json()["command"]["id"]
    claimed = claim(factory, generation)
    monkeypatch.setattr(REGISTRY, "_handlers", {})
    monkeypatch.setattr("seeding.registries.load_builtin_domains", lambda: None)
    assert execute(factory, engine, *claimed, generation) == 1
    with factory() as db:
        assert db.query(IngestionJob).count() == 0


def test_capability_transaction_failure_cannot_certify_ready(pg, monkeypatch):
    from sqlalchemy.orm import Session
    client, factory, engine = pg
    register_worker(factory)
    class FailingCommit(Session):
        def commit(self):
            raise RuntimeError("Inert commit failure")
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine, class_=FailingCommit))
    result = client.get("/api/v1/admin/etl/dispatch", headers=AUTH)
    assert result.status_code == 200
    body = result.json()
    assert body["available"] is False and body["generation"] is None
    assert body["worker"]["status"] == "unavailable"
    assert all(source["available"] is False for source in body["sources"].values())


def test_post_commit_acknowledgment_failure_recovers_original_acceptance(pg, monkeypatch):
    from sqlalchemy.orm import Session
    client, factory, engine = pg
    generation, key = register_worker(factory), uuid4()
    class LostAcknowledgment(Session):
        def commit(self):
            super().commit()
            raise RuntimeError("Inert lost acknowledgment after durable commit")
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine, class_=LostAcknowledgment))
    first = post(client, generation, key)
    assert first.status_code == 503
    monkeypatch.setattr(database, "SessionLocal", factory)
    expire(factory)
    recovered = post(client, uuid4(), key)
    assert recovered.status_code == 202 and recovered.json()["replayed"] is True
    with factory() as db:
        assert db.query(EtlDispatchCommand).count() == db.query(AdminAuditLog).count() == 1
        assert str(db.query(EtlDispatchCommand).one().id) == recovered.json()["command"]["id"]


def test_postgres_non_utc_session_returns_only_utc_wire_timestamps(pg, monkeypatch):
    client, factory, _ = pg
    generation = register_worker(factory)
    offset_engine = create_engine(URL, connect_args={"options": "-c timezone=America/Chicago"})
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=offset_engine))
    try:
        ready = client.get("/api/v1/admin/etl/dispatch", headers=AUTH).json()
        assert ready["timestamp"].endswith("Z") and ready["worker"]["last_seen_at"].endswith("Z")
        assert ready["worker"]["expires_at"].endswith("Z")
        accepted = post(client, generation).json()["command"]
        assert accepted["created_at"].endswith("Z") and accepted["updated_at"].endswith("Z")
    finally:
        offset_engine.dispose()
