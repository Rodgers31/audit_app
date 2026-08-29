"""COB NG-BIRR headline extraction — three stacked causes of silence.

``fiscal_summary`` logged ``budget=no_live_value revenue=no_live_value`` on
every run. Three INDEPENDENT bugs each guaranteed that outcome, so fixing
any one alone would have changed nothing:

1. Anchors were written from documented phrasing, not the real report. The
   FY2025/26 report says "original gross budget"; none of the configured
   anchors ("approved budget", "gross estimates", "total budget", ...)
   appear in it.
2. The scanner iterated ``splitlines()``, but the report wraps prose
   mid-sentence, so an anchor and its figure land on different lines.
3. It read ``pages[:8]``; the Executive Summary is on page 23.

The prose below is verbatim from the FY2025/26 nine-month report (page 23).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from seeding.domains.national_budget.headline import (
    extract_budget_bases_from_text,
    extract_overall_budget_billion_from_text,
    extract_total_revenue_billion_from_text,
    unwrap,
)

# Verbatim, INCLUDING the mid-sentence line wraps and hyphenation that
# pdfplumber produces for this page.
REAL_WRAPPED = """The National Government's original gross budget for FY 2025/26 amounts to Kshs. 4.69 trillion, compared
to Kshs.4.37 trillion in the FY 2024/25 after Supplementary III Estimates. This comprises Kshs.744.84
billion for ministerial development expenditure, which was 16 per cent of the original gross national
budget and 29 per cent of the original gross ministerial budget of Kshs.2.55 trillion. Recurrent vote allo-
cation amounts to Kshs.3.95 trillion, comprising the ministerial recurrent allocation of Kshs.1.80 trillion
into the Consolidated Fund amounted to Kshs. 3.21 trillion, representing 72 per cent of the original net
estimates of Kshs.4.43 trillion, compared to the Kshs.2.75 trillion (62 per cent) received in the same"""


class TestUnwrap:
    def test_joins_wrapped_lines(self):
        assert "original net estimates of Kshs.4.43 trillion" in unwrap(REAL_WRAPPED)

    def test_dehyphenates_across_the_break(self):
        # "allo-\ncation" must become "allocation", not "allo cation".
        assert "allocation amounts to" in unwrap(REAL_WRAPPED)

    def test_empty_input(self):
        assert unwrap("") == ""


class TestBudgetExtraction:
    def test_extracts_gross_from_real_wrapped_prose(self):
        """Bugs 1 and 2 together: real anchor, split across lines."""
        assert extract_budget_bases_from_text(REAL_WRAPPED)["gross"] == Decimal("4690.00")

    def test_extracts_net_estimates_separately(self):
        assert extract_budget_bases_from_text(REAL_WRAPPED)["net"] == Decimal("4430.00")

    def test_prior_year_comparison_is_not_mistaken_for_this_year(self):
        """The sentence continues ", compared to Kshs.4.37 trillion in the FY
        2024/25". Reading the LARGEST figure near the anchor, or scanning the
        whole window, can return the prior year. The first figure AFTER the
        anchor is the one the sentence is about."""
        assert extract_overall_budget_billion_from_text(REAL_WRAPPED) == Decimal("4690.00")

    def test_old_anchor_wording_would_have_found_nothing(self):
        """Documents WHY this was silent: the old anchors are absent."""
        low = REAL_WRAPPED.lower()
        for stale in ("approved budget", "gross estimates", "total budget",
                      "overall budget", "annual budget", "total expenditure"):
            assert stale not in low

    def test_absent_anchor_returns_none_not_zero(self):
        assert extract_overall_budget_billion_from_text("no budget here") is None

    def test_empty_text(self):
        assert extract_budget_bases_from_text("") == {"gross": None, "net": None}

    def test_trillion_and_billion_both_normalise_to_billions(self):
        assert extract_overall_budget_billion_from_text(
            "the gross budget of Kshs.703.07 billion"
        ) == Decimal("703.07")


class TestRevenueIsDeliberatelyNotExtracted:
    def test_quarterly_actuals_are_never_promoted_to_an_annual_field(self):
        """The report gives NINE-MONTH cumulative actuals (tax revenue
        Kshs.1.72 trillion) while fiscal_summaries.total_revenue is an
        ANNUAL figure (2,910B). Promoting one onto the other manufactures a
        ~40% variance out of a period mismatch."""
        text = ("The Tax revenue stream contributed the highest proportion of "
                "receipts, recording 54 per cent (Kshs.1.72 trillion)")
        assert extract_total_revenue_billion_from_text(text) is None


class TestBasisGate:
    """Gross (4.69T), net (4.43T) and the BPS figure the fixture holds
    (4.19T) are three different measures. A 15% numeric tolerance cannot
    tell a revision from a redefinition — gross sits 12% away and would be
    promoted silently, moving the homepage headline with nobody deciding."""

    def _payload(self, **row):
        base = {"fiscal_year": "FY 2025/26", "appropriated_budget": 4190,
                "total_revenue": 2910, "tax_revenue": 2560,
                "non_tax_revenue": 350, "recurrent_spending": 2850,
                "development_spending": 672}
        base.update(row)
        return {"fiscal_years": [base]}

    def test_refuses_to_promote_onto_an_undeclared_basis(self):
        from seeding.domains.fiscal_summary.fetcher import (
            _overlay_live_budget_headline,
        )

        payload, status = _overlay_live_budget_headline(self._payload(), 4690.0)
        # "undeclared" and "mismatch" are reported distinctly: one means the
        # row never said what it holds, the other that it holds something
        # else. Both refuse; only the second implies a known conflict.
        assert status.startswith("basis_undeclared")
        assert payload["fiscal_years"][0]["appropriated_budget"] == 4190

    def test_records_the_live_value_for_visibility_even_when_refusing(self):
        """Refusing must not mean discarding — the figure is kept so the
        mismatch is inspectable rather than invisible."""
        from seeding.domains.fiscal_summary.fetcher import (
            _overlay_live_budget_headline,
        )

        payload, _ = _overlay_live_budget_headline(self._payload(), 4690.0)
        row = payload["fiscal_years"][0]
        assert row["_cob_live_budget_billion"] == 4690.0
        assert row["_cob_live_budget_basis"] == "cob_gross"

    def test_promotes_when_the_row_declares_the_same_basis(self):
        from seeding.domains.fiscal_summary.fetcher import (
            _overlay_live_budget_headline,
        )

        payload, status = _overlay_live_budget_headline(
            self._payload(budget_basis="cob_gross", appropriated_budget=4600),
            4690.0,
        )
        assert status == "promoted"
        assert payload["fiscal_years"][0]["appropriated_budget"] == 4690.0

    def test_missing_live_value_is_still_a_no_op(self):
        from seeding.domains.fiscal_summary.fetcher import (
            _overlay_live_budget_headline,
        )

        payload, status = _overlay_live_budget_headline(self._payload(), None)
        assert status == "no_live_value"
        assert payload["fiscal_years"][0]["appropriated_budget"] == 4190
