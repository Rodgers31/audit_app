"""Real CLI transactions: unknown work must never become a completed job.

Handlers here are inert result-boundary producers, not upstream-source proofs.
The CLI, ownership, ORM, rollback and terminal acknowledgement remain real.
"""
import argparse
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from models import AdminAuditLog, Base, IngestionJob, IngestionStatus, SeedingDomainClaim
from seeding import cli, freshness
from seeding.config import SeedingSettings
from seeding.types import DomainRunResult


@compiles(JSONB, "sqlite")
def sqlite_jsonb(_element, _compiler, **_kwargs):
    return "TEXT"


PLAN = dict(mode="discovery_only", extraction="not_requested", publication="not_requested")
COUNTERS = ("items_processed", "items_created", "items_updated")


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'cli-result.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(cli, "SessionLocal", factory)
    monkeypatch.setattr(cli, "load_builtin_domains", lambda: None)
    for flag in ("SOCIAL_GENERATION_HOOK_ENABLED", "SOCIAL_REPORT_GENERATION_ENABLED"):
        monkeypatch.setenv(flag, "false")
    yield factory
    engine.dispose()
    (tmp_path / "cli-result.sqlite").unlink()


def invoke(monkeypatch, handler, *, domain="population", dry_run=False):
    from seeding.registries import DomainRegistry
    registry = DomainRegistry()
    registry.register(domain, handler)
    monkeypatch.setattr(cli, "REGISTRY", registry)
    return cli.run_seed_command(
        argparse.Namespace(domain=[domain], all=False, dry_run=dry_run, since=None),
        SeedingSettings(_env_file=None, log_path=None, total_timeout_seconds=0),
    )


def result(**changes):
    # Exercise the same unvalidated copies/constructs that a handler can return.
    return DomainRunResult(domain="population", items_processed=2).model_copy(update=changes)


BAD_RESULTS = [
    pytest.param(lambda: None, id="missing"), pytest.param(lambda: {}, id="dict"),
    pytest.param(lambda: [], id="list"), pytest.param(lambda: False, id="false"),
    pytest.param(lambda: True, id="true"), pytest.param(lambda: 0, id="zero"),
    pytest.param(lambda: "done", id="string"),
    pytest.param(lambda: DomainRunResult(domain="population"), id="empty-model"),
    pytest.param(lambda: result(domain="audits"), id="wrong-domain"),
    pytest.param(lambda: DomainRunResult(domain="population", items_processed=1, success=False), id="failed-extra"),
    pytest.param(lambda: DomainRunResult(domain="population", items_processed=1, status="failed"), id="status-extra"),
    pytest.param(lambda: result(dry_run=True), id="wrong-intent"),
    pytest.param(lambda: result(errors="bad"), id="string-errors"),
    pytest.param(lambda: result(errors=[None]), id="null-error"),
    pytest.param(lambda: result(errors=[""]), id="empty-error"),
    pytest.param(lambda: result(metadata=[]), id="list-metadata"),
    pytest.param(lambda: result(metadata={"nested": float("nan")}), id="nan-metadata"),
    pytest.param(lambda: result(metadata={"nested": {1: "bad"}}), id="numeric-metadata-key"),
    pytest.param(lambda: result(metadata={"seeding_claim_id": "forged"}), id="ownership-metadata"),
    pytest.param(lambda: result(items_created=2, items_updated=1), id="overcount"),
    pytest.param(lambda: result(started_at="today"), id="string-start"),
    pytest.param(lambda: result(finished_at=datetime(2000, 1, 1, tzinfo=timezone.utc)), id="reversed-time"),
    pytest.param(lambda: result(started_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
                        finished_at=datetime(2000, 1, 1, tzinfo=timezone.utc)), id="stale-run"),
]
BAD_RESULTS += [
    pytest.param(lambda counter=counter, bad=bad: result(**{counter: bad}), id=f"{counter}-{label}")
    for counter in COUNTERS
    for label, bad in [("bool", True), ("false", False), ("float", 1.0),
                       ("string", "1"), ("negative", -1), ("overflow", 2147483648),
                       ("nan", float("nan")), ("infinity", float("inf")), ("none", None)]
]


@pytest.mark.parametrize("bad", BAD_RESULTS)
def test_invalid_return_rolls_back_effects_and_persists_failed_job(db, monkeypatch, bad):
    def handler(session, **_kwargs):
        session.add(AdminAuditLog(actor_id="fixture", action="fixture.effect", payload={}))
        session.flush()
        # Construct during execution so the timestamp guard cannot mask a
        # counter/shape guard's deletion. Only explicit stale cases are stale.
        return bad()
    assert invoke(monkeypatch, handler) == 1
    with db() as session:
        job = session.scalars(select(IngestionJob)).one()
        assert job.status == IngestionStatus.FAILED
        assert (job.items_processed, job.items_created, job.items_updated) == (0, 0, 0)
        assert job.finished_at is not None and job.errors
        assert "Invalid domain result" in job.errors[0]
        assert session.query(AdminAuditLog).count() == 0
        claim = session.scalars(select(SeedingDomainClaim)).one()
        assert claim.returned_at is not None and claim.released_at is not None


@pytest.mark.parametrize("created,updated", [(0, 0), (1, 0), (0, 1), (1, 1)])
@pytest.mark.parametrize("dry_run", [False, True])
def test_positive_inventory_including_unchanged_is_valid(db, monkeypatch, created, updated, dry_run):
    def handler(session, **_kwargs):
        freshness.mark_live("population")
        session.add(AdminAuditLog(actor_id="fixture", action="fixture.effect", payload={}))
        return result(items_created=created, items_updated=updated, dry_run=dry_run)
    assert invoke(monkeypatch, handler, dry_run=dry_run) == 0
    with db() as session:
        job = session.scalars(select(IngestionJob)).one()
        assert job.status == IngestionStatus.COMPLETED
        assert (job.items_processed, job.items_created, job.items_updated) == (2, created, updated)
        assert session.query(AdminAuditLog).count() == int(not dry_run)


@pytest.mark.parametrize("domain,dry_run,plan", [
    ("population", True, PLAN), ("audits", False, PLAN),
    ("audits", True, {}), ("audits", True, {**PLAN, "extra": "unknown"}),
    ("audits", True, {**PLAN, "extraction": True}),
])
def test_discovery_exception_cannot_authorize_other_empty_work(db, monkeypatch, domain, dry_run, plan):
    def handler(**_kwargs):
        return DomainRunResult(domain=domain, dry_run=dry_run, metadata={"dry_run_plan": plan})
    assert invoke(monkeypatch, handler, domain=domain, dry_run=dry_run) == 1
    with db() as session:
        assert session.scalars(select(IngestionJob)).one().status == IngestionStatus.FAILED


@pytest.mark.parametrize("errors", [[], ["listing unavailable"]])
def test_exact_oag_discovery_plan_retains_success_and_warning_contract(db, monkeypatch, errors):
    def handler(**_kwargs):
        return DomainRunResult(domain="audits", dry_run=True, errors=errors,
                               metadata={"dry_run_plan": PLAN})
    assert invoke(monkeypatch, handler, domain="audits", dry_run=True) == 0
    with db() as session:
        job = session.scalars(select(IngestionJob)).one()
        assert job.status == (IngestionStatus.COMPLETED_WITH_ERRORS if errors else IngestionStatus.COMPLETED)
        assert job.errors == errors and job.meta["dry_run_plan"] == PLAN


def test_zero_inventory_with_explicit_errors_is_not_execution_success(db, monkeypatch):
    assert invoke(monkeypatch, lambda **_: result(items_processed=0, errors=["fetch unavailable"])) == 1
    with db() as session:
        job = session.scalars(select(IngestionJob)).one()
        assert job.status == IngestionStatus.COMPLETED_WITH_ERRORS
        assert job.errors == ["fetch unavailable"]


def test_zero_inventory_fixture_failure_remains_a_warning_and_nonzero_exit(db, monkeypatch):
    def handler(**_kwargs):
        freshness.mark_fixture("population", reason="fixture_boundary_control")
        return DomainRunResult(domain="population")
    assert invoke(monkeypatch, handler) == 1
    with db() as session:
        job = session.scalars(select(IngestionJob)).one()
        assert job.status == IngestionStatus.COMPLETED_WITH_ERRORS
        assert job.meta["source_mode"] == "fixture"
        assert any("served from fixture" in error for error in job.errors)


def test_discovery_only_plan_cannot_claim_processed_inventory(db, monkeypatch):
    def handler(**_kwargs):
        return DomainRunResult(domain="audits", dry_run=True, items_processed=1,
                               metadata={"dry_run_plan": PLAN})
    assert invoke(monkeypatch, handler, domain="audits", dry_run=True) == 1
    with db() as session:
        assert session.scalars(select(IngestionJob)).one().status == IngestionStatus.FAILED


@pytest.mark.parametrize("failure", [RuntimeError("fixture exception"), cli.DomainTimeoutError("fixture timeout")])
def test_handler_failure_remains_failed_with_rollback(db, monkeypatch, failure):
    def handler(session, **_kwargs):
        session.add(AdminAuditLog(actor_id="fixture", action="fixture.effect", payload={}))
        session.flush()
        raise failure
    assert invoke(monkeypatch, handler) == 1
    with db() as session:
        assert session.scalars(select(IngestionJob)).one().status == IngestionStatus.FAILED
        assert session.query(AdminAuditLog).count() == 0


def test_caller_catching_cancellation_cannot_commit_handler_effect(db, monkeypatch):
    sessions = []
    def handler(session, **_kwargs):
        sessions.append(session)
        session.add(AdminAuditLog(actor_id="fixture", action="fixture.effect", payload={}))
        session.flush()
        raise KeyboardInterrupt("fixture cancellation")
    with pytest.raises(KeyboardInterrupt):
        invoke(monkeypatch, handler)
    sessions[0].commit()
    with db() as session:
        assert session.scalars(select(IngestionJob)).one().status == IngestionStatus.RUNNING
        assert session.query(AdminAuditLog).count() == 0
        claim = session.scalars(select(SeedingDomainClaim)).one()
        assert claim.returned_at is None and claim.released_at is None
