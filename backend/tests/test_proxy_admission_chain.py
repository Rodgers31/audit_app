"""Actual Gunicorn settings and a tiny Uvicorn loopback TCP request chain."""
import asyncio
import socket
import sys

import httpx
from fastapi import FastAPI, Request
from gunicorn.app.wsgiapp import WSGIApplication
import uvicorn

import social_worker_supervisor
from middleware.security import RateLimitMiddleware


def configuration(monkeypatch):
    monkeypatch.setenv('WEB_CONCURRENCY','1')
    monkeypatch.setattr(sys,'argv',social_worker_supervisor.web_command({'PORT':'8000'}))
    return WSGIApplication().cfg


def test_web_command_pins_one_worker_and_no_forwarded_identity(monkeypatch):
    # Command flags must win over ambient server-setting overrides.
    monkeypatch.setenv('GUNICORN_CMD_ARGS','--workers 4 --forwarded-allow-ips=*')
    cfg = configuration(monkeypatch)
    assert cfg.workers == 1
    assert cfg.forwarded_allow_ips == []


def test_forged_forwarding_headers_cannot_rotate_socket_peer_budget(monkeypatch):
    monkeypatch.delenv('GUNICORN_CMD_ARGS',raising=False)
    cfg = configuration(monkeypatch)
    monkeypatch.setattr(RateLimitMiddleware,'dispatch',getattr(RateLimitMiddleware,'_original_dispatch',RateLimitMiddleware.dispatch))
    async def exercise():
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware,calls=2,period=60)
        @app.get('/x')
        def endpoint(request: Request):
            return {'peer':request.client.host,'scheme':request.url.scheme}
        sock = socket.socket()
        sock.bind(('127.0.0.1',0))
        sock.listen(8)
        port = sock.getsockname()[1]
        config = uvicorn.Config(app,log_level='error',lifespan='off',proxy_headers=True,
            forwarded_allow_ips=','.join(cfg.forwarded_allow_ips))
        server = uvicorn.Server(config)
        task = asyncio.create_task(server.serve(sockets=[sock]))
        try:
            async with asyncio.timeout(2):
                while not server.started:
                    await asyncio.sleep(.01)
            async with httpx.AsyncClient(trust_env=False,timeout=1) as client:
                responses = [await client.get(f'http://127.0.0.1:{port}/x',headers={
                    'X-Forwarded-For':f'198.51.100.{n}', 'X-Forwarded-Proto':'https'}) for n in range(3)]
            assert responses[0].json() == {'peer':'127.0.0.1','scheme':'http'}
            assert [r.status_code for r in responses] == [200,200,429]
        finally:
            server.should_exit = True
            await asyncio.wait_for(task,2)
            sock.close()
    asyncio.run(exercise())
