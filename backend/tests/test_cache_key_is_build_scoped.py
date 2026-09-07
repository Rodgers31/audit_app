"""A cache entry written by one build must never be served by another.

Follow-up to issue #184. Making the four model-returning endpoints cacheable
introduced a risk that did not exist while they were silently uncached: the
cached value is a **dict**, which FastAPI re-validates against
``response_model`` on the way out. Redis outlives a deploy, so a build that
changes one of those models can read an entry written by the previous build.

OBSERVED on this branch before the fix, by planting an entry under the live
cache key of ``/api/v1/economic/population/latest``:

* entry missing a field that is REQUIRED in the new build  → **500**
* entry whose field has the wrong TYPE                     → **500**
* entry missing a field that is OPTIONAL in the new build  → **200 with a
  silently wrong body** — ``source`` came back ``null`` for a figure that has
  a source.

The third is the dangerous one. It does not fail; it publishes a false
provenance claim, and it keeps doing so until the entry's TTL runs out (up to
an hour for ``population/latest``, twelve for some others).

The fix scopes every key to the build that wrote it, inside ``RedisCache`` so
that all three ``cached`` decorators in this codebase get it without any of
them having to remember.
"""

from __future__ import annotations

import json

import pytest

from models import PopulationData
from tests.test_model_responses_are_cacheable import FakeRedisClient

URL = "/api/v1/economic/population/latest"
SEEDED_POPULATION = 47_564_296


@pytest.fixture()
def cache_with_client(db_session):
    """A live cache pointed at a serialising client, with population seeded."""
    import cache.redis_cache as rc

    db_session.add(
        PopulationData(entity_id=None, year=2019, total_population=SEEDED_POPULATION)
    )
    db_session.commit()

    fake = FakeRedisClient()
    original_client = rc.cache.client
    original_namespace = getattr(rc.cache, "namespace", None)
    rc.cache.client = fake
    rc.cache._memory_cache.clear()
    try:
        yield rc.cache, fake
    finally:
        rc.cache.client = original_client
        if original_namespace is not None:
            rc.cache.namespace = original_namespace
        rc.cache._memory_cache.clear()


#: Pre-deploy entries in the three shapes observed above. Each is a body the
#: PREVIOUS build could legitimately have written and the current one cannot
#: safely serve.
STALE_ENTRIES = {
    "wrong_value": {"population": 111, "year": 1900, "source": "STALE", "updated_at": None},
    "missing_optional_field": {"population": 111, "year": 1900},
    "wrong_type": {"population": "not-a-number", "year": 1900, "source": "STALE"},
}


class TestABuildDoesNotReadAnotherBuildsEntries:
    @pytest.mark.parametrize("shape", sorted(STALE_ENTRIES))
    def test_a_previous_builds_entry_is_not_served(
        self, client, cache_with_client, shape
    ):
        cache, fake = cache_with_client

        # ── build A: warm the endpoint so we learn the real key ──────────
        cache.namespace = "build-A"
        warm = client.get(URL)
        assert warm.status_code == 200, warm.text
        assert fake.store, "nothing was cached; this test would prove nothing"
        key = next(iter(fake.store))

        # Plant what the previous build had written under that exact key.
        fake.store[key] = json.dumps(STALE_ENTRIES[shape])

        # POSITIVE CONTROL. The planted entry must genuinely be reachable
        # within its own build, or "build B ignored it" would be vacuous.
        still_a = client.get(URL)
        assert still_a.content != warm.content or still_a.status_code != 200, (
            "the planted entry was never read back even by the build that "
            "wrote it, so this test cannot show that a LATER build ignores it"
        )

        # ── build B: a deploy. The entry is still physically in Redis. ───
        cache.namespace = "build-B"
        after_deploy = client.get(URL)

        assert after_deploy.status_code == 200, (
            f"a {shape} entry from the previous build broke the endpoint "
            f"({after_deploy.status_code}); it must be ignored, not served"
        )
        body = after_deploy.json()
        assert body["population"] == SEEDED_POPULATION, (
            f"the new build served the previous build's {shape} entry "
            f"({body!r}). Redis outlives a deploy; the key must not."
        )
        assert body["source"] == "KNBS", (
            "the new build published the previous build's provenance "
            f"({body['source']!r}). This is the failure mode that does not "
            "raise — it just states something untrue until the TTL expires."
        )


class TestTheNamespaceIsObservable:
    """A build scope that silently falls back to a shared value protects nothing.

    If ``RENDER_GIT_COMMIT`` is absent in production the namespace is constant
    across deploys and this guard is inert — while looking exactly like a
    working one. So the resolved value and where it came from are reported.
    """

    def test_health_check_reports_the_namespace_and_its_source(
        self, cache_with_client
    ):
        cache, _ = cache_with_client
        health = cache.health_check()
        assert health.get("cache_namespace"), (
            f"health_check() does not say which build scope is in use: {health!r}"
        )
        assert health.get("cache_namespace_source"), (
            "health_check() does not say where the namespace came from, so an "
            "operator cannot tell a real per-deploy scope from the fallback"
        )

    def test_the_namespace_actually_reaches_the_stored_key(self, cache_with_client):
        """Otherwise the whole mechanism is decoration."""
        cache, fake = cache_with_client
        cache.namespace = "build-XYZ"
        cache.set("some:key", {"a": 1}, ttl=60)
        assert fake.store, "nothing was written"
        stored_key = next(iter(fake.store))
        assert "build-XYZ" in stored_key, (
            f"the namespace never reached the key: {stored_key!r}"
        )

    def test_a_value_is_still_readable_within_one_build(self, cache_with_client):
        """POSITIVE CONTROL — scoping must not break ordinary caching."""
        cache, _ = cache_with_client
        cache.namespace = "build-A"
        cache.set("some:key", {"a": 1}, ttl=60)
        assert cache.get("some:key") == {"a": 1}
