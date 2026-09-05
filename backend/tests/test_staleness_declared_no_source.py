"""A gate that is red every night stops being read.

The nightly's "Validate seeded data" step exited 1 on five staleness findings.
Two of them — learning_hub and stalled_projects — are fixture-backed BY DESIGN:
they call mark_fixture(reason="no_live_source") because no extractor has ever
been built for them. The gate could not tell that apart from national_budget's
live_fetch_failed, so it failed the run for a known, accepted gap every single
night, and a genuine regression would have landed in an already-red step.

Downgrading them to WARN keeps the gap reported and keeps every real failure
failing. The distinction is the reason the domain DECLARED, never the domain
name — and an unrecorded reason stays a FAIL, because "we don't know why this
fell back" is the exact state this module exists to catch.
"""

import pytest

from seeding.staleness import DECLARED_NO_SOURCE_REASONS, FAIL, WARN


class _Job:
    def __init__(self, reason=None, mode="fixture"):
        self.meta = {"source_mode": mode}
        if reason:
            self.meta["source_fallback_reason"] = reason


def _classify(reasons):
    """Mirror the rule the module applies to an all-fixture domain."""
    return WARN if (reasons and set(reasons) <= DECLARED_NO_SOURCE_REASONS) else FAIL


class TestClassification:
    def test_a_declared_absence_warns_rather_than_fails(self):
        assert _classify({"no_live_source"}) == WARN

    @pytest.mark.parametrize(
        "reason",
        ["live_fetch_failed", "parser_returned_nothing", "no_document_extracted",
         "live_pdf_fetch_disabled", "cbk_bulletin_unavailable"],
    )
    def test_every_failure_reason_still_fails(self, reason):
        assert _classify({reason}) == FAIL

    def test_an_unrecorded_reason_still_fails(self):
        """The bootstrap_reference_data case: 26 fixture runs, reason unknown."""
        assert _classify(set()) == FAIL

    def test_a_mixed_domain_fails(self):
        """One declared reason must not launder a real failure beside it."""
        assert _classify({"no_live_source", "live_fetch_failed"}) == FAIL

    def test_the_exemption_list_is_deliberately_small(self):
        """Widening it is a decision, not a convenience — pin it."""
        assert set(DECLARED_NO_SOURCE_REASONS) == {"no_live_source"}


class TestRealFindings:
    """The five findings from the 2026-09-04 run, classified."""

    LIVE_RUN = {
        "bootstrap_reference_data": set(),
        "counties_budget": {"parser_returned_nothing"},
        "learning_hub": {"no_live_source"},
        "national_budget": {"live_fetch_failed"},
        "stalled_projects": {"no_live_source"},
    }

    def test_only_the_two_by_design_domains_are_downgraded(self):
        got = {d: _classify(r) for d, r in self.LIVE_RUN.items()}
        assert got == {
            "bootstrap_reference_data": FAIL,
            "counties_budget": FAIL,
            "learning_hub": WARN,
            "national_budget": FAIL,
            "stalled_projects": WARN,
        }

    def test_the_gate_still_fails_the_run(self):
        """This does NOT turn the nightly green — three real failures remain."""
        levels = [_classify(r) for r in self.LIVE_RUN.values()]
        assert levels.count(FAIL) == 3


class TestAgainstTheRealClassifier:
    """The tests above mirror the rule; this one runs it.

    A test that reimplements the logic it checks agrees with itself by
    construction. This drives check_ingestion_freshness with fabricated
    ingestion jobs so the shipped branch is what gets exercised.
    """

    @staticmethod
    def _session(rows):
        from datetime import datetime, timezone

        class _Q:
            def __init__(self, rows):
                self._rows = rows

            def filter(self, *a, **k):
                return self

            def order_by(self, *a, **k):
                return self

            def all(self):
                return self._rows

        class _Job:
            def __init__(self, domain, reason):
                self.domain = domain
                self.started_at = datetime.now(timezone.utc)
                self.meta = {"source_mode": "fixture"}
                if reason:
                    self.meta["source_fallback_reason"] = reason

        class _Session:
            def query(self, *a, **k):
                return _Q([_Job(d, r) for d, r in rows])

        return _Session()

    def _levels(self, rows):
        from seeding.staleness import check_ingestion_freshness

        findings = check_ingestion_freshness(
            self._session(rows), domains=[d for d, _ in rows]
        )
        return {f.label.split()[0]: f.level for f in findings}

    def test_declared_no_source_is_warn_in_the_shipped_code(self):
        levels = self._levels([("stalled_projects", "no_live_source")])
        assert levels.get("stalled_projects") == WARN

    def test_a_failed_fetch_is_still_fail_in_the_shipped_code(self):
        levels = self._levels([("national_budget", "live_fetch_failed")])
        assert levels.get("national_budget") == FAIL

    def test_an_unrecorded_reason_is_still_fail_in_the_shipped_code(self):
        levels = self._levels([("bootstrap_reference_data", None)])
        assert levels.get("bootstrap_reference_data") == FAIL
