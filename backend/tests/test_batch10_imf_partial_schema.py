"""Optional IMF absence must not abort real PostgreSQL reader transactions."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from models import (
    Base,
    Country,
    DebtCategory,
    DebtTimeline,
    DocumentType,
    Entity,
    EntityType,
    FiscalSummary,
    GDPData,
    ImfWeoObservation,
    Loan,
    SourceDocument,
)


@pytest.fixture(scope="module")
def optional_imf_postgres():
    from batch10_readiness_fixture.postgres import postgres

    with postgres() as url:
        yield url


@pytest.fixture
def db_session(optional_imf_postgres):
    schema = "batch10_partial_imf_" + uuid4().hex
    admin = create_engine(optional_imf_postgres)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(optional_imf_postgres).update_query_dict(
        {"options": "-csearch_path=" + schema}
    )
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    ImfWeoObservation.__table__.drop(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture(autouse=True)
def inert_providers(monkeypatch):
    import main

    monkeypatch.setattr(main, "_imf_fetch_debt_to_gdp", lambda *a, **kw: {})
    monkeypatch.setattr(main, "_wb_fetch_indicator", lambda *a, **kw: {})
    main._peers_cache.update(ts=0.0, data=None)
    yield
    main._peers_cache.update(ts=0.0, data=None)


def seed_fiscal(db):
    db.add(
        FiscalSummary(
            fiscal_year="FY 2025/26",
            appropriated_budget=100,
            total_revenue=70,
            total_borrowing=30,
            county_allocation=10,
            unit="KES",
            page_ref="PDF p.1",
        )
    )
    db.commit()


def seed_timeline(db):
    db.add(
        DebtTimeline(
            year=2025, external=30, domestic=30, total=60, gdp=100, gdp_ratio=60
        )
    )
    db.commit()


@pytest.mark.parametrize("seeded", ["none", "timeline", "fiscal", "both"])
def test_sustainability_optional_imf_table_absent_keeps_partial_response(
    client, db_session, seeded
):
    if seeded in {"timeline", "both"}:
        seed_timeline(db_session)
    if seeded in {"fiscal", "both"}:
        seed_fiscal(db_session)
    result = client.get("/api/v1/debt/sustainability")
    assert result.status_code == 200, (
        "PARTIAL_IMF_SCHEMA_CAUSES_HTTP_500: " + result.text
    )
    body = result.json()
    assert body["projections"] == [] and body["projections_source"] is None
    assert body["projections_absent_reason"] == "no_published_projection_seeded"
    assert body["status"] == ("no_data" if seeded == "none" else "success")
    if seeded in {"timeline", "both"}:
        assert body["debt_to_gdp"]["value"] == 60
        assert (
            body["debt_to_gdp"]["source"]
            == "CBK Annual Reports / National Treasury BPS"
        )
    else:
        assert body["debt_to_gdp"] is None
    assert (
        db_session.scalar(text("SELECT 1")) == 1
    ), "OPTIONAL_IMF_QUERY_ABORTED_TRANSACTION"


@pytest.mark.parametrize("helper", ["headline", "projection"])
def test_optional_imf_helpers_preserve_real_transaction(db_session, helper):
    import main

    result = (
        main._latest_imf_debt_to_gdp(db_session)
        if helper == "headline"
        else main._published_debt_projections(db_session)
    )
    assert result == (
        None if helper == "headline" else ([], None, "no_published_projection_seeded")
    )
    assert (
        db_session.scalar(text("SELECT 1")) == 1
    ), "OPTIONAL_IMF_QUERY_ABORTED_TRANSACTION"


def test_fiscal_optional_imf_absence_keeps_transaction_usable(client, db_session):
    seed_fiscal(db_session)
    result = client.get("/api/v1/fiscal/summary")
    assert result.status_code == 200, result.text
    assert result.json()["debt_anchor"]["debt_to_gdp_pct"] is None
    assert (
        db_session.scalar(text("SELECT 1")) == 1
    ), "OPTIONAL_IMF_QUERY_ABORTED_TRANSACTION"


def test_national_debt_optional_imf_absence_preserves_fallback_and_provenance(
    client, db_session
):
    country = Country(
        iso_code="KEN",
        name="Kenya",
        currency="KES",
        timezone="Africa/Nairobi",
        default_locale="en_KE",
    )
    db_session.add(country)
    db_session.flush()
    doc = SourceDocument(
        country_id=country.id,
        publisher="Synthetic Treasury",
        title="Synthetic debt source",
        fetch_date=datetime(2025, 1, 1),
        doc_type=DocumentType.REPORT,
        meta={"publication_date": "2025-01-01"},
    )
    entity = Entity(
        country_id=country.id,
        type=EntityType.NATIONAL,
        canonical_name="Synthetic National Treasury",
        slug="synthetic-national",
    )
    db_session.add_all([doc, entity])
    db_session.flush()
    db_session.add_all(
        [
            Loan(
                entity_id=entity.id,
                lender="Synthetic Treasury Bonds",
                debt_category=DebtCategory.DOMESTIC_BONDS,
                principal=60,
                outstanding=60,
                issue_date=datetime(2025, 1, 1),
                currency="KES",
                source_document_id=doc.id,
            ),
            GDPData(year=2025, gdp_value=100, source_document_id=doc.id),
        ]
    )
    db_session.commit()
    result = client.get("/api/v1/debt/national")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["data"].get("debt_to_gdp_ratio") == 60, (
        "OPTIONAL_IMF_ABSENCE_LOST_REAL_DEBT_FALLBACK: " + result.text
    )
    assert body["data"]["debt_to_gdp_year"] == 2025
    assert body["data"]["debt_to_gdp_source"] == "CBK / World Bank"
    assert body["last_updated"].startswith("2025-01-01")


def test_broader_debt_optional_imf_absence_is_not_seeded(client, db_session):
    result = client.get("/api/v1/debt/broader")
    assert result.status_code == 200, (
        "OPTIONAL_IMF_ABSENCE_CAUSES_BROADER_500: " + result.text
    )
    assert result.json() == {"status": "unavailable", "reason": "not_seeded_yet"}
    assert db_session.scalar(text("SELECT 1")) == 1


@pytest.mark.parametrize(
    "reader", ["headline", "projection", "sustainability", "broader"]
)
def test_present_imf_table_preserves_real_actuals_and_forecasts(
    client, db_session, reader
):
    import main

    ImfWeoObservation.__table__.create(db_session.get_bind())
    vintage = datetime(2026, 10, 1, tzinfo=timezone.utc)
    for year, value, projection in [(2025, 61.3, False), (2027, 64.7, True)]:
        db_session.add(
            ImfWeoObservation(
                country_code="KEN",
                indicator="GGXWDG_NGDP",
                year=year,
                value=value,
                is_projection=projection,
                vintage=vintage,
                source="synthetic",
            )
        )
    db_session.commit()
    if reader == "headline":
        assert main._latest_imf_debt_to_gdp(db_session) == (
            61.3,
            2025,
            vintage.isoformat(),
        )
    elif reader == "projection":
        rows, source, absent = main._published_debt_projections(db_session)
        assert rows == [
            {
                "year": 2027,
                "projected_debt_to_gdp": 64.7,
                "is_published_projection": True,
            }
        ]
        assert source == "IMF World Economic Outlook (GGXWDG_NGDP)" and absent is None
    elif reader == "sustainability":
        seed_timeline(db_session)
        result = client.get("/api/v1/debt/sustainability")
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["debt_to_gdp"]["value"] == 61.3
        assert body["debt_to_gdp"]["source"] == "IMF World Economic Outlook"
        assert body["projections"][0]["projected_debt_to_gdp"] == 64.7
    else:
        result = client.get("/api/v1/debt/broader")
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "success"
    assert db_session.scalar(text("SELECT 1")) == 1


@pytest.mark.parametrize("reader", ["headline", "projection", "broader"])
def test_optional_imf_discovery_failure_is_not_absence(db_session, monkeypatch, reader):
    import asyncio
    import main
    import sqlalchemy

    def failed_discovery(*args, **kwargs):
        raise RuntimeError("synthetic catalog unavailable")

    monkeypatch.setattr(sqlalchemy, "inspect", failed_discovery)
    with pytest.raises(RuntimeError, match="synthetic catalog unavailable"):
        if reader == "headline":
            main._latest_imf_debt_to_gdp(db_session)
        elif reader == "projection":
            main._published_debt_projections(db_session)
        else:
            asyncio.run(main.get_debt_broader(db_session))
    assert db_session.scalar(text("SELECT 1")) == 1
