"""Independent executed Operations review with inert auth and isolated storage."""
import asyncio
import copy
import math

import pytest
from fastapi import HTTPException

from routers import admin, etl_admin
from routers.admin_operations import safe_job_metadata
from supabase_auth import require_admin
from test_admin_operations_lane import AUTH, operations, seed


def replace_report(monkeypatch, change):
    report = etl_admin.SmartScheduler().generate_schedule_report()
    change(report)

    class FakePlanner:
        def generate_schedule_report(self):
            return copy.deepcopy(report)

    monkeypatch.setattr(etl_admin, "SmartScheduler", FakePlanner)


@pytest.mark.parametrize("config", [
    {"secret": "PRIVATE_TEST_PASSWORD"}, {},
    {"default": {"frequency": "weekly", "day": "monday", "days_after": True}},
    {"default": {"frequency": "weekly", "day": "monday", "days_after": math.nan}},
    {"default": {"frequency": "weekly", "day": "monday", "days_after": math.inf}},
    {"default": {"frequency": "weekly", "day": "monday", "days_after": -1}},
])
def test_untrusted_planner_config_is_not_transferred(operations, monkeypatch, config):
    client, _, _ = operations
    replace_report(monkeypatch, lambda report: report["oag"].update(schedule_config=config))
    for route in ["schedule", "schedule/summary", "schedule/source/oag", "health"]:
        response = client.get("/api/v1/admin/etl/" + route, headers=AUTH)
        assert response.status_code == 200
        assert "schedule_config" not in response.text
        assert "PRIVATE_TEST_PASSWORD" not in response.text
    assert response.json()["plan_status"] == "available"
    assert response.json()["scheduler_status"] == "unverified"


@pytest.mark.parametrize("bad", [None, [], {}, "PRIVATE_TEST_PASSWORD", 0, True])
def test_wrong_planner_report_fails_closed(operations, monkeypatch, bad):
    client, _, _ = operations

    class FakePlanner:
        def generate_schedule_report(self):
            return bad

    monkeypatch.setattr(etl_admin, "SmartScheduler", FakePlanner)
    for route in ["schedule", "schedule/summary", "schedule/source/oag"]:
        response = client.get("/api/v1/admin/etl/" + route, headers=AUTH)
        assert response.status_code == 503
        assert "PRIVATE_TEST_PASSWORD" not in response.text
        assert "no-store" in response.headers["cache-control"]
    health = client.get("/api/v1/admin/etl/health", headers=AUTH).json()
    assert health["plan_status"] == "unavailable"
    assert health["worker_status"] == health["data_freshness"] == "unverified"


@pytest.mark.parametrize("bad", [None, 0, 1, "false", math.nan, math.inf, -math.inf, {}])
def test_planner_decision_requires_actual_boolean(operations, monkeypatch, bad):
    client, _, _ = operations
    replace_report(monkeypatch, lambda report: report["oag"].update(should_run_now=bad))
    assert client.get("/api/v1/admin/etl/schedule", headers=AUTH).status_code == 503


def test_absent_planner_does_not_fake_availability(operations, monkeypatch):
    client, _, _ = operations
    monkeypatch.setattr(etl_admin, "SmartScheduler", None)
    response = client.get("/api/v1/admin/etl/schedule", headers=AUTH)
    assert response.status_code == 503
    assert client.get("/api/v1/admin/etl/health", headers=AUTH).json()["plan_status"] == "unavailable"


@pytest.mark.parametrize("bad", ["2026-10-08", "2026-W41-4T00:00:00", "2026-10-08X00:00:00"])
def test_planner_dates_match_browser_timestamp_contract(operations, monkeypatch, bad):
    client, _, _ = operations
    replace_report(monkeypatch, lambda report: report["oag"].update(next_run=bad))
    assert client.get("/api/v1/admin/etl/schedule", headers=AUTH).status_code == 503
    assert client.get("/api/v1/admin/etl/health", headers=AUTH).json()["plan_status"] == "unavailable"


@pytest.mark.parametrize("errors,expected", [
    (None, 0), ([], 0), ({}, 1), ({"secret": "PRIVATE_TEST_PASSWORD"}, 1),
    ("PRIVATE_TEST_PASSWORD", 1), (True, 1), (False, 1), (0, 1),
    (["PRIVATE_TEST_PASSWORD", {"secret": "PRIVATE_TEST_PASSWORD"}], 2),
])
def test_diagnostic_shapes_have_equivalent_private_list_and_detail(operations, errors, expected):
    client, factory, _ = operations
    job_id = seed(factory, errors=errors, meta={"private": "PRIVATE_TEST_PASSWORD"})
    listing = client.get("/api/v1/admin/ingestion-jobs", headers=AUTH)
    detail = client.get(f"/api/v1/admin/ingestion-jobs/{job_id}", headers=AUTH)
    assert listing.status_code == detail.status_code == 200
    assert listing.json()["jobs"][0]["error_count"] == detail.json()["error_count"] == expected
    assert "PRIVATE_TEST_PASSWORD" not in listing.text + detail.text


@pytest.mark.parametrize("bad", [None, [], "PRIVATE_TEST_PASSWORD", True, 0])
def test_unknown_metadata_shapes_stay_private(bad):
    assert safe_job_metadata(bad) == {}


@pytest.mark.parametrize("bounds", [
    {"page": 0}, {"page": -1}, {"page": 10001}, {"page": True},
    {"page_size": 0}, {"page_size": -1}, {"page_size": 101}, {"page_size": True},
    {"page": None}, {"page_size": None}, {"page": math.nan}, {"page_size": math.inf},
    {"page": -math.inf}, {"page_size": 1.5}, {"days": True}, {"days": math.nan},
])
def test_direct_list_cannot_bypass_pagination_bounds(operations, bounds):
    _, factory, _ = operations
    for _ in range(3):
        seed(factory)
    args = {"domain": None, "status": None, "days": 7, "page": 1, "page_size": 20, **bounds}
    with factory() as db:
        with pytest.raises(HTTPException) as rejected:
            asyncio.run(admin.list_ingestion_jobs(db=db, **args))
    assert rejected.value.status_code in (400, 422)


@pytest.mark.parametrize("body", [None, {}, {"dry_run": False}, {"dry_run": True}])
def test_direct_duplicate_trigger_never_accepts_without_dispatch(body):
    for _ in range(2):
        with pytest.raises(HTTPException) as rejected:
            asyncio.run(etl_admin.trigger_etl_run("oag", body=body, actor=None))
        assert rejected.value.status_code == 503
        assert rejected.value.detail["code"] == "manual_dispatch_unavailable"


def test_trigger_validation_errors_are_private_and_do_not_echo_input(operations):
    client, _, _ = operations
    response = client.post("/api/v1/admin/etl/trigger/oag", json={"dry_run": "PRIVATE_TEST_PASSWORD"}, headers=AUTH)
    assert response.status_code == 422
    assert "PRIVATE_TEST_PASSWORD" not in response.text
    assert "no-store" in response.headers.get("cache-control", "")


@pytest.mark.parametrize("status", [500, 502, 503])
def test_dependency_http_errors_do_not_transfer_internal_diagnostics(operations, status):
    client, _, _ = operations

    def unavailable_auth():
        raise HTTPException(status_code=status, detail="postgres://inert:PRIVATE_TEST_PASSWORD@invalid/db")

    client.app.dependency_overrides[require_admin] = unavailable_auth
    for method, route in [("get", "ingestion-jobs"), ("get", "etl/schedule"), ("post", "etl/trigger/oag")]:
        response = getattr(client, method)("/api/v1/admin/" + route, headers=AUTH)
        assert response.status_code in (500, 502, 503)
        assert "PRIVATE_TEST_PASSWORD" not in response.text
        assert "no-store" in response.headers.get("cache-control", "")


def test_unexpected_storage_failure_is_safe_and_noncacheable(operations):
    import database

    client, _, _ = operations

    def unavailable_storage():
        raise RuntimeError("postgres://inert:PRIVATE_TEST_PASSWORD@invalid/db")

    client.app.dependency_overrides[database.get_db] = unavailable_storage
    response = client.get("/api/v1/admin/ingestion-jobs", headers=AUTH)
    assert response.status_code == 503
    assert "PRIVATE_TEST_PASSWORD" not in response.text
    assert "no-store" in response.headers.get("cache-control", "")


@pytest.mark.parametrize("route,method", [
    ("ingestion-jobs", "get"), ("etl/schedule", "get"), ("etl/trigger/oag", "post"),
])
def test_auth_failures_remain_private(operations, route, method):
    client, _, _ = operations
    for headers in [{}, {"Authorization": "Bearer viewer"}]:
        response = getattr(client, method)("/api/v1/admin/" + route, headers=headers)
        assert response.status_code in (401, 403)
        assert "no-store" in response.headers.get("cache-control", "")


def test_unknown_stored_status_fails_closed_without_echoing_raw_value(operations):
    from sqlalchemy import text

    client, factory, engine = operations
    job_id = seed(factory)
    with engine.begin() as conn:
        conn.execute(text("UPDATE ingestion_jobs SET status = :value WHERE id = :job_id"),
                     {"value": "PRIVATE_TEST_UNKNOWN_STATUS", "job_id": job_id})
    for route in ["ingestion-jobs", f"ingestion-jobs/{job_id}", "ingestion-jobs/stats/summary"]:
        response = client.get("/api/v1/admin/" + route, headers=AUTH)
        assert response.status_code == 503
        assert "PRIVATE_TEST_UNKNOWN_STATUS" not in response.text
        assert "no-store" in response.headers.get("cache-control", "")
