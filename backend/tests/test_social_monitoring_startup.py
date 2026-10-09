"""Real main.app startup and SDK captures in secret-free isolated processes."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROUTE_INVENTORY = r'''
def social_route_inventory(routes):
    from fastapi import routing
    # Older supported FastAPI versions flatten included routers; current
    # versions expose effective prefixed contexts through the public iterator.
    contexts = getattr(routing, 'iter_route_contexts', iter)(routes)
    return [(method, route.path) for route in contexts
            for method in (getattr(route, 'methods', None) or ())
            if '/social' in (getattr(route, 'path', None) or '')]
'''

SCRIPT = ROUTE_INVENTORY + r'''
import json, socket, sys
import os
socket.socket.connect = lambda *a, **kw: (_ for _ in ()).throw(AssertionError('External network forbidden'))
import sentry_sdk
from sentry_sdk.transport import Transport
sent = []; calls = []; startup_error = None
class MemoryTransport(Transport):
    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.type in ('event', 'transaction'):
                sent.append((item.type, item.payload.json))
            else:
                sent.append((item.type, {}))
original_init = sentry_sdk.init
def memory_init(**options):
    calls.append(options)
    options['transport'] = MemoryTransport
    return original_init(**options)
sentry_sdk.init = memory_init
try:
    import main
except Exception as exc:
    startup_error = str(exc)
if startup_error is None:
    if os.environ.get('CI_DUPLICATE_SOCIAL_ROUTER') == 'true':
        from social.api import router
        main.app.include_router(router)
    from fastapi.testclient import TestClient
    from social.api import service, require_admin
    from supabase_auth import AdminUser
    class Fixture:
        def status(self):
            return dict(publishing_enabled=False, controls_version=1,
                worker=dict(state='unavailable', heartbeat_at=None, last_scan_at=None),
                queue_counts={}, adapters_available=[], media_upload_available=False,
                generation_enabled=False, auto_approve_enabled=False,
                auto_schedule_enabled=False, auto_publish_enabled=False)
        def posts(self, *args):
            raise RuntimeError('INERT-549-PRIVATE-MARKER')
    main.app.dependency_overrides[service] = lambda: Fixture()
    main.app.dependency_overrides[require_admin] = lambda: AdminUser(
        id='00000000-0000-4000-8000-000000000001', email=None, roles=['admin'])
    # Exercise actual middleware/router without unrelated seeding/schedulers.
    client = TestClient(main.app, raise_server_exceptions=False)
    @main.app.post('/_runtime-fixture/error')
    async def automatic_error(request: __import__('fastapi').Request):
        body = await request.body()
        assert b'INERT-549-PRIVATE-MARKER' in body
        raise RuntimeError('INERT-549-PRIVATE-MARKER')
    responses = [client.get('/api/v1/admin/social/system/status', params={'code':'INERT-549-PRIVATE-MARKER'}),
                 client.get('/api/v1/admin/social/posts', params={'access_token':'INERT-549-PRIVATE-MARKER'})]
    main.app.dependency_overrides.clear()
    responses.append(client.get('/api/v1/admin/social/accounts'))
    assert [r.status_code for r in responses] == [200,500,401]
    assert all(r.headers['cache-control'] == 'private, no-store' for r in responses)
    routes = social_route_inventory(main.app.routes)
    assert len(routes) == len(set(routes)) == 35, 'Social route inventory must contain 35 unique registrations'
    assert not any('/privacy/' in path for _,path in routes)
    assert not vars(main.app.state)['_state']
    assert client.post('/_runtime-fixture/error', data={'signed_request':'INERT-549-PRIVATE-MARKER'}).status_code == 500
sentry_sdk.flush()
transactions = [e for kind,e in sent if kind == 'transaction']
events = [e for kind,e in sent if kind == 'event']
print(json.dumps(dict(init_calls=len(calls), startup_error=startup_error,
    events=len(events), transactions=len(transactions),
    status_codes=[e.get('contexts',{}).get('response',{}).get('status_code') for e in transactions],
    marker_present='INERT-549-PRIVATE-MARKER' in json.dumps(sent),
    profiles=sum(kind=='profile' for kind,_ in sent),
    private_options_disabled=all(o['include_local_variables'] is False and o['include_source_context'] is False
        and o['profiles_sample_rate']==0 and o['max_request_body_size']=='never' for o in calls))))
'''


def capture(**values):
    backend = Path(__file__).resolve().parents[1]
    env = {'PATH': os.defpath, 'PYTHONPATH': str(backend), 'PYTHON_DOTENV_DISABLED': '1',
           'DATABASE_URL': 'postgresql+psycopg2://test:test@127.0.0.1:55474/unused',
           'SECRET_BACKEND':'env', 'ENVIRONMENT':'test', 'AUTO_SEEDER_ENABLED':'false',
           'AUTO_WARMUP_ENABLED':'false', **values}
    result = subprocess.run([sys.executable, '-B', '-c', SCRIPT], cwd=backend, env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, 'Isolated actual-app capture failed: ' + result.stderr[-2000:]
    return json.loads(result.stdout)


@pytest.mark.parametrize('enabled', [None, 'false'])
def test_dsn_alone_never_activates_actual_app(enabled):
    values = {'SENTRY_DSN':'https://fixture@example.invalid/1', 'SENTRY_TRACES_SAMPLE_RATE':'private-invalid'}
    if enabled is not None:
        values['SENTRY_ENABLED'] = enabled
    result = capture(**values)
    assert result['init_calls'] == result['transactions'] == result['events'] == 0
    assert result['startup_error'] is None


def test_explicit_actual_app_startup_preserves_healthy_and_failed_captures():
    result = capture(SENTRY_ENABLED='true', SENTRY_DSN='https://fixture@example.invalid/1',
                     SENTRY_TRACES_SAMPLE_RATE='1', SENTRY_PROFILES_SAMPLE_RATE='1')
    assert result['init_calls'] == 1
    # The app logger and automatic exception integration each emit one event.
    assert result['transactions'] == 4 and result['events'] == 2
    assert result['status_codes'] == [200,500,401,500]
    assert result['marker_present'] is False and result['profiles'] == 0
    assert result['private_options_disabled']


def test_duplicate_actual_social_router_registration_is_detected():
    with pytest.raises(AssertionError, match='Social route inventory must contain 35 unique registrations'):
        capture(CI_DUPLICATE_SOCIAL_ROUTER='true')


def test_route_inventory_supports_flat_routes_without_discarding_duplicates(monkeypatch):
    from fastapi import APIRouter, routing

    router = APIRouter()

    @router.get('/api/v1/admin/social/fixture')
    async def fixture():
        return {'fixture': True}

    namespace = {}
    exec(ROUTE_INVENTORY, namespace)
    monkeypatch.delattr(routing, 'iter_route_contexts', raising=False)
    inventory = namespace['social_route_inventory']
    expected = [('GET', '/api/v1/admin/social/fixture')]
    assert inventory(router.routes) == expected
    assert inventory(router.routes + router.routes) == expected + expected


@pytest.mark.parametrize('values', [
    {}, {'SENTRY_DSN':'INERT-549-PRIVATE-MARKER'},
    {'SENTRY_DSN':'https://fixture@example.invalid/1', 'SENTRY_TRACES_SAMPLE_RATE':'INERT-549-PRIVATE-MARKER'},
    *({'SENTRY_DSN':'https://fixture@example.invalid/1', 'SENTRY_TRACES_SAMPLE_RATE':v}
      for v in ['nan','inf','-1','1.1']),
])
def test_enabled_invalid_configuration_fails_before_sdk_init_without_private_detail(values):
    result = capture(SENTRY_ENABLED='true', **values)
    assert result['init_calls'] == 0
    assert result['startup_error'] == 'Sentry startup configuration is invalid.'


def test_invalid_opt_in_is_a_safe_configuration_failure():
    result = capture(SENTRY_ENABLED='INERT-549-PRIVATE-MARKER')
    assert result['init_calls'] == 0
    assert result['startup_error'] == 'Sentry startup configuration is invalid.'


def test_direct_setup_sampling_parse_error_does_not_echo_configuration(monkeypatch):
    from fastapi import FastAPI
    from monitoring.instrumentation import setup_sentry
    monkeypatch.setenv('SENTRY_TRACES_SAMPLE_RATE', 'INERT-549-PRIVATE-MARKER')
    with pytest.raises(ValueError) as failure:
        setup_sentry(FastAPI(), dsn='https://fixture@example.invalid/1')
    assert str(failure.value) == 'Sentry trace sampling configuration is invalid.'
