"""Real application import and HTTP ingress with inert, isolated configuration."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


MARKER = 'INERT-META-STARTUP-PRIVATE'
SCRIPT = r'''
import io, json, logging, socket
socket.socket.connect = lambda *a, **kw: (_ for _ in ()).throw(AssertionError('Network forbidden'))
result = {}
try:
    import main
except Exception as error:
    chain = []
    while error is not None:
        chain.append(str(error))
        error = error.__context__
    result['startup_errors'] = chain
else:
    from fastapi.testclient import TestClient
    from social.privacy.api import DATA_PATH, STATUS_PATH, DEAUTH_PATH
    from social.privacy.runtime import registered_ownership
    from types import SimpleNamespace
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(logging.Formatter('%(message)s'))
    audit = logging.getLogger('middleware.security')
    audit.setLevel(logging.DEBUG)
    audit.addHandler(handler)
    client = TestClient(main.app, raise_server_exceptions=False)
    responses = [client.post(DATA_PATH, content='unknown=INERT-META-STARTUP-PRIVATE',
        headers={'Content-Type':'application/x-www-form-urlencoded'}),
        client.get(STATUS_PATH, params={'code':'INERT-META-STARTUP-PRIVATE'}),
        client.post(DEAUTH_PATH, content='signed_request=x',
            headers={'Content-Type':'application/x-www-form-urlencoded'})]
    client.get('/api/v1/social/privacy/meta/INERT-META-STARTUP-PRIVATE')
    owner = registered_ownership(SimpleNamespace(app=main.app))
    # Exercise the installed Uvicorn formatter, whose five-argument contract
    # is distinct from the application audit logger.
    from uvicorn.logging import AccessFormatter
    handler.setFormatter(AccessFormatter('%(message)s', use_colors=False))
    access = logging.getLogger('uvicorn.access')
    access.setLevel(logging.INFO)
    access.addHandler(handler)
    access.info('%s - "%s %s HTTP/%s" %d', '127.0.0.1:1', 'GET',
        STATUS_PATH + '?code=INERT-META-STARTUP-PRIVATE', '1.1', 404)
    result.update(startup_errors=[], statuses=[r.status_code for r in responses],
        bodies=[r.text for r in responses],
        headers=[dict(r.headers) for r in responses],
        ownership_app=owner.app_id if owner else None,
        native_registered=hasattr(main.app.state, 'social_native_registration'),
        private_log_marker='INERT-META-STARTUP-PRIVATE' in output.getvalue())
print(json.dumps(result))
'''


def configuration():
    return {
        'META_PRIVACY_ENABLED': 'true', 'META_DEAUTHORIZATION_ENABLED': 'true',
        'META_APP_ID': '1396416369308998',
        'META_APP_SECRET': MARKER,
        'META_PRIVACY_STATUS_URL': 'https://privacy.example.test/api/v1/social/privacy/meta/data-deletion/status',
        'SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION': 'e1',
        'SOCIAL_CREDENTIAL_KEYS': json.dumps({'e1': base64.urlsafe_b64encode(b'e' * 32).decode()}),
        'META_PRIVACY_SUBJECT_ACTIVE_KEY_VERSION': 'd1',
        'META_PRIVACY_SUBJECT_KEYS': json.dumps({'d1': base64.urlsafe_b64encode(b'd' * 32).decode()}),
    }


def capture(values):
    backend = Path(__file__).resolve().parents[1]
    env = {'PATH': os.defpath, 'PYTHONPATH': str(backend), 'PYTHON_DOTENV_DISABLED': '1',
           'DATABASE_URL': 'postgresql+psycopg2://test:test@127.0.0.1:55474/unused',
           'SECRET_BACKEND': 'env', 'ENVIRONMENT': 'test', 'AUTO_SEEDER_ENABLED': 'false',
           'AUTO_WARMUP_ENABLED': 'false', **values}
    run = subprocess.run([sys.executable, '-B', '-c', SCRIPT], cwd=backend,
                         env=env, text=True, capture_output=True, timeout=30)
    assert run.returncode == 0, run.stderr[-2000:]
    result = json.loads(run.stdout)
    assert MARKER not in run.stdout + run.stderr
    return result


def test_explicit_privacy_configuration_installs_actual_public_signed_ingress():
    result = capture(configuration())
    assert result['startup_errors'] == []
    assert result['statuses'] == [400, 404, 400]
    assert json.loads(result['bodies'][0])['detail']['code'] == 'PRIVACY_REQUEST_INVALID'
    assert result['ownership_app'] == '1396416369308998'
    assert result['native_registered'] is False
    assert result['private_log_marker'] is False
    for headers in result['headers']:
        assert headers['cache-control'] == 'private, no-store'
        assert headers['referrer-policy'] == 'no-referrer'
        assert headers['content-security-policy'] == "default-src 'none'; frame-ancestors 'none'"


@pytest.mark.parametrize('deauthorization', [None, 'false'])
def test_privacy_only_keeps_app_removal_off_by_default(deauthorization):
    values = configuration()
    if deauthorization is None:
        values.pop('META_DEAUTHORIZATION_ENABLED')
    else:
        values['META_DEAUTHORIZATION_ENABLED'] = deauthorization
    result = capture(values)
    assert result['startup_errors'] == []
    assert result['statuses'] == [400, 404, 404]
    assert result['ownership_app'] == '1396416369308998'


@pytest.mark.parametrize('enabled', [None, 'false'])
def test_disabled_privacy_ignores_unused_secrets_and_mounts_nothing(enabled):
    values = {k: MARKER for k in configuration()
              if k not in {'META_PRIVACY_ENABLED', 'META_DEAUTHORIZATION_ENABLED'}}
    if enabled is not None:
        values['META_PRIVACY_ENABLED'] = enabled
    result = capture(values)
    assert result['startup_errors'] == []
    assert result['statuses'] == [404, 404, 404]
    assert result['ownership_app'] is None


@pytest.mark.parametrize('change', [
    {'META_PRIVACY_ENABLED': 'yes'},
    {'META_DEAUTHORIZATION_ENABLED': 'yes'},
    {'META_PRIVACY_ENABLED': 'false'},
    {'META_CONNECTIONS_ENABLED': 'true', 'META_DEAUTHORIZATION_ENABLED': 'false'},
    {'META_CONNECTIONS_ENABLED': 'true', 'META_PRIVACY_ENABLED': 'false'},
    {'META_APP_ID': MARKER}, {'META_APP_SECRET': ''},
    {'META_PRIVACY_STATUS_URL': 'https://privacy.example.test/wrong'},
    {'SOCIAL_CREDENTIAL_KEYS': MARKER},
    {'META_PRIVACY_SUBJECT_KEYS': MARKER},
    {'META_PRIVACY_SUBJECT_KEYS': '{"d1":"' + MARKER + '","d1":"duplicate"}'},
    {'META_PRIVACY_SUBJECT_ACTIVE_KEY_VERSION': 'missing'},
    {'META_PRIVACY_SUBJECT_KEYS': json.dumps({'d1': base64.urlsafe_b64encode(b'e' * 32).decode()})},
])
def test_invalid_or_incomplete_enabled_configuration_refuses_app_startup_without_secret_context(change):
    result = capture({**configuration(), **change})
    assert result['startup_errors'] == [
        'PRIVACY_CONFIGURATION_INVALID'
    ]
