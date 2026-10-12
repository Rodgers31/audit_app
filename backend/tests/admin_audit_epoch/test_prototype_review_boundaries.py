"""Real reader-role and issued-bookmark boundaries found during PR618 review."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from test_prototype import insert, launch, prototype, storage
from supabase_auth import AdminUser, get_current_user


@pytest.mark.parametrize("grant", [
    "GRANT INSERT ON admin_audit_log TO issue611_reader",
    "GRANT INSERT(actor_id) ON admin_audit_log TO issue611_reader",
    "GRANT issue611_writer TO issue611_reader",
])
def test_writer_capable_reader_refuses_before_pagination(storage, grant):
    owner, factory, client, *_ = storage
    insert(factory)
    with owner.begin() as db:
        db.execute(text(grant))
    response = client.get("/api/v1/admin/audit-log?days=0")
    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "Audit evidence is unavailable."
    assert "no-store" in response.headers["cache-control"]
    with owner.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM admin_audit_log")) == 1


@pytest.mark.parametrize("field", ["active", "xmin", "xmax", "ceiling", "as_of", "scope", "unsigned"])
def test_modified_issued_bookmark_cannot_change_visible_population(storage, field):
    owner, factory, client, *_ = storage
    with factory() as early:
        early.add(launch.item())
        early.flush()
        insert(factory)
        first = client.get("/api/v1/admin/audit-log?days=0&page_size=1").json()
        assert first["total"] == 1
        early.commit()
    params = {"days": 0, "page": 2, "page_size": 1,
              **{k: first[k] for k in ("snapshot_id", "as_of", "visibility_snapshot")}}
    unchanged = client.get("/api/v1/admin/audit-log", params=params)
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["total"] == 1
    assert unchanged.json()["entries"] == []
    parts = params["visibility_snapshot"].split(":")
    if field == "active":
        assert parts[4]
        parts[4] = ""
    elif field == "xmin":
        parts[2] = str(int(parts[2]) - 1)
    elif field == "xmax":
        parts[3] = str(int(parts[3]) - 1)
    elif field == "scope":
        parts[1] = "61100000-0000-4000-8000-000000000099"
    elif field == "unsigned":
        parts[0] = "v2"
        parts = parts[:5]
    elif field == "ceiling":
        params["snapshot_id"] -= 1
    elif field == "as_of":
        params["as_of"] = (datetime.fromisoformat(first["as_of"]) - timedelta(microseconds=1)).isoformat()
    if field not in ("ceiling", "as_of"):
        params["visibility_snapshot"] = ":".join(parts)
    response = client.get("/api/v1/admin/audit-log", params=params)
    assert response.status_code == 422, response.text
    assert "no-store" in response.headers["cache-control"]
    with owner.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM admin_audit_log")) == 2


def test_bookmark_is_bound_to_authenticated_actor_and_process(storage, monkeypatch):
    _, factory, client, _, _, app = storage
    insert(factory)
    first = client.get("/api/v1/admin/audit-log?days=0").json()
    params = {"days": 0, **{k: first[k] for k in ("snapshot_id", "as_of", "visibility_snapshot")}}
    app.dependency_overrides[get_current_user] = lambda: AdminUser(id="different-admin", email=None, roles=["admin"])
    assert client.get("/api/v1/admin/audit-log", params=params).status_code == 422
    app.dependency_overrides[get_current_user] = lambda: AdminUser(id="inert-admin", email=None, roles=["admin"])
    monkeypatch.setattr(prototype, "BOOKMARK_KEY", b"inert-restarted-prototype-key")
    assert client.get("/api/v1/admin/audit-log", params=params).status_code == 422
    assert client.get("/api/v1/admin/audit-log?days=0").status_code == 200


def test_same_issued_population_supports_concurrent_reads_and_filter_transfer(storage):
    _, factory, client, *_ = storage
    insert(factory)
    first = client.get("/api/v1/admin/audit-log?days=0").json()
    params = {"days": 0, **{k: first[k] for k in ("snapshot_id", "as_of", "visibility_snapshot")}}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.get("/api/v1/admin/audit-log", params=params), range(4)))
    assert all(response.status_code == 200 and response.json()["entries"] == first["entries"] for response in responses)
    filtered = client.get("/api/v1/admin/audit-log", params={**params, "actor_id": "absent"})
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 0
    assert filtered.json()["visibility_snapshot"] == first["visibility_snapshot"]
