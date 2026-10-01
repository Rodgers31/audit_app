"""#137: registry coverage, stored lineage and byte verification differ.

Synthetic PostgreSQL/SQLite observations exercise direct and HTTP responses.
These fixtures do not assert production prevalence or authentic document bytes.
"""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from models import Base, Country, GDPData, PopulationData, SourceDocument
from routers import data_provenance as provenance

WB_GDP = "https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CN"
WB_POP = "https://data.worldbank.org/indicator/SP.POP.TOTL?locations=KE"
KNBS = "https://www.knbs.or.ke/wp-content/uploads/2025/05/2025-Economic-Survey.pdf"


@pytest.fixture(params=["sqlite", "postgresql"])
def health_db(request):
    schema = owner = None
    if request.param == "sqlite":
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    else:
        raw = os.environ.get("HEALTH_TEST_POSTGRES_URL")
        if not raw:
            pytest.skip(
                "Set HEALTH_TEST_POSTGRES_URL to disposable loopback PostgreSQL"
            )
        url = make_url(raw)
        assert (
            url.host == "127.0.0.1"
            and not url.query
            and url.drivername == "postgresql+psycopg2"
        )
        connect = dict(
            hostaddr="127.0.0.1",
            sslmode="disable",
            gssencmode="disable",
            connect_timeout=5,
        )
        schema = "r9_health_" + uuid.uuid4().hex
        owner = create_engine(url, connect_args=connect)
        with owner.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
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
            db.commit()
            yield db
    finally:
        engine.dispose()
        if schema:
            with owner.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            owner.dispose()


@pytest.fixture
def health_client(health_db):
    app = FastAPI()
    app.include_router(provenance.router)
    app.dependency_overrides[provenance.get_db] = lambda: health_db
    with TestClient(app) as client:
        yield client


def document(db, **overrides):
    values = dict(
        country_id=1,
        publisher="World Bank",
        title="World Bank Kenya GDP NY.GDP.MKTP.CN",
        url=WB_GDP,
        doc_type="REPORT",
        fetch_date=datetime.now(timezone.utc),
        meta={},
    )
    values.update(overrides)
    doc = SourceDocument(**values)
    db.add(doc)
    db.flush()
    return doc


def gdp(db, **overrides):
    values = dict(year=2022, gdp_value=123, currency="KES", meta={})
    values.update(overrides)
    item = GDPData(**values)
    db.add(item)
    db.commit()
    return item


def health(client, table="gdp_data"):
    response = client.get("/api/v1/provenance/health")
    assert response.status_code == 200, response.text
    body = response.json()
    direct = asyncio.run(
        provenance.get_data_health(
            db=client.app.dependency_overrides[provenance.get_db]()
        )
    ).model_dump()
    assert [{k: v for k, v in t.items()} for t in direct["tables"]] == body["tables"]
    result = next(t for t in body["tables"] if t["table"] == table)
    assert result["document_bytes_checked"] is False
    assert (
        sum(p["row_count"] for p in result["represented_publishers"])
        + result["unresolved_source_rows"]
        == result["row_count"]
    )
    assert (
        sum(result["attribution_reasons"].values()) == result["unresolved_source_rows"]
    )
    return result, body


def test_registry_does_not_claim_active_or_cross_validated_sources(health_client):
    sources = health_client.get("/api/v1/provenance/sources")
    assert sources.status_code == 200
    assert sources.json() == [
        s.model_dump() for s in asyncio.run(provenance.list_data_sources())
    ]
    assert len(sources.json()) == 6
    for source in sources.json():
        assert source["scope"] == "supported_publisher_registry"
        assert source["document_bytes_checked"] is False
        assert "cross-validated" not in str(source)
    _, body = health(health_client)
    assert body["sources_cited"] == 0
    assert body["supported_publisher_count"] == 6


@pytest.mark.parametrize(
    "publisher,url,meta,expected",
    [
        ("World Bank", WB_GDP, {}, "worldbank"),
        (
            "KNBS",
            KNBS,
            {"measure": "GDP, current KES", "dataset_id": "knbs_economic_survey"},
            "knbs",
        ),
    ],
)
def test_coherent_document_publisher_is_derived_not_static(
    health_db, health_client, publisher, url, meta, expected
):
    doc = document(
        health_db,
        publisher=publisher,
        url=url,
        title="Economic Survey 2025"
        if expected == "knbs"
        else "World Bank Kenya GDP NY.GDP.MKTP.CN",
        meta=meta,
    )
    gdp(health_db, source_document_id=doc.id, gdp_value=0)
    result, body = health(health_client)
    assert result["source"] == provenance.OFFICIAL_SOURCES[expected]["name"]
    assert result["attribution_status"] == "single_publisher"
    assert result["represented_publishers"] == [
        {
            "source_id": expected,
            "name": provenance.OFFICIAL_SOURCES[expected]["name"],
            "row_count": 1,
        }
    ]
    assert result["attribution_basis"] == "coherent_observation_identity"
    assert result["status"] == "degraded" and body["sources_cited"] == 1
    verified = health_client.get("/api/v1/provenance/verify/gdp_data").json()
    assert (
        verified["verification_status"] == "publishable"
        and "not been fetched or validated" in verified["reason"]
    )


def test_mixed_cohort_does_not_borrow_the_latest_publisher(health_db, health_client):
    wb = document(health_db)
    knbs = document(
        health_db,
        publisher="KNBS",
        url=KNBS,
        title="Economic Survey 2025",
        meta={"measure": "GDP, current KES"},
    )
    gdp(health_db, year=2022, source_document_id=wb.id)
    gdp(health_db, year=2024, source_document_id=knbs.id)
    result, body = health(health_client)
    assert (
        result["source"] is None and result["attribution_status"] == "mixed_publishers"
    )
    assert {p["source_id"] for p in result["represented_publishers"]} == {
        "worldbank",
        "knbs",
    }
    assert result["row_count"] == 2 and body["sources_cited"] == 2


@pytest.mark.parametrize(
    "meta",
    [
        [],
        "garbage",
        {"source": "KNBS"},
        {"indicator": "SP.POP.TOTL"},
        {"measure": "GDP growth"},
        {"datasets": []},
        {"year": True},
    ],
)
def test_malformed_conflicting_or_unsupported_identity_is_explicit(
    health_db, health_client, meta
):
    doc = document(health_db)
    gdp(health_db, source_document_id=doc.id, meta=meta)
    result, body = health(health_client)
    assert result["source"] is None and result["attribution_status"] == "unresolved"
    assert result["unresolved_source_rows"] == 1 and result["attribution_reasons"]
    assert body["sources_cited"] == 0


def test_partial_cohort_is_not_one_fully_attributed_publisher(health_db, health_client):
    doc = document(health_db)
    gdp(health_db, source_document_id=doc.id)
    gdp(health_db, year=2023, meta={})
    result, _ = health(health_client)
    assert result["source"] is None and result["attribution_status"] == "partial"
    assert (
        result["unresolved_source_rows"] == 1
        and result["represented_publishers"][0]["row_count"] == 1
    )


@pytest.mark.parametrize(
    "publisher,url",
    [
        ("Unknown Institute", "https://example.invalid/report"),
        ("World Bank impostor", WB_GDP),
    ],
)
def test_unknown_publisher_does_not_get_a_supported_label(
    health_db, health_client, publisher, url
):
    doc = document(
        health_db, publisher=publisher, url=url, meta={"measure": "GDP, current KES"}
    )
    gdp(health_db, source_document_id=doc.id)
    result, body = health(health_client)
    assert (
        result["source"] is None
        and result["represented_publishers"] == []
        and body["sources_cited"] == 0
    )


def test_metadata_only_population_keeps_low_grade_and_selected_identity(
    health_db, health_client
):
    health_db.add(
        PopulationData(
            id=79,
            year=2019,
            total_population=51_202_827,
            meta={
                "source": "World Bank Development Indicators (2019)",
                "dataset_id": "SP.POP.TOTL",
                "source_url": WB_POP,
            },
        )
    )
    health_db.commit()
    result, _ = health(health_client, "population_data")
    assert result["source"] == provenance.OFFICIAL_SOURCES["worldbank"]["name"]
    assert result["attribution_basis"] == "coherent_observation_identity"
    verified = health_client.get(
        "/api/v1/provenance/verify/population_data", params={"year": 2019}
    ).json()
    assert (
        verified["verification_status"] == "unverified"
        and verified["source_document"] is None
    )
    assert verified["value"] == "51,202,827 (year 2019)"
    assert health_db.get(PopulationData, 79).total_population == 51_202_827


@pytest.mark.parametrize(
    "doc_meta,meta",
    [([], {}), ({}, {"source": "World Bank"}), ({}, {"census_year": True}), ({}, [])],
)
def test_population_bad_document_or_row_shape_is_unresolved(
    health_db, health_client, doc_meta, meta
):
    doc = document(
        health_db,
        publisher="KNBS",
        url="https://www.knbs.or.ke/census2019.pdf",
        title="Census 2019",
        meta=doc_meta,
    )
    health_db.add(
        PopulationData(
            year=2019, total_population=0, source_document_id=doc.id, meta=meta
        )
    )
    health_db.commit()
    result, _ = health(health_client, "population_data")
    assert result["source"] is None and result["unresolved_source_rows"] == 1


def test_no_rows_have_no_attributed_publisher(health_client):
    for table in ("gdp_data", "population_data", "entities", "budget_lines"):
        result, _ = health(health_client, table)
        assert result["source"] is None and result["attribution_status"] == "empty"
        assert result["represented_publishers"] == [] and result["row_count"] == 0


def test_attribution_never_promotes_stale_or_partial_status(health_db, health_client):
    doc = document(
        health_db, fetch_date=datetime.now(timezone.utc) - timedelta(days=700)
    )
    for year in range(2018, 2023):
        gdp(health_db, year=year, source_document_id=doc.id)
    result, _ = health(health_client)
    assert result["source"] == provenance.OFFICIAL_SOURCES["worldbank"]["name"]
    assert result["status"] == "stale" and result["age_days"] >= 700
    assert "no row has changed" in result["notes"]


def test_original_worldbank_health_attribution_regression(health_db, health_client):
    """Assert the old response fields first: red means the actual wrong label."""
    doc = document(health_db)
    gdp(health_db, source_document_id=doc.id)
    response = health_client.get("/api/v1/provenance/health")
    assert response.status_code == 200
    result = next(t for t in response.json()["tables"] if t["table"] == "gdp_data")
    assert result["source"] == "World Bank Open Data"


def test_original_registry_cross_validation_claim_regression(health_client):
    response = health_client.get("/api/v1/provenance/sources")
    assert response.status_code == 200
    worldbank = next(s for s in response.json() if s["source_id"] == "worldbank")
    assert "cross-validated" not in worldbank["datasets"][0]["covers"]


def test_population_document_zero_cannot_be_ignored_for_metadata(
    health_db, health_client
):
    doc = document(
        health_db,
        id=0,
        publisher="KNBS",
        url="https://www.knbs.or.ke/census2019.pdf",
        title="Census 2019",
    )
    health_db.add(
        PopulationData(
            year=2022,
            total_population=0,
            source_document_id=doc.id,
            meta={
                "source": "World Bank Development Indicators (2022)",
                "dataset_id": "SP.POP.TOTL",
                "source_url": WB_POP,
            },
        )
    )
    health_db.commit()
    result, body = health(health_client, "population_data")
    assert result["source"] is None and result["attribution_status"] == "unresolved"
    assert result["unresolved_source_rows"] == 1 and body["sources_cited"] == 0


@pytest.mark.parametrize("payload", [[], "garbage", True, 42])
def test_population_malformed_extraction_cannot_certify_coherent_lineage(
    health_db, health_client, payload
):
    from models import Extraction

    doc = document(
        health_db,
        publisher="KNBS",
        url="https://www.knbs.or.ke/census2019.pdf",
        title="Census 2019",
    )
    extraction = Extraction(
        source_document_id=doc.id,
        page_number=3,
        extracted_json=payload,
        extractor="synthetic",
    )
    health_db.add(extraction)
    health_db.flush()
    health_db.add(
        PopulationData(
            year=2019,
            total_population=0,
            source_document_id=doc.id,
            source_page=3,
            extraction_id=extraction.id,
            meta={"source": "KNBS", "census_year": 2019},
        )
    )
    health_db.commit()
    result, _ = health(health_client, "population_data")
    assert result["source"] is None and result["attribution_status"] == "unresolved"
    assert result["unresolved_source_rows"] == 1


@pytest.mark.parametrize("location", ["row", "extraction"])
@pytest.mark.parametrize(
    "declaration",
    [
        {"source": "KNBS and World Bank"},
        {"source": "KNBS impostor"},
        {"source": "Kenya National Bureau of Statistics / World Bank"},
        {"source": "World Bank"},
        {"year": 2020},
        {"dataset_id": "NY.GDP.MKTP.CN"},
        {"year": True},
        {"indicators": []},
        {"measure": "GDP, current KES"},
    ],
)
def test_population_explicit_declarations_cannot_be_hidden_by_document(
    health_db, health_client, location, declaration
):
    from models import Extraction

    doc = document(
        health_db,
        publisher="KNBS",
        url="https://www.knbs.or.ke/census2019.pdf",
        title="Census 2019",
    )
    values = dict(year=2019, total_population=0, source_document_id=doc.id, meta={})
    if location == "row":
        values["meta"] = declaration
    else:
        extraction = Extraction(
            source_document_id=doc.id,
            page_number=3,
            extracted_json=declaration,
            extractor="synthetic",
        )
        health_db.add(extraction)
        health_db.flush()
        values.update(extraction_id=extraction.id, source_page=3)
    health_db.add(PopulationData(**values))
    health_db.commit()
    result, _ = health(health_client, "population_data")
    assert result["source"] is None and result["unresolved_source_rows"] == 1


@pytest.mark.parametrize("total", [0, 4_397_073])
def test_genuine_census_document_and_extraction_remain_attributed(
    health_db, health_client, total
):
    from models import Extraction, Entity
    from seeding.domains.population import census_counties

    health_db.add(
        Entity(
            id=1, country_id=1, type="COUNTY", canonical_name="Nairobi", slug="nairobi"
        )
    )
    doc = document(
        health_db,
        publisher=census_counties.PUBLISHER,
        url=census_counties.CENSUS_VOLUME_I_URL,
        title=census_counties.CENSUS_TITLE,
    )
    extraction = Extraction(
        source_document_id=doc.id,
        page_number=17,
        extracted_json={"table": "2.2"},
        extractor="knbs_census_population",
    )
    health_db.add(extraction)
    health_db.flush()
    health_db.add(
        PopulationData(
            year=2019,
            entity_id=1,
            total_population=total,
            source_document_id=doc.id,
            extraction_id=extraction.id,
            source_page=17,
            page_ref="p. 17",
            meta={
                "source": "KNBS Census 2019",
                "census_year": 2019,
                "dataset_id": "knbs_census_2019",
                "source_url": doc.url,
            },
        )
    )
    health_db.commit()
    result, _ = health(health_client, "population_data")
    assert result["source"] == provenance.OFFICIAL_SOURCES["knbs"]["name"]
    assert result["unresolved_source_rows"] == 0 and result["status"] == "degraded"


@pytest.mark.parametrize("location", ["row", "document_meta", "document_publisher"])
@pytest.mark.parametrize(
    "source",
    ["KNBS Census 2018", "KNBS  Census  2018", "KNBS Census–2018", "Kenya Census 2018"],
)
def test_normalized_population_source_labels_keep_observation_year(
    health_db, health_client, location, source
):
    doc = document(
        health_db,
        publisher=source if location == "document_publisher" else "KNBS",
        url="https://www.knbs.or.ke/census2019.pdf",
        title="Census 2019",
        meta={"source": source} if location == "document_meta" else {},
    )
    health_db.add(
        PopulationData(
            year=2019,
            total_population=0,
            source_document_id=doc.id,
            meta={"source": source} if location == "row" else {},
        )
    )
    health_db.commit()
    result, _ = health(health_client, "population_data")
    assert result["source"] is None and result["unresolved_source_rows"] == 1


def test_population_document_publisher_label_year_cannot_be_borrowed(
    health_db, health_client
):
    doc = document(
        health_db,
        publisher="World Bank Development Indicators (2018)",
        title="Population",
        url="https://data.worldbank.org/indicator/SP.POP.TOTL?locations=KE",
    )
    health_db.add(
        PopulationData(
            year=2019, total_population=0, source_document_id=doc.id, meta={}
        )
    )
    health_db.commit()
    result, _ = health(health_client, "population_data")
    assert result["source"] is None and result["unresolved_source_rows"] == 1


def test_other_tables_inventory_document_links_without_grading_observations(
    health_db, health_client
):
    from models import DebtTimeline

    doc = document(
        health_db,
        publisher="CBK",
        url="https://www.centralbank.go.ke/public-debt/report.pdf",
        title="Debt Bulletin",
    )
    health_db.add(
        DebtTimeline(
            year=2022,
            total=0,
            external=0,
            domestic=0,
            source_document_id=doc.id,
            meta=["unassessed observation"],
        )
    )
    health_db.add(DebtTimeline(year=2023, total=123, external=123, domestic=0, meta={}))
    health_db.commit()
    result, _ = health(health_client, "debt_timeline")
    assert result["attribution_basis"] == "stored_document_links"
    assert result["attribution_status"] == "partial" and result["source"] is None
    assert result["represented_publishers"][0]["source_id"] == "cbk"
    assert (
        result["represented_publishers"][0]["row_count"] == 1
        and result["unresolved_source_rows"] == 1
    )


def test_withheld_audits_do_not_add_a_publisher_to_counted_cohort(
    health_db, health_client
):
    from models import Audit, Entity, FiscalPeriod

    health_db.add(
        Entity(
            id=1, country_id=1, type="COUNTY", canonical_name="Nairobi", slug="nairobi"
        )
    )
    health_db.add(
        FiscalPeriod(
            id=1,
            country_id=1,
            label="FY2024/25",
            start_date=datetime(2024, 7, 1),
            end_date=datetime(2025, 6, 30),
        )
    )
    doc = document(
        health_db,
        publisher="Office of the Auditor General",
        url="https://www.oagkenya.go.ke/report.pdf",
        title="Audit Report",
    )
    other = document(
        health_db,
        publisher="KNBS",
        url="https://www.knbs.or.ke/report.pdf",
        title="Withheld report",
    )
    health_db.add(
        Audit(
            entity_id=1,
            period_id=1,
            source_document_id=doc.id,
            finding_text="Revenue records were not reconciled.",
            severity="WARNING",
            page_ref="p. 17",
            audit_year=2025,
        )
    )
    health_db.add(
        Audit(
            entity_id=1,
            period_id=1,
            source_document_id=other.id,
            finding_text="Unlocated record.",
            severity="WARNING",
            page_ref=None,
            audit_year=2025,
        )
    )
    health_db.commit()
    result, body = health(health_client, "audits")
    assert (
        result["row_count"] == 1
        and result["attribution_basis"] == "stored_document_links"
    )
    assert result["represented_publishers"][0]["source_id"] == "oag"
    assert (
        result["represented_publishers"][0]["row_count"] == 1
        and body["sources_cited"] == 1
    )
    assert "1 withheld" in result["notes"]
