"""Explicit saved-grant proof with intercepted Graph reads; no external traffic."""
import asyncio
from dataclasses import replace
from uuid import UUID,uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from social.adapters import FacebookPageAdapter,InstagramFacebookLoginAdapter,MetaAdapterConfig
from social.account_publishing import account_publishing
from social.connections import api
from social.connections.provider import MetaProvider
from social.connections.service import ConnectionService
from social.http_boundary import require_admin,AdminUser
from social.models import SocialAccount,SocialControls,SocialAuditEvent,SocialCommandReceipt
from social.service import SocialService,SocialError
from social.validation import capability_for
from test_connections_support import config,db,graph,svc,start,complete,select_asset,ACTOR,BINDING,SESSION,USER,PAGE

@pytest.fixture
def saved(db,config,graph):
 old=svc(db,config,graph);flow,state=start(old);complete(old,state);select_asset(old,UUID(flow['flow_id']))
 cfg=MetaAdapterConfig(graph_version='v26.0',enabled=True,operational_gates_verified=True,app_secret=config.app_secret)
 def no_send(request):raise AssertionError('Native adapter must never send during grant verification')
 adapters={('facebook','facebook_pages'):FacebookPageAdapter(cfg,transport=httpx.MockTransport(no_send)),('instagram','instagram_graph_facebook_login'):InstagramFacebookLoginAdapter(cfg,transport=httpx.MockTransport(no_send))}
 service=ConnectionService(db,config,provider_factory=lambda c:MetaProvider(c,transport=httpx.MockTransport(graph)),available_adapters=adapters)
 row=db.scalar(select(SocialAccount).where(SocialAccount.platform=='facebook'));db.rollback();graph.calls.clear()
 yield service,row,adapters
 for adapter in adapters.values():asyncio.run(adapter.close())


def body_for(service,row):
 status=account_publishing(service.base,row.id);service.db.rollback()
 return {'expected_controls_version':status['controls_version'],'expected_state':status['state_token'],'reason':'Verify existing explicitly paused owned grant'}


def client_for(service):
 app=FastAPI();app.include_router(api.router)
 app.dependency_overrides[api.service]=lambda:service
 app.dependency_overrides[require_admin]=lambda:AdminUser(id=str(ACTOR),email=None,roles=['admin'])
 app.dependency_overrides[api.admin_session]=lambda:api.AdminSession(ACTOR,BINDING)
 return TestClient(app,raise_server_exceptions=False)


def test_missing_existing_grant_path_cannot_promote_without_provider_proof(saved,graph):
 service,row,registry=saved
 assert capability_for(row,registry).adapter_available is False
 account_id=row.id;body=body_for(service,row);response=client_for(service).post(f'/api/v1/admin/social/accounts/{account_id}/verify-publishing-access',json=body,headers={'Idempotency-Key':str(uuid4())})
 assert response.status_code==200,response.text
 assert response.json()['publishing_enabled'] is False
 assert response.json()['enable_available'] is True
 assert graph.calls and all(request.method=='GET' for request in graph.calls)
 assert sum(request.url.path.endswith('/debug_token') for request in graph.calls)==2


def verify(service,row,body=None,key=None):
 account_id=row.id
 service.db.rollback()
 command=body if body is not None else body_for(service,row)
 return service.verify_existing_grant(account_id,ACTOR,BINDING,'POST verify/'+str(account_id),key or uuid4(),command,uuid4())


def test_saved_grant_direct_positive(saved,graph):
 service,row,_=saved
 result=verify(service,row)
 assert result['enable_available'] is True
 assert graph.calls and all(r.method=='GET' for r in graph.calls)


def test_provider_reads_have_no_database_transaction_and_replay_has_no_reads(saved,graph):
 service,row,_=saved;body=body_for(service,row);account_id=row.id;service.db.rollback();key=uuid4();original=graph.__call__
 def read(request):
  assert not service.db.in_transaction()
  assert request.method=='GET'
  return original(request)
 service.provider_factory=lambda c:MetaProvider(c,transport=httpx.MockTransport(read))
 result=verify(service,row,body,key);count=len(graph.calls)
 assert result['publishing_enabled'] is False and result['global_publishing_enabled'] is False
 assert verify(service,row,body,key)==result
 assert len(graph.calls)==count
 changed={**body,'reason':'Another explicit reason'}
 with pytest.raises(SocialError,match='IDEMPOTENCY_CONFLICT'):verify(service,row,changed,key)
 assert len(graph.calls)==count
 service.db.expire_all();assert service.db.get(SocialAccount,account_id).publishing_enabled is False
 assert service.db.get(SocialControls,1).publishing_enabled is False


@pytest.mark.parametrize('change',['absent','legacy_names','native_disabled','operator_unaccepted','wrong_app'])
def test_native_server_gates_refuse_before_graph(saved,graph,change):
 service,row,registry=saved;body=body_for(service,row)
 if change=='absent':service.base.available_adapters={}
 elif change=='legacy_names':service.base.available_adapters=('facebook',)
 else:
  adapter=registry[('facebook','facebook_pages')]
  adapter.config=replace(adapter.config,**({'enabled':False} if change=='native_disabled' else {'operational_gates_verified':False} if change=='operator_unaccepted' else {'app_secret':'wrong-app'}))
  # Both actual registrations must be disabled to prove the early global gate.
  other=registry[('instagram','instagram_graph_facebook_login')];other.config=adapter.config
 with pytest.raises(SocialError,match='NATIVE_ADMISSION_UNAVAILABLE'):verify(service,row,body)
 assert not graph.calls


@pytest.mark.parametrize('change',['revoked','expired_user','permissions','tasks','page_absent','linked_identity','subject','shorter_page_expiry','shorter_data_expiry'])
def test_provider_evidence_failures_never_promote(saved,graph,change):
 service,row,_=saved
 if change=='linked_identity':row=service.db.scalar(select(SocialAccount).where(SocialAccount.platform=='instagram'));service.db.rollback()
 body=body_for(service,row)
 if change=='revoked':graph.revoke=True
 elif change=='expired_user':graph.expired=True
 elif change=='permissions':graph.scopes=[]
 elif change=='tasks':graph.pages[0]['tasks']=[]
 elif change=='page_absent':graph.pages=[]
 elif change=='linked_identity':graph.pages[0]['instagram_business_account']=None
 original=graph.__call__
 def read(request):
  result=original(request)
  if request.url.path.endswith('/debug_token'):
   value=result.json()
   if change=='subject':value['data']['user_id']='999'
   if change=='shorter_page_expiry' and request.url.params['input_token']==PAGE:value['data']['expires_at']=value['data']['data_access_expires_at']
   if change=='shorter_data_expiry':value['data']['data_access_expires_at']=int(__import__('time').time())+60
   return httpx.Response(200,json=value)
  return result
 service.provider_factory=lambda c:MetaProvider(c,transport=httpx.MockTransport(read))
 with pytest.raises(SocialError):verify(service,row,body)
 service.db.expire_all();assert service.db.get(SocialAccount,row.id).capability_snapshot['adapter_available'] is False
 assert not list(service.db.scalars(select(SocialAuditEvent).where(SocialAuditEvent.action=='connection.publishing_access_verified')))


def test_exact_linked_instagram_can_be_verified_without_its_sibling_promotion(saved,graph):
 service,row,_=saved;row=service.db.scalar(select(SocialAccount).where(SocialAccount.platform=='instagram'));service.db.rollback()
 result=verify(service,row)
 assert result['enable_available'] is True and result['publishing_enabled'] is False
 service.db.expire_all();facebook=service.db.scalar(select(SocialAccount).where(SocialAccount.platform=='facebook'))
 assert facebook.capability_snapshot['adapter_available'] is False
 assert all(r.method=='GET' for r in graph.calls)


@pytest.mark.parametrize('change',['credential_version','sibling_enabled','controls_version','disconnect','envelope'])
def test_changes_during_read_are_fenced(saved,graph,change):
 from social.connections.models import SocialCredential
 service,row,_=saved;account_id=row.id;credential_id=row.credential_id;body=body_for(service,row);seen=False;original=graph.__call__
 def read(request):
  nonlocal seen
  assert not service.db.in_transaction()
  if not seen:
   seen=True
   if change=='credential_version':service.db.get(SocialCredential,credential_id).version+=1
   elif change=='sibling_enabled':service.db.scalar(select(SocialAccount).where(SocialAccount.platform=='instagram')).publishing_enabled=True
   elif change=='controls_version':service.db.get(SocialControls,1).version+=1
   elif change=='disconnect':service.db.get(SocialAccount,account_id).connection_state='disconnected'
   elif change=='envelope':service.db.get(SocialCredential,credential_id).encrypted_bundle=b'changed-during-get'
   service.db.commit()
  return original(request)
 service.provider_factory=lambda c:MetaProvider(c,transport=httpx.MockTransport(read))
 with pytest.raises(SocialError):verify(service,row,body)
 service.db.expire_all();assert service.db.get(SocialAccount,account_id).capability_snapshot['adapter_available'] is False


@pytest.mark.parametrize('patch',[{'expected_controls_version':True},{'expected_controls_version':0},{'expected_state':'bad'},{'publishing_enabled':True},{'reason':''}])
def test_http_strict_contract(saved,patch):
 service,row,_=saved;account_id=row.id;body=body_for(service,row)
 response=client_for(service).post(f'/api/v1/admin/social/accounts/{account_id}/verify-publishing-access',json={**body,**patch},headers={'Idempotency-Key':str(uuid4())})
 assert response.status_code==422,response.text
 assert response.headers['cache-control']=='private, no-store'


@pytest.mark.parametrize('failure',['proof_write','audit_write'])
def test_suppressed_proof_or_audit_cannot_commit_receipt(saved,failure):
 from sqlalchemy import text
 service,row,_=saved;body=body_for(service,row)
 if failure=='proof_write':sql="CREATE TRIGGER review_proof AFTER UPDATE ON social_accounts BEGIN UPDATE social_accounts SET capability_snapshot=OLD.capability_snapshot WHERE id=NEW.id; END"
 else:sql="CREATE TRIGGER review_audit BEFORE INSERT ON social_audit_events WHEN NEW.action='connection.publishing_access_verified' BEGIN SELECT RAISE(IGNORE); END"
 service.db.execute(text(sql));service.db.commit()
 with pytest.raises(SocialError,match='ACCOUNT_CONTROL_FAILED'):verify(service,row,body)
 service.db.expire_all();assert service.db.get(SocialAccount,row.id).capability_snapshot['adapter_available'] is False


@pytest.mark.parametrize('during_read',[False,True])
@pytest.mark.parametrize('reader_present',[False,True])
def test_pending_privacy_receipt_cannot_be_bypassed(saved,graph,during_read,reader_present):
 from social.models import Base
 from social.privacy.models import PRIVACY_TABLES,SocialPrivacyReceipt
 from social.privacy.ownership import OwnershipRecorder
 from social.privacy.subjects import SubjectDigester
 service,row,_=saved;db=service.db
 db.rollback();Base.metadata.create_all(db.bind,tables=PRIVACY_TABLES)
 digester=SubjectDigester('test',{'test':b'x'*32})
 if reader_present:service.ownership_recorder=OwnershipRecorder(service.config.app_id,digester)
 body=body_for(service,row)
 def insert():
  audit_id=db.scalar(select(SocialAuditEvent.id).limit(1))
  db.add(SocialPrivacyReceipt(app_id=service.config.app_id,kind='deauthorization',digest_version='test',subject_digest=digester.digest(service.config.app_id,'701'),event_key='c'*64,request_fingerprint='d'*64,affected={},resolution='fixture_pending',state='ownership_unresolved',audit_id=audit_id));db.commit()
 if not during_read:insert()
 original=graph.__call__;seen=False
 def read(request):
  nonlocal seen
  if during_read and not seen:seen=True;insert()
  return original(request)
 service.provider_factory=lambda c:MetaProvider(c,transport=httpx.MockTransport(read))
 with pytest.raises(SocialError,match='PRIVACY_(GRANT_BLOCKED|STATE_UNAVAILABLE)'):verify(service,row,body)


@pytest.mark.parametrize('denial',[401,403])
def test_verification_http_admin_boundary(saved,graph,denial):
 from fastapi import HTTPException
 service,row,_=saved;account_id=row.id;body=body_for(service,row);client=client_for(service)
 def denied():raise HTTPException(denial)
 client.app.dependency_overrides[require_admin]=denied
 response=client.post(f'/api/v1/admin/social/accounts/{account_id}/verify-publishing-access',json=body,headers={'Idempotency-Key':str(uuid4())})
 assert response.status_code==denial and not graph.calls
 assert response.headers['cache-control']=='private, no-store'


def test_fresh_reverification_changes_monotonic_token(saved):
 service,row,_=saved
 first=verify(service,row);second=verify(service,row)
 assert second['controls_version']==first['controls_version']+1
 assert second['state_token']!=first['state_token']


@pytest.mark.parametrize('malformed',[None,[],{'facebook':None},{'facebook':{'publishing_enabled':1}},{'facebook':{'publishing_enabled':'false'}}])
def test_malformed_platform_policy_refuses_verification_before_reads(saved,graph,malformed):
 from sqlalchemy.orm.attributes import flag_modified
 service,row,_=saved;controls=service.db.get(SocialControls,1);controls.platform_controls=malformed;flag_modified(controls,'platform_controls');service.db.commit();body=body_for(service,row)
 with pytest.raises(SocialError,match='PLATFORM_CONTROLS_UNAVAILABLE'):verify(service,row,body)
 assert not graph.calls


def test_suppressed_verification_timestamp_cannot_report_success(saved):
 from sqlalchemy import text
 from datetime import timedelta
 service,row,_=saved;row.capabilities_checked_at=service.base.now()-timedelta(days=2);row.last_api_success_at=row.capabilities_checked_at;service.db.commit();body=body_for(service,row)
 service.db.execute(text('CREATE TRIGGER review_proof_metadata AFTER UPDATE ON social_accounts BEGIN UPDATE social_accounts SET capabilities_checked_at=OLD.capabilities_checked_at,last_api_success_at=OLD.last_api_success_at WHERE id=NEW.id; END'));service.db.commit()
 with pytest.raises(SocialError,match='ACCOUNT_CONTROL_FAILED'):verify(service,row,body)
