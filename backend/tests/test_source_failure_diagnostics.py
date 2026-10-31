"""Unsafe or unavailable publisher HTTPS stays unavailable with useful reasons."""
import json
import ssl
import asyncio
from types import SimpleNamespace

import httpx
import pytest

from services import source_reachability as sr


def certificate_error(code):
    error = ssl.SSLCertVerificationError(1, "INERT_PRIVATE certificate diagnostic")
    error.verify_code = code
    wrapped = httpx.ConnectError("INERT_PRIVATE transport detail")
    wrapped.__cause__ = error
    return wrapped


def test_wrapped_certificate_failure_retains_its_classification():
    error = httpx.ConnectError('outer inert transport failure')
    error.__cause__ = ValueError('CERTIFICATE_VERIFY_FAILED INERT_PRIVATE')
    assert sr.failure_detail(error) == ('certificate_error', 'certificate_untrusted')


@pytest.mark.asyncio
@pytest.mark.parametrize('error,reason,word', [
    (certificate_error(10), 'certificate_expired', 'expired'),
    (certificate_error(20), 'certificate_chain_unverified', 'chain'),
    (certificate_error(21), 'certificate_chain_unverified', 'chain'),
    (certificate_error(62), 'certificate_hostname_mismatch', 'hostname'),
    (certificate_error(999), 'certificate_untrusted', 'certificate'),
    (httpx.ConnectTimeout('INERT_PRIVATE'), 'connect_timeout', 'connection'),
    (httpx.ReadTimeout('INERT_PRIVATE'), 'response_timeout', 'response'),
])
async def test_unavailable_source_reason_survives_without_exposing_library_text(monkeypatch, error, reason, word):
    closes, calls = [], []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs.get('verify', True) is True
            assert kwargs['timeout'] == 2.0
            assert kwargs['max_redirects'] == 2
            assert kwargs['limits'].max_connections == 5

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            closes.append(True)

        async def head(self, url):
            calls.append(url)
            raise error

    monkeypatch.setattr(sr.httpx, 'AsyncClient', Client)
    monitor = sr.SourceReachability()
    monitor.observe()
    await monitor._task
    sources, running = monitor.observe()
    assert not running and len(calls) == 5 and len(closes) == 1
    assert all(s['reachable'] is False and s['failure_reason'] == reason for s in sources.values())
    snapshot = dict(alerts=[], database={'entities': {'counties': 47}}, auto_seeder={}, checked_at='2026-10-31T00:00:00Z')
    result = sr.assemble_health(snapshot, sources, running)
    assert result['status'] == 'degraded'
    assert result['summary']['warnings'] == 5
    assert all(word in a['message'].lower() for a in result['alerts'])
    assert 'INERT_PRIVATE' not in json.dumps(result)
    legacy = await monitor.legacy()
    assert all(word in row['error'].lower() for row in legacy.values())
    assert len(calls) == 5, 'Legacy consumed the retained observation instead of starting another batch'


@pytest.mark.asyncio
async def test_cob_uses_verified_direct_homepage_within_existing_batch_budget(monkeypatch):
    calls = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs['timeout'] == 2.0
            assert kwargs.get('verify', True) is True

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def head(self, url):
            calls.append(url)
            # Scaled deterministic control of the observed extra redirect hop.
            if url == 'https://www.cob.go.ke':
                await asyncio.sleep(.04)
            else:
                await asyncio.sleep(.001)
            return SimpleNamespace(status_code=200)

    monkeypatch.setattr(sr.httpx, 'AsyncClient', Client)
    monkeypatch.setattr(sr, 'BATCH_SECONDS', .02)
    monitor = sr.SourceReachability()
    monitor.observe()
    await monitor._task
    sources, _ = monitor.observe()
    assert sources['cob']['reachable'] is True
    assert sources['cob']['status_code'] == 200
    assert 'https://cob.go.ke' in calls and 'https://www.cob.go.ke' not in calls
