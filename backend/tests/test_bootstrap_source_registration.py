"""Bootstrap registration cannot claim an unperformed publisher download (#652)."""
from datetime import datetime

import pytest
from sqlalchemy import select

import bootstrap
from models import DocumentStatus, DocumentType, SourceDocument


@pytest.mark.parametrize("url", [None, "", "https://publisher.example.invalid/report.pdf"])
def test_new_bootstrap_registration_is_not_an_available_download(
    db_session, seed_country, url
):
    document = bootstrap._ensure_source_document(
        db_session,
        country_id=seed_country.id,
        title="Owned bootstrap registration",
        publisher="Owned fixture",
        doc_type=DocumentType.LOAN,
        fetch_date=datetime(2025, 4, 30),
        metadata={"source": "bootstrap", "url": url},
    )
    db_session.expire(document)
    assert document.status == DocumentStatus.FAILED
    assert document.url == url
    assert document.md5 is None
    assert document.http_status is None
    assert document.last_verified_at is None


@pytest.mark.parametrize("status", list(DocumentStatus))
def test_refresh_preserves_document_identity_and_acquisition_evidence(
    db_session, seed_country, status
):
    # FAILED/no-URL is the actual migrated legacy shape. AVAILABLE and ARCHIVED
    # exercise preservation of existing acquisition history, not a new fetch.
    url = None if status == DocumentStatus.FAILED else "https://publisher.example.invalid/existing.pdf"
    verified = None if url is None else datetime(2025, 5, 1)
    document = SourceDocument(
        country_id=seed_country.id,
        title="Owned legacy registration",
        publisher="Original publisher",
        doc_type=DocumentType.LOAN,
        status=status,
        url=url,
        fetch_date=datetime(2025, 5, 1),
        md5=None if url is None else "a" * 32,
        http_status=None if url is None else 200,
        last_verified_at=verified,
        meta={"status_before_3c": "AVAILABLE", "preserved": True},
    )
    db_session.add(document)
    db_session.flush()
    identity = document.id
    evidence = (document.status, document.url, document.md5, document.fetch_date,
                document.http_status, document.last_verified_at)
    refreshed = bootstrap._ensure_source_document(
        db_session,
        country_id=seed_country.id,
        title=document.title,
        publisher="Bootstrap does not replace publisher",
        doc_type=DocumentType.LOAN,
        fetch_date=datetime(2025, 4, 30),
        metadata={"source": "bootstrap", "scope": "national"},
    )
    db_session.expire(refreshed)
    assert refreshed.id == identity
    assert refreshed.publisher == "Original publisher"
    assert (refreshed.status, refreshed.url, refreshed.md5, refreshed.fetch_date,
            refreshed.http_status, refreshed.last_verified_at) == evidence
    assert refreshed.meta == {
        "status_before_3c": "AVAILABLE", "preserved": True,
        "source": "bootstrap", "scope": "national",
    }
    assert len(db_session.scalars(select(SourceDocument)).all()) == 1


def test_actual_national_bootstrap_registers_an_unfetched_source(
    db_session, seed_country
):
    period = bootstrap._ensure_fiscal_period(db_session, seed_country.id)
    bootstrap._seed_national_data(db_session, country=seed_country, period=period)
    (document,) = db_session.scalars(select(SourceDocument)).all()
    assert document.status == DocumentStatus.FAILED
    assert document.url is None
    assert document.md5 is None
    assert document.http_status is None
    assert document.last_verified_at is None
    assert document.meta["source"] == "bootstrap"
