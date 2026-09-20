"""A nightly that refreshed nothing must not exit 0.

WHAT HAPPENED
-------------
Run 35415601792, 2026-09-19. ``audits`` processed 0 rows — all five OAG URLs
returned HTML, not PDFs. ``counties_budget`` fell back to its fixture after a
COB 403. ``national_budget`` too. The "Check ingestion job results" step
printed::

    [STALE] national_budget: completed_with_errors | created=0 updated=0 ...
    [STALE] counties_budget: completed_with_errors | created=0 updated=0 ...
    [STALE] audits: completed_with_errors | created=0 updated=0 processed=0 ...
      ERROR: fetch failed for https://www.oagkenya.go.ke/...
    All domains completed successfully.

and exited 0. It counted only ``status == 'failed'``.

The validate job ran minutes later and printed::

    [OK] audits ingestion: reached the publisher in 13/22 recent run(s)

Also true, also useless here: that gate judges a 14-day WINDOW, so a single
hollow night is drowned by the fortnight around it. Neither check was asking
"did anything arrive tonight?".

The two log lines the expensive domains emit on a healthy night —
"Parsed COB county BIRR PDF (188 records, …)" and "publishable backfill:
2311 published …" — are absent from that run's log entirely, which is how
the hollow pass was confirmed rather than inferred.

WHAT THESE TESTS DO
-------------------
They pull the real ``Check ingestion job results`` step out of
``.github/workflows/seed.yml`` and RUN it, against a SQLite database holding
the ``ingestion_jobs`` rows of the night in question. Following #208 and
#220: the defect lives in the workflow, so the workflow step is what gets
executed, not asserted about as text.

*Seen to fail against the pre-fix step: the Sep 19 job rows produce exit 0
and "All domains completed successfully."*
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
WORKFLOW = REPO / ".github" / "workflows" / "seed.yml"
STEP_NAME = "Check ingestion job results"


def _step_script(name: str = STEP_NAME) -> str:
    """The step's own ``run:`` block, read from the workflow."""
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in (doc.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            if step.get("name") == name:
                return step["run"]
    raise AssertionError(
        f"step {name!r} not found in {WORKFLOW} — this test would otherwise "
        "pass vacuously against a workflow that no longer has the gate"
    )


SCRIPT = _step_script()
assert "${{" not in SCRIPT, (
    "the step now carries a GitHub expression; it is substituted before the "
    "shell sees it, so running the raw text here would test the wrong string"
)


# ── The Sep 19 run, and a healthy one, as ingestion_jobs rows ─────────────
#
# Copied from the two runs' own "--- Ingestion Job Results ---" tables, so
# the fixture is the observed state rather than a plausible one.

HOLLOW_NIGHT = [
    # domain, status, created, updated, processed, mode, reason
    ("stalled_projects", "completed_with_errors", 25, 0, 25, "fixture", "no_live_source"),
    ("revenue_by_source", "completed", 0, 0, 49, "live", None),
    ("population", "completed", 0, 95, 110, "live", None),
    ("pending_bills", "completed", 0, 48, 48, "live", None),
    ("national_gdp", "completed", 0, 0, 74, "live", None),
    ("national_debt", "completed", 0, 43, 47, "live", None),
    ("national_budget", "completed_with_errors", 0, 0, 20, "fixture", "parser_returned_nothing"),
    ("learning_hub", "completed_with_errors", 0, 0, 10, "fixture", "no_live_source"),
    ("imf_weo", "completed", 188, 0, 188, "live", None),
    ("fiscal_summary", "completed", 0, 29, 29, "live", None),
    ("economic_indicators", "completed", 0, 6, 76, "live", None),
    ("debt_timeline", "completed", 0, 13, 13, "live", None),
    ("county_officials", "completed", 0, 0, 47, "live", None),
    ("counties_budget", "completed_with_errors", 0, 0, 1880, "fixture", "parser_returned_nothing"),
    ("audits", "completed_with_errors", 0, 0, 0, "fixture", "no_document_extracted"),
]

#: Run 35048000013, 2026-09-16 — every domain live except the two that have
#: no publisher. The gate must stay green on this, or it is useless.
HEALTHY_NIGHT = [
    ("stalled_projects", "completed_with_errors", 25, 0, 25, "fixture", "no_live_source"),
    ("revenue_by_source", "completed", 0, 0, 49, "live", None),
    ("population", "completed", 0, 95, 110, "live", None),
    ("pending_bills", "completed", 0, 48, 48, "live", None),
    ("national_gdp", "completed", 0, 0, 74, "live", None),
    ("national_debt", "completed", 0, 43, 47, "live", None),
    ("national_budget", "completed", 0, 0, 9, "live", None),
    ("learning_hub", "completed_with_errors", 0, 0, 10, "fixture", "no_live_source"),
    ("imf_weo", "completed", 188, 0, 188, "live", None),
    ("fiscal_summary", "completed", 0, 29, 29, "live", None),
    ("economic_indicators", "completed", 0, 0, 76, "live", None),
    ("debt_timeline", "completed", 0, 13, 13, "live", None),
    ("county_officials", "completed", 0, 0, 47, "live", None),
    ("counties_budget", "completed", 0, 9, 188, "live", None),
    ("audits", "completed", 0, 1, 2311, "live", None),
]


def _write_db(tmp_path: Path, rows, extra=()) -> str:
    """Build a SQLite database holding these ingestion_jobs rows."""
    db_path = tmp_path / "seed_check.sqlite"
    url = f"sqlite:///{db_path}"

    sys.path.insert(0, str(BACKEND))
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import models

    engine = create_engine(url)
    models.Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    started = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=2)

    with Session() as session:
        for domain, status, created, updated, processed, mode, reason in (
            list(rows) + list(extra)
        ):
            meta = {"source_mode": mode} if mode is not None else {}
            if reason:
                meta["source_fallback_reason"] = reason
            session.add(
                models.IngestionJob(
                    domain=domain,
                    status=models.IngestionStatus(status),
                    dry_run=False,
                    started_at=started,
                    finished_at=started + timedelta(seconds=30),
                    items_processed=processed,
                    items_created=created,
                    items_updated=updated,
                    errors=[],
                    meta=meta,
                )
            )
        session.commit()
    engine.dispose()
    return url


def _run_step(db_url: str) -> subprocess.CompletedProcess:
    """Execute the workflow step for real, from the repo root as Actions does."""
    env = dict(os.environ)
    env["DATABASE_URL"] = db_url
    env.pop("DB_USER", None)
    env.pop("DB_HOST", None)
    env["PYTHONPATH"] = str(BACKEND)
    # The step invokes bare `python`, which Actions puts on PATH via
    # setup-python. Locally that is the interpreter running pytest, so the
    # step runs against the same dependencies the suite does.
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    result = subprocess.run(
        ["bash", "-e", "-c", SCRIPT],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    # A step that never ran cannot be evidence about what it decides. This
    # has teeth: the first run of these tests exited non-zero with
    # "python: command not found", which the hollow-night assertion
    # (returncode != 0) would have read as the gate working.
    combined = result.stdout + result.stderr
    assert "--- Ingestion Job Results ---" in combined, (
        "the step did not get as far as reading the jobs table, so its exit "
        f"code says nothing about the gate:\n{combined}"
    )
    return result


@pytest.fixture(scope="module", autouse=True)
def _require_python():
    if not (BACKEND / "database.py").exists():  # pragma: no cover - sanity
        pytest.skip("backend not present")


class TestTheStepItself:
    def test_the_hollow_night_fails_the_run(self, tmp_path):
        """The whole point. Seen to fail before the fix: exit 0."""
        result = _run_step(_write_db(tmp_path, HOLLOW_NIGHT))
        out = result.stdout + result.stderr
        assert result.returncode != 0, (
            "a run that ingested nothing for audits, counties_budget and "
            f"national_budget reported success.\n{out}"
        )
        assert "All domains completed successfully." not in out
        for domain in ("audits", "counties_budget", "national_budget"):
            assert f"[FAIL] {domain} this run" in out, (
                f"{domain} served a fixture and was not named.\n{out}"
            )

    def test_the_healthy_night_still_passes(self, tmp_path):
        """A gate that fires every night gets muted along with everything
        beside it. learning_hub and stalled_projects have no publisher and
        must not turn the nightly red."""
        result = _run_step(_write_db(tmp_path, HEALTHY_NIGHT))
        out = result.stdout + result.stderr
        assert result.returncode == 0, (
            f"a fully live night was reported as a failure.\n{out}"
        )
        assert "All domains completed successfully." in out
        assert "[FAIL]" not in out

    def test_a_failed_domain_still_fails(self, tmp_path):
        """The pre-existing behaviour is not lost."""
        rows = [r for r in HEALTHY_NIGHT if r[0] != "audits"]
        rows.append(("audits", "failed", 0, 0, 0, None, None))
        result = _run_step(_write_db(tmp_path, rows))
        out = result.stdout + result.stderr
        assert result.returncode != 0
        assert "1 domain(s) failed!" in out

    def test_a_failed_domain_is_not_counted_twice(self, tmp_path):
        """A failed domain records no source_mode. It must be reported once,
        under its status, not also as 'recorded no source_mode'."""
        rows = [r for r in HEALTHY_NIGHT if r[0] != "audits"]
        rows.append(("audits", "failed", 0, 0, 0, None, None))
        result = _run_step(_write_db(tmp_path, rows))
        out = result.stdout + result.stderr
        # Positive control: this assertion is about an ABSENCE, so it would
        # also hold if the step printed nothing at all.
        assert "[FAIL] audits:" in out, f"the failed domain was not listed\n{out}"
        assert "[FAIL] audits this run" not in out

    def test_bootstrap_does_not_redden_the_sunday_run(self, tmp_path):
        """bootstrap_reference_data reads git-tracked files by definition and
        always records source_mode=fixture. Its own vocabulary is judged by
        the window gate; failing the Sunday nightly on it would be wrong."""
        result = _run_step(
            _write_db(
                tmp_path,
                HEALTHY_NIGHT,
                extra=[
                    (
                        "bootstrap_reference_data",
                        "completed",
                        0,
                        0,
                        47,
                        "fixture",
                        "fixture_current",
                    )
                ],
            )
        )
        out = result.stdout + result.stderr
        assert result.returncode == 0, out

    def test_a_partial_night_is_named_but_does_not_fail(self, tmp_path):
        """PARTIAL used to print [OK] and exit 0 — the gate's own defect,
        one mode over, live on revenue_by_source and population.

        It must now be visible without turning the nightly red: a secondary
        series did refresh, and revenue_by_source has been partial for ~20
        consecutive runs, so failing on it would mute the gate.
        """
        rows = [r for r in HEALTHY_NIGHT if r[0] != "revenue_by_source"]
        rows.append(
            (
                "revenue_by_source",
                "completed",
                0,
                0,
                49,
                "partial",
                "no_live_overlay_applied",
            )
        )
        result = _run_step(_write_db(tmp_path, rows))
        out = result.stdout + result.stderr
        assert "[PARTIAL] revenue_by_source" in out, (
            f"a partial domain printed as though it were fine.\n{out}"
        )
        assert "[WARN] revenue_by_source this run" in out
        assert result.returncode == 0, (
            f"a partial night failed the run; it should warn.\n{out}"
        )

    def test_a_refused_night_fails_the_run(self, tmp_path):
        rows = [r for r in HEALTHY_NIGHT if r[0] != "national_debt"]
        rows.append(
            (
                "national_debt",
                "completed",
                0,
                0,
                0,
                "refused",
                "external_register_incomplete",
            )
        )
        result = _run_step(_write_db(tmp_path, rows))
        out = result.stdout + result.stderr
        assert "[REFUSED] national_debt" in out
        assert "[FAIL] national_debt this run" in out
        assert result.returncode != 0, (
            f"a domain that refused to publish reported success.\n{out}"
        )

    def test_an_empty_jobs_table_is_not_a_success(self, tmp_path):
        """One step further back: the seeder recorded nothing at all.

        The domain loop prints nothing, `failed` stays 0, and the step used
        to report a success it had not observed.
        """
        result = _run_step(_write_db(tmp_path, []))
        out = result.stdout + result.stderr
        assert result.returncode != 0, (
            f"an empty ingestion_jobs table reported success.\n{out}"
        )
        assert "recorded nothing" in out

    def test_a_census_only_table_is_not_a_success(self, tmp_path):
        """__row_census__ is the validate job's own bookkeeping. A table
        holding only that is still a run that ingested nothing."""
        result = _run_step(
            _write_db(
                tmp_path,
                [],
                extra=[("__row_census__", "completed", 0, 0, 0, None, None)],
            )
        )
        assert result.returncode != 0, result.stdout + result.stderr

    def test_the_row_census_does_not_redden_the_run(self, tmp_path):
        """The validate job parks its counts in this same table under
        __row_census__ and records no source_mode. It is bookkeeping, not a
        domain; a gate that generates its own noise gets muted."""
        result = _run_step(
            _write_db(
                tmp_path,
                HEALTHY_NIGHT,
                extra=[("__row_census__", "completed", 0, 0, 0, None, None)],
            )
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestTheRuleItself:
    """Unit-level, so a change to the rule is diagnosable without bash."""

    def _job(self, domain, mode, reason=None, status="completed"):
        class _J:
            pass

        j = _J()
        j.domain = domain
        j.started_at = datetime(2026, 9, 19, 2, 30)
        j.meta = {}
        if mode is not None:
            j.meta["source_mode"] = mode
        if reason:
            j.meta["source_fallback_reason"] = reason

        class _S:
            value = status

        j.status = _S()
        return j

    def test_only_the_two_declared_reasons_are_exempt(self):
        from seeding.staleness import (
            DECLARED_NO_SOURCE_REASONS,
            EXEMPT_FIXTURE_REASONS,
            SUPERSEDED_REASONS,
        )

        assert EXEMPT_FIXTURE_REASONS == (
            DECLARED_NO_SOURCE_REASONS | SUPERSEDED_REASONS
        )
        assert EXEMPT_FIXTURE_REASONS == {"no_live_source", "fixture_superseded"}

    def test_every_other_fixture_reason_fails(self):
        from seeding.staleness import hollow_run_findings

        # Every fixture reason the domains actually emit, grepped from
        # seeding/domains/*/: none of these means "there is no publisher".
        for reason in (
            "parser_returned_nothing",
            "live_fetch_failed",
            "source_unreachable",
            "no_document_extracted",
            "brop_unavailable",
            "cbk_bulletin_unavailable",
            "no_source_available",
            "fixture_missing",
            "live_pdf_fetch_disabled",
            "live_source_disabled",
            "county_entities_unresolved",
            "external_register_incomplete",
            "no_live_overlay_applied",
            "no_live_county_source",
        ):
            findings = hollow_run_findings([self._job("audits", "fixture", reason)])
            assert findings, f"{reason} was silently exempt"
            assert findings[0].level == "FAIL"
            assert reason in findings[0].message

    def test_an_unrecorded_mode_is_not_a_pass(self):
        from seeding.staleness import hollow_run_findings

        findings = hollow_run_findings([self._job("audits", None)])
        assert findings and findings[0].level == "FAIL"
        assert "no source_mode" in findings[0].message

    def test_partial_is_reported_as_a_warning_not_passed_over(self):
        """PARTIAL means the headline figure is still a fixture.

        The first version of this gate branched on ``fixture`` and
        ``unknown`` only, so partial fell through to NO FINDING AT ALL and
        printed ``[OK]`` — the gate's own defect, one mode over, live on
        ``revenue_by_source`` (KRA overlay unpromoted) and ``population``
        (county breakdown still the census fixture).

        It is WARN and not FAIL deliberately, matching what
        ``check_ingestion_freshness`` says about the same state: a secondary
        series did refresh, and revenue_by_source has been partial for ~20
        consecutive runs, so failing on it would paint every night red and
        the gate would be muted along with everything beside it.
        """
        from seeding.staleness import hollow_run_findings

        findings = hollow_run_findings(
            [self._job("population", "partial", "no_live_county_source")]
        )
        assert findings, "PARTIAL produced no finding at all"
        assert findings[0].level == "WARN"
        assert "SECONDARY" in findings[0].message
        assert "no_live_county_source" in findings[0].message

    def test_refused_fails_the_run(self):
        """A domain that refused to publish wrote nothing; the reader is on
        the previous seed's rows. The window gate calls this FAIL, and so
        does this one — same verdict, asked about tonight."""
        from seeding.staleness import hollow_run_findings

        findings = hollow_run_findings(
            [self._job("national_debt", "refused", "external_register_incomplete")]
        )
        assert findings and findings[0].level == "FAIL"
        assert "REFUSED" in findings[0].message

    def test_every_declared_mode_is_judged(self):
        """freshness.py declares five modes. A mode this function has not
        been taught must not arrive green — matching a known set and failing
        on the remainder is what keeps a sixth one from slipping through."""
        from seeding import freshness
        from seeding.staleness import hollow_run_findings

        declared = {
            freshness.LIVE,
            freshness.FIXTURE,
            freshness.PARTIAL,
            freshness.REFUSED,
            freshness.UNKNOWN,
        }
        assert declared == {"live", "fixture", "partial", "refused", "unknown"}

        silent = [
            m
            for m in declared - {"live"}
            if not hollow_run_findings([self._job("audits", m, "some_reason")])
        ]
        assert not silent, f"these modes produced no finding at all: {silent}"

    def test_an_unrecognised_or_oddly_cased_mode_fails(self):
        """Not reachable from today's writers, which are constants — but a
        value this function does not recognise is the absence of evidence
        that the publisher was reached, not evidence that it was."""
        from seeding.staleness import hollow_run_findings

        for mode in ("Fixture", "FIXTURE", " fixture", "fixture\n", "", 0, ["fixture"]):
            findings = hollow_run_findings([self._job("audits", mode)])
            assert findings and findings[0].level == "FAIL", (
                f"source_mode={mode!r} passed the gate silently"
            )

    def test_live_is_not_hollow(self):
        from seeding.staleness import hollow_run_findings

        assert hollow_run_findings([self._job("audits", "live")]) == []

    def test_the_verdict_uses_the_newest_row_per_domain(self):
        from seeding.staleness import hollow_run_findings

        old = self._job("audits", "fixture", "parser_returned_nothing")
        old.started_at = datetime(2026, 9, 19, 2, 0)
        old.id = 1
        new = self._job("audits", "live")
        new.started_at = datetime(2026, 9, 19, 2, 30)
        new.id = 2
        assert hollow_run_findings([old, new]) == []
        assert hollow_run_findings([new, old]) == []

    def test_a_started_at_tie_is_broken_by_id_not_by_caller_order(self):
        """``_run_order`` alone is stable, so the survivor used to be
        whichever the CALLER's ordering put last — and the nightly queries
        ``ORDER BY id DESC``, which made the tie-break pick the OLDEST row
        and report a superseded verdict as this run's."""
        from seeding.staleness import hollow_run_findings, latest_job_per_domain

        same = datetime(2026, 9, 19, 2, 30)
        first = self._job("audits", "live")
        first.started_at, first.id = same, 1
        second = self._job("audits", "fixture", "parser_returned_nothing")
        second.started_at, second.id = same, 2

        for order in ([second, first], [first, second]):
            assert [j.id for j in latest_job_per_domain(order)] == [2]
            findings = hollow_run_findings(order)
            assert findings and findings[0].level == "FAIL", (
                "the older row won the tie and its verdict was reported"
            )

    def test_the_bootstrap_domain_name_matches_bootstrap(self):
        """The constant is spelled out in staleness.py to keep a workflow
        step from importing the whole bootstrap module. Pin the copy."""
        from bootstrap import BOOTSTRAP_DOMAIN as real
        from seeding.staleness import BOOTSTRAP_DOMAIN as copied

        assert copied == real

    def test_a_malformed_meta_does_not_crash_the_gate(self):
        """``meta`` is JSONB and can come back as a list, a string or null.
        A raise here would take out the step whose job is reporting."""
        from seeding.staleness import hollow_run_findings

        for bad in ([], "fixture", None, 7):
            job = self._job("audits", "live")
            job.meta = bad
            findings = hollow_run_findings([job])
            assert findings and findings[0].level == "FAIL", (
                f"meta={bad!r} produced no finding; an unreadable provenance "
                "record is not evidence of a live fetch"
            )
