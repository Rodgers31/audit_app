"""Independent hostile-boundary controls. No remote/production traffic."""
import base64
import hashlib
import hmac
import io
import json
from types import SimpleNamespace

import pytest

import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location("reviewed_refresh", Path(__file__).resolve().parents[2] / "scripts/verification/nightly_workflow/refresh.py")
refresh=importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)
from cache import invalidation
from social.connections.provider import _IdentityBodyStream

CONTEXT = {'source_sha':'a'*40,'plan_sha256':'b'*64,'run_id':'1234','run_attempt':'1','schema_head':'a756b20a0001'}


class Reply(io.BytesIO):
    status = 200
    def __init__(self, raw, signature):
        super().__init__(raw)
        self.headers = {'x-revalidate-response-signature':signature}


def test_exact_original_response_retained_for_signed_non_utf8(tmp_path):
    """Invalid JSON must refuse, but its retained signature still needs original bytes."""
    raw = b'{"result":"\xff"}'
    signature = hmac.new(b'fixture', raw, hashlib.sha256).hexdigest()
    evidence = tmp_path/'evidence'
    client = refresh.SignedClient('fixture', CONTEXT, evidence)
    client.opener = SimpleNamespace(open=lambda *a, **k: Reply(raw, signature))
    with pytest.raises((ValueError, UnicodeError)):
        client.post('https://fixture.invalid/status')
    stored = json.loads(evidence.read_text())
    if 'response_base64' in stored:
        retained = base64.b64decode(stored['response_base64'], validate=True)
    else:
        retained = stored['response'].encode()
    assert retained == raw, (retained, raw)
    assert hmac.new(b'fixture', retained, hashlib.sha256).hexdigest() == stored['response_signature']


def test_valid_pid1_single_uvicorn_needs_no_nonexistent_parent(monkeypatch):
    """The repository container's exec-form CMD can make Uvicorn PID1/PPID0."""
    def process(pid):
        if pid == 0:
            raise FileNotFoundError('/proc/0/stat')
        assert pid == 1
        return {'pid':1,'parent':0,'identity':'1:123',
                'command':'/usr/local/bin/python /usr/local/bin/uvicorn main:app --host 0.0.0.0 --workers 1'}
    monkeypatch.setattr(invalidation, '_process', process)
    monkeypatch.setattr(invalidation.os, 'getpid', lambda:1)
    monkeypatch.setattr(invalidation, '_listener_scope', lambda allowed: None)
    result = invalidation.serving_census()
    assert result['workers'] == ['1:123'] and result['worker'] == '1:123'


def test_unknown_process_named_uvicorn_is_not_a_supported_server(monkeypatch):
    """An arbitrary script path substring cannot establish serving topology."""
    def process(pid):
        if pid == 99:
            return {'pid':99,'parent':98,'identity':'99:123','command':'python /scratch/not_uvicorn_supervised.py'}
        return {'pid':98,'parent':1,'identity':'98:100','command':'python /scratch/custom_pool.py'}
    monkeypatch.setattr(invalidation, '_process', process)
    monkeypatch.setattr(invalidation.os, 'getpid', lambda:99)
    with pytest.raises(invalidation.InvalidationError, match='serving_census_unverified'):
        invalidation.serving_census()


@pytest.mark.parametrize('bad',[None,{},[],True,float('nan'),float('inf'),-1,0,'0'])
def test_direct_context_invalid_shapes_refuse(bad,tmp_path):
    with pytest.raises((ValueError,TypeError)):
        refresh.SignedClient('fixture',bad,tmp_path/'unused')


@pytest.mark.parametrize('bad',[None,{},[],True,{'scope':'container','instance':'a'*64,'supervisor':'1:1','workers':[],'worker':'1:1'},
    {'scope':'container','instance':'a'*64,'supervisor':'1:1','workers':['1:1','1:1'],'worker':'1:1'},
    {'scope':'container','instance':'a'*64,'supervisor':'1:1','workers':['1:1'],'worker':'2:1'}])
def test_direct_census_empty_duplicate_missing_worker_refuses(bad):
    with pytest.raises((ValueError,TypeError)):
        refresh.census_key(bad)


def test_provider_rejects_oversized_transport_before_coalescer_copy():
    class Source:
        closed=False
        def __iter__(self):yield b'x' * 1_000_001
        def close(self):self.closed=True
    source=Source();out=_IdentityBodyStream(source,None,1_000_000)
    with pytest.raises(ValueError):next(iter(out))
    out.close();assert source.closed


def test_provider_trickle_checks_deadline_on_every_transport_chunk(monkeypatch):
    from social.connections import provider
    now=[0]
    monkeypatch.setattr(provider.time,'monotonic',lambda:now[0])
    class Source:
        count=0
        def __iter__(self):
            for _ in range(100):
                self.count+=1;now[0]+=11;yield b'x'
        def close(self):pass
    source=Source();out=_IdentityBodyStream(source,None,1_000_000)
    with pytest.raises(ValueError):list(out)
    assert source.count==3


def test_signed_client_nan_clock_fails_closed_before_http(tmp_path):
    calls=[]
    clock=[0.0]
    client=refresh.SignedClient('fixture',CONTEXT,tmp_path/'evidence',clock=lambda:clock[0])
    client.opener=SimpleNamespace(open=lambda *a,**k:calls.append(True))
    clock[0]=float('nan')
    with pytest.raises(ValueError):client.post('https://fixture.invalid/status')
    assert not calls


def test_two_independent_uvicorn_servers_cannot_each_certify_singleton(tmp_path):
    """Real sibling web processes cannot each be all-serving singleton truth."""
    import os,socket,subprocess,sys,signal,time,httpx
    app=tmp_path/'peer_app.py'
    app.write_text('from fastapi import FastAPI,HTTPException\nfrom cache.invalidation import serving_census,InvalidationError\napp=FastAPI()\n@app.get("/census")\ndef census():\n try:return serving_census()\n except InvalidationError as e:raise HTTPException(503,e.reason)\n')
    ports=[]
    for _ in range(2):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));ports.append(listener.getsockname()[1])
    children=[]
    try:
        for port in ports:
            log=(tmp_path/f'server-{port}.log').open('w')
            process=subprocess.Popen([sys.executable,'-m','uvicorn','peer_app:app','--host','127.0.0.1','--port',str(port),'--workers','1'],cwd=tmp_path,env={**os.environ,'PYTHONPATH':str(tmp_path)+':'+os.environ['PYTHONPATH']},stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            children.append(process);log.close()
        results=[]
        with httpx.Client(trust_env=False,timeout=1) as client:
            for port in ports:
                end=time.monotonic()+15
                while True:
                    try:response=client.get(f'http://127.0.0.1:{port}/census');break
                    except httpx.HTTPError:
                        assert time.monotonic()<end
                        time.sleep(.05)
                assert response.status_code in (200,503),response.text
                results.append(response)
        actual={p.pid for p in children}
        for response in results:
            if response.status_code==503:continue # Explicit unsupported topology is safe.
            census=response.json()
            seen={int(w.split(':')[0])for w in census['workers']}
            assert seen==actual,(seen,actual,census)
    finally:
        for process in children:
            if process.poll() is None:os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=3)
            try:os.killpg(process.pid,0)
            except ProcessLookupError:pass
            else:raise AssertionError('owned sibling web process group remains')
