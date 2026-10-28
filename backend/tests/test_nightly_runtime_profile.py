"""Replay #836's timing envelope through the real scheduled CLI, without HTTP.

This qualifies time allocation and terminal job accounting, not live source
freshness. Provider handlers and the clock are simulated; the CLI, source plan,
ownership and job persistence are real.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re

from models import IngestionStatus
from seeding import cli, fair_progress
from seeding.config import SeedingSettings
from seeding.source_plan import DAILY, build_plan
from seeding.types import DomainRunResult
from test_hollow_run_gate import HEALTHY_NIGHT, _run_step, _write_db
from test_seeding_cli_budget import (
    _FakeRegistry, _jobs_by_domain, clock, sessionmaker_factory,
)
import yaml
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from models import IngestionJob


TRACE = json.loads((Path(__file__).parent / "fixtures/nightly_runtime_836.json").read_text())
WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/seed.yml"


def workflow_profile():
    workflow = yaml.safe_load(WORKFLOW.read_text())
    expression = workflow["env"]["SEED_TOTAL_TIMEOUT_SECONDS"]
    match = re.fullmatch(r"\$\{\{ vars.SEED_TOTAL_TIMEOUT_SECONDS \|\| '(\d+)' \}\}", expression)
    assert match, "The test must resolve the actual workflow fallback"
    return int(match[1]), workflow["jobs"]["seed"]


def replay(clock, monkeypatch, *, total_seconds, slow_domain=None):
    plan = build_plan(event="schedule", schedule=DAILY, domain="", dry_run="false",
                      cra="false", opendata="false", discovery="false")
    order = TRACE["execution_order"]
    assert set(plan.domains) == set(order) == set(TRACE["handler_seconds"])
    selected = cli.build_parser().parse_args(plan.argv[3:])
    assert selected.fair_progress is True
    calls, alarms = [], []
    current_alarm = [None]

    @contextmanager
    def simulated_alarm(seconds):
        alarms.append(seconds)
        current_alarm[0] = seconds
        yield

    def handler(name):
        def run(**kwargs):
            calls.append(name)
            work = TRACE["handler_seconds"][name] + TRACE["orchestration_seconds_per_domain"]
            if name == slow_domain:
                work = 601
            if work > current_alarm[0]:
                clock.advance(current_alarm[0])
                raise cli.DomainTimeoutError("simulated alarm at the actual CLI allocation")
            clock.advance(work)
            return DomainRunResult(domain=name)
        return run

    monkeypatch.setattr(fair_progress, "admission_order", lambda maker, domains: list(order))
    monkeypatch.setattr(cli, "_domain_timeout", simulated_alarm)
    monkeypatch.setattr(cli, "REGISTRY", _FakeRegistry({n: handler(n) for n in order}))
    settings = SeedingSettings(_env_file=None, total_timeout_seconds=total_seconds)
    result = cli.run_seed_command(selected, settings)
    return result, calls, alarms


def test_workflow_default_finishes_the_observed_full_daily_timing_envelope(
    clock, sessionmaker_factory, monkeypatch,
):
    total, _ = workflow_profile()
    status, calls, alarms = replay(clock, monkeypatch, total_seconds=total)
    assert status == 0
    assert calls == TRACE["execution_order"]
    jobs = _jobs_by_domain(sessionmaker_factory)
    assert len(jobs) == 15
    assert all(job.status == IngestionStatus.COMPLETED for job in jobs.values())
    assert all(job.meta["execution_plan"]["total_budget_seconds"] == total for job in jobs.values())
    assert max(alarms) == 600  # Extending the run never extends a single source.


def test_old_22_minute_limit_still_reports_partial_work_as_failure(
    clock, sessionmaker_factory, monkeypatch,
):
    status, calls, _ = replay(clock, monkeypatch, total_seconds=1320)
    assert status == 1
    assert calls[-1] == "fiscal_summary"
    jobs = _jobs_by_domain(sessionmaker_factory)
    assert len(jobs) == 15
    for name in ("fiscal_summary", "national_budget", "revenue_by_source"):
        assert jobs[name].status == IngestionStatus.FAILED
        assert jobs[name].errors
        assert jobs[name].items_processed == 0


def test_larger_run_limit_keeps_a_stuck_source_failed_and_continues(
    clock, sessionmaker_factory, monkeypatch,
):
    total, _ = workflow_profile()
    status, calls, alarms = replay(clock, monkeypatch, total_seconds=total, slow_domain="audits")
    assert status == 1
    assert calls == TRACE["execution_order"]
    jobs = _jobs_by_domain(sessionmaker_factory)
    assert jobs["audits"].status == IngestionStatus.FAILED
    assert jobs["audits"].items_processed == 0
    assert all(j.status == IngestionStatus.COMPLETED for n, j in jobs.items() if n != "audits")
    assert max(alarms) == 600


def test_workflow_and_cli_defaults_leave_separate_cleanup_and_setup_headroom(monkeypatch):
    monkeypatch.delenv("SEED_TOTAL_TIMEOUT_SECONDS", raising=False)
    total, seed = workflow_profile()
    settings = SeedingSettings(_env_file=None)
    assert settings.total_timeout_seconds == total
    step = next(s for s in seed["steps"] if s.get("name") == "Seed planned domains")
    assert step["timeout-minutes"] * 60 >= total + 300
    assert seed["timeout-minutes"] >= step["timeout-minutes"] + 5
    assert seed["runs-on"] == "ubuntu-latest"


@pytest.mark.parametrize("state,mode,reason,label,exit_code", [
    ("failed", None, None, "FAIL", 1),
    ("completed_with_errors", "fixture", "no_document_extracted", "STALE", 1),
    ("completed", "live", None, "OK", 0),
])
def test_result_gate_includes_early_current_run_jobs(
    tmp_path, state, mode, reason, label, exit_code,
):
    rows = [r for r in HEALTHY_NIGHT if r[0] != "audits"]
    rows.append(("audits", state, 0, 0, 1, mode, reason))
    url = _write_db(tmp_path, rows)
    engine = create_engine(url)
    try:
        with Session(engine) as session:
            job = session.scalar(select(IngestionJob).where(IngestionJob.domain == "audits"))
            job.started_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1988)
            job.finished_at = job.started_at + timedelta(seconds=354)
            session.commit()
    finally:
        engine.dispose()
    result = _run_step(url)
    assert f"[{label}] audits:" in result.stdout, result.stdout
    assert result.returncode == exit_code, result.stdout + result.stderr


def test_result_gate_rejects_a_missing_planned_source(tmp_path):
    rows = [r for r in HEALTHY_NIGHT if r[0] != "audits"]
    result = _run_step(_write_db(tmp_path, rows))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "[MISSING] audits" in result.stdout


def test_result_gate_rejects_a_nonterminal_planned_source(tmp_path):
    rows = [r for r in HEALTHY_NIGHT if r[0] != "audits"]
    rows.append(("audits", "running", 0, 0, 1, "live", None))
    result = _run_step(_write_db(tmp_path, rows))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "[FAIL] audits: running" in result.stdout


def test_result_gate_excludes_failed_jobs_before_current_run_boundary(tmp_path):
    rows = [("audits", "failed", 0, 0, 0, None, None), *HEALTHY_NIGHT]
    result = _run_step(_write_db(tmp_path, rows), floor=1)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[FAIL] audits:" not in result.stdout
    assert "[OK] audits:" in result.stdout
