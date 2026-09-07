"""Endpoints that return a Pydantic model were never cached under Redis.

Issue #184. ``RedisCache.set`` serialised with a bare ``json.dumps(value)``.
An endpoint declaring ``response_model`` returns the **model**, and
``json.dumps(BaseModel)`` raises ``TypeError``. One ``except Exception``
wrapped the whole method, so the write was dropped, the entry never appeared,
and every request re-ran the query. The only trace was

    Cache set error: Object of type AuditSummaryResponse is not JSON serializable

which reads like a Redis hiccup and is indistinguishable from one.

WHY IT SURVIVED, and why a careless test here proves nothing. Redis is not
configured in development or in CI, so ``self.client`` is ``None`` and the
in-memory branch stored the object **unserialised**. The defect is invisible
on the path every test takes. A test that does not drive a client which
actually serialises will pass against the broken code.

So these tests install a client with redis-py's storage contract — only
``str``/``bytes``/``int``/``float`` may be stored — and
``test_the_harness_can_observe_a_successful_write`` proves that harness can
record a write, so "nothing was cached" cannot be confused with "the fake is
inert".

The fix normalises in ``RedisCache.set`` for BOTH branches, so the in-memory
cache now stores what Redis would store. Development and CI no longer differ
from production on the one axis that hid this.
"""

from __future__ import annotations

import logging
import re

import pytest

from models import PopulationData

POPULATION_URL = "/api/v1/economic/population/latest"


class FakeRedisClient:
    """Storage contract of a real redis-py client.

    ``setex`` refuses anything that is not ``str``/``bytes``/``int``/``float``
    — the same refusal a real server makes — so a "fix" that hands the model
    straight to the client instead of serialising it still fails here.
    """

    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        if not isinstance(value, (str, bytes, int, float)):
            raise TypeError(
                f"Invalid input of type: {type(value).__name__!r}. "
                "Convert to a bytes, string, int or float first."
            )
        self.store[key] = value

    def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)

    def keys(self, pattern):  # noqa: ARG002
        return []

    def flushdb(self):
        self.store.clear()

    def ping(self):
        return True

    def info(self):
        return {"connected_clients": 1, "used_memory_human": "1M", "uptime_in_seconds": 1}


@pytest.fixture()
def redis_client():
    """Point the module-level cache at a serialising client, as production is."""
    import cache.redis_cache as rc

    fake = FakeRedisClient()
    original = rc.cache.client
    rc.cache.client = fake
    rc.cache._memory_cache.clear()
    try:
        yield fake
    finally:
        rc.cache.client = original
        rc.cache._memory_cache.clear()


@pytest.fixture()
def seeded_population(db_session):
    db_session.add(
        PopulationData(entity_id=None, year=2019, total_population=47_564_296)
    )
    db_session.commit()


@pytest.fixture()
def seeded_audits(db_session, seed_entity, seed_fiscal_period, seed_source_doc):
    """Enough audit findings that wiping them visibly changes every response."""
    from models import Audit, Severity

    for year, amount in ((2022, 1_000_000.0), (2023, 2_500_000.0)):
        db_session.add(
            Audit(
                entity_id=seed_entity.id,
                period_id=seed_fiscal_period.id,
                source_document_id=seed_source_doc.id,
                finding_text=f"probe finding {year}",
                severity=Severity.CRITICAL,
                query_type="Irregular Expenditure",
                amount=amount,
                audit_year=year,
                publishable=True,
            )
        )
    db_session.commit()


#: Every cached endpoint that returns a Pydantic model rather than a dict.
#: Established by driving the live route table against a serialising client,
#: not by reading the source — see the module docstring.
MODEL_ROUTES = [
    "/api/v1/audit/summary",
    "/api/v1/audit/trends",
    "/api/v1/economic/summary",
    "/api/v1/economic/population/latest",
]


class TestModelReturningEndpointsAreCached:
    def test_the_harness_can_observe_a_successful_write(self, redis_client):
        """POSITIVE CONTROL — without this, "nothing cached" proves nothing.

        If the fake client could never record a write, every assertion below
        would pass for the wrong reason.
        """
        import cache.redis_cache as rc

        rc.cache.set("probe:dict", {"a": 1}, ttl=60)
        assert redis_client.store, (
            "the fake client recorded nothing for a plain dict — the harness "
            "is inert and the tests below would be false negatives"
        )
        assert rc.cache.get("probe:dict") == {"a": 1}

    def test_the_response_reaches_the_cache(
        self, client, redis_client, seeded_population
    ):
        """RED before the fix: the store is empty and the log says only
        "Cache set error", the same thing it says when Redis is down."""
        resp = client.get(POPULATION_URL)
        assert resp.status_code == 200, resp.text

        assert redis_client.store, (
            "the response never reached Redis. Every request re-runs the "
            "query; the endpoint is uncached in production."
        )

    def test_a_second_request_is_served_from_the_cache(
        self, client, db_session, redis_client, seeded_population
    ):
        """The behaviour the cache exists for, proved without reading internals.

        The row is deleted between the two requests. A handler that re-runs
        answers 404; only a cache hit can still answer 200.
        """
        first = client.get(POPULATION_URL)
        assert first.status_code == 200, first.text

        db_session.query(PopulationData).delete()
        db_session.commit()

        second = client.get(POPULATION_URL)
        assert second.status_code == 200, (
            "the second request re-ran the query against a now-empty table, "
            f"so it was never cached (got {second.status_code})"
        )
        assert second.content == first.content, (
            "the cached response differs from the uncached one byte-for-byte. "
            "A performance fix must not change what the endpoint says."
        )


class TestSerialisationFailureIsReportable:
    """"Redis is down" and "this value can never be cached" must not look alike.

    The first is transient and self-healing. The second is permanent and needs
    a code change. Reporting both as ``Cache set error`` is why this ran
    uncached in production long enough to be found in a PR review rather than
    by an alert.
    """

    def _cache_with(self, client):
        from cache.redis_cache import RedisCache

        c = RedisCache.__new__(RedisCache)
        c.redis_url = "redis://test"
        c.client = client
        c._memory_cache = {}
        c._memory_cache_max_size = 8
        RedisCache._instances.add(c)
        return c

    def test_an_unserialisable_value_is_counted_as_such(self, caplog):
        class _Unserialisable:
            pass

        cache = self._cache_with(FakeRedisClient())
        with caplog.at_level(logging.ERROR, logger="cache.redis_cache"):
            cache.set("k", _Unserialisable(), ttl=60)

        health = cache.health_check()
        assert health["status"] == "healthy", (
            "this must be asserted against a WORKING Redis — a healthy "
            "connection being handed uncacheable values is the production "
            f"state issue #184 sat in. Got {health!r}"
        )
        assert health.get("unserialisable_values") == 1, (
            "a value that can never be cached left no structural trace — an "
            "operator has only a log line that looks like a Redis blip. "
            f"health_check() returned {health!r}"
        )

    def test_a_redis_outage_is_not_counted_as_a_serialisation_failure(self, caplog):
        class _Down(FakeRedisClient):
            def setex(self, key, ttl, value):
                raise ConnectionError("Error 61 connecting to localhost:6379")

            def ping(self):
                raise ConnectionError("Error 61 connecting to localhost:6379")

        cache = self._cache_with(_Down())
        with caplog.at_level(logging.ERROR, logger="cache.redis_cache"):
            cache.set("k", {"a": 1}, ttl=60)

        health = cache.health_check()
        assert health.get("unserialisable_values") == 0, (
            "a transport outage was classified as a permanent serialisation "
            "failure; the two must stay distinguishable"
        )


class TestNoCachedRouteSilentlyFailsToSerialise:
    """The durable guard: this catches the NEXT model-returning endpoint.

    Walking the live route table rather than a hand-kept list means an
    endpoint added later is covered without anyone remembering to add it.
    """

    @staticmethod
    def _walk(routes):
        for r in routes:
            included = getattr(r, "original_router", None)
            if included is not None:
                yield from TestNoCachedRouteSilentlyFailsToSerialise._walk(
                    included.routes
                )
            elif getattr(r, "path", None) is not None:
                yield r

    @staticmethod
    def _is_cached(fn):
        """``functools.wraps`` overwrites ``__qualname__``; the code object's
        ``co_qualname`` still names where the function was defined."""
        seen = set()
        while fn is not None and id(fn) not in seen:
            seen.add(id(fn))
            code = getattr(fn, "__code__", None)
            if code is not None and "cached.<locals>" in getattr(
                code, "co_qualname", ""
            ):
                return True
            fn = getattr(fn, "__wrapped__", None)
        return False

    def test_no_cached_endpoint_fails_to_serialise(
        self, client, db_session, redis_client, seeded_population, caplog
    ):
        import main

        main.redis_cache.client = redis_client

        routes = [
            r
            for r in self._walk(main.app.routes)
            if "GET" in (getattr(r, "methods", None) or set())
            and self._is_cached(getattr(r, "endpoint", None))
        ]
        assert len(routes) >= 30, (
            f"only {len(routes)} cached routes found — the route walk broke "
            "and this guard is inspecting almost nothing"
        )

        failures, exercised = [], []
        for route in sorted(routes, key=lambda r: r.path):
            url = re.sub(r"\{(\w+)(:[^}]+)?\}", "1", route.path)
            redis_client.store.clear()
            caplog.clear()
            with caplog.at_level(logging.ERROR, logger="cache.redis_cache"):
                resp = client.get(url)
            if resp.status_code == 200:
                exercised.append(route.path)
            for record in caplog.records:
                if "serialis" in record.getMessage().lower() or (
                    "not JSON serializable" in record.getMessage()
                ):
                    failures.append((route.path, record.getMessage()))

        # The four model-returning routes must be among those actually driven,
        # or this sweep would be green because it never reached them.
        must_reach = {
            "/api/v1/audit/summary",
            "/api/v1/audit/trends",
            "/api/v1/economic/summary",
            "/api/v1/economic/population/latest",
        }
        missed = must_reach - set(exercised)
        assert not missed, (
            f"these routes never returned 200, so the sweep did not test "
            f"them: {sorted(missed)}"
        )

        assert not failures, "cached endpoints whose value cannot be stored:\n" + "\n".join(
            f"  {p}\n     {m}" for p, m in failures
        )


class TestCachedAndUncachedBodiesAreIdentical:
    """A performance fix must not change one byte of what the API says.

    The cached path returns a dict, which FastAPI re-validates against
    ``response_model``; the uncached path returns the model itself. Those are
    two different code paths through serialisation, and if they disagreed the
    cache would be quietly rewriting published figures — a behaviour change
    hiding inside a performance fix.

    The rows every one of these endpoints reads are deleted between the two
    requests, so a handler that re-ran could not produce the first body again.
    That, and not an internal counter, is what makes the second response
    provably the cached one.
    """

    @pytest.mark.parametrize("url", MODEL_ROUTES)
    def test_the_cached_body_is_byte_identical(
        self, client, db_session, redis_client, seeded_population, seeded_audits, url
    ):
        from models import Audit

        assert not redis_client.store
        first = client.get(url)
        assert first.status_code == 200, first.text
        assert redis_client.store, f"{url} never reached the cache"

        db_session.query(Audit).delete()
        db_session.query(PopulationData).delete()
        db_session.commit()

        second = client.get(url)
        assert second.status_code == first.status_code
        assert second.content == first.content, (
            f"{url} answers differently from cache than from the database.\n"
            f"  uncached: {first.content[:400]!r}\n"
            f"  cached:   {second.content[:400]!r}"
        )
