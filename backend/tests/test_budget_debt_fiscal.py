"""
Tests for budget, debt, and fiscal endpoints.

Covers:
  GET /api/v1/budget/national
  GET /api/v1/budget/utilization
  GET /api/v1/budget/overview
  GET /api/v1/budget/enhanced
  GET /api/v1/debt/timeline
  GET /api/v1/debt/top-loans
  GET /api/v1/debt/loans
  GET /api/v1/debt/national
  GET /api/v1/fiscal/summary
  GET /api/v1/pending-bills
  GET /api/v1/pending-bills/summary
  GET /api/v1/pending-bills/counties/{county_id}
  GET /api/v1/debt/sustainability
"""

from datetime import datetime

import pytest
from models import (
    BillType,
    BudgetLine,
    DebtCategory,
    DebtTimeline,
    Entity,
    EntityType,
    FiscalPeriod,
    FiscalSummary,
    Loan,
    PendingBill,
)


@pytest.fixture()
def seed_budget_data(db_session, seed_country, seed_source_doc):
    """Seed budget, debt timeline, and fiscal summary data."""
    entity = Entity(
        id=30,
        country_id=seed_country.id,
        type=EntityType.NATIONAL,
        canonical_name="National Treasury",
        slug="national-treasury",
    )
    db_session.add(entity)
    db_session.flush()

    fp = FiscalPeriod(
        id=30,
        country_id=seed_country.id,
        label="FY2024/25",
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    db_session.add(fp)
    db_session.flush()

    # Budget line
    bl = BudgetLine(
        entity_id=entity.id,
        period_id=fp.id,
        category="Education",
        allocated_amount=500_000_000_000,
        actual_spent=420_000_000_000,
        currency="KES",
        source_document_id=seed_source_doc.id,
    )
    db_session.add(bl)

    # Debt timeline entry
    dt = DebtTimeline(
        year=2024,
        external=3_500_000_000_000,
        domestic=4_800_000_000_000,
        total=8_300_000_000_000,
        gdp=14_000_000_000_000,
        gdp_ratio=59.3,
    )
    db_session.add(dt)

    # Fiscal summary
    fs = FiscalSummary(
        fiscal_year="2024/25",
        appropriated_budget=3_600_000_000_000,
        total_revenue=2_800_000_000_000,
        tax_revenue=2_200_000_000_000,
        non_tax_revenue=400_000_000_000,
        total_borrowing=800_000_000_000,
        debt_service_cost=1_000_000_000_000,
        development_spending=700_000_000_000,
        recurrent_spending=2_100_000_000_000,
        county_allocation=400_000_000_000,
    )
    db_session.add(fs)

    # Loan
    loan = Loan(
        entity_id=entity.id,
        lender="China EXIM Bank",
        debt_category=DebtCategory.EXTERNAL_BILATERAL,
        principal=500_000_000_000,
        outstanding=350_000_000_000,
        currency="KES",
        source_document_id=seed_source_doc.id,
        issue_date=datetime(2018, 6, 1),
    )
    db_session.add(loan)

    db_session.commit()
    return entity


class TestNationalBudget:
    """Tests for GET /api/v1/budget/national."""

    def test_returns_200(self, client):
        response = client.get("/api/v1/budget/national")
        assert response.status_code == 200

    def test_returns_data_structure(self, client, seed_budget_data):
        data = client.get("/api/v1/budget/national").json()
        assert isinstance(data, (dict, list))


class TestBudgetUtilization:
    """Tests for GET /api/v1/budget/utilization."""

    def test_returns_200(self, client):
        response = client.get("/api/v1/budget/utilization")
        assert response.status_code == 200


class TestBudgetOverview:
    """Tests for GET /api/v1/budget/overview."""

    def test_returns_200(self, client):
        response = client.get("/api/v1/budget/overview")
        assert response.status_code == 200

    def test_returns_overview_data(self, client, seed_budget_data):
        data = client.get("/api/v1/budget/overview").json()
        assert isinstance(data, (dict, list))


class TestBudgetEnhanced:
    """Tests for GET /api/v1/budget/enhanced."""

    def test_returns_200(self, client):
        response = client.get("/api/v1/budget/enhanced")
        assert response.status_code == 200


class TestDebtTimeline:
    """Tests for GET /api/v1/debt/timeline."""

    def test_returns_200(self, client):
        response = client.get("/api/v1/debt/timeline")
        assert response.status_code == 200

    def test_returns_timeline_data(self, client, seed_budget_data):
        data = client.get("/api/v1/debt/timeline").json()
        assert isinstance(data, (dict, list))


class TestDebtTopLoans:
    """Tests for GET /api/v1/debt/top-loans."""

    def test_returns_200(self, client):
        response = client.get("/api/v1/debt/top-loans")
        assert response.status_code == 200


class TestDebtLoans:
    """Tests for GET /api/v1/debt/loans."""

    def test_returns_200(self, client):
        response = client.get("/api/v1/debt/loans")
        assert response.status_code == 200

    def test_returns_loans_data(self, client, seed_budget_data):
        data = client.get("/api/v1/debt/loans").json()
        assert isinstance(data, (dict, list))


class TestDebtNational:
    """Tests for GET /api/v1/debt/national."""

    def test_returns_200(self, client):
        response = client.get("/api/v1/debt/national")
        assert response.status_code == 200


class TestFiscalSummary:
    """Tests for GET /api/v1/fiscal/summary."""

    def test_returns_200(self, client):
        response = client.get("/api/v1/fiscal/summary")
        assert response.status_code == 200

    def test_returns_fiscal_data(self, client, seed_budget_data):
        data = client.get("/api/v1/fiscal/summary").json()
        assert isinstance(data, (dict, list))


class TestPendingBills:
    """Tests for GET /api/v1/pending-bills."""

    def test_returns_200(self, client):
        response = client.get("/api/v1/pending-bills")
        assert response.status_code == 200

    def test_returns_data(self, client):
        data = client.get("/api/v1/pending-bills").json()
        assert isinstance(data, (dict, list))


# ── Fixtures for pending bills + debt sustainability ──────────────────


@pytest.fixture()
def seed_pending_bills(db_session, seed_country, seed_source_doc):
    """Seed pending bills data for a county entity."""
    county = Entity(
        id=40,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Nairobi",
        slug="nairobi",
    )
    db_session.add(county)
    db_session.flush()

    bills = [
        PendingBill(
            entity_id=county.id,
            bill_type=BillType.SUPPLIER_ARREARS,
            amount=500_000_000,
            fiscal_year="2024/25",
            aging_days=45,
            source_document_id=seed_source_doc.id,
        ),
        PendingBill(
            entity_id=county.id,
            bill_type=BillType.SALARY,
            amount=200_000_000,
            fiscal_year="2024/25",
            aging_days=10,
            source_document_id=seed_source_doc.id,
        ),
        PendingBill(
            entity_id=county.id,
            bill_type=BillType.PENSION,
            amount=100_000_000,
            fiscal_year="2023/24",
            aging_days=200,
            source_document_id=seed_source_doc.id,
        ),
    ]
    for b in bills:
        db_session.add(b)

    db_session.commit()
    return county


@pytest.fixture()
def seed_debt_sustainability(db_session, seed_country, seed_source_doc):
    """Seed debt timeline + fiscal summary for sustainability tests."""
    entity = Entity(
        id=50,
        country_id=seed_country.id,
        type=EntityType.NATIONAL,
        canonical_name="National Treasury",
        slug="national-treasury-sust",
    )
    db_session.add(entity)
    db_session.flush()

    # Multiple years of debt timeline for projection tests
    for i, (yr, ext, dom, tot, gdp, ratio) in enumerate([
        (2020, 3000, 3500, 6500, 10500, 61.9),
        (2021, 3200, 3800, 7000, 11200, 62.5),
        (2022, 3400, 4200, 7600, 12500, 60.8),
        (2023, 3600, 4500, 8100, 13200, 61.4),
        (2024, 3800, 4800, 8600, 14000, 61.4),
    ]):
        dt = DebtTimeline(
            year=yr,
            external=ext * 1_000_000_000,
            domestic=dom * 1_000_000_000,
            total=tot * 1_000_000_000,
            gdp=gdp * 1_000_000_000,
            gdp_ratio=ratio,
        )
        db_session.add(dt)

    fs = FiscalSummary(
        fiscal_year="2024/25",
        appropriated_budget=3_600_000_000_000,
        total_revenue=2_800_000_000_000,
        tax_revenue=2_200_000_000_000,
        debt_service_cost=1_000_000_000_000,
    )
    db_session.add(fs)
    db_session.commit()
    return entity


# ── Pending Bills Summary ──────────────────────────────────────────────


class TestPendingBillsSummary:
    """Tests for GET /api/v1/pending-bills/summary."""

    def test_with_data_returns_summary(self, client, seed_pending_bills):
        data = client.get("/api/v1/pending-bills/summary").json()
        assert data["status"] == "success"
        assert data["total_pending_amount"] == 800_000_000  # 500M + 200M + 100M
        assert "supplier_arrears" in data["breakdown_by_type"]
        assert "salary" in data["breakdown_by_type"]
        assert data["breakdown_by_type"]["supplier_arrears"] == 500_000_000

    def test_aging_buckets(self, client, seed_pending_bills):
        data = client.get("/api/v1/pending-bills/summary").json()
        buckets = data["aging_buckets"]
        assert buckets["0-30d"] == 200_000_000  # salary (10 days)
        assert buckets["31-90d"] == 500_000_000  # supplier (45 days)
        assert buckets["180d+"] == 100_000_000  # pension (200 days)

    def test_trend_has_entries(self, client, seed_pending_bills):
        data = client.get("/api/v1/pending-bills/summary").json()
        assert len(data["trend"]) >= 1

    def test_top_counties(self, client, seed_pending_bills):
        data = client.get("/api/v1/pending-bills/summary").json()
        assert len(data["top_counties_by_amount"]) >= 1
        assert data["top_counties_by_amount"][0]["county"] == "Nairobi"


# ── Pending Bills by County ───────────────────────────────────────────


class TestPendingBillsByCounty:
    """Tests for GET /api/v1/pending-bills/counties/{county_id}."""

    def test_unknown_county_returns_404(self, client):
        response = client.get("/api/v1/pending-bills/counties/999")
        assert response.status_code == 404

    def test_county_by_slug(self, client, seed_pending_bills):
        data = client.get("/api/v1/pending-bills/counties/nairobi").json()
        assert data["status"] == "success"
        assert data["county"] == "Nairobi"
        assert data["total_pending"] == 800_000_000

    def test_county_by_id(self, client, seed_pending_bills):
        data = client.get("/api/v1/pending-bills/counties/40").json()
        assert data["status"] == "success"
        assert data["total_pending"] == 800_000_000

    def test_county_breakdown_by_type(self, client, seed_pending_bills):
        data = client.get("/api/v1/pending-bills/counties/nairobi").json()
        assert "supplier_arrears" in data["breakdown_by_type"]
        assert data["breakdown_by_type"]["supplier_arrears"] == 500_000_000

    def test_county_aging_buckets(self, client, seed_pending_bills):
        data = client.get("/api/v1/pending-bills/counties/nairobi").json()
        assert data["aging_buckets"]["31-90d"] == 500_000_000

    def test_county_bills_detail(self, client, seed_pending_bills):
        data = client.get("/api/v1/pending-bills/counties/nairobi").json()
        assert len(data["bills"]) == 3


# ── Debt Sustainability ───────────────────────────────────────────────


class TestDebtSustainability:
    """Tests for GET /api/v1/debt/sustainability."""

    def test_with_data_debt_to_gdp(self, client, seed_debt_sustainability):
        data = client.get("/api/v1/debt/sustainability").json()
        assert data["status"] == "success"
        d2g = data["debt_to_gdp"]
        assert d2g is not None
        assert d2g["value"] == 61.4
        assert d2g["year"] == 2024
        assert d2g["threshold_imf"] == 55.0
        assert d2g["status"] == "above"

    def test_debt_service_to_revenue(self, client, seed_debt_sustainability):
        data = client.get("/api/v1/debt/sustainability").json()
        ds2r = data["debt_service_to_revenue"]
        assert ds2r is not None
        # 1T / 2.8T * 100 = 35.7%
        assert ds2r["value"] == 35.7
        assert ds2r["status"] == "above"

    def test_external_debt_share(self, client, seed_debt_sustainability):
        data = client.get("/api/v1/debt/sustainability").json()
        ext = data["external_debt_share"]
        assert ext is not None
        # 3800B / 8600B * 100 = 44.2%
        assert ext == 44.2

    def test_projections(self, client, seed_debt_sustainability):
        data = client.get("/api/v1/debt/sustainability").json()
        proj = data["projections"]
        assert len(proj) == 5
        assert proj[0]["year"] == 2025
        assert "projected_debt_to_gdp" in proj[0]

    def test_regional_peers(self, client, seed_debt_sustainability):
        data = client.get("/api/v1/debt/sustainability").json()
        peers = data["regional_peers"]
        assert len(peers) == 5
        countries = [p["country"] for p in peers]
        assert "Kenya" in countries
        assert "Tanzania" in countries
        # Kenya's value should come from DB
        kenya_peer = next(p for p in peers if p["country"] == "Kenya")
        assert kenya_peer["debt_to_gdp"] == 61.4
