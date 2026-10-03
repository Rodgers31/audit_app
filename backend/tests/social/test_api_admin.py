import os
from uuid import UUID, uuid4

# Explicit isolated local config before importing the existing DB dependency.
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:social_local_test@127.0.0.1:62124/social_domain_test"

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from social.api import get_db, require_admin, router, service
from social.service import SocialService
from supabase_auth import AdminUser
from test_domain_support import ACTOR, account, db, draft_body


def make_client(engine, *, authenticated=True, actor=ACTOR, adapters=()):
    app = FastAPI()
    app.include_router(router)
    def isolated_db():
        with Session(engine, expire_on_commit=False) as session:
            yield session
    app.dependency_overrides[get_db] = isolated_db
    if authenticated:
        app.dependency_overrides[require_admin] = lambda: AdminUser(id=str(actor), email=None, roles=["admin"])
    if adapters:
        from fastapi import Depends
        def fake_service(db=Depends(get_db)):
            return SocialService(db, available_adapters=adapters)
        app.dependency_overrides[service] = fake_service
    return TestClient(app, raise_server_exceptions=False)


def key():
    return {"Idempotency-Key": str(uuid4())}


def test_auth_errors_and_validation_have_no_store(db):
    client = make_client(db.bind, authenticated=False)
    response = client.get("/api/v1/admin/social/posts")
    assert response.status_code in {401, 403}
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["detail"]["code"] in {"AUTHENTICATION_REQUIRED", "PERMISSION_DENIED"}
    client = make_client(db.bind)
    for data in [{"title": "x", "origin_type": "generated", "document": {"master": {}}}, {"title": "x", "document": {"schema_version": True, "master": {}}}]:
        response = client.post("/api/v1/admin/social/posts", json=data, headers=key())
        assert response.status_code == 422
        assert response.headers["cache-control"] == "private, no-store"
        assert response.json()["detail"]["code"] == "INVALID_REQUEST"
        UUID(response.json()["detail"]["request_id"])
    response = client.post("/api/v1/admin/social/posts", json=draft_body().model_dump(mode="json"))
    assert response.status_code == 422  # every mutation requires a UUID key.


def test_create_replay_patch_get_compact_list(db):
    client = make_client(db.bind)
    headers = key()
    body = draft_body().model_dump(mode="json")
    response = client.post("/api/v1/admin/social/posts", json=body, headers=headers)
    assert response.status_code == 201, response.text
    original = response.json()
    repeated = client.post("/api/v1/admin/social/posts", json=body, headers=headers)
    assert repeated.json() == original
    changed = client.post("/api/v1/admin/social/posts", json={**body, "title": "Changed"}, headers=headers)
    assert changed.status_code == 409
    assert changed.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"
    detail = client.get("/api/v1/admin/social/posts/" + original["id"])
    assert detail.status_code == 200
    assert detail.headers["cache-control"] == "private, no-store"
    edit = client.patch("/api/v1/admin/social/posts/" + original["id"], json={"expected_version": 1, "title": "Edited"}, headers=key())
    assert edit.status_code == 200
    assert edit.json()["version"] == 2
    stale = client.patch("/api/v1/admin/social/posts/" + original["id"], json={"expected_version": 1, "title": "Overwrite"}, headers=key())
    assert stale.status_code == 409
    listing = client.get("/api/v1/admin/social/posts?page_size=1")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert "document" not in listing.json()["posts"][0]
    invalid = client.get("/api/v1/admin/social/posts?page_size=101")
    assert invalid.status_code == 422
    assert invalid.headers["cache-control"] == "private, no-store"


def test_no_accounts_schema_errors_status_are_truthful(db):
    client = make_client(db.bind)
    assert client.get("/api/v1/admin/social/accounts").json() == {"accounts": []}
    status = client.get("/api/v1/admin/social/system/status").json()
    assert status["publishing_enabled"] is False
    assert status["worker"]["state"] == "unavailable"
    assert status["adapters_available"] == []
    assert status["media_upload_available"] is False
    platforms = client.get("/api/v1/admin/social/platforms").json()["platforms"]
    assert len(platforms) == 5
    assert all(p["capabilities"]["eligible"] is False for p in platforms)
    missing = client.get("/api/v1/admin/social/posts/" + str(uuid4()))
    assert missing.status_code == 404
    assert missing.headers["cache-control"] == "private, no-store"
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    response = make_client(engine).get("/api/v1/admin/social/posts")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SOCIAL_SCHEMA_UNAVAILABLE"
    assert response.headers["cache-control"] == "private, no-store"
    assert "SELECT" not in response.text
    engine.dispose()


def test_uuid_actor_and_safe_internal_errors(db, monkeypatch):
    client = make_client(db.bind, actor="legacy-integer-actor")
    response = client.post("/api/v1/admin/social/posts", json=draft_body().model_dump(mode="json"), headers=key())
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PERMISSION_DENIED"
    def crash(self, *args, **kwargs):
        raise RuntimeError("fixture_secret_value")
    monkeypatch.setattr(SocialService, "posts", crash)
    response = make_client(db.bind).get("/api/v1/admin/social/posts")
    assert response.status_code == 500
    assert "fixture_secret_value" not in response.text
    assert response.headers["cache-control"] == "private, no-store"


def test_manual_fake_flow_and_sparse_get_roundtrip(db):
    row = account(db)
    client = make_client(db.bind, adapters=("facebook",))
    created = client.post("/api/v1/admin/social/posts", json=draft_body((row,)).model_dump(mode="json"), headers=key())
    assert created.status_code == 201, created.text
    post = created.json()
    assert post["document"]["targets"][0]["overrides"] == {}
    base = "/api/v1/admin/social/posts/" + post["id"]
    validation = client.post(base + "/validate", json={"expected_version": 1})
    assert validation.status_code == 200
    assert validation.json()["valid"] is True
    paused = client.post(base + "/publish", json={"expected_version": 1, "revision_id": post["revision_id"]}, headers=key())
    assert paused.status_code == 409
    enabled = client.patch("/api/v1/admin/social/controls", json={"expected_version": 1, "publishing_enabled": True, "reason": "Local fake test"}, headers=key())
    assert enabled.status_code == 200, enabled.text
    accepted = client.post(base + "/publish", json={"expected_version": 1, "revision_id": post["revision_id"]}, headers=key())
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["targets"][0]["status"] == "queued"
    detail = client.get(base)
    assert detail.json()["document"]["targets"][0]["overrides"] == {}
    assert detail.json()["targets"][0]["state"] == "queued"
    invalid_version = client.post(base + "/cancel", json={"expected_version": True}, headers=key())
    assert invalid_version.status_code == 422


def test_compact_status_excludes_large_columns_at_sql_boundary(db):
    from sqlalchemy import event
    row = account(db)
    client = make_client(db.bind, adapters=("facebook",))
    body = draft_body((row,)).model_dump(mode="json")
    body["document"]["master"]["text"] = "a" * 4000
    created = client.post("/api/v1/admin/social/posts", json=body, headers=key()).json()
    path = "/api/v1/admin/social/posts/" + created["id"]
    client.post(path + "/approve", json={"expected_version": 1, "revision_id": created["revision_id"]}, headers=key())
    sql = []
    def capture(conn, cursor, statement, params, context, executemany):
        sql.append(statement)
    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        response = client.get(path + "/status")
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert "document" not in response.json()
    assert "references" not in response.json()
    assert "resolved_payload" not in response.text
    assert len(response.content) < 1500
    statements = " ".join(sql)
    assert "social_post_revisions" not in statements
    assert "resolved_payload" not in statements
    assert "checkpoint" not in statements
    assert "evidence_snapshot" not in statements
    assert "social_publish_attempts" not in statements
