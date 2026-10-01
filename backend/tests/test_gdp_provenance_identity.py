"""#408: selected GDP and its evidence must describe the same observation.

Synthetic PostgreSQL/SQLite records exercise the real router and HTTP boundary.
KNBS controls use the published 2025 survey's nominal GDP figure; constructing
locators is not a claim that this endpoint fetches or independently verifies it.
"""
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

from models import Base, Country, Entity, Extraction, GDPData, SourceDocument
from routers import data_provenance, economic
from seeding.domains.national_gdp import _ensure_gdp_source_document

WB_URL = "https://data.worldbank.org/indicator/NY.GDP.MKTP.CN?locations=KE"
WB_META = {
    "source": "World Bank Development Indicators (2022)",
    "dataset_id": "NY.GDP.MKTP.CN",
    "source_url": WB_URL,
}
KNBS_URL = "https://www.knbs.or.ke/wp-content/uploads/2025/05/2025-Economic-Survey.pdf"
MEASURE = "GDP, current KES"


@pytest.fixture(params=["sqlite", "postgresql"])
def gdp_db(request):
    schema = None
    owner = None
    if request.param == "sqlite":
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    else:
        raw = os.environ.get("GDP_TEST_POSTGRES_URL")
        if not raw:
            pytest.skip("Set GDP_TEST_POSTGRES_URL to disposable loopback PostgreSQL")
        url = make_url(raw)
        assert url.host == "127.0.0.1" and not url.query
        assert url.drivername == "postgresql+psycopg2"
        connect = dict(
            hostaddr="127.0.0.1",
            sslmode="disable",
            gssencmode="disable",
            connect_timeout=5,
        )
        schema = "gdp_408_" + uuid.uuid4().hex
        owner = create_engine(url, connect_args=connect)
        with owner.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(
            url, connect_args={**connect, "options": f"-csearch_path={schema}"}
        )
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(
                Country(
                    id=1,
                    iso_code="KEN",
                    name="Kenya",
                    currency="KES",
                    timezone="Africa/Nairobi",
                    default_locale="en_KE",
                )
            )
            db.flush()
            # Exercise the real writer in its current single-country context.
            # Additional countries test reader identity without changing that writer.
            _ensure_gdp_source_document(db)
            db.add(
                Country(
                    id=2,
                    iso_code="UGA",
                    name="Uganda",
                    currency="UGX",
                    timezone="Africa/Kampala",
                    default_locale="en_UG",
                )
            )
            db.flush()
            db.add_all(
                [
                    Entity(
                        id=1,
                        country_id=1,
                        type="COUNTY",
                        canonical_name="Nairobi",
                        slug="nairobi",
                    ),
                    Entity(
                        id=2,
                        country_id=1,
                        type="NATIONAL",
                        canonical_name="Kenya",
                        slug="kenya",
                    ),
                    Entity(
                        id=3,
                        country_id=2,
                        type="NATIONAL",
                        canonical_name="Uganda",
                        slug="uganda",
                    ),
                ]
            )
            db.commit()
            yield db
    finally:
        engine.dispose()
        if schema:
            with owner.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            owner.dispose()


@pytest.fixture
def gdp_client(gdp_db):
    app = FastAPI()
    app.include_router(data_provenance.router)
    app.include_router(economic.router)
    app.dependency_overrides[data_provenance.get_db] = lambda: gdp_db
    app.dependency_overrides[economic.get_db] = lambda: gdp_db
    with TestClient(app) as client:
        yield client


def row(db, **kwargs):
    values = dict(year=2022, gdp_value=1_234_000_000_000, currency="KES", meta=WB_META)
    values.update(kwargs)
    item = GDPData(**values)
    db.add(item)
    db.commit()
    return item


def verify(client, **params):
    response = client.get("/api/v1/provenance/verify/gdp_data", params=params)
    assert response.status_code == 200
    body = response.json()
    assert body["verification_status"] not in {"error", "verified"}, body
    db = client.app.dependency_overrides[data_provenance.get_db]()
    direct = asyncio.run(
        data_provenance.verify_data_point(
            "gdp_data", params.get("entity_id"), params.get("year"), db
        )
    )
    assert direct.model_dump() == body
    return body


def absent(body, value="KES 1.23T (year 2022)"):
    assert body["value"] == value
    assert body["verification_status"] == "unverified"
    assert body["provenance_chain"] == []
    assert body["publisher"] is None and body["source_url"] is None
    assert body["source_document"] is None and body["reason"]


def document(db, **kwargs):
    values = dict(
        country_id=1,
        publisher="Kenya National Bureau of Statistics",
        title="Economic Survey 2025",
        url=KNBS_URL,
        doc_type="REPORT",
        fetch_date=datetime(2026, 10, 1),
        md5="a" * 32,
        meta={
            "dataset_id": "knbs_economic_survey",
            "measure": MEASURE,
            "country_code": "KEN",
            "scope": "national",
            "currency": "KES",
        },
    )
    values.update(kwargs)
    doc = SourceDocument(**values)
    db.add(doc)
    db.flush()
    return doc


def test_worldbank_json_hint_does_not_invent_pdf_or_cross_check(gdp_db, gdp_client):
    item = row(gdp_db)
    body = verify(gdp_client, year=2022)
    consumer = gdp_client.get("/api/v1/economic/gdp", params={"year": 2022}).json()[0]
    assert consumer["id"] == item.id and consumer["gdp_value"] == float(item.gdp_value)
    assert body["value"] == "KES 1.23T (year 2022)"
    assert body["verification_status"] == "unverified"
    assert body["source_document"] is None and body["source_url"] is None
    hint = body["provenance_chain"][0]
    assert hint["source"] == WB_META["source"]
    assert hint["dataset"] == "NY.GDP.MKTP.CN" and hint["url"] == WB_URL
    assert hint["record_id"] == item.id and hint["year"] == 2022
    assert hint["entity_id"] is None and hint["currency"] == "KES"
    assert (
        "cross_check" not in hint
        and "extraction_id" not in hint
        and "page_ref" not in hint
    )


@pytest.mark.parametrize("value", [1_234_000_000_000, 0])
def test_real_worldbank_writer_document_keeps_qualified_status(
    gdp_db, gdp_client, value
):
    doc = _ensure_gdp_source_document(gdp_db)
    item = row(
        gdp_db,
        gdp_value=value,
        source_document_id=doc.id,
        meta={
            "source": "World Bank NY.GDP.MKTP.CN",
            "scope": "national",
            "seeding_domain": "national_gdp",
            "data_quality": "official",
        },
    )
    body = verify(gdp_client, year=2022)
    assert body["value"] == f"KES {value / 1e12:.2f}T (year 2022)"
    assert body["verification_status"] == "publishable"
    assert body["publisher"] == "World Bank" and body["source_document"] == doc.title
    assert body["fetch_date"] == doc.fetch_date.isoformat()
    assert "not been fetched or validated" in body["reason"]
    assert len(body["provenance_chain"]) == 1
    hint = body["provenance_chain"][0]
    assert hint["source"] == doc.publisher and hint["source_document_id"] == doc.id
    assert hint["record_id"] == item.id and hint["url"] == doc.url
    assert "cross_check" not in hint and "source_page" not in hint


def test_knbs_nominal_observation_keeps_exact_stored_locators(gdp_db, gdp_client):
    doc = document(gdp_db)
    extraction = Extraction(
        source_document_id=doc.id,
        page_number=42,
        extracted_json={
            "measure": MEASURE,
            "year": 2024,
            "currency": "KES",
            "entity_id": None,
        },
        extractor="pdfplumber",
    )
    gdp_db.add(extraction)
    gdp_db.flush()
    item = row(
        gdp_db,
        year=2024,
        gdp_value=16_224_500_000_000,
        source_document_id=doc.id,
        extraction_id=extraction.id,
        source_page=42,
        page_ref="PDF p. 42",
        source_hash="b" * 64,
        meta={
            "source": "KNBS",
            "measure": MEASURE,
            "year": 2024,
            "source_url": doc.url,
        },
    )
    body = verify(gdp_client, year=2024)
    assert body["value"] == "KES 16.22T (year 2024)"
    assert (
        body["verification_status"] == "publishable"
        and body["publisher"] == doc.publisher
    )
    hint = body["provenance_chain"][0]
    assert hint["record_id"] == item.id and hint["source_page"] == 42
    assert hint["page_ref"] == "PDF p. 42" and hint["source_hash"] == "b" * 64
    assert hint["extraction_id"] == extraction.id


@pytest.mark.parametrize(
    "meta",
    [
        None,
        {},
        [],
        "",
        "bad",
        True,
        42,
        {"source": "World Bank"},
        {**WB_META, "source": ["World Bank"]},
        {**WB_META, "dataset_id": "SP.POP.TOTL"},
        {**WB_META, "dataset_id": "NY.GDP.PCAP.CN"},
        {**WB_META, "dataset_id": "NY.GDP.MKTP.CD"},
        {**WB_META, "dataset_id": ""},
        {**WB_META, "source_url": "https://example.test/gdp"},
        {**WB_META, "source": "World Bank Development Indicators (2023)"},
        {**WB_META, "measure": "GDP per capita"},
        {**WB_META, "year": True},
        {**WB_META, "year": 2023},
        {**WB_META, "currency": "USD"},
        {**WB_META, "country_code": "UGA"},
        {**WB_META, "entity_id": 1},
        {**WB_META, "source_url": WB_URL.replace("KE", "UG")},
        {
            **WB_META,
            "source_url": "https://api.worldbank.org/v2/country/UGA/indicator/NY.GDP.MKTP.CN",
        },
        {
            **WB_META,
            "source_url": "https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CN?date=2023",
        },
        {
            **WB_META,
            "source_url": "https://api.worldbank.org/v2/country/KEN/indicator/SP.POP.TOTL?date=2022",
        },
        {
            **WB_META,
            "cross_check": {"source": "KNBS", "status": "verified"},
            "indicator": "NY.GDP.PCAP.CN",
        },
    ],
)
def test_json_absence_and_conflicts_never_get_guessed_lineage(gdp_db, gdp_client, meta):
    row(gdp_db, meta=meta)
    absent(verify(gdp_client, year=2022))


@pytest.mark.parametrize(
    "field,value",
    [
        ("meta", []),
        ("meta", {"indicator": "SP.POP.TOTL"}),
        ("meta", {"indicator": "NY.GDP.PCAP.CN"}),
        ("meta", {"measure": "real GDP growth"}),
        ("meta", {"year": 2023, "indicator": "NY.GDP.MKTP.CN"}),
        ("meta", {"indicator": "NY.GDP.MKTP.CN", "entity_id": 1}),
        ("meta", {"indicator": "NY.GDP.MKTP.CN", "currency": "USD"}),
        ("url", "https://api.worldbank.org/v2/country/UGA/indicator/NY.GDP.MKTP.CN"),
        ("url", "https://api.worldbank.org/v2/country/KEN/indicator/SP.POP.TOTL"),
        ("url", "https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CD"),
        (
            "url",
            "https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CN?date=2023",
        ),
        ("publisher", ""),
        ("publisher", "KNBS"),
        ("country_id", 2),
        ("title", "World Bank population (SP.POP.TOTL)"),
        ("url", None),
        ("url", "javascript:bad"),
    ],
)
def test_document_identity_cannot_override_conflicts(gdp_db, gdp_client, field, value):
    doc = _ensure_gdp_source_document(gdp_db)
    setattr(doc, field, value)
    row(gdp_db, source_document_id=doc.id, meta={})
    absent(verify(gdp_client, year=2022))


@pytest.mark.parametrize(
    "meta",
    [
        [],
        "bad",
        {"source": "KNBS"},
        {"source": "National Treasury"},
        {"source": ""},
        {"dataset_id": "SP.POP.TOTL"},
        {"indicator": False},
        {"year": 2023},
        {"entity_id": True},
        {"currency": "USD"},
        {"scope": "county"},
        {"source_url": "https://www.knbs.or.ke/economic-survey/"},
        {"source": "World Bank SP.POP.TOTL"},
        {"source": "World Bank Development Indicators (2023)"},
        {"units": "millions"},
        {"measure": "GDP, constant KES"},
    ],
)
def test_row_declarations_cannot_be_hidden_by_a_correct_document(
    gdp_db, gdp_client, meta
):
    doc = _ensure_gdp_source_document(gdp_db)
    row(gdp_db, source_document_id=doc.id, meta=meta)
    absent(verify(gdp_client, year=2022))


@pytest.mark.parametrize(
    "publisher,meta,accepted",
    [
        (
            "National Treasury",
            {"source": " National Treasury ", "measure": MEASURE},
            True,
        ),
        (
            "Unknown Institute",
            {"source": "Unknown Institute", "measure": MEASURE},
            True,
        ),
        ("National Treasury", {"source": "World Bank", "measure": MEASURE}, False),
        ("National Treasury", {"source": "National Treasury"}, False),
        ("KNBS", {"source": "KNBS"}, False),
    ],
)
def test_custom_publisher_needs_measure_evidence(
    gdp_db, gdp_client, publisher, meta, accepted
):
    doc = document(
        gdp_db, publisher=publisher, url="https://example.test/economic-report", meta={}
    )
    row(gdp_db, source_document_id=doc.id, meta=meta)
    body = verify(gdp_client, year=2022)
    if accepted:
        assert body["verification_status"] == "publishable"
        assert (
            body["publisher"] == publisher
            and body["provenance_chain"][0]["source"] == publisher
        )
    else:
        absent(body)


@pytest.mark.parametrize(
    "override",
    [
        {"source_page": 9},
        {"extraction_id": 999},
        {"page_ref": "PDF p. 9"},
        {"source_hash": "b" * 64},
        {"entity_id": 1},
        {"entity_id": 3},
        {"currency": "USD"},
        {"quarter": "Q1"},
    ],
)
def test_worldbank_annual_json_cannot_impersonate_other_scopes_or_pdf(
    gdp_db, gdp_client, override
):
    # Unknown extraction FK cannot be inserted in PostgreSQL; use an actual
    # extraction row to prove that an API document is not PDF evidence.
    if "extraction_id" in override:
        doc = document(gdp_db)
        extraction = Extraction(
            source_document_id=doc.id,
            page_number=9,
            extracted_json={},
            extractor="pdfplumber",
        )
        gdp_db.add(extraction)
        gdp_db.flush()
        override = {"extraction_id": extraction.id}
    doc = _ensure_gdp_source_document(gdp_db)
    row(gdp_db, source_document_id=doc.id, meta={}, **override)
    body = verify(
        gdp_client,
        year=2022,
        **({"entity_id": override["entity_id"]} if "entity_id" in override else {}),
    )
    absent(body, value=f"{override.get('currency', 'KES')} 1.23T (year 2022)")


def test_entity_and_year_selection_stay_exact(gdp_db, gdp_client):
    row(gdp_db)
    row(
        gdp_db,
        year=2023,
        gdp_value=0,
        meta={**WB_META, "source": "World Bank Development Indicators (2023)"},
    )
    row(gdp_db, entity_id=1, gdp_value=123, meta=WB_META)
    assert verify(gdp_client)["value"] == "KES 0.00T (year 2023)"
    assert verify(gdp_client, year=2022)["provenance_chain"][0]["year"] == 2022
    absent(verify(gdp_client, year=2022, entity_id=1), value="KES 0.00T (year 2022)")
    for params in ({"year": 0}, {"year": 2020}, {"entity_id": 999}):
        body = verify(gdp_client, **params)
        assert (
            body["value"] is None and body["provenance_chain"] == [] and body["reason"]
        )


def test_captured_publisher_json_runs_through_real_gdp_parser(gdp_db, gdp_client):
    from seeding.domains.national_gdp.fetcher import _parse_wb_gdp

    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "worldbank_gdp_2022.json").read_text()
    )
    observation = payload[1][0]
    value = _parse_wb_gdp(payload)[2022]
    item = row(
        gdp_db,
        gdp_value=value,
        meta={
            "source": "World Bank Development Indicators (2022)",
            "dataset_id": observation["indicator"]["id"],
            "country_code": observation["countryiso3code"],
            "year": int(observation["date"]),
            "source_url": "https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CN?format=json&date=2022",
        },
    )
    body = verify(gdp_client, year=2022)
    assert body["value"] == f"KES {value / 1e12:.2f}T (year 2022)"
    assert body["provenance_chain"][0]["record_id"] == item.id
    assert body["verification_status"] == "unverified"
    consumer = gdp_client.get("/api/v1/economic/gdp", params={"year": 2022}).json()[0]
    assert consumer["gdp_value"] == value


@pytest.mark.parametrize(
    "payload",
    [
        [],
        "bad",
        {"measure": "GDP per capita"},
        {"measure": MEASURE, "year": 2023},
        {"measure": MEASURE, "entity_id": 1},
        {"measure": MEASURE, "currency": "USD"},
        {"measure": MEASURE, "indicator": "SP.POP.TOTL"},
    ],
)
def test_extraction_cannot_contradict_the_selected_observation(
    gdp_db, gdp_client, payload
):
    doc = document(gdp_db)
    extraction = Extraction(
        source_document_id=doc.id,
        page_number=42,
        extracted_json=payload,
        extractor="pdfplumber",
    )
    gdp_db.add(extraction)
    gdp_db.flush()
    row(gdp_db, source_document_id=doc.id, extraction_id=extraction.id, meta={})
    absent(verify(gdp_client, year=2022))


def test_extraction_from_another_document_is_not_a_locator(gdp_db, gdp_client):
    doc = document(gdp_db)
    other = document(gdp_db, url="https://www.knbs.or.ke/another-report.pdf")
    extraction = Extraction(
        source_document_id=other.id,
        page_number=42,
        extracted_json={"measure": MEASURE},
        extractor="pdfplumber",
    )
    gdp_db.add(extraction)
    gdp_db.flush()
    row(gdp_db, source_document_id=doc.id, extraction_id=extraction.id, meta={})
    absent(verify(gdp_client, year=2022))


@pytest.mark.parametrize("entity_id", [None, 2])
def test_explicit_kenya_national_entity_is_supported(gdp_db, gdp_client, entity_id):
    doc = _ensure_gdp_source_document(gdp_db)
    row(gdp_db, source_document_id=doc.id, meta={}, entity_id=entity_id)
    body = verify(
        gdp_client, **({"entity_id": entity_id} if entity_id is not None else {})
    )
    assert body["verification_status"] == "publishable"
    assert body["provenance_chain"][0]["entity_id"] == entity_id


def test_county_gcp_requires_its_own_measure_and_entity_evidence(gdp_db, gdp_client):
    doc = document(
        gdp_db,
        meta={
            "dataset_id": "knbs_gross_county_product",
            "measure": "Gross County Product, current KES",
            "entity_id": 1,
            "scope": "county",
            "year": 2022,
        },
    )
    row(gdp_db, source_document_id=doc.id, meta={}, entity_id=1)
    body = verify(gdp_client, entity_id=1)
    assert body["verification_status"] == "publishable"
    assert body["provenance_chain"][0]["measure"] == "Gross County Product, current KES"
    assert body["provenance_chain"][0]["entity_id"] == 1


@pytest.mark.parametrize("value", ["NaN", "-1"])
def test_invalid_nominal_amount_cannot_gain_a_document_grade(gdp_db, gdp_client, value):
    from decimal import Decimal

    doc = _ensure_gdp_source_document(gdp_db)
    if value == "NaN" and gdp_db.bind.dialect.name == "sqlite":
        # The SQLite driver turns NaN into NULL. Prove the database rejects it.
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            row(gdp_db, gdp_value=Decimal(value), source_document_id=doc.id, meta={})
        gdp_db.rollback()
        return
    row(gdp_db, gdp_value=Decimal(value), source_document_id=doc.id, meta={})
    body = verify(gdp_client)
    assert body["verification_status"] == "unverified"
    assert body["provenance_chain"] == [] and body["source_url"] is None
    assert body["reason"]


@pytest.mark.parametrize("location", ["row", "document", "extraction"])
@pytest.mark.parametrize(
    "declaration",
    [
        {"indicators": ["SP.POP.TOTL"]},
        {"indicators": {"id": "NY.GDP.MKTP.CD"}},
        {"indicators": []},
        {"indicators": None},
        {"measures": ["GDP per capita"]},
        {"datasets": ["SP.POP.TOTL"]},
        {"dataset": "SP.POP.TOTL"},
        {"dataset_id": "population"},
        {"gdp_value": 999},
        {"value": True},
    ],
)
def test_all_declared_evidence_shapes_must_be_coherent(
    gdp_db, gdp_client, location, declaration
):
    doc = document(gdp_db)
    meta = {}
    extraction_id = None
    if location == "row":
        meta = declaration
    elif location == "document":
        doc.meta = {**doc.meta, **declaration}
    else:
        extraction = Extraction(
            source_document_id=doc.id,
            page_number=42,
            extracted_json=declaration,
            extractor="pdfplumber",
        )
        gdp_db.add(extraction)
        gdp_db.flush()
        extraction_id = extraction.id
    row(gdp_db, source_document_id=doc.id, meta=meta, extraction_id=extraction_id)
    absent(verify(gdp_client))


@pytest.mark.parametrize(
    "title",
    [
        "Kenya population report",
        "GDP per capita, current KES",
        "GDP growth",
        "GDP constant prices",
        "GDP, current USD",
        "GDP ny.gdp.pcap.cn",
        "GDP per-capita",
        "GDP (current US$)",
        "Real gross domestic product",
        "Growth in Gross Domestic Product",
        "GDP\nper capita",
    ],
)
def test_explicit_wrong_measure_titles_do_not_certify_nominal_gdp(
    gdp_db, gdp_client, title
):
    doc = document(gdp_db, title=title)
    row(gdp_db, source_document_id=doc.id, meta={})
    absent(verify(gdp_client))


def test_document_publisher_label_year_is_not_ignored(gdp_db, gdp_client):
    doc = _ensure_gdp_source_document(gdp_db)
    doc.publisher = "World Bank Development Indicators (2023)"
    row(gdp_db, source_document_id=doc.id, meta={})
    absent(verify(gdp_client))


@pytest.mark.parametrize(
    "quarter,meta,accepted",
    [
        ("ZZ", {"quarter": "ZZ"}, False),
        ("Q1", {}, False),
        ("Q1", {"quarter": "Q1"}, True),
    ],
)
def test_quarter_requires_explicit_supported_observation_identity(
    gdp_db, gdp_client, quarter, meta, accepted
):
    doc = document(gdp_db)
    row(gdp_db, source_document_id=doc.id, meta=meta, quarter=quarter)
    body = verify(gdp_client)
    if accepted:
        assert body["verification_status"] == "publishable"
        assert body["provenance_chain"][0]["quarter"] == quarter
    else:
        absent(body)


@pytest.mark.parametrize(
    "meta",
    [
        None,
        {},
        {"indicators": ["NY.GDP.MKTP.CN"]},
        {"dataset": "NY.GDP.MKTP.CN"},
        {"measures": [MEASURE]},
        {"gdp_value": 1_234_000_000_000},
    ],
)
def test_positive_document_evidence_including_lists_does_not_need_row_labels(
    gdp_db, gdp_client, meta
):
    doc = _ensure_gdp_source_document(gdp_db)
    row(gdp_db, source_document_id=doc.id, meta=meta)
    assert verify(gdp_client)["verification_status"] == "publishable"


def test_survey_publication_year_is_not_the_observation_year(gdp_db, gdp_client):
    doc = document(gdp_db, title="Economic Survey 2023")
    row(gdp_db, source_document_id=doc.id, meta={})
    assert verify(gdp_client, year=2022)["verification_status"] == "publishable"
