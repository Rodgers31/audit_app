"""Tests for the population seeding domain."""

from __future__ import annotations

from typing import Iterator

import httpx
import pytest
from models import Base, Country, Entity, EntityType, PopulationData
from seeding.config import SeedingSettings
from seeding.domains.population import run as run_population_domain
from seeding.types import DomainRunContext
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover - dialect shim
    return "TEXT"


@pytest.fixture()
def sqlite_session(tmp_path) -> Iterator[Session]:
    engine = create_engine(f"sqlite:///{tmp_path/'population.db'}")
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def http_mock(monkeypatch):
    state = {
        "payload": {"records": []},
        "status": 200,
        "calls": 0,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        return httpx.Response(
            state["status"],
            json=state["payload"],
            headers={"content-type": "application/json"},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr("seeding.http_client.httpx.Client", client_factory)
    return state


def _bootstrap_entities(session: Session) -> None:
    country = Country(
        iso_code="KEN",
        name="Kenya",
        currency="KES",
        timezone="Africa/Nairobi",
        default_locale="en-KE",
    )
    session.add(country)
    session.flush()

    session.add(
        Entity(
            country_id=country.id,
            type=EntityType.COUNTY,
            canonical_name="Nairobi City",
            slug="nairobi",
            alt_names=["Nairobi"],
            meta={},
        )
    )
    session.commit()


def _build_settings(
    tmp_path, url: str, *, enrich_with_worldbank: bool = False
) -> SeedingSettings:
    settings = SeedingSettings(
        storage_path=tmp_path / "storage",
        cache_path=tmp_path / "cache",
        log_path=tmp_path / "logs" / "seed.log",
        population_dataset_url=url,
        retry_backoff=0.01,
        max_retries=2,
        # Disable live enrichment in unit tests so the mock transport
        # only serves the test fixture payload (not World Bank API calls).
        enrich_with_worldbank=enrich_with_worldbank,
        live_pdf_fetch_enabled=False,
    )
    settings.ensure_directories()
    return settings


def test_population_domain_persists_records(sqlite_session, http_mock, tmp_path):
    _bootstrap_entities(sqlite_session)
    http_mock["payload"] = {
        "records": [
            {
                "level": "national",
                "entity": "Kenya",
                "year": 2023,
                "total_population": 54000000,
                "male_population": 26000000,
                "female_population": 28000000,
                "dataset_id": "pop-2023",
            },
            {
                "level": "county",
                "entity": "Nairobi City",
                "entity_slug": "nairobi",
                "year": 2023,
                "total_population": 4500000,
                "male_population": 2200000,
                "female_population": 2300000,
                "dataset_id": "pop-2023",
            },
        ]
    }
    http_mock["calls"] = 0

    settings = _build_settings(tmp_path, "https://example.test/population")
    context = DomainRunContext(since=None, dry_run=False)

    result = run_population_domain(sqlite_session, settings, context)
    sqlite_session.commit()

    assert result.items_processed == 2
    assert result.items_created == 2
    assert result.metadata["skipped"] == 0
    assert http_mock["calls"] == 1

    rows = sqlite_session.execute(select(PopulationData)).scalars().all()
    assert len(rows) == 2
    national = next(row for row in rows if row.entity_id is None)
    county = next(row for row in rows if row.entity_id is not None)
    assert national.total_population == 54000000
    assert county.total_population == 4500000


def test_population_domain_skips_unknown_entity(sqlite_session, http_mock, tmp_path):
    _bootstrap_entities(sqlite_session)
    http_mock["payload"] = {
        "records": [
            {
                "level": "county",
                "entity": "Unknown County",
                "entity_slug": "unknown",
                "year": 2023,
                "total_population": 100000,
                "dataset_id": "pop-2023",
            }
        ]
    }
    http_mock["calls"] = 0

    settings = _build_settings(tmp_path, "https://example.test/population")
    context = DomainRunContext(since=None, dry_run=False)

    result = run_population_domain(sqlite_session, settings, context)

    assert result.items_processed == 1
    assert result.items_created == 0
    assert result.metadata["skipped"] == 1
    assert result.errors
    assert http_mock["calls"] == 1

    rows = sqlite_session.execute(select(PopulationData)).scalars().all()
    assert rows == []
