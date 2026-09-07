"""A floor that cannot fail is worse than no floor — it reads as coverage.

Issue #137 P8. The nightly's "Validate seeded data" step asserts ~20 absolute
row-count floors. They are the "27 rows >= 20" shape the freshness gates were
built to replace, still running, one step above the gates that replaced it.

The counts below are not estimates. They are the literal output of the
2026-09-07 nightly, run 34076386280 (the first green seed in weeks):

    [OK] Budget Lines: 2136 rows (expected >= 400)
    [OK] Audit Records: 2338 rows (expected >= 20)
    [OK] Extractions (provenance middle link): 2325 rows (expected >= 1)

The headline test below takes the database four fifths of the way to empty and
asserts the nightly goes RED. Against unfixed code it does not: fourteen of the
twenty floors still print ``[OK]``, including every large fact table, and
``run_all`` has no count to compare. The floors are parsed out of
``.github/workflows/seed.yml`` rather than copied here, so the measurement
tracks the workflow instead of drifting from it.

New symbols are reached through the ``staleness`` module rather than imported
by name, deliberately: this file must COLLECT against the pre-fix code so the
red run is a statement about behaviour, not an ImportError.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from models import IngestionJob, IngestionStatus
from seeding import staleness
from seeding.staleness import FAIL, OK, WARN, check_ingestion_freshness, run_all

NOW = datetime(2026, 9, 8, 3, 0, tzinfo=timezone.utc)

SEED_WORKFLOW = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "seed.yml"
)

#: Every count the 2026-09-07 nightly printed, verbatim.
#: gh run view 34076386280 --log | grep 'expected >='
OBSERVED_2026_09_07 = {
    "Counties": 47,
    "National Entity": 2,
    "Fiscal Periods": 8,
    "Budget Lines": 2136,
    "Audit Records": 2338,
    "Extractions (provenance middle link)": 2325,
    "Publishable audits with extraction provenance": 2311,
    "Audits with audit_year": 2338,
    "Audits with query_type": 2246,
    "Population Records": 77,
    "National Population (entity_id=NULL)": 16,
    "GDP Records (entity-linked)": 7,
    "GDP Records (national, entity_id=NULL)": 66,
    "Economic Indicators": 82,
    "Inflation Rate records": 15,
    "Unemployment Rate records": 11,
    "Poverty Index Records": 8,
    "Loan Records": 110,
    "Debt Timeline": 13,
    "Fiscal Summaries": 29,
}

#: The tables whose volume grows with ingestion, as opposed to the structural
#: reference data (47 counties is 47 counties, and its floor is exact).
FACT_TABLES = [
    "Budget Lines",
    "Audit Records",
    "Extractions (provenance middle link)",
    "Publishable audits with extraction provenance",
    "Audits with audit_year",
    "Audits with query_type",
]

CATASTROPHIC_LOSS = 0.80  # four rows in five gone


def _parse_floors(text: str) -> dict:
    """The ``check(label, ..., floor)`` calls in the workflow, as data."""
    floors = {}
    for match in re.finditer(r"check\(\s*'([^']+)'", text):
        depth, i = 1, match.end()
        while i < len(text) and depth:
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
            i += 1
        args, depth, current = [], 0, []
        for ch in text[match.end() : i - 1]:
            if ch in "([":
                depth += 1
            elif ch in ")]":
                depth -= 1
            if ch == "," and depth == 0:
                args.append("".join(current))
                current = []
                continue
            current.append(ch)
        args.append("".join(current))
        # args[0] is the empty remainder of the label, [1] the query,
        # [2] the floor, [3] the optional is_warning kwarg.
        floors[match.group(1)] = int(args[2].strip())
    return floors


def _decimate(counts: dict, fraction: float = CATASTROPHIC_LOSS) -> dict:
    """What the database looks like after losing ``fraction`` of every row."""
    return {label: int(n * (1 - fraction)) for label, n in counts.items()}


def _census(session, counts: dict, when: datetime) -> None:
    session.add(
        IngestionJob(
            domain=staleness.ROW_CENSUS_DOMAIN,
            status=IngestionStatus.COMPLETED,
            started_at=when.replace(tzinfo=None),
            finished_at=when.replace(tzinfo=None),
            items_processed=len(counts),
            meta={"row_counts": dict(counts)},
        )
    )
    session.flush()


def _by_label(findings, label):
    return next(f for f in findings if f.label == label)


def _floors_breached(counts: dict) -> set:
    """Which of the shipping floors this database would actually trip."""
    floors = _parse_floors(SEED_WORKFLOW.read_text())
    return {label for label, n in counts.items() if n < floors[label]}


class TestTheNightlyMustNoticeACatastrophicLoss:
    """THE test. Red against unfixed code, and red for the right reason.

    Part 1 is the defect, measured: with four fifths of every row gone, the
    floors that ship today still report [OK] on fourteen of twenty tables and
    on EVERY large fact table. Part 1 passes before and after the fix — it is
    a statement about the floors, and it is what makes part 2 necessary.

    Part 2 is the fix: something in the nightly must fail this database.
    Against unfixed code it raises, because there is nothing that can.
    """

    def test_a_database_that_lost_four_rows_in_five_fails_the_nightly(
        self, db_session
    ):
        after = _decimate(OBSERVED_2026_09_07)

        # ── Part 1: what the shipping floors can see ──────────────────
        breached = _floors_breached(after)
        assert len(breached) == 6, sorted(breached)
        assert len(OBSERVED_2026_09_07) - len(breached) == 14
        for label in FACT_TABLES:
            assert label not in breached, (
                f"{label} lost 80% of its rows and its floor still passed — "
                f"that is the defect this test exists to pin"
            )

        # ── Part 2: therefore the run must be failed by something else ──
        _census(db_session, OBSERVED_2026_09_07, NOW - timedelta(days=1))
        failed = {
            f.label
            for f in run_all(db_session, now=NOW, counts=after)
            if f.level == FAIL
        }
        for label in FACT_TABLES:
            assert label in failed, (
                f"nothing in the nightly noticed {label} losing 80% of its rows"
            )


class TestTheFloorsCannotSeeIt:
    """The measurement, broken out. These pass unfixed — that is the point.

    If they ever start failing, the floors have become capable of detecting a
    catastrophic loss and this gate should be re-argued rather than kept.
    """

    def test_the_workflow_floors_parse(self):
        floors = _parse_floors(SEED_WORKFLOW.read_text())
        assert set(floors) == set(OBSERVED_2026_09_07), (
            "the workflow's floors and the counts the nightly printed have "
            "diverged; re-read a run log before trusting this file"
        )
        assert len(floors) == 20

    def test_every_large_fact_table_still_reports_OK(self):
        """The floors are blindest exactly where the data is biggest."""
        assert not set(FACT_TABLES) & _floors_breached(
            _decimate(OBSERVED_2026_09_07)
        )

    def test_the_headroom_is_the_reason(self):
        """Extractions could lose 2,324 of 2,325 rows and print [OK]."""
        floors = _parse_floors(SEED_WORKFLOW.read_text())
        headroom = {
            lbl: 1 - floors[lbl] / n for lbl, n in OBSERVED_2026_09_07.items()
        }
        assert headroom["Extractions (provenance middle link)"] > 0.999
        assert headroom["Budget Lines"] > 0.81
        assert headroom["Audit Records"] > 0.99

    def test_the_floors_that_do_work_are_the_structural_ones(self):
        """Kept, not deleted: 47 counties is 47 counties, and 0 rows is 0 rows.

        The absolute floors remain the only thing that can judge a database
        with no baseline at all — a fresh environment, or a restore.
        """
        breached = _floors_breached(_decimate(OBSERVED_2026_09_07))
        assert "Counties" in breached
        assert "National Entity" in breached


class TestTheGateFires:
    """Positive controls: the condition the floors miss, gate says FAIL."""

    def test_the_message_names_the_numbers_and_the_baseline_date(self, db_session):
        _census(db_session, {"Budget Lines": 2136}, NOW - timedelta(days=2))

        f = _by_label(
            staleness.check_row_count_drop(
                db_session, {"Budget Lines": 427}, now=NOW
            ),
            "Budget Lines",
        )

        assert f.level == FAIL
        # A gate that withholds must say why in a way a reader can act on.
        assert "427" in f.message
        assert "2136" in f.message
        assert "2026-09-06" in f.message
        assert "80%" in f.message

    def test_a_slow_bleed_fails_even_though_no_single_night_does(self, db_session):
        """Why the baseline is the window MAXIMUM, not last night.

        Five percent a night clears a night-over-night comparison every
        single time and still costs a third of the table inside a week.
        """
        counts, nightly = 2000, []
        for days_ago in range(staleness.ROW_CENSUS_WINDOW_DAYS - 1, 0, -1):
            _census(
                db_session, {"Budget Lines": counts}, NOW - timedelta(days=days_ago)
            )
            nightly.append(counts)
            counts = int(counts * 0.95)

        # Night over night this is a 5% step every time — inside tolerance,
        # so a "compare with last night" gate never fires on any of them.
        for previous, current in zip(nightly, nightly[1:] + [counts]):
            assert current >= previous * (1 - staleness.ROW_DROP_TOLERANCE)
        assert counts < 2000 * 0.75  # …and a quarter of the table is gone

        f = _by_label(
            staleness.check_row_count_drop(
                db_session, {"Budget Lines": counts}, now=NOW
            ),
            "Budget Lines",
        )
        assert f.level == FAIL
        assert "2000" in f.message  # measured against the high-water mark

    def test_a_small_drop_inside_tolerance_passes(self, db_session):
        """It must be able to say OK, or nobody will believe the FAILs.

        pending_bills rewrites 48 of the 110 loan rows every night; a short
        BROP table is normal churn, not a regression.
        """
        _census(db_session, {"Loan Records": 110}, NOW - timedelta(days=1))

        f = _by_label(
            staleness.check_row_count_drop(
                db_session, {"Loan Records": 105}, now=NOW
            ),
            "Loan Records",
        )
        assert f.level == OK

    def test_one_row_off_a_tiny_table_is_not_a_regression(self, db_session):
        """7 rows losing 1 is 14% — percentage arithmetic, not a defect."""
        _census(db_session, {"GDP Records (entity-linked)": 7}, NOW - timedelta(days=1))

        f = _by_label(
            staleness.check_row_count_drop(
                db_session, {"GDP Records (entity-linked)": 6}, now=NOW
            ),
            "GDP Records (entity-linked)",
        )
        assert f.level == OK

    def test_but_two_rows_off_the_same_tiny_table_is(self, db_session):
        _census(db_session, {"GDP Records (entity-linked)": 7}, NOW - timedelta(days=1))

        f = _by_label(
            staleness.check_row_count_drop(
                db_session, {"GDP Records (entity-linked)": 5}, now=NOW
            ),
            "GDP Records (entity-linked)",
        )
        assert f.level == FAIL


class TestItCannotReportHealthyWithoutMeasuring:
    """The repo's signature defect: a check that is green because it is blind."""

    def test_no_baseline_is_a_WARN_never_an_OK(self, db_session):
        findings = staleness.check_row_count_drop(
            db_session, {"Budget Lines": 2136}, now=NOW
        )

        assert [f.level for f in findings] == [WARN]
        assert "no baseline" in findings[0].message

    def test_a_baseline_older_than_the_window_does_not_count(self, db_session):
        _census(
            db_session,
            {"Budget Lines": 2136},
            NOW - timedelta(days=staleness.ROW_CENSUS_WINDOW_DAYS + 1),
        )

        findings = staleness.check_row_count_drop(
            db_session, {"Budget Lines": 10}, now=NOW
        )

        # Not OK. It does not know, and it says so.
        assert all(f.level != OK for f in findings)

    def test_a_new_count_says_so_rather_than_passing(self, db_session):
        _census(db_session, {"Budget Lines": 2136}, NOW - timedelta(days=1))

        f = _by_label(
            staleness.check_row_count_drop(
                db_session, {"Budget Lines": 2136, "Debt Instruments": 56}, now=NOW
            ),
            "Debt Instruments",
        )
        assert f.level == WARN
        assert "no baseline" in f.message

    def test_a_count_that_left_the_workflow_is_reported(self, db_session):
        """Narrowing the watch list silently is the defect in miniature."""
        _census(
            db_session,
            {"Budget Lines": 2136, "Audit Records": 2338},
            NOW - timedelta(days=1),
        )

        findings = staleness.check_row_count_drop(
            db_session, {"Budget Lines": 2136}, now=NOW
        )

        census = _by_label(findings, "Row census")
        assert census.level == WARN
        assert "Audit Records" in census.message

    def test_recording_happens_after_checking_not_before(self, db_session):
        """A baseline that includes tonight is a baseline tonight cannot fail.

        This is the fail-open shape the gate replaces, and the reason
        check_and_record_row_census exists instead of two loose functions.
        """
        first = staleness.check_and_record_row_census(
            db_session, {"Budget Lines": 2136}, now=NOW - timedelta(days=1)
        )
        assert [f.level for f in first] == [WARN]  # nothing known yet

        second = staleness.check_and_record_row_census(
            db_session, {"Budget Lines": 200}, now=NOW
        )

        f = _by_label(second, "Budget Lines")
        assert f.level == FAIL, (
            "the run's own census masked its own collapse — recording ran "
            "before checking"
        )

    @pytest.mark.parametrize("junk", [None, [], "row_counts", 7, {"row_counts": []}])
    def test_a_malformed_census_row_does_not_take_out_the_step(
        self, db_session, junk
    ):
        """``meta`` is JSONB and can hold anything. A raise in the read loop
        would kill the whole validate step, taking the floors with it."""
        db_session.add(
            IngestionJob(
                domain=staleness.ROW_CENSUS_DOMAIN,
                status=IngestionStatus.COMPLETED,
                started_at=(NOW - timedelta(days=1)).replace(tzinfo=None),
                meta=junk,
            )
        )
        db_session.flush()

        findings = staleness.check_row_count_drop(
            db_session, {"Budget Lines": 2136}, now=NOW
        )

        # Unusable, so: not OK, and not a crash.
        assert [f.level for f in findings] == [WARN]

    def test_an_unwritable_census_fails_loudly(self, db_session, monkeypatch):
        """A census that stops being written freezes the baseline forever."""
        monkeypatch.setattr(
            type(db_session),
            "commit",
            lambda self, *a, **kw: (_ for _ in ()).throw(RuntimeError("disk full")),
        )

        findings = staleness.record_row_census(
            db_session, {"Budget Lines": 2136}, now=NOW
        )

        assert [f.level for f in findings] == [FAIL]
        assert "could NOT be recorded" in findings[0].message

    def test_run_all_without_counts_runs_no_census(self, db_session):
        """The old two-gate call site must keep working, and must not claim
        a third gate ran when it did not."""
        findings = run_all(db_session, now=NOW)
        assert not [f for f in findings if f.label == "Row census"]


class TestItDoesNotPolluteTheOtherGates:
    def test_the_census_is_not_mistaken_for_a_seeding_domain(self, db_session):
        """It has no publisher; watching it posts a permanent false WARN."""
        _census(db_session, {"Budget Lines": 2136}, NOW - timedelta(days=1))

        findings = check_ingestion_freshness(db_session, now=NOW)

        assert not [
            f for f in findings if staleness.ROW_CENSUS_DOMAIN in f.label
        ]


class TestTheKnobsAreDeliberate:
    """Each constant is a decision. Pin them so widening one is a change."""

    @pytest.mark.parametrize(
        "name,value",
        [
            ("ROW_DROP_TOLERANCE", 0.10),
            ("ROW_DROP_MIN_ABSOLUTE", 2),
            ("ROW_CENSUS_WINDOW_DAYS", 7),
        ],
    )
    def test_constant(self, name, value):
        assert getattr(staleness, name) == value

    def test_the_tolerance_is_far_tighter_than_the_floors_it_supplements(self):
        floors = _parse_floors(SEED_WORKFLOW.read_text())
        worst = max(1 - floors[lbl] / n for lbl, n in OBSERVED_2026_09_07.items())
        assert staleness.ROW_DROP_TOLERANCE < worst / 9
