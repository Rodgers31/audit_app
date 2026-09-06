"""A run that dropped domains must not report success.

The global wall-clock budget was built (issues #105-#113) so a slow night ends
cleanly instead of being SIGKILLed by the CI step timeout. It ends the run by
recording the in-flight domain as ``completed_with_errors`` and returning 0,
and by `break`ing out of the loop — which leaves the domains it never reached
with **no ingestion_jobs row at all**.

The 2026-09-06 03:19 nightly is what that looks like in production::

    Global seed budget exhausted during 'pending_bills' (1319s elapsed);
    stopping run cleanly
    ...
    [WARN] pending_bills: completed_with_errors | ... | source=unrecorded
      ERROR: stopped: global seed budget exhausted

`population`, `revenue_by_source` and `stalled_projects` sort after
`pending_bills` and were never attempted, so they appear nowhere in the
"--- Ingestion Job Results ---" summary. The workflow's exit-code check counts
only ``status == 'failed'``, so the step's verdict was decided entirely by an
unrelated bootstrap failure; without it the step would have printed "All
domains completed successfully."

Nor does the freshness gate catch it: `check_ingestion_freshness` reports OK
while any run in its 14-day window reached the publisher, so a domain dropped
every night stays OK for a fortnight and then becomes a WARN — never a FAIL.

Four domains can therefore stop refreshing indefinitely without anything going
red. The original "stay green so the validation job still runs" concern is kept
by making `validate` independent of the seed job's conclusion in seed.yml,
not by having the run misreport itself.
"""

from __future__ import annotations

import argparse
from typing import Iterator

import pytest
from models import Base, IngestionJob, IngestionStatus
from seeding import cli as seed_cli
from seeding.config import SeedingSettings
from seeding.types import DomainRunResult
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover - shim
    return "TEXT"


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _FakeRegistry:
    def __init__(self, handlers: dict) -> None:
        self._handlers = handlers

    def domains(self):
        return list(self._handlers)

    def get(self, name):
        return self._handlers.get(name)


@pytest.fixture()
def maker(tmp_path) -> Iterator[sessionmaker]:
    engine = create_engine(f"sqlite:///{tmp_path / 'truncated.db'}")
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine)
    finally:
        engine.dispose()


@pytest.fixture()
def clock(monkeypatch, maker) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(seed_cli, "SessionLocal", maker)
    monkeypatch.setattr(seed_cli, "load_builtin_domains", lambda: None)
    monkeypatch.setattr(seed_cli, "time", fake)
    return fake


def _args() -> argparse.Namespace:
    return argparse.Namespace(domain=None, all=True, dry_run=False, since=None)


def _jobs(maker: sessionmaker) -> dict:
    with maker() as session:
        return {
            row.domain: row
            for row in session.execute(select(IngestionJob)).scalars().all()
        }


def _handler(calls, name, *, work=0.0, raise_timeout=False, clock=None):
    def _run(*, session, settings, context):
        calls.append(name)
        if clock is not None and work:
            clock.advance(work)
        if raise_timeout:
            raise seed_cli.DomainTimeoutError("aborted by the CLI")
        return DomainRunResult(domain=name)

    return _run


class TestDomainsNeverAttemptedAreRecorded:
    def test_a_skipped_domain_leaves_a_row(self, clock, maker, monkeypatch):
        """The bug: 'c' vanishes from the run entirely."""
        calls: list[str] = []
        monkeypatch.setattr(
            seed_cli,
            "REGISTRY",
            _FakeRegistry(
                {
                    "a": _handler(calls, "a", work=60, clock=clock),
                    "b": _handler(calls, "b", work=60, clock=clock),
                    "c": _handler(calls, "c", work=60, clock=clock),
                }
            ),
        )
        settings = SeedingSettings(
            total_timeout_seconds=100, domain_timeout_seconds=600
        )

        status = seed_cli.run_seed_command(_args(), settings)

        assert calls == ["a", "b"], "c must still not be started"
        jobs = _jobs(maker)
        assert "c" in jobs, (
            "a domain the budget skipped writes no ingestion_jobs row, so it "
            "is absent from the nightly summary and invisible to the "
            "freshness gate"
        )
        assert jobs["c"].status == IngestionStatus.FAILED
        assert any("budget" in str(e).lower() for e in (jobs["c"].errors or []))
        assert status == 1, "a run that dropped a domain did not do its job"

    def test_the_in_flight_domain_is_a_failure_not_a_warning(
        self, clock, maker, monkeypatch
    ):
        """`pending_bills` did not refresh; completed_with_errors reads as OK."""
        calls: list[str] = []
        monkeypatch.setattr(
            seed_cli,
            "REGISTRY",
            _FakeRegistry(
                {
                    "a": _handler(calls, "a", work=60, clock=clock),
                    "b": _handler(calls, "b", raise_timeout=True),
                    "c": _handler(calls, "c"),
                }
            ),
        )
        settings = SeedingSettings(
            total_timeout_seconds=100, domain_timeout_seconds=600
        )

        status = seed_cli.run_seed_command(_args(), settings)

        jobs = _jobs(maker)
        assert jobs["b"].status == IngestionStatus.FAILED
        assert jobs["c"].status == IngestionStatus.FAILED
        assert status == 1

    def test_every_dropped_domain_is_named_not_just_the_first(
        self, clock, maker, monkeypatch
    ):
        """Production dropped four; all four must be visible."""
        calls: list[str] = []
        monkeypatch.setattr(
            seed_cli,
            "REGISTRY",
            _FakeRegistry(
                {
                    "a": _handler(calls, "a", work=200, clock=clock),
                    "b": _handler(calls, "b"),
                    "c": _handler(calls, "c"),
                    "d": _handler(calls, "d"),
                }
            ),
        )
        settings = SeedingSettings(
            total_timeout_seconds=100, domain_timeout_seconds=600
        )

        seed_cli.run_seed_command(_args(), settings)

        jobs = _jobs(maker)
        assert {"b", "c", "d"} <= set(jobs), sorted(jobs)
        for name in ("b", "c", "d"):
            assert jobs[name].status == IngestionStatus.FAILED


class TestAnUntruncatedRunIsUnaffected:
    """The budget must stay invisible on a night that fits."""

    def test_a_run_that_finishes_is_still_green(self, clock, maker, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr(
            seed_cli,
            "REGISTRY",
            _FakeRegistry(
                {
                    "a": _handler(calls, "a", work=10, clock=clock),
                    "b": _handler(calls, "b", work=10, clock=clock),
                }
            ),
        )
        settings = SeedingSettings(
            total_timeout_seconds=100, domain_timeout_seconds=600
        )

        assert seed_cli.run_seed_command(_args(), settings) == 0
        assert calls == ["a", "b"]
        assert all(
            j.status == IngestionStatus.COMPLETED for j in _jobs(maker).values()
        )

    def test_no_global_budget_means_no_dropped_rows(self, clock, maker, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr(
            seed_cli,
            "REGISTRY",
            _FakeRegistry(
                {
                    "a": _handler(calls, "a", work=10_000, clock=clock),
                    "b": _handler(calls, "b", work=10_000, clock=clock),
                }
            ),
        )
        settings = SeedingSettings(
            total_timeout_seconds=0, domain_timeout_seconds=600
        )

        assert seed_cli.run_seed_command(_args(), settings) == 0
        assert calls == ["a", "b"]
