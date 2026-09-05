"""Bootstrap must say WHY it served a fixture, not just that it did.

The nightly's staleness gate reported `bootstrap_reference_data ... (reasons:
unrecorded)` for 26 consecutive runs. It could see the domain had never
reached a publisher, but not why — which is the single thing needed to act on
it, and the reason this was the hardest of the five findings to diagnose.

The reason must also stay a FAIL. Every fixture here DECLARES a live domain
meant to supersede it (`audits`, `counties_budget`), so an all-fixture run is
a live path that is not working — not a by-design gap like learning_hub's, and
it must not be excused as one.
"""

import bootstrap
import pytest
from seeding.staleness import DECLARED_NO_SOURCE_REASONS


class TestReasonIsRecorded:
    def test_the_live_run_names_a_reason(self):
        p = bootstrap.bootstrap_provenance()
        assert p.get("source_fallback_reason"), "the gate reads this exact key"
        assert p.get("source_fallback_detail")

    def test_the_reason_is_not_the_empty_string(self):
        """`reasons: unrecorded` came from a falsy value, not a missing key."""
        p = bootstrap.bootstrap_provenance()
        assert p["source_fallback_reason"].strip()

    def test_stale_fixtures_are_reported_as_stale(self):
        """All three shipped fixtures are >180d old today."""
        p = bootstrap.bootstrap_provenance()
        assert p["is_stale"] is True
        assert p["source_fallback_reason"] == "fixture_stale"

    def test_the_detail_names_the_domain_that_should_supersede_it(self):
        """Enough to act on without opening the code."""
        p = bootstrap.bootstrap_provenance()
        assert "supersede" in p["source_fallback_detail"]
        assert any(
            d in p["source_fallback_detail"] for d in ("audits", "counties_budget")
        )


class TestItStillFails:
    def test_the_reason_is_not_excused_as_a_by_design_gap(self):
        """The distinction that keeps this red.

        `no_live_source` downgrades to WARN. None of bootstrap's reasons may
        be in that set, because every fixture here has a live domain behind it.
        """
        p = bootstrap.bootstrap_provenance()
        assert p["source_fallback_reason"] not in DECLARED_NO_SOURCE_REASONS

    @pytest.mark.parametrize(
        "reason", ["fixture_stale", "fixture_missing", "fixture_current", "bootstrap_failed"]
    )
    def test_no_bootstrap_reason_is_ever_exempt(self, reason):
        assert reason not in DECLARED_NO_SOURCE_REASONS


class TestGateIntegration:
    def test_the_gate_reports_the_reason_instead_of_unrecorded(self):
        from datetime import datetime, timezone

        from seeding.staleness import FAIL, check_ingestion_freshness

        prov = bootstrap.bootstrap_provenance()

        class _Job:
            domain = "bootstrap_reference_data"
            started_at = datetime.now(timezone.utc)
            meta = prov

        class _Q:
            def filter(self, *a, **k):
                return self

            def order_by(self, *a, **k):
                return self

            def all(self):
                return [_Job()]

        class _S:
            def query(self, *a, **k):
                return _Q()

        finding = check_ingestion_freshness(
            _S(), domains=["bootstrap_reference_data"]
        )[0]
        assert finding.level == FAIL
        assert "unrecorded" not in finding.message
        assert prov["source_fallback_reason"] in finding.message
