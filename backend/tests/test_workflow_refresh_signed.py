"""Invocation-bound refresh acknowledgments; no production or provider calls."""
import hashlib
import hmac
import json
import time

from test_cache_generation_status import isolated, SECRET

CONTEXT = {'source_sha': 'a' * 40, 'plan_sha256': 'b' * 64,
           'run_id': '1234', 'run_attempt': '1', 'schema_head': 'b953a11e0001'}


def request(client, path, **changes):
    body = {'protocol': 'nightly-refresh-v2', 'ts': int(time.time()),
            'nonce': 'c' * 32, 'context': CONTEXT, **changes}
    raw = json.dumps(body, separators=(',', ':')).encode()
    response = client.post(path, content=raw, headers={'x-revalidate-signature':
        hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()})
    return response, raw


def test_backend_acknowledgment_is_signed_and_bound_to_invocation(isolated, monkeypatch):
    from routers import cache_invalidation as invalidation
    monkeypatch.setenv('RENDER_GIT_COMMIT', CONTEXT['source_sha'])
    monkeypatch.setattr(invalidation, 'serving_census', lambda: {
        'scope': 'container', 'instance': 'd' * 64, 'supervisor': '1:100',
        'workers': ['2:200', '3:300'], 'worker': '2:200'}, raising=False)
    response, raw = request(isolated, '/api/v1/system/cache/invalidate')
    assert response.status_code == 200
    signature = hmac.new(SECRET.encode(), response.content, hashlib.sha256).hexdigest()
    assert response.headers.get('x-revalidate-response-signature') == signature
    body = response.json()
    assert body['request_sha256'] == hashlib.sha256(raw).hexdigest()
    assert body['context'] == CONTEXT
    assert body['result']['census']['workers'] == ['2:200', '3:300']


def test_wrong_serving_source_refuses_before_invalidation(isolated, monkeypatch):
    from routers import cache_invalidation as router
    calls = []
    monkeypatch.setenv('RENDER_GIT_COMMIT', 'e' * 40)
    monkeypatch.setattr(router, 'invalidate_all', lambda: calls.append(True) or {})
    response, _ = request(isolated, '/api/v1/system/cache/invalidate')
    assert response.status_code == 409 and calls == []


def test_unknown_refresh_protocol_refuses_before_invalidation(isolated, monkeypatch):
    from routers import cache_invalidation as router
    calls = []
    monkeypatch.setattr(router, 'invalidate_all', lambda: calls.append(True) or {})
    response, _ = request(isolated, '/api/v1/system/cache/invalidate', protocol='future-v900')
    assert response.status_code == 400 and calls == []


def test_actual_gunicorn_census_and_signed_worker_adoption(tmp_path):
    import os
    import re
    import socket
    import subprocess
    import sys
    import signal
    from pathlib import Path
    import httpx
    import pytest
    if os.environ.get('TEST_REFRESH_CENSUS_CONTAINER') == '1':
        # Reproduce Render's separate-UID sidecar in an owned PID/network
        # namespace. Only the fixture launcher needs the identity-switch caps.
        backend = Path(__file__).resolve().parents[1]
        cidfile = tmp_path / 'refresh-census.cid'
        launcher = '''
scratch=$(mktemp -d)
chmod 1777 "$scratch"
export TEST_REFRESH_SIDECAR_PORT="$scratch/port"
setpriv --reuid=10002 --regid=10002 --clear-groups python -B -c '
import socket, sys, time
from pathlib import Path

port = Path(sys.argv[1])
while not port.exists():
    time.sleep(.02)
with socket.socket() as listener:
    listener.bind(("127.0.0.2", int(port.read_text())))
    listener.listen()
    time.sleep(60)
' "$TEST_REFRESH_SIDECAR_PORT" &
export TEST_REFRESH_SIDECAR_PID=$!
exec setpriv --reuid=10001 --regid=10001 --clear-groups "$@"
'''
        try:
            result = subprocess.run([
                'docker', 'run', '--platform', 'linux/amd64', '--pull', 'never', '--rm',
                '--network', 'none', '--user', '0:0', '--cap-drop', 'ALL',
                '--cap-add', 'SETUID', '--cap-add', 'SETGID',
                '--security-opt', 'no-new-privileges', '--cidfile', str(cidfile),
                '--mount', f'type=bind,source={backend},target=/backend,readonly',
                '--workdir', '/backend', '--env', 'HOME=/tmp',
                '--env', 'PYTHONPATH=/backend:/backend/tests',
                '--env', 'PYTHONDONTWRITEBYTECODE=1',
                'auditgava-ci-refresh-census:local', '/bin/sh', '-ec', launcher,
                'fixture', 'python', '-m', 'pytest',
                '--noconftest', '-p', 'no:cacheprovider', '-o', 'addopts=', '-q',
                'tests/test_workflow_refresh_signed.py::test_actual_gunicorn_census_and_signed_worker_adoption',
            ], capture_output=True, text=True, timeout=60)
            assert result.returncode == 0, result.stdout + result.stderr
        finally:
            if cidfile.is_file():
                identity = cidfile.read_text().strip()
                assert re.fullmatch(r'[0-9a-f]{64}', identity), 'Invalid owned census container identity'
                subprocess.run(['docker', 'rm', '-f', identity], capture_output=True, timeout=10)
        return

    sidecar = os.environ.get('TEST_REFRESH_SIDECAR_PID')
    if sidecar is not None:
        proc = Path('/proc') / sidecar
        assert os.geteuid() == 10001
        assert proc.stat().st_uid == 10002
        with pytest.raises(PermissionError):
            list((proc / 'fd').iterdir())

    app = tmp_path/'owned_web.py'
    app.write_text('from fastapi import FastAPI\nfrom routers.cache_invalidation import router\napp=FastAPI()\napp.include_router(router)\n')
    with socket.socket() as reserve:
        reserve.bind(('127.0.0.1',0));port=reserve.getsockname()[1]
    env={**os.environ,'PYTHONPATH':str(tmp_path)+':'+os.environ['PYTHONPATH'],
         'CACHE_GENERATION_FILE':str(tmp_path/'generation'),'REVALIDATE_SECRET':SECRET,
         'RENDER_GIT_COMMIT':CONTEXT['source_sha']}
    with (tmp_path/'server.log').open('w') as log:
        process=subprocess.Popen([sys.executable,'-m','gunicorn','--config','/dev/null','--workers','2',
            '--worker-class','uvicorn.workers.UvicornWorker','--bind',f'127.0.0.1:{port}',
            '--timeout','20','--graceful-timeout','2','owned_web:app'],cwd=tmp_path,env=env,
            stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    try:
        deadline=time.monotonic()+15
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=2,headers={'Connection':'close'}) as client:
            while True:
                try:
                    response,_=request(client,'/api/v1/system/cache/invalidate')
                    assert response.status_code == 200, (response.text, (tmp_path/'server.log').read_text())
                    break
                except httpx.HTTPError:pass
                assert process.poll() is None and time.monotonic()<deadline,(tmp_path/'server.log').read_text()
                time.sleep(.05)
            original=response.json()['result'];workers=original['census']['workers']
            assert len(workers) == len(set(workers)) == 2

            def signed_worker_status():
                response, raw = request(client, '/api/v1/system/cache/status',
                                        nonce=__import__('secrets').token_hex(16))
                assert response.status_code == 200, response.text
                signature = hmac.new(SECRET.encode(), response.content, hashlib.sha256).hexdigest()
                assert response.headers['x-revalidate-response-signature'] == signature
                value = response.json()
                assert value['request_sha256'] == hashlib.sha256(raw).hexdigest()
                row = value['result']
                assert row['census']['workers'] == workers
                assert row['observed_identity'] == row['adopted_identity'] == original['marker_identity']
                assert row['synchronised'] is True
                return row['census']['worker']

            first = signed_worker_status()
            assert first in workers
            pid = int(first.split(':', 1)[0])
            from cache.invalidation import _process
            worker = _process(pid)
            assert worker['identity'] == first and worker['parent'] == process.pid
            assert os.getpgid(pid) == process.pid

            # Pause the worker that already answered. Its listening socket and
            # census identity stay intact, but only its peer can handle a request.
            os.kill(pid, signal.SIGSTOP)
            try:
                deadline = time.monotonic() + 2
                while True:
                    status = Path(f'/proc/{pid}/status').read_text()
                    if re.search(r'^State:\s+T\b', status, re.MULTILINE):
                        break
                    assert time.monotonic() < deadline, 'Fixture worker did not stop'
                    time.sleep(.01)
                peer = signed_worker_status()
            finally:
                os.kill(pid, signal.SIGCONT)

            def assert_all_workers_acknowledged(*identities):
                assert set(identities) == set(workers), 'Incomplete signed worker adoption'

            with pytest.raises(AssertionError, match='Incomplete signed worker adoption'):
                assert_all_workers_acknowledged(peer)
            assert_all_workers_acknowledged(first, peer)

            if sidecar is not None:
                # The separate-UID process now binds the same port on another
                # address. Its unreadable descriptors cannot hide that listener.
                port_file = Path(os.environ['TEST_REFRESH_SIDECAR_PORT'])
                staged = port_file.with_suffix('.new')
                staged.write_text(str(port))
                staged.replace(port_file)
                deadline = time.monotonic() + 5
                while True:
                    try:
                        with socket.create_connection(('127.0.0.2', port), timeout=1):
                            break
                    except ConnectionRefusedError:
                        assert time.monotonic() < deadline, 'Fixture listener did not start'
                        time.sleep(.02)
                generation = tmp_path/'generation'
                before = generation.stat()
                response, _ = request(client, '/api/v1/system/cache/invalidate')
                assert response.status_code == 500 and response.json()['detail']['error'] == 'serving_census_unverified'
                assert generation.stat() == before
    finally:
        os.killpg(process.pid,signal.SIGTERM)
        try:process.wait(timeout=6)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=3)
        try:os.killpg(process.pid,0)
        except ProcessLookupError:pass
        else:raise AssertionError('owned web process group remains')


def test_backend_refuses_oversized_signed_body_before_mutation(isolated,monkeypatch):
    from routers import cache_invalidation as router
    calls=[];monkeypatch.setattr(router,'invalidate_all',lambda:calls.append(True) or {})
    raw=json.dumps({'ts':time.time(),'reason':'x'*9000}).encode()
    response=isolated.post('/api/v1/system/cache/invalidate',content=raw,headers={
        'x-revalidate-signature':hmac.new(SECRET.encode(),raw,hashlib.sha256).hexdigest()})
    assert response.status_code==413 and calls==[]
