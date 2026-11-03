"""Inert ASGI body streams; callback effects use a recording double."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI

from social.connections import direct_api
from social.connections.api import service
from social.http_policy import SocialNoStoreMiddleware
from middleware.security import install_security
from middleware.request_resources import RequestResourceMiddleware

API = 'https://api.example.test'
ORIGIN = 'https://admin.example.test'
PATH = '/api/v1/social/oauth/meta/launch'
CALLBACK = API + '/api/v1/social/oauth/meta/callback'


def application(monkeypatch, *, held=False, guarded=True):
    calls = []

    class Config:
        def require_direct(self):
            if held:
                raise direct_api.refused('CALLBACK_INGRESS_UNVERIFIED', 503)
            return CALLBACK

    class Transport:
        def __init__(self, svc):
            pass

        def launch(self, flow_id, token, origin):
            calls.append((flow_id, token, origin))
            return 'https://www.facebook.com/inert-authorize', '__Host-inert', 'inert-browser'

    monkeypatch.setattr(direct_api, 'DirectCallback', Transport)
    app = FastAPI()
    app.include_router(direct_api.router)
    app.dependency_overrides[service] = lambda: SimpleNamespace(config=Config())
    if guarded:
        # Use the actual serving installer/order. Only shorten time in this
        # fixture; byte/admission limits and route behavior stay unchanged.
        install_security(app)
        for middleware in app.user_middleware:
            if middleware.cls is RequestResourceMiddleware:
                middleware.kwargs['body_timeout'] = 0.03
    app.add_middleware(SocialNoStoreMiddleware)
    return app, calls


def resource_guard(app):
    layer = app.middleware_stack
    while not isinstance(layer, RequestResourceMiddleware):
        layer = layer.app
    return layer


async def invoke(app, receive, *, watchdog=2.0):
    messages = []
    scope = {
        'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
        'method': 'POST', 'scheme': 'https', 'path': PATH,
        'raw_path': PATH.encode(), 'query_string': b'',
        'root_path': '', 'server': ('api.example.test', 443),
        'client': ('127.0.0.1', 12345),
        'headers': [(b'host', b'api.example.test'), (b'origin', ORIGIN.encode()),
                    (b'content-type', b'application/x-www-form-urlencoded')],
    }

    async def send(message):
        messages.append(message)

    await asyncio.wait_for(app(scope, receive, send), timeout=watchdog)
    start = next(m for m in messages if m['type'] == 'http.response.start')
    body = b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body')
    return start['status'], dict(start['headers']), body


@pytest.mark.parametrize('held', [False, True], ids=['qualified-fixture', 'held'])
@pytest.mark.parametrize('kind', ['before_first_chunk', 'after_partial_chunk', 'slow_drip', 'empty_chunks'])
def test_installed_guard_bounds_stalled_launch_before_flow_mutation(monkeypatch, kind, held):
    app, calls = application(monkeypatch, held=held)

    async def scenario():
        count = 0
        cancelled = False

        async def receive():
            nonlocal count, cancelled
            count += 1
            try:
                if kind == 'after_partial_chunk' and count == 1:
                    return {'type': 'http.request', 'body': b'launch_token=INERT-body-marker', 'more_body': True}
                if kind in {'slow_drip', 'empty_chunks'}:
                    await asyncio.sleep(0.01)
                    return {'type': 'http.request', 'body': b'x' if kind == 'slow_drip' else b'', 'more_body': True}
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled = True
                raise

        status, headers, body = await invoke(app, receive)
        assert status == 408
        assert headers[b'cache-control'] == b'private, no-store'
        assert headers[b'referrer-policy'] == b'no-referrer'
        assert b'location' not in headers and b'set-cookie' not in headers
        assert b'INERT-body-marker' not in body
        assert b'BODY_READ_TIMEOUT' in body
        assert cancelled  # The pending reader is cancelled, not orphaned.
        assert calls == []
        guard = resource_guard(app)
        assert (guard.inflight, guard.body_inflight, guard.buffered) == (0, 0, 0)

    asyncio.run(scenario())


def test_complete_bounded_body_preserves_launch_response(monkeypatch):
    app, calls = application(monkeypatch)
    flow_id = uuid4()
    raw = urlencode({'flow_id': str(flow_id), 'launch_token': 'a' * 43}).encode()
    chunks = [raw[:20], raw[20:]]

    async def receive():
        if not chunks:
            await asyncio.Event().wait()
        body = chunks.pop(0)
        return {'type': 'http.request', 'body': body, 'more_body': bool(chunks)}

    status, headers, body = asyncio.run(invoke(app, receive))
    assert status == 303
    assert calls == [(flow_id, 'a' * 43, ORIGIN)]
    assert headers[b'location'] == b'https://www.facebook.com/inert-authorize'
    assert b'Secure' in headers[b'set-cookie'] and b'HttpOnly' in headers[b'set-cookie']
    assert headers[b'cache-control'] == b'private, no-store'


def test_body_overflow_refuses_before_flow_mutation(monkeypatch):
    app, calls = application(monkeypatch)

    # Valid form structure ensures parsing cannot mask a relaxed byte cap.
    raw = urlencode({'flow_id': str(uuid4()), 'launch_token': 'a' * 1000}).encode()
    assert 1024 < len(raw) < 2048

    async def receive():
        return {'type': 'http.request', 'body': raw, 'more_body': False}

    status, headers, body = asyncio.run(invoke(app, receive))
    assert status == 409 and calls == []
    assert b'location' not in headers and b'set-cookie' not in headers


def test_callback_hold_refuses_complete_body_before_flow_mutation(monkeypatch):
    app, calls = application(monkeypatch, held=True)

    async def receive():
        return {'type': 'http.request', 'body': b'flow_id=INERT-held', 'more_body': False}

    status, headers, body = asyncio.run(invoke(app, receive))
    assert status == 503 and calls == []
    assert b'CALLBACK_INGRESS_UNVERIFIED' in body


def test_router_without_required_guard_is_only_a_negative_composition_control(monkeypatch):
    app, calls = application(monkeypatch, guarded=False)

    async def receive():
        await asyncio.Event().wait()

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(invoke(app, receive, watchdog=0.15))
    assert calls == []


def test_caller_cancellation_releases_body_admission(monkeypatch):
    app, calls = application(monkeypatch)

    async def scenario():
        reading = asyncio.Event()

        async def receive():
            reading.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(invoke(app, receive))
        await asyncio.wait_for(reading.wait(), 2.0)
        guard = resource_guard(app)
        assert (guard.inflight, guard.body_inflight, guard.buffered) == (1, 1, 0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        guard = resource_guard(app)
        assert (guard.inflight, guard.body_inflight, guard.buffered) == (0, 0, 0)
        assert calls == []

    asyncio.run(scenario())
