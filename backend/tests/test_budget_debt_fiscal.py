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
    BudgetLine,
    DebtCategory,
    DebtTimeline,
    Entity,
    EntityType,
    FiscalPeriod,
    FiscalSummary,
    Loan,
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
        # Tier B (#137): a published fiscal row cites a page.
        page_ref="s.3.2, report p.16 (PDF p.37)",
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

    def test_total_excludes_pending_bills_but_breakdown_reports_them(
        self, client, db_session, seed_country, seed_source_doc
    ):
        """Headline totals must NOT include PENDING_BILLS rows, but the
        per-category ``summary.pending_bills`` line must still report
        them. PR #84 made the seeding writer actually persist 48
        pending-bills rows into the ``loans`` table for the first
        time, which exposed a latent bug at this aggregator: it was
        summing every loan as debt and the displayed Total Debt KPI
        jumped 11.8T → 13.59T (+702B = the per-row pending bills the
        user confirmed via screen recording). This test pins the
        post-fix behaviour so a future endpoint touching this code
        path can't silently re-inflate the headline.
        """
        entity = Entity(
            id=4090,
            country_id=seed_country.id,
            type=EntityType.NATIONAL,
            canonical_name="National Government 4090",
            slug="national-government-4090",
        )
        db_session.add(entity)
        db_session.flush()

        # Two real-debt loans + one pending-bills row + one NULL-
        # category row. The NULL row is the second half of Copilot's
        # review feedback on PR #90: SQL ``debt_category != X``
        # silently drops NULL rows because of three-valued logic, so
        # the helper now wraps the filter in
        # ``or_(is_(None), != PENDING_BILLS)`` to keep NULLs in the
        # debt total. Test would pass even with the broken filter if
        # we omitted this row.
        db_session.add_all(
            [
                Loan(
                    entity_id=entity.id,
                    lender="Test World Bank",
                    debt_category=DebtCategory.EXTERNAL_MULTILATERAL,
                    principal=1_000_000_000_000,
                    outstanding=900_000_000_000,
                    currency="KES",
                    source_document_id=seed_source_doc.id,
                    issue_date=datetime(2024, 1, 1),
                ),
                Loan(
                    entity_id=entity.id,
                    lender="Test Treasury Bonds",
                    debt_category=DebtCategory.DOMESTIC_BONDS,
                    principal=500_000_000_000,
                    outstanding=480_000_000_000,
                    currency="KES",
                    source_document_id=seed_source_doc.id,
                    issue_date=datetime(2023, 7, 1),
                ),
                Loan(
                    entity_id=entity.id,
                    lender="Test Pending Bills",
                    debt_category=DebtCategory.PENDING_BILLS,
                    principal=200_000_000_000,
                    outstanding=200_000_000_000,
                    currency="KES",
                    source_document_id=seed_source_doc.id,
                    issue_date=datetime(2024, 6, 30),
                ),
                Loan(
                    entity_id=entity.id,
                    lender="Test Legacy Untagged",
                    debt_category=None,  # NULL — must still count as debt
                    principal=50_000_000_000,
                    outstanding=50_000_000_000,
                    currency="KES",
                    source_document_id=seed_source_doc.id,
                    issue_date=datetime(2022, 1, 1),
                ),
            ]
        )
        db_session.commit()

        body = client.get("/api/v1/debt/national").json()
        data = body.get("data", body)

        # Headline excludes the 200B pending-bills row; includes the
        # 50B NULL-category row → total_outstanding = 900 + 480 + 50.
        assert data["total_outstanding"] == 1_430_000_000_000
        # Same shape on the ``total_debt`` (principal sum) field.
        assert data["total_debt"] == 1_550_000_000_000  # 1000 + 500 + 50

        # Per-category breakdown still reports the pending bills.
        summary = data.get("summary", {})
        assert summary.get("pending_bills") == 200_000_000_000


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
    """Seed pending bills for a county entity, the way production stores them.

    Pending bills are ``Loan`` rows in the ``PENDING_BILLS`` category — the
    shape ``seeding/domains/pending_bills/writer.py`` writes. This fixture used
    to seed a ``pending_bills`` table that no production code ever wrote
    (issue #137 P6), so these tests exercised a branch production never ran.
    """
    county = Entity(
        id=40,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Nairobi",
        slug="nairobi",
    )
    db_session.add(county)
    db_session.flush()

    # Declared as the pending_bills fetcher stamps a county row since #238:
    # the Controller of Budget's year-end report, the county side, and the day
    # the figure is a stock on. An undeclared row is withheld (the fixture's
    # invented county figures used to pass as sourced), and the writer retires
    # the previous edition's rows, so a county holds one as-at date.
    for day, (lender, amount) in enumerate(
        [
            ("Pending Bills — Suppliers (Nairobi County)", 500_000_000),
            ("Pending Bills — Salary Arrears (Nairobi County)", 200_000_000),
            ("Pending Bills — Pension Arrears (Nairobi County)", 100_000_000),
        ],
        start=1,
    ):
        db_session.add(
            Loan(
                entity_id=county.id,
                lender=lender,
                debt_category=DebtCategory.PENDING_BILLS,
                principal=amount,
                outstanding=amount,
                issue_date=datetime(2026, 6, day),
                currency="KES",
                source_document_id=seed_source_doc.id,
                provenance={
                    "fiscal_year": "FY2025/26",
                    "source": "cob_pending_bills_etl",
                    "publication": "cob_cbirr_year_end",
                    "category": "county",
                    "as_at": "2026-06-30",
                },
            )
        )

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
        # Tier B (#137): a published fiscal row cites a page.
        page_ref="s.3.2, report p.16 (PDF p.37)",
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
        assert data["data_source"] == "loans_table_fallback"
        # Only the county half is published here, so there is no total: a
        # grand total needs the national BROP lines stated on the same day
        # (see _published_pending_bills). The county figure is in top_counties.
        assert data["total_pending_amount"] is None
        assert data["county_as_at"] == "2026-06-30"
        assert data["top_counties_by_amount"][0]["amount"] == 800_000_000  # 500M + 200M + 100M
        # Typed only where the lender string says so; the rest is unclassified.
        assert data["breakdown_by_type"]["salary"] == 200_000_000
        assert data["breakdown_by_type"]["pension"] == 100_000_000
        assert data["breakdown_by_type"]["unclassified"] == 500_000_000

    def test_aging_is_absent_with_a_reason(self, client, seed_pending_bills):
        """``loans`` carries no bill age, so no age distribution is stated."""
        data = client.get("/api/v1/pending-bills/summary").json()
        assert data["aging_buckets"] is None
        assert data["aging_buckets_absent_reason"] == "loans_table_carries_no_aging_data"

    def test_note_does_not_send_readers_to_a_table_nothing_writes(
        self, client, seed_pending_bills
    ):
        data = client.get("/api/v1/pending-bills/summary").json()
        assert "Seed pending_bills table" not in (data.get("note") or "")

    def test_trend_has_entries(self, client, seed_pending_bills):
        data = client.get("/api/v1/pending-bills/summary").json()
        assert [(p["year"], p["total_amount"]) for p in data["trend"]] == [
            ("FY2025/26", 800_000_000)
        ]

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
        assert data["data_source"] == "loans_table_fallback"
        assert data["county"] == "Nairobi"
        assert data["total_pending"] == 800_000_000

    def test_county_by_id(self, client, seed_pending_bills):
        data = client.get("/api/v1/pending-bills/counties/40").json()
        assert data["status"] == "success"
        assert data["total_pending"] == 800_000_000

    def test_county_breakdown_by_type(self, client, seed_pending_bills):
        data = client.get("/api/v1/pending-bills/counties/nairobi").json()
        assert data["breakdown_by_type"]["salary"] == 200_000_000
        assert data["breakdown_by_type"]["unclassified"] == 500_000_000

    def test_county_aging_is_absent_with_a_reason(self, client, seed_pending_bills):
        data = client.get("/api/v1/pending-bills/counties/nairobi").json()
        assert data["aging_buckets"] is None
        assert data["aging_buckets_absent_reason"] == "loans_table_carries_no_aging_data"

    def test_county_has_no_bill_level_detail(self, client, seed_pending_bills):
        """``loans`` rows are aggregates, not bills; none is presented as one."""
        data = client.get("/api/v1/pending-bills/counties/nairobi").json()
        assert data["bills"] == []


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
        """No published projection seeded → none published.

        This asserted ``len(proj) == 5`` starting at 2025 — the shape of the
        five-year least-squares extrapolation the endpoint used to fit over
        this fixture's five DebtTimeline points and emit as
        ``projected_debt_to_gdp``. It was pinning the defect: the line was
        nobody's forecast, and against the IMF projection that does exist for
        Kenya it ran 2.6 points of GDP low by 2030.

        ``projections`` now carries the IMF WEO series or nothing. This fixture
        seeds no ``imf_weo_observations``, so the answer is nothing, with a
        reason. The populated case is covered in
        tests/test_debt_sustainability_one_label_one_measure.py.
        """
        data = client.get("/api/v1/debt/sustainability").json()
        assert data["projections"] == []
        assert data["projections_absent_reason"] == "no_published_projection_seeded"
        assert data["projections_source"] is None

    def test_regional_peers(self, client, seed_debt_sustainability):
        """Kenya is not special-cased inside its own comparison.

        This asserted ``kenya_peer["debt_to_gdp"] == 61.4`` — this fixture's
        ``DebtTimeline.gdp_ratio``, injected over Kenya's cell while the four
        comparators beside it came from IMF GGXWDG. It was pinning the
        injection: one country in a five-country table measured on a different
        basis from the other four, and on a different basis from the site's
        own declared headline.

        The fixture seeds no ``imf_weo_observations``, so there is no IMF
        reference year and every country — Kenya included — falls through the
        same path. The case where IMF rows ARE seeded, and Kenya's cell equals
        the headline above it by construction, is covered in
        tests/test_debt_to_gdp_is_one_measure_everywhere.py.
        """
        data = client.get("/api/v1/debt/sustainability").json()
        peers = data["regional_peers"]
        assert len(peers) == 5
        countries = [p["country"] for p in peers]
        assert "Kenya" in countries
        assert "Tanzania" in countries

        kenya_peer = next(p for p in peers if p["country"] == "Kenya")
        assert kenya_peer["debt_to_gdp"] != 61.4, "still injecting DebtTimeline"
        # Nothing here is at the reference year, and every row says so.
        assert data["regional_peers_basis"]["debt_to_gdp"]["reference_year"] is None
        assert all(p["debt_to_gdp_year"] is None for p in peers)
