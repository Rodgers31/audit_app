"""Discovery and a successful fetch are not publication acceptance."""

from datetime import date, datetime, timedelta, timezone

import pytest
from models import DocumentType, SourceDocument, BudgetLine


def document(db, country, **kw):
    values = dict(
        country_id=country.id,
        publisher="Controller of Budget",
        title="CBIRR",
        url="https://cob.go.ke/report.pdf",
        doc_type=DocumentType.BUDGET,
        fetch_date=datetime.now(timezone.utc),
        meta={},
    )
    values.update(kw)
    doc = SourceDocument(**values)
    db.add(doc)
    db.commit()
    return doc


def source(client, code="COB"):
    res = client.get("/api/v1/data/freshness")
    assert res.status_code == 200, res.text
    return next(s for s in res.json()["sources"] if s["source"] == code)


def test_registration_does_not_make_a_publisher_fresh(client, db_session, seed_country):
    document(db_session, seed_country)
    result = source(client)
    assert result["status"] == "unknown"
    assert result["last_updated"] is None
    assert result["last_checked"] is None


@pytest.mark.parametrize("accepted", [False, True])
def test_only_accepted_rows_contribute_publication_vintage(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, accepted
):
    old = (datetime.now(timezone.utc) - timedelta(days=500)).date().isoformat()
    doc = document(db_session, seed_country, meta={"publication_date": old})
    db_session.add(
        BudgetLine(
            entity_id=seed_entity.id,
            period_id=seed_fiscal_period.id,
            category="Total",
            allocated_amount=100,
            currency="KES",
            source_document_id=doc.id,
            publishable=accepted,
        )
    )
    db_session.commit()
    # Discovery of a newer report must not refresh existing accepted data.
    document(
        db_session,
        seed_country,
        meta={"publication_date": datetime.now(timezone.utc).date().isoformat()},
    )
    result = source(client)
    assert result["status"] == ("outdated" if accepted else "unknown")
    assert result["last_updated"] == (old if accepted else None)
    assert result["covers_through"] == (seed_fiscal_period.label if accepted else None)


def test_download_is_reported_separately_from_publication(
    client, db_session, seed_country
):
    document(
        db_session,
        seed_country,
        md5="a" * 32,
        http_status=200,
        last_verified_at=datetime.now(timezone.utc),
        meta={"publication_date": datetime.now(timezone.utc).date().isoformat()},
    )
    result = source(client)
    assert result["status"] == "unknown"
    assert result["last_checked"] is not None
    assert result["last_updated"] is None


def test_summary_does_not_call_registration_a_download(
    client, db_session, seed_country
):
    document(db_session, seed_country)
    result = client.get("/api/v1/sources/summary")
    assert result.status_code == 200, result.text
    row = result.json()["sources"][0]
    assert row["document_count"] == 1
    assert row["last_fetched"] is None
    assert row["downloaded_documents"] == 0


def test_public_api_responses_cannot_reuse_old_http_bodies_after_invalidation(client):
    response = client.get("/api/v1/data/freshness")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_public_api_error_cannot_be_cached_as_the_result_of_a_later_refresh(client):
    response = client.get("/api/v1/this-route-does-not-exist")
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "publication,publisher",
    [
        (
            datetime.now(timezone.utc).date().isoformat() + "-garbage",
            "Controller of Budget",
        ),
        (datetime.now(timezone.utc).date().isoformat(), "A SCRAPED COPY"),
    ],
)
def test_malformed_date_or_publisher_cannot_certify_fresh(
    client,
    db_session,
    seed_country,
    seed_entity,
    seed_fiscal_period,
    publication,
    publisher,
):
    doc = document(
        db_session,
        seed_country,
        publisher=publisher,
        meta={"publication_date": publication},
    )
    db_session.add(
        BudgetLine(
            entity_id=seed_entity.id,
            period_id=seed_fiscal_period.id,
            category="Total",
            allocated_amount=100,
            currency="KES",
            source_document_id=doc.id,
            publishable=True,
        )
    )
    db_session.commit()
    assert all(
        row["status"] == "unknown"
        for row in client.get("/api/v1/data/freshness").json()["sources"]
    )


@pytest.mark.parametrize("digest,days", [(" ", 0), ("z" * 32, 0), ("a" * 32, 365)])
def test_malformed_transport_evidence_is_not_a_verified_download(
    client, db_session, seed_country, digest, days
):
    document(
        db_session,
        seed_country,
        md5=digest,
        http_status=200,
        last_verified_at=datetime.now(timezone.utc) + timedelta(days=days),
    )
    assert source(client)["last_checked"] is None
    row = client.get("/api/v1/sources/summary").json()["sources"][0]
    assert row["downloaded_documents"] == 0


@pytest.mark.parametrize("publication", [True, {}, [], 10**100, "2026-02-31"])
def test_malformed_publication_cannot_crash_freshness(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, publication
):
    doc = document(db_session, seed_country, meta={"publication_date": publication})
    db_session.add(
        BudgetLine(
            entity_id=seed_entity.id,
            period_id=seed_fiscal_period.id,
            category="Total",
            allocated_amount=100,
            currency="KES",
            source_document_id=doc.id,
            publishable=True,
        )
    )
    db_session.commit()
    assert source(client)["status"] == "unknown"


@pytest.mark.parametrize(
    "publisher", ["Controller of Budget", "Office of the Controller of Budget (OCOB)"]
)
def test_accepted_recent_publication_remains_fresh(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, publisher
):
    doc = document(
        db_session,
        seed_country,
        publisher=publisher,
        meta={"publication_date": datetime.now(timezone.utc).date().isoformat()},
        md5="a" * 32,
        http_status=200,
        last_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(
        BudgetLine(
            entity_id=seed_entity.id,
            period_id=seed_fiscal_period.id,
            category="Total",
            allocated_amount=0,
            currency="KES",
            source_document_id=doc.id,
            publishable=True,
        )
    )
    db_session.commit()
    result = source(client)
    assert result["status"] == "fresh"
    assert result["covers_through"] == seed_fiscal_period.label
    row = client.get("/api/v1/sources/summary").json()["sources"][0]
    assert row["downloaded_documents"] == 1
    assert row["last_fetched"] is not None


def test_no_content_is_not_a_download(client, db_session, seed_country):
    document(
        db_session,
        seed_country,
        md5="a" * 32,
        http_status=204,
        last_verified_at=datetime.now(timezone.utc),
    )
    assert source(client)["last_checked"] is None


def test_future_instant_with_an_earlier_local_date_is_not_published(
    client, db_session, seed_country, seed_entity, seed_fiscal_period
):
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).astimezone(
        timezone(timedelta(hours=-12))
    )
    doc = document(
        db_session, seed_country, meta={"publication_date": future.isoformat()}
    )
    db_session.add(
        BudgetLine(
            entity_id=seed_entity.id,
            period_id=seed_fiscal_period.id,
            category="Total",
            allocated_amount=100,
            currency="KES",
            source_document_id=doc.id,
            publishable=True,
        )
    )
    db_session.commit()
    assert source(client)["status"] == "unknown"


@pytest.mark.parametrize(
    "published_at,expected_date,expected_status",
    [
        ("2026-09-28T00:30:00+03:00", "2026-09-28", "fresh"),
        ("2026-09-28T02:00:00+03:00", None, "unknown"),
    ],
)
def test_publisher_midnight_uses_the_instant_before_judging_its_local_date(
    client,
    db_session,
    seed_country,
    seed_entity,
    seed_fiscal_period,
    monkeypatch,
    published_at,
    expected_date,
    expected_status,
):
    from routers import data_freshness

    class FrozenDate(date):
        @classmethod
        def today(cls):
            return date(2026, 9, 27)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = datetime(2026, 9, 27, 22, 0, tzinfo=timezone.utc)
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

    monkeypatch.setattr(data_freshness, "date", FrozenDate)
    monkeypatch.setattr(data_freshness, "datetime", FrozenDateTime)
    doc = document(db_session, seed_country, meta={"publication_date": published_at})
    db_session.add(
        BudgetLine(
            entity_id=seed_entity.id,
            period_id=seed_fiscal_period.id,
            category="Total",
            allocated_amount=100,
            currency="KES",
            source_document_id=doc.id,
            publishable=True,
        )
    )
    db_session.commit()
    result = source(client)
    assert result["last_updated"] == expected_date
    assert result["status"] == expected_status
