"""#368: detail discloses the terms actually used in the county index."""
from datetime import datetime, timezone

import pytest

from models import (
    Audit, BudgetLine, DebtCategory, Entity, EntityType, FiscalPeriod, Loan,
    Severity, SourceDocument, DocumentType,
)


@pytest.fixture
def health_county(db_session, seed_country, seed_source_doc):
    entity = Entity(
        country_id=seed_country.id, type=EntityType.COUNTY,
        canonical_name="Mombasa County", slug="mombasa-county",
    )
    period = FiscalPeriod(
        country_id=seed_country.id, label="FY2025/26",
        start_date=datetime(2025, 7, 1), end_date=datetime(2026, 6, 30),
    )
    db_session.add_all([entity, period])
    db_session.flush()
    for category, allocated, spent in (
        ("Total", 10_000_000, 5_000_000),
        ("Own Source Revenue", 1_000_000, 400_000),
    ):
        db_session.add(BudgetLine(
            entity_id=entity.id, period_id=period.id,
            source_document_id=seed_source_doc.id,
            category=category, allocated_amount=allocated, actual_spent=spent,
            currency="KES", page_ref="p.42",
        ))
    db_session.flush()
    return entity, period, seed_source_doc


def detail(client):
    response = client.get("/api/v1/counties/mombasa-county/comprehensive")
    assert response.status_code == 200, response.text
    return response.json()


def assert_recomputes(health):
    components = health["components"]
    assert len(components) >= health["minimum_components"]
    denominator = sum(component["weight"] for component in components)
    assert health["effective_weight"] == denominator
    assert health["score"] == round(
        sum(component["score"] * component["weight"] for component in components)
        / denominator, 1
    )
    for component in components:
        assert component["share_pct"] == pytest.approx(
            round(component["weight"] / denominator * 100, 1)
        )


def test_partial_coverage_discloses_effective_denominator_and_missing_inputs(
    client, health_county
):
    _, period, source = health_county
    body = detail(client)
    health = body["financial_health"]
    assert health["score"] == body["financial_summary"]["health_score"] == 45.0
    assert health["effective_weight"] == 2
    assert {c["name"] for c in health["components"]} == {
        "budget_absorption", "own_source_revenue"
    }
    assert {c["name"] for c in health["unavailable_inputs"]} == {
        "pending_bills", "audit_opinion"
    }
    assert {c["name"]: c["reason"] for c in health["unavailable_inputs"]} == {
        "pending_bills": "pending_bills_not_reported",
        "audit_opinion": "no_publishable_audit_signal",
    }
    assert all(c["source_period"] == period.label for c in health["components"])
    assert all(c["source_url"] == source.url for c in health["components"])
    assert next(c for c in health["components"] if c["name"] == "budget_absorption")["observed"] == 50
    assert_recomputes(health)


def test_full_coverage_discloses_all_weights_periods_and_observed_values(
    client, db_session, health_county, seed_country
):
    entity, period, source = health_county
    oag = SourceDocument(
        country_id=seed_country.id, title="Auditor-General county report",
        publisher="Office of the Auditor-General", url="https://oagkenya.go.ke/report.pdf",
        fetch_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT,
    )
    db_session.add(oag)
    db_session.flush()
    db_session.add(Audit(
        entity_id=entity.id, period_id=period.id,
        source_document_id=oag.id, finding_text="Qualified opinion",
        severity=Severity.WARNING, page_ref="p.7", publishable=True,
        audit_year=2026, audit_opinion="qualified",
    ))
    db_session.add(Loan(
        entity_id=entity.id, lender="Pending Bills — County Governments (Mombasa)",
        debt_category=DebtCategory.PENDING_BILLS,
        principal=1_250_000, outstanding=1_250_000, currency="KES",
        issue_date=datetime(2026, 6, 30, tzinfo=timezone.utc),
        source_document_id=source.id,
        provenance={
            "publication": "cob_cbirr_year_end", "category": "county",
            "fiscal_year": "FY 2025/26", "as_at": "2026-06-30",
            "source_url": source.url, "table": "Table 2.10",
        },
    ))
    db_session.flush()
    health = detail(client)["financial_health"]
    assert health["score"] == 53.3
    assert health["effective_weight"] == 6
    assert health["unavailable_inputs"] == []
    assert {c["name"] for c in health["components"]} == set(health["weights"])
    assert next(c for c in health["components"] if c["name"] == "audit_opinion")["observed"] == "qualified"
    assert next(c for c in health["components"] if c["name"] == "audit_opinion")["source_period"] == period.label
    pending = next(c for c in health["components"] if c["name"] == "pending_bills")
    assert pending["observed"] == 12.5
    assert pending["source_period"] == "FY 2025/26"
    assert pending["as_at"] == "2026-06-30"
    assert_recomputes(health)


def test_single_component_does_not_publish_a_composite(client, db_session, health_county):
    db_session.query(BudgetLine).filter(
        BudgetLine.category == "Own Source Revenue"
    ).delete()
    db_session.flush()
    body = detail(client)
    health = body["financial_health"]
    assert body["financial_summary"]["health_score"] is None
    assert health["score"] is None
    assert health["grade"] is None
    assert health["absent_reason"] == "fewer_than_two_components"
    assert health["effective_weight"] == 0
    assert health["components"] == []
    assert health["available_inputs"] == ["budget_absorption"]


def test_reported_zero_own_source_is_included(client, db_session, health_county):
    row = db_session.query(BudgetLine).filter(
        BudgetLine.category == "Own Source Revenue"
    ).one()
    row.actual_spent = 0
    db_session.flush()
    health = detail(client)["financial_health"]
    assert next(c for c in health["components"] if c["name"] == "own_source_revenue")["score"] == 0
    assert health["score"] == 25
    assert_recomputes(health)


def test_cash_own_source_component_cites_the_cash_document(
    client, db_session, health_county, seed_country
):
    entity, period, _ = health_county
    cash_doc = SourceDocument(
        country_id=seed_country.id, title="County revenue performance",
        publisher="Controller of Budget", url="https://example.test/cash.pdf",
        fetch_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
        doc_type=DocumentType.BUDGET,
    )
    db_session.add(cash_doc)
    db_session.flush()
    for name, target, actual in (
        ("Equitable Share", 1_500_000, 1_500_000),
        ("Own Source Revenue", 1_000_000, 500_000),
        ("Total", 2_500_000, 2_000_000),
    ):
        db_session.add(BudgetLine(
            entity_id=entity.id, period_id=period.id,
            source_document_id=cash_doc.id, category="Revenue Receipts",
            subcategory=name, allocated_amount=target, actual_spent=actual,
            currency="KES", page_ref="p.43",
        ))
    db_session.flush()
    body = detail(client)
    assert body["revenue"]["local_revenue_basis"] == "cash_receipts"
    own = next(
        c for c in body["financial_health"]["components"]
        if c["name"] == "own_source_revenue"
    )
    assert own["observed"] == 50
    assert own["source_url"] == cash_doc.url
    assert own["measurement_basis"] == "cash_receipts"


def test_mixed_pending_stocks_disclose_all_periods_without_a_false_single_source(
    client, db_session, health_county
):
    entity, _, source = health_county
    for year, amount in ((2025, 1_000_000), (2026, 1_250_000)):
        db_session.add(Loan(
            entity_id=entity.id,
            lender=f"Pending Bills — County Governments (Mombasa) {year}",
            debt_category=DebtCategory.PENDING_BILLS,
            principal=amount, outstanding=amount, currency="KES",
            issue_date=datetime(year, 6, 30, tzinfo=timezone.utc),
            source_document_id=source.id,
            provenance={
                "publication": "cob_cbirr_year_end", "category": "county",
                "fiscal_year": f"FY {year - 1}/{str(year)[2:]}",
                "as_at": f"{year}-06-30", "source_url": source.url,
                "table": "Table 2.10",
            },
        ))
    db_session.flush()
    pending = next(
        c for c in detail(client)["financial_health"]["components"]
        if c["name"] == "pending_bills"
    )
    assert pending["observed"] == 22.5  # currently summed by the shared reader
    assert pending["source_period"] is None
    assert pending["source_periods"] == ["FY 2024/25", "FY 2025/26"]
    assert pending["as_at"] is None
    assert pending["source_url"] is None
    assert pending["source_warning"] == "mixed_pending_periods"
