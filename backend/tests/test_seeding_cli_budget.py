"""Tests for the global wall-clock budget in ``run_seed_command``.

These exercise ``seeding.cli.run_seed_command`` with a fake monotonic clock,
a fake registry, and a sqlite DB. The fake clock drives all deadline logic, so
no real ``time.sleep`` ever runs; handlers that need to "time out" raise
``DomainTimeoutError`` directly rather than waiting for a real SIGALRM. The
per-domain SIGALRM is still armed and cancelled, but with budgets far larger
than the (instant) handlers, so it never fires — keeping the tests
deterministic.
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
def _compile_jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover - dialect shim
    return "TEXT"


class _Clock:
    """Controllable stand-in for the ``time`` module used by the CLI."""

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
def sessionmaker_factory(tmp_path) -> Iterator[sessionmaker]:
    engine = create_engine(f"sqlite:///{tmp_path / 'seed_cli.db'}")
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine)
    finally:
        engine.dispose()


@pytest.fixture()
def clock(monkeypatch, sessionmaker_factory) -> _Clock:
    """Wire the CLI to the sqlite DB, a no-op builtin loader, and a fake clock."""
    fake = _Clock()
    monkeypatch.setattr(seed_cli, "SessionLocal", sessionmaker_factory)
    monkeypatch.setattr(seed_cli, "load_builtin_domains", lambda: None)
    monkeypatch.setattr(seed_cli, "time", fake)
    return fake


def _args() -> argparse.Namespace:
    return argparse.Namespace(domain=None, all=True, dry_run=False, since=None)


def _jobs_by_domain(maker: sessionmaker) -> dict:
    with maker() as session:
        rows = session.execute(select(IngestionJob)).scalars().all()
        return {row.domain: row for row in rows}


def _make_handler(calls, name, *, work=0.0, raise_timeout=False, clock=None):
    def _handler(*, session, settings, context):
        calls.append(name)
        if clock is not None and work:
            clock.advance(work)
        if raise_timeout:
            raise seed_cli.DomainTimeoutError(
                "domain exceeded Ns budget; aborted by the CLI"
            )
        return DomainRunResult(domain=name)

    return _handler


def test_global_budget_skips_remaining_domains_and_stays_green(
    clock, sessionmaker_factory, monkeypatch
):
    calls: list[str] = []
    handlers = {
        "a": _make_handler(calls, "a", work=60, clock=clock),
        "b": _make_handler(calls, "b", work=60, clock=clock),
        "c": _make_handler(calls, "c", work=60, clock=clock),
    }
    monkeypatch.setattr(seed_cli, "REGISTRY", _FakeRegistry(handlers))
    settings = SeedingSettings(total_timeout_seconds=100, domain_timeout_seconds=600)

    status = seed_cli.run_seed_command(_args(), settings)

    assert status == 0  # clean, green exit (no SIGKILL, validation can run)
    assert calls == ["a", "b"]  # "c" never started — past the global deadline
    jobs = _jobs_by_domain(sessionmaker_factory)
    assert jobs["a"].status == IngestionStatus.COMPLETED
    assert jobs["b"].status == IngestionStatus.COMPLETED
    assert "c" not in jobs  # skipped domains get no job record


def test_global_budget_truncates_in_flight_domain_cleanly(
    clock, sessionmaker_factory, monkeypatch
):
    calls: list[str] = []
    handlers = {
        "a": _make_handler(calls, "a", work=60, clock=clock),
        # Simulates the globally-capped alarm firing mid-domain.
        "b": _make_handler(calls, "b", raise_timeout=True),
        "c": _make_handler(calls, "c"),
    }
    monkeypatch.setattr(seed_cli, "REGISTRY", _FakeRegistry(handlers))
    settings = SeedingSettings(total_timeout_seconds=100, domain_timeout_seconds=600)

    status = seed_cli.run_seed_command(_args(), settings)

    assert status == 0  # a global-budget truncation is NOT a failure
    assert calls == ["a", "b"]  # "c" never started
    jobs = _jobs_by_domain(sessionmaker_factory)
    assert jobs["a"].status == IngestionStatus.COMPLETED
    assert jobs["b"].status == IngestionStatus.COMPLETED_WITH_ERRORS
    assert any("budget" in str(e).lower() for e in (jobs["b"].errors or []))
    assert "c" not in jobs


def test_per_domain_timeout_still_fails_and_continues(
    clock, sessionmaker_factory, monkeypatch
):
    # Global budget disabled: a domain blowing its OWN budget is a real failure
    # (status 1, job FAILED) and the run continues to the next domain — exactly
    # the behaviour that existed before the global budget was added.
    calls: list[str] = []
    handlers = {
        "a": _make_handler(calls, "a", raise_timeout=True),
        "b": _make_handler(calls, "b"),
    }
    monkeypatch.setattr(seed_cli, "REGISTRY", _FakeRegistry(handlers))
    settings = SeedingSettings(total_timeout_seconds=0, domain_timeout_seconds=600)

    status = seed_cli.run_seed_command(_args(), settings)

    assert status == 1
    assert calls == ["a", "b"]  # per-domain failure does not stop the whole run
    jobs = _jobs_by_domain(sessionmaker_factory)
    assert jobs["a"].status == IngestionStatus.FAILED
    assert jobs["b"].status == IngestionStatus.COMPLETED


def _make_swallowing_handler(calls, swallowed, name):
    """A handler mimicking a real domain fetcher: it wraps the (timing-out)
    upstream call in ``except Exception`` and falls back to a fixture.

    This is the exact shape that made the SIGALRM budget silently useless in
    production (issues #105-#113): the alarm fired, the fetcher caught the
    ``DomainTimeoutError`` here as if a single item had failed, "recovered",
    and the domain kept running until the CI step SIGKILL. If the timeout is a
    plain ``Exception`` it is swallowed here; as a ``BaseException`` it must
    propagate to the CLI.
    """

    def _handler(*, session, settings, context):
        calls.append(name)
        try:
            raise seed_cli.DomainTimeoutError(
                "domain exceeded Ns budget; aborted by the CLI"
            )
        except Exception:  # noqa: BLE001 - intentionally broad; mirrors fetchers
            swallowed.append(name)
            return DomainRunResult(domain=name)  # pretend the fixture fallback won

    return _handler


def test_global_budget_timeout_survives_fetcher_except_exception(
    clock, sessionmaker_factory, monkeypatch
):
    """Regression: a globally-capped timeout must not be swallowed by a
    fetcher's ``except Exception``. It should stop the run cleanly (green)."""
    calls: list[str] = []
    swallowed: list[str] = []
    handlers = {
        "a": _make_handler(calls, "a", work=60, clock=clock),
        "b": _make_swallowing_handler(calls, swallowed, "b"),
        "c": _make_handler(calls, "c"),
    }
    monkeypatch.setattr(seed_cli, "REGISTRY", _FakeRegistry(handlers))
    settings = SeedingSettings(total_timeout_seconds=100, domain_timeout_seconds=600)

    status = seed_cli.run_seed_command(_args(), settings)

    assert swallowed == []  # the fetcher's except Exception did NOT catch it
    assert status == 0  # clean global-budget stop, not a failure
    assert calls == ["a", "b"]  # timeout stopped the run at b; c never started
    jobs = _jobs_by_domain(sessionmaker_factory)
    assert jobs["b"].status == IngestionStatus.COMPLETED_WITH_ERRORS
    assert "c" not in jobs


def test_own_budget_timeout_survives_fetcher_except_exception(
    clock, sessionmaker_factory, monkeypatch
):
    """Regression: a domain's own-budget timeout must not be swallowed by a
    fetcher's ``except Exception`` either — it should fail that domain (status
    1, job FAILED) and continue to the next one."""
    calls: list[str] = []
    swallowed: list[str] = []
    handlers = {
        "a": _make_swallowing_handler(calls, swallowed, "a"),
        "b": _make_handler(calls, "b"),
    }
    monkeypatch.setattr(seed_cli, "REGISTRY", _FakeRegistry(handlers))
    settings = SeedingSettings(total_timeout_seconds=0, domain_timeout_seconds=600)

    status = seed_cli.run_seed_command(_args(), settings)

    assert swallowed == []  # not swallowed by the fetcher's except Exception
    assert status == 1
    assert calls == ["a", "b"]  # failed domain does not stop the whole run
    jobs = _jobs_by_domain(sessionmaker_factory)
    assert jobs["a"].status == IngestionStatus.FAILED
    assert jobs["b"].status == IngestionStatus.COMPLETED
