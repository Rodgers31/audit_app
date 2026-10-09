"""Supplied SQLite sessions are test transactions, not PostgreSQL authority."""
import pytest
from sqlalchemy import select

import bootstrap
from models import Entity, EntityType, IngestionJob, IngestionStatus
from seeding.registries import REGISTRY, load_builtin_domains


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
    assert reference.meta["national_budget"]["ownership_retained"] is bool(fault)
