"""Elapsed budgets must survive ASGI receives that do not yield to timer callbacks."""
import asyncio

import pytest
from starlette.responses import JSONResponse

from middleware import request_resources as resources


async def exchange(guard, receive):
    messages = []

    async def send(message):
        messages.append(message)

    await guard({'type': 'http', 'method': 'POST', 'path': '/fixture',
                 'headers': [], 'query_string': b'', 'client': ('192.0.2.1', 1)},
                receive, send)
    return messages


def test_ready_final_body_chunk_cannot_outlive_body_budget(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(resources, 'monotonic', lambda: clock[0])
    calls = []

    async def endpoint(scope, receive, send):
        calls.append(True)
        await JSONResponse({'ok': True})(scope, receive, send)

    async def receive():
        # The await completes immediately, so asyncio's scheduled timeout has
        # no chance to run. Clock advancement models elapsed body processing.
        clock[0] = 6.0
        return {'type': 'http.request', 'body': b'{}', 'more_body': False}

    guard = resources.RequestResourceMiddleware(endpoint, body_timeout=5)
    messages = asyncio.run(exchange(guard, receive))
    assert messages[0]['status'] == 408
    assert b'BODY_READ_TIMEOUT' in messages[1]['body']
    assert calls == []
    assert guard.inflight == guard.body_inflight == guard.buffered == 0


@pytest.mark.parametrize('body', [b'', b'x'], ids=['empty-chunks', 'nonempty-chunks'])
def test_ready_chunk_sequence_stops_at_elapsed_body_budget(monkeypatch, body):
    clock = [0.0]
    monkeypatch.setattr(resources, 'monotonic', lambda: clock[0])
    reads, calls = [], []

    async def endpoint(scope, receive, send):
        calls.append(True)
        await JSONResponse({'ok': True})(scope, receive, send)

    async def receive():
        reads.append(True)
        clock[0] += 1
        return {'type': 'http.request', 'body': body, 'more_body': len(reads) < 10}

    guard = resources.RequestResourceMiddleware(endpoint, body_timeout=3)
    messages = asyncio.run(exchange(guard, receive))
    assert messages[0]['status'] == 408
    assert len(reads) == 3
    assert calls == []
    assert guard.inflight == guard.body_inflight == guard.buffered == 0


def test_request_deadline_can_expire_before_body_deadline(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(resources, 'monotonic', lambda: clock[0])
    calls = []

    async def endpoint(scope, receive, send):
        calls.append(True)
        await JSONResponse({'ok': True})(scope, receive, send)

    async def receive():
        clock[0] = 2
        return {'type': 'http.request', 'body': b'{}', 'more_body': False}

    guard = resources.RequestResourceMiddleware(endpoint, body_timeout=5, request_timeout=1)
    messages = asyncio.run(exchange(guard, receive))
    assert messages[0]['status'] == 504
    assert b'REQUEST_TIME_BUDGET_EXCEEDED' in messages[1]['body']
    assert calls == []
    assert guard.inflight == guard.body_inflight == guard.buffered == 0


def test_elapsed_synchronous_scan_cannot_start_handler(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(resources, 'monotonic', lambda: clock[0])
    calls = []

    async def endpoint(scope, receive, send):
        calls.append(True)
        await JSONResponse({'ok': True})(scope, receive, send)

    async def receive():
        return {'type': 'http.request', 'body': b'{}', 'more_body': False}

    guard = resources.RequestResourceMiddleware(endpoint, request_timeout=1)
    original = guard.check_json_budget

    def scan(raw, scope):
        original(raw, scope)
        clock[0] = 2

    guard.check_json_budget = scan
    messages = asyncio.run(exchange(guard, receive))
    assert messages[0]['status'] == 504
    assert calls == []
    assert guard.inflight == guard.body_inflight == guard.buffered == 0


def test_ready_healthy_chunks_preserve_bytes_and_release_capacity(monkeypatch):
    monkeypatch.setattr(resources, 'monotonic', lambda: 0.0)
    chunks = [b'', b' {"x":', b'"\xc3\xa9"} ']
    seen = []

    async def receive():
        chunk = chunks.pop(0)
        return {'type': 'http.request', 'body': chunk, 'more_body': bool(chunks)}

    async def endpoint(scope, receive, send):
        seen.append((await receive())['body'])
        await JSONResponse({'ok': True})(scope, receive, send)

    guard = resources.RequestResourceMiddleware(endpoint)
    assert asyncio.run(exchange(guard, receive))[0]['status'] == 200
    assert seen == [b' {"x":"\xc3\xa9"} ']
    assert guard.inflight == guard.body_inflight == guard.buffered == 0
