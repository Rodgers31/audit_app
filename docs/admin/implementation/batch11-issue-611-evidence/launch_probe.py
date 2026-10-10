"""Actual PostgreSQL/API launch behavior; no replacement CLI or writer."""
import os
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from database import get_db
from models import AdminAuditLog
from routers.admin_audit_log import router
from supabase_auth import AdminUser, get_current_user


@pytest.fixture
def owned():
    if os.getenv("ISSUE611_OWNED_POSTGRES") != "1":
        pytest.skip("issue611 owned PostgreSQL on 55534 required")
    engine = create_engine("postgresql+psycopg2://inert:inert@127.0.0.1:55534/issue611")
    AdminAuditLog.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: AdminUser(
        id="inert-admin", email=None, roles=["admin"]
    )

    def sessions():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = sessions
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield engine, factory, client
    finally:
        AdminAuditLog.__table__.drop(engine)
        engine.dispose()


def item():
    return AdminAuditLog(actor_id="inert-admin", action="etl.trigger",
                         payload={"job_id": 1, "dry_run": True},
                         created_at=datetime.now(timezone.utc))


def test_root_writer_late_lower_id_is_excluded(owned):
    engine, factory, client = owned
    with factory() as early:
        early.add(item())
        early.flush()
        with factory() as later:
            later.add(item())
            later.commit()
        response = client.get("/api/v1/admin/audit-log?days=0&page_size=1")
        assert response.status_code == 200, response.text
        first = response.json()
        assert first["total"] == 1
        early.commit()
    second = client.get("/api/v1/admin/audit-log", params={
        "days": 0, "page_size": 1, "page": 2,
        **{k: first[k] for k in ("snapshot_id", "as_of", "visibility_snapshot")},
    })
    assert second.status_code == 200, second.text
    assert second.json()["total"] == 1
    assert second.json()["entries"] == []
    assert second.headers["cache-control"] == "private, no-store"
    with engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM admin_audit_log")) == 2


def test_durable_capability_at_real_current_epoch(owned):
    """Run before/after a controlled owned-cluster epoch boundary.

    Epoch zero is a positive control. Epoch one exposes the intentionally
    unsupported capability as a behavioral red, not a production outage.
    """
    engine, factory, client = owned
    with factory() as db:
        db.add(item())
        db.commit()
    with engine.connect() as db:
        print("actual_pg_snapshot", db.scalar(text("SELECT pg_current_snapshot()::text")))
        print("postgres_version", db.scalar(text("SELECT version()")))
    response = client.get("/api/v1/admin/audit-log?days=0")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
