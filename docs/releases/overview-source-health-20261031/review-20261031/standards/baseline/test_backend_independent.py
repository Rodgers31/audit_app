"""Independent offline hostile controls: real auth, CORS, async probe state."""
import asyncio,copy,json,math,ssl,time,threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from contextlib import contextmanager
import httpx,jwt,pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
import supabase_auth as auth
from services import source_reachability as sr
REAL_CLIENT=httpx.AsyncClient
PRIVATE='PRIVATE_ISSUER_TOKEN=/not-a-public-path bearer=secret-inert'

@pytest.fixture
def clock(monkeypatch):
 now=[100.0]
 for k,v in [('_jwks_cache',None),('_jwks_cache_ts',0.0),('_jwks_last_attempt_ts',None),('_jwks_refresh_in_flight',False)]:monkeypatch.setattr(auth,k,v)
 monkeypatch.setattr(auth,'_jwks_clock',lambda:now[0]);return now

@pytest.fixture
def keys(clock):
 key=ec.generate_private_key(ec.SECP256R1());public=json.loads(jwt.algorithms.ECAlgorithm.to_jwk(key.public_key()));public.update(kid='owned-key',alg='ES256')
 def token(*,signer=None,kid='owned-key',aud='authenticated'):
  return jwt.encode({'sub':'11111111-1111-4111-8111-111111111111','aud':aud,'exp':int(time.time())+120},signer or key,algorithm='ES256',headers={'kid':kid})
 return {'keys':[public]},token

def denied(call,delay):
 with pytest.raises(HTTPException) as caught:call()
 e=caught.value;assert e.status_code==503;assert e.headers=={'Retry-After':str(delay),'Cache-Control':'no-store'};assert PRIVATE not in e.detail

@pytest.mark.parametrize('elapsed',[0.0,.01,1.001,29.00001,29.999999])
def test_cold_cooldown_advice_uses_ceil_remaining_without_fetch(clock,monkeypatch,elapsed):
 auth._jwks_last_attempt_ts=100.0;clock[0]+=elapsed;monkeypatch.setattr(auth,'_read_jwks',lambda:pytest.fail('cooldown fetched provider'));denied(auth._fetch_jwks,max(1,math.ceil(30-elapsed)))

def test_leader_failure_advertises_remaining_attempt_cooldown(clock,monkeypatch):
 def failed():clock[0]+=4.25;raise httpx.ConnectError(PRIVATE)
 monkeypatch.setattr(auth,'_read_jwks',failed);denied(auth._fetch_jwks,26)

def test_exact_cooldown_boundary_recovers_once(clock,keys,monkeypatch):
 doc,token=keys;auth._jwks_last_attempt_ts=100.;clock[0]=130.;calls=[];monkeypatch.setattr(auth,'_read_jwks',lambda:calls.append(True) or doc)
 assert auth._decode_supabase_jwt(token())['aud']=='authenticated';assert len(calls)==1

@pytest.mark.parametrize('bad',['signature','audience','kid'])
def test_retry_changes_never_accept_invalid_signed_claims(clock,keys,monkeypatch,bad):
 doc,token=keys;auth._jwks_cache=doc;auth._jwks_cache_ts=100.;auth._jwks_last_attempt_ts=100.;monkeypatch.setattr(auth,'_read_jwks',lambda:pytest.fail('warm signing verification fetched provider'))
 value=token(signer=ec.generate_private_key(ec.SECP256R1())) if bad=='signature' else token(aud='another-project') if bad=='audience' else token(kid='not-a-key')
 with pytest.raises(HTTPException) as caught:auth._decode_supabase_jwt(value)
 assert caught.value.status_code==401;assert 'Retry-After' not in (caught.value.headers or {})

def test_warm_cache_serves_verified_readers_during_one_forced_fetch(clock,keys,monkeypatch):
 doc,token=keys;auth._jwks_cache=doc;auth._jwks_cache_ts=100.;entered=threading.Event();release=threading.Event();calls=[]
 def fetch():
  calls.append(True);entered.set()
  if not release.wait(2):raise RuntimeError('Owned fetch not released')
  raise httpx.ConnectError(PRIVATE)
 monkeypatch.setattr(auth,'_read_jwks',fetch)
 with ThreadPoolExecutor(max_workers=1) as pool:
  future=pool.submit(auth._fetch_jwks,True)
  try:
   assert entered.wait(1)
   for _ in range(9):assert auth._decode_supabase_jwt(token())['aud']=='authenticated'
   assert len(calls)==1
  finally:release.set()
  with pytest.raises(HTTPException):future.result(timeout=1)
 assert auth._jwks_cache==doc and auth._jwks_cache_ts==100.

def test_expired_cold_followers_refuse_immediately_while_single_fetch_runs(clock,keys,monkeypatch):
 doc,token=keys;auth._jwks_cache=doc;auth._jwks_cache_ts=100.-3600;entered=threading.Event();release=threading.Event();calls=[]
 def fetch():
  calls.append(True);entered.set()
  if not release.wait(2):raise RuntimeError('Owned fetch not released')
  return doc
 monkeypatch.setattr(auth,'_read_jwks',fetch)
 with ThreadPoolExecutor(max_workers=1) as pool:
  leader=pool.submit(auth._decode_supabase_jwt,token())
  try:
   assert entered.wait(1)
   for _ in range(12):denied(lambda:auth._decode_supabase_jwt(token()),1)
   assert not leader.done() and len(calls)==1
  finally:release.set()
  assert leader.result(timeout=1)['aud']=='authenticated'

@pytest.mark.asyncio
@pytest.mark.parametrize('origin',['https://allowed.owned','https://unknown.owned'])
async def test_real_admin_cors_refusal_exposes_retry_only_for_allowed_origin(clock,keys,monkeypatch,origin):
 import main
 _,token=keys
 monkeypatch.setattr(auth,'_read_jwks',lambda:(_ for _ in ()).throw(httpx.ConnectError(PRIVATE)))
 monkeypatch.setattr(auth,'_fetch_roles',lambda *_:pytest.fail('provider failure reached private profile'))
 async with REAL_CLIENT(transport=httpx.ASGITransport(app=main.app),base_url='http://api.owned') as client:
  response=await client.get('/api/v1/admin/users/stats',headers={'Origin':origin,'Authorization':'Bearer '+token(),'X-Inert-Private':'secret-inert'})
 assert response.status_code==503;assert response.headers['retry-after']=='30';assert response.headers['cache-control']=='no-store'
 assert response.headers.get('access-control-allow-origin')==('https://allowed.owned' if origin=='https://allowed.owned' else None)
 assert {s.strip().lower() for s in response.headers.get('access-control-expose-headers','').split(',')}=={'retry-after'}
 assert 'authorization' not in response.headers and 'set-cookie' not in response.headers and PRIVATE not in response.text and 'secret-inert' not in response.text

@pytest.mark.asyncio
async def test_unknown_origin_preflight_cannot_read_private_endpoint():
 import main
 async with REAL_CLIENT(transport=httpx.ASGITransport(app=main.app),base_url='http://api.owned') as client:
  response=await client.options('/api/v1/admin/users/stats',headers={'Origin':'https://unknown.owned','Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'authorization'})
 assert response.status_code==400;assert 'access-control-allow-origin' not in response.headers

def cert(code):
 e=ssl.SSLCertVerificationError(1,PRIVATE);e.verify_code=code;return e

@pytest.mark.parametrize('code',[True,False,'10',10.0,None,{},[],10**50])
def test_malformed_certificate_code_does_not_invent_specific_diagnosis(code):
 leaf=cert(code);outer=httpx.ConnectError(PRIVATE);middle=RuntimeError(PRIVATE);outer.__cause__=middle;middle.__context__=leaf
 assert sr.failure_detail(outer)==('certificate_error','certificate_untrusted')

@pytest.mark.parametrize('typed',[False,True])
def test_cyclic_wrapped_failure_is_bounded_and_safe(typed):
 a=RuntimeError(PRIVATE);b=cert(62) if typed else RuntimeError('CERTIFICATE_VERIFY_FAILED '+PRIVATE);a.__cause__=b;b.__context__=a
 assert sr.failure_detail(a)==('certificate_error','certificate_hostname_mismatch' if typed else 'certificate_untrusted')

def snapshot():return dict(alerts=[],database={'entities':{'counties':47}},auto_seeder={},checked_at='2026-10-31T00:00:00Z')

@pytest.mark.asyncio
async def test_unknown_clock_state_and_stale_diagnostics_never_claim_fresh_health():
 monitor=sr.SourceReachability();monitor._clock=lambda:100.;monitor._next_attempt=1000.;monitor._observed_mono=101.;monitor._records={k:dict(outcome='certificate_error',reachable=False,status_code=None,observed_at='old',failure_reason='certificate_expired') for k in sr.SOURCES}
 sources,running=monitor.observe();assert not running
 assert all(s['outcome']=='not_observed' and s['failure_reason'] is None and s['reachable'] is None for s in sources.values());assert sr.assemble_health(snapshot(),sources,running)['status']=='unknown'
 monitor._observed_mono=-200.;sources,_=monitor.observe();assert all(s['freshness']=='stale' for s in sources.values());assert not sr.assemble_health(snapshot(),sources,False)['alerts'];assert sr.assemble_health(snapshot(),sources,False)['status']=='unknown'

def test_unknown_reason_and_model_reject_raw_diagnostic_text():
 assert sr.observation_error(dict(failure_reason=PRIVATE,outcome='request_error',status_code=None))=='Homepage request failed.'
 with pytest.raises(ValueError):sr.SourceObservation(key='knbs',name='KNBS',url=sr.SOURCES['knbs'][1],freshness='fresh',outcome='request_error',reachable=False,failure_reason=PRIVATE)

@pytest.mark.asyncio
async def test_one_batch_survives_legacy_caller_cancellation_and_keeps_legacy_shape(monkeypatch):
 entered=asyncio.Event();release=asyncio.Event();calls=[];closed=[]
 class Client:
  def __init__(self,**kw):
   assert kw['timeout']==2.;assert kw.get('verify',True) is True;assert kw['max_redirects']==2 and kw['follow_redirects'] is True;assert kw['limits'].max_connections==5 and kw['limits'].max_keepalive_connections==0
  async def __aenter__(self):return self
  async def __aexit__(self,*_):closed.append(True)
  async def head(self,url):calls.append(url);entered.set();await release.wait();raise cert(20)
 monkeypatch.setattr(sr.httpx,'AsyncClient',Client);m=sr.SourceReachability();m._clock=lambda:100.;caller=asyncio.create_task(m.legacy())
 try:
  await asyncio.wait_for(entered.wait(),1);caller.cancel()
  with pytest.raises(asyncio.CancelledError):await caller
  for _ in range(30):sources,running=m.observe();assert running and all(s['failure_reason'] is None for s in sources.values())
  assert not m._task.cancelled();release.set();await asyncio.wait_for(m._task,1);legacy=await m.legacy()
  assert len(calls)==5 and len(closed)==1;assert sr.SOURCES['cob'][1]=='https://cob.go.ke';assert 'https://www.cob.go.ke' not in calls
  assert all(set(v)=={'key','name','url','reachable','error'} and v['reachable'] is False and 'chain' in v['error'] for v in legacy.values());assert PRIVATE not in json.dumps(legacy)
 finally:release.set();await asyncio.gather(caller,return_exceptions=True)

@pytest.mark.asyncio
async def test_batch_deadline_retains_slot_until_all_client_cleanup_finishes(monkeypatch):
 close_entered=asyncio.Event();close_release=asyncio.Event();heads=[];cancelled=[];opened=[]
 class Client:
  def __init__(self,**kw):opened.append(kw)
  async def __aenter__(self):return self
  async def __aexit__(self,*_):close_entered.set();await close_release.wait()
  async def head(self,url):
   heads.append(url)
   try:await asyncio.Future()
   finally:cancelled.append(url)
 monkeypatch.setattr(sr.httpx,'AsyncClient',Client);monkeypatch.setattr(sr,'BATCH_SECONDS',.01);clock=[100.];m=sr.SourceReachability();m._clock=lambda:clock[0];m.observe()
 try:
  await asyncio.wait_for(close_entered.wait(),1);clock[0]=500.
  for _ in range(9):assert m.observe()[1] is True
  assert len(opened)==1 and len(heads)==len(cancelled)==5;close_release.set();await asyncio.wait_for(m._task,1)
  m._next_attempt=1000.;sources,running=m.observe();assert not running;assert all(s['failure_reason']=='request_timeout' and s['reachable'] is False for s in sources.values());assert sr.assemble_health(snapshot(),sources,False)['status']=='degraded'
 finally:close_release.set();await asyncio.gather(m._task,return_exceptions=True)

@pytest.mark.asyncio
async def test_failed_client_entry_is_complete_safe_refusal(monkeypatch):
 class Client:
  def __init__(self,**kw):pass
  async def __aenter__(self):raise RuntimeError(PRIVATE)
  async def __aexit__(self,*_):pytest.fail('unentered client exit')
 monkeypatch.setattr(sr.httpx,'AsyncClient',Client);m=sr.SourceReachability();m.observe();await m._task;sources,running=m.observe();assert len(sources)==5 and not running
 assert all(s['outcome']=='request_error' and s['failure_reason']=='request_failed' and s['reachable'] is False for s in sources.values());assert PRIVATE not in json.dumps(sr.assemble_health(snapshot(),sources,running))

@pytest.mark.asyncio
async def test_successful_next_batch_clears_previous_reason_at_exact_ttl(monkeypatch):
 status=[False];calls=[]
 class Client:
  def __init__(self,**kw):pass
  async def __aenter__(self):return self
  async def __aexit__(self,*_):pass
  async def head(self,url):
   calls.append(url)
   if not status[0]:raise cert(10)
   return SimpleNamespace(status_code=200)
 monkeypatch.setattr(sr.httpx,'AsyncClient',Client);clock=[100.];m=sr.SourceReachability();m._clock=lambda:clock[0];m.observe();await m._task;clock[0]=399.999;sources,running=m.observe();assert not running and len(calls)==5
 clock[0]=400.;status[0]=True;sources,running=m.observe();assert running and all(s['freshness']=='stale' for s in sources.values());await m._task;sources,running=m.observe();assert not running and len(calls)==10
 assert all(s['reachable'] is True and s['failure_reason'] is None for s in sources.values());assert sr.assemble_health(snapshot(),sources,False)['status']=='healthy';assert all('error' not in v for v in (await m.legacy()).values())
