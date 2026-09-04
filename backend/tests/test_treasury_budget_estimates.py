"""Ingesting the ENACTED budget for a fiscal year COB has not reported on yet.

On 2026-08-29 the homepage still read "FY 2025/26", two months into FY2026/27.
That was NOT the frozen-COB defect fixed in 897a00d — the COB path was working
and current (its newest National Government BIRR really is the FY2025/26
nine-month report, because COB publishes at quarter-end + 45 days). The gap was
structural:

  * COB cannot publish an FY2026/27 report before ~15 November 2026, and
  * ``_overlay_live_budget_headline`` only ever MUTATED ``max(fiscal_years)``,
    so no overlay could ever CREATE a fiscal year.

Every fixture line below is REAL text, extracted on 2026-08-29 from the
National Treasury's FY2026/27 Approved Programme Based Budget Book
(29,637,635 bytes, 1,206 pages) at
https://www.treasury.go.ke/sites/default/files/Budget%20Books/Budget%20books%202026-2027/FY%202026%202027%20Programme%20Based%20Budget%20Book_Approved.pdf
— PDF page 11 (the voted total) and PDF page 1,193 (the CFS summary).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from seeding.domains.fiscal_summary.budget_estimates import (
    BudgetEstimatesError,
    build_estimates,
    extract_voted_gross_from_text,
    numbers_in_line,
    parse_cfs_summary_from_text,
    parse_fy_columns,
)

# ── Real page text ───────────────────────────────────────────────────
# PDF page 11: "Summary of Expenditure by Vote and Category 2026/2027", the
# last rows plus the total. The anchor and its figures sit on SEPARATE lines,
# exactly as pdfplumber renders them.
VOTED_PAGE = """GLOBAL BUDGET - CAPITAL & CURRENT
Summary of Expenditure by Vote and Category 2026/2027 (KShs)
GROSS CURRENT GROSS CAPITAL GROSS TOTAL
ESTIMATES ESTIMATES ESTIMATES
VOTE CODE TITLE 2026/2027 - KSHS
2141 National Gender and Equality Commission
667,738,000 - 667,738,000
2151 Independent Policing Oversight Authority
1,561,610,040 - 1,561,610,040
TOTAL VOTED EXPENDITURE ... KShs.
2,078,271,468,734 844,435,444,450 2,922,706,913,184
((vv))"""

# PDF page 1,193: "SUMMARY 1 - CONSLIDATED FUND SERVICES" (the typo is the
# publisher's). Note the stray spaces pdfplumber leaves inside right-aligned
# figures ("2 ,562,973,919,672", "9 86,725,816,391", "7 2,480,000") and that
# the page spells the same row both "Sub - Total" and "Sub-Total".
CFS_PAGE = """SUMMARY 1 - CONSLIDATED FUND SERVICES FY2026/27-MEDIUM TERM
CONSOLIDATED FUND SERVICES
ESTIMATES SUPP I ESTIMATES ESTIMATES ESTIMATES ESTIMATES ESTIMATES
2025/2026 2025/2026 2026/2027 2027/2028 2028/2029 2029/2030 2030/2031
PUBLIC DEBT
3 2,339,038,790 Kshs Kshs Kshs Kshs Kshs Kshs Kshs
INTEREST
2420000Interest - Internal 851,421,395,591 883,760,434,381 9 86,725,816,391 9 92,103,622,234 1 ,029,412,828,500 1,090,948,968,877 1 ,143,946,560,748
2410100Interest- External 246,268,214,714 242,771,420,966 2 67,511,793,402 3 06,913,121,186 3 44,179,346,304 373,847,084,209 3 95,792,345,423
Sub - Total Kshs 1,097,689,610,305 1,126,531,855,347 1 ,254,237,609,793 1 ,299,016,743,420 1 ,373,592,174,804 1,464,796,053,085 1 ,539,738,906,171
REDEMPTION
5210000Redemption - Internal 463,510,480,597 544,257,100,597 6 48,777,016,498 7 17,724,324,000 7 07,318,950,000 691,223,285,000 4 50,802,450,000
5210600Redemption - External 340,189,856,116 673,761,174,472 4 12,869,765,915 4 60,105,961,785 4 99,824,974,501 658,408,900,193 5 95,346,407,239
Sub - Total Kshs 803,700,336,713 1,218,018,275,069 1 ,061,646,782,413 1 ,177,830,285,785 1 ,207,143,924,501 1,349,632,185,193 1 ,046,148,857,239
Total: INTEREST & REDEMPTION Kshs 1,901,389,947,018 2,344,550,130,416 2 ,315,884,392,206 2 ,476,847,029,206 2 ,580,736,099,305 2,814,428,238,278 2 ,585,887,763,410
PENSIONS, SALARIES & ALLOWANCES AND OTHERS
2710100Pensions 234,898,447,748 234,898,447,748 2 41,937,772,895 2 50,474,277,797 2 56,886,297,846 264,578,358,497 2 72,501,180,968
2110000Salaries and Allowances 4,665,706,399 5,097,044,003 5,079,274,572 5,172,208,406 5,038,151,492 5 ,024,861,397 5,380,171,699
5220200Miscellaneous Services 71,000,000 71,000,000 72,480,000 72,480,000 72,480,000 7 2,480,000 72,480,000
5210600Guaranteed Debt - - - - - - -
2620100Subscriptions to International Organizations - - - - - - -
Sub-Total Kshs 239,635,154,147 240,066,491,752 2 47,089,527,466 2 55,718,966,202 2 61,996,929,338 269,675,699,894 2 77,953,832,666
GRAND TOTAL Kshs 2,141,025,101,165 2,584,616,622,168 2 ,562,973,919,672 2 ,732,565,995,408 2 ,842,733,028,643 3,084,103,938,172 2 ,863,841,596,076
((((iiii))))
Page 1 of 14"""

VOTED_FY2026_27 = (
    Decimal("2078271468734"),
    Decimal("844435444450"),
    Decimal("2922706913184"),
)


# ── Splitting figures that pdfplumber broke ──────────────────────────
class TestNumberRepair:
    @pytest.mark.parametrize(
        "line,expected",
        [
            ("Sub-Total Kshs 2 ,562,973,919,672", [Decimal("2562973919672")]),
            ("Interest - Internal 9 86,725,816,391", [Decimal("986725816391")]),
            ("Miscellaneous 7 2,480,000", [Decimal("72480000")]),
            ("x 1 ,029,412,828,500", [Decimal("1029412828500")]),
        ],
    )
    def test_leading_digit_is_rejoined(self, line, expected):
        assert numbers_in_line(line) == expected

    def test_adjacent_columns_are_never_fused(self):
        """The repair must not turn two columns into one 18-digit number.

        POSITIVE CONTROL for the rule above: "...000 71,..." looks exactly
        like a split figure to any rule that merges on proximity alone.
        """
        line = "5220200Miscellaneous Services 71,000,000 71,000,000 72,480,000"
        assert numbers_in_line(line) == [
            Decimal("71000000"),
            Decimal("71000000"),
            Decimal("72480000"),
        ]

    def test_dashes_are_not_numbers(self):
        assert numbers_in_line("5210600Guaranteed Debt - - - - - - -") == []


# ── The two page parsers ─────────────────────────────────────────────
class TestVotedTotal:
    def test_reads_the_three_gross_columns(self):
        assert extract_voted_gross_from_text(VOTED_PAGE) == VOTED_FY2026_27

    def test_anchor_and_figures_may_sit_on_different_lines(self):
        """The real book puts the label and the numbers on separate lines;
        a same-line scanner returns nothing, which is how the COB headline
        extractor produced no value for months."""
        assert "TOTAL VOTED EXPENDITURE ... KShs.\n2,078" in VOTED_PAGE

    def test_missing_anchor_returns_none(self):
        assert extract_voted_gross_from_text("no totals here") is None
        assert extract_voted_gross_from_text("") is None


class TestCfsSummary:
    def test_column_order_marks_the_supplementary(self):
        """FY2025/26 appears TWICE — printed estimates and Supplementary I.
        Picking by year alone would be a coin flip between an original and a
        revised budget."""
        assert parse_fy_columns(CFS_PAGE) == [
            ("FY 2025/26", False),
            ("FY 2025/26", True),
            ("FY 2026/27", False),
            ("FY 2027/28", False),
            ("FY 2028/29", False),
            ("FY 2029/30", False),
            ("FY 2030/31", False),
        ]

    def test_reads_the_grand_total_per_year(self):
        cfs = parse_cfs_summary_from_text(CFS_PAGE)
        assert cfs["FY 2026/27"] == Decimal("2562973919672")
        # The FY2025/26 entry must be the PRINTED column, not Supplementary I
        # (2,584,616,622,168) — that is what makes the COB cross-check valid.
        assert cfs["FY 2025/26"] == Decimal("2141025101165")

    def test_a_page_without_the_anchors_yields_nothing(self):
        assert parse_cfs_summary_from_text("Vote 2151 Part F: Summary") == {}

    def test_components_that_do_not_reconcile_are_refused(self):
        """GATE 2 must FIRE: corrupt the pensions sub-total so
        interest+other no longer equals the grand total."""
        broken = CFS_PAGE.replace(
            "Sub-Total Kshs 239,635,154,147 240,066,491,752 2 47,089,527,466",
            "Sub-Total Kshs 239,635,154,147 240,066,491,752 9 47,089,527,466",
        )
        with pytest.raises(BudgetEstimatesError) as exc:
            parse_cfs_summary_from_text(broken)
        assert exc.value.reason == "cfs_does_not_reconcile"

    def test_missing_component_rows_are_refused_not_trusted(self):
        """A GRAND TOTAL nobody can check against its own parts is not a
        figure, it is a claim."""
        no_parts = "\n".join(
            line
            for line in CFS_PAGE.splitlines()
            if "INTEREST & REDEMPTION" not in line
        )
        with pytest.raises(BudgetEstimatesError) as exc:
            parse_cfs_summary_from_text(no_parts)
        assert exc.value.reason == "cfs_components_not_found"


# ── The gate ─────────────────────────────────────────────────────────
def _cfs():
    return parse_cfs_summary_from_text(CFS_PAGE)


class TestGate:
    def test_publishes_the_enacted_gross_budget(self):
        est = build_estimates(
            fiscal_year="FY 2026/27", voted=VOTED_FY2026_27, cfs_by_year=_cfs()
        )
        # 2,922,706,913,184 voted + 2,562,973,919,672 CFS
        assert est.gross_budget_kes == Decimal("5485680832856")
        assert round(est.gross_budget_billion, 1) == 5485.7

    def test_prior_year_cfs_is_checked_against_cob(self):
        est = build_estimates(
            fiscal_year="FY 2026/27", voted=VOTED_FY2026_27, cfs_by_year=_cfs()
        )
        assert any("matches COB" in c for c in est.checks)

    def test_prior_year_cfs_mismatch_quarantines(self):
        """GATE 3 must FIRE — the cross-PUBLISHER check.

        Treasury's own book prints FY2025/26 CFS as 2.141T and COB
        independently publishes 2.14T. Move Treasury's figure and the two
        publishers no longer agree, which means the column mapping is wrong
        and nothing on this page may be published.
        """
        bad = dict(_cfs())
        bad["FY 2025/26"] = Decimal("3141025101165")
        with pytest.raises(BudgetEstimatesError) as exc:
            build_estimates(
                fiscal_year="FY 2026/27", voted=VOTED_FY2026_27, cfs_by_year=bad
            )
        assert exc.value.reason == "prior_year_cfs_mismatch"

    def test_prior_year_column_missing_quarantines(self):
        bad = {k: v for k, v in _cfs().items() if k != "FY 2025/26"}
        with pytest.raises(BudgetEstimatesError) as exc:
            build_estimates(
                fiscal_year="FY 2026/27", voted=VOTED_FY2026_27, cfs_by_year=bad
            )
        assert exc.value.reason == "prior_year_cfs_missing"

    def test_voted_columns_that_do_not_add_up_quarantine(self):
        """GATE 1 must FIRE."""
        with pytest.raises(BudgetEstimatesError) as exc:
            build_estimates(
                fiscal_year="FY 2026/27",
                voted=(Decimal("1"), Decimal("1"), Decimal("2922706913184")),
                cfs_by_year=_cfs(),
            )
        assert exc.value.reason == "voted_does_not_reconcile"

    def test_a_year_with_no_original_column_is_not_invented(self):
        with pytest.raises(BudgetEstimatesError) as exc:
            build_estimates(
                fiscal_year="FY 2031/32",
                voted=VOTED_FY2026_27,
                cfs_by_year=_cfs(),
            )
        assert exc.value.reason == "cfs_year_not_found"

    def test_units_slip_is_caught(self):
        """A book read in shillings-million would land ~1,000,000x low.

        It trips the cross-publisher check FIRST — Treasury's FY2025/26 CFS
        can no longer match COB's 2.14T — which is the stronger verdict, so
        that is what the record should say.
        """
        millions = {k: v / 1_000_000 for k, v in _cfs().items()}
        with pytest.raises(BudgetEstimatesError) as exc:
            build_estimates(
                fiscal_year="FY 2026/27",
                voted=tuple(v / 1_000_000 for v in VOTED_FY2026_27),
                cfs_by_year=millions,
            )
        assert exc.value.reason == "prior_year_cfs_mismatch"

    def test_plausibility_band_fires_where_no_cross_check_exists(self):
        """POSITIVE CONTROL for the band itself, on a year with no COB
        figure on file — otherwise the band could be dead code hiding
        behind the cross-check."""
        with pytest.raises(BudgetEstimatesError) as exc:
            build_estimates(
                fiscal_year="FY 2030/31",
                voted=(
                    Decimal("25000000000000"),
                    Decimal("25000000000000"),
                    Decimal("50000000000000"),
                ),
                cfs_by_year=_cfs(),
            )
        assert exc.value.reason == "gross_outside_plausible_band"

    def test_a_skipped_cross_check_says_so(self):
        """`no-silent-fallbacks`: when no COB figure exists for the prior
        year the strongest gate did not run, and the record must admit it
        rather than reporting three checks when two ran."""
        est = build_estimates(
            fiscal_year="FY 2030/31",
            voted=VOTED_FY2026_27,
            cfs_by_year=_cfs(),
        )
        assert any("SKIPPED" in c for c in est.checks)


class TestRedemptionSplit:
    """The redemption sub-total, gated by its own identity.

    Kenya's FY2026/27 gross budget is 5,485.7B; most budget coverage quotes
    ~4.82T. The difference is redemption of maturing debt coming out and the
    county equitable share going in. Publishing the redemption figure is what
    turns "these measures differ" into "here is by how much and why" — so it
    has to be right, and it is only trusted when the page's own interest and
    redemption sub-totals add up to their combined line.
    """

    def test_the_redemption_subtotal_is_read(self):
        cfs = parse_cfs_summary_from_text(CFS_PAGE)
        # "Sub - Total Kshs" under REDEMPTION, 2026/2027 column.
        assert cfs.redemption["FY 2026/27"] == Decimal("1061646782413")

    def test_it_reconciles_to_the_combined_line(self):
        """1,254,237,609,793 interest + 1,061,646,782,413 redemption
        = 2,315,884,392,206, the 'Total: INTEREST & REDEMPTION' figure."""
        cfs = parse_cfs_summary_from_text(CFS_PAGE)
        assert cfs.redemption["FY 2026/27"] + Decimal("1254237609793") == Decimal(
            "2315884392206"
        )

    def test_a_split_that_does_not_reconcile_is_withheld(self):
        """THE gate. If the sub-totals do not add up to their own combined
        line, the rows were mis-selected and no redemption figure is
        published — the CFS total still is, so the page keeps its headline.
        """
        broken = CFS_PAGE.replace(
            "Sub - Total Kshs 803,700,336,713 1,218,018,275,069 1 ,061,646,782,413",
            "Sub - Total Kshs 803,700,336,713 1,218,018,275,069 9 99,999,999,999",
        )
        assert broken != CFS_PAGE, "fixture text did not change — test is vacuous"

        cfs = parse_cfs_summary_from_text(broken)
        assert cfs.totals["FY 2026/27"] == Decimal("2562973919672")
        assert "FY 2026/27" not in cfs.redemption
