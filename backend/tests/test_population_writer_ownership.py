"""Population writers must replace values and evidence as one observation."""

import hashlib
from datetime import datetime, timezone

import httpx
import pytest
from models import (
    DocumentType,
    Entity,
    EntityType,
    Extraction,
    PopulationData,
    SourceDocument,
)
from seeding.config import SeedingSettings
from seeding.domains.population import census_counties, run
from seeding.domains.population.parser import PopulationRecord, parse_population_payload
from seeding.domains.population.writer import persist_population_records
from seeding.extractors.knbs_census_population import (
    KENYAN_COUNTIES,
    PUBLISHED_NATIONAL_TOTAL,
    CensusPopulation,
    CountyPopulation,
)
from seeding.types import DomainRunContext
from sqlalchemy import select


@pytest.fixture()
def population_seed(db_session, seed_country, seed_entity):
    doc = SourceDocument(
        country_id=seed_country.id,
        publisher="Kenya National Bureau of Statistics",
        title="Previous population publication",
        url="https://www.knbs.or.ke/previous-population.pdf",
        fetch_date=datetime.now(timezone.utc),
        doc_type=DocumentType.REPORT,
    )
    db_session.add(doc)
    db_session.flush()
    extraction = Extraction(
        source_document_id=doc.id,
        page_number=17,
        extractor="knbs_census_population",
        extracted_json={"table": "2.2"},
        confidence=1.0,
    )
    db_session.add(extraction)
    db_session.flush()

    def make_row(*, national=False):
        row = PopulationData(
            entity_id=None if national else seed_entity.id,
            year=2019,
            total_population=47_564_296 if national else 4_397_073,
            male_population=23_548_056 if national else 2_192_452,
            female_population=24_014_716 if national else 2_204_376,
            source_document_id=doc.id,
            source_page=17,
            extraction_id=extraction.id,
            page_ref="p. 17",
            source_hash="a" * 64,
            confidence_score=1.0,
            publishable=True,
            meta={
                "source": "Kenya Census 2019",
                "source_url": doc.url,
                "table": "2.2",
                "intersex_population": 1_524 if national else 245,
            },
        )
        db_session.add(row)
        db_session.flush()
        return row

    return make_row


def _snapshot(row):
    return {
        name: getattr(row, name)
        for name in (
            "total_population",
            "male_population",
            "female_population",
            "meta",
            "source_document_id",
            "source_page",
            "extraction_id",
            "page_ref",
            "source_hash",
            "confidence_score",
            "publishable",
        )
    }


def _settings(tmp_path, *, worldbank=False):
    settings = SeedingSettings(
        storage_path=tmp_path / "storage",
        cache_path=tmp_path / "cache",
        log_path=tmp_path / "logs" / "seed.log",
        population_dataset_url="https://fixture.test/population.json",
        enrich_with_worldbank=worldbank,
        max_retries=1,
        live_pdf_fetch_enabled=False,
    )
    settings.ensure_directories()
    return settings


def _network(monkeypatch, handler):
    original_client = httpx.Client
    transport = httpx.MockTransport(handler)

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr("seeding.http_client.httpx.Client", client_factory)


def _refuse_census(monkeypatch):
    monkeypatch.setattr(
        census_counties,
        "load_census_population",
        lambda *a, **k: census_counties.CensusLoadStats(
            quarantine_reason="census_pdf_not_downloaded",
            errors=["Synthetic census fetch refusal"],
        ),
    )


@pytest.mark.parametrize("national", [False, True], ids=["county", "national"])
def test_population_domain_does_not_replace_sourced_rows_with_fixture(
    db_session, population_seed, monkeypatch, tmp_path, national
):
    row = population_seed(national=national)
    before = _snapshot(row)
    fixture_record = {
        "level": "national" if national else "county",
        "entity": "Kenya" if national else "Nairobi",
        "entity_slug": "nairobi",
        "year": 2019,
        "total_population": 50_000_000 if national else 4_900_000,
        "source": "unverified fixture",
    }
    _network(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"records": [fixture_record]}, request=request
        ),
    )
    _refuse_census(monkeypatch)

    run(db_session, _settings(tmp_path), DomainRunContext(None, False))
    db_session.flush()
    db_session.expire(row)

    assert _snapshot(row) == before


def test_generic_population_writer_refuses_county_even_with_worldbank_label(
    db_session, population_seed
):
    row = population_seed()
    before = _snapshot(row)
    records = parse_population_payload(
        [
            {
                "level": "county",
                "entity_slug": "nairobi",
                "entity": "Nairobi",
                "year": 2019,
                "total_population": 4_900_000,
                "source": "World Bank Development Indicators (2019)",
                "source_url": "https://data.worldbank.org/indicator/SP.POP.TOTL?locations=KE",
            }
        ]
    )

    stats = persist_population_records(
        db_session, records, DomainRunContext(None, False)
    )
    db_session.flush()
    db_session.expire(row)

    assert _snapshot(row) == before
    assert stats.updated == 0
    assert stats.skipped == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("total_population", True),
        ("total_population", -1),
        ("total_population", float("nan")),
        ("total_population", float("inf")),
        ("total_population", 52_000_000.25),
        ("total_population", None),
        ("year", True),
        ("year", -1),
        ("year", float("nan")),
        ("year", float("inf")),
        ("year", 2019.25),
        ("year", None),
        ("male_population", True),
        ("male_population", -1),
        ("male_population", float("nan")),
        ("male_population", float("inf")),
        ("male_population", 25_000_000.25),
        ("female_population", -1),
        ("meta", None),
        ("meta", []),
        ("meta", "World Bank"),
    ],
)
def test_generic_writer_refuses_malformed_observations_without_mutation(
    db_session, population_seed, field, value
):
    row = population_seed(national=True)
    before = _snapshot(row)
    payload = {
        "level": "national",
        "entity_slug": None,
        "entity_name": "Kenya",
        "year": 2019,
        "total_population": 52_000_000,
        "male_population": 25_000_000,
        "female_population": 27_000_000,
        "meta": {
            "source": "World Bank Development Indicators (2019)",
            "dataset_id": "SP.POP.TOTL",
            "source_url": "https://data.worldbank.org/indicator/SP.POP.TOTL?locations=KE",
        },
    }
    payload[field] = value

    stats = persist_population_records(
        db_session, [PopulationRecord(**payload)], DomainRunContext(None, False)
    )

    assert _snapshot(row) == before
    assert stats.created == 0
    assert stats.updated == 0
    assert stats.skipped == 1
    assert stats.errors


def test_generic_writer_refuses_sex_components_exceeding_total_without_mutation(
    db_session, population_seed
):
    row = population_seed(national=True)
    before = _snapshot(row)
    record = PopulationRecord(
        level="national",
        entity_slug=None,
        entity_name="Kenya",
        year=2019,
        total_population=50_000_000,
        male_population=30_000_000,
        female_population=30_000_000,
        meta={
            "dataset_id": "SP.POP.TOTL",
            "source_url": "https://data.worldbank.org/indicator/SP.POP.TOTL?locations=KE",
        },
    )

    stats = persist_population_records(
        db_session, [record], DomainRunContext(None, False)
    )

    assert _snapshot(row) == before
    assert stats.updated == stats.created == 0
    assert stats.skipped == 1
    assert stats.errors


@pytest.mark.parametrize(
    "total,year",
    [(True, "2019"), (-1, "2019"), (52_000_000.25, "2019"), (52_000_000, 2019.25)],
)
def test_worldbank_transport_cannot_coerce_bad_observation_into_sourced_value(
    db_session, population_seed, monkeypatch, tmp_path, total, year
):
    row = population_seed(national=True)
    before = _snapshot(row)

    def response(request):
        if request.url.host != "api.worldbank.org":
            return httpx.Response(200, json={"records": []}, request=request)
        indicator = request.url.path.rsplit("/", 1)[-1]
        value = total if indicator == "SP.POP.TOTL" else None
        return httpx.Response(
            200, json=[{}, [{"date": year, "value": value}]], request=request
        )

    _network(monkeypatch, response)
    _refuse_census(monkeypatch)

    result = run(
        db_session, _settings(tmp_path, worldbank=True), DomainRunContext(None, False)
    )

    assert _snapshot(row) == before
    assert result.items_updated == 0
    assert result.items_created == 0


def test_valid_observation_preserves_reported_zero_sex_count(
    db_session, population_seed
):
    row = population_seed(national=True)
    records = parse_population_payload(
        [
            {
                "level": "national",
                "entity": "Kenya",
                "year": 2019,
                "total_population": 52_000_000,
                "male_population": 0,
                "female_population": 52_000_000,
                "dataset_id": "SP.POP.TOTL",
                "source": "World Bank Development Indicators (2019)",
                "source_url": "https://data.worldbank.org/indicator/SP.POP.TOTL?locations=KE",
            }
        ]
    )

    stats = persist_population_records(
        db_session, records, DomainRunContext(None, False)
    )
    db_session.flush()
    db_session.expire(row)

    assert stats.updated == 1
    assert row.total_population == 52_000_000
    assert row.male_population == 0
    assert row.female_population == 52_000_000


@pytest.mark.parametrize("include_sexes", [True, False], ids=["full", "total_only"])
def test_worldbank_update_replaces_stale_observation_and_evidence(
    db_session, population_seed, monkeypatch, tmp_path, include_sexes
):
    row = population_seed(national=True)
    row.confidence = 0.25
    values = {"SP.POP.TOTL": 52_000_000}
    if include_sexes:
        values.update(
            {"SP.POP.TOTL.MA.IN": 25_000_000, "SP.POP.TOTL.FE.IN": 27_000_000}
        )

    def response(request):
        if request.url.host == "api.worldbank.org":
            indicator = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(
                200,
                json=[{}, [{"date": "2019", "value": values.get(indicator)}]],
                request=request,
            )
        return httpx.Response(200, json={"records": []}, request=request)

    _network(monkeypatch, response)
    _refuse_census(monkeypatch)
    result = run(
        db_session, _settings(tmp_path, worldbank=True), DomainRunContext(None, False)
    )
    db_session.flush()
    db_session.expire(row)

    assert result.items_updated == 1
    assert row.total_population == 52_000_000
    assert row.male_population == (25_000_000 if include_sexes else None)
    assert row.female_population == (27_000_000 if include_sexes else None)
    assert row.meta["source"] == "World Bank Development Indicators (2019)"
    assert (
        row.meta["source_url"]
        == "https://data.worldbank.org/indicator/SP.POP.TOTL?locations=KE"
    )
    assert "table" not in row.meta
    assert "intersex_population" not in row.meta
    assert row.source_document_id is None
    assert row.source_page is None
    assert row.extraction_id is None
    assert row.page_ref is None
    assert row.source_hash is None
    assert float(row.confidence) == 1.0
    assert row.publishable is False


def test_census_writer_quarantines_unrecognized_source_and_entity_codes(
    db_session, seed_country, tmp_path, monkeypatch
):
    unknown = Entity(
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Unknown County",
        slug="unknown-county",
    )
    db_session.add(unknown)
    pdf_path = tmp_path / "census.pdf"
    pdf_path.write_bytes(b"synthetic invalid census result")
    doc = SourceDocument(
        country_id=seed_country.id,
        publisher=census_counties.PUBLISHER,
        title=census_counties.CENSUS_TITLE,
        url=census_counties.CENSUS_VOLUME_I_URL,
        file_path=str(pdf_path),
        fetch_date=datetime.now(timezone.utc),
        doc_type=DocumentType.REPORT,
    )
    db_session.add(doc)
    db_session.flush()
    monkeypatch.setattr(census_counties, "fetch_document", lambda *a, **k: doc)
    monkeypatch.setattr(
        census_counties,
        "read_census_counties",
        lambda _: CensusPopulation(
            counties=[CountyPopulation("Lost County", 100, 100, 0, 200, 17)],
            national_total=200,
            page=17,
            checks=[],
        ),
    )

    stats = census_counties.load_census_population(
        db_session, None, _settings(tmp_path), country_id=seed_country.id
    )
    db_session.flush()

    assert stats.quarantine_reason == "county_entities_unresolved"
    assert stats.processed == stats.created == stats.updated == 0
    assert db_session.query(PopulationData).count() == 0


@pytest.mark.parametrize(
    "bootstrap_entities", [False, True], ids=["legacy_slugs", "bootstrap_slugs"]
)
def test_census_writer_updates_counties_and_replaces_source_links(
    db_session, seed_country, tmp_path, monkeypatch, bootstrap_entities
):
    if bootstrap_entities:
        import bootstrap

        monkeypatch.setattr(bootstrap, "SessionLocal", lambda: db_session)
        monkeypatch.setattr(db_session, "close", lambda: None)
        monkeypatch.setattr(bootstrap, "_seed_national_data", lambda *a, **k: None)
        monkeypatch.setattr(bootstrap, "_seed_national_budget", lambda *a, **k: None)
        bootstrap.initialize_reference_data(force=True)
        entities = (
            db_session.execute(
                select(Entity)
                .where(Entity.type == EntityType.COUNTY)
                .order_by(Entity.canonical_name)
            )
            .scalars()
            .all()
        )
        assert len(entities) == 47
        assert (
            next(e for e in entities if e.canonical_name == "Mandera County").slug
            == "mandera-009"
        )
        assert all("governor" not in (e.meta or {}) for e in entities)
        assert all("economic_profile" not in (e.meta or {}) for e in entities)
        assert db_session.query(PopulationData).count() == 0
        monkeypatch.setattr(
            bootstrap,
            "_load_json",
            lambda _: pytest.fail(
                "Complete county set must skip reference county writes"
            ),
        )
        bootstrap.initialize_reference_data(force=False)
        assert db_session.query(PopulationData).count() == 0
    else:
        entities = []
        for name in KENYAN_COUNTIES:
            entity = Entity(
                country_id=seed_country.id,
                type=EntityType.COUNTY,
                canonical_name=name,
                slug=name.lower().replace(" ", "-").replace("'", "") + "-county",
            )
            db_session.add(entity)
            entities.append(entity)
    db_session.flush()
    old_row = PopulationData(
        entity_id=entities[0].id,
        year=2019,
        total_population=999_999,
        source_page=3,
        page_ref="p. 3",
        source_hash="a" * 64,
        confidence_score=1.0,
        publishable=True,
        meta={"source": "old fixture"},
    )
    db_session.add(old_row)
    pdf_path = tmp_path / "census.pdf"
    pdf_path.write_bytes(b"synthetic test transport, parser output injected below")
    doc = SourceDocument(
        country_id=seed_country.id,
        publisher=census_counties.PUBLISHER,
        title=census_counties.CENSUS_TITLE,
        url=census_counties.CENSUS_VOLUME_I_URL,
        file_path=str(pdf_path),
        fetch_date=datetime.now(timezone.utc),
        doc_type=DocumentType.REPORT,
    )
    db_session.add(doc)
    db_session.flush()
    share, remainder = divmod(PUBLISHED_NATIONAL_TOTAL, len(KENYAN_COUNTIES))
    counties = []
    for i, name in enumerate(KENYAN_COUNTIES):
        total = share + (remainder if i == 0 else 0)
        counties.append(CountyPopulation(name, total - 3, 2, 1, total, 17))
    result = CensusPopulation(
        counties=counties,
        national_total=PUBLISHED_NATIONAL_TOTAL,
        page=17,
        checks=["all 47 counties present", "sum to the national total"],
    )
    monkeypatch.setattr(census_counties, "fetch_document", lambda *a, **k: doc)
    monkeypatch.setattr(census_counties, "read_census_counties", lambda _: result)

    stats = census_counties.load_census_population(
        db_session, None, _settings(tmp_path), country_id=seed_country.id
    )
    db_session.flush()
    rows = db_session.execute(select(PopulationData)).scalars().all()

    assert stats.processed == 47
    assert stats.created == 46
    assert stats.updated == 1
    assert stats.quarantine_reason is None
    assert sum(row.total_population for row in rows) == PUBLISHED_NATIONAL_TOTAL
    assert all(row.source_document_id == doc.id for row in rows)
    assert all(row.extraction_id is not None for row in rows)
    assert all(row.source_page == 17 and row.page_ref == "p. 17" for row in rows)
    assert all(
        row.meta["source_url"] == census_counties.CENSUS_VOLUME_I_URL for row in rows
    )
    assert all(
        row.source_hash == hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        for row in rows
    )
    assert all(row.publishable is False for row in rows)
    assert old_row.total_population == counties[0].total
    assert "source" not in old_row.meta
