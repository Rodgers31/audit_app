"""The cache's own diagnostics must be reachable, and registering them must not
break the probes production actually depends on.

Issue #184 gave ``RedisCache`` two things worth reporting: a count of values it
can never serialise, and the build scope its keys are written under. Both lived
only in ``health_check()``, whose sole caller — ``backend/routers/health.py`` —
``main.py`` never imported. ``/health/detailed`` returned 404. A cache that
cannot report its own failure is the same defect class as a gate that cannot
fail, so the report has to be on a live endpoint.

REGISTERING THAT ROUTER NAIVELY WOULD HAVE BROKEN PRODUCTION. It defined
``/health``, ``/health/live`` and ``/health/ready`` as well, duplicating routes
``main.py`` already serves — and ``include_router`` runs at main.py:1734, well
before those ``@app.api_route`` declarations at 2036, so the router's versions
win. Observed by registering an equivalent router ahead of them:

    GET /health/ready   503 {"status":"starting"}  ->  200 {"status":"ready"}

That is the readiness gate destroyed: Render would send traffic to an instance
whose reference-data bootstrap had not finished. The router's own
``/health/ready`` also returns a ``(dict, int)`` tuple, which FastAPI serialises
as a 200 JSON array rather than a 503.

So the duplicates were removed and ``main.py`` keeps the probes. The router now
contributes only the detailed report. ``TestTheProbesAreNotShadowed`` exists to
fail if those duplicates ever come back.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_cache_counters():
    import cache.redis_cache as rc

    rc.cache._unserialisable_values = 0
    rc.cache._last_unserialisable = None
    yield
    rc.cache._unserialisable_values = 0
    rc.cache._last_unserialisable = None


class TestHealthDetailedIsReachable:
    def test_it_answers_at_all(self, client):
        """RED before this change: 404 — the router was never imported."""
        resp = client.get("/health/detailed")
        assert resp.status_code == 200, (
            f"/health/detailed returned {resp.status_code}; the cache has no "
            "live surface to report on"
        )

    def test_it_reports_the_database_as_healthy_when_it_is(self, client):
        """The DB probe used a raw ``db.execute("SELECT 1")``.

        SQLAlchemy 2.0 raises ArgumentError for a bare string, so the component
        would have reported ``unhealthy`` — and the whole report ``degraded`` —
        against a perfectly good database, on every single call.
        """
        body = client.get("/health/detailed").json()
        db_component = body["components"]["database"]
        assert db_component["status"] == "healthy", (
            "the database is up in this test, but the health report says "
            f"{db_component!r}. A probe that always says 'degraded' is noise "
            "an operator learns to ignore."
        )
        assert body["status"] == "healthy", body

    def test_it_reports_the_cache_build_scope(self, client):
        """So an operator can see whether per-deploy scoping is really active."""
        cache = client.get("/health/detailed").json()["components"]["cache"]
        assert cache.get("cache_namespace"), cache
        assert cache.get("cache_namespace_source"), (
            "the report does not say where the namespace came from, so a "
            f"silent fallback to the shared 'dev' scope is invisible: {cache!r}"
        )

    def test_a_serialisation_failure_becomes_visible_on_the_endpoint(self, client):
        """End to end: the #184 counter now reaches an operator.

        This is the whole point. Before, a value that could never be cached
        produced one log line indistinguishable from a Redis blip and nothing
        queryable at all.
        """
        import cache.redis_cache as rc

        before = client.get("/health/detailed").json()["components"]["cache"]
        assert before["unserialisable_values"] == 0, before

        class _Unserialisable:
            pass

        rc.cache.set("health:probe", _Unserialisable(), ttl=60)

        after = client.get("/health/detailed").json()["components"]["cache"]
        assert after["unserialisable_values"] == 1, (
            f"the endpoint does not surface the failure: {after!r}"
        )
        assert "health:probe" in after.get("last_unserialisable", ""), after


class TestTheProbesAreNotShadowed:
    """Guards, not new behaviour: these pass before and after.

    Their job is to go red if ``routers/health.py`` ever regains the duplicate
    ``/health``, ``/health/live`` or ``/health/ready`` routes — which would be
    registered ahead of main.py's and silently replace them.

    Which of them actually discriminate was measured, not assumed, by
    registering the duplicates and re-running all four:

    * ``test_readiness_is_still_gated_on_bootstrap`` — CATCHES it (200 "ready"
      instead of 503 "starting"). This is the one that matters.
    * ``test_get_health_is_still_main_s_own_body`` — CATCHES it (body shape).
    * ``test_head_health_is_still_served`` — does NOT catch it. Starlette
      derives HEAD from any GET route, so HEAD survives shadowing; the concern
      that UptimeRobot's keepalive would break was unfounded.
    * ``test_liveness_is_still_served`` — does NOT catch it; the duplicate
      returns an identical body.

    The last two are kept as plain regression cover for the probes, not as
    shadowing guards.
    """

    def test_head_health_is_still_served(self, client):
        """UptimeRobot keeps the Render instance warm with this."""
        assert client.request("HEAD", "/health").status_code == 200

    def test_get_health_is_still_main_s_own_body(self, client):
        body = client.get("/health").json()
        assert body.get("status") == "ok", (
            f"/health is no longer served by main.py: {body!r}"
        )
        assert "timestamp" in body, body

    def test_readiness_is_still_gated_on_bootstrap(self, client):
        """The gate that keeps traffic off an un-bootstrapped instance.

        ``_app_ready`` is never set in tests (the client fixture clears the
        startup handlers), so this must report 503 "starting".
        """
        resp = client.get("/health/ready")
        assert resp.status_code == 503, (
            f"readiness returned {resp.status_code} {resp.content!r} while the "
            "app had not bootstrapped. Render would route traffic to it."
        )
        assert resp.json()["status"] == "starting", resp.json()

    def test_liveness_is_still_served(self, client):
        resp = client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive", resp.json()


class TestTheCacheComponentCannotHideAnOutage:
    """"Using the in-memory fallback" means opposite things in dev and in prod.

    Without ``REDIS_URL`` it is the normal, supported mode and reporting the
    app degraded would be noise an operator learns to ignore. WITH ``REDIS_URL``
    set it means Redis was unreachable when the process started and every
    endpoint is now uncached — an incident. ``RedisCache`` could not tell the
    two apart, because ``redis_url`` falls back to ``redis://localhost:6379``
    whether or not the variable was ever set.
    """

    def test_no_redis_configured_is_not_an_incident(self, client):
        import cache.redis_cache as rc

        rc.cache.client = None
        rc.cache.redis_url_configured = False
        body = client.get("/health/detailed").json()
        assert body["components"]["cache"]["redis_configured"] is False
        assert body["status"] == "healthy", (
            "running on the in-memory cache with no Redis configured is the "
            f"normal development mode, not a degraded service: {body!r}"
        )

    def test_configured_but_unreachable_redis_is_reported_degraded(self, client):
        """RED before this change: reported healthy while nothing was cached."""
        import cache.redis_cache as rc

        original = getattr(rc.cache, "redis_url_configured", False)
        rc.cache.client = None
        rc.cache.redis_url_configured = True
        try:
            body = client.get("/health/detailed").json()
            assert body["components"]["cache"]["redis_configured"] is True
            assert body["status"] == "degraded", (
                "REDIS_URL is set but the client never connected, so every "
                "endpoint is running uncached — and the health endpoint calls "
                f"that healthy: {body!r}"
            )
        finally:
            rc.cache.redis_url_configured = original
