from types import SimpleNamespace
from uuid import uuid4
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from social.connections.api import router,service,admin_session
from social.http_boundary import get_db,require_admin
from social.service import SocialError
from social.connections.config import MetaConfig
from test_connections_support import *

def client(db,config,graph,*,admin=True,session=SESSION):
    app=FastAPI();app.include_router(router)
    def isolated():
        with Session(db.bind,expire_on_commit=False) as session:
            yield session
    def fake(db=Depends(get_db)): return svc(db,config,graph)
    app.dependency_overrides[get_db]=isolated
    app.dependency_overrides[service]=fake
    if admin: app.dependency_overrides[require_admin]=lambda:SimpleNamespace(id=str(ACTOR),roles=['admin'],session_id=str(session) if session else None)
    return TestClient(app,raise_server_exceptions=False)

def key():return {'Idempotency-Key':str(uuid4())}

@pytest.mark.parametrize('path',['/connections/meta/status','/accounts/'+str(uuid4())+'/health'])
def test_read_routes_require_existing_admin_and_have_no_store(db,config,graph,path):
    response=client(db,config,graph,admin=False).get('/api/v1/admin/social'+path)
    assert response.status_code in {401,403}
    assert response.headers['cache-control']=='private, no-store'
    assert graph.calls==[]

def test_verified_admin_session_is_required_not_a_client_header(db,config,graph):
    c=client(db,config,graph,session=None)
    response=c.post('/api/v1/admin/social/connections/meta/start',headers={**key(),'X-Session-ID':str(SESSION)},json={'redirect_uri':REDIRECT,'reason':'Owned asset'})
    assert response.status_code==401 and response.json()['detail']['code']=='ADMIN_SESSION_REQUIRED'
    assert response.headers['cache-control']=='private, no-store'
    assert graph.calls==[]


def test_api_start_complete_select_health_strips_secrets(db,config,graph):
    c=client(db,config,graph)
    start=c.post('/api/v1/admin/social/connections/meta/start',headers=key(),json={'redirect_uri':REDIRECT,'reason':'Owned asset'})
    assert start.status_code==200,start.text
    state=parse_qs(urlsplit(start.json()['authorize_url']).query)['state'][0]
    flow=start.json()['flow_id']
    body={'state':state,'code':'fake-short-code','redirect_uri':REDIRECT}
    complete=c.post('/api/v1/admin/social/connections/meta/complete',headers=key(),json=body)
    assert complete.status_code==200,complete.text
    other=client(db,config,graph,session=uuid4())
    blocked=other.get('/api/v1/admin/social/connections/meta/flows/'+flow)
    assert blocked.status_code==409
    selected=c.post('/api/v1/admin/social/connections/meta/flows/'+flow+'/select',headers=key(),json={'page_id':'901','instagram_id':'801','reason':'Confirm AuditGava'})
    assert selected.status_code==200,selected.text
    health=c.get('/api/v1/admin/social/accounts/'+selected.json()['accounts'][0]['id']+'/health')
    assert health.status_code==200,health.text
    assert health.json()['credential_version']==1
    for response in (complete,selected,health):
        assert all(secret not in response.text for secret in (USER,PAGE,config.app_secret,state,'fake-short-code'))
        assert response.headers['cache-control']=='private, no-store'


def test_missing_configuration_and_malformed_commands_are_truthful(db,config,graph):
    c=client(db,MetaConfig(),graph)
    status=c.get('/api/v1/admin/social/connections/meta/status')
    assert status.status_code==200 and status.json()['available'] is False
    assert 'ENCRYPTION_CONFIGURATION_INVALID' in status.json()['blockers']
    failed=c.post('/api/v1/admin/social/connections/meta/start',headers=key(),json={'redirect_uri':REDIRECT,'reason':'Owned'})
    assert failed.status_code==503 and failed.json()['detail']['code']=='CONNECTIONS_UNAVAILABLE'
    c=client(db,config,graph)
    for body in [{'redirect_uri':'https://evil.example/admin/social/accounts/callback','reason':'x'},{'redirect_uri':REDIRECT+'?token=x','reason':'x'},{'redirect_uri':REDIRECT,'reason':'x','access_token':USER}]:
        response=c.post('/api/v1/admin/social/connections/meta/start',headers=key(),json=body)
        assert response.status_code==422
        assert USER not in response.text
    response=c.post('/api/v1/admin/social/connections/meta/start',json={'redirect_uri':REDIRECT,'reason':'x'})
    assert response.status_code==422
    assert graph.calls==[]


def test_provider_http_occurs_after_state_commit_without_db_transaction(db,config,graph):
    original=graph.__call__
    def ensure_no_transaction(request):
        assert not db.in_transaction()
        return original(request)
    service=svc(db,config,ensure_no_transaction)
    _,state=start(service)
    complete(service,state)
