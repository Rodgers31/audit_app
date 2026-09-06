"""Bootstrap must not write ``audits`` while a seed run is writing it.

Run 34008714644 (2026-09-06, the Sunday nightly) failed with::

    [STALE] bootstrap_reference_data: failed | source=fixture (bootstrap_failed)
      ERROR: (psycopg2.errors.QueryCanceled) canceling statement due to
             statement timeout
      CONTEXT: while updating tuple (0,6) in relation "audits"
      [SQL: UPDATE audits SET amount=%(amount)s WHERE audits.id = %(id)s]

``while updating tuple`` is a ROW-LOCK WAIT, not a slow statement — a
single-row update by primary key does not take 30 seconds on its own. The
"Bootstrap Reference Data" workflow job in that same run SUCCEEDED in 53
seconds, so the failing writer was somewhere else: ``main.py``'s
``_startup_sequence`` runs ``initialize_reference_data()`` on every production
web process start, and it collided with the ``audits`` domain writing 2,311
rows in the concurrent seed job.

The cost was not only the timeout. The seed job's "Check ingestion job results"
step counts every ingestion row in a 30-minute window, so a failure in the
PRODUCTION WEB PROCESS was reported as "1 domain(s) failed" by the nightly, and
``_startup_sequence`` returns without setting ``_app_ready`` — leaving the
service permanently not-ready on /health/ready.

So bootstrap defers while a seed run is in flight. It records NO ingestion job
when it does: it did not run, and a fixture-mode row for a run that never
happened would corrupt the very census the freshness gate reads.
"""

from datetime import datetime, timedelta, timezone

import pytest

import bootstrap
from models import IngestionJob, IngestionStatus


def _running(db_session, domain="audits", *, minutes_ago=0):
    started = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    db_session.add(
        IngestionJob(
            domain=domain,
            status=IngestionStatus.RUNNING,
            dry_run=False,
            started_at=started.replace(tzinfo=None),
        )
    )
    db_session.commit()


class TestItDefers:
    def test_a_live_seed_run_is_detected(self, db_session):
        _running(db_session)
        assert bootstrap._seed_run_in_flight(db_session) == "audits"

    def test_it_writes_nothing_while_a_seed_run_holds_the_table(
        self, db_session, monkeypatch
    ):
        """The whole point: no write, so no lock wait, so no timeout."""
        _running(db_session)
        monkeypatch.setattr(bootstrap, "SessionLocal", lambda: db_session)

        def _explode(*a, **k):  # any write path is a bug
            raise AssertionError("bootstrap wrote while a seed run was in flight")

        monkeypatch.setattr(bootstrap, "_ensure_country", _explode)
        bootstrap.initialize_reference_data()

    def test_a_deferred_run_records_no_ingestion_job(self, db_session, monkeypatch):
        """It did not run. A fixture-mode row here would poison the census."""
        _running(db_session)
        monkeypatch.setattr(bootstrap, "SessionLocal", lambda: db_session)
        monkeypatch.setattr(bootstrap, "_ensure_country", lambda *a, **k: None)

        bootstrap.initialize_reference_data()

        assert (
            db_session.query(IngestionJob)
            .filter(IngestionJob.domain == bootstrap.BOOTSTRAP_DOMAIN)
            .count()
            == 0
        )


class TestItDoesNotDeferForever:
    def test_a_stale_running_row_does_not_block(self, db_session):
        """A crashed run must not wedge every future boot."""
        _running(db_session, minutes_ago=bootstrap.DEFER_TO_SEED_WITHIN_MINUTES + 5)
        assert bootstrap._seed_run_in_flight(db_session) is None

    def test_an_idle_database_does_not_defer(self, db_session):
        assert bootstrap._seed_run_in_flight(db_session) is None

    @pytest.mark.parametrize(
        "status", [IngestionStatus.COMPLETED, IngestionStatus.FAILED]
    )
    def test_a_finished_run_does_not_block(self, db_session, status):
        db_session.add(
            IngestionJob(
                domain="audits",
                status=status,
                dry_run=False,
                started_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        db_session.commit()
        assert bootstrap._seed_run_in_flight(db_session) is None

    def test_bootstrap_does_not_defer_to_itself(self, db_session):
        """Otherwise two bootstrap boots deadlock each other into no-ops."""
        _running(db_session, domain=bootstrap.BOOTSTRAP_DOMAIN)
        assert bootstrap._seed_run_in_flight(db_session) is None

    def test_force_overrides_the_deferral(self, db_session, monkeypatch):
        """The weekly job must still be able to insist."""
        _running(db_session)
        monkeypatch.setattr(bootstrap, "SessionLocal", lambda: db_session)
        reached = []
        monkeypatch.setattr(
            bootstrap, "_ensure_country", lambda *a, **k: reached.append(True)
        )
        with pytest.raises(Exception):
            # It gets past the deferral and into the real work, which this
            # stub cannot complete — reaching it at all is the assertion.
            bootstrap.initialize_reference_data(force=True)
        assert reached
