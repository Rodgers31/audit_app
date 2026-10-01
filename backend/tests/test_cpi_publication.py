"""#380: real reader/writer boundaries using captured CPI source shapes."""
import asyncio
import copy
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from models import Base, Country, EconomicIndicator, Extraction, SourceDocument
from routers import economic
from seeding.config import SeedingSettings
from seeding.domains.economic_indicators import fetcher, parser, writer
from seeding.types import DomainRunContext

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads(
    (
        ROOT
        / "docs/operations/2026-09-30-economic-evidence/cpi-correction-proposal.json"
    ).read_text()
)


@compiles(JSONB, "sqlite")
def jsonb_sqlite(element, compiler, **kw):
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Country(
                id=1,
                iso_code="KEN",
                name="Kenya",
                currency="KES",
                timezone="Africa/Nairobi",
                default_locale="en_KE",
            )
        )
        session.commit()
        yield session
    engine.dispose()


def insert_source(db, ref="knbs_jan2025"):
    source = MANIFEST["source_documents_to_allocate_or_reuse"][ref]
    doc = SourceDocument(
        country_id=1,
        publisher=source["publisher"],
        title=source["title"],
        url=source["url"],
        md5=source["md5"],
        doc_type="REPORT",
        status="AVAILABLE",
        fetch_date=datetime(2026, 9, 30),
        content_type="application/pdf",
        http_status=200,
        meta={
            "sha256": source["sha256"],
            "reviewed_table1_sha256": source["reviewed_table1_sha256"],
        },
    )
    db.add(doc)
    db.flush()
    payload = MANIFEST["extractions_to_allocate"][ref + "_table1"]
    extraction = Extraction(
        source_document_id=doc.id,
        page_number=2,
        extractor="manual_review",
        extracted_json=copy.deepcopy(payload["extracted_json"]),
    )
    db.add(extraction)
    db.flush()
    return doc, extraction


def indicator(db, *, value="142.68", approved=True, kind="CPI", **kwargs):
    doc, extraction = insert_source(db)
    row = EconomicIndicator(
        indicator_type=kind,
        indicator_date=datetime(2025, 1, 31),
        value=Decimal(value),
        unit="index_2019_02_100",
        source_document_id=doc.id,
        extraction_id=extraction.id,
        page_ref="p.2 / Table 1",
        source_page=2,
        source_hash=doc.meta["sha256"],
        publishable=approved,
        basis="ACTUAL",
        meta={
            "base_period": "2019-02",
            "frequency": "monthly",
            "measure": "overall consumer price index, February 2019 = 100",
            "publisher": doc.publisher,
        },
        **kwargs
    )
    db.add(row)
    db.commit()
    return row, doc, extraction


def read(db, **overrides):
    args = dict(
        indicator_type=None,
        entity_id=None,
        start_date=None,
        end_date=None,
        min_confidence=0,
        limit=100,
        db=db,
    )
    args.update(overrides)
    return asyncio.run(economic.get_economic_indicators(**args))


def test_explicit_unpublished_cpi_is_withheld(db):
    row, _, _ = indicator(db, approved=False)
    assert read(db) == [], "unpublished CPI must not appear as an official index"
    assert db.get(EconomicIndicator, row.id) is not None


@pytest.mark.parametrize(
    "damage",
    [
        "failed",
        "landing",
        "no_source",
        "no_extraction",
        "hash",
        "base",
        "value",
        "page",
        "bootstrap",
        "measure",
        "source_country",
        "quarantine",
    ],
)
def test_bad_source_cpi_is_withheld(db, damage):
    row, doc, ext = indicator(db)
    if damage == "failed":
        doc.status = "FAILED"
    elif damage == "landing":
        doc.url = "https://www.knbs.or.ke/consumer-price-indices/"
    elif damage == "no_source":
        row.source_document_id = None
    elif damage == "no_extraction":
        row.extraction_id = None
    elif damage == "hash":
        row.source_hash = "f" * 64
    elif damage == "base":
        row.meta = {**row.meta, "base_period": "2009-02"}
    elif damage == "value":
        row.value = Decimal("143.08")
    elif damage == "page":
        row.source_page = 1
    elif damage == "bootstrap":
        row.meta = {**row.meta, "bootstrap": True}
    elif damage == "measure":
        row.meta = {**row.meta, "measure": "CPI inflation, annual average"}
    elif damage == "source_country":
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
        doc.country_id = 2
    elif damage == "quarantine":
        row.quarantine_reason = "source conflict"
    db.commit()
    assert read(db) == [], damage


@pytest.mark.parametrize("value", ["142.68", "0"])
def test_matching_reviewed_source_and_zero_are_public(db, value):
    row, doc, ext = indicator(db, value=value)
    ext.extracted_json = {**ext.extracted_json, "observations": {"2025-01-31": value}}
    from services.publication_gate import cpi_extraction_digest

    doc.meta = {
        **doc.meta,
        "reviewed_table1_sha256": cpi_extraction_digest(ext.extracted_json),
    }
    db.commit()
    rows = read(db)
    assert [(r.id, r.value) for r in rows] == [(row.id, float(value))]
    assert rows[0].confidence == 1.0


def test_withheld_rows_do_not_starve_limit_or_change_annual_history(db):
    bad, _, _ = indicator(db, approved=False)
    annual = EconomicIndicator(
        indicator_type="inflation_rate",
        indicator_date=datetime(2024, 12, 31),
        value=0,
        unit="percent",
        meta={"measure": "CPI inflation, annual average"},
    )
    db.add(annual)
    db.commit()
    assert [(r.id, r.value) for r in read(db, limit=1)] == [(annual.id, 0)]
    assert db.get(EconomicIndicator, bad.id).value == Decimal("142.68")


def test_api_preserves_list_shape_and_explains_withholding(db):
    indicator(db, approved=False)
    app = FastAPI()
    app.include_router(economic.router)
    app.dependency_overrides[economic.get_db] = lambda: db
    with TestClient(app) as client:
        result = client.get(
            "/api/v1/economic/indicators?indicator_type=CPI&min_confidence=0"
        )
    assert result.status_code == 200 and result.json() == []
    assert result.headers["X-Economic-Withheld-Count"] == "1"
    assert "not approved" in result.headers["X-Economic-Withheld-Reasons"]


def test_fixture_supplement_cannot_reintroduce_bad_cpi(monkeypatch):
    legacy = MANIFEST["fixture_prerequisite"]["before"]
    monkeypatch.setattr(
        fetcher,
        "_fetch_wb_indicators",
        lambda client: [
            {
                "indicator_type": "cpi_index",
                "date": "2024-12-31",
                "value": 200,
                "unit": "index_2010_100",
            }
        ],
    )
    monkeypatch.setattr(
        fetcher, "_fetch_cbk", lambda client: ([], "synthetic absent CBK", [])
    )
    monkeypatch.setattr(
        fetcher, "load_json_resource", lambda **kw: [copy.deepcopy(legacy)]
    )
    payload = fetcher.fetch_economic_payload(None, SeedingSettings())
    assert all(r["indicator_type"].lower() != "cpi" for r in payload.records)
    assert payload.records[0]["unit"] == "index_2010_100"


def test_direct_legacy_writer_refuses_before_source_or_row_changes(db):
    existing = EconomicIndicator(
        id=67,
        indicator_type="cpi",
        indicator_date=datetime(2025, 1, 31),
        value=Decimal("142.68"),
        unit="index_2019_02_100",
        meta={"retained": "correction"},
    )
    db.add(existing)
    db.commit()
    records = parser.parse_economic_payload(
        [MANIFEST["fixture_prerequisite"]["before"]]
    )
    stats = writer.persist_economic_records(
        db, records, SeedingSettings(), DomainRunContext(since=None, dry_run=False)
    )
    db.commit()
    assert stats.errors and stats.skipped == 1
    assert db.get(EconomicIndicator, 67).value == Decimal("142.68")
    assert db.query(SourceDocument).count() == 0


def test_checked_in_fixture_has_no_unreviewed_cpi():
    fixture = json.loads(
        (ROOT / "backend/seeding/real_data/economic_indicators.json").read_text()
    )
    assert all(r["indicator_type"].lower() != "cpi" for r in fixture)


def test_county_profile_uses_same_gate_and_explains_absence(db, monkeypatch):
    from models import Entity, EntityType

    county = Entity(
        id=47,
        country_id=1,
        type=EntityType.COUNTY,
        canonical_name="Synthetic County",
        slug="synthetic-county",
    )
    db.add(county)
    db.commit()
    indicator(db, entity_id=47)
    db.add(
        EconomicIndicator(
            indicator_type="gdp_growth_rate",
            indicator_date=datetime(2025, 1, 31),
            value=0,
            unit="percent",
            entity_id=47,
        )
    )
    db.commit()

    class Clock(datetime):
        @classmethod
        def now(cls):
            return cls(2025, 6, 1)

    monkeypatch.setattr(economic, "datetime", Clock)
    profile = asyncio.run(economic.get_county_economic_profile(county_id=47, db=db))
    assert [
        (r.indicator_type, r.value, r.entity_name) for r in profile.economic_indicators
    ] == [("gdp_growth_rate", 0, "Synthetic County")]
    assert profile.withheld_indicator_count == 1
    assert profile.indicator_publication_notes == ["CPI base or measure conflict"]


@pytest.mark.parametrize(
    "damage",
    [
        "empty_meta",
        "empty_payload",
        "bool_observation",
        "nan_observation",
        "wrong_frequency",
        "credentials_url",
        "mixed_case_unapproved",
        "zero_confidence",
    ],
)
def test_adversarial_source_shapes_never_make_false_publication_claim(db, damage):
    row, doc, ext = indicator(db)
    if damage == "empty_meta":
        row.meta = {}
    elif damage == "empty_payload":
        ext.extracted_json = {}
    elif damage == "bool_observation":
        ext.extracted_json = {
            **ext.extracted_json,
            "observations": {"2025-01-31": True},
        }
    elif damage == "nan_observation":
        ext.extracted_json = {
            **ext.extracted_json,
            "observations": {"2025-01-31": "NaN"},
        }
    elif damage == "wrong_frequency":
        row.meta = {**row.meta, "frequency": "annual"}
    elif damage == "credentials_url":
        doc.url = (
            "https://attacker@www.knbs.or.ke/wp-content/uploads/2025/01/release.pdf"
        )
    elif damage == "mixed_case_unapproved":
        row.indicator_type = "CpI"
        row.publishable = False
    else:
        row.confidence = 0
    db.commit()
    rows = read(db)
    if damage == "zero_confidence":
        assert len(rows) == 1 and rows[0].confidence == 0
    else:
        assert rows == []


def test_public_source_fields_match_reviewed_chain(db):
    row, doc, _ = indicator(db)
    published = read(db)[0]
    assert (
        published.source_url,
        published.source_hash,
        published.page_ref,
        published.base_period,
        published.publication_status,
    ) == (doc.url, row.source_hash, "p.2 / Table 1", "2019-02", "source_bound")


def test_matching_row_and_extraction_drift_does_not_keep_old_source_approval(db):
    row, _, ext = indicator(db)
    row.value = Decimal("143.08")
    ext.extracted_json = {
        **ext.extracted_json,
        "observations": {"2025-01-31": "143.08", "2024-12-31": "141.66"},
    }
    db.commit()
    assert (
        read(db) == []
    ), "matching two changed fields does not prove unchanged PDF evidence"


def test_added_source_fields_do_not_break_legacy_finite_observations(db):
    row = EconomicIndicator(
        indicator_type="inflation_rate",
        indicator_date=datetime(2024, 12, 31),
        value=4.5,
        unit="percent",
        meta={"measure": {"unknown_schema": True}, "base_period": 2010},
    )
    db.add(row)
    db.commit()
    published = read(db)[0]
    assert (
        published.value == 4.5
        and published.measure is None
        and published.base_period is None
    )
    assert published.publication_status == "not_checked_here"
