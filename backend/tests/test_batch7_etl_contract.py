"""Public dispatch contract: inert auth, no product lifespan or live transport."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import supabase_auth
from routers import etl_admin


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(supabase_auth, "_decode_supabase_jwt", lambda token: {"sub": token})
    monkeypatch.setattr(supabase_auth, "_fetch_roles", lambda uid: ("inert@example.invalid", ["admin"] if uid == "admin" else ["user"]))
    app = FastAPI()
    app.include_router(etl_admin.router)
    with TestClient(app) as value:
        yield value


AUTH = {"Authorization": "Bearer admin"}


def test_disabled_dispatch_is_an_explicit_private_capability(client):
    response = client.get("/api/v1/admin/etl/dispatch", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["evidence"] == "worker_dispatch"
    assert body["available"] is False and body["generation"] is None
    assert body["worker"]["status"] == "unavailable"
    assert set(body["sources"]) == {"treasury", "cob", "oag", "knbs", "opendata", "cra"}
    assert all(source["available"] is False for source in body["sources"].values())
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize("change", [
    {"dry_run": 1}, {"version": True}, {"version": 0}, {"version": 9007199254740992},
    {"source": "other"}, {"outcome": "completed"}, {"job_id": 1},
    {"started_at": "2026-10-09T12:00:00Z"}, {"created_at": "2026-10-09T12:00:00"},
    {"updated_at": "2026-10-08T12:00:00Z"}, {"status": "completed"},
])
def test_malformed_stored_receipt_is_rejected(change):
    from admin_etl_dispatch import Command
    from pydantic import ValidationError
    payload = {"id": "22222222-2222-4222-8222-222222222222", "source": "oag", "dry_run": False,
        "status": "queued", "version": 1, "created_at": "2026-10-09T12:00:00Z", "updated_at": "2026-10-09T12:00:00Z",
        "started_at": None, "finished_at": None, "job_id": None, "outcome": None}
    with pytest.raises(ValidationError):
        Command.model_validate({**payload, **change})


def test_outbound_receipts_and_capability_normalize_offsets_to_utc():
    from datetime import datetime, timedelta, timezone
    from uuid import UUID
    from admin_etl_dispatch import Command, DispatchCapability, WorkerCapability
    local = datetime(2026, 10, 9, 7, 0, tzinfo=timezone(timedelta(hours=-5)))
    command = Command(id=UUID("22222222-2222-4222-8222-222222222222"), source="oag", dry_run=False,
        status="queued", version=1, created_at=local, updated_at=local,
        started_at=None, finished_at=None, job_id=None, outcome=None)
    assert command.model_dump(mode="json")["created_at"] == "2026-10-09T12:00:00Z"
    capability = DispatchCapability(timestamp=local, evidence="worker_dispatch", available=False,
        reason="Unavailable", generation=None,
        worker=WorkerCapability(status="unavailable", last_seen_at=local, expires_at=local + timedelta(seconds=30)),
        sources={s: {"available": False, "reason": "Unavailable"} for s in etl_admin.VALID_SOURCES})
    body = capability.model_dump(mode="json")
    assert body["timestamp"] == body["worker"]["last_seen_at"] == "2026-10-09T12:00:00Z"
