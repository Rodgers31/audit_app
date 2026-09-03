"""A transient failure must not be cached for as long as a success.

Issue #141. ``@cached`` stored whatever the handler returned, including the
honest-failure body, for the endpoint's full TTL:

    @app.get("/api/v1/debt/national")
    @cached(key_prefix="debt:national", ttl=43200)

So a database blip poisoned the cache for **12 hours**. Observed in production
on 2026-09-03: the database recovered, ``/debt/timeline`` and
``/fiscal/summary`` immediately served live data, and ``/debt/national`` kept
answering ``database_unavailable`` with ``x-process-time: 0.002`` — it never
reached the database. A cache-busting query param did not clear it; the key
ignores query params.

This is the mirror of the defect PR #135 addressed. That one stopped the API
rendering *absence as a figure*. This one made the API render *presence as
absence*, and pinned it there for half a day.

THE DISTINCTION THAT MATTERS. Not every degraded body is transient:

* ``database_unavailable`` / ``source_unavailable`` — the source could not be
  READ. Transient; a recovered source must be picked up promptly.
* ``database_empty`` / ``not_yet_seeded`` — the source was read and holds
  nothing. That is a durable, correct answer and SHOULD cache normally; an
  empty table does not fill in the next thirty seconds, and re-querying it on
  every request would put load on a database for no new information.

Caching both briefly would trade this bug for a thundering herd.
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.fixture(autouse=True)
def _clear_cache():
    from cache.redis_cache import cache

    cache.clear() if hasattr(cache, "clear") else None
    yield


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestTransientFailuresGetAShortTtl:
    def test_an_unreadable_source_is_not_cached_for_the_full_ttl(self):
        """RED before the fix: the failure body was stored with ttl=43200."""
        from cache.redis_cache import cached

        seen = {}

        class _Recorder:
            def get(self, k):
                return None

            def set(self, k, v, ttl):
                seen[k] = ttl

        import cache.redis_cache as rc

        original = rc.cache
        rc.cache = _Recorder()
        try:
            @cached(ttl=43200, key_prefix="t:transient")
            async def handler():
                return {
                    "status": "no_data",
                    "data_source": "database_unavailable",
                    "reason": "source_unavailable",
                }

            _run(handler())
        finally:
            rc.cache = original

        assert seen, "nothing was cached at all — the fixture proved nothing"
        ttl = next(iter(seen.values()))
        assert ttl < 300, (
            f"a transient failure was cached for {ttl}s. A recovered source "
            "stays invisible for that long."
        )

    def test_a_success_keeps_the_full_ttl(self):
        """POSITIVE CONTROL — the fix must not shorten normal caching."""
        from cache.redis_cache import cached
        import cache.redis_cache as rc

        seen = {}

        class _Recorder:
            def get(self, k):
                return None

            def set(self, k, v, ttl):
                seen[k] = ttl

        original = rc.cache
        rc.cache = _Recorder()
        try:
            @cached(ttl=43200, key_prefix="t:ok")
            async def handler():
                return {"status": "success", "data_source": "database", "data": {"x": 1}}

            _run(handler())
        finally:
            rc.cache = original

        assert next(iter(seen.values())) == 43200

    def test_an_empty_but_readable_source_keeps_the_full_ttl(self):
        """The distinction that keeps this from becoming a thundering herd.

        `database_empty` means the source WAS read and holds nothing — a
        durable answer. Re-querying it every 30s would load the database for
        no new information.
        """
        from cache.redis_cache import cached
        import cache.redis_cache as rc

        seen = {}

        class _Recorder:
            def get(self, k):
                return None

            def set(self, k, v, ttl):
                seen[k] = ttl

        original = rc.cache
        rc.cache = _Recorder()
        try:
            @cached(ttl=43200, key_prefix="t:empty")
            async def handler():
                return {
                    "status": "no_data",
                    "data_source": "database_empty",
                    "reason": "not_yet_seeded",
                }

            _run(handler())
        finally:
            rc.cache = original

        assert next(iter(seen.values())) == 43200, (
            "an empty-but-readable source was given the short TTL; that is a "
            "durable answer and re-querying it every 30s is pure load"
        )


class TestTheClassifierMatchesTheRealResponses:
    """A classifier tuned to an imagined body is worthless. These are the
    exact shapes the API builds, copied from main.py and from the live
    response captured during the 2026-09-03 incident."""

    def test_the_production_debt_national_failure_is_recognised(self):
        from cache.redis_cache import is_transient_failure

        # Captured verbatim from https://www.auditgava.com/api/v1/debt/national
        # while the schema was mismatched.
        live = {
            "status": "no_data",
            "data_source": "database_unavailable",
            "reason": "source_unavailable",
            "last_updated": None,
            "message": (
                "National debt figures are unavailable because the data source "
                "could not be read. This is not a finding that debt is zero."
            ),
            "data": {"total_debt": None, "total_outstanding": None},
        }
        assert is_transient_failure(live) is True

    def test_the_empty_but_readable_twin_is_not(self):
        """Same endpoint, other branch: `_db_unreachable` false."""
        from cache.redis_cache import is_transient_failure

        assert (
            is_transient_failure(
                {
                    "status": "no_data",
                    "data_source": "database_empty",
                    "reason": "not_yet_seeded",
                }
            )
            is False
        )

    def test_a_healthy_response_is_not(self):
        from cache.redis_cache import is_transient_failure

        assert (
            is_transient_failure(
                {"status": "success", "data_source": "database", "data": {"total": 1}}
            )
            is False
        )

    def test_non_dict_results_are_handled(self):
        from cache.redis_cache import is_transient_failure

        for value in ([], "", 0, None, [{"status": "error"}]):
            assert is_transient_failure(value) is False


class TestRecoveryIsVisible:
    """The behaviour the issue is actually about: after the source recovers,
    the next request must serve live data rather than the cached failure."""

    def test_a_recovered_source_is_served_not_the_cached_failure(self, monkeypatch):
        import time as _time

        import main

        # Pin the in-memory path. Not a convenience: production logs
        # "Redis not configured — using in-memory cache", so this IS the code
        # path that ran during the incident, and its expiry is computed in
        # process from time.time() — which the clock jump below can move.
        #
        # CI, unlike production, runs a real Redis service. There `setex` sets
        # a SERVER-side TTL that no patched clock can reach, so an earlier
        # version of this test passed locally and failed in CI while asserting
        # nothing about the defect.
        if getattr(main.redis_cache, "client", None) is not None:
            monkeypatch.setattr(main.redis_cache, "client", None)
        monkeypatch.setattr(main.redis_cache, "_memory_cache", {}, raising=False)
        assert getattr(main.redis_cache, "client", None) is None, (
            "the in-memory path is not pinned; this test would assert nothing "
            "about expiry, because a real Redis owns its own TTL"
        )

        state = {"healthy": False}
        calls = {"n": 0}

        @main.cached(key_prefix="t:recovery", ttl=43200)
        async def endpoint():
            calls["n"] += 1
            if not state["healthy"]:
                return {
                    "status": "no_data",
                    "data_source": "database_unavailable",
                    "reason": "source_unavailable",
                }
            return {"status": "success", "data_source": "database", "total": 42}

        first = _run(endpoint())
        assert first["data_source"] == "database_unavailable"
        assert calls["n"] == 1

        # Still inside the short window: the failure is served from cache, so
        # a struggling database is not hammered by every request.
        second = _run(endpoint())
        assert second["data_source"] == "database_unavailable"
        assert calls["n"] == 1, "the short TTL must still absorb repeat traffic"

        # The source recovers, and the short window elapses.
        state["healthy"] = True
        real_time = _time.time
        monkeypatch.setattr(
            _time, "time", lambda: real_time() + 31
        )

        third = _run(endpoint())
        assert third["status"] == "success", (
            "the recovered source was not served — the failure body outlived "
            "the outage, which is the whole defect"
        )
        assert third["total"] == 42

    def test_a_success_is_not_re_fetched_within_its_ttl(self):
        """POSITIVE CONTROL — normal caching must still work."""
        import main

        calls = {"n": 0}

        @main.cached(key_prefix="t:success-ttl", ttl=43200)
        async def endpoint():
            calls["n"] += 1
            return {"status": "success", "data_source": "database", "total": 7}

        _run(endpoint())
        _run(endpoint())
        assert calls["n"] == 1
