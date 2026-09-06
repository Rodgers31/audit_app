"""The financial-health index must measure more than one thing.

It used to be::

    health_score = utilization              if utilization <= 95
                 = 90                       if 95 < utilization <= 100
                 = max(0, 80 - (util-100))  if utilization > 100

A piecewise transform of ONE input. A county that had spent 42.9% of its
budget was shown "42.9/100" with a grade of B-, immediately beside a Budget
Utilisation figure of 42.9% — the same number twice, the second time wearing
the word "health". And ``total_allocated == 0`` produced 0.0, which graded a
county with no budget data a C.

It is now an equal-weighted mean of components each derived from a published
figure, reported with the score so it can be taken apart.
"""

import pytest

from main import (
    _MIN_HEALTH_COMPONENTS,
    _PENDING_BILLS_SEVERE_SHARE,
    county_financial_health,
)

FULL = dict(
    total_allocated=10_000_000_000,
    total_spent=5_000_000_000,
    pending_bills=500_000_000,
    audit_status="qualified",
    own_source_target=1_000_000_000,
    own_source_actual=400_000_000,
)


def health(**over):
    return county_financial_health(**{**FULL, **over})


class TestItIsACompositeNow:
    def test_it_uses_every_component_it_can(self):
        result = health()

        assert {c["name"] for c in result["components"]} == {
            "budget_absorption",
            "own_source_revenue",
            "pending_bills",
            "audit_opinion",
        }

    def test_the_score_is_not_the_absorption_figure(self):
        """The whole point. 50% absorbed must not produce a score of 50."""
        result = health()
        absorption = next(
            c for c in result["components"] if c["name"] == "budget_absorption"
        )

        assert absorption["observed"] == 50.0
        assert result["score"] != 50.0

    def test_the_components_are_reported_so_the_score_can_be_taken_apart(self):
        result = health()

        for component in result["components"]:
            assert component["basis"], component
            assert "observed" in component
        assert result["weighting"] == "equal"

    def test_the_score_is_the_mean_of_the_components(self):
        result = health()
        expected = sum(c["score"] for c in result["components"]) / len(
            result["components"]
        )

        assert result["score"] == pytest.approx(round(expected, 1))


class TestComponents:
    def test_absorption_is_scored_symmetrically_about_full_spending(self):
        """Under-spending is a failure to deliver; over-spending is a failure
        to budget. 80% and 120% are equally far from spending the budget."""
        under = health(total_spent=8_000_000_000)
        over = health(total_spent=12_000_000_000)

        def absorption(r):
            return next(
                c["score"] for c in r["components"] if c["name"] == "budget_absorption"
            )

        assert absorption(under) == absorption(over) == 80.0

    def test_revenue_performance_is_capped_at_target(self):
        """A lowballed target must not buy a score above 100."""
        result = health(own_source_actual=5_000_000_000)  # 500% of target
        osr = next(
            c for c in result["components"] if c["name"] == "own_source_revenue"
        )

        assert osr["score"] == 100.0
        assert osr["observed"] == 500.0

    def test_pending_bills_score_falls_as_the_burden_rises(self):
        def bills(share_pct):
            r = health(pending_bills=10_000_000_000 * share_pct / 100)
            return next(
                c["score"] for c in r["components"] if c["name"] == "pending_bills"
            )

        assert bills(0) == 100.0
        assert bills(_PENDING_BILLS_SEVERE_SHARE) == 0.0
        assert bills(_PENDING_BILLS_SEVERE_SHARE * 2) == 0.0  # floored, not negative
        assert bills(5) > bills(15)

    @pytest.mark.parametrize(
        "opinion,expected",
        [("clean", 100.0), ("qualified", 60.0), ("adverse", 20.0), ("disclaimer", 0.0)],
    )
    def test_the_audit_opinion_orders_as_the_auditor_general_orders_it(
        self, opinion, expected
    ):
        result = health(audit_status=opinion)
        score = next(
            c["score"] for c in result["components"] if c["name"] == "audit_opinion"
        )

        assert score == expected

    def test_a_pending_audit_contributes_nothing(self):
        """"pending" is not an opinion — it must not score as one."""
        result = health(audit_status="pending")

        assert "audit_opinion" not in {c["name"] for c in result["components"]}


class TestAbsence:
    def test_a_county_with_no_budget_data_has_no_score(self):
        """It used to score 0.0, which graded it a C."""
        result = county_financial_health(
            total_allocated=None,
            total_spent=None,
            pending_bills=None,
            audit_status=None,
        )

        assert result is None

    def test_a_zero_budget_has_no_score_either(self):
        result = county_financial_health(
            total_allocated=0,
            total_spent=0,
            pending_bills=0,
            audit_status=None,
        )

        assert result is None

    def test_one_component_is_not_a_composite(self):
        """Exactly the failure being fixed: a "composite" of one input."""
        result = county_financial_health(
            total_allocated=10_000_000_000,
            total_spent=5_000_000_000,
            pending_bills=None,
            audit_status=None,
        )

        assert result is None

    def test_two_components_are_enough(self):
        result = county_financial_health(
            total_allocated=10_000_000_000,
            total_spent=5_000_000_000,
            pending_bills=None,
            audit_status="clean",
        )

        assert result is not None
        assert len(result["components"]) == _MIN_HEALTH_COMPONENTS

    def test_absence_is_not_zero(self):
        result = county_financial_health(
            total_allocated=None, total_spent=None,
            pending_bills=None, audit_status=None,
        )

        assert result is None
        assert result != 0


class TestGrade:
    def test_a_county_doing_everything_right_grades_a(self):
        result = health(
            total_spent=10_000_000_000,  # spent its budget
            own_source_actual=1_000_000_000,  # hit its revenue target
            audit_status="clean",
            pending_bills=0,
        )

        assert result["score"] == 100.0
        assert result["grade"] == "A"

    def test_equal_weighting_lets_strong_components_offset_a_disclaimer(self):
        """A property of the choice, recorded rather than hidden.

        Perfect absorption and revenue performance, against a disclaimer of
        opinion and a pending-bill burden of a whole budget, averages to 50.0
        and grades B-. Equal weights mean the worst audit outcome the
        Auditor-General can issue does not dominate — which is precisely why
        the components are published beside the score instead of only the
        letter. Any other weighting would assert a ranking of importance that
        nobody has published.
        """
        result = health(
            total_spent=10_000_000_000,
            own_source_actual=1_000_000_000,
            audit_status="disclaimer",
            pending_bills=10_000_000_000,
        )

        assert result["score"] == 50.0
        assert result["grade"] == "B-"
        assert [c["score"] for c in result["components"]] == [100.0, 100.0, 0.0, 0.0]

    def test_no_score_means_no_grade(self):
        """A county with no data must not be graded at all — it used to get C."""
        assert county_financial_health(
            total_allocated=None, total_spent=None,
            pending_bills=None, audit_status=None,
        ) is None
