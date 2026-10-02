"""A response begun before refresh cannot refill the money-flow cache."""

import asyncio

import pytest

from cache import invalidation
from cache.redis_cache import RedisCache
from routers import money_flow


@pytest.mark.parametrize("cache_backend", ["memory_instance", "fallback", "redis"])
def test_late_money_flow_fill_is_unreachable_after_refresh(
    monkeypatch, tmp_path, cache_backend
):
    monkeypatch.setenv("CACHE_GENERATION_FILE", str(tmp_path / "generation"))
    monkeypatch.setattr(invalidation, "_seen", None)
    monkeypatch.setattr(invalidation, "_seen_initialised", False)
    if cache_backend == "fallback":
        cache = None
    else:
        cache = RedisCache()
        cache.client = None
        if cache_backend == "redis":
            class Store:
                def __init__(self):
                    self.entries = {}

                def get(self, key):
                    return self.entries.get(key)

                def setex(self, key, ttl, value):
                    self.entries[key] = value

                def scan_iter(self, **kwargs):
                    return iter(list(self.entries))

                def delete(self, *keys):
                    return sum(self.entries.pop(key, None) is not None for key in keys)

            cache.client = Store()
    monkeypatch.setattr(money_flow, "_redis_cache", cache)

    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()
        version = ["before"]
        calls = []

        @money_flow._cached(key_prefix="refresh:money-flow", ttl=1800)
        async def response():
            observed = version[0]
            calls.append(observed)
            if observed == "before":
                entered.set()
                await release.wait()
            return {"version": observed}

        first = asyncio.create_task(response())
        await asyncio.wait_for(entered.wait(), timeout=5)
        try:
            invalidation.invalidate_all()
            version[0] = "after"
        finally:
            release.set()
        assert await asyncio.wait_for(first, timeout=5) == {"version": "before"}
        assert await response() == {"version": "after"}
        assert await response() == {"version": "after"}
        assert calls == ["before", "after"], "the refreshed response must still cache"

    asyncio.run(exercise())
