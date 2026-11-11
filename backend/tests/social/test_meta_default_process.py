"""Mounted public API -> actual owned product child -> real isolated PG.

Fixture substitutes config, authenticated AdminUser and database dependency only;
public verification_service/admin_session/delegate remain actual implementation.
Only Graph HTTP transport is intercepted inside the trusted fixture child.
An unassigned PG target skips; an assigned non-fixture target fails. Qualified
release profiles must assign the exact owned target and execute all27PGcases
without skips; a default no-PG suite is not runtime acceptance.
"""
import asyncio,copy,json,os,shutil,subprocess,sys,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID,uuid4
import httpx,pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select,text
from sqlalchemy.orm import Session,sessionmaker
from cryptography.fernet import Fernet
from social.models import Base,SocialAccount,SocialAuditEvent,SocialCommandReceipt,SocialControls
from social.connections.models import CONNECTION_TABLES
from social.privacy.models import PRIVACY_TABLES,SocialPrivacyReceipt
from social.connections.config import MetaConfig
from social.connections import api
from social.connections import verification_execution as execution
from social.connections.verification_protocol import encode
from social.connections.crypto import CredentialCipher
from social.connections.service import ConnectionService
from social.connections.provider import MetaProvider
from social.privacy.ownership import OwnershipRecorder
from social.privacy.subjects import SubjectDigester
from social.privacy.runtime import PrivacyRegistration
from social.privacy.service import PrivacyConfig
from social.worker.native_runtime import NativeRegistration
from social.adapters import FacebookPageAdapter,InstagramFacebookLoginAdapter,MetaAdapterConfig
from social.http_boundary import require_admin
from supabase_auth import AdminUser
from middleware.request_resources import request_deadline
from test_connections_support import FakeGraph,svc,start,complete,select_asset,ACTOR,SESSION,REDIRECT
from test_existing_grant_verification import body_for
ROOT=ENTRY=None
PRODUCTION_ENTRY=execution.ENTRYPOINT
DSN=os.environ.get('SOCIAL_META_PROCESS_TEST_DATABASE_URL')

@pytest.fixture
def harness(monkeypatch,tmp_path):
    global ROOT,ENTRY
    if sys.platform != 'linux':
        pytest.skip('The owned verification process requires Linux lifecycle guards')
    from sqlalchemy.engine import make_url
    if not DSN:
        pytest.skip('An explicitly assigned isolated SOCIAL_META_PROCESS_TEST_DATABASE_URL is required')
    url=make_url(DSN)
    if url.drivername!='postgresql+psycopg2' or url.host!='127.0.0.1' or url.database!='social_worker_test' or dict(url.query)!={'sslmode':'disable'}:
        pytest.fail('Only literal127.0.0.1 ssl-disabled owned social_worker_test fixture is permitted')
    ROOT=tmp_path/'state';ROOT.mkdir()
    entry_dir=tmp_path/'trusted'/'entries';entry_dir.mkdir(parents=True)
    for name in ('graph_entry.py','commit_delay_entry.py'):
        shutil.copyfile(Path(__file__).with_name('meta_process_fixture')/name,entry_dir/name)
    backend=Path(api.__file__).resolve().parents[2]
    bootstrap={'backend':str(backend),'social_tests':str(backend/'tests/social'),'pytest_tool_root':str(Path(pytest.__file__).resolve().parents[1]),'fixture_root':str(ROOT)}
    (entry_dir/'bootstrap.json').write_text(json.dumps(bootstrap))
    ENTRY=entry_dir/'graph_entry.py'
    for p in ROOT.iterdir():p.unlink()
    (ROOT/'mode.json').write_text(json.dumps({'mode':'normal'}))
    engine=create_engine(DSN,pool_size=3,max_overflow=0)
    with engine.begin()as conn:
        conn.execute(text('DROP SCHEMA public CASCADE'));conn.execute(text('CREATE SCHEMA public'))
    Base.metadata.create_all(engine)
    config=MetaConfig(enabled=True,app_configuration_validated=True,app_id='123',app_secret='fake-app-secret',redirect_uris=(REDIRECT,),verified_callback_ingress_uris=(REDIRECT,),access_mode='owned_standard',active_key_version='v1',encryption_keys={'v1':Fernet.generate_key().decode()})
    with Session(engine,expire_on_commit=False)as db:
        bootstrap=ConnectionService(db,config,provider_factory=lambda c:MetaProvider(c,transport=httpx.MockTransport(FakeGraph())),ownership_recorder=OwnershipRecorder(config.app_id,SubjectDigester('v1',{'v1':b'x'*32,'v2':b'y'*32})))
        flow,state=start(bootstrap);complete(bootstrap,state);select_asset(bootstrap,UUID(flow['flow_id']))
        ids={a.platform:a.id for a in db.scalars(select(SocialAccount))};db.rollback()
    app=FastAPI();app.include_router(api.router)
    factory=sessionmaker(engine,expire_on_commit=False)
    def getdb():
        with factory()as db:yield db
    app.dependency_overrides[api.get_db]=getdb
    # Actual admin_session converts this existing authenticated session identity.
    app.dependency_overrides[require_admin]=lambda:AdminUser(id=str(ACTOR),email=None,roles=['admin'],session_id=str(SESSION))
    monkeypatch.setattr(api,'load_config',lambda:config)
    cfg=MetaAdapterConfig('v26.0',enabled=True,operational_gates_verified=True,app_secret=config.app_secret)
    def denied(request):raise RuntimeError('parent delivery port denied')
    adapters={('facebook','facebook_pages'):FacebookPageAdapter(cfg,transport=httpx.MockTransport(denied)),('instagram','instagram_graph_facebook_login'):InstagramFacebookLoginAdapter(cfg,transport=httpx.MockTransport(denied))}
    app.state.social_native_registration=NativeRegistration(adapters,None,None)
    digester=SubjectDigester('v2',{'v1':b'x'*32,'v2':b'y'*32})
    from social.privacy.api import STATUS_PATH
    app.state.social_privacy_registration=PrivacyRegistration(PrivacyConfig('123',config.app_secret,'https://admin.example.test'+STATUS_PATH),digester,CredentialCipher(config.active_key_version,config.encryption_keys),factory)
    h=SimpleNamespace(engine=engine,config=config,ids=ids,app=app,root=ROOT,seconds=None,children=[],digester=digester,commit_entry=entry_dir/'commit_delay_entry.py')
    @app.middleware('http')
    async def deadline(request,call_next):
        token=request_deadline.set(time.monotonic()+h.seconds if h.seconds else None)
        try:return await call_next(request)
        finally:request_deadline.reset(token)
    from contextvars import ContextVar
    active_headers=ContextVar('fixture_lifecycle_headers',default=None)
    real_run_child=execution.run_child
    h.payload_headers=[]
    def checked_run_child(payload,deadline):
        assert payload['owner_pid']==os.getpid() and payload['deadline']==deadline
        expected=(str(payload['owner_pid']),repr(payload['deadline']))
        h.payload_headers.append(expected)
        token=active_headers.set(expected)
        try:return real_run_child(payload,deadline)
        finally:active_headers.reset(token)
    monkeypatch.setattr(execution,'run_child',checked_run_child)
    realpopen=execution.subprocess.Popen
    def popen(command,**kwargs):
        expected=active_headers.get()
        headers=(kwargs['env'].get('AUDITGAVA_META_OWNER_PID'),kwargs['env'].get('AUDITGAVA_META_DEADLINE'))
        if expected is not None:assert headers==expected and headers[0]==str(os.getpid())
        h.children.append({'command':list(command),'keys':sorted(kwargs['env']),'cwd':kwargs.get('cwd'),'lifecycle_matched':expected is not None and headers==expected})
        p=realpopen(command,**kwargs);h.children[-1]['pid']=p.pid;h.children[-1]['process']=p
        return p
    monkeypatch.setattr(execution.subprocess,'Popen',popen)
    monkeypatch.setattr(execution,'ENTRYPOINT',ENTRY)
    with TestClient(app,raise_server_exceptions=False)as client:
        h.client=client;yield h
    for child in h.children:
        if 'process'in child:
            assert child['process'].poll() is not None
            with pytest.raises(ProcessLookupError):os.kill(child['pid'],0)
    for adapter in adapters.values():asyncio.run(adapter.close())
    engine.dispose()

def status(h,platform):
    with Session(h.engine,expire_on_commit=False)as db:
        from social.connections.service import ConnectionService
        row=db.get(SocialAccount,h.ids[platform]);return body_for(ConnectionService(db,h.config),row)

def call(h,platform='facebook',body=None,key=None):
    account=h.ids[platform]
    return h.client.post(f'/api/v1/admin/social/accounts/{account}/verify-publishing-access',json=body or status(h,platform),headers={'Idempotency-Key':str(key or uuid4())})

def graph(h):return [json.loads(l)for l in (h.root/'graph.jsonl').read_text().splitlines()] if(h.root/'graph.jsonl').exists()else []

def saved(h):
    with Session(h.engine)as db:
        controls=db.get(SocialControls,1)
        accounts=[{'id':a.id,'platform':a.platform,'paused':not a.publishing_enabled,'proof':copy.deepcopy(a.capability_snapshot)}for a in db.scalars(select(SocialAccount))]
        audits=list(db.scalars(select(SocialAuditEvent).where(SocialAuditEvent.action=='connection.publishing_access_verified')))
        receipts=list(db.scalars(select(SocialCommandReceipt).where(SocialCommandReceipt.route_key.like('%verify-publishing-access'))))
        return {'version':controls.version,'publishing':controls.publishing_enabled,'accounts':accounts,'audits':len(audits),'receipts':len(receipts)}

@pytest.mark.parametrize('platform',['facebook','instagram'])
def test_default_mounted_native_real_child_commit_and_exact_replay(harness,platform):
    h=harness;body=status(h,platform);key=uuid4();before=saved(h)
    response=call(h,platform,body,key)
    assert response.status_code==200,response.text
    value=response.json();assert value['publishing_enabled']is False and value['enable_available']is True
    observed=graph(h);assert observed and all(r['method']=='GET'for r in observed)
    assert all(r['pid']!=os.getpid()and r['optimize']==sys.flags.optimize for r in observed)
    assert all(c['command'][1:3]==['-I','-B']and c['command'][-1]==str(ENTRY)for c in h.children)
    assert all(c['keys']==['AUDITGAVA_META_DEADLINE','AUDITGAVA_META_OWNER_PID','LANG','PATH','PYTHON_DOTENV_DISABLED']for c in h.children)
    assert all(c['lifecycle_matched']for c in h.children)
    state=saved(h);assert state['audits']==state['receipts']==1 and state['version']==before['version']+1
    assert state['publishing']is False and all(a['paused']for a in state['accounts'])
    count=len(observed);second=call(h,platform,body,key)
    assert second.status_code==200 and second.json()==value
    assert len(graph(h))==count and saved(h)==state
    bad=call(h,platform,{**body,'reason':'Changed command'},key)
    assert bad.status_code==409 and len(graph(h))==count
    h.app.dependency_overrides[require_admin]=lambda:AdminUser(id=str(ACTOR),email=None,roles=['admin'],session_id=str(uuid4()))
    rebound=call(h,platform,body,key)
    assert rebound.status_code==409 and len(graph(h))==count


def test_default_restricted_registry_keeps_both_accounts_paused(harness):
    h=harness;h.app.state.social_native_registration=NativeRegistration({},None,None)
    response=call(h)
    assert response.status_code==200,response.text
    assert response.json()['enable_available']is False
    state=saved(h);assert state['audits']==state['receipts']==1
    assert all(a['paused']for a in state['accounts'])


def test_default_child_reconstructs_historical_privacy_keyring_and_refuses_matching_receipt(harness):
    h=harness
    with Session(h.engine)as db:
        audit=db.scalar(select(SocialAuditEvent.id).limit(1))
        db.add(SocialPrivacyReceipt(app_id='123',kind='deauthorization',digest_version='v1',subject_digest=h.digester.digest('123','701','v1'),event_key='c'*64,request_fingerprint='d'*64,affected={},resolution='fixture_pending',state='ownership_unresolved',audit_id=audit));db.commit()
    response=call(h)
    assert response.status_code==503 and response.json()['detail']['code']=='PRIVACY_GRANT_BLOCKED',response.text
    assert not graph(h)and saved(h)['receipts']==0

@pytest.mark.parametrize('change',['controls','sibling'])
def test_default_real_child_concurrent_commit_during_graph_is_fenced(harness,change):
    h=harness;(h.root/'mode.json').write_text(json.dumps({'mode':'gate'}));body=status(h,'facebook')
    with ThreadPoolExecutor(max_workers=1)as pool:
        future=pool.submit(call,h,'facebook',body)
        deadline=time.monotonic()+8
        while not(h.root/'gate-seen').exists()and time.monotonic()<deadline:time.sleep(.01)
        assert(h.root/'gate-seen').exists(),'actual child did not reach Graph'
        with Session(h.engine)as other:
            if change=='controls':other.get(SocialControls,1).version+=1
            else:other.get(SocialAccount,h.ids['instagram']).publishing_enabled=True
            other.commit()
        (h.root/'gate-release').write_text('release')
        response=future.result(timeout=8)
    assert response.status_code in [409,503],response.text
    assert saved(h)['audits']==saved(h)['receipts']==0

@pytest.mark.parametrize('corruption',['proof','audit'])
def test_default_real_child_receipt_trigger_corruption_rolls_back(harness,corruption):
    h=harness
    statement=("UPDATE social_accounts SET capability_snapshot='{}'::json WHERE id='"+str(h.ids['facebook'])+"';")if corruption=='proof'else"DELETE FROM social_audit_events WHERE action='connection.publishing_access_verified';"
    with h.engine.begin()as db:
        db.execute(text("CREATE FUNCTION corrupt_verification() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.route_key LIKE '%verify-publishing-access' THEN "+statement+" END IF; RETURN NEW; END $$"))
        db.execute(text('CREATE TRIGGER receipt_corruption AFTER INSERT ON social_command_receipts FOR EACH ROW EXECUTE FUNCTION corrupt_verification()'))
    before=saved(h);response=call(h)
    assert response.status_code==503 and response.json()['detail']['code']=='ACCOUNT_CONTROL_FAILED',response.text
    assert saved(h)==before


def test_default_child_sql_timeout_does_not_claim_confirmed_no_effect(harness):
    h=harness
    with h.engine.begin()as db:
        db.execute(text("CREATE FUNCTION sleep_verification() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.route_key LIKE '%verify-publishing-access' THEN PERFORM pg_sleep(4); END IF; RETURN NEW; END $$"))
        db.execute(text('CREATE TRIGGER receipt_delay BEFORE INSERT ON social_command_receipts FOR EACH ROW EXECUTE FUNCTION sleep_verification()'))
    before=saved(h);started=time.monotonic();response=call(h);elapsed=time.monotonic()-started
    assert response.status_code==503 and response.json()['detail']['code']=='GRANT_VERIFICATION_UNCONFIRMED',response.text
    assert elapsed<8 and graph(h)
    assert saved(h)==before


def test_default_child_headers_timeout_positive_reap_retains_original_command_key(harness):
    h=harness;h.seconds=4;(h.root/'mode.json').write_text(json.dumps({'mode':'headers_delay'}));body=status(h,'facebook');key=uuid4()
    response=call(h,'facebook',body,key)
    assert response.status_code==503 and response.json()['detail']['code']=='GRANT_VERIFICATION_UNCONFIRMED',response.text
    assert graph(h),'timeout must occur inside real Graph phase'
    assert saved(h)['receipts']==0
    (h.root/'mode.json').write_text(json.dumps({'mode':'normal'}));h.seconds=None
    replay=call(h,'facebook',body,key)
    assert replay.status_code==200,replay.text
    assert saved(h)['audits']==saved(h)['receipts']==1


def test_committed_receipt_with_delayed_owned_exit_is_unknown_then_same_key_replays(harness,monkeypatch):
    h=harness;h.seconds=4;monkeypatch.setattr(execution,'ENTRYPOINT',h.commit_entry)
    body=status(h,'facebook');key=uuid4();response=call(h,'facebook',body,key)
    assert response.status_code==503 and response.json()['detail']['code']=='GRANT_VERIFICATION_UNCONFIRMED',response.text
    state=saved(h);assert state['audits']==state['receipts']==1,'must actually commit before timeout'
    count=len(graph(h));h.seconds=None;monkeypatch.setattr(execution,'ENTRYPOINT',ENTRY)
    replay=call(h,'facebook',body,key)
    assert replay.status_code==200,replay.text
    assert len(graph(h))==count and saved(h)==state


def test_public_api_selects_fixed_production_entrypoint_and_I_before_spawn(harness,monkeypatch):
    h=harness;monkeypatch.setattr(execution,'ENTRYPOINT',PRODUCTION_ENTRY);seen=[]
    def refused(command,**kwargs):
        seen.append((command,kwargs));raise OSError('inert spawn refusal')
    monkeypatch.setattr(execution.subprocess,'Popen',refused)
    response=call(h)
    assert response.status_code==503 and seen
    argv,options=seen[0]
    assert argv[-1]==str(PRODUCTION_ENTRY)and argv[1:3]==['-I','-B']
    assert options['stderr']==subprocess.DEVNULL and options['start_new_session']is True
    assert sorted(options['env'])==['AUDITGAVA_META_DEADLINE','AUDITGAVA_META_OWNER_PID','LANG','PATH','PYTHON_DOTENV_DISABLED']
    assert (options['env']['AUDITGAVA_META_OWNER_PID'],options['env']['AUDITGAVA_META_DEADLINE'])==h.payload_headers[-1]
    assert not graph(h)and saved(h)['receipts']==0

@pytest.mark.parametrize('bad',[{}, {'version':True}])
def test_actual_fixed_isolated_script_rejects_bad_protocol_without_io(harness,bad):
    h=harness;before=saved(h)
    run=actual_script(bad)
    assert run.returncode==2 and run.stdout==b'' and run.stderr==b''
    assert not graph(h)and saved(h)==before


@pytest.mark.parametrize('old_key_present',[True,False])
def test_actual_historical_key_is_required_for_unrelated_retained_privacy_receipt(harness,old_key_present):
    h=harness
    with Session(h.engine)as db:
        audit=db.scalar(select(SocialAuditEvent.id).limit(1))
        db.add(SocialPrivacyReceipt(app_id='123',kind='deauthorization',digest_version='v1',subject_digest=h.digester.digest('123','777','v1'),event_key='e'*64,request_fingerprint='f'*64,affected={},resolution='fixture_pending',state='ownership_unresolved',audit_id=audit));db.commit()
    if not old_key_present:
        old=h.app.state.social_privacy_registration
        h.app.state.social_privacy_registration=PrivacyRegistration(old.config,SubjectDigester('v2',{'v2':b'y'*32}),old.cipher,old.session_factory)
    response=call(h)
    if old_key_present:
        assert response.status_code==200,response.text
        assert saved(h)['receipts']==1 and graph(h)
    else:
        assert response.status_code==409 and response.json()['detail']['code']=='PRIVACY_GRANT_BLOCKED',response.text
        assert saved(h)['receipts']==0 and not graph(h)


def test_body_phase_whole_deadline_kills_actual_owned_child_without_automatic_retry(harness):
    h=harness;h.seconds=4;(h.root/'mode.json').write_text(json.dumps({'mode':'body_delay'}))
    response=call(h)
    assert response.status_code==503 and response.json()['detail']['code']=='GRANT_VERIFICATION_UNCONFIRMED',response.text
    assert (h.root/'body-started').exists() and len(h.children)==1 and len(graph(h))==1
    assert saved(h)['receipts']==0
    assert h.children[0]['process'].poll() is not None


def test_one_slot_admission_refuses_second_public_request_without_spawning(harness):
    h=harness;(h.root/'mode.json').write_text(json.dumps({'mode':'gate'}));body=status(h,'facebook')
    with ThreadPoolExecutor(max_workers=1)as pool:
        first=pool.submit(call,h,'facebook',body)
        deadline=time.monotonic()+8
        while not(h.root/'gate-seen').exists()and time.monotonic()<deadline:time.sleep(.01)
        assert(h.root/'gate-seen').exists()
        denied=call(h,'facebook',body)
        assert denied.status_code==503 and denied.json()['detail']['code']=='GRANT_VERIFICATION_UNAVAILABLE',denied.text
        assert len(h.children)==1
        (h.root/'gate-release').write_text('release')
        assert first.result(timeout=8).status_code==200
    assert saved(h)['audits']==saved(h)['receipts']==1


def recorded_payload(h,monkeypatch):
    saved=[];original=execution.run_child
    def capture(payload,deadline):
        saved.append(copy.deepcopy(payload));return original(payload,deadline)
    monkeypatch.setattr(execution,'run_child',capture)
    response=call(h)
    assert response.status_code==200,response.text
    assert len(saved)==1
    payload=saved[0];payload['deadline']=time.monotonic()+15;payload['nonce']='a'*64
    return payload


def actual_script(payload):
    # Qualified nonsecret startup headers reach main's protocol validation.
    # The valid replay control below proves this launch path can succeed.
    environment={'PATH':'/usr/local/bin:/usr/bin:/bin','LANG':'C.UTF-8','PYTHON_DOTENV_DISABLED':'1',
        'AUDITGAVA_META_OWNER_PID':str(os.getpid()),
        'AUDITGAVA_META_DEADLINE':repr(payload.get('deadline',time.monotonic()+15))}
    return subprocess.run([sys.executable,'-I','-B',*(['-O']if sys.flags.optimize else []),str(PRODUCTION_ENTRY)],input=encode(payload),stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment,timeout=5)


def test_actual_production_I_script_replays_valid_receipt_without_test_entry(harness,monkeypatch):
    from social.connections.verification_protocol import decode
    h=harness;payload=recorded_payload(h,monkeypatch);before=saved(h);count=len(graph(h))
    result=actual_script(payload)
    assert result.returncode==0 and result.stderr==b''
    decoded=decode(result.stdout)
    assert decoded['kind']=='success' and decoded['nonce']==payload['nonce']
    assert decoded['value']['publishing_enabled']is False and decoded['value']['enable_available']is True
    assert saved(h)==before and len(graph(h))==count


@pytest.mark.parametrize('field',['transport','mode','code'])
def test_actual_production_protocol_refuses_code_transport_mode_on_otherwise_valid_replay(harness,monkeypatch,field):
    h=harness;payload=recorded_payload(h,monkeypatch);before=saved(h);count=len(graph(h));payload[field]='caller-selected'
    result=actual_script(payload)
    assert result.returncode==2 and result.stdout==result.stderr==b''
    assert saved(h)==before and len(graph(h))==count


def test_outer_request_reserves_cleanup_and_refuses_before_spawn_when_insufficient(harness):
    h=harness;h.seconds=.5;before=saved(h);response=call(h)
    assert response.status_code==503 and response.json()['detail']['code']=='GRANT_VERIFICATION_UNAVAILABLE',response.text
    assert not h.children and not graph(h)and saved(h)==before
