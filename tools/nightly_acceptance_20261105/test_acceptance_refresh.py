"""Two real serving cache-router workers plus an inert HMAC frontend responder."""
import copy
from datetime import datetime, timezone
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time

import pytest
from common import Refusal, canonical, sha256
from acceptance_refresh import capture_loopback, observe_workers, verify_capture
from record import reap


@pytest.fixture(scope='module')
def actual_capture(tmp_path_factory):
    root = tmp_path_factory.mktemp('real-serving-refresh')
    secret = b'inert-only-refresh-signing-key-20261105'
    run = dict(commit='a'*40, run_id=101, attempt=1)
    (root/'acceptance_fixture_app.py').write_text(
        'from fastapi import FastAPI\nfrom routers.cache_invalidation import router\n'
        'from cache.invalidation import register_local_cache\n'
        'app=FastAPI(); app.include_router(router)\n'
        'register_local_cache("owned-probe",lambda: 0)\n')
    class Frontend(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
            if self.path != '/api/revalidate' or not hmac.compare_digest(signature, self.headers.get('x-revalidate-signature','')):
                self.send_error(401); return
            value = json.loads(body)
            result = canonical(dict(revalidated=value['paths'], rejected=[], at=datetime.now(timezone.utc).isoformat()))
            self.send_response(200); self.send_header('Content-Length',str(len(result))); self.end_headers(); self.wfile.write(result)
    frontend = ThreadingHTTPServer(('127.0.0.1',0), Frontend)
    thread = threading.Thread(target=frontend.serve_forever, daemon=True); thread.start()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port = sock.getsockname()[1]
    env = {'PATH':str(Path(sys.executable).parent)+':/usr/bin:/bin',
        'PYTHONPATH':str(root)+':'+str(Path(__file__).absolute().parents[2]/'backend'),
        'HOME':str(root), 'TMPDIR':str(root), 'PYTHONDONTWRITEBYTECODE':'1', 'PYTHON_DOTENV_DISABLED':'1',
        'REVALIDATE_SECRET':secret.decode(), 'CACHE_GENERATION_FILE':str(root/'generation'),
        'RENDER_GIT_COMMIT':run['commit'], 'REDIS_URL':'', 'ENVIRONMENT':'test',
        'SECRET_BACKEND':'env', 'SECRET_KEY':'inert-fixture-key-20261105'}
    with (root/'server.log').open('xb') as log:
        process = subprocess.Popen([sys.executable,'-B','-m','uvicorn','acceptance_fixture_app:app',
            '--host','127.0.0.1','--port',str(port),'--workers','2','--log-level','warning'],
            cwd=root, env=env, stdout=log, stderr=log, start_new_session=True)
        try:
            deadline = time.monotonic()+25
            while True:
                try:
                    census = observe_workers(process.pid,port,2)
                    with socket.create_connection(('127.0.0.1',port),.2): pass
                    break
                except (Refusal, OSError):
                    if process.poll() is not None or time.monotonic()>=deadline:
                        pytest.fail('real serving prerequisite failed: '+(root/'server.log').read_text()[-2000:])
                    time.sleep(.05)
            observed = capture_loopback(root/'capture',supervisor_pid=process.pid,backend_port=port,
                frontend_port=frontend.server_port,expected_workers=2,secret=secret,run_binding=run)
            assert observed['verdict']=='LOCAL_SERVING_SIGNED_REFRESH_OBSERVED'
            with pytest.raises(Refusal): observe_workers(os.getpid(),port,2)
        finally:
            cleanup = reap(process)
            frontend.shutdown(); frontend.server_close(); thread.join(timeout=3)
    assert cleanup['group_absent'] is True and not thread.is_alive()
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); sock.bind(('127.0.0.1',port))
    return root/'capture', secret, run, census


def test_real_signed_serving_census_precedes_page_ack(actual_capture):
    path, secret, run, census = actual_capture
    verified = verify_capture(path/'refresh.json',secret=secret,expected_binding=run,expected_census=census)
    assert len(verified['worker_pids'])==2 and verified['production_accepted'] is False


@pytest.mark.parametrize('mutation', ['forged-signature','wrong-run','inert-body','missing-worker',
    'duplicate-worker','frontend-first','partial-pages','stale-request','false-layer',
    'boolean-binding','malformed-response'])
def test_resealed_malformed_or_forged_refresh_cannot_pass(actual_capture,tmp_path,mutation):
    source, secret, run, census = actual_capture
    root=tmp_path/'packet'; shutil.copytree(source,root)
    path=root/'refresh.json';value=json.loads(path.read_bytes())
    def replace(event, key, body):
        original=root/event[key]['path']; original.write_bytes(body)
        event[key].update(sha256=sha256(original),size=len(body))
        if key=='request':event['signature']=hmac.new(secret,body,hashlib.sha256).hexdigest()
    if mutation=='forged-signature': value['events'][0]['signature']='a'*64
    elif mutation=='wrong-run':value['binding']['run_id']=102
    elif mutation=='inert-body':replace(value['events'][0],'response',b'{"success":true}')
    elif mutation=='missing-worker':value['events'].pop(1)
    elif mutation=='duplicate-worker':value['events'][2]['response']=value['events'][1]['response']
    elif mutation=='frontend-first':value['events'][0],value['events'][-1]=value['events'][-1],value['events'][0]
    elif mutation=='partial-pages':
        event=value['events'][-1];response=json.loads((root/event['response']['path']).read_bytes());response['revalidated'].pop()
        replace(event,'response',canonical(response))
    elif mutation in ('stale-request','boolean-binding'):
        event=value['events'][0];request=json.loads((root/event['request']['path']).read_bytes())
        if mutation=='stale-request':request['ts']-=1000
        else:request['binding']['attempt']=True
        replace(event,'request',canonical(request))
    elif mutation=='false-layer':
        event=value['events'][0];response=json.loads((root/event['response']['path']).read_bytes());response['redis']={}
        replace(event,'response',canonical(response))
    else:replace(value['events'][0],'response',b'[]')
    value['seal']=hmac.new(secret,b'nightly-refresh-capture-v1\0'+canonical({k:v for k,v in value.items()if k!='seal'}),hashlib.sha256).hexdigest()
    path.write_bytes(canonical(value))
    with pytest.raises((Refusal, ValueError)):
        verify_capture(path,secret=secret,expected_binding=run,expected_census=census)


def test_offline_refresh_rejects_untrusted_key_and_missing_original(actual_capture,tmp_path):
    source, secret, run, census=actual_capture
    with pytest.raises(Refusal,match='seal'):
        verify_capture(source/'refresh.json',secret=b'wrong-inert-key-but-long-enough-20261105',expected_binding=run,expected_census=census)
    root=tmp_path/'packet';shutil.copytree(source,root)
    value=json.loads((root/'refresh.json').read_bytes());(root/value['events'][0]['request']['path']).unlink()
    with pytest.raises((Refusal,OSError)):
        verify_capture(root/'refresh.json',secret=secret,expected_binding=run,expected_census=census)


@pytest.mark.parametrize('fault', ['invalidation', 'unsynchronised', 'wrong-commit', 'wrong-marker'])
def test_bad_backend_never_reaches_frontend(tmp_path, monkeypatch, fault):
    """Actual loopback HTTP, with a known census and deliberately bad ack bodies."""
    import acceptance_refresh as module
    secret=b'inert-only-refresh-signing-key-20261105'
    run=dict(commit='a'*40,run_id=101,attempt=1)
    seen=[]
    class Peer(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            seen.append(self.path)
            if self.path.endswith('/invalidate'):
                value=dict(invalidated=fault!='invalidation',reason=request['reason'],generation='a'*32,
                    marker_identity=[7,8,9],pid=7,redis=dict(configured=False,deleted=0),
                    local=dict(cleared_entries=0,by_cache={'probe':0}))
            elif self.path.endswith('/status'):
                value=dict(pid=7,commit='b'*40 if fault=='wrong-commit' else run['commit'],
                    synchronised=fault!='unsynchronised',marker_path='/scratch/marker',
                    observed_identity=[7,8,9],adopted_identity=[7,8,10] if fault=='wrong-marker' else [7,8,9])
            else:value=dict(revalidated=request['paths'],rejected=[],at=datetime.now(timezone.utc).isoformat())
            body=canonical(value);self.send_response(200);self.send_header('Content-Length',str(len(body)))
            self.end_headers();self.wfile.write(body)
    backend=ThreadingHTTPServer(('127.0.0.1',0),Peer);frontend=ThreadingHTTPServer(('127.0.0.1',0),Peer)
    threads=[threading.Thread(target=s.serve_forever,daemon=True)for s in (backend,frontend)]
    for thread in threads:thread.start()
    census=dict(supervisor_pid=6,supervisor_start_ticks=1,port=backend.server_port,
                listener_inode='123',workers=[dict(pid=7,start_ticks=2)])
    monkeypatch.setattr(module,'observe_workers',lambda *args:census)
    try:
        with pytest.raises(Refusal):
            capture_loopback(tmp_path/'bad-capture',supervisor_pid=6,backend_port=backend.server_port,
                frontend_port=frontend.server_port,expected_workers=1,secret=secret,run_binding=run)
        assert '/api/revalidate' not in seen, seen
    finally:
        for server in (backend,frontend):server.shutdown();server.server_close()
        for thread in threads:thread.join(timeout=3)


@pytest.mark.parametrize('phase',['headers','body'])
def test_trickling_peer_cannot_extend_absolute_refresh_deadline(tmp_path,monkeypatch,phase):
    import acceptance_refresh as module
    from types import SimpleNamespace
    real_monotonic=time.monotonic
    # The existing 30s policy becomes 1 real second, keeping the regression
    # bounded while preserving real socket inactivity vs absolute-time behavior.
    monkeypatch.setattr(module,'time',SimpleNamespace(monotonic=lambda:30*real_monotonic(),
        monotonic_ns=time.monotonic_ns,time=time.time,sleep=time.sleep))
    class Trickle(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            body=b'{"invalidated":false}'
            wire=b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'
            try:
                if phase=='headers':
                    for byte in wire:self.connection.sendall(bytes([byte]));time.sleep(.06)
                    self.connection.sendall(body)
                else:
                    self.connection.sendall(wire)
                    for byte in body:self.connection.sendall(bytes([byte]));time.sleep(.15)
            except (BrokenPipeError,ConnectionResetError):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Trickle)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    census=dict(supervisor_pid=6,supervisor_start_ticks=1,port=server.server_port,
                listener_inode='123',workers=[dict(pid=7,start_ticks=2)])
    monkeypatch.setattr(module,'observe_workers',lambda *args:census)
    started=real_monotonic()
    try:
        with pytest.raises((Refusal,TimeoutError)):
            capture_loopback(tmp_path/'slow',supervisor_pid=6,backend_port=server.server_port,
                frontend_port=server.server_port+1,expected_workers=1,
                secret=b'inert-only-refresh-signing-key-20261105',run_binding=dict(commit='a'*40,run_id=101,attempt=1))
        assert real_monotonic()-started < 2.5, 'idle timeout extended the absolute capture budget'
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
