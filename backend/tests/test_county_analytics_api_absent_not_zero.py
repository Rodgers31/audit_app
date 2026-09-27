"""``apis/county_analytics_api.py`` publishes an absent figure as absent (#207).

The service read ``analytics_summary`` out of ``enhanced_county_data.json`` and
served each figure with ``.get(key, 0)``. The committed data file
(``backend/data/reference/enhanced_county_data.json``) has no
``analytics_summary`` key at all, so every call said the counties' budgets
totalled KSh 0, that no money was missing, and that average financial health
was 0 — beside a hard-coded ``"total_counties": 47`` that did not look at the
file either. It also served ``loans_received: 0`` for every county, a field no
record carries.

The shape now is ``/budget/national``'s: the figure, or ``None`` and a reason
(``budget_split_absent_reason``). Each test that proves an absence is paired
with a control proving a present value — including a real zero — still comes
through, so nulling the fields unconditionally would fail here.

The module loads its data at import time from the working directory, so each
test imports a fresh copy from a temporary directory holding the fixture.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

from tests._repo_tree import REPO_ROOT

MODULE_PATH = REPO_ROOT / "apis" / "county_analytics_api.py"

RECORD = {
    "population": 1208333,
    "budget_2025": 9_800_000_000,
    "revenue_2024": 8_330_000_000,
    "debt_outstanding": 1_470_000_000,
    "pending_bills": 784_000_000,
    "audit_rating": "B",
    "missing_funds": 196_000_000,
    "financial_health_score": 75.0,
    "budget_execution_rate": 75.0,
    "per_capita_budget": 8110.0,
    "debt_to_budget_ratio": 15.0,
}


def _load(tmp_path: Path, monkeypatch, payload: dict):
    (tmp_path / "enhanced_county_data.json").write_text(json.dumps(payload))
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("county_analytics_api_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _root(module) -> dict:
    return asyncio.run(module.root())


def test_a_file_without_a_summary_publishes_no_figures_and_says_why(tmp_path, monkeypatch):
    module = _load(
        tmp_path,
        monkeypatch,
        {"county_data": {"Mombasa": RECORD, "Kwale": RECORD}},
    )
    body = _root(module)

    for key in ("total_county_budgets", "total_missing_funds", "average_financial_health"):
        assert body[key] is None, f"{key} published {body[key]!r} with no summary to read"
        assert body[f"{key}_absent_reason"] == "not_in_county_data_file", body

    # Counted from the file, not asserted.
    assert body["total_counties"] == 2


def test_a_file_with_a_summary_publishes_it_including_a_real_zero(tmp_path, monkeypatch):
    """Control: present values come through, and a measured 0 is still 0."""
    module = _load(
        tmp_path,
        monkeypatch,
        {
            "county_data": {"Mombasa": RECORD},
            "analytics_summary": {
                "total_county_budgets": 9_800_000_000,
                "total_missing_funds": 0,
                "average_financial_health": 75.0,
            },
        },
    )
    body = _root(module)

    assert body["total_county_budgets"] == 9_800_000_000
    assert body["total_missing_funds"] == 0
    assert body["average_financial_health"] == 75.0
    for key in ("total_county_budgets", "total_missing_funds", "average_financial_health"):
        assert body[f"{key}_absent_reason"] is None, body
    assert body["total_counties"] == 1


def test_a_summary_missing_one_figure_withholds_only_that_one(tmp_path, monkeypatch):
    module = _load(
        tmp_path,
        monkeypatch,
        {
            "county_data": {"Mombasa": RECORD},
            "analytics_summary": {"total_county_budgets": 9_800_000_000},
        },
    )
    body = _root(module)

    assert body["total_county_budgets"] == 9_800_000_000
    assert body["total_county_budgets_absent_reason"] is None
    assert body["total_missing_funds"] is None
    assert body["total_missing_funds_absent_reason"] == "not_in_county_data_file"


def test_the_committed_data_file_carries_no_summary():
    """Pins the premise: against the real file, the old code published zeros."""
    committed = json.loads(
        (REPO_ROOT / "backend" / "data" / "reference" / "enhanced_county_data.json").read_text()
    )
    assert "analytics_summary" not in committed
    assert not any("loans_received" in r for r in committed["county_data"].values())


def test_loans_received_is_absent_not_zero(tmp_path, monkeypatch):
    with_loans = dict(RECORD, loans_received=1_000_000_000)
    module = _load(
        tmp_path,
        monkeypatch,
        {"county_data": {"Mombasa": RECORD, "Kwale": with_loans}},
    )

    listed = {c.county: c for c in asyncio.run(module.get_all_counties(limit=47))}
    assert listed["Mombasa"].loans_received is None
    assert listed["Kwale"].loans_received == 1_000_000_000

    detail = asyncio.run(module.get_county_details("Mombasa"))
    assert detail["financial_metrics"]["loans_received"] is None
    detail = asyncio.run(module.get_county_details("Kwale"))
    assert detail["financial_metrics"]["loans_received"] == 1_000_000_000


def test_the_summary_prose_does_not_state_a_zero_either(tmp_path, monkeypatch):
    """``/analytics/summary`` republished the same figures as sentences.

    ``f"Total missing funds: {summary.get('total_missing_funds', 0):,.0f} KES"``
    rendered "Total missing funds: 0 KES" — the #207 claim in prose, where a
    label-keyed rule cannot see it.
    """
    module = _load(tmp_path, monkeypatch, {"county_data": {"Mombasa": RECORD}})
    insights = asyncio.run(module.get_analytics_summary())["key_insights"]

    assert not any(": 0 KES" in line or ": 0%" in line for line in insights), insights
    assert "Total missing funds: not in the county data file" in insights, insights

    module = _load(
        tmp_path,
        monkeypatch,
        {
            "county_data": {"Mombasa": RECORD},
            "analytics_summary": {"total_missing_funds": 0},
        },
    )
    insights = asyncio.run(module.get_analytics_summary())["key_insights"]
    assert "Total missing funds: 0 KES" in insights, "a measured zero must still print"
