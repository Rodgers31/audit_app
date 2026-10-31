"""The admin snapshot must not wait for government-host probes."""
import asyncio
import ssl
from types import SimpleNamespace

import httpx
import pytest
import database
import main
from .test_pipeline_health_worker import SessionProbe, health_runtime
from services import source_reachability as sr

REAL_CLIENT = httpx.AsyncClient


@pytest.mark.asyncio
async def test_status_returns_while_source_probe_is_still_pending(health_runtime, monkeypatch):
    probe = SessionProbe()
    monkeypatch.setattr(database, "SessionLocal", probe.factory)
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked_head(self, url):
        entered.set()
        await release.wait()
        return type("Reply", (), {"status_code": 200})()

    monkeypatch.setattr(main.httpx.AsyncClient, "head", blocked_head)
    target = getattr(main, "get_pipeline_health_v2", main.get_pipeline_health)
    task = asyncio.create_task(target())
    try:
        await asyncio.wait_for(entered.wait(), .8)
        await asyncio.sleep(.02)
        assert task.done(), "database status still waits for a government HEAD"
        result = task.result()
        assert result["database"]["entities"]["counties"] == 47
        assert result["status"] == "unknown"
        assert all(s["reachable"] is None for s in result["sources"].values())
        assert probe.closes == 1
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(.02)


class Client:
    calls = []
    closes = 0
    gate = None
    errors = {}

    def __init__(self, **kwargs):
        assert kwargs["max_redirects"] == 2
        assert kwargs["timeout"] == 2
        assert kwargs["limits"].max_connections == 5
        assert kwargs.get("verify", True) is True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        type(self).closes += 1

    async def head(self, url):
        type(self).calls.append(url)
        if self.gate is not None:
            await self.gate.wait()
        if url in self.errors:
            raise self.errors[url]
        return SimpleNamespace(status_code=200)


@pytest.fixture
def monitor(monkeypatch):
    Client.calls, Client.closes, Client.gate, Client.errors = [], 0, None, {}
    monkeypatch.setattr(sr.httpx, "AsyncClient", Client)
    return sr.SourceReachability()


@pytest.mark.asyncio
async def test_cold_unknown_coalesces_and_warm_reads_do_not_probe(monitor):
    Client.gate = asyncio.Event()
    for _ in range(20):
        sources, running = monitor.observe()
        assert running and all(s["reachable"] is None for s in sources.values())
    await asyncio.sleep(.01)
    assert len(Client.calls) == 5
    Client.gate.set()
    await monitor._task
    for _ in range(20):
        sources, running = monitor.observe()
        assert not running and all(s["freshness"] == "fresh" for s in sources.values())
    assert len(Client.calls) == 5 and Client.closes == 1


@pytest.mark.asyncio
async def test_stale_success_and_clock_reversal_are_not_fresh(monitor, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(monitor, "_clock", lambda: clock[0])
    monitor.observe()
    await monitor._task
    clock[0] += sr.REFRESH_SECONDS
    Client.gate = asyncio.Event()
    sources, running = monitor.observe()
    assert running and all(s["freshness"] == "stale" and s["reachable"] is True for s in sources.values())
    clock[0] = 0
    sources, _ = monitor.observe()
    assert all(s["freshness"] == "unknown" and s["reachable"] is None for s in sources.values())
    Client.gate.set()
    await monitor._task


@pytest.mark.asyncio
async def test_deadline_closes_batch_and_retains_timeout_as_an_observation(monitor, monkeypatch):
    monkeypatch.setattr(sr, "BATCH_SECONDS", .02)
    Client.gate = asyncio.Event()
    monitor.observe()
    await asyncio.wait_for(monitor._task, .5)
    sources, running = monitor.observe()
    assert not running and Client.closes == 1
    assert len(Client.calls) == 5
    assert all(s["outcome"] == "timeout" and s["reachable"] is False for s in sources.values())
    assert all(s["observed_at"] and s["freshness"] == "fresh" for s in sources.values())


@pytest.mark.parametrize("exc,outcome", [
    (httpx.ReadTimeout("private detail"), "timeout"),
    (ssl.SSLCertVerificationError("private detail"), "certificate_error"),
    (httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] private path"), "certificate_error"),
    (httpx.ConnectError("private detail"), "request_error"),
    (httpx.TooManyRedirects("private detail"), "request_error"),
])
def test_error_classification_without_exception_text(exc, outcome):
    assert sr.exception_outcome(exc) == outcome


@pytest.mark.asyncio
async def test_legacy_waits_for_a_real_boolean_then_reuses_same_batch(monitor):
    Client.gate = asyncio.Event()
    task = asyncio.create_task(monitor.legacy())
    await asyncio.sleep(.01)
    assert not task.done()
    sources, _ = monitor.observe()
    assert all(s["reachable"] is None for s in sources.values())
    Client.gate.set()
    legacy = await task
    assert all(type(s["reachable"]) is bool and s["status_code"] == 200 for s in legacy.values())
    assert await monitor.legacy() == legacy
    assert len(Client.calls) == 5


@pytest.mark.asyncio
async def test_cancelled_legacy_waiter_does_not_cancel_shared_probe(monitor):
    Client.gate = asyncio.Event()
    task = asyncio.create_task(monitor.legacy())
    await asyncio.sleep(.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert monitor._running and not monitor._task.done()
    for _ in range(10):
        monitor.observe()
    assert len(Client.calls) == 5
    Client.gate.set()
    await monitor._task
    assert Client.closes == 1


def test_no_observations_or_database_cannot_be_healthy():
    snapshot = dict(alerts=[], database={}, auto_seeder={}, checked_at="2026-10-24T00:00:00Z")
    assert sr.assemble_health(snapshot, {}, False)["status"] == "unknown"


@pytest.mark.asyncio
async def test_v2_is_admin_gated_before_database_or_source_work(monkeypatch):
    def refuse(*a, **k):
        pytest.fail("unauthenticated request performed health work")
    monkeypatch.setattr(main, "_local_health_v2", refuse)
    monkeypatch.setattr(main._source_reachability, "observe", refuse)
    async with REAL_CLIENT(transport=httpx.ASGITransport(app=main.app), base_url="http://owned.test") as client:
        response = await client.get("/api/v1/system/pipeline-health/v2")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_v2_does_not_inspect_retired_web_module(health_runtime, monkeypatch):
    probe = SessionProbe()
    monkeypatch.setattr(database, "SessionLocal", probe.factory)
    real = main.importlib.import_module

    def import_without_legacy(name, *a, **k):
        assert name != "etl.kenya_pipeline"
        return real(name, *a, **k)

    monkeypatch.setattr(main.importlib, "import_module", import_without_legacy)
    answer = await main.get_pipeline_health_v2()
    assert answer["execution"]["status"] == "not_observed"
    assert not any(a["source"] == "etl.kenya_pipeline" for a in answer["alerts"])
    await main._source_reachability._task


@pytest.mark.asyncio
async def test_authenticated_wire_shape_and_private_headers(health_runtime, monkeypatch):
    probe = SessionProbe()
    monkeypatch.setattr(database, "SessionLocal", probe.factory)
    previous = dict(main.app.dependency_overrides)
    main.app.dependency_overrides[main._status_require_admin] = lambda: object()
    try:
        async with REAL_CLIENT(transport=httpx.ASGITransport(app=main.app), base_url="http://owned.test") as client:
            response = await client.get("/api/v1/system/pipeline-health/v2")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-store"
        assert response.json()["schema_version"] == 2
        assert response.json()["execution"]["status"] == "not_observed"
        assert "modules" not in response.json() and "etl_jobs" not in response.json()
        assert all(s["reachable"] is None for s in response.json()["sources"].values())
        await main._source_reachability._task
    finally:
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(previous)
