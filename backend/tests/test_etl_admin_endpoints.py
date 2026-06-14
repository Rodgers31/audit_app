"""
Tests for ETL and admin endpoints.

Covers:
  POST /api/v1/admin/etl/run
  GET  /api/v1/admin/etl/status
  GET  /api/v1/admin/etl/schedule
  GET  /api/v1/admin/etl/schedule/summary
  GET  /api/v1/admin/etl/health
  GET  /api/v1/admin/ingestion-jobs
  GET  /api/v1/admin/ingestion-jobs/stats/summary
  GET  /api/v1/etl/status/{job_id}
  GET  /api/v1/etl/kenya/sources
  GET  /api/v1/storage/status
  GET  /api/v1/docs/resolve

Auth assertion convention
-------------------------
Every ``/api/v1/admin/*`` route now goes through ``require_admin`` from
``supabase_auth.py``. With no Bearer token there are exactly two
acceptable outcomes:

  * 401 / 403 — auth machinery rejected the request (expected in CI
    when ``SUPABASE_URL`` etc. are configured)
  * 500       — the auth dependency itself couldn't run because the
    env vars are missing (acceptable in a bare test container; the
    request still didn't reach the handler)

We deliberately do **not** allow 200. If the route ever becomes
publicly readable without a token the test must fail loudly so the
regression is caught in CI rather than discovered in prod logs.
``ADMIN_UNAUTHED`` captures that contract in one place.
"""

ADMIN_UNAUTHED = (401, 403, 500)


class TestETLAdminRun:
    """Tests for POST /api/v1/admin/etl/run."""

    def test_etl_run_returns_response(self, client):
        """ETL run requires auth; unauthenticated calls must NOT succeed."""
        response = client.post("/api/v1/admin/etl/run")
        # 422 covers the case where the handler runs but rejects the
        # body before auth (request-validation errors) — kept because
        # FastAPI evaluates body validation before some dependencies.
        assert response.status_code in ADMIN_UNAUTHED + (422,)


class TestETLAdminStatus:
    """Tests for GET /api/v1/admin/etl/status."""

    def test_returns_status(self, client):
        response = client.get("/api/v1/admin/etl/status")
        # /etl/status is itself admin-gated; 404 is allowed because the
        # route has been removed in some configurations.
        assert response.status_code in ADMIN_UNAUTHED + (404,)


class TestETLSchedule:
    """Tests for GET /api/v1/admin/etl/schedule."""

    def test_returns_schedule(self, client):
        response = client.get("/api/v1/admin/etl/schedule")
        assert response.status_code in ADMIN_UNAUTHED


class TestETLScheduleSummary:
    """Tests for GET /api/v1/admin/etl/schedule/summary."""

    def test_returns_summary(self, client):
        response = client.get("/api/v1/admin/etl/schedule/summary")
        assert response.status_code in ADMIN_UNAUTHED


class TestETLHealth:
    """Tests for GET /api/v1/admin/etl/health."""

    def test_returns_health(self, client):
        response = client.get("/api/v1/admin/etl/health")
        assert response.status_code in ADMIN_UNAUTHED


class TestIngestionJobs:
    """Tests for GET /api/v1/admin/ingestion-jobs."""

    def test_returns_list(self, client):
        response = client.get("/api/v1/admin/ingestion-jobs")
        assert response.status_code in ADMIN_UNAUTHED

    def test_pagination_params(self, client):
        response = client.get("/api/v1/admin/ingestion-jobs?page=1&page_size=5")
        assert response.status_code in ADMIN_UNAUTHED


class TestIngestionJobStats:
    """Tests for GET /api/v1/admin/ingestion-jobs/stats/summary."""

    def test_returns_stats(self, client):
        response = client.get("/api/v1/admin/ingestion-jobs/stats/summary")
        assert response.status_code in ADMIN_UNAUTHED


class TestETLJobStatus:
    """Tests for GET /api/v1/etl/status/{job_id}."""

    def test_returns_status_for_id(self, client):
        response = client.get("/api/v1/etl/status/test-job-123")
        assert response.status_code in (200, 404, 500)


class TestETLKenyaSources:
    """Tests for GET /api/v1/etl/kenya/sources."""

    def test_returns_sources(self, client):
        response = client.get("/api/v1/etl/kenya/sources")
        assert response.status_code == 200

    def test_sources_is_list(self, client):
        data = client.get("/api/v1/etl/kenya/sources").json()
        assert isinstance(data, (list, dict))


class TestStorageStatus:
    """Tests for GET /api/v1/storage/status."""

    def test_returns_200(self, client):
        response = client.get("/api/v1/storage/status")
        assert response.status_code == 200


class TestDocsResolve:
    """Tests for GET /api/v1/docs/resolve."""

    def test_returns_response(self, client):
        response = client.get("/api/v1/docs/resolve")
        assert response.status_code in (200, 422, 400)
