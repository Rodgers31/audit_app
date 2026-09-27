"""#328: exercise the public entity routes, including response serialization."""
from datetime import datetime

import pytest
from models import (
    BudgetLine,
    Entity,
    EntityType,
    FiscalPeriod,
    SourceDocument,
    DocumentType,
)


@pytest.fixture
def accounts(db_session, seed_country, seed_source_doc):
    entity = Entity(
        country_id=seed_country.id,
        canonical_name="Mombasa County",
        slug="mombasa-county",
        type=EntityType.COUNTY,
    )
    db_session.add(entity)
    db_session.flush()
    periods = []
    for year, scale in [(2024, 0.5), (2025, 1)]:
        period = FiscalPeriod(
            country_id=seed_country.id,
            label=f"FY{year}/{str(year+1)[2:]}",
            start_date=datetime(year, 7, 1),
            end_date=datetime(year + 1, 6, 30),
        )
        db_session.add(period)
        db_session.flush()
        periods.append(period)
        for category, value in [
            ("Total", 100),
            ("Recurrent", 60),
            ("Development", 40),
            ("Own Source Revenue", 10),
        ]:
            db_session.add(
                BudgetLine(
                    entity_id=entity.id,
                    period_id=period.id,
                    category=category,
                    allocated_amount=value * scale,
                    actual_spent=None,
                    currency="KES",
                    page_ref="p.42",
                    source_document_id=seed_source_doc.id,
                )
            )
    db_session.commit()
    return entity, periods


def summaries(client, entity):
    listing = client.get("/api/v1/entities?entity_type=county")
    detail = client.get(f"/api/v1/entities/{entity.id}")
    assert listing.status_code == detail.status_code == 200
    return (
        listing.json()[0]["financial_summary"],
        detail.json()["financial_time_series"],
    )


def test_totals_do_not_include_components_revenue_or_other_years(client, accounts):
    entity, periods = accounts
    summary, series = summaries(client, entity)
    assert summary["total_allocation"] == 100
    assert [p["total_allocation"] for p in series] == [100, 50]
    assert summary["fiscal_period"]["id"] == periods[1].id
    assert summary == series[0]
    assert summary["accounting_basis"] == "reported_total"
    assert summary["sources"][0]["page_refs"] == ["p.42"]


def test_missing_spending_is_not_zero(client, accounts):
    summary, series = summaries(client, accounts[0])
    for value in [summary, *series]:
        assert value["total_spent"] is None
        assert value["execution_rate"] is None
        assert value["absent_reasons"]["total_spent"] == "spending_not_reported"
    lines = client.get(f"/api/v1/entities/{accounts[0].id}").json()[
        "recent_budget_lines"
    ]
    assert all(line["actual_spent"] is None for line in lines)


def test_reported_zero_is_preserved(client, accounts, db_session):
    entity, _ = accounts
    for line in db_session.query(BudgetLine).all():
        if line.category == "Total":
            line.actual_spent = 0
    db_session.flush()
    summary, series = summaries(client, entity)
    assert summary["total_allocation"] == 100
    assert summary["total_spent"] == summary["execution_rate"] == 0
    assert series[1]["total_spent"] == 0


def test_zero_total_is_not_replaced_by_components(client, accounts, db_session):
    for line in db_session.query(BudgetLine).all():
        if line.category == "Total":
            line.allocated_amount = line.actual_spent = 0
    db_session.flush()
    summary, _ = summaries(client, accounts[0])
    assert summary["total_allocation"] == 0
    assert summary["execution_rate"] is None


def test_complete_classification_is_additive(client, accounts, db_session):
    db_session.query(BudgetLine).filter(BudgetLine.category == "Total").delete()
    for line in db_session.query(BudgetLine).all():
        line.actual_spent = line.allocated_amount / 2
    db_session.flush()
    summary, _ = summaries(client, accounts[0])
    assert summary["total_allocation"] == 100
    assert summary["total_spent"] == 50
    assert summary["execution_rate"] == 50
    assert summary["accounting_basis"] == "recurrent_plus_development"


def test_incomplete_classification_withholds_total(client, accounts, db_session):
    db_session.query(BudgetLine).filter(
        BudgetLine.category.in_(["Total", "Development"])
    ).delete()
    db_session.flush()
    summary, _ = summaries(client, accounts[0])
    assert summary["total_allocation"] is None
    assert summary["absent_reasons"]["total_allocation"] == "incomplete_classification"


def test_conflicting_sources_are_not_summed_or_arbitrarily_chosen(
    client, accounts, db_session, seed_country
):
    entity, periods = accounts
    source = SourceDocument(
        country_id=seed_country.id,
        title="Other report",
        publisher="Controller of Budget",
        url="https://cob.go.ke/other.pdf",
        fetch_date=datetime(2026, 9, 27),
        doc_type=DocumentType.BUDGET,
    )
    db_session.add(source)
    db_session.flush()
    db_session.add(
        BudgetLine(
            entity_id=entity.id,
            period_id=periods[1].id,
            category="Total",
            allocated_amount=150,
            currency="KES",
            page_ref="p.5",
            source_document_id=source.id,
        )
    )
    db_session.flush()
    summary, _ = summaries(client, entity)
    assert summary["total_allocation"] is None
    assert summary["absent_reasons"]["total_allocation"] == "multiple_sources"
    assert len(summary["sources"]) == 2


def test_newer_projection_does_not_replace_county_report(
    client, accounts, db_session, seed_country, seed_source_doc
):
    entity, _ = accounts
    period = FiscalPeriod(
        country_id=seed_country.id,
        label="FY2026/27",
        start_date=datetime(2026, 7, 1),
        end_date=datetime(2027, 6, 30),
    )
    db_session.add(period)
    db_session.flush()
    db_session.add(
        BudgetLine(
            entity_id=entity.id,
            period_id=period.id,
            category="Health",
            allocated_amount=900,
            actual_spent=800,
            currency="KES",
            source_document_id=seed_source_doc.id,
        )
    )
    db_session.flush()
    summary, _ = summaries(client, entity)
    assert summary["total_allocation"] == 100
    assert summary["fiscal_period"]["label"] == "FY2025/26"


def test_county_health_ratios_use_the_published_classification(client, accounts, db_session):
    db_session.query(BudgetLine).filter(BudgetLine.category == "Total").delete()
    for row in db_session.query(BudgetLine).all():
        row.actual_spent = row.allocated_amount * (20 if row.category == "Own Source Revenue" else 8) / 10
    db_session.flush()
    listing = client.get("/api/v1/counties").json()[0]
    detail = client.get("/api/v1/counties/047").json()
    comprehensive = client.get("/api/v1/counties/047/comprehensive").json()
    for payload in (listing, detail):
        assert payload["total_budget"] == 100
        absorption = next(c for c in payload["financial_health"]["components"] if c["name"] == "budget_absorption")
        assert absorption["observed"] == 80
    assert comprehensive["financial_summary"]["health_score"] == listing["financial_health_score"]
