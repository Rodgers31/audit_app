"""
Tests for audit dashboard endpoints.

Covers:
  GET /api/v1/audit/summary
  GET /api/v1/audit/trends
  GET /api/v1/audit/recurring
  GET /api/v1/audit/findings
"""

from datetime import datetime
from decimal import Decimal

import pytest
from models import Audit, Entity, EntityType, FiscalPeriod, Severity


@pytest.fixture()
def seed_audit_dashboard(db_session, seed_country, seed_source_doc):
    """Seed multiple audit findings across counties and years."""
    # Two counties
    nairobi = Entity(
        id=100,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Nairobi",
        slug="nairobi-audit",
    )
    mombasa = Entity(
        id=101,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Mombasa",
        slug="mombasa-audit",
    )
    db_session.add_all([nairobi, mombasa])
    db_session.flush()

    fp1 = FiscalPeriod(
        id=100,
        country_id=seed_country.id,
        label="FY2022/23",
        start_date=datetime(2022, 7, 1),
        end_date=datetime(2023, 6, 30),
    )
    fp2 = FiscalPeriod(
        id=101,
        country_id=seed_country.id,
        label="FY2023/24",
        start_date=datetime(2023, 7, 1),
        end_date=datetime(2024, 6, 30),
    )
    db_session.add_all([fp1, fp2])
    db_session.flush()

    audits = [
        # Nairobi, 2022, Financial Irregularity
        Audit(
            entity_id=nairobi.id,
            period_id=fp1.id,
            finding_text="Irregular procurement KES 50M",
            severity=Severity.CRITICAL,
            source_document_id=seed_source_doc.id,
            query_type="Financial Irregularity",
            amount=Decimal("50000000"),
            status="Unresolved",
            audit_opinion="Adverse",
            audit_year=2022,
            follow_up_status="Recurring",
        ),
        # Nairobi, 2023, same query_type (recurring by multi-year)
        Audit(
            entity_id=nairobi.id,
            period_id=fp2.id,
            finding_text="Irregular procurement KES 30M",
            severity=Severity.WARNING,
            source_document_id=seed_source_doc.id,
            query_type="Financial Irregularity",
            amount=Decimal("30000000"),
            status="Unresolved",
            audit_opinion="Qualified",
            audit_year=2023,
        ),
        # Mombasa, 2023, different type
        Audit(
            entity_id=mombasa.id,
            period_id=fp2.id,
            finding_text="Unsupported expenditure KES 10M",
            severity=Severity.WARNING,
            source_document_id=seed_source_doc.id,
            query_type="Unsupported Expenditure",
            amount=Decimal("10000000"),
            status="Resolved",
            audit_opinion="Unqualified",
            audit_year=2023,
        ),
        # Nairobi, 2023, no amount
        Audit(
            entity_id=nairobi.id,
            period_id=fp2.id,
            finding_text="Weak internal controls",
            severity=Severity.INFO,
            source_document_id=seed_source_doc.id,
            query_type="Governance",
            audit_opinion="Qualified",
            audit_year=2023,
        ),
    ]
    db_session.add_all(audits)
    db_session.commit()
    return {"nairobi": nairobi, "mombasa": mombasa, "audits": audits}


# ── Summary ──────────────────────────────────────────────────────────────


class TestAuditSummary:
    def test_returns_200_empty(self, client):
        resp = client.get("/api/v1/audit/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_findings"] == 0
        assert data["total_irregular_expenditure"] == 0

    def test_summary_totals(self, client, seed_audit_dashboard):
        data = client.get("/api/v1/audit/summary").json()
        assert data["total_findings"] == 4
        # Only Financial Irregularity amounts: 50M + 30M = 80M
        assert data["total_irregular_expenditure"] == 80_000_000
        # Unsupported = status != Resolved → 50M + 30M + 0 = 80M (Mombasa resolved excluded)
        assert data["total_unsupported_expenditure"] == 80_000_000

    def test_findings_by_type(self, client, seed_audit_dashboard):
        data = client.get("/api/v1/audit/summary").json()
        assert data["findings_by_type"]["Financial Irregularity"] == 2
        assert data["findings_by_type"]["Unsupported Expenditure"] == 1
        assert data["findings_by_type"]["Governance"] == 1

    def test_findings_by_opinion(self, client, seed_audit_dashboard):
        data = client.get("/api/v1/audit/summary").json()
        assert data["findings_by_opinion"]["Qualified"] == 2
        assert data["findings_by_opinion"]["Adverse"] == 1

    def test_worst_counties(self, client, seed_audit_dashboard):
        data = client.get("/api/v1/audit/summary").json()
        worst = data["worst_counties"]
        assert len(worst) >= 2
        # Nairobi should be first (80M vs 10M)
        assert worst[0]["county_name"] == "Nairobi"
        assert worst[0]["total_amount"] == 80_000_000

    def test_year_range(self, client, seed_audit_dashboard):
        data = client.get("/api/v1/audit/summary").json()
        assert data["year_range"]["min_year"] == 2022
        assert data["year_range"]["max_year"] == 2023


# ── Trends ───────────────────────────────────────────────────────────────


class TestAuditTrends:
    def test_returns_200_empty(self, client):
        resp = client.get("/api/v1/audit/trends")
        assert resp.status_code == 200
        data = resp.json()
        assert data["years"] == []

    def test_trends_all(self, client, seed_audit_dashboard):
        data = client.get("/api/v1/audit/trends").json()
        assert 2022 in data["years"]
        assert 2023 in data["years"]
        assert data["findings_per_year"]["2022"] == 1
        assert data["findings_per_year"]["2023"] == 3

    def test_trends_filter_county(self, client, seed_audit_dashboard):
        data = client.get("/api/v1/audit/trends?county_id=101").json()
        # Only Mombasa
        assert data["years"] == [2023]
        assert data["findings_per_year"]["2023"] == 1

    def test_trends_filter_query_type(self, client, seed_audit_dashboard):
        data = client.get(
            "/api/v1/audit/trends?query_type=Financial+Irregularity"
        ).json()
        assert data["findings_per_year"]["2022"] == 1
        assert data["findings_per_year"]["2023"] == 1

    def test_trends_opinion_per_year(self, client, seed_audit_dashboard):
        data = client.get("/api/v1/audit/trends").json()
        assert data["opinion_per_year"]["2022"]["Adverse"] == 1
        assert data["opinion_per_year"]["2023"]["Qualified"] == 2


# ── Recurring ────────────────────────────────────────────────────────────


class TestAuditRecurring:
    def test_returns_200_empty(self, client):
        resp = client.get("/api/v1/audit/recurring")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    def test_detects_recurring(self, client, seed_audit_dashboard):
        data = client.get("/api/v1/audit/recurring").json()
        assert data["total"] >= 1
        # Nairobi Financial Irregularity appears in 2022 and 2023
        nairobi_fi = [
            r
            for r in data["recurring_findings"]
            if r["county_name"] == "Nairobi"
            and r["query_type"] == "Financial Irregularity"
        ]
        assert len(nairobi_fi) == 1
        assert sorted(nairobi_fi[0]["years_appeared"]) == [2022, 2023]
        assert nairobi_fi[0]["total_amount"] == 80_000_000


# ── Findings List ────────────────────────────────────────────────────────


class TestAuditFindings:
    def test_returns_200_empty(self, client):
        resp = client.get("/api/v1/audit/findings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["page"] == 1

    def test_returns_all_findings(self, client, seed_audit_dashboard):
        data = client.get("/api/v1/audit/findings").json()
        assert data["total"] == 4
        assert len(data["items"]) == 4

    def test_filter_by_county(self, client, seed_audit_dashboard):
        data = client.get("/api/v1/audit/findings?county_id=101").json()
        assert data["total"] == 1
        assert data["items"][0]["county_name"] == "Mombasa"

    def test_filter_by_year(self, client, seed_audit_dashboard):
        data = client.get("/api/v1/audit/findings?year=2022").json()
        assert data["total"] == 1

    def test_filter_by_query_type(self, client, seed_audit_dashboard):
        data = client.get(
            "/api/v1/audit/findings?query_type=Financial+Irregularity"
        ).json()
        assert data["total"] == 2

    def test_pagination(self, client, seed_audit_dashboard):
        data = client.get("/api/v1/audit/findings?page=1&limit=2").json()
        assert data["total"] == 4
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["limit"] == 2

        data2 = client.get("/api/v1/audit/findings?page=2&limit=2").json()
        assert len(data2["items"]) == 2

    def test_finding_detail_fields(self, client, seed_audit_dashboard):
        data = client.get("/api/v1/audit/findings?county_id=100&year=2022").json()
        item = data["items"][0]
        assert item["county_name"] == "Nairobi"
        assert item["query_type"] == "Financial Irregularity"
        assert item["amount"] == 50_000_000
        assert item["audit_opinion"] == "Adverse"
        assert item["follow_up_status"] == "Recurring"
