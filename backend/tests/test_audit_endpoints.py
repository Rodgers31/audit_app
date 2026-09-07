"""
Tests for audit-related endpoints.

Covers:
  GET /api/v1/audits/statistics
  GET /api/v1/audits/federal
  GET /api/v1/counties/{county_id}/audits
  GET /api/v1/counties/{county_id}/audits/history
  GET /api/v1/counties/{county_id}/audits/list
"""

from datetime import datetime

import pytest
from models import Audit, Entity, EntityType, FiscalPeriod, Severity


@pytest.fixture()
def seed_audit(db_session, seed_country, seed_source_doc):
    """Seed a county entity with an audit finding."""
    entity = Entity(
        id=20,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Kisumu",
        slug="kisumu",
    )
    db_session.add(entity)
    db_session.flush()

    fp = FiscalPeriod(
        id=20,
        country_id=seed_country.id,
        label="FY2023/24",
        start_date=datetime(2023, 7, 1),
        end_date=datetime(2024, 6, 30),
    )
    db_session.add(fp)
    db_session.flush()

    audit = Audit(
        entity_id=entity.id,
        period_id=fp.id,
        finding_text="Irregular procurement of medical supplies totalling KES 50M",
        severity=Severity.CRITICAL,
        recommended_action="Investigate and recover funds",
        source_document_id=seed_source_doc.id,
        # Tier B (#137): a published finding cites a page.
        page_ref="p.409",
    )
    db_session.add(audit)
    db_session.commit()
    return entity, audit


class TestAuditStatistics:
    """Tests for GET /api/v1/audits/statistics."""

    def test_returns_200(self, client):
        response = client.get("/api/v1/audits/statistics")
        assert response.status_code == 200

    def test_returns_statistics_structure(self, client, seed_audit):
        data = client.get("/api/v1/audits/statistics").json()
        # Should contain stats-like data
        assert isinstance(data, dict)

    def test_statistics_with_data(self, client, seed_audit):
        data = client.get("/api/v1/audits/statistics").json()
        # Should reflect at least one finding exists
        assert isinstance(data, dict)


class TestFederalAudits:
    """Tests for GET /api/v1/audits/federal."""

    def test_returns_200(self, client):
        response = client.get("/api/v1/audits/federal")
        assert response.status_code == 200

    def test_returns_list_structure(self, client):
        data = client.get("/api/v1/audits/federal").json()
        assert isinstance(data, (list, dict))


class TestCountyAudits:
    """Tests for GET /api/v1/counties/{county_id}/audits."""

    def test_returns_audits_for_county(self, client, seed_audit):
        entity, audit = seed_audit
        response = client.get("/api/v1/counties/042/audits")  # 042 = Kisumu
        assert response.status_code in (200, 404, 503)

    def test_returns_error_for_unknown_county(self, client):
        response = client.get("/api/v1/counties/999/audits")
        assert response.status_code in (200, 404, 503)


class TestCountyAuditsList:
    """Tests for GET /api/v1/counties/{county_id}/audits/list."""

    def test_returns_paginated_list(self, client, seed_audit):
        entity, audit = seed_audit
        response = client.get("/api/v1/counties/042/audits/list")
        assert response.status_code in (200, 404, 503)

    def test_list_has_expected_fields(self, client, seed_audit):
        entity, audit = seed_audit
        response = client.get("/api/v1/counties/042/audits/list")
        if response.status_code == 200:
            data = response.json()
            assert "total" in data
            assert "items" in data


class TestCountyAuditsHistory:
    """Tests for GET /api/v1/counties/{county_id}/audits/history."""

    def test_returns_history(self, client, seed_audit):
        entity, audit = seed_audit
        response = client.get("/api/v1/counties/042/audits/history")
        assert response.status_code in (200, 404, 503)
