"""Opt-in pinned-PDF cash parser -> PostgreSQL writer -> public account checks.

Set COUNTY_CASH_TEST_POSTGRES_URL to an owned loopback database and
COUNTY_CASH_SOURCE_PDF to the original annual CoB artifact. Neither production
settings nor dotenv credentials authorize this fixture.
"""
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from models import Base, BudgetLine, Country, Entity, EntityType
from seeding.config import SeedingSettings
from seeding.domains.counties_budget import fetcher, parser, writer
from seeding.pdf_parsers import CoBQuarterlyReportParser, ExtractedTable
from seeding.types import DomainRunContext
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

SHA = "5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3"
FIXTURE = Path(__file__).parent / "fixtures/cbirr_annual_cash_layouts.json"


@pytest.fixture
def cash_postgres():
    raw_url = os.environ.get("COUNTY_CASH_TEST_POSTGRES_URL")
    if not raw_url:
        pytest.skip("owned PostgreSQL URL was not supplied")
    url = make_url(raw_url)
    if (
        url.get_backend_name() != "postgresql"
        or url.host != "127.0.0.1"
        or url.port is None
        or not url.database
        or not (url.database == "round8_s5" or url.database.startswith("round8_s5_"))
        or url.query
    ):
        pytest.fail(
            "cash persistence test requires an explicitly owned loopback round8_s5 database"
        )
    schema = "round8_s5_cash_" + uuid4().hex
    driver = {
        "hostaddr": "127.0.0.1",
        "sslmode": "disable",
        "gssencmode": "disable",
        "connect_timeout": 3,
    }
    admin = create_engine(url, connect_args=driver)
    engine = None
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(
            url,
            connect_args={
                **driver,
                "options": f"-csearch_path={schema} -cstatement_timeout=10000 -clock_timeout=5000",
            },
        )
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            yield session
    finally:
        if engine is not None:
            engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


@pytest.mark.parametrize(
    "county,total,equitable,local",
    [
        ("Kisii", "16499037626", "9819721768", "2486891009"),
        ("Kisumu", "13360566017.46", "8902026938", "1591040253"),
        ("Kitui", "13809805963", "11503907836", "968156610"),
    ],
)
def test_recovered_cash_survives_real_persistence_and_public_account(
    cash_postgres,
    tmp_path,
    county,
    total,
    equitable,
    local,
):
    pdf_value = os.environ.get("COUNTY_CASH_SOURCE_PDF")
    if not pdf_value:
        pytest.skip("checksum-pinned source PDF was not supplied")
    pdf = Path(pdf_value)
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == SHA
    source = json.loads(FIXTURE.read_text())
    assert source["source_sha256"] == SHA
    cash_parser = CoBQuarterlyReportParser(pdf)
    # The exact extracted source rows are pinned in the default regression
    # suite; here the actual parser reads county ownership and report period
    # from the original PDF before supplying its cash records to the fetcher.
    cash_parser.tables = [
        ExtractedTable(**t) for ts in source["tables"].values() for t in ts
    ]
    raw_records = cash_parser._extract_county_revenue_receipts()
    raw_records = [r for r in raw_records if r["county"] == county]
    assert raw_records
    settings = SeedingSettings(
        cache_path=tmp_path, live_pdf_fetch_enabled=False, enrich_with_worldbank=False
    )
    with patch(
        "seeding.cob_cbirr.download_cbirr",
        return_value=SimpleNamespace(path=pdf, sha256=SHA),
    ), patch(
        "seeding.parse_cache.parse_with_cache",
        return_value=raw_records,
    ):
        payload = fetcher._download_and_parse_county_pdf(
            None, source["source_url"], settings
        )
    normalized = parser.parse_budget_payload(payload)
    assert len(normalized) == len(raw_records)
    session = cash_postgres
    country_row = Country(
        iso_code="KEN",
        name="Kenya",
        currency="KES",
        timezone="Africa/Nairobi",
        default_locale="en_KE",
    )
    session.add(country_row)
    session.flush()
    slug = county.lower() + "-county"
    entity = Entity(
        country_id=country_row.id,
        type=EntityType.COUNTY,
        canonical_name=county + " County",
        slug=slug,
    )
    session.add(entity)
    session.flush()
    stats = writer.persist_budget_records(
        session, normalized, settings, DomainRunContext(since=None, dry_run=False)
    )
    assert stats.created == len(raw_records) and stats.skipped == 0 and not stats.errors
    session.commit()
    session.expire_all()
    rows = session.scalars(
        select(BudgetLine).where(BudgetLine.entity_id == entity.id)
    ).all()
    total_row = next(r for r in rows if r.subcategory == "Total")
    assert total_row.actual_spent == Decimal(total)
    assert all(r.currency == "KES" and r.page_ref for r in rows)
    assert all(r.provenance[-1]["artifact_sha256"] == SHA for r in rows)
    assert total_row.source_document.url == source["source_url"]
    assert total_row.source_document.publisher == "Controller of Budget"
    assert total_row.period.label == "FY2025/26"

    from database import get_db
    from main import app, clear_all_caches

    def owned_db():
        yield session

    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = owned_db
    clear_all_caches()
    try:
        with patch("main.get_db", owned_db):
            client = TestClient(app)
            response = client.get(f"/api/v1/counties/{slug}/comprehensive")
        assert response.status_code == 200, response.text[:300]
        revenue = response.json()["revenue"]
        assert Decimal(str(revenue["total_revenue"])) == Decimal(total)
        assert Decimal(str(revenue["equitable_share"])) == Decimal(equitable)
        assert Decimal(str(revenue["local_revenue"])) == Decimal(local)
        assert revenue["fiscal_year"] == "FY2025/26"
        assert (
            revenue["total_revenue_basis"] == "cash_receipts_including_opening_balance"
        )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        clear_all_caches()
