"""The statistics money total must survive PostgreSQL numeric NaN."""

import os
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Query, sessionmaker

from main import app, clear_all_caches
from models import (
    Audit, Base, Country, DocumentStatus, DocumentType, Entity, EntityType,
    FiscalPeriod, Severity, SourceDocument,
)


def test_statistics_endpoint_rejects_nonfinite_aggregate_even_without_postgres(
    client, db_session, seed_entity, seed_fiscal_period, seed_source_doc, monkeypatch
):
    """Default-suite guard: emulate PG's NaN SUM, which SQLite cannot store."""
    db_session.add(Audit(entity_id=seed_entity.id, period_id=seed_fiscal_period.id,
                         source_document_id=seed_source_doc.id, page_ref="p.7",
                         finding_text="Cited KES 5.25", severity=Severity.WARNING,
                         amount=Decimal("5.25")))
    db_session.commit()
    original_scalar = Query.scalar

    def postgres_nan_sum(query):
        if "sum(audits.amount)" in str(query.statement).lower():
            return Decimal("NaN")
        return original_scalar(query)

    monkeypatch.setattr(Query, "scalar", postgres_nan_sum)
    result = client.get("/api/v1/audits/statistics")
    assert result.status_code == 200, result.text
    assert result.json()["total_amount_flagged"] == 5.25


@pytest.fixture()
def postgres_audits():
    url = os.environ.get("AUDIT_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set AUDIT_TEST_POSTGRES_URL to a disposable local PostgreSQL database")
    if make_url(url).host not in {"127.0.0.1", "localhost", "::1"}:
        pytest.fail("AUDIT_TEST_POSTGRES_URL must point to disposable local PostgreSQL")
    schema = f"statistics_{uuid4().hex}"
    admin_engine = create_engine(url)
    with admin_engine.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add(Country(id=1, iso_code="KEN", name="Kenya", currency="KES",
                       timezone="Africa/Nairobi", default_locale="en_KE"))
        db.add(Entity(id=1, country_id=1, type=EntityType.COUNTY,
                      canonical_name="Test County", slug="test-county"))
        db.add(FiscalPeriod(id=1, country_id=1, label="FY2024/25",
                            start_date=datetime(2024, 7, 1), end_date=datetime(2025, 6, 30)))
        db.add(SourceDocument(id=1, country_id=1, publisher="Test OAG",
                              title="Synthetic cited report", url="https://example.org/report.pdf",
                              fetch_date=datetime(2025, 9, 1, tzinfo=timezone.utc),
                              doc_type=DocumentType.AUDIT, status=DocumentStatus.AVAILABLE))
        db.commit()

    def add(amount, *, text_value="Cited finding", severity=Severity.WARNING,
            provenance=None):
        with Session() as db:
            db.add(Audit(entity_id=1, period_id=1, source_document_id=1,
                         page_ref="p.7", finding_text=text_value,
                         severity=severity, amount=amount, provenance=provenance))
            db.commit()

    def response():
        clear_all_caches()

        def get_test_db():
            with Session() as db:
                yield db

        with patch("main.get_db", get_test_db):
            return TestClient(app, raise_server_exceptions=False).get(
                "/api/v1/audits/statistics"
            )

    yield add, response, engine
    Base.metadata.drop_all(engine)
    engine.dispose()
    with admin_engine.begin() as connection:
        connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    admin_engine.dispose()


def test_mixed_postgres_nan_preserves_finding_and_finite_sum(postgres_audits):
    add, response, engine = postgres_audits
    add(Decimal("NaN"), text_value="Legacy text KES 999 conflicts with stored amount",
        provenance={"amount_involved": "KES 999"})
    add(Decimal("5.25"))
    add(Decimal("0.00"))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT sum(amount)::text FROM audits")).scalar() == "NaN"

    result = response()
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["total_findings"] == 3
    assert data["by_severity"]["warning"] == 3
    assert data["total_amount_flagged"] == 5.25
    assert data["findings_with_amount"] == 2
    assert data["findings_with_invalid_amount"] == 1
    assert data["findings_without_amount"] == 0


def test_all_invalid_amounts_have_no_total(postgres_audits):
    add, response, _ = postgres_audits
    add(Decimal("NaN"), text_value="Legacy text KES 999 conflicts",
        severity=Severity.CRITICAL, provenance={"amount_involved": "KES 999"})
    result = response()
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["total_findings"] == 1
    assert data["recent_critical"][0]["finding"] == "Legacy text KES 999 conflicts"
    assert data["recent_critical"][0]["amount"] is None
    assert data["recent_critical"][0]["amount_unavailable_reason"] == "invalid_stored_amount"
    assert data["total_amount_flagged"] is None
    assert data["findings_with_amount"] == 0
    assert data["findings_with_invalid_amount"] == 1
    assert data["findings_without_amount"] == 0


def test_missing_amount_is_distinct_from_stored_zero(postgres_audits):
    add, response, _ = postgres_audits
    add(None, text_value="Finding with no money figure")
    missing = response()
    assert missing.status_code == 200, missing.text
    assert missing.json()["total_amount_flagged"] is None
    assert missing.json()["findings_without_amount"] == 1

    add(Decimal("0.00"))
    with_zero = response()
    assert with_zero.status_code == 200, with_zero.text
    assert with_zero.json()["total_amount_flagged"] == 0
    assert with_zero.json()["findings_with_amount"] == 1
    assert with_zero.json()["findings_without_amount"] == 1


def test_legacy_plain_kes_fallback_keeps_coverage_explicit(postgres_audits):
    add, response, _ = postgres_audits
    add(None, text_value="Unsupported KES 1,200 on cited page")
    result = response()
    assert result.status_code == 200, result.text
    assert result.json()["total_amount_flagged"] == 1200
    assert result.json()["findings_with_amount"] == 1


def test_recent_critical_does_not_invent_zero_for_absent_amount(postgres_audits):
    add, response, _ = postgres_audits
    add(None, text_value="No amount stated", severity=Severity.CRITICAL)
    result = response()
    assert result.status_code == 200, result.text
    assert result.json()["recent_critical"][0]["amount"] is None
    assert result.json()["total_amount_flagged"] is None


def test_recent_critical_prefers_finite_stored_amount(postgres_audits):
    add, response, _ = postgres_audits
    add(Decimal("5.25"), text_value="No amount stated", severity=Severity.CRITICAL)
    result = response()
    assert result.status_code == 200, result.text
    assert result.json()["recent_critical"][0]["amount"] == 5.25


def test_oversized_critical_legacy_amount_cannot_break_json(postgres_audits):
    add, response, _ = postgres_audits
    add(None, text_value="KES " + "9" * 309, severity=Severity.CRITICAL)
    result = response()
    assert result.status_code == 200, result.text
    assert result.json()["total_amount_flagged"] is None
    assert result.json()["total_amount_flagged_reason"] == "non_finite_total"
    assert result.json()["recent_critical"][0]["amount"] is None
    assert result.json()["recent_critical"][0]["amount_unavailable_reason"] == "non_finite_text_amount"


@pytest.mark.parametrize("finding", [
    "Irregular procurement totalling KES 50M",
    "Irregular procurement totalling KES 5 million",
    "Irregular procurement totalling KES 1,234.50",
    "Irregular procurement totalling KES 1,2,3",
    "Irregular procurement totalling KES ١٢٣",
])
def test_legacy_text_does_not_turn_partial_or_scaled_figures_into_plain_kes(
    postgres_audits, finding
):
    add, response, _ = postgres_audits
    add(None, text_value=finding)
    result = response()
    assert result.status_code == 200, result.text
    assert result.json()["total_amount_flagged"] is None
    assert result.json()["findings_without_amount"] == 1


def test_amount_query_count_stays_bounded_as_findings_grow(postgres_audits):
    add, response, engine = postgres_audits
    add(Decimal("1.00"))
    statements = []

    def record(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().lower().startswith("select"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        assert response().status_code == 200
        initial_count = len(statements)
        statements.clear()
        for _ in range(30):
            add(Decimal("1.00"))
        result = response()
        assert result.status_code == 200, result.text
        assert result.json()["total_amount_flagged"] == 31
        assert len(statements) == initial_count
        # The legacy text fallback must fetch only rows without a stored figure.
        text_queries = [sql.lower() for sql in statements
                        if "select audits.finding_text" in sql.lower()]
        assert len(text_queries) == 1
        assert "audits.amount is null" in text_queries[0]
    finally:
        event.remove(engine, "before_cursor_execute", record)
