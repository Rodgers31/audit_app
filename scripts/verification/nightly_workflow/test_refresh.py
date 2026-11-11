"""Run the strict client and direct boundary controls without remote traffic."""
import copy
import hashlib
import hmac
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import refresh as r

C = {'source_sha':'a'*40,'plan_sha256':'b'*64,'run_id':'1234','run_attempt':'1','schema_head':'a756b20a0001'}
CENSUS = {'scope':'container','instance':'d'*64,'supervisor':'1:100','workers':['2:200','3:300'],'worker':'2:200'}
MARKER = [123,456,32]


class Reply(io.BytesIO):
    status = 200
    def __init__(self, raw, signature):
        super().__init__(raw)
        self.headers = {'x-revalidate-response-signature':signature}


@pytest.mark.parametrize('bad', [None,'signature','request','source','attempt','plan','stale','boolean_at','duplicate_key'])
def test_signed_client_consumes_original_response_and_refuses_bad_identity(tmp_path,bad):
    client = r.SignedClient('inert',C,tmp_path/'evidence',now=lambda:1000)
    def open_(request, **kwargs):
        assert request.full_url == 'https://fixture.test/status'
        assert request.headers['X-revalidate-signature'] == hmac.new(b'inert',request.data,hashlib.sha256).hexdigest()
        value={'protocol':r.PROTOCOL,'context':dict(C),'request_sha256':hashlib.sha256(request.data).hexdigest(),'at':1000,'result':{'ok':True}}
        if bad=='request':value['request_sha256']='0'*64
        if bad in ('source','attempt','plan'):value['context'][{'source':'source_sha','attempt':'run_attempt','plan':'plan_sha256'}[bad]]='wrong'
        if bad=='stale':value['at']=1
        if bad=='boolean_at':value['at']=True
        raw=json.dumps(value).encode()
        if bad=='duplicate_key':raw=raw[:-1]+b',"at":1000}'
        signature=hmac.new(b'inert',raw,hashlib.sha256).hexdigest() if bad!='signature' else '0'*64
        return Reply(raw,signature)
    client.opener=SimpleNamespace(open=open_)
    if bad is None:assert client.post('https://fixture.test/status')=={'ok':True}
    else:
        with pytest.raises(ValueError):client.post('https://fixture.test/status')
    original=json.loads((tmp_path/'evidence').read_text())
    assert original['request_base64'] and original['response_base64']  # failure retains the consumed bytes


class PhaseClient:
    context=C
    def __init__(self,statuses):self.statuses=statuses;self.calls=[]
    def post(self,url,**payload):
        self.calls.append(url)
        if url.endswith('/invalidate'):
            return {'invalidated':True,'commit':C['source_sha'],'marker_identity':MARKER,'pid':2,'census':copy.deepcopy(CENSUS)}
        return copy.deepcopy(self.statuses.pop(0) if len(self.statuses)>1 else self.statuses[0])
    def now(self):return 1000
    def remaining(self):return 1


def status(worker='3:300'):
    return {'commit':C['source_sha'],'pid':int(worker.split(':')[0]),'census':dict(CENSUS,worker=worker),
            'synchronised':True,'observed_identity':MARKER,'adopted_identity':MARKER}


def test_every_censused_worker_precedes_page_invocation():
    client=PhaseClient([status('2:200'),status()])
    state=r.adopt_backend(client,'https://fixture.test',pause=lambda _:None)
    assert state['adopted_workers']==CENSUS['workers']
    def pages(url,**payload):return {'revalidated':['/'],'rejected':[],'backend_adoption_sha256':payload['backend_adoption_sha256']}
    client.post=pages
    r.revalidate_pages(client,state,'https://pages.test',['/'])


@pytest.mark.parametrize('bad',['missing','duplicate_census','changed_census','wrong_source','partial','boolean_marker','stale_generation','wrong_worker','false_sync'])
def test_backend_adoption_refusals_never_reach_pages(bad):
    value=status()
    if bad=='missing':value=status('2:200')
    if bad=='duplicate_census':value['census']['workers']=['2:200','2:200']
    if bad=='changed_census':value['census']['instance']='e'*64
    if bad=='wrong_source':value['commit']='e'*40
    if bad=='partial':value.pop('adopted_identity')
    if bad=='boolean_marker':value['adopted_identity']=[True,456,32]
    if bad=='stale_generation':value['adopted_identity']=[124,456,32]
    if bad=='wrong_worker':value['pid']=10
    if bad=='false_sync':value['synchronised']='true'
    client=PhaseClient([value])
    with pytest.raises(ValueError):r.adopt_backend(client,'https://fixture.test',pause=lambda _:None)
    assert len(client.calls)<=64 and all('/api/v1/system/cache/' in x for x in client.calls)


@pytest.mark.parametrize('bad',['stale','missing','wrong_context','duplicate_pages'])
def test_page_phase_refuses_incomplete_state_before_http(bad):
    client=PhaseClient([status('2:200'),status()]);state=r.adopt_backend(client,'https://fixture.test',pause=lambda _:None)
    client.calls.clear();paths=['/']
    if bad=='stale':state['at']=1
    if bad=='missing':state['adopted_workers']=['2:200']
    if bad=='wrong_context':state['context']={**C,'run_attempt':'2'}
    if bad=='duplicate_pages':paths=['/','/']
    with pytest.raises(ValueError):r.revalidate_pages(client,state,'https://pages.test',paths)
    assert client.calls==[]


def test_client_deadline_and_request_allowance_are_aggregate(tmp_path):
    now=[0]
    client=r.SignedClient('inert',C,tmp_path/'evidence',clock=lambda:now[0])
    client.requests=64
    with pytest.raises(ValueError,match='request allowance'):client.post('https://fixture.test/status')
    now[0]=91
    with pytest.raises(ValueError,match='deadline'):client.remaining()


def test_worker_inventory_leaves_one_request_for_invalidation():
    workers = sorted(f'{pid}:100' for pid in range(2, r.MAX_REQUESTS + 1))
    supported = dict(CENSUS, workers=workers, worker='2:100')
    assert r.census_key(supported)['workers'] == workers
    unsupported = dict(supported, workers=sorted([*workers, '65:100']))
    with pytest.raises(ValueError, match='worker inventory'):
        r.census_key(unsupported)


def test_cli_deadline_interrupts_a_blocking_socket_read():
    import signal
    import socket

    original = signal.getsignal(signal.SIGALRM)
    reader, writer = socket.socketpair()
    with reader, writer:
        # Keep a writer open without sending data, just as an incomplete
        # response header leaves urllib waiting for the next byte.
        reader.settimeout(1)
        with pytest.raises(ValueError, match='refresh deadline exceeded'):
            with r._phase_deadline(0.05):
                reader.recv(1)
    assert signal.getsignal(signal.SIGALRM) == original
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_public_log_seals_replayable_signatures_but_preserves_private_originals(tmp_path,capsys):
    import base64
    import os
    import subprocess
    secret='inert-log-secrecy-control'
    client=r.SignedClient(secret,C,tmp_path/'private.jsonl',now=lambda:1000)
    def open_(request,**kwargs):
        value={'protocol':r.PROTOCOL,'context':dict(C),'request_sha256':hashlib.sha256(request.data).hexdigest(),'at':1000,'result':{'ok':True}}
        raw=json.dumps(value).encode()
        return Reply(raw,hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest())
    client.opener=SimpleNamespace(open=open_)
    assert client.post('https://fixture.test/status')=={'ok':True}
    private=json.loads((tmp_path/'private.jsonl').read_text())
    public=capsys.readouterr().out
    assert private['request_signature'] not in public and private['response_signature'] not in public
    assert private['request_base64'] not in public and (tmp_path/'private.jsonl').stat().st_mode & 0o077==0
    envelope=json.loads(public.split('REFRESH_HTTP_EVIDENCE_V2 ',1)[1])
    child=subprocess.run(['node',str(Path(r.__file__).with_name('evidence.cjs')),'open'],
        input=json.dumps(envelope).encode(),capture_output=True,env={'PATH':os.environ['PATH'],'REVALIDATE_SECRET':secret},timeout=5)
    assert child.returncode==0,child.stderr
    assert child.stdout+b'\n'==(tmp_path/'private.jsonl').read_bytes()
    assert base64.b64decode(json.loads(child.stdout)['response_base64'],validate=True)


@pytest.mark.parametrize('mutation',['ciphertext','tag','nonce','hash','algorithm','extra','wrong_key'])
def test_authenticated_evidence_refuses_tampering_without_plaintext_output(tmp_path,mutation):
    import os
    import subprocess
    helper=str(Path(r.__file__).with_name('evidence.cjs'))
    environment={'PATH':os.environ['PATH'],'REVALIDATE_SECRET':'inert-sealed-evidence-key'}
    raw=b'private exact original request signature and response bytes'
    sealed=subprocess.run(['node',helper,'seal'],input=raw,capture_output=True,env=environment,timeout=5)
    assert sealed.returncode==0,sealed.stderr
    value=json.loads(sealed.stdout)
    if mutation in ('ciphertext','tag','nonce'):
        old=value[mutation];value[mutation]=('A' if old[0]!='A' else 'B')+old[1:]
    if mutation=='hash':value['plaintext_sha256']='0'*64
    if mutation=='algorithm':value['algorithm']='aes-128-cbc'
    if mutation=='extra':value['unknown']=True
    if mutation=='wrong_key':environment['REVALIDATE_SECRET']='other-inert-key'
    opened=subprocess.run(['node',helper,'open'],input=json.dumps(value).encode(),capture_output=True,env=environment,timeout=5)
    assert opened.returncode==1 and opened.stdout==b'' and raw not in opened.stderr


def test_evidence_helper_is_bounded_and_requires_explicit_secret(tmp_path):
    import os
    import subprocess
    helper=str(Path(r.__file__).with_name('evidence.cjs'))
    for raw,environment in [(b'',{'REVALIDATE_SECRET':'inert'}),(b'x'*131073,{'REVALIDATE_SECRET':'inert'}),(b'original',{})]:
        child=subprocess.run(['node',helper,'seal'],input=raw,capture_output=True,env={'PATH':os.environ['PATH'],**environment},timeout=5)
        assert child.returncode==1 and child.stdout==b''


@pytest.mark.parametrize('kind',['public_permissions','symlink','hardlink'])
def test_private_evidence_refuses_unsafe_files_before_any_append(tmp_path,capsys,kind):
    import os
    target=tmp_path/'original';target.write_bytes(b'unchanged original');target.chmod(0o600)
    path=tmp_path/'evidence'
    if kind=='symlink':path.symlink_to(target)
    elif kind=='hardlink':os.link(target,path)
    else:path.write_bytes(b'unchanged original');path.chmod(0o644)
    client=r.SignedClient('inert',C,path,now=lambda:1000)
    def open_(request,**kwargs):
        raw=json.dumps({'protocol':r.PROTOCOL,'context':C,'request_sha256':hashlib.sha256(request.data).hexdigest(),'at':1000,'result':{}}).encode()
        return Reply(raw,hmac.new(b'inert',raw,hashlib.sha256).hexdigest())
    client.opener=SimpleNamespace(open=open_)
    with pytest.raises((ValueError,OSError)):client.post('https://fixture.test/status')
    assert target.read_bytes()==b'unchanged original' and path.read_bytes()==b'unchanged original'
    assert capsys.readouterr().out==''


@pytest.mark.parametrize('operation',['append','digest'])
def test_private_evidence_refuses_symlinked_ancestors(tmp_path,capsys,operation):
    import os
    target=tmp_path/'original';target.mkdir()
    leaf=target/'evidence';leaf.write_bytes(b'unchanged original');leaf.chmod(0o600)
    link=tmp_path/'linked-parent';link.symlink_to(target,target_is_directory=True)
    path=link/'evidence'
    if operation=='digest':
        with pytest.raises(OSError):r.private_evidence_fd(path,os.O_RDONLY)
    else:
        client=r.SignedClient('inert',C,path,now=lambda:1000)
        def open_(request,**kwargs):
            raw=json.dumps({'protocol':r.PROTOCOL,'context':C,'request_sha256':hashlib.sha256(request.data).hexdigest(),'at':1000,'result':{}}).encode()
            return Reply(raw,hmac.new(b'inert',raw,hashlib.sha256).hexdigest())
        client.opener=SimpleNamespace(open=open_)
        with pytest.raises(OSError):client.post('https://fixture.test/status')
    assert leaf.read_bytes()==b'unchanged original'
    assert capsys.readouterr().out==''


def test_sealed_evidence_uses_fresh_nonce_and_does_not_load_ambient_node_options(tmp_path,monkeypatch):
    import os
    import subprocess
    preload=tmp_path/'preload.cjs';marker=tmp_path/'unexpected'
    preload.write_text("require('node:fs').writeFileSync("+json.dumps(str(marker))+",'unsafe preload');")
    monkeypatch.setenv('NODE_OPTIONS','--require '+str(preload))
    client=r.SignedClient('inert',C,tmp_path/'evidence',now=lambda:1000)
    def open_(request,**kwargs):
        raw=json.dumps({'protocol':r.PROTOCOL,'context':C,'request_sha256':hashlib.sha256(request.data).hexdigest(),'at':1000,'result':{}}).encode()
        return Reply(raw,hmac.new(b'inert',raw,hashlib.sha256).hexdigest())
    client.opener=SimpleNamespace(open=open_)
    client.post('https://fixture.test/status')
    assert not marker.exists()
    helper=str(Path(r.__file__).with_name('evidence.cjs'))
    env={'PATH':os.environ['PATH'],'REVALIDATE_SECRET':'inert'}
    a=subprocess.run(['node',helper,'seal'],input=b'original',capture_output=True,env=env,timeout=5)
    b=subprocess.run(['node',helper,'seal'],input=b'original',capture_output=True,env=env,timeout=5)
    assert a.returncode==b.returncode==0
    assert json.loads(a.stdout)['nonce']!=json.loads(b.stdout)['nonce']
    assert json.loads(a.stdout)['ciphertext']!=json.loads(b.stdout)['ciphertext']
