"""Live COB headline overlay for the budget figure (recommendation #3).

The fiscal_summary headline budget can now be refined from the authoritative
COB NG-BIRR — but ONLY through a safe, reconciliation-gated overlay so a bad
parse can never replace the curated fixture. Plus borrowing_pct_of_budget is
now DERIVED, so a corrected/overlaid budget flows through consistently.

Covers:
  - the pure overall-budget text extractor (billion/trillion, grand-total,
    ignores non-budget lines, no-match → None);
  - the overlay promotion rules (promote in-tolerance; reject out-of-tolerance,
    implausible, or missing — fixture stands);
  - derived borrowing_pct_of_budget.
"""

from __future__ import annotations

from decimal import Decimal

from seeding.domains.fiscal_summary.fetcher import (
    _overlay_live_budget_headline,
    _overlay_live_revenue_headline,
)
from seeding.domains.fiscal_summary.parser import parse_fiscal_summary_payload
from seeding.domains.national_budget.headline import (
    extract_overall_budget_billion_from_text,
    extract_total_revenue_billion_from_text,
)

# A complete latest-year fixture row (billion KES) for overlay tests.
LATEST = {
    "fiscal_year": "FY 2025/26",
    "appropriated_budget": 4190,
    "total_revenue": 2910,
    "tax_revenue": 2560,
    "non_tax_revenue": 350,
    "total_borrowing": 910,
    "recurrent_spending": 2850,
    "development_spending": 672,
}


# ── pure text extractor ─────────────────────────────────────────────────
def test_extract_billions_on_budget_line():
    txt = "The total approved budget for FY 2025/26 was Kshs 4,292.0 billion."
    assert extract_overall_budget_billion_from_text(txt) == Decimal("4292.0")


def test_extract_trillions_normalised_to_billions():
    txt = "Gross estimates amounted to KSh 4.29 trillion in the period."
    assert extract_overall_budget_billion_from_text(txt) == Decimal("4290.00")


def test_extract_picks_grand_total_over_subfigures_on_anchor_line():
    txt = (
        "The total approved budget of Kshs 4,292 billion comprised a recurrent "
        "vote of Kshs 2,800 billion and Kshs 744 billion for development."
    )
    assert extract_overall_budget_billion_from_text(txt) == Decimal("4292")


def test_extract_ignores_non_budget_lines():
    # Revenue must NOT be mistaken for the budget (no budget anchor present).
    txt = "Total revenue collected was Kshs 2,910 billion against target."
    assert extract_overall_budget_billion_from_text(txt) is None


def test_extract_no_match_returns_none():
    assert extract_overall_budget_billion_from_text("no money here") is None
    assert extract_overall_budget_billion_from_text("") is None


# ── overlay promotion rules ─────────────────────────────────────────────
def _payload():
    return {"fiscal_years": [dict(LATEST)]}


def test_overlay_promotes_in_tolerance_value():
    """In-tolerance values promote — once the row declares its basis.

    UPDATED 2026-08-29. This previously passed no basis, asserting that a
    plausible in-tolerance number is promoted on numeric grounds alone.
    That contract is unsafe: COB's original GROSS budget for FY2025/26 is
    4.69T while the fixture row holds the Budget Policy Statement figure of
    4.19T — different measures, 12% apart, i.e. INSIDE the 15% tolerance.
    Under the old rule the homepage headline would have moved to 4.69T with
    nobody choosing it. Promotion now also requires the row to declare the
    same basis; the numeric behaviour it was written to pin is unchanged.
    """
    payload = {"fiscal_years": [dict(LATEST, budget_basis="cob_gross")]}
    payload, status = _overlay_live_budget_headline(payload, 4292.0)
    assert status == "promoted"
    assert payload["fiscal_years"][0]["appropriated_budget"] == 4292.0
    assert payload["fiscal_years"][0]["_budget_source"] == "cob_ng_birr_live"


def test_overlay_refuses_a_row_that_declares_no_basis():
    """POSITIVE CONTROL for the gate above: an in-tolerance, plausible value
    is still refused when the row does not say which measure it holds."""
    payload, status = _overlay_live_budget_headline(_payload(), 4292.0)
    assert status.startswith("basis_undeclared")
    assert payload["fiscal_years"][0]["appropriated_budget"] == 4190
    # ...but the live figure is recorded, so the refusal is inspectable.
    assert payload["fiscal_years"][0]["_cob_live_budget_billion"] == 4292.0


def test_overlay_refuses_a_differently_declared_basis():
    payload = {"fiscal_years": [dict(LATEST, budget_basis="bps")]}
    payload, status = _overlay_live_budget_headline(payload, 4690.0)
    assert status == "basis_mismatch(row=bps,live=cob_gross)"
    assert payload["fiscal_years"][0]["appropriated_budget"] == 4190


def test_overlay_rejects_out_of_tolerance_keeps_fixture():
    # 5000 is plausible + spending ≤ budget, but >15% above the 4190 fixture.
    payload, status = _overlay_live_budget_headline(_payload(), 5000.0)
    assert status == "outside_tolerance"
    assert payload["fiscal_years"][0]["appropriated_budget"] == 4190


def test_overlay_rejects_implausible_value():
    payload, status = _overlay_live_budget_headline(_payload(), 99999.0)
    assert status == "failed_plausibility"
    assert payload["fiscal_years"][0]["appropriated_budget"] == 4190


def test_overlay_noop_on_missing_value():
    payload, status = _overlay_live_budget_headline(_payload(), None)
    assert status == "no_live_value"
    assert payload["fiscal_years"][0]["appropriated_budget"] == 4190


# ── revenue extractor (#2) ──────────────────────────────────────────────
def test_extract_total_revenue_billions():
    txt = "Total revenue collected in the period was Kshs 2,968 billion."
    assert extract_total_revenue_billion_from_text(txt) == Decimal("2968")


def test_extract_ordinary_revenue_trillions():
    txt = "Ordinary revenue amounted to KSh 2.75 trillion against target."
    assert extract_total_revenue_billion_from_text(txt) == Decimal("2750.00")


def test_revenue_extractor_ignores_budget_lines():
    txt = "The total approved budget was Kshs 4,292 billion."
    assert extract_total_revenue_billion_from_text(txt) is None


# ── revenue overlay (#2) ────────────────────────────────────────────────
def test_revenue_overlay_promotes_and_scales_components():
    payload, status = _overlay_live_revenue_headline(_payload(), 2968.0)
    assert status == "promoted"
    row = payload["fiscal_years"][0]
    assert row["total_revenue"] == 2968.0
    # tax + non-tax must still sum to the new total (within rounding).
    assert abs((row["tax_revenue"] + row["non_tax_revenue"]) - 2968.0) < 1.0
    assert row["_revenue_source"] == "cob_ng_birr_live"


def test_revenue_overlay_rejects_out_of_tolerance():
    payload, status = _overlay_live_revenue_headline(_payload(), 2000.0)
    assert status == "outside_tolerance"
    assert payload["fiscal_years"][0]["total_revenue"] == 2910


def test_revenue_overlay_rejects_implausible():
    payload, status = _overlay_live_revenue_headline(_payload(), 99999.0)
    assert status == "failed_plausibility"
    assert payload["fiscal_years"][0]["total_revenue"] == 2910


def test_revenue_overlay_noop_on_missing():
    payload, status = _overlay_live_revenue_headline(_payload(), None)
    assert status == "no_live_value"
    assert payload["fiscal_years"][0]["total_revenue"] == 2910


# ── derived borrowing_pct_of_budget ─────────────────────────────────────
def test_borrowing_pct_is_derived_from_budget():
    payload = {
        "fiscal_years": [
            {"fiscal_year": "FY 2025/26", "appropriated_budget": 4292,
             "total_borrowing": 910, "borrowing_pct_of_budget": 99.9}  # declared bogus
        ]
    }
    rec = parse_fiscal_summary_payload(payload)[0]
    # 910 / 4292 * 100 = 21.2 — derived, ignoring the bogus declared 99.9.
    assert rec.borrowing_pct_of_budget == 21.2


def test_borrowing_pct_tracks_a_corrected_budget():
    # Same borrowing, different budgets → different (correct) shares.
    p1 = {"fiscal_years": [{"fiscal_year": "FY 2025/26", "appropriated_budget": 4190, "total_borrowing": 910}]}
    p2 = {"fiscal_years": [{"fiscal_year": "FY 2025/26", "appropriated_budget": 4292, "total_borrowing": 910}]}
    assert parse_fiscal_summary_payload(p1)[0].borrowing_pct_of_budget == 21.7
    assert parse_fiscal_summary_payload(p2)[0].borrowing_pct_of_budget == 21.2
