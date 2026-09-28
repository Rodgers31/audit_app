"""The population domain consumes publisher observations without fixture fallback."""
from contextlib import contextmanager
from copy import deepcopy

import httpx
from models import PopulationData
from seeding.config import SeedingSettings
from seeding.domains import population
from seeding.domains.population import census_counties
from seeding.types import DomainRunContext

WB_SOURCE = "https://data.worldbank.org/indicator/SP.POP.TOTL?locations=KE"


def run_domain(
    db_session,
    monkeypatch,
    *,
    enabled=True,
    fail=False,
    values=None,
    census_processed=0
):
    values = values or {
        "SP.POP.TOTL": 51202827,
        "SP.POP.TOTL.MA.IN": 25485390,
        "SP.POP.TOTL.FE.IN": 25717437,
    }
    requested = []

    class Client:
        def get(self, url, **kwargs):
            requested.append(url)
            if fail:
                raise httpx.ConnectError("publisher unavailable")
            code = url.rsplit("/", 1)[-1]
            return httpx.Response(
                200, json=[{}, [{"date": "2019", "value": values.get(code)}]]
            )

    @contextmanager
    def factory(settings):
        yield Client()

    monkeypatch.setattr(population, "create_http_client", factory)
    monkeypatch.setattr(
        census_counties,
        "load_census_population",
        lambda *a, **k: census_counties.CensusLoadStats(
            processed=census_processed,
            quarantine_reason=None if census_processed else "test_no_pdf",
        ),
    )
    result = population.run(
        db_session,
        SeedingSettings(enrich_with_worldbank=enabled),
        DomainRunContext(since=None, dry_run=False),
    )
    db_session.commit()
    return result, requested


def test_world_bank_refresh_replaces_mixed_bootstrap_record(
    db_session, seed_country, seed_source_doc, monkeypatch
):
    row = PopulationData(
        year=2019,
        total_population=47564296,
        source_document_id=seed_source_doc.id,
        page_ref="old p. 17",
        source_page=17,
        meta={"source": "World Bank Development Indicators (2019)", "bootstrap": True},
    )
    db_session.add(row)
    db_session.commit()
    result, requests = run_domain(db_session, monkeypatch)
    db_session.refresh(row)
    assert result.items_updated == 1
    assert len(requests) == 7
    assert row.total_population == 51202827
    assert row.male_population + row.female_population == row.total_population
    assert row.meta == {
        "source": "World Bank Development Indicators (2019)",
        "source_url": WB_SOURCE,
        "dataset_id": "SP.POP.TOTL",
    }
    assert (
        row.source_document_id is None
        and row.page_ref is None
        and row.source_page is None
    )


def test_world_bank_disabled_preserves_existing_observation(
    db_session, seed_country, monkeypatch
):
    row = PopulationData(
        year=2019, total_population=47564296, meta={"source": "existing"}
    )
    db_session.add(row)
    db_session.commit()
    before = deepcopy(row.meta)
    result, requests = run_domain(db_session, monkeypatch, enabled=False)
    db_session.refresh(row)
    assert requests == []
    assert result.items_created == result.items_updated == 0
    assert row.total_population == 47564296 and row.meta == before


def test_world_bank_unavailable_never_falls_back(db_session, seed_country, monkeypatch):
    result, requests = run_domain(db_session, monkeypatch, fail=True)
    assert requests  # The publisher was actually attempted.
    assert result.items_created == result.items_updated == 0
    assert db_session.query(PopulationData).count() == 0


def test_sex_series_without_total_cannot_create_population(
    db_session, seed_country, monkeypatch
):
    result, _ = run_domain(
        db_session, monkeypatch, values={"SP.POP.TOTL.MA.IN": 25485390}
    )
    assert result.items_created == 0
    assert db_session.query(PopulationData).count() == 0


def test_refused_national_series_is_not_reported_live(
    db_session, seed_country, monkeypatch
):
    from seeding import freshness

    result, _ = run_domain(
        db_session, monkeypatch, values={"SP.POP.TOTL": 82}, census_processed=47
    )
    assert result.errors
    assert freshness.get("population")["mode"] == freshness.PARTIAL


def test_both_accepted_sources_are_reported_live(db_session, seed_country, monkeypatch):
    from seeding import freshness

    result, _ = run_domain(db_session, monkeypatch, census_processed=47)
    assert not result.errors
    assert freshness.get("population")["mode"] == freshness.LIVE
