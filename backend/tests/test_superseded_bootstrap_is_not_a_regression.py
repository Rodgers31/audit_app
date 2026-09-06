"""A fully-superseded bootstrap must not be reported as a CRITICAL failure.

``bootstrap_provenance`` can conclude ``fixture_superseded``: every fixture it
read is vestigial, verified THIS RUN against the database — nothing in any of
them can reach a reader. That is the terminal healthy state the supersession
machinery (18466fc, 2760328) was built to produce.

``check_ingestion_freshness`` cannot express it. ``source_mode`` is always
``"fixture"`` for bootstrap (bootstrap.py, the ``return`` of
``bootstrap_provenance``), so the all-fixture branch runs, and that branch
downgrades to WARN only when the reasons are a subset of
``DECLARED_NO_SOURCE_REASONS`` — which holds ``no_live_source`` alone.

So the WEAKER claim ("nobody ever built an extractor for this") warns, while
the STRONGER, evidence-backed one ("the extractor exists, it delivered, and
this file now reaches nobody") fails the nightly as CRITICAL. A domain in the
best state the design allows is indistinguishable from one that is broken.
"""

from datetime import datetime, timedelta, timezone

import pytest

from models import IngestionJob, IngestionStatus
from seeding.staleness import FAIL, OK, WARN, check_ingestion_freshness

DOMAIN = "bootstrap_reference_data"


def _record(db_session, reason, runs=3):
    now = datetime.now(timezone.utc)
    for i in range(runs):
        db_session.add(
            IngestionJob(
                domain=DOMAIN,
                status=IngestionStatus.COMPLETED,
                dry_run=False,
                started_at=(now - timedelta(days=i)).replace(tzinfo=None),
                finished_at=(now - timedelta(days=i)).replace(tzinfo=None),
                meta={
                    "source_mode": "fixture",
                    "source_fallback_reason": reason,
                    "source_fallback_detail": f"detail for {reason}",
                },
            )
        )
    db_session.commit()
    found = check_ingestion_freshness(db_session, domains=[DOMAIN])
    assert len(found) == 1
    return found[0]


class TestSupersededIsNotAFailure:
    def test_a_fully_superseded_bootstrap_does_not_fail_the_nightly(self, db_session):
        """The bug: the healthiest reachable state is reported CRITICAL."""
        finding = _record(db_session, "fixture_superseded")
        assert finding.level != FAIL, (
            "a fixture verified this run to reach no reader is the terminal "
            f"healthy state, but the gate reports {finding.level}: {finding.message}"
        )

    def test_the_evidence_is_in_the_message(self, db_session):
        """'reasons: fixture_stale' names no file — the detail already exists."""
        finding = _record(db_session, "fixture_stale")
        assert "detail for fixture_stale" in finding.message, (
            "bootstrap records source_fallback_detail naming the offending "
            f"file; the gate drops it: {finding.message}"
        )


class TestEveryBrokenStateStillFails:
    """The whole point: nothing else moves."""

    @pytest.mark.parametrize(
        "reason",
        ["fixture_stale", "fixture_missing", "fixture_current", "bootstrap_failed"],
    )
    def test_a_broken_bootstrap_is_still_critical(self, db_session, reason):
        assert _record(db_session, reason).level == FAIL

    def test_an_unrecorded_reason_is_still_critical(self, db_session):
        finding = _record(db_session, None)
        assert finding.level == FAIL

    def test_superseded_beside_a_real_failure_still_fails(self, db_session):
        """One good run must not launder a broken one beside it."""
        now = datetime.now(timezone.utc)
        for reason in ("fixture_superseded", "fixture_stale"):
            db_session.add(
                IngestionJob(
                    domain=DOMAIN,
                    status=IngestionStatus.COMPLETED,
                    dry_run=False,
                    started_at=now.replace(tzinfo=None),
                    finished_at=now.replace(tzinfo=None),
                    meta={
                        "source_mode": "fixture",
                        "source_fallback_reason": reason,
                    },
                )
            )
        db_session.commit()
        found = check_ingestion_freshness(db_session, domains=[DOMAIN])
        assert found[0].level == FAIL

    def test_superseded_is_never_reported_as_OK(self, db_session):
        """It still reads a git-tracked file. Visible, never silent."""
        assert _record(db_session, "fixture_superseded").level != OK
