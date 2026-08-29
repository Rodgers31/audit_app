"""Fiscal-summary validation gate (recommendation #1).

Locks in the plausibility + reconciliation guard that makes turning on live
budget/revenue parsing safe:
  - `check_fiscal_summary` flags band violations (unit slips / wrong-row
    parses) and component breakdowns that don't reconcile — for BOTH dicts
    (API) and FiscalSummaryRecord-like objects (seed time).
  - the fiscal_summary domain QUARANTINES a bad row (keeps last-known-good).
  - /fiscal/summary surfaces the caveat in _meta.quality_notes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from services.trust_guards import check_fiscal_summary

# A clean FY2025/26 row (billion KES), matching the seeded fixture shape.
CLEAN = {
    "fiscal_year": "FY 2025/26",
    "appropriated_budget": 4190,
    "total_revenue": 2910,
    "tax_revenue": 2560,
    "non_tax_revenue": 350,
    "total_borrowing": 910,
    "debt_service_cost": 1900,
    "development_spending": 672,
    "recurrent_spending": 2850,
    "county_allocation": 415,
}


# ── pure guard ──────────────────────────────────────────────────────────
def test_clean_row_has_no_notes():
    assert check_fiscal_summary(CLEAN) == []


def test_accepts_dataclass_like_object():
    # Seed time passes a FiscalSummaryRecord (attributes, not .get()).
    assert check_fiscal_summary(SimpleNamespace(**CLEAN)) == []


def test_raw_kes_row_is_normalised_not_flagged():
    # Since the stage1 3a migration the TABLE stores raw KES, so the guard
    # normalises >=1e9 values to billions before banding: a correct raw-KES
    # row must pass. (This test previously asserted the opposite — it
    # encoded the pre-migration undeclared-billions convention, F5.5.)
    row = {**CLEAN, "appropriated_budget": 4_190_000_000_000}
    assert check_fiscal_summary(row) == []


def test_out_of_band_raw_kes_is_still_caught():
    # POSITIVE CONTROL: normalisation must not disable the band check —
    # a 50T budget (raw) is out of band in any unit.
    row = {**CLEAN, "appropriated_budget": 50_000_000_000_000}
    notes = check_fiscal_summary(row)
    assert any("appropriated_budget" in n and "band" in n for n in notes)


def test_trillions_collapse_is_caught():
    row = {**CLEAN, "appropriated_budget": 4.19}  # wrote trillions
    assert any("appropriated_budget" in n for n in check_fiscal_summary(row))


def test_revenue_components_must_reconcile():
    # tax + non-tax must ≈ total_revenue (±5%).
    row = {**CLEAN, "tax_revenue": 1000}  # 1000 + 350 = 1350 ≠ 2910
    assert any("reconcile" in n for n in check_fiscal_summary(row))


def test_spending_cannot_exceed_budget():
    row = {**CLEAN, "recurrent_spending": 4000, "development_spending": 1000}
    assert any("exceeds the appropriated budget" in n for n in check_fiscal_summary(row))


# ── seed-time quarantine ────────────────────────────────────────────────
def test_domain_quarantines_bad_row_keeps_good(db_session, seed_country, monkeypatch):
    from models import FiscalSummary
    from seeding.config import SeedingSettings
    from seeding.domains import fiscal_summary
    from seeding.domains.fiscal_summary import fetcher
    from seeding.types import DomainRunContext

    payload = {
        "metadata": {"source": "test"},
        "fiscal_years": [
            CLEAN,  # plausible → written
            {**CLEAN, "fiscal_year": "FY 2024/25", "appropriated_budget": 99999},  # band → quarantined
        ],
    }
    monkeypatch.setattr(
        fetcher, "fetch_fiscal_summary_payload", lambda client, settings: payload
    )

    result = fiscal_summary.run(
        db_session, SeedingSettings(), DomainRunContext(since=None, dry_run=False)
    )
    db_session.commit()

    years = {r.fiscal_year for r in db_session.query(FiscalSummary).all()}
    assert "FY 2025/26" in years  # good row written
    assert "FY 2024/25" not in years  # bad row quarantined
    assert any("Quarantined" in e and "FY 2024/25" in e for e in result.errors)


# ── API surfacing ───────────────────────────────────────────────────────
def test_fiscal_summary_endpoint_surfaces_quality_notes(client, db_session, seed_source_doc):
    from models import FiscalSummary

    # An implausible latest year (budget far outside band) but enough fields
    # populated to pass the endpoint's completeness filter and become `current`.
    db_session.add(
        FiscalSummary(
            fiscal_year="FY 2025/26",
            appropriated_budget=99999,
            total_revenue=2910,
            total_borrowing=910,
            county_allocation=415,
            source_document_id=seed_source_doc.id,
        )
    )
    db_session.commit()

    resp = client.get("/api/v1/fiscal/summary")
    assert resp.status_code == 200
    notes = resp.json()["_meta"].get("quality_notes") or []
    assert any("appropriated_budget" in n for n in notes)


# ── calibration: the gate must NOT reject the real curated fixture ───────
def test_gate_accepts_every_real_fixture_row():
    """Guards against an over-tight band quarantining good, curated data."""
    import json
    from pathlib import Path

    fixture = (
        Path(__file__).resolve().parent.parent
        / "seeding"
        / "real_data"
        / "fiscal_summary.json"
    )
    rows = json.loads(fixture.read_text()).get("fiscal_years", [])
    assert rows, "fixture should have fiscal-year rows"
    for row in rows:
        assert check_fiscal_summary(row) == [], (
            f"{row.get('fiscal_year')} unexpectedly flagged: "
            f"{check_fiscal_summary(row)}"
        )
