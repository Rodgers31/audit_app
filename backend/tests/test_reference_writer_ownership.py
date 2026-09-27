"""Bootstrap and web refresh may not relabel a source-owned observation."""
import asyncio
import importlib
from copy import deepcopy
from unittest.mock import AsyncMock

import bootstrap
import pytest
from models import Entity, EntityType, PopulationData
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def reference_db(db_session, seed_country, seed_source_doc, monkeypatch):
    factory = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr(bootstrap, "SessionLocal", factory)
    monkeypatch.setattr(bootstrap, "_seed_national_data", lambda *a, **k: None)
    monkeypatch.setattr(bootstrap, "_seed_national_budget", lambda *a, **k: None)
    monkeypatch.setattr(
        bootstrap, "bootstrap_provenance", lambda s: {"is_stale": False}
    )
    payload = {
        "county_data": {
            "Mandera": {
                "population": 1200890,
                "governor": "Fixture official",
                "county_type": "modelled",
                "last_updated": "2025-01-01T00:00:00",
            }
        }
    }
    monkeypatch.setattr(bootstrap, "_load_json", lambda path: payload)
    provenance = {
        "source": "Council of Governors",
        "source_url": "https://cog.go.ke/current-governors/",
        "source_document_id": seed_source_doc.id,
        "fetched_at": "2026-09-27T00:00:00Z",
    }
    county = Entity(
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Mandera County",
        slug="mandera-county",
        meta={
            "governor": "Sourced official",
            "governor_provenance": provenance,
            "unrelated": "preserve",
        },
    )
    db_session.add(county)
    db_session.flush()
    pop = PopulationData(
        entity_id=county.id,
        year=2019,
        total_population=867457,
        source_document_id=seed_source_doc.id,
        page_ref="p. 17",
        source_page=17,
        meta={"table": "2.2"},
    )
    db_session.add(pop)
    db_session.commit()
    return county, pop, factory


@pytest.mark.parametrize("force", [False, True])
def test_bootstrap_keeps_official_and_evidence_together(
    db_session, reference_db, force
):
    county, _, _ = reference_db
    before = deepcopy(county.meta)
    bootstrap.initialize_reference_data(force=force)
    db_session.refresh(county)
    assert county.meta["metrics"]  # The actual partial/forced county loop ran.
    assert county.meta["governor"] == before["governor"]
    assert county.meta["governor_provenance"] == before["governor_provenance"]
    assert county.meta["unrelated"] == "preserve"


def test_bootstrap_cannot_replace_census_with_budget_citation(db_session, reference_db):
    _, pop, _ = reference_db
    before = (
        pop.total_population,
        pop.source_document_id,
        pop.page_ref,
        pop.source_page,
        deepcopy(pop.meta),
    )
    bootstrap.initialize_reference_data()
    db_session.refresh(pop)
    assert (
        pop.total_population,
        pop.source_document_id,
        pop.page_ref,
        pop.source_page,
        pop.meta,
    ) == before


def test_bootstrap_does_not_recreate_retired_profile(db_session, reference_db):
    county, _, _ = reference_db
    bootstrap.initialize_reference_data()
    db_session.refresh(county)
    assert "economic_profile" not in county.meta


def test_web_population_dispatch_refuses_before_fetch_or_write(
    db_session, reference_db, monkeypatch
):
    _, pop, factory = reference_db
    module = importlib.import_module("services.auto_seeder")
    monkeypatch.setattr(module, "SessionLocal", factory)
    seeder = module.AutoSeeder()
    fetch = AsyncMock(
        return_value={
            "fetch_success": True,
            "census_year": 2019,
            "counties": [{"county": "Mandera", "total_population": 1200890}],
        }
    )
    monkeypatch.setattr(
        seeder.aggregator, "fetch_all_population_data", fetch, raising=False
    )
    with pytest.raises(ValueError, match="dedicated"):
        asyncio.run(seeder._seed_domain("population"))
    fetch.assert_not_called()
    db_session.refresh(pop)
    assert pop.total_population == 867457


def test_national_bootstrap_preserves_world_bank_series(
    db_session, seed_country, seed_source_doc
):
    row = PopulationData(
        entity_id=None,
        year=2019,
        total_population=51202827,
        male_population=25485390,
        female_population=25717437,
        meta={"source": "World Bank Development Indicators (2019)"},
    )
    db_session.add(row)
    db_session.commit()
    before = (row.total_population, row.source_document_id, deepcopy(row.meta))
    period = bootstrap._ensure_fiscal_period(db_session, seed_country.id)
    bootstrap._seed_national_data(db_session, country=seed_country, period=period)
    db_session.flush()
    db_session.refresh(row)
    assert (row.total_population, row.source_document_id, row.meta) == before
    assert (
        db_session.query(Entity).filter(Entity.type == EntityType.NATIONAL).count() == 1
    )
    assert db_session.query(PopulationData).count() == 1
