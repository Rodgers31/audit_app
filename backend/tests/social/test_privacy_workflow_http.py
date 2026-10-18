"""Actual router auth, strict request shapes, idempotency and no-store boundaries."""
from types import SimpleNamespace
from uuid import UUID, uuid4
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from social.privacy.workflow_api import router, workflow
from social.http_boundary import require_admin
from test_privacy_workflow import setup, config, db, graph, ACTOR, APPROVER, POLICY

@pytest.fixture
def client(setup):
    svc, command, _ = setup
    app = FastAPI()
    app.include_router(router)
    actor = {'id': str(ACTOR)}
    def auth():
        if actor['id'] == 'unauthenticated':
            raise HTTPException(401)
        if actor['id'] == 'nonadmin':
            raise HTTPException(403)
        return SimpleNamespace(id=actor['id'])
    app.dependency_overrides[workflow] = lambda: svc
    app.dependency_overrides[require_admin] = auth
    with TestClient(app) as client:
        yield client, actor, command


def test_authenticated_proposal_independent_decision_execute_and_query(client):
    client, actor, command = client
    key = str(uuid4())
    response = client.post('/api/v1/admin/social/privacy/plans', json=command.model_dump(mode='json'), headers={'Idempotency-Key':key})
    assert response.status_code == 200 and response.headers['cache-control'] == 'private, no-store'
    plan = response.json()
    assert client.post('/api/v1/admin/social/privacy/plans', json=command.model_dump(mode='json'),headers={'Idempotency-Key':key}).json()['id'] == plan['id']
    assert client.get('/api/v1/admin/social/privacy/requests').json()['total'] == 1
    body={'plan_hash':plan['plan_hash'],'decision':'approved','reason':'Independent fixture policy review.'}
    assert client.post(f"/api/v1/admin/social/privacy/plans/{plan['id']}/decision",json=body).status_code == 409
    actor['id']=str(APPROVER)
    assert client.post(f"/api/v1/admin/social/privacy/plans/{plan['id']}/decision",json=body).status_code == 200
    assert client.post(f"/api/v1/admin/social/privacy/plans/{plan['id']}/execute",json={'expected_version':True}).status_code == 422
    response=client.post(f"/api/v1/admin/social/privacy/plans/{plan['id']}/execute",json={'expected_version':1})
    assert response.status_code == 200
    assert response.json()['execution']['state']=='completed'
    detail=client.get(f'/api/v1/admin/social/privacy/requests/{command.receipt_id}').json()
    assert detail['plans'][0]['id']==plan['id']
    assert 'subject_digest' not in str(detail) and 'encrypted_bundle' not in str(detail)

@pytest.mark.parametrize('identity,status',[('unauthenticated',401),('nonadmin',403)])
def test_every_endpoint_requires_admin(client, identity, status):
    client,actor,command=client
    actor['id']=identity
    for method,path,body in [('get','/requests',None),('get',f'/requests/{command.receipt_id}',None),('get',f'/plans/{uuid4()}',None),('post','/plans',command.model_dump(mode='json')),('post',f'/plans/{uuid4()}/decision',{}),('post',f'/plans/{uuid4()}/execute',{}),('post',f'/plans/{uuid4()}/reconcile',{})]:
        response=client.request(method,'/api/v1/admin/social/privacy'+path,json=body,headers={'Idempotency-Key':str(uuid4())})
        assert response.status_code==status and response.headers['cache-control']=='private, no-store'
