"""Public response caches retain the contract while avoiding repeated reads."""

import asyncio
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, RLock

import pytest
from pydantic import BaseModel

from cache import redis_cache as module


class _Payload(BaseModel):
    value: int
    source: str | None = None


@pytest.fixture
def memory_cache(monkeypatch):
    instance = module.RedisCache.__new__(module.RedisCache)
    instance.client = None
    instance.namespace = "test-build"
    instance._memory_cache = {}
    instance._memory_cache_max_size = 3
    instance._metrics = Counter()
    instance._memory_lock = RLock()
    monkeypatch.setattr(module, "cache", instance)
    return instance


def test_filters_pages_defaults_and_response_fidelity(memory_cache):
    calls = []

    @module.cached(ttl=60, key_prefix="findings")
    async def findings(*, county_id=None, page=1, limit=20, db=None):
        calls.append((county_id, page, limit))
        return _Payload(value=len(calls), source="OAG")

    async def exercise():
        first = await findings(county_id=4, page=1, limit=20, db=object())
        second = await findings(limit=20, page=1, county_id=4, db=object())
        other_page = await findings(county_id=4, page=2, db=object())
        other_filter = await findings(county_id=5, db=object())
        return first, second, other_page, other_filter

    first, second, other_page, other_filter = asyncio.run(exercise())
    assert first.model_dump() == _Payload.model_validate(second).model_dump()
    assert [first.value, other_page.value, other_filter.value] == [1, 2, 3]
    assert len(calls) == 3
    assert len(memory_cache._memory_cache) <= 3
    assert all("county_id" not in key for key in memory_cache._memory_cache)


def test_concurrent_identical_cold_requests_coalesce(memory_cache):
    calls = 0

    @module.cached(ttl=60, key_prefix="coalesce")
    async def expensive(*, page=1, db=None):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.02)
        return {"page": page, "calls": calls}

    async def exercise():
        return await asyncio.gather(*(expensive(page=1, db=object()) for _ in range(12)))

    answers = asyncio.run(exercise())
    assert answers == [{"page": 1, "calls": 1}] * 12
    assert calls == 1


def test_sync_cold_requests_coalesce_without_sharing_sessions(memory_cache):
    start = Barrier(2)
    calls = []

    @module.cached(ttl=60, key_prefix="sync-coalesce")
    def expensive(*, page=1, db=None):
        calls.append(db)
        module.time.sleep(0.03)
        return {"page": page, "count": len(calls)}

    def request():
        session = object()
        start.wait()
        return expensive(page=1, db=session)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(request) for _ in range(2)]
        answers = [future.result() for future in futures]
    assert answers == [{"page": 1, "count": 1}] * 2
    assert len(calls) == 1


def test_zero_and_withheld_model_fields_survive_cache(memory_cache):
    class PublicFigure(BaseModel):
        amount: int | None
        source: str | None
        reason: str | None

    @module.cached(ttl=60, key_prefix="public-figure")
    async def figure(*, withheld=False):
        if withheld:
            return PublicFigure(amount=None, source=None, reason="withheld")
        return PublicFigure(amount=0, source="OAG", reason=None)

    async def exercise():
        return (
            await figure(),
            await figure(),
            await figure(withheld=True),
            await figure(withheld=True),
        )

    first, cached_zero, withheld, cached_withheld = asyncio.run(exercise())
    assert PublicFigure.model_validate(cached_zero) == first
    assert PublicFigure.model_validate(cached_withheld) == withheld
    assert first.amount == 0 and first.source == "OAG"
    assert withheld.amount is None and withheld.reason == "withheld"


def test_expiry_invalidation_and_failure_recovery(memory_cache, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(module.time, "time", lambda: now[0])
    calls = 0

    @module.cached(ttl=120, key_prefix="recovery")
    async def public_data(*, page=1):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary database failure")
        return {"status": "success", "calls": calls}

    async def exercise():
        with pytest.raises(RuntimeError):
            await public_data()
        first = await public_data()
        assert await public_data() == first
        now[0] += 121
        expired = await public_data()
        memory_cache._memory_cache.clear()
        invalidated = await public_data()
        return first, expired, invalidated

    first, expired, invalidated = asyncio.run(exercise())
    assert [first["calls"], expired["calls"], invalidated["calls"]] == [2, 3, 4]


def test_transient_unavailable_body_expires_briefly(memory_cache, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(module.time, "time", lambda: now[0])
    calls = 0

    @module.cached(ttl=3600, key_prefix="transient-recovery")
    async def endpoint():
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"status": "unavailable", "value": None}
        return {"status": "success", "value": 0}

    async def exercise():
        first = await endpoint()
        assert await endpoint() == first
        now[0] += module.TRANSIENT_FAILURE_TTL + 1
        return await endpoint()

    assert asyncio.run(exercise()) == {"status": "success", "value": 0}
    assert calls == 2


def test_bounded_entries_for_many_distinct_filters(memory_cache):
    for page in range(10):
        memory_cache.set(f"page:{page}", {"page": page}, ttl=60)
    assert len(memory_cache._memory_cache) == 3
    assert memory_cache.get("page:0") is None
    assert memory_cache.get("page:9") == {"page": 9}


def test_memory_budget_rejects_large_payload_and_evicts_to_total_limit(memory_cache):
    memory_cache._memory_cache_max_entry_bytes = 1_500_000
    memory_cache._memory_cache_max_bytes = 1_700_000
    memory_cache.set("too-large", {"body": "x" * 1_500_000}, ttl=60)
    assert memory_cache.get("too-large") is None
    for page in range(4):
        memory_cache.set(f"page:{page}", {"body": "y" * 600_000}, ttl=60)
    assert sum(entry[2] for entry in memory_cache._memory_cache.values()) <= 1_700_000
    assert len(memory_cache._memory_cache) <= 2


def test_cache_health_reports_bounded_counts_without_keys(memory_cache):
    memory_cache.set("private:query-value", {"value": 1}, ttl=60)
    assert memory_cache.get("private:query-value") == {"value": 1}
    assert memory_cache.get("missing") is None
    health = memory_cache.health_check()
    assert health["response_cache_counters"]["hit"] >= 1
    assert health["response_cache_counters"]["miss"] >= 1
    assert health["memory_entries"] == 1
    assert health["memory_payload_bytes"] > 0
    assert "private:query-value" not in str(health)


def test_late_fill_after_invalidation_is_unreachable(memory_cache, monkeypatch, tmp_path):
    from cache.invalidation import bump_generation

    monkeypatch.setenv("CACHE_GENERATION_FILE", str(tmp_path / "generation"))
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    @module.cached(ttl=60, key_prefix="generation")
    async def endpoint():
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await release.wait()
            return {"value": "stale"}
        return {"value": "fresh"}

    async def exercise():
        first = asyncio.create_task(endpoint())
        await started.wait()
        bump_generation()
        release.set()
        assert await first == {"value": "stale"}
        return await endpoint()

    assert asyncio.run(exercise()) == {"value": "fresh"}
    assert calls == 2


def test_cancelled_loader_does_not_poison_following_request(memory_cache):
    started = asyncio.Event()
    calls = 0

    @module.cached(ttl=60, key_prefix="cancel")
    async def endpoint():
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await asyncio.Event().wait()
        return {"value": "healthy"}

    async def exercise():
        first = asyncio.create_task(endpoint())
        await started.wait()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        return await endpoint()

    assert asyncio.run(exercise()) == {"value": "healthy"}
    assert calls == 2


def test_pipeline_health_uses_short_shared_cache(
    client, monkeypatch, pipeline_health_database
):
    import httpx
    from starlette.responses import JSONResponse

    calls = []

    class FakeResponse:
        status_code = 200

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def head(self, url):
            calls.append(url)
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(module.cache, "client", None)
    module.cache._memory_cache.clear()
    first = client.get("/api/v1/system/pipeline-health")
    second = client.get("/api/v1/system/pipeline-health")
    assert first.status_code == second.status_code == 200
    assert second.content == first.content
    assert first.content == JSONResponse(first.json()).body
    assert len(calls) == 5
    assert first.json()["status"] in {"healthy", "degraded", "unhealthy"}


def test_request_log_uses_route_template_without_query_values(client, caplog):
    marker = "PRIVATE_EVIDENCE_TEXT"
    with caplog.at_level(logging.DEBUG, logger="main"):
        response = client.get(f"/api/v1/audit/findings?query_type={marker}")
    assert response.status_code == 200
    entries = [
        r.getMessage()
        for r in caplog.records
        if r.name == "main" and "http_request" in r.getMessage()
    ]
    assert entries and any('"route":"/api/v1/audit/findings"' in entry for entry in entries)
    assert all(marker not in entry for entry in entries)
