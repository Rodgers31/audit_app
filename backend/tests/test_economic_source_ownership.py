"""Only the dedicated economic domain may write economic observations."""

import importlib
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import bootstrap
import pytest
from models import DocumentType, EconomicIndicator, Entity, EntityType, SourceDocument
from seeding.config import SeedingSettings
from seeding.domains.economic_indicators.parser import parse_economic_payload
from seeding.domains.economic_indicators.writer import persist_economic_records
from seeding.types import DomainRunContext
from services import live_data_fetcher
from services.auto_seeder import AutoSeeder

seeder_module = importlib.import_module("services.auto_seeder")


@pytest.mark.parametrize(
    "day,value,entity,metadata",
    [
        (
            datetime(2025, 1, 31), "155", None,
            {"source": "independent", "measure": "index"},
        ),
        (
            datetime(2025, 1, 31), "0", None,
            {"source": "independent", "measure": "index"},
        ),
        (datetime(2025, 1, 31), "143.08", None, {"source": "fixture", "bootstrap": True}),
        (datetime(2024, 12, 31), "142.47", None, {"source": "fixture", "bootstrap": True}),
        (datetime(2023, 1, 31), "121", None, {"source": "independent"}),
        (datetime(2025, 1, 31), "77", "county", {"source": "county survey"}),
    ],
)
def test_bootstrap_preserves_cpi_identity_and_evidence(
    db_session, seed_country, seed_source_doc, day, value, entity, metadata
):
    county_id = None
    if entity == "county":
        county = Entity(
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name="Test County",
            slug="test-county",
        )
        db_session.add(county)
        db_session.flush()
        county_id = county.id
    independent_doc = SourceDocument(
        country_id=seed_country.id,
        publisher="Synthetic independent publisher",
        title="Synthetic CPI evidence",
        url="https://example.org/synthetic-cpi-evidence",
        fetch_date=datetime(2025, 2, 1),
        doc_type=DocumentType.REPORT,
    )
    db_session.add(independent_doc)
    db_session.flush()
    row = EconomicIndicator(
        indicator_type="CPI",
        indicator_date=day,
        value=Decimal(value),
        unit="index_2009_100",
        entity_id=county_id,
        source_document_id=independent_doc.id,
        source_page=7,
        page_ref="p. 7",
        source_hash="a" * 64,
        confidence=Decimal("0.77"),
        meta=metadata,
    )
    db_session.add(row)
    db_session.flush()
    before = (
        row.id,
        row.value,
        row.unit,
        row.entity_id,
        row.source_document_id,
        row.source_page,
        row.page_ref,
        row.source_hash,
        row.confidence,
        dict(row.meta),
    )

    for _ in range(2):
        bootstrap._seed_economic_indicators(
            db_session, source_document_id=seed_source_doc.id
        )
        db_session.flush()

    assert (
        row.id,
        row.value,
        row.unit,
        row.entity_id,
        row.source_document_id,
        row.source_page,
        row.page_ref,
        row.source_hash,
        row.confidence,
        row.meta,
    ) == before
    assert db_session.query(EconomicIndicator).count() == 1


def test_bootstrap_does_not_fill_absent_cpi_with_literal(db_session, seed_source_doc):
    bootstrap._seed_economic_indicators(
        db_session, source_document_id=seed_source_doc.id
    )
    db_session.flush()
    assert db_session.query(EconomicIndicator).count() == 0


def test_dedicated_cpi_writer_keeps_value_measure_and_source_together(
    db_session, seed_country, seed_source_doc
):
    record = parse_economic_payload(
        [
            {
                "indicator_type": "CPI",
                "date": "2025-01-31",
                "value": "155",
                "unit": "index_2019_100",
                "source_url": "https://example.org/synthetic-cpi-release",
                "source": "Synthetic independent release",
                "publisher": "Synthetic publisher",
                "measure": "index (2019=100)",
            }
        ]
    )
    stats = persist_economic_records(
        db_session,
        record,
        SeedingSettings(),
        DomainRunContext(since=None, dry_run=False),
    )
    db_session.flush()
    assert (stats.created, stats.updated, stats.errors) == (1, 0, [])
    row = db_session.query(EconomicIndicator).one()
    assert row.indicator_type == "cpi"
    source = row.source_document
    assert (row.value, row.unit, row.meta["measure"]) == (
        Decimal("155"),
        "index_2019_100",
        "index (2019=100)",
    )
    assert (source.url, source.publisher) == (
        "https://example.org/synthetic-cpi-release",
        "Synthetic publisher",
    )

    bootstrap._seed_economic_indicators(
        db_session, source_document_id=seed_source_doc.id
    )
    db_session.flush()
    assert db_session.query(EconomicIndicator).count() == 1
    assert (row.value, row.unit, row.source_document_id, row.meta["measure"]) == (
        Decimal("155"),
        "index_2019_100",
        source.id,
        "index (2019=100)",
    )


@pytest.mark.asyncio
async def test_direct_web_economic_refresh_refuses_before_fetch_or_db(monkeypatch):
    seeder = AutoSeeder()
    fetch = AsyncMock(return_value={"fetch_success": True, "gdp_kes": 123})
    monkeypatch.setattr(seeder.aggregator, "fetch_all_economic_data", fetch, raising=False)

    def unexpected_db():
        raise AssertionError("web economic refresh opened a database session")

    monkeypatch.setattr(seeder_module, "SessionLocal", unexpected_db)
    with pytest.raises(ValueError, match="dedicated seeding runner"):
        await seeder._seed_economic_live()
    with pytest.raises(ValueError, match="dedicated seeding runner"):
        await seeder._seed_domain("economic")
    fetch.assert_not_called()


@pytest.mark.asyncio
async def test_web_refresh_schedule_and_status_do_not_promise_economic(monkeypatch):
    seeder = AutoSeeder()
    run = AsyncMock()
    monkeypatch.setattr(seeder, "_seed_domain", run)
    monkeypatch.setattr(seeder_module.asyncio, "sleep", AsyncMock())
    await seeder.seed_all_domains()
    await seeder._check_and_refresh()
    dispatched = [call.args[0] for call in run.call_args_list]
    assert "economic" not in dispatched
    status = seeder.get_status()
    assert "economic" not in status["last_refresh"]
    assert "economic" not in status["next_refresh"]
    assert "economic_indicators" in status["external_job_owner"]["domains"]


def test_shipping_backend_has_no_root_economic_extractor_dependency():
    """The Docker build context is backend/; its web fetcher must stay inside it."""
    backend = Path(live_data_fetcher.__file__).resolve().parents[1]
    assert (backend / "Dockerfile").exists()
    assert (backend / "Dockerfile.prod").exists()
    assert not (backend / "extractors").exists()
    assert not hasattr(live_data_fetcher.LiveDataAggregator, "fetch_all_economic_data")
