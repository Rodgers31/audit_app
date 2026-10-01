"""Actual PostgreSQL endpoint regression for #387; no production database access."""
import os
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from database import get_db
from main import app, clear_all_caches
from models import (Audit, Base, Country, DocumentStatus, DocumentType, Entity,
                    EntityType, FiscalPeriod, Severity, SourceDocument)


@pytest.fixture()
def amount_endpoints():
    url = os.environ.get("AUDIT_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set AUDIT_TEST_POSTGRES_URL to disposable local PostgreSQL")
    if make_url(url).host not in {"127.0.0.1", "localhost", "::1"}:
        pytest.fail("Only disposable local PostgreSQL is allowed")
    schema = f"amount_consumers_{uuid4().hex}"
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        db.add(Country(id=1, iso_code="KEN", name="Kenya", currency="KES",
                       timezone="Africa/Nairobi", default_locale="en_KE"))
        db.add_all([
            Entity(id=501, country_id=1, type=EntityType.COUNTY,
                   canonical_name="Nairobi County", slug="nairobi"),
            Entity(id=502, country_id=1, type=EntityType.COUNTY,
                   canonical_name="Mombasa County", slug="mombasa"),
            Entity(id=503, country_id=1, type=EntityType.MINISTRY,
                   canonical_name="Synthetic Ministry", slug="synthetic-ministry"),
            FiscalPeriod(id=1, country_id=1, label="FY2024/25",
                         start_date=datetime(2024, 7, 1), end_date=datetime(2025, 6, 30)),
            FiscalPeriod(id=2, country_id=1, label="FY2023/24",
                         start_date=datetime(2023, 7, 1), end_date=datetime(2024, 6, 30)),
            SourceDocument(id=1, country_id=1, publisher="Synthetic OAG",
                           title="Synthetic cited PDF", url="https://example.org/report.pdf",
                           fetch_date=datetime(2025, 9, 1), doc_type=DocumentType.AUDIT,
                           status=DocumentStatus.AVAILABLE),
        ])
        db.commit()

    def add(amount, *, entity=501, period=1, query_type="Financial Irregularity", published=True):
        with sessions() as db:
            db.add(Audit(entity_id=entity, period_id=period, audit_year=2024 if period == 1 else 2023,
                         amount=amount, finding_text="Legacy text KES 999 conflicts",
                         provenance={"amount_involved": "KES 999"}, severity=Severity.CRITICAL,
                         query_type=query_type, page_ref="p.7" if published else None,
                         source_document_id=1))
            db.commit()

    def override():
        with sessions() as db:
            yield db

    old_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override
    client = TestClient(app, raise_server_exceptions=False)

    def request(path):
        clear_all_caches()
        result = client.get(path)
        assert result.status_code == 200, result.text
        return result.json()

    try:
        yield add, request, engine
    finally:
        app.dependency_overrides = old_overrides
        clear_all_caches()
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


SURFACES = ["county", "batch", "national", "summary", "trends"]


def figure(request, surface):
    if surface in {"county", "batch", "national"}:
        path = {"county": "/counties/001/money-flow", "batch": "/money-flow/all-counties",
                "national": "/audit/money-flow/national"}[surface]
        body = request(f"/api/v1{path}?year=FY2024%2F25")
        if surface == "batch":
            body = next(row for row in body if row["county_id"] == 501)
        stage = next(s for s in body["stages"] if s["stage"] == "Flagged")
        assert stage.get("gap_from_prev") is None
        assert body["total_waste_estimate"] == stage["amount"]
        assert stage.get("amount_coverage") == body["audit_amount_coverage"]
        return stage["amount"], body["audit_amount_coverage"]
    if surface == "summary":
        body = request("/api/v1/audit/summary")
        result = body["total_irregular_expenditure"]
        if result["value"] is None or result["amount_coverage"]["status"] == "partial":
            assert result["reason"]
        return result["value"], result["amount_coverage"]
    body = request("/api/v1/audit/trends")
    return body["amount_per_year"]["2024"], body["amount_coverage_per_year"]["2024"]


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("values,total,status,finite,missing,invalid", [
    ([Decimal("NaN"), Decimal("5.25"), Decimal(0), None], 5.25, "partial", 2, 1, 1),
    ([Decimal("NaN")], None, "unavailable", 0, 0, 1),
    ([None], None, "unavailable", 0, 1, 0),
    ([Decimal(0)], 0, "complete", 1, 0, 0),
    ([Decimal("5.25")], 5.25, "complete", 1, 0, 0),
    ([Decimal("-5.25")], -5.25, "complete", 1, 0, 0),
    ([Decimal("5.25"), Decimal("-5.25")], 0, "complete", 2, 0, 0),
    ([Decimal("5.25"), Decimal("-5.25"), Decimal("NaN")], 0, "partial", 2, 0, 1),
    ([Decimal("NaN"), None], None, "unavailable", 0, 1, 1),
])
def test_amount_coverage_at_real_endpoints(amount_endpoints, surface, values, total, status,
                                         finite, missing, invalid):
    add, request, engine = amount_endpoints
    for value in values:
        add(value)
    if invalid:
        with engine.connect() as conn:
            assert conn.execute(text("SELECT sum(amount)::text FROM audits")).scalar() == "NaN"
    amount, coverage = figure(request, surface)
    assert amount == total
    assert coverage["status"] == status
    assert coverage["total_findings"] == len(values)
    assert coverage["findings_with_amount"] == finite
    assert coverage["findings_without_amount"] == missing
    assert coverage["findings_with_invalid_amount"] == invalid
    assert bool(coverage["reason"]) == (status != "complete")


def test_scopes_grouping_and_withheld_rows(amount_endpoints):
    add, request, _ = amount_endpoints
    add(Decimal("NaN"))
    add(Decimal("5.25"))
    add(Decimal("100"), entity=502, query_type="Unsupported Expenditure")
    add(Decimal("300"), entity=503)
    add(Decimal("20"), period=2)
    add(Decimal("900"), published=False)
    assert figure(request, "county")[0] == 5.25
    amount, coverage = figure(request, "national")
    assert amount == 105.25 and coverage["total_findings"] == 3
    assert figure(request, "summary")[0] == 325.25
    trends = request("/api/v1/audit/trends?county_id=501&query_type=Financial%20Irregularity")
    assert trends["amount_per_year"] == {"2023": 20, "2024": 5.25}
    assert trends["findings_per_year"] == {"2023": 1, "2024": 2}
    assert trends["amount_coverage_per_year"]["2024"]["findings_with_invalid_amount"] == 1
    batch = request("/api/v1/money-flow/all-counties?year=FY2024%2F25")
    assert {r["county_id"]: r["total_waste_estimate"] for r in batch} == {501: 5.25, 502: 100}
    assert request("/api/v1/audit/trends?query_type=Nonexistent")["amount_per_year"] == {}


def test_empty_withheld_and_unknown_period_stay_distinct(amount_endpoints):
    add, request, _ = amount_endpoints
    for surface in ["county", "batch", "national"]:
        assert figure(request, surface)[1]["reason"] == "no_findings"
    assert request("/api/v1/audit/trends")["amount_coverage"]["reason"] == "no_findings"
    add(Decimal("99"), published=False)
    for surface in ["county", "batch", "national"]:
        assert figure(request, surface)[1]["reason"] == "no_publishable_findings"
    for path in ["counties/001/money-flow", "money-flow/all-counties", "audit/money-flow/national"]:
        body = request(f"/api/v1/{path}?year=FY1999%2F00")
        rows = body if isinstance(body, list) else [body]
        assert all(r["audit_amount_coverage"]["reason"] == "fiscal_period_not_found" for r in rows)
    trends = request("/api/v1/audit/trends")
    assert trends["amount_per_year"] == {}
    assert trends["amount_coverage"]["reason"] == "no_publishable_findings"


@pytest.mark.parametrize("surface", SURFACES)
def test_query_cost_is_bounded_and_no_finding_text_payload(amount_endpoints, surface):
    add, request, engine = amount_endpoints
    add(Decimal("NaN"))
    statements = []
    def record(_conn, _cursor, sql, *_args):
        if sql.lstrip().lower().startswith("select"):
            statements.append(sql)
    event.listen(engine, "before_cursor_execute", record)
    try:
        figure(request, surface)
        original = len(statements)
        for i in range(30):
            add(Decimal("1"), entity=501 if i % 2 else 502)
        statements.clear()
        amount, _ = figure(request, surface)
        assert amount == (15 if surface in {"county", "batch"} else 30)
        assert len(statements) == original
        assert not any("select audits.finding_text" in sql.lower() for sql in statements)
    finally:
        event.remove(engine, "before_cursor_execute", record)


@pytest.mark.parametrize("surface", ["summary", "trends", "batch", "national", "county"])
def test_missing_and_zero_coverage_in_default_suite(client, db_session, seed_entity,
                                                  seed_fiscal_period, seed_source_doc, surface):
    """The ordinary SQLite suite also exercises actual endpoints and the new contract."""
    db_session.add(Audit(entity_id=seed_entity.id, period_id=seed_fiscal_period.id,
                         audit_year=2024, source_document_id=seed_source_doc.id,
                         page_ref="p.7", finding_text="Legacy text KES 999",
                         severity=Severity.CRITICAL, query_type="Financial Irregularity"))
    db_session.commit()
    def request(path):
        clear_all_caches()
        if "/counties/001/" in path:
            path = path.replace("/counties/001/", f"/counties/{seed_entity.slug}/")
        path = path.replace("FY2024%2F25", seed_fiscal_period.label)
        result = client.get(path)
        assert result.status_code == 200, result.text
        body = result.json()
        if surface == "batch" and isinstance(body, list):
            # Align the shared assertion's synthetic ID with this fixture.
            for row in body:
                if row["county_id"] == seed_entity.id:
                    row["county_id"] = 501
        return body
    value, coverage = figure(request, surface)
    assert value is None
    assert coverage["reason"] == "no_amounts_recorded"
    db_session.add(Audit(entity_id=seed_entity.id, period_id=seed_fiscal_period.id,
                         audit_year=2024, source_document_id=seed_source_doc.id,
                         page_ref="p.7", finding_text="Zero on cited page", amount=Decimal(0),
                         severity=Severity.CRITICAL, query_type="Financial Irregularity"))
    db_session.commit()
    value, coverage = figure(request, surface)
    assert value == 0
    assert coverage["status"] == "partial"
    assert coverage["findings_with_amount"] == coverage["findings_without_amount"] == 1


def test_postgres_finite_expression_covers_unconstrained_infinities(amount_endpoints):
    from sqlalchemy import Numeric, literal, select
    from services.audit_amounts import finite_audit_amount
    _, _, engine = amount_endpoints
    with engine.connect() as conn:
        for value in ["NaN", "Infinity", "-Infinity"]:
            assert conn.execute(select(finite_audit_amount(
                literal(Decimal(value), type_=Numeric())))).scalar() is None
        for value in ["0", "-1", "5.25"]:
            assert conn.execute(select(finite_audit_amount(
                literal(Decimal(value), type_=Numeric())))).scalar() == Decimal(value)


def test_source_revocation_does_not_publish_a_zero(amount_endpoints):
    add, request, engine = amount_endpoints
    add(Decimal("NaN"))
    add(Decimal("5.25"))
    with engine.begin() as conn:
        conn.execute(text("UPDATE source_documents SET url = NULL WHERE id = 1"))
    for surface in ["county", "batch", "national", "summary"]:
        amount, coverage = figure(request, surface)
        assert amount is None
        assert coverage["reason"] == "no_publishable_findings"
        assert coverage["total_findings"] == 0
        assert coverage["withheld_findings"] == 2
    trends = request("/api/v1/audit/trends")
    assert trends["amount_per_year"] == {}
    assert trends["amount_coverage"]["reason"] == "no_publishable_findings"
    assert trends["amount_coverage"]["withheld_findings"] == 2
