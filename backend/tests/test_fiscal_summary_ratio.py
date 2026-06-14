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


def test_committed_seed_fy2025_26_is_authoritative_not_understated():
    recs = parse_fiscal_summary_payload(json.loads(SEED.read_text()))
    by_fy = {r.fiscal_year: r for r in recs}
    cur = by_fy["FY 2025/26"]
    # Authoritative ~64-65% (well above the old understated 56%).
    assert 60.0 <= cur.debt_service_per_shilling <= 70.0
    # And it must equal the derived value (no drift).
    assert cur.debt_service_per_shilling == round(
        cur.debt_service_cost / cur.total_revenue * 100, 1
    )
