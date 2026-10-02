"""#347: exercise destructive supersession through the real CLI transaction."""

import argparse
import copy
import os
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from models import (
    Base,
    Country,
    DocumentType,
    EconomicIndicator,
    IngestionJob,
    IngestionStatus,
    SourceDocument,
)
from seeding import cli, freshness
from seeding.config import SeedingSettings
from seeding.domains import economic_indicators as domain
from seeding.domains.economic_indicators.fetcher import EconomicPayload


@pytest.fixture
def lineage_database():
    raw = os.environ.get("ROUND16_SESSION9_TEST_DATABASE_URL")
    if not raw:
        # The default suite still executes the regression using a durable local
        # SQLite database; the incident rehearsal explicitly supplies PostgreSQL.
        from tempfile import TemporaryDirectory

        scratch = TemporaryDirectory(prefix="inflation-lineage-")
        raw = f"sqlite:///{scratch.name}/lineage.sqlite"
    else:
        scratch = None
        url = make_url(raw)
        assert url.host == "127.0.0.1" and url.database == "round16_session9"
        assert url.port == 5479 and url.username == "round16_session9"
    engine = create_engine(raw)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(
            Country(
                name="Synthetic Kenya",
                iso_code="KE",
                currency="KES",
                timezone="Africa/Nairobi",
                default_locale="en",
            )
        )
        db.commit()
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
        if scratch:
            scratch.cleanup()


def _image(row):
    """Independent expected DB image, using physical column names."""
    result = {}
    for attr in inspect(type(row)).column_attrs:
        value = getattr(row, attr.key)
        if isinstance(value, (datetime, Decimal)):
            value = value.isoformat() if isinstance(value, datetime) else str(value)
        elif hasattr(value, "value"):
            value = value.value
        result[attr.columns[0].name] = copy.deepcopy(value)
    return result


def _seed(factory, *, sourced=False, bootstrap=False):
    with factory() as db:
        source = SourceDocument(
            country_id=db.query(Country).one().id,
            publisher="Synthetic alternate publisher",
            title="Synthetic fiscal-year inflation table",
            url="https://example.invalid/synthetic-inflation.pdf",
            fetch_date=datetime(2024, 8, 1),
            doc_type=DocumentType.REPORT,
            md5="a" * 32,
            meta={"edition": "synthetic only", "table": "Table 2"},
        )
        db.add(source)
        db.flush()
        row = EconomicIndicator(
            indicator_type="inflation_rate",
            indicator_date=datetime(2024, 6, 30),
            value=Decimal("4.60"),
            unit="percent",
            confidence=Decimal("0.77"),
            source_document_id=source.id if sourced else None,
            source_page=2 if sourced else None,
            page_ref="p.2 Table 2" if sourced else None,
            source_hash="b" * 64 if sourced else None,
            meta=(
                {
                    "measure": "CPI inflation, fiscal-year average",
                    "period": "FY2023/24",
                    "bootstrap": bootstrap,
                }
                if sourced
                else {"bootstrap": bootstrap}
            ),
            created_at=datetime(2024, 8, 2),
        )
        db.add(row)
        db.commit()
        return row.id, _image(row), _image(source)


def _run(monkeypatch, factory, *, dry=False, expected_exit=0):
    monkeypatch.setattr(cli, "SessionLocal", factory)
    monkeypatch.setattr(domain, "create_http_client", lambda settings: _Client())

    def payload(*args):
        freshness.mark_live("economic_indicators", detail="synthetic WB response")
        return EconomicPayload(
            records=[
                {
                    "indicator_type": "inflation_rate",
                    "date": "2024-12-31",
                    "value": 4.5,
                    "unit": "percent",
                    "publisher": "World Bank",
                    "measure": "CPI inflation, annual average",
                    "source_url": "https://example.invalid/synthetic-wb-series",
                }
            ],
            coverage={"inflation_rate": {"2023-12-31", "2024-12-31", "2025-12-31"}},
        )

    monkeypatch.setattr(domain.fetcher, "fetch_economic_payload", payload)
    args = argparse.Namespace(
        domain=["economic_indicators"], all=False, since=None, dry_run=dry
    )
    settings = SeedingSettings(
        _env_file=None, total_timeout_seconds=0, http_cache_enabled=False
    )
    assert cli.run_seed_command(args, settings) == expected_exit


class _Client:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.mark.parametrize("bootstrap", [False, True])
def test_cli_preserves_source_backed_alternative_at_non_calendar_date(
    lineage_database, monkeypatch, bootstrap
):
    factory = lineage_database
    row_id, before, source_before = _seed(factory, sourced=True, bootstrap=bootstrap)
    _run(monkeypatch, factory)
    # A new session proves that commit/restart retains every original field.
    with factory() as db:
        row = db.get(EconomicIndicator, row_id)
        assert (
            row is not None
        ), "calendar coverage deleted a source-backed fiscal-year observation"
        assert _image(row) == before
        assert _image(db.get(SourceDocument, row.source_document_id)) == source_before
        job = db.query(IngestionJob).one()
        assert job.meta["superseded_rows_removed"] == []
        assert any(
            "source review" in error and str(row_id) in error for error in job.errors
        )
        assert db.query(EconomicIndicator).count() == 2  # WB progress also committed


def test_cli_retirement_retains_full_before_image_in_same_committed_job(
    lineage_database, monkeypatch
):
    factory = lineage_database
    row_id, before, _ = _seed(factory, bootstrap=True)
    _run(monkeypatch, factory)
    with factory() as db:
        assert db.get(EconomicIndicator, row_id) is None
        job = db.query(IngestionJob).one()
        (receipt,) = job.meta["superseded_rows_removed"]
        assert receipt["before_image"] == before
        assert receipt["id"] == row_id and receipt["stored_value"] == "4.60"
        assert job.errors == [] and not job.dry_run


def test_dry_run_rolls_back_retirement_but_keeps_explicit_dry_receipt(
    lineage_database, monkeypatch
):
    factory = lineage_database
    row_id, before, _ = _seed(factory, bootstrap=True)
    _run(monkeypatch, factory, dry=True)
    with factory() as db:
        assert _image(db.get(EconomicIndicator, row_id)) == before
        job = db.query(IngestionJob).one()
        assert job.dry_run
        (receipt,) = job.meta["superseded_rows_removed"]
        assert receipt["before_image"] == before
        assert db.query(EconomicIndicator).count() == 1


@pytest.mark.parametrize(
    "metadata",
    [
        {"bootstrap": True},
        {
            "bootstrap": True,
            "statistical_basis": "fiscal-year CPI average",
            "fiscal_year": "FY2023/24",
        },
        {},
    ],
)
def test_bootstrap_flag_cannot_authorize_retiring_source_document_evidence(
    lineage_database, monkeypatch, metadata
):
    factory = lineage_database
    row_id, _, _ = _seed(factory, sourced=True)
    with factory() as db:
        row = db.get(EconomicIndicator, row_id)
        row.meta = metadata
        row.source_page = row.page_ref = row.source_hash = None
        db.commit()
        before = _image(row)
    _run(monkeypatch, factory)
    with factory() as db:
        row = db.get(EconomicIndicator, row_id)
        assert row is not None
        assert _image(row) == before
        assert db.query(IngestionJob).one().errors


@pytest.mark.parametrize(
    "metadata",
    [
        {
            "publisher": "Synthetic alternate publisher",
            "statistical_basis": "fiscal-year CPI average",
            "fiscal_year": "FY2023/24",
        },
        {"measure": ""},
        {"unknown": None},
        ["unknown legacy evidence"],
        "unknown legacy evidence",
    ],
)
def test_unknown_or_malformed_metadata_is_preserved_until_source_review(
    lineage_database, monkeypatch, metadata
):
    factory = lineage_database
    row_id, _, _ = _seed(factory)
    with factory() as db:
        row = db.get(EconomicIndicator, row_id)
        row.meta = metadata
        db.commit()
        before = _image(row)
    _run(monkeypatch, factory)
    with factory() as db:
        row = db.get(EconomicIndicator, row_id)
        assert row is not None
        assert _image(row) == before
        job = db.query(IngestionJob).one()
        assert job.errors and job.meta["superseded_rows_removed"] == []


@pytest.mark.parametrize("failure", ["after_deletion", "final_commit"])
def test_failed_transaction_restores_row_and_does_not_commit_retirement_receipt(
    lineage_database, monkeypatch, failure
):
    factory = lineage_database
    row_id, before, _ = _seed(factory, bootstrap=True)
    if failure == "after_deletion":
        original_sweep = domain.writer.remove_superseded_rows

        def failed_sweep(*args, **kwargs):
            removed, _ = original_sweep(*args, **kwargs)
            assert len(removed) == 1
            raise RuntimeError("synthetic failure after deletion")

        monkeypatch.setattr(domain.writer, "remove_superseded_rows", failed_sweep)
        cli_factory = factory
    else:

        class FailFinalCommit(Session):
            def commit(self):
                if self.info.get("running_job_committed"):
                    raise RuntimeError("synthetic final commit failure")
                super().commit()
                self.info["running_job_committed"] = True

        cli_factory = sessionmaker(bind=factory.kw["bind"], class_=FailFinalCommit)

    _run(monkeypatch, cli_factory, expected_exit=1)
    with factory() as db:
        assert _image(db.get(EconomicIndicator, row_id)) == before
        assert db.query(EconomicIndicator).count() == 1
        job = db.query(IngestionJob).one()
        assert job.status == IngestionStatus.FAILED
        assert any("synthetic" in error for error in job.errors)
        assert not job.meta.get("superseded_rows_removed")
