"""Bounded dummy contract checks; run ONLY in the documented OS sandbox.

Exercises real middleware and Uvicorn, without importing main, databases,
provider adapters, or production data. This is not a deployment qualifier.
"""
import asyncio
import json
from pathlib import Path
import socket
import sys
import unittest

# Resolve this checkout rather than depending on the caller's cwd/PYTHONPATH.
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'backend'))

import httpx
import uvicorn
from fastapi import FastAPI, Request
from middleware.security import RateLimitMiddleware
from middleware.request_resources import cheap_health


def app_for_contract():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, calls=2, aggregate_calls=3, period=60)

    @app.api_route('/{path:path}', methods=['GET', 'HEAD', 'POST', 'OPTIONS'])
    async def endpoint(request: Request):
        return {'peer': request.client.host if request.client else 'unknown',
                'scheme': request.url.scheme}

    return app


class OriginContract(unittest.IsolatedAsyncioTestCase):
    async def test_log_proposal_excludes_sensitive_recovery_path(self):
        proposal = json.loads((REPO / 'docs/security/b95-edge-origin-settings.json').read_text())
        rule = proposal['optional_vercel_rule']
        if rule['initial_action'] == 'log':
            self.assertNotIn('/api/auth/reset-password', rule['paths_exact'])
        self.assertFalse(proposal['apply'])
        self.assertFalse(rule['enabled'])

    async def test_forwarding_and_origin_headers_do_not_select_identity(self):
        app = app_for_contract()
        async with httpx.AsyncClient(base_url='http://fixture.invalid', trust_env=False,
                transport=httpx.ASGITransport(app, client=('192.0.2.8', 1))) as client:
            results = []
            for n in range(3):
                results.append(await client.get('/api/v1/owned', headers={
                    'X-Forwarded-For': f'198.51.100.{n}', 'X-Real-IP': '127.0.0.1',
                    'CF-Connecting-IP': '::1', 'Forwarded': 'for=127.0.0.1;proto=https',
                    'Origin': 'https://www.auditgava.com', 'X-Forwarded-Proto': 'https',
                    'X-Forwarded-Host': 'trusted.invalid', 'User-Agent': 'provider-health'}))
        self.assertEqual([r.status_code for r in results], [200, 200, 429])
        self.assertEqual(results[0].json(), {'peer': '192.0.2.8', 'scheme': 'http'})
        self.assertEqual(results[-1].headers['cache-control'], 'no-store')

    async def test_loopback_is_not_exempt(self):
        app = app_for_contract()
        async with httpx.AsyncClient(base_url='http://fixture.invalid', trust_env=False,
                transport=httpx.ASGITransport(app, client=('127.0.0.1', 1))) as client:
            self.assertEqual([(await client.get('/owned')).status_code for _ in range(3)],
                             [200, 200, 429])

    async def test_missing_peer_shares_unknown_budget(self):
        app = app_for_contract()
        async with httpx.AsyncClient(base_url='http://fixture.invalid', trust_env=False,
                transport=httpx.ASGITransport(app, client=None)) as client:
            self.assertEqual([(await client.get('/owned')).status_code for _ in range(3)],
                             [200, 200, 429])

    async def test_distinct_peers_share_process_budget(self):
        app = app_for_contract()
        statuses = []
        for n in range(4):
            async with httpx.AsyncClient(base_url='http://fixture.invalid', trust_env=False,
                    transport=httpx.ASGITransport(app, client=(f'192.0.2.{n}', 1))) as client:
                statuses.append((await client.get('/owned')).status_code)
        self.assertEqual(statuses, [200, 200, 200, 429])

    async def test_provider_paths_have_no_rate_bypass(self):
        for path in ['/api/v1/social/oauth/meta/callback',
                     '/api/v1/social/privacy/meta/data-deletion',
                     '/api/v1/social/platform-events/owned', '/health/detailed']:
            with self.subTest(path=path):
                app = app_for_contract()
                async with httpx.AsyncClient(base_url='http://fixture.invalid', trust_env=False,
                        transport=httpx.ASGITransport(app, client=('192.0.2.1', 1))) as client:
                    self.assertEqual([(await client.get(path)).status_code for _ in range(3)],
                                     [200, 200, 429])

    async def test_health_exception_is_exact_path_and_method(self):
        for path in ['/health', '/health/live', '/health/ready']:
            for method in ['GET', 'HEAD']:
                self.assertTrue(cheap_health({'path': path, 'method': method}))
        for path in ['/health/', '/health/live/extra', '/health/detailed', '/api/v1/health']:
            self.assertFalse(cheap_health({'path': path, 'method': 'GET'}))
        for method in ['POST', 'OPTIONS', '', None]:
            self.assertFalse(cheap_health({'path': '/health/live', 'method': method}))
        app = app_for_contract()
        async with httpx.AsyncClient(base_url='http://fixture.invalid', trust_env=False,
                transport=httpx.ASGITransport(app)) as client:
            self.assertEqual([(await client.get('/owned')).status_code for _ in range(3)],
                             [200, 200, 429])
            self.assertEqual([(await client.get('/health/live')).status_code for _ in range(3)],
                             [200, 200, 200])
            self.assertEqual((await client.post('/health/live')).status_code, 429)

    async def test_fresh_middleware_instance_has_fresh_budget(self):
        for _ in range(2):
            async with httpx.AsyncClient(base_url='http://fixture.invalid', trust_env=False,
                    transport=httpx.ASGITransport(app_for_contract())) as client:
                self.assertEqual([(await client.get('/owned')).status_code for _ in range(3)],
                                 [200, 200, 429])

    async def test_real_tcp_chain_and_unsafe_trust_negative_control(self):
        for trusted, expected, peer in [('', [200, 200, 429], '127.0.0.1'),
                                        ('*', [200, 200, 200], '198.51.100.1')]:
            with self.subTest(trusted=trusted):
                sock = socket.socket()
                sock.bind(('127.0.0.1', 0))
                sock.listen(4)
                port = sock.getsockname()[1]
                server = uvicorn.Server(uvicorn.Config(app_for_contract(), lifespan='off',
                    log_level='error', proxy_headers=True, forwarded_allow_ips=trusted))
                task = asyncio.create_task(server.serve(sockets=[sock]))
                try:
                    async with asyncio.timeout(3):
                        while not server.started:
                            await asyncio.sleep(.01)
                    async with httpx.AsyncClient(trust_env=False, timeout=1) as client:
                        replies = [await client.get(f'http://127.0.0.1:{port}/owned',
                            headers={'X-Forwarded-For': f'198.51.100.{n}',
                                     'X-Forwarded-Proto': 'https'}) for n in range(1, 4)]
                    self.assertEqual([r.status_code for r in replies], expected)
                    self.assertEqual(replies[0].json()['peer'], peer)
                    self.assertEqual(replies[0].json()['scheme'], 'https' if trusted else 'http')
                finally:
                    server.should_exit = True
                    await asyncio.wait_for(task, 3)
                    sock.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
