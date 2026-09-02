"""
Tests for unit safety — ensures all finance endpoints include _meta with unit
and entity_scope, and that monetary values pass plausibility bounds.

Phase 18: Unit Safety & Trust Safeguards Audit
"""

from datetime import datetime

import pytest
from models import (
    BudgetLine,
    DebtTimeline,
    Entity,
    EntityType,
    FiscalPeriod,
    FiscalSummary,
    Loan,
)


@pytest.fixture()
def seed_unit_test_data(db_session, seed_country, seed_source_doc):
    """Seed minimal data for unit-safety tests across multiple tables."""
    # National entity
    national = Entity(
        country_id=seed_country.id,
        type=EntityType.NATIONAL,
        canonical_name="National Government",
        slug="national-government",
    )
    county = Entity(
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Test County",
        slug="test-county",
    )
    db_session.add_all([national, county])
    db_session.flush()

    # Fiscal period
    fp = FiscalPeriod(
        country_id=seed_country.id,
        label="FY2024/25",
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    db_session.add(fp)
    db_session.flush()

    # BudgetLine — raw KES
    db_session.add(
        BudgetLine(
            entity_id=national.id,
            period_id=fp.id,
            source_document_id=seed_source_doc.id,
            category="Education",
            allocated_amount=500_000_000_000,
            actual_spent=400_000_000_000,
            committed_amount=450_000_000_000,
            currency="KES",
        )
    )
    db_session.add(
        BudgetLine(
            entity_id=county.id,
            period_id=fp.id,
            source_document_id=seed_source_doc.id,
            category="Health",
            allocated_amount=5_000_000_000,
            actual_spent=4_200_000_000,
            currency="KES",
        )
    )

    # FiscalSummary — billion KES
    db_session.add(
        FiscalSummary(
            fiscal_year="FY 2024/25",
            appropriated_budget=3310,
            total_revenue=2810,
            tax_revenue=2100,
            non_tax_revenue=710,
            total_borrowing=800,
            borrowing_pct_of_budget=24.2,
            debt_service_cost=1050,
            debt_service_per_shilling=37,
            debt_ceiling=10000,
            actual_debt=11500,
            debt_ceiling_usage_pct=115,
            development_spending=700,
            recurrent_spending=2610,
            county_allocation=410,
            source_document_id=seed_source_doc.id,
        )
    )

    # DebtTimeline — billion KES
    db_session.add(
        DebtTimeline(
            year=2025,
            external=5200,
            domestic=6800,
            total=12000,
            gdp=17500,
            gdp_ratio=68.6,
            source_document_id=seed_source_doc.id,
        )
    )

    # Loan — raw KES
    db_session.add(
        Loan(
            entity_id=national.id,
            lender="World Bank IDA",
            principal=120_000_000_000,
            outstanding=95_000_000_000,
            interest_rate=1.5,
            currency="KES",
            issue_date=datetime(2020, 1, 1),
            maturity_date=datetime(2045, 1, 1),
            source_document_id=seed_source_doc.id,
        )
    )

    db_session.commit()


# ── _meta presence tests ──────────────────────────────────────────────


class TestMetaPresence:
    """Every finance endpoint must return a _meta dict with unit and entity_scope."""

    def test_fiscal_summary_has_meta(self, client, seed_unit_test_data):
        r = client.get("/api/v1/fiscal/summary")
        assert r.status_code == 200
        body = r.json()
        meta = body.get("_meta")
        assert meta is not None, "/fiscal/summary missing _meta"
        # See test_debt_timeline_has_meta: assert the AGREEMENT, not a
        # constant that contradicted the rows (F8, PR #136).
        current = body.get("current") or {}
        if current.get("unit"):
            assert meta["unit"] == ("KES" if current["unit"] == "KES" else "billion_kes")
        else:
            assert meta["unit"] == "billion_kes"
        assert meta["entity_scope"] == "national"

    def test_debt_timeline_has_meta(self, client, seed_unit_test_data):
        r = client.get("/api/v1/debt/timeline")
        assert r.status_code == 200
        body = r.json()
        meta = body.get("_meta")
        assert meta is not None, "/debt/timeline missing _meta"
        # UPDATED after the F8 finding on PR #136. This asserted the constant
        # "billion_kes" while the rows in the same response carried
        # unit="KES" — it pinned the contradiction rather than the property.
        # The invariant is that the response-level unit AGREES with its rows,
        # which holds whichever side of the 3a migration the database is on.
        rows = body.get("timeline") or []
        if rows and rows[0].get("unit"):
            assert meta["unit"] == ("KES" if rows[0]["unit"] == "KES" else "billion_kes")
        else:
            assert meta["unit"] == "billion_kes"
        assert meta["entity_scope"] == "national"

    def test_budget_overview_has_meta(self, client, seed_unit_test_data):
        r = client.get("/api/v1/budget/overview")
        assert r.status_code == 200
        meta = r.json().get("_meta")
        assert meta is not None, "/budget/overview missing _meta"
        # This endpoint returns mixed units; meta must document them
        assert "sectors_unit" in meta
        assert "fiscal_history_unit" in meta
        assert meta["sectors_unit"] == "kes"
        assert meta["fiscal_history_unit"] == "billion_kes"

    def test_budget_national_has_meta(self, client, seed_unit_test_data):
        r = client.get("/api/v1/budget/national")
        assert r.status_code == 200
        meta = r.json().get("_meta")
        assert meta is not None, "/budget/national missing _meta"
        assert meta["unit"] == "kes"
        assert meta["entity_scope"] == "national"

    def test_budget_utilization_has_meta(self, client, seed_unit_test_data):
        r = client.get("/api/v1/budget/utilization")
        assert r.status_code == 200
        meta = r.json().get("_meta")
        assert meta is not None, "/budget/utilization missing _meta"
        assert meta["unit"] == "kes"
        assert meta["entity_scope"] == "county"

    def test_budget_enhanced_has_meta(self, client, seed_unit_test_data):
        r = client.get("/api/v1/budget/enhanced")
        assert r.status_code == 200
        meta = r.json().get("_meta")
        assert meta is not None, "/budget/enhanced missing _meta"
        assert meta["revenue_by_source_unit"] == "billion_kes"
        assert meta["execution_by_sector_unit"] == "kes"
        assert meta["economic_context_units"] == "field_name_suffixed"

    def test_fiscal_outturns_has_meta(self, client, seed_unit_test_data):
        r = client.get("/api/v1/dashboards/national/fiscal-outturns")
        assert r.status_code == 200
        body = r.json()
        assert body.get("unit") == "billion_kes"
        meta = body.get("_meta")
        assert meta is not None
        assert meta["unit"] == "billion_kes"
        assert meta["entity_scope"] == "national"

    def test_debt_sustainability_has_meta(self, client, seed_unit_test_data):
        r = client.get("/api/v1/debt/sustainability")
        assert r.status_code == 200
        meta = r.json().get("_meta")
        assert meta is not None, "/debt/sustainability missing _meta"
        assert meta["unit"] == "percentage"
        assert meta["entity_scope"] == "national"


# ── Plausibility bound tests ─────────────────────────────────────────


class TestPlausibilityBounds:
    """Monetary values must stay within order-of-magnitude bounds."""

    def test_fiscal_summary_values_are_billions(self, client, seed_unit_test_data):
        """FiscalSummary values should be smallish numbers (< 20,000 billion)."""
        r = client.get("/api/v1/fiscal/summary")
        assert r.status_code == 200
        current = r.json().get("current", {})
        budget = current.get("appropriated_budget", 0)
        # Must be in billions: 3310 not 3_310_000_000_000
        assert (
            budget < 20_000
        ), f"appropriated_budget={budget} too large for billion_kes"
        assert budget > 100, f"appropriated_budget={budget} too small — wrong unit?"

    def test_debt_timeline_values_are_billions(self, client, seed_unit_test_data):
        r = client.get("/api/v1/debt/timeline")
        assert r.status_code == 200
        timeline = r.json().get("timeline", [])
        assert len(timeline) > 0
        total = timeline[-1]["total"]
        assert total < 50_000, f"debt total={total} too large for billion_kes"
        assert total > 10, f"debt total={total} too small — wrong unit?"

    def test_budget_overview_sectors_are_raw_kes(self, client, seed_unit_test_data):
        """Sector amounts from BudgetLine should be raw KES (large numbers)."""
        r = client.get("/api/v1/budget/overview")
        assert r.status_code == 200
        sectors = r.json().get("sectors", [])
        non_zero = [s for s in sectors if s.get("amount", 0) > 0]
        for s in non_zero:
            amount = s["amount"]
            # Raw KES values should be > 1M
            assert (
                amount > 1_000_000
            ), f"sector {s.get('name')} amount={amount} too small for raw KES"

    def test_budget_overview_summary_has_no_mixed_units(
        self, client, seed_unit_test_data
    ):
        """summary must not contain billion-KES fields alongside raw-KES fields."""
        r = client.get("/api/v1/budget/overview")
        assert r.status_code == 200
        summary = r.json().get("summary", {})
        # These FiscalSummary-sourced billion-KES fields must NOT appear
        for forbidden in [
            "development_budget",
            "recurrent_budget",
            "county_allocation",
            "total_revenue",
            "total_borrowing",
            "_unit_note",
        ]:
            assert (
                forbidden not in summary
            ), f"summary still contains mixed-unit field '{forbidden}'"
        # These raw-KES fields must still be present
        assert "total_budget" in summary
        assert "total_spent" in summary
        assert "execution_rate" in summary
