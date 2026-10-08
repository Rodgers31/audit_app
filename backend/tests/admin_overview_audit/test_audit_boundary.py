"""Actual audit router and caller boundaries, using isolated SQLite and inert providers."""
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database
import supabase_admin
from database import get_db
from models import AdminAuditLog, IngestionJob
from routers import admin_audit_log, admin_users, etl_admin
from supabase_auth import AdminUser, get_current_user
from utils.audit import record_admin_action

ACTOR = AdminUser(id="00000000-0000-4000-8000-000000000001", email="admin@example.invalid", roles=["admin"])


@pytest.fixture()
def audit_env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'audit.sqlite'}", connect_args={"check_same_thread": False})
    AdminAuditLog.__table__.create(engine)
    IngestionJob.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "SessionLocal", factory)
    app = FastAPI()
    app.include_router(admin_audit_log.router)
    app.include_router(admin_users.router)
    app.include_router(etl_admin.router)
    app.dependency_overrides[get_current_user] = lambda: ACTOR
    def sessions():
        with factory() as session:
            yield session
    app.dependency_overrides[get_db] = sessions
    app.dependency_overrides[etl_admin._db_dep] = sessions
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, factory, app
    engine.dispose()


def insert(factory, **kwargs):
    with factory() as session:
        row = AdminAuditLog(actor_id=ACTOR.id, action="etl.trigger", payload={"job_id": 1, "dry_run": False}, created_at=datetime(2026, 1, 1), **kwargs)
        session.add(row)
        session.commit()


def test_order_is_stable_on_equal_timestamps(audit_env):
    client, factory, _ = audit_env
    insert(factory, id=1)
    insert(factory, id=2)
    response = client.get("/api/v1/admin/audit-log?days=0&page_size=1")
    assert response.json()["entries"][0]["id"] == 2


def test_snapshot_excludes_later_backdated_insert(audit_env):
    client, factory, _ = audit_env
    insert(factory, id=1)
    insert(factory, id=2)
    first = client.get("/api/v1/admin/audit-log?days=0&page_size=1").json()
    assert "snapshot_id" in first and "as_of" in first
    insert(factory, id=3)
    second = client.get("/api/v1/admin/audit-log", params={"days": 0, "page_size": 1, "page": 2, "snapshot_id": first["snapshot_id"], "as_of": first["as_of"]}).json()
    assert [r["id"] for r in second["entries"]] == [1]
    assert second["total"] == first["total"] == 2


@pytest.mark.parametrize("query", ["days=999999999", "page=10001", "page_size=101", "action=" + "a" * 81])
def test_filters_are_bounded_and_errors_private(audit_env, query):
    client, _, _ = audit_env
    response = client.get("/api/v1/admin/audit-log?" + query)
    assert response.status_code == 422
    assert response.headers.get("cache-control") == "private, no-store"


def test_private_success_and_authorization(audit_env):
    client, _, app = audit_env
    assert client.get("/api/v1/admin/audit-log").headers.get("cache-control") == "private, no-store"
    app.dependency_overrides[get_current_user] = lambda: AdminUser(id=ACTOR.id, email=None, roles=["citizen"])
    response = client.get("/api/v1/admin/audit-log")
    assert response.status_code == 403
    assert response.headers.get("cache-control") == "private, no-store"
    app.dependency_overrides.pop(get_current_user)
    assert client.get("/api/v1/admin/audit-log").status_code == 401


def test_absent_storage_is_unavailable_not_empty(audit_env):
    client, factory, _ = audit_env
    AdminAuditLog.__table__.drop(factory.kw["bind"])
    response = client.get("/api/v1/admin/audit-log")
    assert response.status_code == 503
    assert response.json() == {"detail": "Audit evidence is unavailable."}
    assert response.headers.get("cache-control") == "private, no-store"


def test_legacy_payload_is_redacted_on_read(audit_env):
    client, factory, _ = audit_env
    with factory() as session:
        session.add(AdminAuditLog(actor_id=ACTOR.id, action="users.send_reset", payload={"email": "inert@example.invalid", "redirect_to": "https://example.invalid/reset?token=INERT_SECRET", "password": "INERT_SECRET", "nested": {"access_token": "INERT_SECRET"}}))
        session.commit()
    response = client.get("/api/v1/admin/audit-log?days=0")
    assert response.status_code == 200
    assert "INERT_SECRET" not in response.text
    assert response.json()["entries"][0]["payload"]["email"] == "inert@example.invalid"


def test_actual_reset_caller_persists_safe_payload(audit_env, monkeypatch):
    client, factory, _ = audit_env
    monkeypatch.setattr(supabase_admin, "get_user", lambda _: {"email": "inert@example.invalid"})
    provider = Mock()
    monkeypatch.setattr(supabase_admin, "generate_recovery_link", provider)
    response = client.post("/api/v1/admin/users/00000000-0000-4000-8000-000000000002/send-reset", json={"redirect_to": "https://example.invalid/reset?token=INERT_SECRET#INERT_SECRET"})
    assert response.status_code == 200
    provider.assert_called_once()
    with factory() as session:
        row = session.query(AdminAuditLog).one()
        assert "INERT_SECRET" not in str(row.payload)


def test_recording_failure_never_logs_parameters_or_poison_caller(audit_env, monkeypatch, caplog):
    client, _, _ = audit_env
    audit_db = Mock()
    audit_db.commit.side_effect = RuntimeError("SQL parameters: INERT_SECRET")
    monkeypatch.setattr(database, "SessionLocal", lambda: audit_db)
    monkeypatch.setattr(supabase_admin, "get_user", lambda _: {"email": "inert@example.invalid"})
    monkeypatch.setattr(supabase_admin, "generate_recovery_link", Mock())
    assert client.post("/api/v1/admin/users/inert/send-reset", json={}).status_code == 200
    assert "Failed to write admin_audit_log row" in caplog.text
    assert "INERT_SECRET" not in caplog.text
    audit_db.rollback.assert_called_once()
    audit_db.close.assert_called_once()


def test_independent_transaction_and_unknown_payload(audit_env):
    _, factory, _ = audit_env
    with factory() as caller:
        record_admin_action(caller, actor=ACTOR, action="future.action", payload={"anything": "INERT_SECRET"})
        caller.rollback()
    with factory() as observer:
        row = observer.query(AdminAuditLog).one()
        assert "INERT_SECRET" not in str(row.payload)


def test_actual_role_delete_and_etl_callers(audit_env, monkeypatch):
    client, factory, _ = audit_env
    target = "00000000-0000-4000-8000-000000000002"
    monkeypatch.setattr(supabase_admin, "get_profile", lambda _: {"roles": ["citizen"]})
    monkeypatch.setattr(supabase_admin, "get_profiles", lambda _: [{"id": target, "roles": ["admin"]}])
    monkeypatch.setattr(supabase_admin, "get_user", lambda _: {"id": target, "email": "inert@example.invalid", "created_at": "2026-01-01T00:00:00Z"})
    roles, deletion = Mock(), Mock()
    monkeypatch.setattr(supabase_admin, "update_profile_roles", roles)
    monkeypatch.setattr(supabase_admin, "delete_user", deletion)
    assert client.patch(f"/api/v1/admin/users/{target}/roles", json={"roles": ["admin"]}).status_code == 200
    assert client.delete(f"/api/v1/admin/users/{target}").status_code == 200
    assert client.post("/api/v1/admin/etl/trigger/cob", json={"dry_run": True}).status_code == 200
    roles.assert_called_once()
    deletion.assert_called_once()
    with factory() as db:
        rows = {r.action: r for r in db.query(AdminAuditLog).all()}
        assert rows["users.update_roles"].payload == {"old": ["citizen"], "new": ["admin"]}
        assert rows["users.delete"].payload["deleted_email"] == "inert@example.invalid"
        assert rows["etl.trigger"].payload == {"job_id": 1, "dry_run": True}
        assert db.query(IngestionJob).one().status.value == "pending"
    assert client.delete(f"/api/v1/admin/users/{ACTOR.id}").status_code == 400
    assert client.post("/api/v1/admin/etl/trigger/unknown").status_code == 404
    with factory() as db:
        assert db.query(AdminAuditLog).count() == 3


def test_exact_filters_date_ranges_and_snapshot_pairs(audit_env):
    client, factory, _ = audit_env
    insert(factory, id=1, target_type="etl_source", target_id="cob")
    params = {"days": 0, "actor_id": ACTOR.id, "action": "etl.trigger", "target_type": "etl_source", "target_id": "cob", "since": "2025-12-31T23:00:00Z", "until": "2026-01-01T01:00:00Z"}
    result = client.get("/api/v1/admin/audit-log", params=params)
    assert result.status_code == 200 and result.json()["total"] == 1
    params["target_id"] = "other"
    assert client.get("/api/v1/admin/audit-log", params=params).json()["total"] == 0
    for query in ("snapshot_id=1", "as_of=2026-01-01T00:00:00Z", "as_of=9999-01-01T00:00:00Z&snapshot_id=1", "since=2026-02-01T00:00:00Z&until=2026-01-01T00:00:00Z"):
        assert client.get("/api/v1/admin/audit-log?" + query).status_code == 422


@pytest.mark.parametrize("field,value", [("as_of", "9999-12-31T23:59:59-23:59"), ("since", "9999-12-31T23:59:59-23:59"), ("until", "0001-01-01T00:00:00+23:59")])
def test_timezone_overflow_is_invalid_filter_not_storage_outage(audit_env, field, value):
    client, _, _ = audit_env
    assert client.get('/api/v1/admin/audit-log', params={field: value}).status_code == 422


def test_actual_caller_drops_malformed_email_evidence(audit_env, monkeypatch):
    client, factory, _ = audit_env
    monkeypatch.setattr(supabase_admin, "get_user", lambda _: {"email": "inert@example.invalid\0INERT_SECRET"})
    monkeypatch.setattr(supabase_admin, "generate_recovery_link", Mock())
    assert client.post('/api/v1/admin/users/inert/send-reset', json={}).status_code == 200
    with factory() as db:
        assert 'INERT_SECRET' not in str(db.query(AdminAuditLog).one().payload)
