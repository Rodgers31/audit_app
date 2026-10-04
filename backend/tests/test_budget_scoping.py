"""
Tests for budget query scoping — ensures endpoints filter by fiscal period and entity type.

These tests reproduce the bug where budget overview, national budget, and utilization
endpoints were summing ALL budget lines across ALL fiscal periods and ALL entity types,
producing wildly inflated totals.
"""

from datetime import datetime

import pytest
from models import BudgetLine, Entity, EntityType, FiscalPeriod


@pytest.fixture()
def seed_multi_period_data(db_session, seed_country, seed_source_doc):
    """Seed budget lines across multiple fiscal periods and entity types.

    Creates a scenario that would expose unscoped queries:
    - 2 counties with budget lines in FY2024/25
    - 1 national entity with budget lines in FY2023/24 and FY2024/25
    """
    # Synthetic monetary values on genuine Kenyan county identities: the
    # public overview deliberately refuses invented/foreign county names.
    # Entities
    county_a = Entity(
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Baringo County",
        slug="baringo-county",
    )
    county_b = Entity(
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Kajiado County",
        slug="kajiado-county",
    )
    national = Entity(
        country_id=seed_country.id,
        type=EntityType.NATIONAL,
        canonical_name="National Government",
        slug="national-government",
    )
    db_session.add_all([county_a, county_b, national])
    db_session.flush()

    # Fiscal periods
    fp_old = FiscalPeriod(
        country_id=seed_country.id,
        label="FY2023/24",
        start_date=datetime(2023, 7, 1),
        end_date=datetime(2024, 6, 30),
    )
    fp_current = FiscalPeriod(
        country_id=seed_country.id,
        label="FY2024/25",
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    db_session.add_all([fp_old, fp_current])
    db_session.flush()

    common = {"currency": "KES", "source_document_id": seed_source_doc.id}

    # County A — FY2024/25 only
    db_session.add(
        BudgetLine(
            entity_id=county_a.id,
            period_id=fp_current.id,
            category="Education & Training",
            allocated_amount=10_000_000_000,
            actual_spent=8_000_000_000,
            **common,
        )
    )
    db_session.add(
        BudgetLine(
            entity_id=county_a.id,
            period_id=fp_current.id,
            category="Health",
            allocated_amount=7_000_000_000,
            actual_spent=5_500_000_000,
            **common,
        )
    )

    # County B — FY2024/25 only
    db_session.add(
        BudgetLine(
            entity_id=county_b.id,
            period_id=fp_current.id,
            category="Education & Training",
            allocated_amount=6_000_000_000,
            actual_spent=5_000_000_000,
            **common,
        )
    )

    # National — FY2023/24 (should NOT appear in county overview)
    db_session.add(
        BudgetLine(
            entity_id=national.id,
            period_id=fp_old.id,
            category="Education",
            allocated_amount=500_000_000_000,
            actual_spent=400_000_000_000,
            **common,
        )
    )
    # National — FY2024/25
    db_session.add(
        BudgetLine(
            entity_id=national.id,
            period_id=fp_current.id,
            category="Education",
            allocated_amount=600_000_000_000,
            actual_spent=500_000_000_000,
            **common,
        )
    )

    # County A — old FY (should NOT appear in latest-FY queries)
    db_session.add(
        BudgetLine(
            entity_id=county_a.id,
            period_id=fp_old.id,
            category="Education & Training",
            allocated_amount=9_000_000_000,
            actual_spent=7_000_000_000,
            **common,
        )
    )

    # "Total Budget" aggregate row (should be excluded from sector breakdowns)
    db_session.add(
        BudgetLine(
            entity_id=county_a.id,
            period_id=fp_current.id,
            category="Total Budget",
            allocated_amount=17_000_000_000,
            actual_spent=13_500_000_000,
            **common,
        )
    )

    db_session.commit()
    return {
        "county_a": county_a,
        "county_b": county_b,
        "national": national,
        "fp_old": fp_old,
        "fp_current": fp_current,
    }


class TestBudgetOverviewScoping:
    """Verify /budget/overview only includes county budget lines for the latest FY."""

    def test_excludes_national_budget_lines(self, client, seed_multi_period_data):
        resp = client.get("/api/v1/budget/overview")
        assert resp.status_code == 200
        data = resp.json()
        total = data["summary"]["total_budget"]
        # County-only FY2024/25: 10B + 7B + 6B = 23B
        # If national is leaking: would be 23B + 600B = 623B
        assert (
            total < 100_000_000_000
        ), f"Total {total:,.0f} includes national budget lines — should be county-only"
        assert total == pytest.approx(23_000_000_000, rel=0.01)

    def test_excludes_old_fiscal_periods(self, client, seed_multi_period_data):
        resp = client.get("/api/v1/budget/overview")
        data = resp.json()
        total = data["summary"]["total_budget"]
        # If old FY leaks: county total would be 23B + 9B = 32B
        assert total == pytest.approx(
            23_000_000_000, rel=0.01
        ), f"Total {total:,.0f} includes old fiscal periods"

    def test_excludes_total_budget_category(self, client, seed_multi_period_data):
        resp = client.get("/api/v1/budget/overview")
        data = resp.json()
        sector_names = [s["sector"] for s in data["sectors"]]
        assert "Total Budget" not in sector_names

    def test_reports_fiscal_period(self, client, seed_multi_period_data):
        resp = client.get("/api/v1/budget/overview")
        data = resp.json()
        assert data.get("fiscal_period") == "FY2024/25"

    def test_unknown_county_cannot_select_a_newer_period_or_add_money(
        self, client, db_session, seed_country, seed_source_doc, seed_multi_period_data,
    ):
        unknown = Entity(country_id=seed_country.id, type=EntityType.COUNTY,
                         canonical_name="Alpha County", slug="alpha-county")
        newer = FiscalPeriod(country_id=seed_country.id, label="FY2025/26",
                             start_date=datetime(2025, 7, 1), end_date=datetime(2026, 6, 30))
        db_session.add_all([unknown, newer])
        db_session.flush()
        # A newer unknown county must not displace the legitimate latest FY.
        for period in (newer, seed_multi_period_data["fp_current"]):
            db_session.add(BudgetLine(entity_id=unknown.id, period_id=period.id,
                                     category="Health", allocated_amount=90_000_000_000,
                                     actual_spent=80_000_000_000, currency="KES",
                                     source_document_id=seed_source_doc.id))
        db_session.commit()
        response = client.get("/api/v1/budget/overview")
        assert response.status_code == 200
        data = response.json()
        assert data["fiscal_period"] == "FY2024/25"
        assert data["summary"]["total_budget"] == pytest.approx(23_000_000_000)
        assert "Alpha County" not in str(data.get("county_utilization", {}))

    def test_county_utilization_excludes_national(self, client, seed_multi_period_data):
        resp = client.get("/api/v1/budget/overview")
        data = resp.json()
        util = data.get("county_utilization", {})
        all_counties = util.get("top_5", []) + util.get("bottom_5", [])
        names = [c["county"] for c in all_counties]
        assert "National Government" not in names
        assert "National Treasury" not in names


class TestNationalBudgetScoping:
    """Verify /budget/national only includes national entity budget lines."""

    def test_excludes_county_budget_lines(self, client, seed_multi_period_data):
        resp = client.get("/api/v1/budget/national")
        assert resp.status_code == 200
        data = resp.json()["data"]
        total = data["total"]
        # National FY2024/25 only: 600B
        # If county leaks: 600B + 23B = 623B
        assert total == pytest.approx(
            600_000_000_000, rel=0.01
        ), f"Total {total:,.0f} includes county budget lines"

    def test_defaults_to_latest_national_fy(self, client, seed_multi_period_data):
        resp = client.get("/api/v1/budget/national")
        data = resp.json()["data"]
        # Should be latest national FY (FY2024/25, 600B), not FY2023/24 (500B)
        assert data["total"] == pytest.approx(600_000_000_000, rel=0.01)


class TestBudgetUtilizationScoping:
    """Verify /budget/utilization is scoped to county entities and latest FY."""

    def test_only_county_entities(self, client, seed_multi_period_data):
        resp = client.get("/api/v1/budget/utilization")
        assert resp.status_code == 200
        entities = resp.json()["data"]
        names = [e["entity"] for e in entities]
        assert "National Government" not in names
        assert "National Treasury" not in names

    def test_total_matches_county_only(self, client, seed_multi_period_data):
        resp = client.get("/api/v1/budget/utilization")
        entities = resp.json()["data"]
        total = sum(e["allocated"] for e in entities)
        assert total == pytest.approx(23_000_000_000, rel=0.01)
