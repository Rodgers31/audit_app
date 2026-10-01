"""#403: selected population and citation must identify the same observation."""
import asyncio
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from models import Base, Country, Entity, Extraction, PopulationData, SourceDocument
from routers import data_provenance, economic
from seeding.domains.population import census_counties

WB_URL = "https://data.worldbank.org/indicator/SP.POP.TOTL?locations=KE"
WB_META = {"source": "World Bank Development Indicators (2019)",
           "dataset_id": "SP.POP.TOTL", "source_url": WB_URL}


@pytest.fixture(params=["sqlite", "postgresql"])
def population_db(request):
    if request.param == "sqlite":
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                               poolclass=StaticPool)
        schema = None
    else:
        raw = os.environ.get("POPULATION_TEST_POSTGRES_URL")
        if not raw:
            pytest.skip("Set POPULATION_TEST_POSTGRES_URL to disposable local PostgreSQL")
        url = make_url(raw)
        assert url.host in {"127.0.0.1", "localhost", "::1"} and not url.query
        schema = "population_403_" + uuid.uuid4().hex
        owner = create_engine(url)
        with owner.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Country(id=1, iso_code="KEN", name="Kenya", currency="KES",
                       timezone="Africa/Nairobi", default_locale="en_KE"))
        db.add(Entity(id=1, country_id=1, type="COUNTY", canonical_name="Nairobi",
                      slug="nairobi"))
        db.commit()
        yield db
    engine.dispose()
    if schema:
        with owner.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        owner.dispose()


@pytest.fixture
def population_client(population_db):
    app = FastAPI()
    app.include_router(data_provenance.router)
    app.include_router(economic.router)
    app.dependency_overrides[data_provenance.get_db] = lambda: population_db
    app.dependency_overrides[economic.get_db] = lambda: population_db
    with TestClient(app) as client:
        yield client


def row(db, **kwargs):
    values = dict(year=2019, total_population=51_202_827, meta=WB_META,
                  confidence=1.0)
    values.update(kwargs)
    item = PopulationData(**values)
    db.add(item)
    db.commit()
    return item


def verify(client, **params):
    response = client.get("/api/v1/provenance/verify/population_data", params=params)
    assert response.status_code == 200
    body = response.json()
    assert body["verification_status"] != "error", body
    db = client.app.dependency_overrides[data_provenance.get_db]()
    direct = asyncio.run(data_provenance.verify_data_point(
        "population_data", params.get("entity_id"), params.get("year"), db
    ))
    assert direct.model_dump() == body
    return body


def test_captured_worldbank_observation_keeps_value_and_unverified_grade(population_db, population_client):
    captured = json.loads((Path(__file__).resolve().parents[2] /
        "docs/operations/2026-09-30-sourced-records/population-79-acceptance.json").read_text())["after"]
    item = row(population_db, id=79, meta=captured["metadata"],
               male_population=captured["male_population"],
               female_population=captured["female_population"])
    body = verify(population_client, year=2019)
    consumer = population_client.get("/api/v1/economic/population", params={"year": 2019}).json()[0]
    assert consumer["id"] == item.id
    assert body["value"] == f'{consumer["total_population"]:,} (year 2019)'
    assert body["verification_status"] == "unverified"
    assert body["reason"] == "no resolvable source document"
    assert body["source_document"] is None and body["source_url"] is None
    hint = body["provenance_chain"][0]
    assert hint["source"] == WB_META["source"]
    assert hint["dataset"] == "SP.POP.TOTL" and hint["url"] == WB_URL
    assert hint["year"] == item.year and hint["entity_id"] is None
    assert "page_ref" not in hint and "extraction_id" not in hint
    direct = asyncio.run(data_provenance.verify_data_point("population_data", None, 2019, population_db))
    assert direct.model_dump() == body


def document(db):
    doc = SourceDocument(country_id=1, publisher=census_counties.PUBLISHER,
        title=census_counties.CENSUS_TITLE, url=census_counties.CENSUS_VOLUME_I_URL,
        fetch_date=datetime(2026, 9, 30), doc_type="REPORT", md5="a" * 32)
    db.add(doc)
    db.flush()
    extraction = Extraction(source_document_id=doc.id, page_number=17,
        extracted_json={"table": "2.2"}, extractor="knbs_census_population")
    db.add(extraction)
    db.flush()
    return doc, extraction


@pytest.mark.parametrize("total", [4_397_073, 0])
def test_county_document_and_exact_locator_including_sourced_zero(population_db, population_client, total):
    doc, extraction = document(population_db)
    item = row(population_db, entity_id=1, total_population=total,
        source_document_id=doc.id, extraction_id=extraction.id, source_page=17,
        page_ref="p. 17", source_hash="b" * 64,
        meta={"census_year": 2019, "table": "2.2", "source_url": doc.url})
    body = verify(population_client, year=2019, entity_id=1)
    assert body["value"] == f"{total:,} (year 2019)"
    assert body["source_document"] == doc.title and body["source_url"] == doc.url
    assert body["verification_status"] == "publishable"
    assert "not been fetched or validated" in body["reason"]
    hint = body["provenance_chain"][0]
    assert hint["source"] == doc.publisher and hint["dataset"] == doc.title
    assert hint["url"] == doc.url and hint["page_ref"] == "p. 17"
    assert hint["source_page"] == 17 and hint["source_hash"] == "b" * 64
    assert hint["extraction_id"] == extraction.id and hint["record_id"] == item.id


@pytest.mark.parametrize("metadata", [None, {}, [], "bad", True, 42,
    {"source": "World Bank"}, {"source": ["World Bank"], "source_url": WB_URL},
    {**WB_META, "dataset_id": "SP.POP.TOTL.MA.IN"},
    {**WB_META, "source_url": "https://example.test/population"},
    {**WB_META, "source": "KNBS Census 2019"},
    {**WB_META, "source": "World Bank Development Indicators (2020)"},
    {**WB_META, "source_url": "https://api.worldbank.org/v2/country/KEN/indicator/SP.POP.TOTL?format=json&date=2020"},
    {**WB_META, "census_year": 2019}])
def test_absent_conflicting_or_malformed_metadata_has_no_guessed_hint(population_db, population_client, metadata):
    row(population_db, meta=metadata)
    body = verify(population_client, year=2019)
    assert body["value"] == "51,202,827 (year 2019)"
    assert body["verification_status"] == "unverified"
    assert body["provenance_chain"] == []
    assert body["reason"]


def test_document_and_worldbank_metadata_conflict_is_explicit(population_db, population_client):
    doc, extraction = document(population_db)
    row(population_db, source_document_id=doc.id, extraction_id=extraction.id)
    body = verify(population_client, year=2019)
    assert body["verification_status"] == "unverified"
    assert body["provenance_chain"] == [] and body["source_url"] is None
    assert "conflicting population source identity" in body["reason"]


def test_year_entity_and_metadata_cannot_borrow_another_observation(population_db, population_client):
    row(population_db)
    row(population_db, year=2020, total_population=0,
        meta={**WB_META, "source": "World Bank Development Indicators (2020)"})
    row(population_db, entity_id=1, total_population=123, meta=WB_META)
    current = verify(population_client)
    assert current["value"] == "0 (year 2020)"
    assert current["provenance_chain"][0]["year"] == 2020
    older = verify(population_client, year=2019)
    assert older["provenance_chain"][0]["year"] == 2019
    county = verify(population_client, year=2019, entity_id=1)
    assert county["value"] == "123 (year 2019)"
    assert county["provenance_chain"] == []  # KEN national indicator cannot cite a county.
    for params in ({"year": 2018}, {"entity_id": 999}, {"year": 0}):
        missing = verify(population_client, **params)
        assert missing["value"] is None and missing["provenance_chain"] == []
        assert missing["reason"]


@pytest.mark.parametrize("metadata", [None, {}])
def test_document_identity_does_not_require_a_metadata_label(population_db, population_client, metadata):
    doc, _ = document(population_db)
    row(population_db, entity_id=1, meta=metadata, source_document_id=doc.id)
    body = verify(population_client, entity_id=1)
    assert body["source_document"] == doc.title
    assert body["provenance_chain"][0]["dataset"] == doc.title
    assert body["verification_status"] == "publishable"


@pytest.mark.parametrize("metadata", [[], "garbage", True,
    {"source_url": ["https://www.knbs.or.ke"]},
    {"census_year": True}, {"census_year": 2020},
    {"source": "World Bank Development Indicators (2019)"}])
def test_document_does_not_hide_conflicting_or_malformed_metadata(population_db, population_client, metadata):
    doc, _ = document(population_db)
    row(population_db, entity_id=1, meta=metadata, source_document_id=doc.id)
    body = verify(population_client, entity_id=1)
    assert body["verification_status"] == "unverified"
    assert body["provenance_chain"] == [] and body["source_url"] is None
    assert body["reason"]


@pytest.mark.parametrize("field,value", [("url", None), ("url", "javascript:alert(1)"),
    ("publisher", ""), ("title", "")])
def test_missing_document_identity_cannot_be_publishable(population_db, population_client, field, value):
    doc, _ = document(population_db)
    setattr(doc, field, value)
    row(population_db, entity_id=1, meta={}, source_document_id=doc.id)
    body = verify(population_client, entity_id=1)
    assert body["verification_status"] == "unverified"
    assert body["provenance_chain"] == [] and body["source_url"] is None


def test_extraction_from_another_document_cannot_be_attached(population_db, population_client):
    doc, _ = document(population_db)
    _, extraction = document(population_db)
    row(population_db, entity_id=1, meta={}, source_document_id=doc.id,
        extraction_id=extraction.id, source_page=17)
    body = verify(population_client, entity_id=1)
    assert body["verification_status"] == "unverified"
    assert body["provenance_chain"] == [] and body["source_url"] is None
    assert "conflicting population extraction identity" in body["reason"]


@pytest.mark.parametrize("field,value", [("source_page", 17), ("page_ref", "p.17"),
    ("extraction_id", None), ("source_hash", "b" * 64)])
def test_json_hint_does_not_reuse_stale_document_locators(population_db, population_client, field, value):
    if field == "extraction_id":
        _, extraction = document(population_db)
        value = extraction.id
    row(population_db, **{field: value})
    body = verify(population_client)
    assert body["verification_status"] == "unverified"
    assert body["provenance_chain"] == []


def test_publisher_json_api_url_is_a_hint_not_a_document(population_db, population_client):
    url = "https://api.worldbank.org/v2/country/KEN/indicator/SP.POP.TOTL?format=json&date=2019"
    row(population_db, meta={**WB_META, "source_url": url})
    body = verify(population_client, year=2019)
    assert body["provenance_chain"][0]["url"] == url
    assert body["source_document"] is None and body["source_url"] is None
    assert body["verification_status"] == "unverified"


def test_extraction_page_conflict_does_not_claim_a_locator(population_db, population_client):
    doc, extraction = document(population_db)
    row(population_db, entity_id=1, meta={}, source_document_id=doc.id,
        extraction_id=extraction.id, source_page=18)
    body = verify(population_client, entity_id=1)
    assert body["verification_status"] == "unverified"
    assert body["provenance_chain"] == [] and body["source_url"] is None
    assert "conflicting population extraction identity" in body["reason"]


def test_registered_application_keeps_population_response_contract(population_db, monkeypatch):
    from main import app

    row(population_db)
    monkeypatch.setitem(app.dependency_overrides, data_provenance.get_db, lambda: population_db)
    # No lifespan context: this probe only executes the registered route and
    # middleware, never the application's bootstrap/startup jobs.
    response = TestClient(app).get("/api/v1/provenance/verify/population_data?year=2019")
    assert response.status_code == 200
    body = response.json()
    assert body["value"] == "51,202,827 (year 2019)"
    assert body["verification_status"] == "unverified"
    assert body["provenance_chain"][0]["url"] == WB_URL


def test_worldbank_document_cannot_hide_a_knbs_source_label(population_db, population_client):
    doc, _ = document(population_db)
    doc.publisher = "World Bank"
    doc.title = "Population, total (SP.POP.TOTL)"
    doc.url = WB_URL
    row(population_db, source_document_id=doc.id,
        meta={"source": "KNBS Census 2019", "source_url": WB_URL})
    body = verify(population_client, year=2019)
    assert body["verification_status"] == "unverified"
    assert body["provenance_chain"] == [] and body["source_url"] is None
    assert "conflicting population source identity" in body["reason"]
