"""Supplied SQLite sessions are test transactions, not PostgreSQL authority."""
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

import bootstrap
from models import Entity, EntityType, IngestionJob, IngestionStatus
from seeding.registries import REGISTRY, load_builtin_domains


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("binding", ["session", "connection"])
@pytest.mark.parametrize("pending", [False, True])
def test_deferred_sqlite_caller_retains_all_bootstrap_writes(
    tmp_path, monkeypatch, force, binding, pending
):
    from models import Base
    engine = create_engine(f"sqlite:///{tmp_path / 'deferred.sqlite'}")
    Base.metadata.create_all(engine)
    connection = engine.connect()
    if binding == "session":
        caller = Session(bind=engine)
        outer = caller.begin()
        connection.close()
        connection = caller.connection()
    else:
        outer = connection.begin()
        caller = Session(bind=connection, join_transaction_mode="control_fully")
    unflushed = IngestionJob(domain="inert-caller", status=IngestionStatus.RUNNING, dry_run=True)
    if pending:
        caller.add(unflushed)
    assert connection.connection.driver_connection.in_transaction is False
    monkeypatch.setattr(bootstrap, "SessionLocal", lambda: caller)
    monkeypatch.setattr(bootstrap, "_seed_national_data", lambda *a, **k: None)
    monkeypatch.setattr(bootstrap, "enter_domain", lambda *a, **k: (_ for _ in ()).throw(
        bootstrap.DomainOwnershipError("inert competing owner")))
    try:
        bootstrap.initialize_reference_data(force=force)
        assert outer.is_active and connection.in_transaction()
        if pending:
            assert unflushed in caller.new
        assert connection.scalar(text("SELECT count(*) FROM entities")) == 47
        with engine.connect() as observer:
            assert observer.scalar(text("SELECT count(*) FROM entities")) == 0
            assert observer.scalar(text("SELECT count(*) FROM ingestion_jobs")) == 0
        outer.rollback()
        with engine.connect() as observer:
            assert observer.scalar(text("SELECT count(*) FROM entities")) == 0
            assert observer.scalar(text("SELECT count(*) FROM ingestion_jobs")) == 0
    finally:
        caller.close()
        connection.close()
        engine.dispose()


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("binding", ["session", "connection"])
def test_refusal_cannot_commit_or_rollback_caller_transaction(
    tmp_path, monkeypatch, force, binding
):
    engine = create_engine(f"sqlite:///{tmp_path / 'caller.sqlite'}")
    from models import Base
    Base.metadata.create_all(engine)
    with engine.begin() as db:
        db.execute(text("CREATE TABLE unrelated_effects(value text)"))
    if binding == "session":
        caller = Session(bind=engine)
        connection = caller.connection()
        outer = caller.get_transaction()
    else:
        connection = engine.connect()
        outer = connection.begin()
        caller = Session(bind=connection, join_transaction_mode="control_fully")
    # Force SQLite's deferred BEGIN before any savepoint can be released.
    connection.execute(text("INSERT INTO unrelated_effects VALUES ('caller-pending')"))
    monkeypatch.setattr(bootstrap, "SessionLocal", lambda: caller)
    monkeypatch.setattr(bootstrap, "_seed_national_data", lambda *a, **k: None)
    monkeypatch.setattr(bootstrap, "enter_domain", lambda *a, **k: (_ for _ in ()).throw(
        bootstrap.DomainOwnershipError("inert competing owner")))
    try:
        bootstrap.initialize_reference_data(force=force)
        assert outer.is_active and connection.in_transaction()
        assert connection.scalar(text("SELECT json_extract(metadata, '$.source_mode') FROM ingestion_jobs WHERE domain='national_budget'")) == "unknown"
        assert connection.scalar(text("SELECT count(*) FROM unrelated_effects")) == 1
        with engine.connect() as other:
            assert other.scalar(text("SELECT count(*) FROM unrelated_effects")) == 0
        outer.rollback()
        with engine.connect() as other:
            assert other.scalar(text("SELECT count(*) FROM unrelated_effects")) == 0
            assert other.scalar(text("SELECT count(*) FROM entities")) == 0
    finally:
        caller.close()
        connection.close()
        engine.dispose()


def test_refused_second_bootstrap_preserves_supplied_connection_reference_rows(
    db_session, seed_country, monkeypatch
):
    load_builtin_domains()
    monkeypatch.setattr(bootstrap, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr(bootstrap, "_seed_national_data", lambda *a, **k: None)

    def failed_budget(**kwargs):
        raise RuntimeError("Inert budget failed; the claim must stay retained")

    monkeypatch.setitem(REGISTRY._handlers, "national_budget", failed_budget)
    bootstrap.initialize_reference_data(force=True)
    entities = db_session.scalars(select(Entity).where(Entity.type == EntityType.COUNTY)).all()
    assert len(entities) == 47
    expected = {row.id for row in entities}
    bootstrap.initialize_reference_data()
    assert {row.id for row in entities} == expected
    assert {row.id for row in db_session.scalars(select(Entity).where(Entity.type == EntityType.COUNTY))} == expected
    failures = db_session.scalars(select(IngestionJob).where(
        IngestionJob.domain == "national_budget", IngestionJob.status == IngestionStatus.FAILED)).all()
    assert len(failures) == 2
    assert failures[-1].meta["ownership_refused"] is True


@pytest.mark.parametrize("fault", [None, "errors", "wrong_domain", "dry_run", "bool_count", "negative_count"])
def test_current_reference_database_records_truthful_budget_status(
    db_session, monkeypatch, fault
):
    from seeding.types import DomainRunResult
    load_builtin_domains()
    monkeypatch.setattr(bootstrap, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr(bootstrap, "_seed_national_data", lambda *a, **k: None)

    def inert_budget(**kwargs):
        result = DomainRunResult(domain="national_budget", items_processed=1)
        if fault == "errors":
            result.errors = ["Inert reported error"]
        elif fault == "wrong_domain":
            result.domain = "audits"
        elif fault == "dry_run":
            result.dry_run = True
        elif fault == "bool_count":
            result.items_processed = True
        elif fault == "negative_count":
            result.items_processed = -1
        return result

    monkeypatch.setitem(REGISTRY._handlers, "national_budget", inert_budget)
    bootstrap.initialize_reference_data(force=True)
    assert db_session.query(Entity).filter(Entity.type == EntityType.COUNTY).count() == 47
    row = db_session.scalars(select(IngestionJob).where(IngestionJob.domain == "national_budget")).one()
    assert row.status == (IngestionStatus.FAILED if fault else IngestionStatus.COMPLETED)
    reference = db_session.scalars(select(IngestionJob).where(IngestionJob.domain == bootstrap.BOOTSTRAP_DOMAIN)).one()
    assert reference.meta["national_budget"]["status"] == row.status.value
    assert reference.meta["national_budget"]["ownership_retained"] is True
    assert row.meta["outer_commit_pending"] is True
