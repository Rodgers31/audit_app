"""Supersession is a fact about NOW, not about the whole 14-day window.

#173 taught ``bootstrap_provenance`` to conclude ``fixture_superseded`` and
taught the gate to downgrade it to WARN. Against production it still FAILS,
because the downgrade is decided on the UNION of every reason in the window::

    reasons = {every source_fallback_reason in the last MAX_DAYS_SINCE_LIVE}
    superseded = reasons <= SUPERSEDED_REASONS

Production's window (queried 2026-09-06) held 57 bootstrap rows::

    fixture_stale       x27     bootstrap_failed    x1
    (no reason)         x26     fixture_superseded  x1   <- newest, 18:10:53

so the union is ``{fixture_stale, fixture_missing, bootstrap_failed,
fixture_superseded}``, which is not a subset of ``{fixture_superseded}``, and
the gate reports CRITICAL while its own message — built from the NEWEST row —
says "all 3 fixture(s) superseded by live data". The verdict and the evidence
in the same line disagree.

Every bootstrap run writes ONE job row carrying a verdict already aggregated
across all three fixtures (bootstrap.py ``bootstrap_provenance`` /
``initialize_reference_data``), so the newest row is a complete, current
answer. Judging it against fourteen days of history asks a different question:
"was bootstrap ever unhealthy this fortnight", to which the answer is
permanently yes. The gate could not go green for 14 days after the fix that
was supposed to turn it green — and one bad night re-arms it for another 14.

This is NOT the same question as ``declared`` (DECLARED_NO_SOURCE_REASONS),
which stays union-based on purpose (test_staleness_declared_no_source.py):
"has an extractor ever been built" is a stable property of the codebase, so a
run that disagrees is genuinely suspicious. "Is every fixture vestigial" is a
property of the live database that is *supposed* to flip from false to true.
"""

from datetime import datetime, timedelta, timezone

from models import IngestionJob, IngestionStatus
from seeding.staleness import FAIL, OK, WARN, check_ingestion_freshness

DOMAIN = "bootstrap_reference_data"


def _row(session, reason, *, minutes_ago, status=IngestionStatus.COMPLETED):
    when = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).replace(
        tzinfo=None
    )
    session.add(
        IngestionJob(
            domain=DOMAIN,
            status=status,
            dry_run=False,
            started_at=when,
            finished_at=when,
            meta={
                "source_mode": "fixture",
                "source_fallback_reason": reason,
                "source_fallback_detail": f"detail for {reason}",
            },
        )
    )


def _finding(session):
    session.commit()
    found = check_ingestion_freshness(session, domains=[DOMAIN])
    assert len(found) == 1
    return found[0]


class TestProductionHistoryDoesNotVetoTheCurrentState:
    def test_the_shape_production_was_actually_in(self, db_session):
        """Reproduces the 14-day window queried on 2026-09-06."""
        for i in range(27):
            _row(db_session, "fixture_stale", minutes_ago=60 + i * 60)
        for i in range(2):
            _row(db_session, "fixture_missing", minutes_ago=2000 + i * 60)
        _row(
            db_session,
            "bootstrap_failed",
            minutes_ago=900,
            status=IngestionStatus.FAILED,
        )
        _row(db_session, "fixture_superseded", minutes_ago=1)

        finding = _finding(db_session)
        assert finding.level != FAIL, (
            "the newest run verified every fixture vestigial against the "
            "database; fourteen days of pre-fix history must not veto it — "
            f"got {finding.level}: {finding.message}"
        )

    def test_it_is_still_a_warning_never_ok(self, db_session):
        """A git-tracked file is still being read. Visible, never silent."""
        _row(db_session, "fixture_stale", minutes_ago=600)
        _row(db_session, "fixture_superseded", minutes_ago=1)
        assert _finding(db_session).level == WARN

    def test_the_message_names_what_the_verdict_was_based_on(self, db_session):
        """Verdict and evidence must come from the same run."""
        _row(db_session, "fixture_stale", minutes_ago=600)
        _row(db_session, "fixture_superseded", minutes_ago=1)
        message = _finding(db_session).message
        assert "detail for fixture_superseded" in message, message
        assert "detail for fixture_stale" not in message, message


class TestHistoryCannotLaunderAPresentBreak:
    """The inverse must stay true, or this is just a relaxed gate."""

    def test_a_broken_newest_run_still_fails(self, db_session):
        """Yesterday's success does not excuse tonight's failure."""
        _row(db_session, "fixture_superseded", minutes_ago=600)
        _row(
            db_session,
            "bootstrap_failed",
            minutes_ago=1,
            status=IngestionStatus.FAILED,
        )
        finding = _finding(db_session)
        assert finding.level == FAIL, finding.message

    def test_a_stale_newest_run_still_fails(self, db_session):
        _row(db_session, "fixture_superseded", minutes_ago=600)
        _row(db_session, "fixture_stale", minutes_ago=1)
        assert _finding(db_session).level == FAIL

    def test_runs_at_the_same_instant_must_agree(self, db_session):
        """Concurrent writers: if the newest moment is not unanimous, fail.

        Guards test_superseded_bootstrap_is_not_a_regression's
        ``test_superseded_beside_a_real_failure_still_fails``.
        """
        _row(db_session, "fixture_superseded", minutes_ago=1)
        _row(db_session, "fixture_stale", minutes_ago=1)
        assert _finding(db_session).level == FAIL

    def test_an_unrecorded_newest_reason_does_not_inherit_supersession(
        self, db_session
    ):
        """A run that recorded no reason is 'we don't know', not 'healthy'."""
        _row(db_session, "fixture_superseded", minutes_ago=600)
        when = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(tzinfo=None)
        db_session.add(
            IngestionJob(
                domain=DOMAIN,
                status=IngestionStatus.COMPLETED,
                dry_run=False,
                started_at=when,
                finished_at=when,
                meta={"source_mode": "fixture"},
            )
        )
        finding = _finding(db_session)
        assert finding.level != OK, finding.message
