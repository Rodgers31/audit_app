"""Inert official-contract metrics; never opens a live provider connection."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import sys
from types import SimpleNamespace
from uuid import UUID, uuid4

from cryptography.fernet import Fernet
import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from social.connections.crypto import CredentialCipher
from social.contracts import ResolvedPostPayload, canonical_hash
from social.models import SocialAccount, SocialAuditEvent, SocialPostTarget
from social.platform_connections.models import PLATFORM_CONNECTION_TABLES, PlatformCredential
from social.service import SocialError
from social.studio.analytics import collect, observations
from social.studio.contracts import MetricRequest
from social.studio.models import MetricCollection
from social.studio.native_metrics import AnalyticsRuntime, CollectionCommand, capability_status, configured_runtime
from social.studio.platform_metrics import COUNTS, PlatformMetricsPort, RATE_HOLD, check_read_hold, parse_counts
from test_domain_support import db
from test_domain_support import account as make_account, ACTOR
from test_studio import source
from social.models import SocialPublication
from test_native_meta_adapters import payload as meta_payload


def platform_fixture(db, platform='threads'):
    account = make_account(db, platform)
    post = source(db)
    publication = SocialPublication(id=uuid4(), post_id=UUID(post['id']), revision_id=UUID(post['revision_id']),
        authorization_kind='human', approved_by=ACTOR, approved_at=datetime.now(timezone.utc), approved_hash='a'*64)
    db.add(publication)
    db.flush()
    for table in PLATFORM_CONNECTION_TABLES:
        table.create(db.bind, checkfirst=True)
    account.platform, account.api_product = platform, 'threads' if platform == 'threads' else 'tiktok_accounts_api'
    account.connection_method, account.credential_id, account.publishing_enabled = platform+'_oauth2', None, False
    account.external_account_id = '901' if platform == 'threads' else 'fixture-open-id'
    account.granted_scopes = ['threads_basic', 'threads_manage_insights'] if platform == 'threads' else ['video.list']
    data = meta_payload(account_id=account.id).model_dump(mode='json') | {'platform': platform, 'api_product': account.api_product,
        'external_account_id': account.external_account_id, 'format': 'text' if platform == 'threads' else 'video'}
    data['content_hash'] = canonical_hash({k:v for k,v in data.items() if k != 'content_hash'})
    payload = ResolvedPostPayload.model_validate(data)
    # Published payloads are immutable; fixtures insert a fresh exact target.
    owned = SocialPostTarget(id=uuid4(), publication_id=publication.id, account_id=account.id,
        resolved_payload=payload.model_dump(mode='json'), payload_hash=payload.content_hash,
        primary_remote_id='777', capability_version='v1.0' if platform == 'threads' else 'v1.3',
        state='published', visibility_state='public', published_at=datetime.now(timezone.utc), confirmation_kind='fixture')
    db.add(owned)
    cipher = CredentialCipher('fixture', {'fixture': Fernet.generate_key().decode()})
    expires = datetime.now(timezone.utc)+timedelta(days=1)
    cred = PlatformCredential(id=uuid4(), account_id=account.id, platform=platform, version=1,
        issued_at=datetime.now(timezone.utc)-timedelta(days=1), access_expires_at=expires)
    bundle = {'access_token': 'inert-metric-token', 'subject': account.external_account_id,
        'scopes': account.granted_scopes, 'expires_at': expires.isoformat()}
    if platform == 'tiktok':
        bundle['open_id'] = account.external_account_id
    cred.key_version, cred.encrypted_bundle = cipher.encrypt(cred.id, f'platform:{platform}:credential', bundle)
    db.add(cred)
    db.commit()
    runtime = AnalyticsRuntime(True, (platform,), True, True, cipher, authorized_native_accounts=(account.id,))
    cmd = CollectionCommand(account_id=account.id, credential_id=cred.id, credential_version=1,
        payload_hash=owned.payload_hash, remote_id='777', runtime_hash=runtime.fingerprint())
    return owned, runtime, cmd


def body(platform, value=0):
    return {'data':[{'name':'likes','id':'777/insights/likes/lifetime','period':'lifetime','values':[{'value':value}]}]} if platform == 'threads' else {'code':0, 'data':{'videos':[{'item_id':'777','media_type':'VIDEO','likes':value}], 'cursor':0, 'has_more':False}}


def port_request(platform):
    request = MetricRequest(platform=platform, account_id=uuid4(), target_id=uuid4(), remote_id='777', deadline=datetime.now(timezone.utc)+timedelta(seconds=10))
    return PlatformMetricsPort(platform, canonical_hash(request.model_dump(mode='json')), '901' if platform == 'threads' else 'fixture-open-id', 'inert-metric-token'), request


@pytest.mark.parametrize('platform', COUNTS)
def test_native_operator_storage_history_api_and_no_publish(db, monkeypatch, platform):
    from test_studio_api import client
    from social.studio.runtime import StudioRuntime
    target, runtime, command = platform_fixture(db, platform)
    calls = []
    def read(port, request):
        def wire(req):
            calls.append(req)
            return httpx.Response(200, json=body(platform))
        return asyncio.run(port._read(request, transport=httpx.MockTransport(wire)))
    monkeypatch.setattr('social.studio.analytics.bounded_collect', read)
    assert capability_status(db, runtime)[0] is True
    db.rollback()
    factory = sessionmaker(bind=db.bind)
    collection_id = collect(factory, target.id, runtime, enabled=True, authorization=command)
    assert len(calls) == 1
    req = calls[0]
    assert req.method == 'GET'
    assert 'access_token' not in req.url.params
    if platform == 'threads':
        assert req.url.host == 'graph.threads.com' and req.url.path == '/v1.0/777/insights'
        assert req.url.params['metric'] == ','.join(COUNTS[platform])
        assert req.headers['authorization'] == 'Bearer inert-metric-token'
    else:
        assert req.url.host == 'business-api.tiktok.com' and req.url.path == '/open_api/v1.3/business/video/list/'
        assert json.loads(req.url.params['filters']) == {'video_ids':['777']}
        assert req.url.params['business_id'] == 'fixture-open-id' and req.url.params['max_count'] == '1'
        assert json.loads(req.url.params['fields']) == ['item_id','media_type',*COUNTS[platform]]
        assert req.headers['access-token'] == 'inert-metric-token'
    with factory() as restarted:
        result = observations(restarted,target.id)
        assert result['collections'][0]['id'] == str(collection_id)
        assert sum(m['value'] == 0 for m in result['collections'][0]['metrics']) == 1
        assert sum(m['value'] is None for m in result['collections'][0]['metrics']) == 5
        assert restarted.get(SocialAccount,target.account_id).publishing_enabled is False
        reserved = restarted.scalar(select(SocialAuditEvent).where(SocialAuditEvent.action == 'metrics.reserved'))
        assert reserved.details['authorization'] == command.model_dump(mode='json')
    api = client(db,StudioRuntime())
    got = api.get('/api/v1/admin/social/studio/analytics/'+str(target.id))
    assert got.status_code == 200 and got.json()['platform'] == platform
    assert got.headers['cache-control'] == 'private, no-store'
    assert api.get('/api/v1/admin/social/studio/capabilities').json()['uploads_enabled'] is False
    with pytest.raises(SocialError,match='METRICS_QUOTA'):
        collect(factory,target.id,runtime,enabled=True,authorization=command)


@pytest.mark.parametrize('platform', COUNTS)
@pytest.mark.parametrize('mutation', ['generation','expiry','renewal','revoked','scope','product','remote','hash','runtime','account','parent','envelope','private','format'])
def test_admission_never_constructs_transport_on_wrong_binding(db, monkeypatch, platform, mutation):
    target, runtime, command = platform_fixture(db,platform)
    account = db.get(SocialAccount,target.account_id)
    cred = db.get(PlatformCredential,command.credential_id)
    if mutation == 'generation': command=command.model_copy(update={'credential_version':2})
    elif mutation == 'expiry': cred.access_expires_at=datetime.now(timezone.utc)
    elif mutation == 'renewal': cred.refresh_claim=uuid4()
    elif mutation == 'revoked': cred.revoked_at=datetime.now(timezone.utc)
    elif mutation == 'scope': account.granted_scopes=[]
    elif mutation == 'product': account.api_product='fixture'
    elif mutation == 'remote': command=command.model_copy(update={'remote_id':'778'})
    elif mutation == 'hash': command=command.model_copy(update={'payload_hash':'a'*64})
    elif mutation == 'runtime': command=command.model_copy(update={'runtime_hash':'b'*64})
    elif mutation == 'account': command=command.model_copy(update={'account_id':uuid4()})
    elif mutation == 'parent': command=command.model_copy(update={'parent_credential_id':uuid4()})
    elif mutation == 'envelope': cred.encrypted_bundle=b'invalid'
    elif mutation == 'private': target.state,target.visibility_state='outcome_unknown','private'
    elif mutation == 'format':
        from sqlalchemy import update
        data=target.resolved_payload | {'format':'reel'}
        data['content_hash']=canonical_hash({k:v for k,v in data.items() if k!='content_hash'})
        db.execute(update(SocialPostTarget).where(SocialPostTarget.id==target.id).values(resolved_payload=data,payload_hash=data['content_hash']))
        command=command.model_copy(update={'payload_hash':data['content_hash']})
    db.commit()
    calls=[]
    monkeypatch.setattr('social.studio.platform_metrics.httpx.AsyncHTTPTransport',lambda **_:calls.append(1))
    with pytest.raises(SocialError):
        collect(sessionmaker(bind=db.bind),target.id,runtime,enabled=True,authorization=command)
    assert calls == [] and db.scalar(select(MetricCollection)) is None


@pytest.mark.parametrize('platform',COUNTS)
@pytest.mark.parametrize('value',[True,False,-1,2**53,float('nan'),float('inf'),'0',{},[]])
def test_scalar_hostile_set(platform,value):
    raw=body(platform,value)
    if platform=='tiktok': raw=raw['data']
    with pytest.raises(ValueError): parse_counts(raw,platform,'777',datetime.now(timezone.utc))


@pytest.mark.parametrize('platform',COUNTS)
@pytest.mark.parametrize('value',[None,{},[],{'data':{}},'bad'])
def test_outer_shapes(platform,value):
    with pytest.raises(ValueError):parse_counts(value,platform,'777',datetime.now(timezone.utc))


@pytest.mark.parametrize('platform',COUNTS)
def test_null_and_omitted_are_not_zero(platform):
    raw=body(platform,None)
    values=parse_counts(raw if platform=='threads' else raw['data'],platform,'777',datetime.now(timezone.utc))
    assert all(m.value is None and m.status=='unavailable' for m in values)


@pytest.mark.parametrize('platform',COUNTS)
@pytest.mark.parametrize('mode',['redirect','oversize','compressed','duplicate','status','rate','bad-rate'])
def test_wire_bounds_no_retry_redaction(platform,mode):
    port,req=port_request(platform)
    calls=[]
    def wire(request):
        calls.append(request)
        if mode=='redirect':return httpx.Response(302,headers={'location':'https://example.org/secret'})
        if mode=='oversize':return httpx.Response(200,content=b'x'*32769)
        if mode=='compressed':return httpx.Response(200,headers={'Content-Encoding':'gzip'},content=b'garbage')
        if mode=='duplicate':return httpx.Response(200,content=b'{"data":{},"data":{}}')
        if mode=='status':return httpx.Response(503,json={'error':{'code':1},'code':1})
        return httpx.Response(429,headers={'Retry-After':'7200' if mode=='rate' else 'garbage'},json={'error':{'code':4},'code':4})
    if mode in {'rate','bad-rate'}:
        metrics=asyncio.run(port._read(req,transport=httpx.MockTransport(wire)))
        assert all(m.status=='unavailable' for m in metrics)
        assert ('retry after' in metrics[0].reason) if mode=='rate' else metrics[0].reason==RATE_HOLD
    else:
        with pytest.raises(ValueError) as exc:asyncio.run(port._read(req,transport=httpx.MockTransport(wire)))
        assert exc.value.__context__ is None and 'inert-metric-token' not in str(exc.value)
    assert len(calls)==1


@pytest.mark.parametrize('platform',COUNTS)
def test_retry_after_durable_restart_and_account_wide_hold(db,monkeypatch,platform):
    target,runtime,command=platform_fixture(db,platform)
    def read(port,req):
        return asyncio.run(port._read(req,transport=httpx.MockTransport(lambda _:httpx.Response(429,headers={'retry-after':'7200'},json={'error':{'code':4},'code':4}))))
    monkeypatch.setattr('social.studio.analytics.bounded_collect',read)
    factory=sessionmaker(bind=db.bind)
    ident=collect(factory,target.id,runtime,enabled=True,authorization=command)
    with factory() as restarted, restarted.begin():
        row=restarted.get(MetricCollection,ident)
        assert row.state=='unavailable' and 'retry after' in row.reason
        # Clock-independent replay: ordinary hourly quota has expired, provider delay has not.
        row.created_at=datetime.now(timezone.utc)-timedelta(hours=2)
    monkeypatch.setattr('social.studio.analytics.bounded_collect',lambda *_:pytest.fail('must not retry'))
    with pytest.raises(SocialError,match='METRICS_RATE_LIMITED'):
        collect(factory,target.id,runtime,enabled=True,authorization=command)


@pytest.mark.parametrize('platform',COUNTS)
def test_revalidate_generation_after_wire(db,monkeypatch,platform):
    target,runtime,command=platform_fixture(db,platform)
    factory=sessionmaker(bind=db.bind)
    def read(port,req):
        with factory() as other,other.begin():other.get(PlatformCredential,command.credential_id).version+=1
        raw=body(platform)
        return parse_counts(raw if platform=='threads' else raw['data'],platform,'777',datetime.now(timezone.utc))
    monkeypatch.setattr('social.studio.analytics.bounded_collect',read)
    with pytest.raises(SocialError,match='METRICS_AUTHORIZATION_CHANGED'):collect(factory,target.id,runtime,enabled=True,authorization=command)
    with factory() as restarted:
        result=observations(restarted,target.id)
        assert result['collections'][0]['state']=='failed' and result['collections'][0]['metrics']==[]


def test_default_off_exact_account_and_x_no_port(db,monkeypatch):
    assert configured_runtime({}).enabled is False
    with pytest.raises(ValueError):AnalyticsRuntime(True,('x',),True,True)
    target,runtime,command=platform_fixture(db)
    with pytest.raises(ValueError):replace(runtime,authorized_native_accounts=())
    other=replace(runtime,authorized_native_accounts=(uuid4(),))
    with pytest.raises(SocialError):other.material(db,target,command.model_copy(update={'runtime_hash':other.fingerprint()}))
    acc=db.get(SocialAccount,target.account_id);acc.platform='x';db.commit()
    monkeypatch.setattr('social.studio.platform_metrics.httpx.AsyncHTTPTransport',lambda **_:pytest.fail('X must deny before transport'))
    with pytest.raises(SocialError,match='METRICS_UNAVAILABLE'):collect(sessionmaker(bind=db.bind),target.id,runtime,enabled=True,authorization=command)


def test_future_threads_insights_scope_is_explicit_and_never_implicit():
    from social.platform_connections.config import ConnectionConfig
    from social.platform_connections.provider import OAuthProvider
    from test_platform_connections import config, REDIRECT
    assert ConnectionConfig('threads').scopes == ('threads_basic','threads_content_publish')
    selected=replace(config('threads'),threads_insights_enabled=True)
    provider=OAuthProvider(selected,transport=httpx.MockTransport(lambda _:pytest.fail('authorization URL is local only')))
    try:
        from urllib.parse import parse_qs,urlsplit
        query=parse_qs(urlsplit(provider.authorize_url('fixture-state',REDIRECT,'fixture-verifier')).query)
        assert query['scope']==['threads_basic,threads_content_publish,threads_manage_insights']
    finally:provider.close()
    assert 'INSIGHTS_CONFIGURATION_INVALID' in replace(config('threads'),threads_insights_enabled=1).blockers()


@pytest.mark.parametrize('platform',COUNTS)
@pytest.mark.parametrize('mode',['success','oversize','delayed','compressed','rate'])
def test_actual_local_http_bounds(platform,mode):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from threading import Thread
    import time
    from test_native_analytics import LocalForward
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_GET(self):
            calls.append(self.path)
            if mode=='delayed':time.sleep(.3)
            self.send_response(429 if mode=='rate' else 200)
            if mode=='rate':self.send_header('Retry-After','7200')
            if mode=='compressed':self.send_header('Content-Encoding','gzip')
            self.end_headers()
            raw={'error':{'code':4},'code':4} if mode=='rate' else body(platform)
            try:self.wfile.write(b'x'*32769 if mode=='oversize' else json.dumps(raw).encode())
            except (BrokenPipeError,ConnectionResetError):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    port,req=port_request(platform)
    if mode=='delayed':
        req=req.model_copy(update={'deadline':datetime.now(timezone.utc)+timedelta(seconds=.1)})
        port=replace(port,request_hash=canonical_hash(req.model_dump(mode='json')))
    try:
        if mode in {'success','rate'}:
            values=asyncio.run(port._read(req,transport=LocalForward(server.server_port)))
            assert len(values)==6
            if mode=='rate':assert all(m.status=='unavailable' and 'retry after' in m.reason for m in values)
        else:
            with pytest.raises(ValueError):asyncio.run(port._read(req,transport=LocalForward(server.server_port)))
        assert len(calls)==1
    finally:
        server.shutdown();server.server_close();thread.join(2)
        assert not thread.is_alive()


from dataclasses import dataclass
@dataclass(frozen=True)
class LocalPlatformProcessPort(PlatformMetricsPort):
    local_port:int=0
    async def _read(self,request,**_):
        from test_native_analytics import LocalForward
        return await super()._read(request,transport=LocalForward(self.local_port))


@pytest.mark.parametrize('platform',COUNTS)
def test_real_spawned_native_transport_operator(db,monkeypatch,platform):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from threading import Thread
    from social.studio.analytics import bounded_collect
    target,runtime,cmd=platform_fixture(db,platform)
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_GET(self):
            calls.append(self.path);self.send_response(200);self.end_headers();self.wfile.write(json.dumps(body(platform)).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    def local(port,req):
        return bounded_collect(LocalPlatformProcessPort(port.platform,port.request_hash,port.external_account_id,port.access_token,local_port=server.server_port),req)
    monkeypatch.setattr('social.studio.analytics.bounded_collect',local)
    try:
        collect(sessionmaker(bind=db.bind),target.id,runtime,enabled=True,authorization=cmd)
        assert len(calls)==1
    finally:
        server.shutdown();server.server_close();thread.join(2)
        assert not thread.is_alive()


# Regressions reproduced by the independent Spec review before repair.
def wire_read(monkeypatch, response):
    calls = []
    def read(port, request):
        def wire(req):
            calls.append(req)
            return response()
        return asyncio.run(port._read(request, transport=httpx.MockTransport(wire)))
    monkeypatch.setattr('social.studio.analytics.bounded_collect', read)
    return calls


def likes():
    return httpx.Response(200, json={'data':[{'name':'likes', 'id':'777/insights/likes/lifetime', 'period':'lifetime', 'values':[{'value':2}]}]})


def test_backdated_durable_quota_reservation_must_refuse_before_dispatch(db,monkeypatch):
    target,runtime,command=platform_fixture(db)
    db.execute(text("CREATE TRIGGER spec_backdate AFTER INSERT ON social_metric_collections BEGIN UPDATE social_metric_collections SET created_at='2000-01-01 00:00:00' WHERE id=NEW.id; END"))
    db.commit()
    calls=wire_read(monkeypatch,likes)
    factory=sessionmaker(bind=db.bind)
    try:
        collect(factory,target.id,runtime,enabled=True,authorization=command)
        collect(factory,target.id,runtime,enabled=True,authorization=command)
    except SocialError as error:
        assert error.code=='METRICS_PERSISTENCE_FAILED'
    assert calls==[], f'Unverified reservation timestamp permitted {len(calls)} provider reads within one hour'


@pytest.mark.parametrize('response_kind',['missing_error','string_error_code','invalid_json'])
def test_threads_http429_retains_server_backoff_even_with_unparseable_error(db,monkeypatch,response_kind):
    target,runtime,command=platform_fixture(db)
    def limited():
        content = b'{}' if response_kind=='missing_error' else b'{"error":{"code":"4"}}' if response_kind=='string_error_code' else b'not json'
        return httpx.Response(429,headers={'Retry-After':'7200'},content=content)
    calls=wire_read(monkeypatch,limited)
    factory=sessionmaker(bind=db.bind)
    try:
        ident=collect(factory,target.id,runtime,enabled=True,authorization=command)
    except SocialError:
        with factory() as restarted:
            ident=restarted.scalar(select(MetricCollection.id))
    with factory() as restarted,restarted.begin():
        row=restarted.get(MetricCollection,ident)
        row.created_at=datetime.now(timezone.utc)-timedelta(hours=2)
    calls_after=wire_read(monkeypatch,likes)
    with pytest.raises(SocialError,match='METRICS_RATE_LIMITED'):
        collect(factory,target.id,runtime,enabled=True,authorization=command)
    assert len(calls)==1 and calls_after==[]


def test_operator_reports_unavailable_collection_truthfully(db,monkeypatch,tmp_path,capsys):
    import social_metrics
    target,runtime,command=platform_fixture(db)
    auth=tmp_path/'command.json';auth.write_text(command.model_dump_json())
    monkeypatch.setattr(social_metrics,'configured_runtime',lambda:runtime)
    monkeypatch.setitem(sys.modules,'database',SimpleNamespace(SessionLocal=sessionmaker(bind=db.bind)))
    wire_read(monkeypatch,lambda:httpx.Response(200,json={'data':[]}))
    code=social_metrics.main([str(target.id),'--authorization',str(auth),'--enable-native-collection'])
    printed=json.loads(capsys.readouterr().out)
    assert code==0
    with sessionmaker(bind=db.bind)() as restarted:
        stored=restarted.get(MetricCollection,__import__('uuid').UUID(printed['collection_id']))
        assert printed['state']==stored.state, f'CLI says {printed["state"]}; durable state is {stored.state}'
