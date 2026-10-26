"""The installed coarse budgets must bind before the ordinary worker recycle."""
import asyncio
import sys

import httpx

from fastapi import FastAPI
from gunicorn.app.wsgiapp import WSGIApplication


def test_installed_peer_and_process_budgets_are_distinct_and_reachable(monkeypatch):
    from middleware.security import install_security
    from social_worker_supervisor import web_command
    monkeypatch.setenv('WEB_CONCURRENCY', '1')
    monkeypatch.setattr(sys, 'argv', web_command({'PORT':'8000'}))
    configured_server = WSGIApplication().cfg
    app = FastAPI()
    install_security(app)
    app.build_middleware_stack()
    limits = app.state.security_limits
    assert limits['aggregate_calls'] < configured_server.max_requests
    assert 1 <= limits['calls'] < limits['aggregate_calls']
    assert limits['identity_scope'] == 'coarse_socket_peer'
    assert limits['process_scope'] == 'one_worker'


def test_refused_peer_cannot_debit_another_peers_process_share(monkeypatch):
    from middleware.security import RateLimitMiddleware
    monkeypatch.setattr(RateLimitMiddleware, 'dispatch', getattr(
        RateLimitMiddleware, '_original_dispatch', RateLimitMiddleware.dispatch))
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, calls=2, aggregate_calls=3, period=60)
    @app.get('/owned')
    def endpoint():
        return {'ok': True}
    async def exercise():
        async with httpx.AsyncClient(base_url='http://fixture.invalid',
                transport=httpx.ASGITransport(app,client=('198.51.100.1',1))) as first:
            assert [(await first.get('/owned')).status_code for _ in range(3)] == [200,200,429]
            assert [(await first.get('/owned')).status_code for _ in range(10)] == [429]*10
        async with httpx.AsyncClient(base_url='http://fixture.invalid',
                transport=httpx.ASGITransport(app,client=('198.51.100.2',1))) as second:
            assert (await second.get('/owned')).status_code == 200
            assert (await second.get('/owned')).status_code == 429
        async with httpx.AsyncClient(base_url='http://fixture.invalid',
                transport=httpx.ASGITransport(app,client=('198.51.100.3',1))) as third:
            assert (await third.get('/owned')).status_code == 429
        wrapped = app.middleware_stack
        while not isinstance(wrapped, RateLimitMiddleware):
            wrapped = wrapped.app
        assert set(wrapped.clients) == {'198.51.100.1','198.51.100.2'}
    asyncio.run(exercise())
