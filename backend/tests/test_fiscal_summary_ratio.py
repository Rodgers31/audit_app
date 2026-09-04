"""Debt-service-to-revenue ratio is derived + authoritative.

The ratio shown on the debt page ("X out of every KES 100 of revenue goes to
debt service") was a hand-entered FY2025/26 value of 55.7, computed off a
narrow "CFS charge" numerator — understated vs the authoritative Treasury
APDMR / BPS figure of ~64-65% (Cytonn 2025; 67.1% actual as at May 2025).

These tests pin two things:
  1. the ratio is DERIVED from debt_service_cost / total_revenue (so it can't
     drift and self-updates on re-seed), and
  2. the committed FY2025/26 figure now lands in the authoritative band.
"""

from __future__ import annotations

import json
from pathlib import Path

from seeding.domains.fiscal_summary.parser import (
    _derive_debt_service_per_shilling,
    parse_fiscal_summary_payload,
)

SEED = (
    Path(__file__).resolve().parent.parent
    / "seeding/real_data/fiscal_summary.json"
)


def test_ratio_is_derived_from_inputs():
    assert _derive_debt_service_per_shilling(1900, 2910, None, label="x") == 65.3
    assert _derive_debt_service_per_shilling(1640, 2406, None, label="x") == 68.2


def test_derive_ignores_a_drifted_declared_value():
    # Inputs say 65.3; a stale declared 55.7 must NOT win.
    assert _derive_debt_service_per_shilling(1900, 2910, 55.7, label="x") == 65.3


def test_derive_falls_back_when_inputs_missing():
    assert _derive_debt_service_per_shilling(None, 2910, 60.0, label="x") == 60.0
    assert _derive_debt_service_per_shilling(1900, None, None, label="x") is None


def test_parse_payload_derives_ratio_not_declared():
    payload = {
        "fiscal_years": [
            {
                "fiscal_year": "FY 2025/26",
                "debt_service_cost": 1900,
                "total_revenue": 2910,
                "debt_service_per_shilling": 55.7,  # stale/wrong — must be ignored
            }
        ]
    }
    recs = parse_fiscal_summary_payload(payload)
    assert recs[0].debt_service_per_shilling == 65.3


def _seed_with_derived_revenue():
    """The committed seed AFTER the live revenue overlay — i.e. what ships.

    Revenue is no longer stored in the seed: revenue_estimates.py derives the
    whole series from Treasury's Budget Summary on every run. So a guard on the
    published ratio has to run on the payload the overlay produces, not on the
    fixture alone, which by design now carries no revenue for these years.
    """
    from decimal import Decimal as _D

    from seeding.domains.fiscal_summary.fetcher import _apply_revenue_estimates
    from seeding.domains.fiscal_summary.revenue_estimates import (
        FiscalFrameworkTable,
        build_revenue_series,
    )

    # Table 2 of the Budget Summary for the FY 2026/27 Budget, PDF p.14.
    table = FiscalFrameworkTable(
        ordinary_revenue={
            "FY2023/24": [_D("2288.9")],
            "FY2024/25": [_D("2420.2")],
            "FY2025/26": [_D("2754.7"), _D("2784.4")],
            "FY2026/27": [_D("2901.9"), _D("2985.7")],
        },
        total_revenues={
            "FY2023/24": [_D("2702.7")],
            "FY2024/25": [_D("2923.6")],
            "FY2025/26": [_D("3321.7"), _D("3399.1")],
            "FY2026/27": [_D("3534.2"), _D("3629.7")],
        },
        ministerial_aia={
            "FY2023/24": [_D("413.7")],
            "FY2024/25": [_D("503.4")],
            "FY2025/26": [_D("566.9"), _D("614.6")],
            "FY2026/27": [_D("632.4"), _D("644.0")],
        },
        page=14,
    )
    series, _ = build_revenue_series(table, through_fiscal_year="FY 2026/27")
    payload, _ = _apply_revenue_estimates(json.loads(SEED.read_text()), series)
    return parse_fiscal_summary_payload(payload)


def test_the_seed_no_longer_stores_revenue_for_the_derived_years():
    """A stored figure is one nothing re-checks. These must come from the PDF."""
    seed = {r["fiscal_year"]: r for r in json.loads(SEED.read_text())["fiscal_years"]}
    for fy in ("FY 2023/24", "FY 2024/25", "FY 2025/26", "FY 2026/27"):
        assert seed[fy]["total_revenue"] is None, fy
        assert seed[fy].get("total_revenue_absent_reason"), fy


def test_committed_seed_fy2025_26_is_authoritative_not_understated():
    by_fy = {r.fiscal_year: r for r in _seed_with_derived_revenue()}
    cur = by_fy["FY 2025/26"]
    # Authoritative ~68% (well above the old understated 56%).
    assert 60.0 <= cur.debt_service_per_shilling <= 70.0
    # And it must equal the derived value (no drift).
    assert cur.debt_service_per_shilling == round(
        cur.debt_service_cost / cur.total_revenue * 100, 1
    )


def test_every_derived_year_gets_a_ratio_once_the_overlay_runs():
    """The gap this whole change closed: FY2026/27 had debt service and no
    revenue, so the chart drew its share of revenue as 0%."""
    by_fy = {r.fiscal_year: r for r in _seed_with_derived_revenue()}
    for fy in ("FY 2023/24", "FY 2024/25", "FY 2025/26", "FY 2026/27"):
        assert by_fy[fy].total_revenue, fy
        assert by_fy[fy].debt_service_per_shilling, fy
