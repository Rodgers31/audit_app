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
    CANONICAL_BUDGET_BASIS,
    _apply_budget_estimates,
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


# ── The basis decision (2026-08-29) ─────────────────────────────────────
# The user chose COB's "original gross budget" as the canonical basis for
# past, present and future. The fixture was BACKFILLED with each year's gross
# from that year's COB report rather than relabelled — stamping "cob_gross"
# on a row holding a 4.19T Budget Policy Statement figure is precisely the
# conflation the gate exists to stop.
class TestBasisDecision:
    def test_canonical_basis_is_cob_gross(self):
        assert CANONICAL_BUDGET_BASIS == "cob_gross"

    def test_a_non_canonical_live_basis_is_refused(self):
        """POSITIVE CONTROL. COB's own net estimates (4.43T for FY2025/26)
        are a real figure from the same real document, in band, and inside
        the tolerance — and still must never land in a field defined as
        gross."""
        payload = {"fiscal_years": [dict(LATEST, budget_basis="cob_gross",
                                         appropriated_budget=4690)]}
        payload, status = _overlay_live_budget_headline(
            payload, 4430.0, basis="cob_net"
        )
        assert status == (
            "basis_not_canonical(live=cob_net,canonical=cob_gross)"
        )
        assert payload["fiscal_years"][0]["appropriated_budget"] == 4690

    def test_gross_promotes_onto_a_gross_row(self):
        """What the shipped fixture now does: FY2025/26 declares cob_gross
        and holds COB's published 4,690, so the live COB parse promotes."""
        payload = {"fiscal_years": [dict(LATEST, budget_basis="cob_gross",
                                         appropriated_budget=4690)]}
        payload, status = _overlay_live_budget_headline(payload, 4690.0)
        assert status == "promoted"
        assert payload["fiscal_years"][0]["_budget_source"] == "cob_ng_birr_live"


class TestOverlayTargetsTheReportsOwnYear:
    """An overlay must write to the year its SOURCE is about.

    ``max(fiscal_years)`` was safe only while the newest row was always the
    year COB had just reported on. Once Treasury's enacted FY2026/27
    estimates can be ingested months before COB's first FY2026/27 report,
    an unanchored overlay stamps COB's FY2025/26 headline onto FY2026/27.
    """

    def _two_years(self):
        return {"fiscal_years": [
            dict(LATEST, budget_basis="cob_gross", appropriated_budget=4690),
            {"fiscal_year": "FY 2026/27", "appropriated_budget": 5485.7,
             "budget_basis": "cob_gross"},
        ]}

    def test_writes_to_the_named_year_not_the_newest(self):
        payload, status = _overlay_live_budget_headline(
            self._two_years(), 4700.0, fiscal_year="FY 2025/26"
        )
        assert status == "promoted"
        rows = {r["fiscal_year"]: r for r in payload["fiscal_years"]}
        assert rows["FY 2025/26"]["appropriated_budget"] == 4700.0
        assert rows["FY 2026/27"]["appropriated_budget"] == 5485.7

    def test_positive_control_unanchored_would_hit_the_wrong_year(self):
        """Shows the defect the parameter prevents: with no fiscal year the
        FY2025/26 figure lands on the FY2026/27 row (and is then rejected
        only by the tolerance, which is luck, not a gate)."""
        payload, status = _overlay_live_budget_headline(
            self._two_years(), 4700.0
        )
        rows = {r["fiscal_year"]: r for r in payload["fiscal_years"]}
        assert rows["FY 2026/27"]["_cob_live_budget_billion"] == 4700.0
        assert "FY 2025/26" not in str(
            rows["FY 2025/26"].get("_cob_live_budget_billion")
        )

    def test_a_year_the_payload_does_not_have_is_not_invented(self):
        payload, status = _overlay_live_budget_headline(
            self._two_years(), 4700.0, fiscal_year="FY 2027/28"
        )
        assert status == "report_year_not_in_payload(FY 2027/28)"
        assert len(payload["fiscal_years"]) == 2


# ── Creating a fiscal year (Treasury enacted estimates) ────────────────
class _Estimates:
    """Stand-in for BudgetEstimates; only the fields the applier reads."""

    def __init__(
        self,
        fy="FY 2026/27",
        gross_billion=5485.7,
        # Mirrors BudgetEstimates.debt_redemption_kes, which is None whenever
        # the book's interest and redemption sub-totals did not reconcile.
        # Kept on the stub rather than letting the applier use getattr, so
        # removing the real field fails here instead of passing silently.
        debt_redemption_kes=1_061_600_000_000,
    ):
        self.fiscal_year = fy
        self.gross_budget_billion = gross_billion
        self.voted_gross_kes = 2_922_706_913_184
        self.cfs_kes = 2_562_973_919_672
        self.debt_redemption_kes = debt_redemption_kes
        self.page_refs = {"voted_total": 11, "cfs_summary": 1193}
        self.checks = ["voted current+capital==total"]
        self.source_url = "https://www.treasury.go.ke/x.pdf"


class TestApplyBudgetEstimates:
    def test_creates_a_fiscal_year_that_did_not_exist(self):
        """The whole point: no overlay in this domain could CREATE a row, so
        the site could not move to a new fiscal year until COB published —
        five months after that year began."""
        payload = {"fiscal_years": [dict(LATEST, budget_basis="cob_gross")]}
        payload, status = _apply_budget_estimates(payload, _Estimates())
        assert status == "created"
        rows = {r["fiscal_year"]: r for r in payload["fiscal_years"]}
        assert rows["FY 2026/27"]["appropriated_budget"] == 5485.7
        assert rows["FY 2026/27"]["budget_basis"] == "cob_gross"

    def test_the_new_row_carries_its_receipt(self):
        payload, _ = _apply_budget_estimates(
            {"fiscal_years": []}, _Estimates()
        )
        source = payload["fiscal_years"][0]["budget_basis_source"]
        assert "PDF p.11" in source["page"]
        assert "PDF p.1193" in source["page"]
        assert source["url"] == "https://www.treasury.go.ke/x.pdf"

    def test_is_idempotent(self):
        payload = {"fiscal_years": []}
        payload, first = _apply_budget_estimates(payload, _Estimates())
        payload, second = _apply_budget_estimates(payload, _Estimates())
        assert (first, second) == ("created", "updated")
        assert len(payload["fiscal_years"]) == 1

    def test_refuses_to_overwrite_a_row_on_another_basis(self):
        payload = {"fiscal_years": [
            {"fiscal_year": "FY 2026/27", "appropriated_budget": 4190,
             "budget_basis": "bps"}
        ]}
        payload, status = _apply_budget_estimates(payload, _Estimates())
        assert status == "basis_mismatch(row=bps,live=cob_gross)"
        assert payload["fiscal_years"][0]["appropriated_budget"] == 4190

    def test_implausible_figure_is_quarantined_not_inserted(self):
        """POSITIVE CONTROL for the plausibility gate on the INSERT path —
        a create must be gated exactly as hard as an overlay."""
        payload, status = _apply_budget_estimates(
            {"fiscal_years": []}, _Estimates(gross_billion=99999.0)
        )
        assert status == "failed_plausibility"
        assert payload["fiscal_years"] == []

    def test_rows_stay_in_fiscal_year_order(self):
        payload = {"fiscal_years": [dict(LATEST, budget_basis="cob_gross")]}
        payload, _ = _apply_budget_estimates(payload, _Estimates())
        labels = [r["fiscal_year"] for r in payload["fiscal_years"]]
        assert labels == sorted(labels)


# ── The shipped fixture ────────────────────────────────────────────────
class TestShippedFixture:
    """`grep-verify-before-listing`: assert against the file that ships, not
    a description of it."""

    def _fixture(self):
        import json
        from pathlib import Path

        path = (
            Path(__file__).resolve().parents[1]
            / "seeding" / "real_data" / "fiscal_summary.json"
        )
        return json.loads(path.read_text())

    def test_every_year_declares_a_budget_basis(self):
        """A row that carries a budget must say which measure it is on.

        Scoped to rows that actually carry one. A row may exist to carry a
        different figure — FY 2026/27 ships the revenue estimate, and its
        gross budget is overlaid live from the Programme Based Budget book by
        budget_estimates.py rather than duplicated here. Such a row must still
        say WHY the budget is absent, so an omission can never pass as a
        deliberate deferral.
        """
        for row in self._fixture()["fiscal_years"]:
            if row.get("appropriated_budget") is None:
                assert row.get("appropriated_budget_absent_reason"), row["fiscal_year"]
                continue
            assert row.get("budget_basis"), row["fiscal_year"]

    def test_every_declared_basis_carries_a_document_and_page(self):
        """No number without provenance — including the provenance of its
        DEFINITION."""
        for row in self._fixture()["fiscal_years"]:
            if row.get("appropriated_budget") is None:
                continue  # no budget figure, so no definition to source
            source = row.get("budget_basis_source") or {}
            assert source.get("url"), row["fiscal_year"]
            assert source.get("page"), row["fiscal_year"]
            assert source.get("quote"), row["fiscal_year"]

    def test_budgets_are_the_cob_gross_figures_not_the_bps_ones(self):
        """The values COB actually publishes. Cross-checked against a live
        parse of each report in tests/test_cob_headline_extraction.py."""
        rows = {r["fiscal_year"]: r for r in self._fixture()["fiscal_years"]}
        assert rows["FY 2023/24"]["appropriated_budget"] == 4340
        assert rows["FY 2024/25"]["appropriated_budget"] == 4490
        assert rows["FY 2025/26"]["appropriated_budget"] == 4690

    def test_the_superseded_bps_figures_are_kept_for_audit(self):
        rows = {r["fiscal_year"]: r for r in self._fixture()["fiscal_years"]}
        assert rows["FY 2025/26"]["_appropriated_budget_bps"] == 4190


class TestDebtRedemptionIsPublished:
    """The gross budget and the enacted headline differ mostly by redemption.

    Kenya's FY2026/27 gross budget is KSh 5,485.7B; the figure quoted in most
    budget coverage is ~4.82T. The difference is redemption of maturing debt
    (1,061.6B) coming out and the county equitable share going in. Without the
    redemption figure the page can assert that the two measures differ but not
    show why, which is the difference between an explanation and a claim.
    """

    def test_the_redemption_figure_reaches_the_row(self):
        payload = {"fiscal_years": []}
        out, status = _apply_budget_estimates(payload, _Estimates())
        row = out["fiscal_years"][0]
        assert status == "created"
        assert row["debt_redemption"] == 1061.6

    def test_it_reconciles_the_gross_figure_to_the_quoted_one(self):
        """5,485.7 − 1,061.6 = 4,424.1, and + ~400B county share ≈ 4.82T."""
        payload = {"fiscal_years": []}
        out, _ = _apply_budget_estimates(payload, _Estimates())
        row = out["fiscal_years"][0]
        national_excl_redemption = row["appropriated_budget"] - row["debt_redemption"]
        assert round(national_excl_redemption, 1) == 4424.1

    def test_an_unproved_split_is_not_published(self):
        """The parser returns None when the book's own sub-totals do not
        reconcile. A guessed redemption figure must never reach the page."""
        payload = {"fiscal_years": []}
        out, _ = _apply_budget_estimates(
            payload, _Estimates(debt_redemption_kes=None)
        )
        row = out["fiscal_years"][0]
        assert "debt_redemption" not in row
        assert row["appropriated_budget"] == 5485.7  # the gross figure still publishes

    def test_the_receipt_names_the_redemption_component(self):
        payload = {"fiscal_years": []}
        out, _ = _apply_budget_estimates(payload, _Estimates())
        composition = out["fiscal_years"][0]["budget_basis_source"]["composition"]
        assert "debt redemption 1,061.6B" in composition
