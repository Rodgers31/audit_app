"""Gates on the Budget Summary revenue extractor.

Every gate gets a test that makes it FIRE. A gate that has only ever been seen
to pass is not a gate — it is a comment. The figure this module publishes goes
straight onto the homepage's debt-service-to-revenue line, so a parse that
slipped a column would be a published falsehood about how much of Kenya's
revenue services its debt.

Numbers are the real ones from the Budget Summary for the FY 2026/27 Budget,
Table 2 (PDF p.14):

    FY 2025/26   Budget 2,754.7   Sup I 2,784.4
    FY 2026/27   BPS 2026 2,901.9 (+ AiA 632.4 = 3,534.2)
                 Approved 2,985.7 (+ AiA 644.0 = 3,629.7)
"""

from decimal import Decimal

import pytest

from seeding.domains.fiscal_summary.revenue_estimates import (
    FiscalFrameworkTable,
    RevenueEstimatesError,
    build_revenue_estimates,
    build_revenue_series,
    parse_fiscal_framework,
)

D = Decimal


def table(**over) -> FiscalFrameworkTable:
    base = dict(
        ordinary_revenue={
            "FY2024/25": [D("2420.2")],
            "FY2025/26": [D("2754.7"), D("2784.4")],
            "FY2026/27": [D("2901.9"), D("2985.7")],
        },
        total_revenues={
            "FY2024/25": [D("2923.6")],
            "FY2025/26": [D("3321.7"), D("3399.1")],
            "FY2026/27": [D("3534.2"), D("3629.7")],
        },
        ministerial_aia={
            "FY2024/25": [D("503.4")],
            "FY2025/26": [D("566.9"), D("614.6")],
            "FY2026/27": [D("632.4"), D("644.0")],
        },
        page=14,
    )
    base.update(over)
    return FiscalFrameworkTable(**base)


class TestHappyPath:
    def test_publishes_the_approved_column_not_the_bps_one(self):
        est = build_revenue_estimates(
            fiscal_year="FY 2026/27",
            table=table(),
            known_prior_ordinary_billion=2784.4,
        )
        # The whole point: 2,985.7 is the approved budget; 2,901.9 is the BPS
        # projection it supersedes. Reading order alone cannot tell them apart.
        assert est.ordinary_revenue_billion == D("2985.7")
        assert est.bps_column_billion == D("2901.9")
        assert est.total_revenue_incl_aia_billion == D("3629.7")
        assert est.ministerial_aia_billion == D("644.0")

    def test_records_every_check_it_actually_ran(self):
        est = build_revenue_estimates(
            fiscal_year="FY 2026/27",
            table=table(),
            known_prior_ordinary_billion=2784.4,
        )
        joined = " | ".join(est.checks)
        assert "2901.9B matches a non-chosen column" in joined
        assert "ordinary+AiA==total revenues" in joined
        assert "FY 2025/26 ordinary revenue 2784.4B matches" in joined

    def test_says_so_when_the_prior_year_check_could_not_run(self):
        """A skipped check must never read as a passed one."""
        est = build_revenue_estimates(
            fiscal_year="FY 2026/27", table=table(), known_prior_ordinary_billion=None
        )
        assert any("SKIPPED" in c for c in est.checks)


class TestGatesFire:
    def test_gate1_rejects_a_column_that_does_not_reconcile(self):
        """ordinary + AiA must equal the printed total for that column."""
        broken = table(
            ministerial_aia={
                "FY2024/25": [D("503.4")],
                "FY2025/26": [D("566.9"), D("614.6")],
                "FY2026/27": [D("632.4"), D("500.0")],  # 2985.7+500 != 3629.7
            }
        )
        with pytest.raises(RevenueEstimatesError) as e:
            build_revenue_estimates(fiscal_year="FY 2026/27", table=broken)
        assert e.value.reason == "revenue_does_not_reconcile"

    def test_gate2_refuses_when_no_column_matches_the_bps_figure(self):
        """If neither column is the BPS one, we cannot say which is approved."""
        drifted = table(
            ordinary_revenue={
                "FY2024/25": [D("2420.2")],
                "FY2025/26": [D("2754.7"), D("2784.4")],
                "FY2026/27": [D("2800.0"), D("2985.7")],
            }
        )
        with pytest.raises(RevenueEstimatesError) as e:
            build_revenue_estimates(fiscal_year="FY 2026/27", table=drifted)
        assert e.value.reason == "bps_column_not_identified"

    def test_gate2_refuses_when_the_chosen_column_is_the_bps_one(self):
        """If the column we would publish IS the BPS projection, refuse.

        The approved estimate is what gets published; publishing the BPS
        figure under its name would be a different claim.
        """
        ambiguous = table(
            ordinary_revenue={
                "FY2025/26": [D("2754.7"), D("2784.4")],
                "FY2026/27": [D("2901.9"), D("2901.9")],
            }
        )
        with pytest.raises(RevenueEstimatesError) as e:
            build_revenue_estimates(fiscal_year="FY 2026/27", table=ambiguous)
        assert e.value.reason == "chosen_column_is_the_bps_one"

    def test_gate2_refuses_a_year_with_no_bps_figure_on_file(self):
        """Without the cross-document anchor there is no way to choose."""
        future = FiscalFrameworkTable(
            ordinary_revenue={"FY2027/28": [D("3387.9"), D("3390.0")]},
            total_revenues={"FY2027/28": [D("4044.3"), D("4038.9")]},
            ministerial_aia={"FY2027/28": [D("656.4"), D("648.9")]},
        )
        with pytest.raises(RevenueEstimatesError) as e:
            build_revenue_estimates(fiscal_year="FY 2027/28", table=future)
        assert e.value.reason == "no_bps_figure_on_file"

    def test_gate3_rejects_a_book_that_disagrees_about_the_prior_year(self):
        """A slipped column shows up as a prior year we can check."""
        with pytest.raises(RevenueEstimatesError) as e:
            build_revenue_estimates(
                fiscal_year="FY 2026/27",
                table=table(),
                known_prior_ordinary_billion=2420.2,  # that is FY2024/25's
            )
        assert e.value.reason == "prior_year_revenue_mismatch"

    def test_gate4_rejects_an_implausible_figure(self):
        """Catches a units error — billions read as millions, say."""
        tiny = table(
            ordinary_revenue={
                "FY2025/26": [D("2754.7"), D("2784.4")],
                "FY2026/27": [D("2901.9"), D("2.9857")],
            },
            total_revenues={
                "FY2025/26": [D("3321.7"), D("3399.1")],
                "FY2026/27": [D("3534.2"), D("3.6297")],
            },
            ministerial_aia={
                "FY2025/26": [D("566.9"), D("614.6")],
                "FY2026/27": [D("632.4"), D("0.644")],
            },
        )
        with pytest.raises(RevenueEstimatesError) as e:
            build_revenue_estimates(fiscal_year="FY 2026/27", table=tiny)
        assert e.value.reason == "revenue_outside_plausible_band"

    def test_refuses_a_year_printed_with_only_one_column(self):
        settled = FiscalFrameworkTable(
            ordinary_revenue={"FY2026/27": [D("2985.7")]},
            total_revenues={"FY2026/27": [D("3629.7")]},
            ministerial_aia={"FY2026/27": [D("644.0")]},
        )
        with pytest.raises(RevenueEstimatesError) as e:
            build_revenue_estimates(fiscal_year="FY 2026/27", table=settled)
        assert e.value.reason == "budget_year_not_two_columns"

    def test_refuses_a_year_the_table_does_not_carry(self):
        with pytest.raises(RevenueEstimatesError) as e:
            build_revenue_estimates(fiscal_year="FY 2030/31", table=table())
        assert e.value.reason == "fiscal_year_not_in_table"


class TestColumnGrid:
    """The bug this class exists for.

    Table 2 is a uniform grid whose year labels sit over the FIRST column of
    their group, not centred on it. Assigning each number to its nearest year
    label therefore pushed a budget year's SECOND column under the following
    year — which silently reduced FY2026/27 to one column and made the
    approved figure unfindable.
    """

    @staticmethod
    def _word(text, x0, top, width=25):
        # Width must stay under the ~31pt column pitch, or the glyph-run
        # rejoiner (gap < 1.6) welds neighbouring cells into one token.
        return {"text": text, "x0": x0, "x1": x0 + width, "top": top}

    def _page(self):
        # Real x-positions from the FY2026/27 Budget Summary, PDF p.14.
        header = [
            ("FY2023/24", 225), ("FY2024/25", 257), ("FY2025/26", 307),
            ("FY2026/27", 369), ("FY2027/28", 415), ("FY2028/29", 448),
            # the "% of GDP" half repeats every label
            ("FY2023/24", 480), ("FY2024/25", 514), ("FY2025/26", 564),
            ("FY2026/27", 627), ("FY2027/28", 674), ("FY2028/29", 706),
        ]
        words = [self._word(t, x, 92) for t, x in header]
        rows = {
            94: ("2.0TOTALREVENUES", [2702.7, 2923.6, 3321.7, 3399.1, 3534.2, 3629.7, 4038.9, 4337.2]),
            96: ("2.1OrdinaryRevenue", [2288.9, 2420.2, 2754.7, 2784.4, 2901.9, 2985.7, 3390.0, 3658.0]),
            98: ("2.2MinisterialAiA", [413.7, 503.4, 566.9, 614.6, 632.4, 644.0, 648.9, 679.2]),
        }
        grid_x = [236, 270, 300, 331, 363, 394, 426, 459]
        for top, (label, values) in rows.items():
            words.append(self._word(label, 75, top))
            for x, v in zip(grid_x, values):
                words.append(self._word(f"{v:,.1f}", x, top))
            # "% of GDP" half — must be ignored entirely.
            for n, x in enumerate([500, 534, 564, 595, 629, 659, 692, 724]):
                words.append(self._word(f"{17.0 + n / 10:.1f}", x, top))
        return words

    def test_a_budget_years_two_columns_stay_with_that_year(self):
        t = parse_fiscal_framework(self._page(), page=14)
        assert t.ordinary_revenue["FY2026/27"] == [D("2901.9"), D("2985.7")]
        assert t.ordinary_revenue["FY2025/26"] == [D("2754.7"), D("2784.4")]

    def test_settled_years_keep_exactly_one_column(self):
        t = parse_fiscal_framework(self._page(), page=14)
        assert t.ordinary_revenue["FY2023/24"] == [D("2288.9")]
        assert t.ordinary_revenue["FY2024/25"] == [D("2420.2")]

    def test_the_share_of_gdp_half_is_not_read_as_money(self):
        t = parse_fiscal_framework(self._page(), page=14)
        for cols in t.ordinary_revenue.values():
            for v in cols:
                assert v > 1000, f"{v} looks like a % of GDP, not KSh billion"

    def test_the_grid_end_to_end_yields_the_approved_figure(self):
        est = build_revenue_estimates(
            fiscal_year="FY 2026/27",
            table=parse_fiscal_framework(self._page(), page=14),
            known_prior_ordinary_billion=2784.4,
        )
        assert est.ordinary_revenue_billion == D("2985.7")


class TestSeries:
    """The whole revenue series comes from ONE document.

    Table 2 carries settled actuals, the current year's supplementary and the
    budget year, so nothing in the series needs to be stored. A year that
    fails a gate is quarantined on its own — one bad column must not withhold
    the other five, and must never be published.
    """

    def _full(self, **over):
        base = dict(
            ordinary_revenue={
                "FY2023/24": [D("2288.9")],
                "FY2024/25": [D("2420.2")],
                "FY2025/26": [D("2754.7"), D("2784.4")],
                "FY2026/27": [D("2901.9"), D("2985.7")],
                "FY2027/28": [D("3390.0")],
            },
            total_revenues={
                "FY2023/24": [D("2702.7")],
                "FY2024/25": [D("2923.6")],
                "FY2025/26": [D("3321.7"), D("3399.1")],
                "FY2026/27": [D("3534.2"), D("3629.7")],
                "FY2027/28": [D("4038.9")],
            },
            ministerial_aia={
                "FY2023/24": [D("413.7")],
                "FY2024/25": [D("503.4")],
                "FY2025/26": [D("566.9"), D("614.6")],
                "FY2026/27": [D("632.4"), D("644.0")],
                "FY2027/28": [D("648.9")],
            },
            page=14,
        )
        base.update(over)
        return FiscalFrameworkTable(**base)

    def test_derives_every_year_through_the_budget_year(self):
        pub, _ = build_revenue_series(self._full(), through_fiscal_year="FY 2026/27")
        assert {fy: float(e.ordinary_revenue_billion) for fy, e in pub.items()} == {
            "FY 2023/24": 2288.9,
            "FY 2024/25": 2420.2,
            "FY 2025/26": 2784.4,  # Sup I, not the original Budget column
            "FY 2026/27": 2985.7,  # Approved, not the BPS column
        }

    def test_forward_projections_are_not_published(self):
        """A projection is a different claim from an actual or an estimate."""
        pub, quar = build_revenue_series(self._full(), through_fiscal_year="FY 2026/27")
        assert "FY 2027/28" not in pub
        assert quar["FY 2027/28"] == "forward_projection_not_published"

    def test_one_bad_year_does_not_withhold_the_others(self):
        broken = self._full(
            ministerial_aia={
                "FY2023/24": [D("413.7")],
                "FY2024/25": [D("999.9")],  # breaks that year's identity only
                "FY2025/26": [D("566.9"), D("614.6")],
                "FY2026/27": [D("632.4"), D("644.0")],
                "FY2027/28": [D("648.9")],
            }
        )
        pub, quar = build_revenue_series(broken, through_fiscal_year="FY 2026/27")
        assert quar["FY 2024/25"] == "revenue_does_not_reconcile"
        assert "FY 2024/25" not in pub
        assert set(pub) == {"FY 2023/24", "FY 2025/26", "FY 2026/27"}

    def test_a_settled_year_the_bps_contradicts_is_quarantined(self):
        """Cross-document disagreement is a parse error until proven otherwise."""
        drifted = self._full(
            ordinary_revenue={
                "FY2023/24": [D("2000.0")],  # BPS publishes 2,288.9
                "FY2024/25": [D("2420.2")],
                "FY2025/26": [D("2754.7"), D("2784.4")],
                "FY2026/27": [D("2901.9"), D("2985.7")],
                "FY2027/28": [D("3390.0")],
            }
        )
        pub, quar = build_revenue_series(drifted, through_fiscal_year="FY 2026/27")
        assert quar["FY 2023/24"] == "bps_disagrees_on_settled_year"
        assert "FY 2023/24" not in pub

    def test_a_multi_column_year_with_no_anchor_is_refused(self):
        """Without an anchor the column ORDER is an assumption, not a fact.

        Publishing the rightmost anyway is how a BPS projection would get
        published as the approved estimate.
        """
        unanchored = FiscalFrameworkTable(
            ordinary_revenue={"FY2029/30": [D("4200.0"), D("4300.0")]},
            total_revenues={"FY2029/30": [D("4900.0"), D("5000.0")]},
            ministerial_aia={"FY2029/30": [D("700.0"), D("700.0")]},
        )
        pub, quar = build_revenue_series(unanchored, through_fiscal_year="FY 2029/30")
        assert quar["FY 2029/30"] == "no_bps_figure_on_file"
        assert pub == {}
