"""Tests for the /data/freshness rework (audit §2.9 — Critical).

Locks in that freshness is judged on the source PUBLICATION date (not the
ETL-run time), exposes last_checked separately, and uses frequency-aware
fresh/stale/outdated thresholds.
"""

from __future__ import annotations

import datetime as dt

import pytest

from routers.data_freshness import _CYCLE_DAYS, _freshness_status

TODAY = dt.date.today()


# ── frequency-aware status ──────────────────────────────────────────────
def test_status_unknown_when_no_date():
    assert _freshness_status(None, "Monthly") == "unknown"


def test_monthly_recent_is_fresh():
    assert _freshness_status(TODAY - dt.timedelta(days=20), "Monthly") == "fresh"


def test_annual_six_months_old_is_still_fresh():
    # The key fix: an annual report ~6 months old is within one publication
    # cycle, so it must NOT be judged "outdated" by a 45-day window...
    assert _freshness_status(TODAY - dt.timedelta(days=180), "Annually") == "fresh"


def test_monthly_six_months_old_is_outdated():
    # ...while a *monthly* series 6 months stale clearly is outdated.
    assert _freshness_status(TODAY - dt.timedelta(days=180), "Monthly") == "outdated"


def test_quarterly_bands():
    cycle = _CYCLE_DAYS["Quarterly"]
    assert _freshness_status(TODAY - dt.timedelta(days=cycle - 5), "Quarterly") == "fresh"
    assert _freshness_status(TODAY - dt.timedelta(days=cycle + 30), "Quarterly") == "stale"
    assert (
        _freshness_status(TODAY - dt.timedelta(days=int(cycle * 3)), "Quarterly")
        == "outdated"
    )


# ── endpoint shape: last_checked present, status valid ──────────────────
def test_freshness_endpoint_exposes_last_checked(client):
    resp = client.get("/api/v1/data/freshness")
    assert resp.status_code == 200
    sources = resp.json()["sources"]
    assert isinstance(sources, list) and sources
    for s in sources:
        # last_updated (publication) and last_checked (ingestion) are distinct
        # fields; both may be null on an empty test DB, but the keys must exist.
        assert "last_updated" in s
        assert "last_checked" in s
        assert s["status"] in {"fresh", "stale", "outdated", "unknown"}


def test_freshness_cache_preserves_unknown_and_recovers_after_invalidation(client, monkeypatch):
    from cache.invalidation import clear_local_caches
    from cache.redis_cache import cache
    from routers import data_freshness

    monkeypatch.setattr(cache, "client", None)
    cache._memory_cache.clear()
    state = {"published": None}
    calls = []

    def publication_date(db, publisher, domain):
        calls.append(publisher)
        return state["published"]

    monkeypatch.setattr(data_freshness, "_source_publication_date", publication_date)
    monkeypatch.setattr(data_freshness, "_covers_through", lambda db, cfg: None)
    first = client.get("/api/v1/data/freshness")
    assert first.status_code == 200
    assert all(item["status"] == "unknown" for item in first.json()["sources"])
    state["published"] = TODAY
    assert client.get("/api/v1/data/freshness").content == first.content
    assert len(calls) == len(data_freshness.SOURCE_CONFIG)
    clear_local_caches()
    refreshed = client.get("/api/v1/data/freshness")
    assert refreshed.status_code == 200
    assert all(item["status"] == "fresh" for item in refreshed.json()["sources"])
