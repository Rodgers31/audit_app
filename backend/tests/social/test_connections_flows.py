import json
from datetime import timedelta
from uuid import UUID,uuid4
from dataclasses import replace
import pytest
from sqlalchemy import select
from social.connections.models import SocialOAuthFlow, SocialCredential
from social.models import SocialAccount, SocialAuditEvent, SocialCommandReceipt
from social.connections.config import MetaConfig, SCOPES
from social.connections.contracts import CompleteCommand, AccountCommand
from social.service import SocialError
from test_connections_support import *


def test_complete_explicit_selection_and_server_only_grants(db,config,graph):
    service = svc(db,config,graph)
    started,state = start(service)
    result = complete(service,state)
    assert result['choices'][0]['page_eligible'] is True
    assert db.scalar(select(SocialAccount.id)) is None
    db.rollback()
    key = uuid4()
    selected = select_asset(service,UUID(started['flow_id']),key=key)
    assert len(selected['accounts']) == 2
    assert all(a['publishing_enabled'] is False and a['capabilities']['adapter_available'] is False for a in selected['accounts'])
    assert [a['display_name'] for a in selected['accounts']] == ['AuditGava','AuditGava IG']
    assert select_asset(service,UUID(started['flow_id']),key=key) == selected
    credentials = list(db.scalars(select(SocialCredential)))
    assert len(credentials) == 2 and {c.credential_kind for c in credentials} == {'facebook_user','facebook_page'}
    assert all(c.refresh_expires_at is None for c in credentials)
    flow = db.get(SocialOAuthFlow, UUID(started['flow_id']))
    assert flow.status == 'completed' and flow.encrypted_pending_grant is None and flow.encrypted_verifier is None
    persisted = json.dumps([r.response for r in db.scalars(select(SocialCommandReceipt))]) + json.dumps([e.details for e in db.scalars(select(SocialAuditEvent))])
    assert all(secret not in persisted + json.dumps(result) + json.dumps(selected) for secret in [USER,PAGE,config.app_secret,'fake-short-lived-code',state])
    assert all(r.url.host == 'graph.facebook.com' for r in graph.calls)
    assert all(r.url.path.rsplit('/',1)[-1] not in {'feed','photos','videos','media_publish','media'} for r in graph.calls)


def test_start_idempotency_and_complete_idempotency_without_code_replay(db,config,graph):
    service=svc(db,config,graph)
    key=uuid4()
    a,state=start(service,key=key)
    b,_=start(service,key=key)
    assert a==b
    done_key=uuid4()
    done=complete(service,state,key=done_key)
    count=len(graph.calls)
    assert complete(service,state,key=done_key)==done and len(graph.calls)==count
    with pytest.raises(SocialError,match='OAUTH_STATE_USED'):
        complete(service,state)
    assert len(graph.calls)==count


@pytest.mark.parametrize('hostility',['wrong_actor','wrong_session','invalid_state','redirect','expired'])
def test_hostile_state_never_reaches_provider(db,config,graph,hostility):
    configured=replace(config,redirect_uris=(REDIRECT,'https://second.example.test/admin/social/accounts/callback'))
    service=svc(db,configured,graph)
    started,state=start(service)
    actor,binding,redirect=ACTOR,BINDING,REDIRECT
    if hostility=='wrong_actor': actor=uuid4()
    if hostility=='wrong_session': binding=session_binding(ACTOR,uuid4())
    if hostility=='invalid_state': state='a'*43
    if hostility=='redirect': redirect=configured.redirect_uris[1]
    if hostility=='expired':
        with db.begin(): db.get(SocialOAuthFlow,UUID(started['flow_id'])).expires_at = datetime.now(timezone.utc)-timedelta(minutes=1)
    with pytest.raises(SocialError): complete(service,state,actor=actor,binding=binding,redirect=redirect)
    assert graph.calls==[]


def test_partial_grants_and_bad_selection(db,config,graph):
    graph.scopes.remove('instagram_content_publish')
    service=svc(db,config,graph)
    started,state=start(service)
    result=complete(service,state)
    choice=result['choices'][0]
    assert choice['page_eligible'] and not choice['instagram_eligible']
    assert choice['missing_instagram_scopes']==['instagram_content_publish']
    for page,ig,code in [('901','999','ASSET_SELECTION_INVALID'),('999',None,'ASSET_SELECTION_INVALID'),('901','801','PERMISSIONS_REQUIRED')]:
        with pytest.raises(SocialError,match=code): select_asset(service,UUID(started['flow_id']),page=page,ig=ig)
    selected=select_asset(service,UUID(started['flow_id']),ig=None)
    assert len(selected['accounts'])==1


@pytest.mark.parametrize('failure',['revoke','expired','permissions','timeout','raw_error'])
def test_consumed_state_cannot_retry_failed_provider_exchange(db,config,graph,caplog,failure):
    graph.revoke=failure=='revoke';graph.expired=failure=='expired'
    if failure=='permissions': graph.scopes.remove('pages_show_list')
    if failure=='raw_error': graph.error={'error':{'code':999,'message':'https://secret.example/?access_token='+USER}}
    if failure=='timeout':
        def failing(req): raise httpx.ReadTimeout('raw URL '+USER, request=req)
        fake=failing
    else: fake=graph
    service=svc(db,config,fake)
    started,state=start(service)
    with caplog.at_level('INFO'):
        with pytest.raises(SocialError): complete(service,state)
    with pytest.raises(SocialError,match='OAUTH_STATE_USED'): complete(service,state)
    flow=db.get(SocialOAuthFlow,UUID(started['flow_id']))
    assert flow.status=='failed' and flow.encrypted_pending_grant is None
    assert USER not in caplog.text and config.app_secret not in caplog.text and state not in caplog.text


def test_pagination_does_not_follow_provider_token_url_and_multi_page_selection(db,config,graph,caplog):
    graph.pages.append({'id':'902','name':'Other Page','access_token':PAGE2,'tasks':['CREATE_CONTENT']})
    graph.paging=True
    service=svc(db,config,graph)
    started,state=start(service)
    with caplog.at_level('INFO'): result=complete(service,state)
    assert [p['page_id'] for p in result['choices']]==['901','902']
    assert all(r.url.host=='graph.facebook.com' for r in graph.calls)
    assert USER not in caplog.text and PAGE not in caplog.text and config.app_secret not in caplog.text
    selected=select_asset(service,UUID(started['flow_id']),page='902',ig=None)
    assert selected['accounts'][0]['display_name']=='Other Page'
