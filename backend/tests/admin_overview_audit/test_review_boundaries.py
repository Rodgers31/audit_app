"""Review regressions execute audit errors and epoch guards without storage/network."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routers import admin_audit_log


@pytest.mark.parametrize("status", [500, 502, 503])
def test_dependency_server_errors_are_private_and_sanitized(status):
    app = FastAPI()
    app.include_router(admin_audit_log.router)

    def broken_authorization():
        raise HTTPException(status, "SUPABASE_URL/JWKS PRIVATE_REVIEW_MARKER")

    app.dependency_overrides[admin_audit_log.require_admin] = broken_authorization
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/admin/audit-log")
    assert response.status_code == status
    assert response.json() == {"detail": "Audit evidence is unavailable."}
    assert "PRIVATE_REVIEW_MARKER" not in response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Authorization"


@pytest.mark.parametrize("snapshot", [
    "3:4294967296:", "4294967296:4294967297:",
    "4294967299:4294967301:4294967300",
])
def test_wrapped_epoch_snapshot_is_rejected(snapshot):
    with pytest.raises(HTTPException) as error:
        admin_audit_log.visibility_filter(snapshot)
    assert error.value.status_code == 422


def test_maximum_supported_epoch_zero_snapshot_is_accepted():
    assert admin_audit_log.visibility_filter("3:4294967295:") == "3:4294967295:"


@pytest.mark.parametrize("supplied,expected_status", [(False, 503), (True, 422)])
def test_captured_and_supplied_epoch_fail_before_audit_query(supplied, expected_status):
    class NoRowsDatabase:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def execute(self, statement):
            return SimpleNamespace(scalar_one=lambda: "4294967296:4294967297:")

        def query(self, *args):
            pytest.fail("Unsupported epoch must not query audit rows")

    kwargs = dict(actor_id=None, action=None, target_type=None, target_id=None,
                  days=30, page=1, page_size=20, since=None, until=None,
                  snapshot_id=1 if supplied else None,
                  as_of=datetime.now(timezone.utc) if supplied else None,
                  visibility_snapshot="4294967296:4294967297:" if supplied else None,
                  db=NoRowsDatabase())
    with pytest.raises(HTTPException) as error:
        asyncio.run(admin_audit_log.list_audit_log(**kwargs))
    assert error.value.status_code == expected_status


@pytest.mark.parametrize("server_snapshot", ["3:4294967296:", "4294967296:4294967297:"])
def test_epoch_zero_bookmark_cannot_skip_current_server_epoch(server_snapshot):
    class NoRowsDatabase:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def execute(self, statement):
            return SimpleNamespace(scalar_one=lambda: server_snapshot)

        def query(self, *args):
            pytest.fail("Current unsupported epoch must fail before audit rows")

    kwargs = dict(actor_id=None, action=None, target_type=None, target_id=None,
                  days=30, page=1, page_size=20, since=None, until=None,
                  snapshot_id=1, as_of=datetime.now(timezone.utc),
                  visibility_snapshot="3:9:", db=NoRowsDatabase())
    with pytest.raises(HTTPException) as error:
        asyncio.run(admin_audit_log.list_audit_log(**kwargs))
    assert error.value.status_code == 503


@pytest.mark.parametrize("snapshot", ["3:4294967296:", "4294967296:4294967297:", "٣:٩:"])
def test_invalid_client_snapshot_is_rejected_before_current_server_read(snapshot):
    class NoStorageRead:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def execute(self, statement):
            pytest.fail("Invalid client metadata must not read current storage")

        def query(self, *args):
            pytest.fail("Invalid client metadata must not query audit rows")

    kwargs = dict(actor_id=None, action=None, target_type=None, target_id=None,
                  days=30, page=1, page_size=20, since=None, until=None,
                  snapshot_id=1, as_of=datetime.now(timezone.utc),
                  visibility_snapshot=snapshot, db=NoStorageRead())
    with pytest.raises(HTTPException) as error:
        asyncio.run(admin_audit_log.list_audit_log(**kwargs))
    assert error.value.status_code == 422
