"""Sourced zero, missing data, and positive controls at the public API boundary."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func

from models import (
    Audit, DebtTimeline, DocumentStatus, DocumentType, Entity, EntityType,
    FiscalPeriod, Severity, SourceDocument,
)
from services.publication_gate import publishable_audit_criterion


@pytest.fixture()
def synthetic_source_doc(db_session, seed_country):
    doc = SourceDocument(
        country_id=seed_country.id,
        publisher="Synthetic fixture",
        title="Synthetic source document",
        url="https://example.invalid/synthetic-source.pdf",
        fetch_date=datetime(2025, 8, 1, tzinfo=timezone.utc),
        doc_type=DocumentType.REPORT,
        status=DocumentStatus.AVAILABLE,
    )
    db_session.add(doc)
    db_session.commit()
    return doc


def _audit(db, *, entity_id, period_id, source_id, amount, provenance=None, page_ref="p.42"):
    db.add(
        Audit(
            entity_id=entity_id,
            period_id=period_id,
            source_document_id=source_id,
            finding_text="Synthetic audit finding",
            severity=Severity.WARNING,
            amount=amount,
            provenance=provenance if provenance is not None else [],
            page_ref=page_ref,
        )
    )


@pytest.mark.parametrize("surface", ("county", "national", "batch"))
@pytest.mark.parametrize(
    "amounts,expected",
    (((), None), ((None,), None), ((Decimal("0"),), 0.0), ((Decimal("25"),), 25.0)),
    ids=("no-audits", "null-amount", "sourced-zero", "positive"),
)
def test_money_flow_distinguishes_a_sourced_zero_from_absence(
    client, db_session, seed_country, seed_fiscal_period, synthetic_source_doc,
    surface, amounts, expected,
):
    entity = Entity(
        id=501,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Synthetic County",
        slug="synthetic-county-zero",
    )
    db_session.add(entity)
    db_session.flush()
    for amount in amounts:
        _audit(
            db_session,
            entity_id=entity.id,
            period_id=seed_fiscal_period.id,
            source_id=synthetic_source_doc.id,
            amount=amount,
        )
    db_session.commit()

    published = db_session.query(func.sum(Audit.amount)).filter(
        publishable_audit_criterion(), Audit.entity_id == entity.id
    ).scalar()
    assert published == (Decimal(str(expected)) if expected is not None else None)

    path = {
        "county": "/api/v1/counties/501/money-flow?year=2024%2F25",
        "national": "/api/v1/audit/money-flow/national?year=2024%2F25",
        "batch": "/api/v1/money-flow/all-counties?year=2024%2F25",
    }[surface]
    response = client.get(path)
    assert response.status_code == 200, response.text
    body = response.json()
    if surface == "batch":
        body = next(row for row in body if row["county_id"] == entity.id)
    flagged = next(stage for stage in body["stages"] if stage["stage"] == "Flagged")
    assert flagged["amount"] == expected
    assert flagged.get("data_unavailable", False) is (expected is None)
    assert body["total_waste_estimate"] == expected
    if expected == 0:
        assert client.get(path).json() == response.json()


@pytest.mark.parametrize("surface", ("county", "national", "batch"))
def test_money_flow_does_not_publish_an_uncited_zero(
    client, db_session, seed_country, seed_fiscal_period, synthetic_source_doc, surface,
):
    entity = Entity(
        id=501,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Synthetic County",
        slug="synthetic-county-uncited",
    )
    db_session.add(entity)
    db_session.flush()
    _audit(
        db_session,
        entity_id=entity.id,
        period_id=seed_fiscal_period.id,
        source_id=synthetic_source_doc.id,
        amount=Decimal("0"),
        page_ref=None,
    )
    db_session.commit()
    assert db_session.query(func.sum(Audit.amount)).filter(
        publishable_audit_criterion(), Audit.entity_id == entity.id
    ).scalar() is None

    path = {
        "county": "/api/v1/counties/501/money-flow?year=2024%2F25",
        "national": "/api/v1/audit/money-flow/national?year=2024%2F25",
        "batch": "/api/v1/money-flow/all-counties?year=2024%2F25",
    }[surface]
    response = client.get(path)
    assert response.status_code == 200, response.text
    body = response.json()
    if surface == "batch":
        body = next(row for row in body if row["county_id"] == entity.id)
    flagged = next(stage for stage in body["stages"] if stage["stage"] == "Flagged")
    assert flagged["amount"] is None
    assert flagged["data_unavailable"] is True
    assert body["total_waste_estimate"] is None


@pytest.mark.parametrize(
    "rows,expected_total,expected_count",
    (
        ((), None, 0),
        (((None, None),), None, 0),
        (((None, "KES unknown"),), None, 0),
        (((Decimal("0"), "KES 0"), (None, "KES 0")), 0.0, 2),
        (((Decimal("25"), "KES 25"),), 25.0, 1),
        (((Decimal("0"), "KES 0"), (Decimal("25"), "KES 25"), (None, None)), 25.0, 2),
    ),
    ids=("no-findings", "no-amount", "malformed", "all-zero", "positive", "mixed"),
)
def test_federal_findings_sum_uses_recorded_amount_coverage(
    client, db_session, seed_country, synthetic_source_doc,
    rows, expected_total, expected_count,
):
    entity = Entity(
        id=601,
        country_id=seed_country.id,
        type=EntityType.MINISTRY,
        canonical_name="Synthetic Ministry",
        slug="synthetic-ministry-zero",
    )
    period = FiscalPeriod(
        id=601,
        country_id=seed_country.id,
        label="FY2024/25",
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    db_session.add_all((entity, period))
    db_session.flush()
    for amount, stated in rows:
        _audit(
            db_session,
            entity_id=entity.id,
            period_id=period.id,
            source_id=synthetic_source_doc.id,
            amount=amount,
            provenance=[{"amount_involved": stated}] if stated is not None else [],
        )
    db_session.commit()

    response = client.get("/api/v1/audits/federal")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_findings"] == len(rows)
    assert body["total_amount_in_findings"] == expected_total
    assert body["findings_with_amount"] == expected_count
    assert body["total_amount_in_findings_reason"] == (
        None if expected_count else "no_amounts_recorded"
    )
    assert sum(f["amount_numeric"] is not None for f in body["findings"]) == expected_count
    assert body["total_amount_questioned"] is None
    assert body["total_amount_questioned_reason"] == "not_extracted"
    if expected_total == 0:
        assert client.get("/api/v1/audits/federal").json() == body


@pytest.mark.parametrize(
    "gdp,gdp_ratio",
    ((None, None), (Decimal("0"), Decimal("0")), (Decimal("1000"), Decimal("65.5"))),
    ids=("null", "sourced-zero", "positive"),
)
def test_debt_timeline_keeps_recorded_zero_gdp_and_ratio(
    client, db_session, synthetic_source_doc, gdp, gdp_ratio,
):
    db_session.add(
        DebtTimeline(
            year=2024,
            external=Decimal("40"),
            domestic=Decimal("60"),
            total=Decimal("100"),
            gdp=gdp,
            gdp_ratio=gdp_ratio,
            unit="KES",
            source_document_id=synthetic_source_doc.id,
        )
    )
    db_session.commit()
    response = client.get("/api/v1/debt/timeline")
    assert response.status_code == 200, response.text
    row = response.json()["timeline"][0]
    assert row["gdp"] == (float(gdp) if gdp is not None else None)
    assert row["gdp_ratio"] == (float(gdp_ratio) if gdp_ratio is not None else None)
    if gdp_ratio == 0:
        assert client.get("/api/v1/debt/timeline").json() == response.json()


def test_debt_timeline_reconciliation_keeps_recorded_zero_total(
    client, db_session, synthetic_source_doc,
):
    db_session.add(
        DebtTimeline(
            year=2024,
            external=Decimal("0"),
            domestic=Decimal("0"),
            total=Decimal("0"),
            unit="KES",
            source_document_id=synthetic_source_doc.id,
        )
    )
    db_session.commit()
    response = client.get("/api/v1/debt/timeline")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["timeline"][0]["total"] == 0
    assert body["reconciliation"]["primary_value_kes"] == 0
