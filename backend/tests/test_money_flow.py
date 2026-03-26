"""
Tests for Follow the Money endpoints.

Covers:
  GET /api/v1/counties/{county_id}/money-flow?year=...
  GET /api/v1/audit/money-flow/national?year=...
"""

from datetime import datetime

import pytest
from models import Audit, BudgetLine, Entity, EntityType, FiscalPeriod, Severity


@pytest.fixture()
def seed_money_flow(db_session, seed_country, seed_source_doc):
    """Seed county with budget lines and audit findings for money-flow tests."""
    entity = Entity(
        id=20,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Nakuru County",
        slug="nakuru",
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

    # Two budget lines
    bl1 = BudgetLine(
        entity_id=entity.id,
        period_id=fp.id,
        category="Health",
        subcategory="Primary Care",
        allocated_amount=10_000_000,
        actual_spent=7_000_000,
        committed_amount=9_000_000,
        currency="KES",
        source_document_id=seed_source_doc.id,
    )
    bl2 = BudgetLine(
        entity_id=entity.id,
        period_id=fp.id,
        category="Education",
        subcategory="ECDE",
        allocated_amount=5_000_000,
        actual_spent=4_500_000,
        committed_amount=4_800_000,
        currency="KES",
        source_document_id=seed_source_doc.id,
    )
    db_session.add_all([bl1, bl2])
    db_session.flush()

    # Audit finding
    audit = Audit(
        entity_id=entity.id,
        period_id=fp.id,
        finding_text="Irregular procurement of medical supplies",
        severity=Severity.CRITICAL,
        amount=1_200_000,
        source_document_id=seed_source_doc.id,
    )
    db_session.add(audit)
    db_session.commit()
    return entity, fp


class TestCountyMoneyFlow:
    """Tests for GET /api/v1/counties/{county_id}/money-flow."""

    def test_returns_waterfall(self, client, seed_money_flow):
        entity, fp = seed_money_flow
        response = client.get(f"/api/v1/counties/{entity.id}/money-flow?year=2024/25")
        assert response.status_code == 200
        data = response.json()

        assert data["county_id"] == entity.id
        assert data["county_name"] == "Nakuru County"
        assert data["fiscal_year"] == "2024/25"

        stages = data["stages"]
        assert len(stages) == 4

        # Stage names
        assert stages[0]["stage"] == "Allocated"
        assert stages[1]["stage"] == "Released"
        assert stages[2]["stage"] == "Spent"
        assert stages[3]["stage"] == "Flagged"

        # Amounts
        assert stages[0]["amount"] == 15_000_000.0  # 10M + 5M
        assert stages[1]["amount"] == 13_800_000.0  # 9M + 4.8M
        assert stages[2]["amount"] == 11_500_000.0  # 7M + 4.5M
        assert stages[3]["amount"] == 1_200_000.0

        # Gaps
        assert stages[1]["gap_from_prev"] == 1_200_000.0  # 15M - 13.8M
        assert stages[2]["gap_from_prev"] == 2_300_000.0  # 13.8M - 11.5M

        # Derived
        assert data["total_waste_estimate"] == 1_200_000.0
        # efficiency = 11.5M / 15M * 100 = 76.67
        assert data["efficiency_score"] == pytest.approx(76.67, abs=0.01)

    def test_404_for_unknown_county(self, client):
        response = client.get("/api/v1/counties/9999/money-flow?year=2024/25")
        assert response.status_code == 404

    def test_missing_year_param(self, client, seed_money_flow):
        entity, _ = seed_money_flow
        response = client.get(f"/api/v1/counties/{entity.id}/money-flow")
        assert response.status_code == 422  # validation error

    def test_no_data_for_year(self, client, seed_money_flow):
        entity, _ = seed_money_flow
        response = client.get(f"/api/v1/counties/{entity.id}/money-flow?year=2020/21")
        assert response.status_code == 200
        data = response.json()
        # All amounts should be None with data_unavailable flags
        for stage in data["stages"]:
            assert stage["amount"] is None
            assert stage.get("data_unavailable") is True


class TestNationalMoneyFlow:
    """Tests for GET /api/v1/audit/money-flow/national."""

    def test_returns_national_aggregate(self, client, seed_money_flow):
        response = client.get("/api/v1/audit/money-flow/national?year=2024/25")
        assert response.status_code == 200
        data = response.json()

        assert data["county_name"] == "National (All Counties)"
        assert data["county_count"] >= 1
        assert len(data["stages"]) == 4
        assert data["stages"][0]["amount"] == 15_000_000.0

    def test_missing_year_param(self, client):
        response = client.get("/api/v1/audit/money-flow/national")
        assert response.status_code == 422

    def test_no_counties_returns_404(self, client):
        """Without any county entities seeded, should return 404."""
        # Clear in-memory cache from prior tests so we hit the real handler
        from routers.money_flow import national_money_flow
        if hasattr(national_money_flow, "_cache"):
            national_money_flow._cache.clear()
        response = client.get("/api/v1/audit/money-flow/national?year=2024/25")
        assert response.status_code == 404
