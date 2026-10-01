"""Execute cold health reads, including cancellation and worker ownership."""

import asyncio
import inspect
import threading
from collections import Counter
from types import SimpleNamespace

import httpx
import pytest

import database
import main
from cache import redis_cache


class SessionProbe:
    def __init__(self, *, slow=False, fail=False, empty=False):
        self.slow = slow
        self.fail = fail
        self.empty = empty
        self.started = threading.Event()
        self.finished = threading.Event()
        self.in_query = threading.Event()
        self.resume = threading.Event()
        self.owner = None
        self.threads = []
        self.closes = 0
        self.queries = 0

    def factory(self):
        self.owner = threading.get_ident()
        return self

    def query(self, *args):
        self.threads.append(threading.get_ident())
        self.queries += 1
        if self.queries == 1:
            self.started.set()
            if self.slow:
                self.in_query.set()
                self.resume.wait(0.5)
                self.in_query.clear()
            if self.fail:
                raise RuntimeError("synthetic database failure")
        return self

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def distinct(self):
        return self

    def count(self):
        return 0 if self.empty else 47

    def first(self):
        return (
            None
            if self.empty
            else SimpleNamespace(year=2025, indicator_date=SimpleNamespace(year=2025))
        )

    def close(self):
        self.threads.append(threading.get_ident())
        self.closes += 1
        self.finished.set()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@pytest.fixture
def health_runtime(monkeypatch):
    cache = redis_cache.RedisCache.__new__(redis_cache.RedisCache)
    cache.client = None
    cache.namespace = "pipeline-worker-tests"
    cache._memory_cache = {}
    cache._memory_lock = threading.RLock()
    cache._metrics = Counter()
    monkeypatch.setattr(redis_cache, "cache", cache)
    calls = []
    real_import = main.importlib.import_module

    def import_available(name, *a, **k):
        if name == "etl.kenya_pipeline":
            return SimpleNamespace()
        return real_import(name, *a, **k)

    monkeypatch.setattr(main.importlib, "import_module", import_available)

    class HeadClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def head(self, url):
            calls.append(url)
            await asyncio.sleep(0)
            return SimpleNamespace(status_code=200)

    monkeypatch.setattr(httpx, "AsyncClient", HeadClient)
    return cache, calls


async def call_health(probe):
    # The old route needed a request session; keep the exact same regression
    # runnable on that base as well as on the worker-owned implementation.
    kwargs = (
        {"db": probe}
        if "db" in inspect.signature(main.get_pipeline_health).parameters
        else {}
    )
    return await main.get_pipeline_health(**kwargs)


@pytest.mark.asyncio
async def test_cold_database_work_allows_unrelated_async_progress(
    health_runtime, monkeypatch
):
    probe = SessionProbe(slow=True)
    monkeypatch.setattr(database, "SessionLocal", probe.factory)
    progress_during_query = []

    async def heartbeat():
        while not probe.started.is_set():
            await asyncio.sleep(0.001)
        progress_during_query.append(probe.in_query.is_set())
        probe.resume.set()

    answer, _ = await asyncio.gather(call_health(probe), heartbeat())
    assert progress_during_query == [
        True
    ], "cold database query starved unrelated async work"
    assert answer["database"]["entities"]["total"] == 47
    assert probe.closes == 1
    assert probe.owner != threading.get_ident()
    assert set(probe.threads) == {probe.owner}


async def until(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0.001)


class GatedSession(SessionProbe):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.release = threading.Event()

    def query(self, *args):
        if self.queries == 0:
            self.started.set()
            if not self.release.wait(3):
                raise RuntimeError("test worker gate timed out")
        return super().query(*args)


@pytest.mark.asyncio
async def test_identical_cold_misses_and_warm_hits_do_one_snapshot(
    health_runtime, monkeypatch
):
    probe = GatedSession()
    opened = []

    def factory():
        opened.append(threading.get_ident())
        return probe.factory()

    monkeypatch.setattr(database, "SessionLocal", factory)
    tasks = [asyncio.create_task(call_health(probe)) for _ in range(12)]
    try:
        await until(probe.started.is_set)
        assert len(opened) == 1
        probe.release.set()
        answers = await asyncio.gather(*tasks)
        assert answers == [answers[0]] * 12
        assert await call_health(probe) == answers[0]
        assert answers[0]["status"] == "healthy"
        assert len(opened) == probe.closes == 1
        assert len(health_runtime[1]) == 5
    finally:
        probe.release.set()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_loader_retains_slot_until_session_closed(
    health_runtime, monkeypatch
):
    from fastapi import HTTPException

    probe = GatedSession()
    monkeypatch.setattr(database, "SessionLocal", probe.factory)
    loader = asyncio.create_task(call_health(probe))
    try:
        await until(probe.started.is_set)
        loader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await loader
        with pytest.raises(HTTPException) as error:
            await call_health(probe)
        assert error.value.status_code == 503
        assert error.value.headers == {"Retry-After": "1"}
        assert probe.closes == 0
        assert not health_runtime[0]._memory_cache
        probe.release.set()
        await until(probe.finished.is_set)
        await until(lambda: main._pipeline_health_worker_slot._value == 1)
        recovered = SessionProbe()
        monkeypatch.setattr(database, "SessionLocal", recovered.factory)
        assert (await call_health(recovered))["status"] == "healthy"
        assert probe.closes == recovered.closes == 1
        assert set(probe.threads) == {probe.owner}
    finally:
        probe.release.set()
        await asyncio.gather(loader, return_exceptions=True)
        await until(probe.finished.is_set)


@pytest.mark.asyncio
async def test_new_generation_is_bounded_and_late_fill_is_unreachable(
    health_runtime, monkeypatch, tmp_path
):
    from cache.invalidation import bump_generation
    from fastapi import HTTPException

    monkeypatch.setenv("CACHE_GENERATION_FILE", str(tmp_path / "generation"))
    old = GatedSession()
    monkeypatch.setattr(database, "SessionLocal", old.factory)
    task = asyncio.create_task(call_health(old))
    try:
        await until(old.started.is_set)
        bump_generation()
        with pytest.raises(HTTPException) as error:
            await call_health(old)
        assert error.value.status_code == 503
        old.release.set()
        stale = await task
        fresh = SessionProbe(empty=True)
        monkeypatch.setattr(database, "SessionLocal", fresh.factory)
        current = await call_health(fresh)
        assert stale["database"]["entities"]["total"] == 47
        assert current["database"]["entities"]["total"] == 0
        assert fresh.closes == old.closes == 1
    finally:
        old.release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    ["empty", "query_failure", "creation_failure", "partial_failure", "close_failure"],
)
async def test_database_absence_and_failures_are_truthful(
    health_runtime, monkeypatch, mode
):
    probe = SessionProbe(empty=mode == "empty", fail=mode == "query_failure")

    def factory():
        if mode == "creation_failure":
            raise RuntimeError("synthetic creation failure")
        return probe.factory()

    monkeypatch.setattr(database, "SessionLocal", factory)
    if mode == "partial_failure":
        original_query = probe.query

        def query(*args):
            if probe.queries == 4:
                raise RuntimeError("synthetic partial read failure")
            return original_query(*args)

        monkeypatch.setattr(probe, "query", query)
    if mode == "close_failure":
        original_close = probe.close

        def close():
            original_close()
            raise RuntimeError("synthetic close failure")

        monkeypatch.setattr(probe, "close", close)
    answer = await call_health(probe)
    assert answer["economic_ingestion"]["job_health"] == "not_checked_here"
    if mode == "empty":
        assert answer["status"] == "degraded"
        assert answer["database"]["population"] == {"records": 0, "latest_year": None}
        assert answer["summary"] == {"errors": 0, "warnings": 4, "total_alerts": 4}
    else:
        assert answer["status"] == "unhealthy"
        assert answer["database"] == {}
        assert any(
            a["source"] == "database" and a["level"] == "error"
            for a in answer["alerts"]
        )
    assert probe.closes == (0 if mode == "creation_failure" else 1)


@pytest.mark.asyncio
async def test_positive_ttl_and_failure_ttl_recovery(health_runtime, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(redis_cache.time, "time", lambda: clock[0])
    probes = []

    def factory():
        probe = SessionProbe(fail=len(probes) == 1)
        probes.append(probe)
        return probe.factory()

    monkeypatch.setattr(database, "SessionLocal", factory)
    healthy = await call_health(None)
    clock[0] += 29
    assert await call_health(None) == healthy
    assert len(probes) == 1
    clock[0] += 2
    failed = await call_health(None)
    assert failed["status"] == "unhealthy"
    clock[0] += redis_cache.TRANSIENT_FAILURE_TTL - 1
    assert await call_health(None) == failed
    clock[0] += 2
    assert (await call_health(None))["status"] == "healthy"
    assert len(probes) == 3
    assert all(p.closes == 1 for p in probes)


@pytest.mark.asyncio
async def test_executor_refusal_releases_slot_without_session(
    health_runtime, monkeypatch
):
    def refuse(*a, **k):
        raise RuntimeError("synthetic executor refusal")

    with monkeypatch.context() as patch:
        patch.setattr(main._pipeline_health_executor, "submit", refuse)
        with pytest.raises(RuntimeError, match="synthetic executor refusal"):
            await call_health(None)
    probe = SessionProbe()
    monkeypatch.setattr(database, "SessionLocal", probe.factory)
    assert (await call_health(probe))["status"] == "healthy"
    assert probe.closes == 1


@pytest.mark.asyncio
async def test_real_sql_session_closes_before_async_heads(
    health_runtime, monkeypatch, pipeline_health_database
):
    from datetime import datetime
    from sqlalchemy import event
    from models import EconomicIndicator, PopulationData

    with database.SessionLocal() as seed:
        seed.add_all(
            [
                PopulationData(year=2025, total_population=123),
                EconomicIndicator(
                    indicator_type="synthetic",
                    indicator_date=datetime(2025, 1, 1),
                    value=0,
                ),
            ]
        )
        seed.commit()
    threads = []
    returned = threading.Event()

    @event.listens_for(pipeline_health_database, "before_cursor_execute")
    def on_sql(*args):
        threads.append(threading.get_ident())

    @event.listens_for(pipeline_health_database, "checkin")
    def on_checkin(*args):
        returned.set()

    async def head(self, url):
        assert returned.is_set(), "database connection held across async source HEAD"
        assert threading.get_ident() not in threads
        health_runtime[1].append(url)
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(httpx.AsyncClient, "head", head)
    answer = await call_health(None)
    assert answer["database"]["population"] == {"records": 1, "latest_year": 2025}
    assert answer["database"]["economic_indicators"] == {
        "records": 1,
        "latest_year": 2025,
    }
    assert len(threads) == 10
    assert len(set(threads)) == 1
    assert len(health_runtime[1]) == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [404, 500, None])
async def test_source_checks_remain_async_and_report_failures(
    health_runtime, monkeypatch, code
):
    probe = SessionProbe()
    monkeypatch.setattr(database, "SessionLocal", probe.factory)
    in_flight = 0
    max_in_flight = 0

    async def head(self, url):
        nonlocal in_flight, max_in_flight
        assert probe.finished.is_set()
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.005)
        in_flight -= 1
        if code is None:
            raise httpx.ConnectError("synthetic unreachable source")
        return SimpleNamespace(status_code=code)

    monkeypatch.setattr(httpx.AsyncClient, "head", head)
    answer = await call_health(probe)
    assert max_in_flight == 5
    assert len(answer["sources"]) == 5
    assert all(
        source["reachable"] == (code == 404) for source in answer["sources"].values()
    )
    assert answer["status"] == ("healthy" if code == 404 else "degraded")
    assert answer["summary"]["warnings"] == (0 if code == 404 else 5)


@pytest.mark.asyncio
async def test_cancelled_request_observes_eventual_worker_exception(
    health_runtime, monkeypatch, caplog
):
    import gc

    started = threading.Event()
    release = threading.Event()

    def fail_worker():
        started.set()
        if not release.wait(3):
            raise RuntimeError("test release timed out")
        raise RuntimeError("synthetic unexpected worker exception")

    monkeypatch.setattr(main, "_pipeline_health_snapshot", fail_worker)
    loop = asyncio.get_running_loop()
    events = []
    original_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _, event: events.append(event))
    task = asyncio.create_task(call_health(None))
    try:
        await until(started.is_set)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        await until(lambda: main._pipeline_health_worker_slot._value == 1)
        await asyncio.sleep(0.01)
        gc.collect()
        await asyncio.sleep(0.01)
        assert not events
        assert "Pipeline health snapshot failed" in caplog.text
        assert not health_runtime[0]._memory_cache
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        loop.set_exception_handler(original_handler)
