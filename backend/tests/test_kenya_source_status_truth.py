"""A retired/unavailable checker is not evidence of publisher health."""

import sys

import pytest


@pytest.mark.parametrize("etl_available", [True, False])
def test_unavailable_checker_never_publishes_success_or_fetch_time(
    client, monkeypatch, etl_available
):
    monkeypatch.setattr("main.ETL_AVAILABLE", etl_available)
    monkeypatch.setitem(sys.modules, "etl_test_runner", None)
    response = client.get("/api/v1/etl/kenya/sources")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["real_time_test"] is False
    assert body["error"] == "live_check_unavailable"
    assert body["freshness_url"] == "/api/v1/data/freshness"
    assert len(body["sources"]) == 3  # the source catalogue remains usable
    for source in body["sources"]:
        assert source["status"] == "unknown"
        assert source["last_fetch"] is None
        assert source["checked_at"] is None
        assert source["url"].startswith("https://")
