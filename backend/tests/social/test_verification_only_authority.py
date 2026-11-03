"""Actual read transport and mounted API, with inert grants and no delivery runtime."""
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from social.account_publishing import AccountPublishingCommand,set_account_publishing
from social.connections import api
from social.connections.verification import SavedGrantVerificationAuthority,_ReadOnlyGraphTransport
from social.models import SocialAccount,SocialControls,SocialPostTarget,SocialPublication
from social.native_admission import native_capability_matches
from social.service import SocialError
from social.validation import registered_capability
from test_existing_grant_verification import saved,body_for,verify,client_for
from test_connections_support import config,db,graph,ACTOR


@pytest.mark.parametrize('header', ['X-HTTP-Method-Override', 'X-HTTP-Method', 'X-Method-Override'])
@pytest.mark.parametrize('method', ['POST', 'DELETE'])
def test_transport_refuses_method_override_headers_before_io(header, method):
 calls=[];transport=_ReadOnlyGraphTransport(httpx.MockTransport(lambda r:calls.append(r) or httpx.Response(200)),'v26.0')
 request=httpx.Request('GET','https://graph.facebook.com/v26.0/801?fields=id,username,name',headers={header:method})
 with pytest.raises(SocialError,match='GRANT_VERIFICATION_UNAVAILABLE'):
  transport.handle_request(request)
 assert not calls


@pytest.mark.parametrize('method,path,params',[
 ('POST','me',{'fields':'id'}),('DELETE','901',{'fields':'id,username,name'}),
 ('GET','oauth/access_token',{}),('GET','901/feed',{}),('GET','901/photos',{}),
 ('GET','batch',{}),('GET','me',{'fields':'id','method':'POST'}),
 ('GET','me/accounts',{'fields':'id,name,access_token,tasks,instagram_business_account'}),
 ('GET','me/permissions',{'fields':'permission,status','batch':'[]'}),
 ('GET','debug_token',{'input_token':'inert','method':'delete'}),
 ('GET','me',{'fields':'id,permissions'}),
])
def test_transport_refuses_every_nonverification_operation_before_io(method,path,params):
 calls=[];transport=_ReadOnlyGraphTransport(httpx.MockTransport(lambda r:calls.append(r)),'v26.0')
 with pytest.raises(SocialError,match='GRANT_VERIFICATION_UNAVAILABLE'):
  transport.handle_request(httpx.Request(method,'https://graph.facebook.com/v26.0/'+path,params=params))
 assert calls==[]


@pytest.mark.parametrize('url',[
 'http://graph.facebook.com/v26.0/me?fields=id',
 'https://attacker.example/v26.0/me?fields=id',
 'https://graph.facebook.com:444/v26.0/me?fields=id',
 'https://user:secret@graph.facebook.com/v26.0/me?fields=id',
 'https://graph.facebook.com/v25.0/me?fields=id',
 'https://graph.facebook.com/v26.0/%6de?fields=id',
 'https://graph.facebook.com/v26.0/me?fields=id&fields=id',
 'https://graph.facebook.com/v26.0/me?fields=id#fragment',
])
def test_transport_binds_exact_origin_version_and_path(url):
 calls=[];transport=_ReadOnlyGraphTransport(httpx.MockTransport(lambda r:calls.append(r)),'v26.0')
 with pytest.raises(SocialError):transport.handle_request(httpx.Request('GET',url))
 assert calls==[]


@pytest.mark.parametrize('changes',[
 {'enabled':False},{'app_configuration_validated':False},{'graph_version':'v27.0'},
 {'app_secret':' '},{'app_secret':'secret\n'},{'app_id':None},{'graph_version':True},
 {'access_mode':float('nan')},{'business_discovery_enabled':1},{'encryption_keys':{}},
])
def test_authority_requires_validated_exact_app_before_constructing_http(config,changes):
 with pytest.raises(SocialError,match='GRANT_VERIFICATION_UNAVAILABLE'):
  SavedGrantVerificationAuthority(replace(config,**changes))


def test_provider_port_does_not_expose_discovery_exchange_or_send(config,graph):
 authority=SavedGrantVerificationAuthority(config,transport=httpx.MockTransport(graph))
 provider=authority.open_provider(config)
 try:
  assert all(not hasattr(provider,name)for name in ['discover','authorize_url','_request','publish','client'])
 finally:provider.close()
 assert not graph.calls


@pytest.mark.parametrize('platform',['facebook','instagram'])
def test_off_state_proof_never_becomes_enablement_or_current_native_admission(saved,graph,platform):
 service,row,registry=saved;service.base.available_adapters={}
 row=service.db.scalar(select(SocialAccount).where(SocialAccount.platform==platform));service.db.rollback()
 result=verify(service,row)
 assert result['enable_available'] is False and result['publishing_enabled'] is False
 assert 'NATIVE_ADMISSION_UNAVAILABLE'in result['enable_blockers']
 assert 'NATIVE_RUNTIME_UNAVAILABLE'in result['delivery_holds']
 account=service.db.get(SocialAccount,row.id)
 # Even installing a real accepted adapter later cannot silently upgrade this proof.
 assert native_capability_matches(account.capability_snapshot,registered_capability(account,registry))is False
 service.base.available_adapters=registry
 from social.account_publishing import account_publishing
 status=account_publishing(service.base,row.id);service.db.rollback()
 command=AccountPublishingCommand(expected_controls_version=status['controls_version'],expected_state=status['state_token'],publishing_enabled=True,reason='Explicit fixture enable attempt')
 with pytest.raises(SocialError,match='NATIVE_ADMISSION_UNAVAILABLE'):
  service.base.command(actor=ACTOR,route='PATCH fixture',key=uuid4(),body=command.model_dump(),request_id=uuid4(),action=lambda:set_account_publishing(service.base,row.id,command))
 service.db.rollback()
 assert service.db.get(SocialControls,1).publishing_enabled is False
 assert not list(service.db.scalars(select(SocialPostTarget)))
 assert not list(service.db.scalars(select(SocialPublication)))
 # Explicit re-verification is still required after real native operational acceptance.
 assert verify(service,row)['enable_available'] is True


def test_api_injects_separate_authority_without_native_or_callback_admission(saved,graph,monkeypatch):
 service,row,_=saved;service.base.available_adapters={};service.config=replace(service.config,verified_callback_ingress_uris=())
 account_id=row.id;body=body_for(service,row);client=client_for(service)
 client.app.dependency_overrides.pop(api.verification_service)
 client.app.dependency_overrides[api.get_db]=lambda:service.db
 monkeypatch.setattr(api,'load_config',lambda:service.config)
 monkeypatch.setattr(httpx,'HTTPTransport',lambda **_:httpx.MockTransport(graph))
 response=client.post(f'/api/v1/admin/social/accounts/{account_id}/verify-publishing-access',json=body,headers={'Idempotency-Key':str(uuid4())})
 assert response.status_code==200,response.text
 assert response.json()['enable_available'] is False and response.json()['publishing_enabled'] is False
 assert response.headers['cache-control']=='private, no-store'
 assert graph.calls and all(r.method=='GET'for r in graph.calls)
 assert 'CALLBACK_INGRESS_UNVERIFIED'in service.config.oauth_blockers()
