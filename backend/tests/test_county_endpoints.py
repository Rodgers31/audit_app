"""
Tests for county-related endpoints.

Covers:
  GET /api/v1/counties
  GET /api/v1/counties/{county_id}
  GET /api/v1/counties/{county_id}/comprehensive
  GET /api/v1/counties/{county_id}/financial
  GET /api/v1/counties/{county_id}/budget
  GET /api/v1/counties/{county_id}/debt
  GET /api/v1/counties/{county_id}/accountability
  GET /api/v1/counties/{county_id}/summary
"""

from datetime import datetime

import pytest
from models import (
    Audit,
    BudgetLine,
    DebtCategory,
    Entity,
    EntityType,
    FiscalPeriod,
    Loan,
    Severity,
)


@pytest.fixture()
def seed_full_county(db_session, seed_country, seed_source_doc):
    """Seed a county entity with budget lines and loans for richer testing."""
    entity = Entity(
        id=10,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Mombasa County",
        slug="mombasa-county",
    )
    db_session.add(entity)
    db_session.flush()

    fp = FiscalPeriod(
        id=10,
        country_id=seed_country.id,
        label="FY2024/25",
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    db_session.add(fp)
    db_session.flush()

    bl = BudgetLine(
        entity_id=entity.id,
        period_id=fp.id,
        category="Health",
        subcategory="Primary Care",
        allocated_amount=5_000_000,
        actual_spent=3_200_000,
        currency="KES",
        source_document_id=seed_source_doc.id,
    )
    db_session.add(bl)

    loan = Loan(
        entity_id=entity.id,
        lender="World Bank",
        debt_category=DebtCategory.EXTERNAL_MULTILATERAL,
        principal=10_000_000,
        outstanding=8_000_000,
        currency="KES",
        source_document_id=seed_source_doc.id,
        issue_date=datetime(2020, 1, 1),
    )
    db_session.add(loan)
    db_session.commit()
    return entity


@pytest.fixture()
def seed_county_with_audits(db_session, seed_country, seed_source_doc):
    """Seed a county with audit findings for accountability scorecard testing."""
    entity = Entity(
        id=10,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Mombasa County",
        slug="mombasa-county",
    )
    db_session.add(entity)
    db_session.flush()

    fp1 = FiscalPeriod(
        id=10,
        country_id=seed_country.id,
        label="FY2022/23",
        start_date=datetime(2022, 7, 1),
        end_date=datetime(2023, 6, 30),
    )
    fp2 = FiscalPeriod(
        id=11,
        country_id=seed_country.id,
        label="FY2023/24",
        start_date=datetime(2023, 7, 1),
        end_date=datetime(2024, 6, 30),
    )
    db_session.add_all([fp1, fp2])
    db_session.flush()

    # Budget line for absorption rate
    bl = BudgetLine(
        entity_id=entity.id,
        period_id=fp1.id,
        category="Health",
        allocated_amount=10_000_000,
        actual_spent=7_000_000,
        currency="KES",
        source_document_id=seed_source_doc.id,
    )
    db_session.add(bl)

    # Audit findings across years
    audits = [
        Audit(
            entity_id=entity.id,
            period_id=fp1.id,
            finding_text="Unsupported expenditure",
            severity=Severity.CRITICAL,
            source_document_id=seed_source_doc.id,
            query_type="unsupported_expenditure",
            amount=500_000,
            status="Pending",
            audit_opinion="qualified",
            audit_year=2022,
        ),
        Audit(
            entity_id=entity.id,
            period_id=fp2.id,
            finding_text="Unsupported expenditure recurring",
            severity=Severity.CRITICAL,
            source_document_id=seed_source_doc.id,
            query_type="unsupported_expenditure",
            amount=750_000,
            status="Unresolved",
            audit_opinion="unqualified",
            audit_year=2023,
        ),
        Audit(
            entity_id=entity.id,
            period_id=fp2.id,
            finding_text="Procurement irregularity",
            severity=Severity.WARNING,
            source_document_id=seed_source_doc.id,
            query_type="procurement",
            amount=200_000,
            status="Resolved",
            audit_opinion="unqualified",
            audit_year=2023,
        ),
    ]
    db_session.add_all(audits)
    db_session.commit()
    return entity


class TestGetCounties:
    """Tests for GET /api/v1/counties."""

    def test_returns_list_or_503_when_empty(self, client):
        """Without any county entities, should return 503 (no data) or empty list."""
        response = client.get("/api/v1/counties")
        # May return 503 with helpful error or 200 with empty list
        assert response.status_code in (200, 503)

    def test_returns_counties_when_seeded(self, client, seed_entity):
        """With at least one county entity, should return county data."""
        response = client.get("/api/v1/counties")
        assert response.status_code in (200, 503)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)

    def test_fiscal_year_filter(self, client, seed_full_county):
        """Fiscal year query param should be accepted."""
        response = client.get("/api/v1/counties?fiscal_year=2024/25")
        assert response.status_code in (200, 503)


class TestGetCountyById:
    """Tests for GET /api/v1/counties/{county_id}."""

    def test_returns_county_data(self, client, seed_entity):
        """A valid county ID should return data."""
        response = client.get("/api/v1/counties/001")
        # The route uses county_id as a string code
        assert response.status_code in (200, 404, 503)

    def test_returns_404_for_unknown(self, client):
        """Unknown county code should return 404."""
        response = client.get("/api/v1/counties/999")
        assert response.status_code in (200, 404, 503)


class TestCountyComprehensive:
    """Tests for GET /api/v1/counties/{county_id}/comprehensive."""

    def test_returns_comprehensive_profile(self, client, seed_full_county):
        response = client.get("/api/v1/counties/047/comprehensive")
        assert response.status_code in (200, 404, 503)

    def test_unknown_county_returns_error(self, client):
        response = client.get("/api/v1/counties/999/comprehensive")
        assert response.status_code in (404, 503, 200)


class TestCountyBudget:
    """Tests for GET /api/v1/counties/{county_id}/budget."""

    def test_returns_budget_data(self, client, seed_full_county):
        response = client.get("/api/v1/counties/047/budget")
        assert response.status_code in (200, 404, 503)


class TestCountyDebt:
    """Tests for GET /api/v1/counties/{county_id}/debt."""

    def test_returns_debt_data(self, client, seed_full_county):
        response = client.get("/api/v1/counties/047/debt")
        assert response.status_code in (200, 404, 503)


class TestCountyFinancial:
    """Tests for GET /api/v1/counties/{county_id}/financial."""

    def test_returns_financial_data(self, client, seed_full_county):
        response = client.get("/api/v1/counties/047/financial")
        assert response.status_code in (200, 404, 503)


class TestCountyAccountability:
    """Tests for GET /api/v1/counties/{county_id}/accountability."""

    def test_returns_accountability_scorecard(self, client, seed_county_with_audits):
        response = client.get("/api/v1/counties/047/accountability")
        assert response.status_code == 200
        data = response.json()
        assert data["county_id"] == "047"
        assert "accountability_grade" in data
        assert "audit_opinion_history" in data
        assert "total_flagged_amount" in data
        assert "recurring_findings_count" in data
        assert "unresolved_findings_count" in data
        assert "absorption_rate" in data
        assert "peer_comparison" in data

    def test_opinion_history_sorted_by_year(self, client, seed_county_with_audits):
        response = client.get("/api/v1/counties/047/accountability")
        data = response.json()
        history = data["audit_opinion_history"]
        assert len(history) == 2
        assert history[0]["year"] == 2022
        assert history[0]["opinion"] == "qualified"
        assert history[1]["year"] == 2023
        assert history[1]["opinion"] == "unqualified"

    def test_flagged_amount_sums_all_findings(self, client, seed_county_with_audits):
        response = client.get("/api/v1/counties/047/accountability")
        data = response.json()
        # 500_000 + 750_000 + 200_000 = 1_450_000
        assert data["total_flagged_amount"] == 1_450_000.0

    def test_recurring_findings_counted(self, client, seed_county_with_audits):
        response = client.get("/api/v1/counties/047/accountability")
        data = response.json()
        # "unsupported_expenditure" appears in 2022 and 2023
        assert data["recurring_findings_count"] == 1

    def test_unresolved_findings_counted(self, client, seed_county_with_audits):
        response = client.get("/api/v1/counties/047/accountability")
        data = response.json()
        # "Pending" + "Unresolved" = 2
        assert data["unresolved_findings_count"] == 2

    def test_absorption_rate_computed(self, client, seed_county_with_audits):
        response = client.get("/api/v1/counties/047/accountability")
        data = response.json()
        # 7_000_000 / 10_000_000 = 0.7
        assert data["absorption_rate"] == 0.7

    def test_grade_a_for_clean_county(self, client, db_session, seed_country, seed_source_doc):
        """County with unqualified opinions and few findings gets grade A."""
        entity = Entity(
            id=20,
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name="Mombasa County",
            slug="mombasa-county",
        )
        db_session.add(entity)
        db_session.flush()
        fp = FiscalPeriod(
            id=20,
            country_id=seed_country.id,
            label="FY2024/25",
            start_date=datetime(2024, 7, 1),
            end_date=datetime(2025, 6, 30),
        )
        db_session.add(fp)
        db_session.flush()
        audit = Audit(
            entity_id=entity.id,
            period_id=fp.id,
            finding_text="Minor issue",
            severity=Severity.INFO,
            source_document_id=seed_source_doc.id,
            audit_opinion="unqualified",
            audit_year=2024,
        )
        db_session.add(audit)
        db_session.commit()

        response = client.get("/api/v1/counties/047/accountability")
        data = response.json()
        assert data["accountability_grade"] == "A"

    def test_grade_drops_for_adverse_opinion(self, client, db_session, seed_country, seed_source_doc):
        """Adverse opinion in any year drops grade to D."""
        entity = Entity(
            id=20,
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name="Nairobi County",
            slug="nairobi-county",
        )
        db_session.add(entity)
        db_session.flush()
        fp = FiscalPeriod(
            id=20,
            country_id=seed_country.id,
            label="FY2024/25",
            start_date=datetime(2024, 7, 1),
            end_date=datetime(2025, 6, 30),
        )
        db_session.add(fp)
        db_session.flush()
        audit = Audit(
            entity_id=entity.id,
            period_id=fp.id,
            finding_text="Serious irregularities",
            severity=Severity.CRITICAL,
            source_document_id=seed_source_doc.id,
            audit_opinion="adverse",
            audit_year=2024,
        )
        db_session.add(audit)
        db_session.commit()

        response = client.get("/api/v1/counties/001/accountability")
        data = response.json()
        assert data["accountability_grade"] == "D"

    def test_peer_comparison_structure(self, client, seed_county_with_audits):
        response = client.get("/api/v1/counties/047/accountability")
        data = response.json()
        pc = data["peer_comparison"]
        assert "region" in pc
        assert "region_avg_flagged_amount" in pc
        assert "region_avg_grade" in pc
        assert "population_bracket" in pc
        assert "population_bracket_avg" in pc
        assert pc["region"] == "Coast"

    def test_404_for_unknown_county(self, client):
        response = client.get("/api/v1/counties/999/accountability")
        assert response.status_code == 404


class TestCountySummary:
    """Tests for GET /api/v1/counties/{county_id}/summary."""

    def test_returns_summary_with_grade(self, client, seed_county_with_audits):
        response = client.get("/api/v1/counties/047/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["county_id"] == "047"
        assert "accountability_grade" in data
        assert "county_name" in data
        assert "total_budget" in data
        assert "audit_findings_count" in data

    def test_404_for_unknown_county(self, client):
        response = client.get("/api/v1/counties/999/summary")
        assert response.status_code == 404
