"""County scorecard withholding must not claim every row lacks a URL."""

from datetime import datetime, timezone

import pytest

from models import (
    Audit,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    Severity,
    SourceDocument,
)


@pytest.fixture()
def county(db_session, seed_country):
    row = Entity(
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Nairobi County",
        slug="nairobi-withholding-reason",
    )
    db_session.add(row)
    db_session.flush()
    return row


def _finding(db, country_id, entity_id, period_id, *, url, page):
    doc = SourceDocument(
        country_id=country_id,
        publisher="Synthetic OAG",
        title="Synthetic county report",
        url=url,
        fetch_date=datetime(2025, 12, 1, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,
    )
    db.add(doc)
    db.flush()
    db.add(
        Audit(
            entity_id=entity_id,
            period_id=period_id,
            source_document_id=doc.id,
            finding_text="Synthetic audit finding",
            severity=Severity.WARNING,
            page_ref=page,
        )
    )
    db.commit()


@pytest.mark.parametrize("with_missing_url", [False, True])
def test_non_url_and_mixed_withholding_are_described_honestly(
    client, db_session, seed_country, seed_fiscal_period, county, with_missing_url
):
    _finding(
        db_session,
        seed_country.id,
        county.id,
        seed_fiscal_period.id,
        url="https://example.invalid/report.pdf",
        page=None,
    )
    if with_missing_url:
        _finding(
            db_session,
            seed_country.id,
            county.id,
            seed_fiscal_period.id,
            url=None,
            page="p. 7",
        )

    response = client.get("/api/v1/counties/001/accountability")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_findings"] == 0
    assert data["withheld"] == {
        "count": 2 if with_missing_url else 1,
        "reason": "publication_requirements_not_met",
    }
    assert data["accountability_grade"] is None
    detail = data["grade_factors"][0]["detail"]
    assert "publication" in detail.lower()
    assert "has no URL" not in detail


def test_no_withholding_has_no_withholding_reason(
    client, db_session, seed_country, seed_fiscal_period, county
):
    _finding(
        db_session,
        seed_country.id,
        county.id,
        seed_fiscal_period.id,
        url="https://example.invalid/report.pdf",
        page="p. 7",
    )
    response = client.get("/api/v1/counties/001/accountability")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_findings"] == 1
    assert data["withheld"] == {"count": 0, "reason": None}
