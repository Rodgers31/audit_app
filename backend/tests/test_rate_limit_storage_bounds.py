"""Small deterministic client sets exercise the production storage boundary."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware import security


@pytest.mark.parametrize('cls', [security.RateLimitMiddleware, security.RedisRateLimitMiddleware])
def test_live_client_cardinality_is_bounded_and_recovers(cls, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(security.time, 'monotonic', lambda: clock[0])
    limiter = cls(FastAPI(), calls=2, period=60)
    # A tiny cap demonstrates the boundary without a stress test.
    monkeypatch.setattr(limiter, '_MAX_MEMORY_CLIENTS', 3, raising=False)
    if cls is security.RedisRateLimitMiddleware:
        check = limiter._check_memory_rate_limit
        entries = limiter.memory_fallback
    else:
        async def check(ip):
            request = security.Request({'type': 'http', 'method': 'GET',
                'path': '/x', 'headers': [], 'client': (ip, 1234)})
            async def accepted(request):
                return security.JSONResponse({'ok': True})
            dispatch = getattr(cls, '_original_dispatch', cls.dispatch)
            return (await dispatch(limiter, request, accepted)).status_code == 200
        entries = limiter.clients

    async def run():
        for n in range(3):
            assert await check(f'192.0.2.{n}')
        assert not await check('198.51.100.1'), 'new identities bypassed storage capacity'
        assert len(entries) == 3
        assert await check('192.0.2.0'), 'capacity must not evict a live budget'
        assert not await check('192.0.2.0')
        clock[0] += 61
        assert await check('198.51.100.1'), 'expired entries must release capacity'
        assert len(entries) <= 3
    import asyncio
    asyncio.run(run())


@pytest.mark.parametrize('cls', [security.RateLimitMiddleware, security.RedisRateLimitMiddleware])
def test_forwarded_headers_do_not_choose_rate_limit_identity(cls, monkeypatch):
    monkeypatch.setenv('REDIS_URL', '')
    monkeypatch.setattr(cls, 'dispatch', getattr(cls, '_original_dispatch', cls.dispatch))
    app = FastAPI()
    app.add_middleware(cls, calls=2, period=60)
    @app.get('/x')
    def endpoint():
        return {'ok': True}
    with TestClient(app, client=('192.0.2.1', 1234)) as client:
        responses = [client.get('/x', headers={'x-forwarded-for': f'198.51.100.{n}'})
                     for n in range(3)]
    assert [r.status_code for r in responses] == [200, 200, 429]
    assert responses[-1].headers['retry-after'] == '60'
