"""Stored app artefacts cannot inflate the public publisher inventory."""

from datetime import datetime, timezone

import pytest
from models import DocumentStatus, DocumentType, Extraction, SourceDocument


@pytest.mark.parametrize(
    "metadata",
    [
        {"dataset_id": "fixture-budgets"},
        {"dataset_id": "  FIXTURE-BUDGETS  "},
        {
            "data_quality": "estimated",
            "source_label": "Estimated based on CRA Equitable Share FY 2023/24",
        },
        {"source_classification": "test_fixture"},
        {"source_classification": "modelled_estimate"},
    ],
)
def test_app_origins_do_not_count_as_publisher_documents(
    client, db_session, seed_country, metadata
):
    now = datetime.now(timezone.utc)
    official = SourceDocument(
        country_id=seed_country.id,
        publisher="Controller of Budget",
        title="CBIRR",
        url="https://cob.go.ke/official.pdf",
        doc_type=DocumentType.BUDGET,
        fetch_date=now,
        last_seen_at=datetime(2024, 1, 1),
        meta={},
    )
    artifact = SourceDocument(
        country_id=seed_country.id,
        publisher="Controller of Budget",
        title="Generated",
        url="https://fixtures.example/budgets",
        doc_type=DocumentType.REPORT,
        fetch_date=now,
        last_seen_at=now,
        meta=metadata,
        md5="a" * 32,
        http_status=200,
        last_verified_at=now,
    )
    db_session.add_all([official, artifact])
    db_session.flush()
    db_session.add(
        Extraction(
            source_document_id=artifact.id,
            page_number=1,
            extracted_json={"fixture": True},
            extractor="fixture",
            confidence=1,
        )
    )
    db_session.commit()
    response = client.get("/api/v1/sources/summary")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["total_documents"] == 1
    row = result["sources"][0]
    assert row["document_count"] == 1
    assert row["doc_types"] == {"budget": 1}
    assert row["downloaded_documents"] == 0
    assert row["extracted_documents"] == 0
    assert row["last_fetched"] is None
    assert row["last_seen_at"] == "2024-01-01T00:00:00"
    assert db_session.query(SourceDocument).count() == 2


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        {},
        {"data_quality": "estimated"},
        {"source_label": "Treasury approved budget estimates"},
        {"notes": "fixture-budgets"},
        {"source_classification": "official_document"},
    ],
)
def test_official_archives_and_estimates_remain_in_inventory(
    client, db_session, seed_country, metadata
):
    db_session.add(
        SourceDocument(
            country_id=seed_country.id,
            publisher="National Treasury",
            title="Budget estimates",
            url="https://treasury.go.ke/budget.pdf",
            doc_type=DocumentType.BUDGET,
            fetch_date=datetime.now(timezone.utc),
            status=DocumentStatus.ARCHIVED,
            meta=metadata,
        )
    )
    db_session.commit()
    response = client.get("/api/v1/sources/summary")
    assert response.status_code == 200, response.text
    assert response.json()["total_documents"] == 1


def test_only_app_archives_have_no_public_publisher_group(
    client, db_session, seed_country
):
    db_session.add(
        SourceDocument(
            country_id=seed_country.id,
            publisher="AuditGava (modelled estimate)",
            title="Historical model",
            url="https://www.crakenya.org/county-allocations/",
            doc_type=DocumentType.BUDGET,
            fetch_date=datetime.now(timezone.utc),
            status=DocumentStatus.ARCHIVED,
            meta={"source_classification": "modelled_estimate"},
        )
    )
    db_session.commit()
    response = client.get("/api/v1/sources/summary")
    assert response.status_code == 200, response.text
    assert response.json() == {"sources": [], "total_documents": 0}
