"""Invocation-bound refresh acknowledgments; no production or provider calls."""
import hashlib
import hmac
import json
import time

from test_cache_generation_status import isolated, SECRET

CONTEXT = {'source_sha': 'a' * 40, 'plan_sha256': 'b' * 64,
           'run_id': '1234', 'run_attempt': '1', 'schema_head': 'a756b20a0001'}


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
    import socket
    import subprocess
    import sys
    import signal
    import httpx
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
                    if response.status_code==200:break
                except httpx.HTTPError:pass
                assert process.poll() is None and time.monotonic()<deadline,(tmp_path/'server.log').read_text()
                time.sleep(.05)
            original=response.json()['result'];workers=original['census']['workers']
            assert len(workers)==2
            seen=set()
            for _ in range(64):
                response,raw=request(client,'/api/v1/system/cache/status',nonce=__import__('secrets').token_hex(16))
                assert response.status_code==200,response.text
                assert response.headers['x-revalidate-response-signature']==hmac.new(SECRET.encode(),response.content,hashlib.sha256).hexdigest()
                value=response.json();assert value['request_sha256']==hashlib.sha256(raw).hexdigest()
                row=value['result'];assert row['census']['workers']==workers
                assert row['observed_identity']==row['adopted_identity']==original['marker_identity']
                assert row['synchronised'] is True
                seen.add(row['census']['worker'])
                if seen==set(workers):break
            assert seen==set(workers)
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
