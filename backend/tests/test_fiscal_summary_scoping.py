"""
Tests for FiscalSummary-backed and dashboard endpoint scoping.

Verifies that:
 - /dashboards/national/fiscal-outturns uses FiscalSummary (not BudgetLine)
   and excludes years with incomplete data.
 - /dashboards/national/sector-ceilings filters by entity type matching the
   period scope (national-only when national period is used).
 - /budget/enhanced execution_by_sector is period-scoped for the national entity.
"""

from datetime import datetime

import pytest
from models import BudgetLine, Entity, EntityType, FiscalPeriod, FiscalSummary


@pytest.fixture()
def seed_fiscal_and_budget(db_session, seed_country, seed_source_doc):
    """Seed data that exposes FiscalSummary vs BudgetLine mixing.

    Creates:
    - 2 FiscalSummary rows (national-scope, in billions KES):
        FY2023/24: complete (revenue + spending)
        FY2022/23: incomplete (no spending → should be filtered from outturns)
    - 1 national entity with BudgetLines in FY2023/24
    - 1 county entity with BudgetLines in FY2023/24
    """
    # === FiscalSummary rows (national-scope by design) ===
    # Money columns store RAW KES since the stage1 3a migration.
    fs_complete = FiscalSummary(
        fiscal_year="FY2023/24",
        appropriated_budget=3600e9,
        total_revenue=2400e9,
        tax_revenue=1800e9,
        non_tax_revenue=600e9,
        total_borrowing=700e9,
        borrowing_pct_of_budget=19.4,
        debt_service_cost=1100e9,
        development_spending=690e9,
        recurrent_spending=2400e9,
        county_allocation=390e9,
        unit="KES",
        source_document_id=seed_source_doc.id,
    )
    fs_incomplete = FiscalSummary(
        fiscal_year="FY2022/23",
        appropriated_budget=3310e9,
        total_revenue=2166e9,
        tax_revenue=1600e9,
        non_tax_revenue=566e9,
        total_borrowing=600e9,
        # No spending data → should be excluded from fiscal-outturns
        development_spending=None,
        recurrent_spending=None,
        county_allocation=370e9,
        unit="KES",
        source_document_id=seed_source_doc.id,
    )
    db_session.add_all([fs_complete, fs_incomplete])
    db_session.flush()

    # === Entities ===
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

    # === Fiscal period ===
    fp = FiscalPeriod(
        country_id=seed_country.id,
        label="FY2023/24",
        start_date=datetime(2023, 7, 1),
        end_date=datetime(2024, 6, 30),
    )
    db_session.add(fp)
    db_session.flush()

    common = {"currency": "KES", "source_document_id": seed_source_doc.id}

    # === National BudgetLines (10 sectors, large national-scale amounts) ===
    national_sectors = [
        ("Education", 628_500_000_000, 558_396_000_000),
        ("Defense", 157_000_000_000, 149_818_000_000),
        ("Health", 135_600_000_000, 110_500_000_000),
    ]
    for cat, alloc, spent in national_sectors:
        db_session.add(
            BudgetLine(
                entity_id=national.id,
                period_id=fp.id,
                category=cat,
                allocated_amount=alloc,
                actual_spent=spent,
                committed_amount=alloc,  # marks as NG-BIRR data
                **common,
            )
        )

    # === County BudgetLines (smaller amounts, different categories) ===
    county_sectors = [
        ("Education & Training", 4_000_000_000, 3_200_000_000),
        ("Health Services", 2_500_000_000, 2_100_000_000),
        ("Agriculture", 1_200_000_000, 900_000_000),
    ]
    for cat, alloc, spent in county_sectors:
        db_session.add(
            BudgetLine(
                entity_id=county.id,
                period_id=fp.id,
                category=cat,
                allocated_amount=alloc,
                actual_spent=spent,
                **common,
            )
        )

    db_session.commit()
    return {
        "national": national,
        "county": county,
        "fp": fp,
        "fs_complete": fs_complete,
        "fs_incomplete": fs_incomplete,
    }


class TestFiscalOutturnsScoping:
    """Verify /dashboards/national/fiscal-outturns uses FiscalSummary, not BudgetLine."""

    def test_uses_fiscal_summary_data(self, client, seed_fiscal_and_budget):
        """Revenue/expenditure should come from FiscalSummary (billions), not BudgetLine."""
        resp = client.get("/api/v1/dashboards/national/fiscal-outturns")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data_source"] == "database"
        series = data["series"]
        assert len(series) >= 1

        # FiscalSummary FY2023/24 has revenue=2400 (billion KES).
        # BudgetLine national total = ~921B (actual KES) or county = ~7.7B.
        # If BudgetLine were being used, revenue would be < 1000B
        # (or ~921B which is billion-scale but the wrong value).
        fy2324 = next((s for s in series if "2023/24" in s["period"]), None)
        assert fy2324 is not None, "FY2023/24 missing from series"
        # Revenue should match FiscalSummary.total_revenue = 2400 (billion)
        assert fy2324["revenue"] == pytest.approx(2400, rel=0.01)

    def test_excludes_incomplete_years(self, client, seed_fiscal_and_budget):
        """Years with zero revenue or zero expenditure should be excluded."""
        resp = client.get("/api/v1/dashboards/national/fiscal-outturns")
        series = resp.json()["series"]
        # FY2022/23 has no spending data → should be excluded
        fy2223 = next((s for s in series if "2022/23" in s["period"]), None)
        assert (
            fy2223 is None
        ), f"FY2022/23 should be excluded (no spending data) but got: {fy2223}"

    def test_no_county_budgetline_mixing(self, client, seed_fiscal_and_budget):
        """Revenue figures should not include any BudgetLine allocated_amount values."""
        resp = client.get("/api/v1/dashboards/national/fiscal-outturns")
        series = resp.json()["series"]
        for entry in series:
            # BudgetLine values are in actual KES (billions scale),
            # FiscalSummary values are stored as billions (2400 = 2400B KES).
            # No entry should have revenue matching BudgetLine totals.
            revenue = entry["revenue"]
            # County total = 7.7B actual KES; national total = 921B actual KES
            # These would appear as large numbers if leaked
            assert revenue < 10_000, (
                f"Revenue {revenue} looks like BudgetLine data (actual KES), "
                "not FiscalSummary (billions)"
            )

    def test_includes_unit_field(self, client, seed_fiscal_and_budget):
        resp = client.get("/api/v1/dashboards/national/fiscal-outturns")
        data = resp.json()
        assert data.get("unit") == "billion_kes"


class TestSectorCeilingsScoping:
    """Verify /dashboards/national/sector-ceilings filters by entity type."""

    def test_excludes_county_categories(self, client, seed_fiscal_and_budget):
        """When national period is selected, county BudgetLines should be excluded."""
        resp = client.get("/api/v1/dashboards/national/sector-ceilings")
        assert resp.status_code == 200
        data = resp.json()
        # County-specific categories should not appear
        keys = list(data.keys())
        county_cats = [
            k for k in keys if "training" in k.lower() or "services" in k.lower()
        ]
        assert (
            len(county_cats) == 0
        ), f"County categories leaked into national sector-ceilings: {county_cats}"

    def test_total_matches_national_only(self, client, seed_fiscal_and_budget):
        """Total amount should be national BudgetLines only."""
        resp = client.get("/api/v1/dashboards/national/sector-ceilings")
        data = resp.json()
        total = data.get("total_amount", 0)
        # National total: 628.5B + 157B + 135.6B = 921.1B
        # County total: 4B + 2.5B + 1.2B = 7.7B
        # If county leaks: total would be ~928.8B
        assert total == pytest.approx(
            921_100_000_000, rel=0.01
        ), f"Total {total:,.0f} includes county data"


class TestBudgetEnhancedScoping:
    """Verify /budget/enhanced execution_by_sector is period-scoped."""

    def test_returns_national_sectors(self, client, seed_fiscal_and_budget):
        resp = client.get("/api/v1/budget/enhanced")
        assert resp.status_code == 200
        data = resp.json()
        sectors = data.get("execution_by_sector", [])
        names = [s["sector"] for s in sectors]
        # Should have national sectors, not county categories
        assert len(sectors) >= 1
        # Check no county-specific "Education & Training" leaks as a separate sector
        for s in sectors:
            assert (
                "Training" not in s["sector"]
            ), f"County category '{s['sector']}' leaked into national execution"

    def test_economic_context_from_fiscal_summary(self, client, seed_fiscal_and_budget):
        """Economic context should come from FiscalSummary, not BudgetLine."""
        resp = client.get("/api/v1/budget/enhanced")
        data = resp.json()
        ec = data.get("economic_context", {})
        assert ec.get("fiscal_year") is not None
