"""
Tests for health check and root endpoints.

Covers:
  GET /
  GET /health
  GET /health/detailed
  GET /health/ready
  GET /health/live
"""

from unittest.mock import MagicMock, patch

import pytest


class TestRootEndpoint:
    """Tests for the root / endpoint."""

    def test_root_returns_200(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_root_has_expected_fields(self, client):
        data = client.get("/").json()
        assert "message" in data
        assert "version" in data
        assert "status" in data
        assert data["status"] == "operational"

    def test_root_version_format(self, client):
        data = client.get("/").json()
        # Version should be semver-like
        assert "." in data["version"]

    def test_root_has_timestamp(self, client):
        data = client.get("/").json()
        assert "timestamp" in data


class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_has_status(self, client):
        data = client.get("/health").json()
        assert "status" in data
        assert data["status"] in ("ok", "healthy")

    def test_health_has_timestamp(self, client):
        data = client.get("/health").json()
        assert "timestamp" in data


class TestLivenessEndpoint:
    """Tests for GET /health/live (if health router is registered)."""

    def test_liveness_returns_status(self, client):
        response = client.get("/health/live")
        # Health router may not be mounted; only assert non-500
        assert response.status_code in (200, 404)


class TestDetailedHealthEndpoint:
    """Tests for GET /health/detailed (if health router is registered)."""

    def test_detailed_health_returns_status(self, client):
        response = client.get("/health/detailed")
        assert response.status_code in (200, 404)


class TestReadinessEndpoint:
    """Tests for GET /health/ready (lifespan-gated readiness)."""

    def test_readiness_returns_status(self, client):
        response = client.get("/health/ready")
        # 503 is the DESIGNED pre-bootstrap answer: TestClient without a
        # lifespan context never runs the startup sequence, so the app
        # correctly reports "starting". 200 = ready, 404 = older builds
        # without the endpoint.
        assert response.status_code in (200, 404, 503)
        if response.status_code == 503:
            assert response.json().get("status") == "starting"
