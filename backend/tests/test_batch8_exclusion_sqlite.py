"""The real CLI's shared ownership on SQLite (no advisory lock; partial index only).

Mirrors the independent Spec reproduction (spec-scope-repro.py) which first
showed forged scopes running work here; no sockets, no PostgreSQL.
"""
import argparse
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from models import Base
from seeding import cli, registries
import seeding.domains.audits.scope  # noqa: F401  registers the real handler once, before patching
from seeding.config import SeedingSettings
from seeding.exclusion import DomainExecution, dispatch_scope, reserve
from seeding.types import DomainRunResult


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(*args, **kwargs):
    return "TEXT"


@pytest.fixture
def sqlite_cli(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'ownership.sqlite'}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE inert_effects (value integer)"))
    factory = sessionmaker(bind=engine)

    def handler(session, settings, context):
        session.execute(text("INSERT INTO inert_effects VALUES (1)"))
        return DomainRunResult(domain="audits", dry_run=context.dry_run, items_created=1)

    monkeypatch.setattr(registries.REGISTRY, "_handlers", {"audits": handler})
    monkeypatch.setattr(cli, "load_builtin_domains", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", factory)
    yield factory, engine
    engine.dispose()


def run():
    args = argparse.Namespace(domain=["audits"], all=False, since=None, dry_run=False,
        audits_source_manifest=None, audits_observe_listing=False)
    return cli.run_seed_command(args, SeedingSettings(log_path=None, total_timeout_seconds=0))


def state(engine):
    with engine.connect() as conn:
        return (conn.scalar(text("SELECT count(*) FROM inert_effects")),
                conn.scalar(text("SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NULL")),
                conn.scalar(text("SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NOT NULL")))


def test_sqlite_native_runs_release_and_retained_claim_excludes(sqlite_cli):
    factory, engine = sqlite_cli
    assert run() == 0 and run() == 0
    assert state(engine) == (2, 0, 2)
    with factory.begin() as db:
        assert reserve(db, "audits", uuid4())
    assert run() == 1
    assert state(engine) == (2, 1, 2)


@pytest.mark.parametrize("reuse_retained", [False, True])
def test_sqlite_forged_scope_starts_no_work_and_keeps_retained_claim(sqlite_cli, reuse_retained):
    factory, engine = sqlite_cli
    retained = uuid4()
    with factory.begin() as db:
        assert reserve(db, "audits", retained)
    execution = DomainExecution(factory, "audits", retained if reuse_retained else uuid4())
    execution.open()
    with dispatch_scope(execution):
        assert run() == 1
    assert state(engine) == (0, 1, 0)
