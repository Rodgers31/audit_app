"""A hard cache initialization failure still absorbs bounded repeat traffic."""

import asyncio
import datetime
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.responses import JSONResponse, StreamingResponse


def test_hard_cache_failure_caches_repeated_public_reads(monkeypatch):
    import main

    monkeypatch.setattr(main, "redis_cache", None)
    calls = []

    @main.cached("hard-cache-failure")
    async def endpoint(value):
        calls.append(value)
        return {"value": value, "zero": 0, "missing": None}

    async def exercise():
        for value in ("one", "two", "one", "two"):
            assert await endpoint(value=value) == {
                "value": value, "zero": 0, "missing": None
            }

    asyncio.run(exercise())
    assert calls == ["one", "two"], "hard initialization failure bypassed caching"


def test_network_failure_keeps_existing_redis_cache_memory_fallback(monkeypatch):
    import main
    from cache import redis_cache as module

    def unavailable(*args, **kwargs):
        raise module.redis.ConnectionError("inert fixture; no network attempted")

    monkeypatch.setattr(module.redis, "from_url", unavailable)
    cache = module.RedisCache("redis://fixture.invalid:6379")
    assert cache.client is None
    monkeypatch.setattr(main, "redis_cache", cache)
    calls = []

    @main.cached("network-cache-failure")
    async def endpoint():
        calls.append(1)
        return {"value": 7}

    assert asyncio.run(endpoint()) == asyncio.run(endpoint()) == {"value": 7}
    assert calls == [1]
    assert len(cache._memory_cache) == 1


def test_real_main_initialization_failure_uses_independent_fallback():
    # A fresh interpreter executes main's real initialization exception path.
    # No external connection is attempted by the injected constructor failure.
    code = """
import asyncio
from cache import redis_cache

def failed_initialization(self, *args, **kwargs):
    raise RuntimeError('inert hard-initialization fixture')

redis_cache.RedisCache.__init__ = failed_initialization
import main
if main.redis_cache is not None:
    raise RuntimeError('fixture did not reach hard initialization failure')
calls = []
@main.cached('real-hard-initialization')
async def endpoint():
    calls.append(1)
    return {'value': 0, 'missing': None}
async def exercise():
    first = await endpoint()
    warm = await endpoint()
    if first != warm or calls != [1]:
        raise RuntimeError('hard initialization failure bypasses caching')
asyncio.run(exercise())
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr[-4000:]


@pytest.fixture
def process_cache(monkeypatch):
    import main
    from cache.endpoint_memory import BoundedResponseCache

    clock = [100.0]
    cache = BoundedResponseCache(
        max_entries=3, max_bytes=180, max_entry_bytes=120, clock=lambda: clock[0]
    )
    monkeypatch.setattr(main, "redis_cache", None)
    monkeypatch.setattr(main, "_endpoint_memory_cache", cache)
    return cache, clock


def test_all_decorated_endpoints_share_entry_and_serialized_byte_limits(process_cache):
    import main

    cache, _ = process_cache
    calls = []

    def build(prefix):
        @main.cached(prefix)
        async def endpoint(value):
            calls.append((prefix, value))
            return {"value": value, "body": "界" * 15}

        return endpoint

    endpoints = [build(f"bounded-{i}") for i in range(30)]

    async def exercise():
        for i, endpoint in enumerate(endpoints):
            await endpoint(value=i)
            assert len(cache) <= 3
            assert cache.payload_bytes <= 180
        await endpoints[-1](value=29)
        await endpoints[0](value=0)

    asyncio.run(exercise())
    assert len(calls) == 31, "newest entry must hit while the evicted oldest reloads"
    assert cache.payload_bytes == sum(len(entry[0]) for entry in cache._entries.values())
    assert all(len(key) == 64 for key in cache._entries)


def test_entry_limit_uses_actual_json_bytes_and_does_not_retain_live_objects(process_cache):
    import main

    cache, _ = process_cache
    calls = []
    payload = {"value": [1, None, 0]}

    @main.cached("detached-json")
    async def endpoint(large=False):
        calls.append(large)
        return {"body": "界" * 100} if large else payload

    async def exercise():
        first = await endpoint()
        first["value"].append(2)
        warm = await endpoint()
        assert warm == {"value": [1, None, 0]}
        warm["value"].append(3)
        assert await endpoint() == {"value": [1, None, 0]}
        await endpoint(large=True)
        await endpoint(large=True)

    asyncio.run(exercise())
    assert calls == [False, True, True]
    assert len(cache) == 1
    assert cache.payload_bytes == len(json.dumps({"value": [1, None, 0]}).encode())


@pytest.mark.parametrize("result", [object(), JSONResponse({"ok": True}), StreamingResponse(iter([b"data"]))])
def test_noncacheable_response_or_arbitrary_object_is_returned_without_retention(process_cache, result):
    import main

    cache, _ = process_cache
    calls = []

    @main.cached("noncacheable")
    async def endpoint():
        calls.append(1)
        return result

    assert asyncio.run(endpoint()) is result
    assert asyncio.run(endpoint()) is result
    assert calls == [1, 1]
    assert len(cache) == cache.payload_bytes == 0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_json_does_not_enter_process_cache(process_cache, value):
    cache, _ = process_cache
    assert cache.set("nonfinite", {"value": value}, ttl=60) is False
    assert cache.get("nonfinite") is None
    assert len(cache) == 0


def test_ttl_and_transient_failure_recovery_use_monotonic_clock(process_cache):
    import main

    cache, clock = process_cache
    calls = []
    healthy = [False]

    @main.cached("transient-recovery", ttl=3600)
    async def endpoint():
        calls.append(1)
        return {"value": 7} if healthy[0] else {"reason": "source_unavailable"}

    assert asyncio.run(endpoint()) == {"reason": "source_unavailable"}
    healthy[0] = True
    clock[0] += 29
    assert asyncio.run(endpoint()) == {"reason": "source_unavailable"}
    clock[0] += 1
    assert asyncio.run(endpoint()) == {"value": 7}
    clock[0] += 3599
    assert asyncio.run(endpoint()) == {"value": 7}
    clock[0] += 1
    assert asyncio.run(endpoint()) == {"value": 7}
    assert len(calls) == 3
    clock[0] += 3600
    assert cache.get("missing") is None
    assert len(cache) == cache.payload_bytes == 0


def test_shorter_endpoint_ttl_is_not_extended_by_transient_failure(process_cache):
    import main

    _, clock = process_cache
    calls = []

    @main.cached("short-transient", ttl=2)
    async def endpoint():
        calls.append(1)
        return {"status": "unavailable"}

    asyncio.run(endpoint())
    clock[0] += 2
    asyncio.run(endpoint())
    assert calls == [1, 1]


def test_model_cold_and_warm_http_responses_keep_the_same_json_contract(monkeypatch):
    import main

    monkeypatch.setattr(main, "redis_cache", None)

    class Payload(BaseModel):
        at: datetime.datetime
        amount: Decimal
        missing: int | None

    calls = []
    app = FastAPI()

    @app.get("/figure", response_model=Payload)
    @main.cached("model-json-contract")
    async def endpoint():
        calls.append(1)
        return Payload(at=datetime.datetime(2026, 1, 1), amount=Decimal("0.00"), missing=None)

    with TestClient(app) as client:
        first = client.get("/figure")
        warm = client.get("/figure")
    assert first.status_code == warm.status_code == 200
    assert first.content == warm.content
    assert first.json() == {"at": "2026-01-01T00:00:00", "amount": "0.00", "missing": None}
    assert calls == [1]


def test_generation_change_during_load_cannot_publish_stale_warm_response(process_cache, monkeypatch, tmp_path):
    import main
    from cache import invalidation

    monkeypatch.setenv("CACHE_GENERATION_FILE", str(tmp_path / "generation"))
    calls = []

    @main.cached("generation-safety")
    async def endpoint():
        calls.append(1)
        if len(calls) == 1:
            invalidation.bump_generation()
        return {"version": len(calls)}

    assert asyncio.run(endpoint()) == {"version": 1}
    assert asyncio.run(endpoint()) == {"version": 2}
    assert asyncio.run(endpoint()) == {"version": 2}


def test_registered_clear_and_test_clear_empty_shared_store(monkeypatch):
    import main
    from cache import invalidation

    monkeypatch.setattr(main, "redis_cache", None)

    @main.cached("clear-shared")
    async def endpoint():
        return {"value": 1}

    asyncio.run(endpoint())
    assert len(main._endpoint_memory_cache) == 1
    assert invalidation.clear_local_caches()["main.endpoint_memory"] == 1
    assert len(main._endpoint_memory_cache) == 0
    asyncio.run(endpoint())
    main.clear_all_caches()
    assert len(main._endpoint_memory_cache) == main._endpoint_memory_cache.payload_bytes == 0


def test_concurrent_fills_never_exceed_shared_limits(process_cache):
    cache, _ = process_cache

    def fill(i):
        cache.set(str(i), {"body": "x" * 35}, ttl=60)
        cache.get(str(i))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(fill, range(100)))
    assert len(cache) <= 3
    assert cache.payload_bytes <= 180
    assert cache.payload_bytes == sum(len(entry[0]) for entry in cache._entries.values())


def test_entry_count_and_total_bytes_are_independently_enforced():
    from cache.endpoint_memory import BoundedResponseCache

    count_cache = BoundedResponseCache(max_entries=2, max_bytes=1000, max_entry_bytes=1000)
    for i in range(10):
        assert count_cache.set(str(i), {"value": i}, ttl=60)
    assert len(count_cache) == 2
    assert count_cache.get("8") == {"value": 8}
    assert count_cache.get("9") == {"value": 9}
    assert count_cache.get("0") is None

    byte_cache = BoundedResponseCache(max_entries=10, max_bytes=40, max_entry_bytes=40)
    for i in range(10):
        assert byte_cache.set(str(i), "x" * 16, ttl=60)
    assert len(byte_cache) == 2
    assert byte_cache.payload_bytes == 36
    assert byte_cache.get("0") is None
    assert byte_cache.get("9") == "x" * 16


def test_default_limits_cache_county_sized_json_and_reject_larger_entry(monkeypatch):
    import main

    monkeypatch.setattr(main, "redis_cache", None)
    calls = []

    @main.cached("county-sized-hard-failure")
    async def endpoint(oversized=False):
        calls.append(oversized)
        return {"body": "x" * (3 * 1024 * 1024 if oversized else 2_362_271)}

    async def exercise():
        assert await endpoint() == await endpoint()
        await endpoint(oversized=True)
        await endpoint(oversized=True)

    asyncio.run(exercise())
    assert calls == [False, True, True]
    assert len(main._endpoint_memory_cache) == 1
    assert main._endpoint_memory_cache.payload_bytes < 3 * 1024 * 1024


def test_cycles_and_zero_ttl_are_not_retained(process_cache):
    cache, _ = process_cache
    cycle = []
    cycle.append(cycle)
    assert cache.set("cycle", cycle, ttl=60) is False
    assert cache.set("zero", {"value": 1}, ttl=0) is False
    assert cache.set("negative", {"value": 1}, ttl=-1) is False
    assert len(cache) == cache.payload_bytes == 0
