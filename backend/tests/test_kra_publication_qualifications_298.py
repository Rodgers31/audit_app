"""Source-shaped observations through the real enhanced API, using SQLite only."""
import gzip
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from models import DocumentType, RevenueBySource, SourceDocument
from seeding.domains.revenue_by_source.fetcher import _overlay_kra_release
from seeding.domains.revenue_by_source.kra_discovery import parse_dashboard_bundle
from seeding.domains.revenue_by_source.parser import parse_revenue_payload


def _source(db, country):
    source = SourceDocument(
        country_id=country.id, publisher="Synthetic KRA fixture; not a refresh",
        title="Accepted artifact in isolated SQLite", url="https://example.invalid/kra-fixture",
        fetch_date=datetime(2026, 9, 27, tzinfo=timezone.utc), doc_type=DocumentType.REPORT,
    )
    db.add(source)
    db.flush()
    return source


def test_accepted_edition_qualifications_survive_the_actual_api(client, db_session, seed_country):
    with gzip.open(Path(__file__).parent / "fixtures/kra/fy2025_26_dashboard_bundle.js.gz", "rt") as stream:
        release = parse_dashboard_bundle(
            stream.read(), url="https://www.kra.go.ke/annual-revenue-performance-fy-2025-2026",
            data_url="https://krarevenue2526testingdashboard.bolt.host/assets/index-n9eGcpF_.js",
        )
    release.retrieved_at = "2026-09-27T00:00:00+00:00"
    release.content_sha256 = "f3cf2fd1075f4af3eb0aafb92ed6c8a1e336437b2603a9dc67a28283561d03d7"
    records = parse_revenue_payload(_overlay_kra_release([], release)[0])
    source = _source(db_session, seed_country)
    for record in records:
        db_session.add(RevenueBySource(
            fiscal_year=record.fiscal_year,
            revenue_type=record.revenue_type, category=record.category,
            amount_billion_kes=record.amount_billion_kes,
            source_document_id=source.id, meta=record.metadata,
        ))
    db_session.flush()
    response = client.get("/api/v1/budget/enhanced")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["_meta"]["revenue_by_source_unit"] == "billion_kes"
    fy, = body["revenue_by_source"]
    assert fy["fiscal_year"] == release.fiscal_year
    rows = {row["revenue_type"]: row for row in fy["sources"]}
    for record in records:
        row = rows[record.revenue_type]
        assert row["share_pct"] is None
        assert row["source"] == record.metadata.get("source")
        if record.amount_billion_kes is not None:
            assert row["amount"] == float(record.amount_billion_kes)
            assert row["source"]["period"] == release.fiscal_year
            assert row["source"]["version"] == "dashboard_bundle"
            assert row["source"]["publication_date"] is None
            assert "not independently reconciled" in row["source"]["reconciliation"]
    assert rows["PAYE"]["source"]["stated_amount_billion_kes"] == "598.807"
    assert Decimal(rows["Customs & Import Duty"]["source"]["stated_amount_billion_kes"]) == Decimal("988.780")
    assert rows["Other Tax Revenue"]["amount"] is None
    assert rows["Other Tax Revenue"]["absent_reason"]


def test_partial_zero_and_missing_locator_keep_their_own_qualifications(client, db_session, seed_country):
    source = _source(db_session, seed_country)
    for fy, name, amount, meta in [
        ("FY 2024/25", "PAYE", Decimal("560.963"), {"basis": "published", "source": {
            "url": "https://example.invalid/older-edition", "period": "FY 2024/25", "version": "press_release",
        }}),
        ("FY 2025/26", "PAYE", Decimal("0"), {"basis": "published", "source": {
            "period": "FY 2025/26", "version": "dashboard_bundle", "publication_date": None,
            "reconciliation": "Synthetic conflicting-version evidence; no preferred edition.",
        }}),
        ("FY 2025/26", "VAT", None, {"absent_reason": "No source observation"}),
        ("FY 2025/26", "Other Tax Revenue", Decimal("216.247"), {"basis": "residual"}),
    ]:
        db_session.add(RevenueBySource(
            fiscal_year=fy, revenue_type=name, category="tax",
            amount_billion_kes=amount, source_document_id=source.id, meta=meta,
        ))
    db_session.flush()
    response = client.get("/api/v1/budget/enhanced")
    assert response.status_code == 200, response.text
    older, current = response.json()["revenue_by_source"]
    assert older["sources"][0]["source"]["period"] == older["fiscal_year"]
    rows = {row["revenue_type"]: row for row in current["sources"]}
    assert rows["PAYE"]["amount"] == 0
    assert rows["PAYE"]["source"]["period"] == current["fiscal_year"]
    assert rows["PAYE"]["source_absent_reason"]
    assert "conflicting-version" in rows["PAYE"]["source"]["reconciliation"]
    assert rows["VAT"]["amount"] is None and rows["VAT"]["source"] is None
    assert rows["Other Tax Revenue"]["amount"] is None
    assert all(row["share_pct"] is None for row in rows.values())


@pytest.mark.parametrize("locator", [{}, {"data_url": "https://example.invalid/captured-bundle.js"}])
def test_missing_publisher_url_does_not_deny_recorded_version_or_date(client, db_session, seed_country, locator):
    source = _source(db_session, seed_country)
    metadata = {
        **locator, "version": "dashboard_bundle", "period": "FY 2025/26",
        "retrieved_at": "2026-09-27T00:00:00Z", "publication_date": None,
        "reconciliation": "Synthetic edition disagreement; preserve both statements.",
    }
    db_session.add(RevenueBySource(
        fiscal_year="FY 2025/26", revenue_type="PAYE", category="tax",
        amount_billion_kes=Decimal("0"), source_document_id=source.id,
        meta={"basis": "published", "source": metadata},
    ))
    db_session.flush()
    response = client.get("/api/v1/budget/enhanced")
    assert response.status_code == 200, response.text
    row, = response.json()["revenue_by_source"][0]["sources"]
    assert row["source"] == metadata and row["amount"] == 0
    assert row["source_absent_reason"] == (None if locator else "Source URL is not recorded for this row.")
