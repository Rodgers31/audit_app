"""Actual aggregated social router, explicit inert administrators and SQLite."""
from uuid import uuid4
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from social.api import router, get_db, require_admin
from supabase_auth import AdminUser
from test_meta_reels_recovery import db, seed, observation, FIRST, SECOND


def client(engine,actor=FIRST):
    app=FastAPI();app.include_router(router)
    def isolated():
        with Session(engine) as session:yield session
    app.dependency_overrides[get_db]=isolated
    def identity():
        if actor is None:raise HTTPException(401,'Inert fixture denial')
        return AdminUser(id=str(actor),email=None,roles=['admin'])
    app.dependency_overrides[require_admin]=identity
    return TestClient(app,raise_server_exceptions=False)


def test_aggregated_router_enforces_admin_independent_proof_and_idempotent_replay(db):
    target_id=seed(db);base=f'/api/v1/admin/social/targets/{target_id}/meta-reels'
    denied=client(db.bind,None).get(base+'/public-proof')
    assert denied.status_code==401 and denied.headers['cache-control']=='private, no-store'
    first=client(db.bind);second=client(db.bind,SECOND)
    context=first.get(base+'/public-proof');assert context.status_code==200,context.text
    context=context.json();evidence=observation(context).model_dump(mode='json')
    body={'expected_publication_version':1,'binding_hash':context['binding_hash'],'observation':evidence,'reason':'Synthetic full packet proposal'}
    assert first.post(base+'/public-proof',json=body).status_code==422
    invalid=first.post(base+'/public-proof',json={**body,'observation':{**evidence,'visibility':'private'}},headers={'Idempotency-Key':str(uuid4())})
    assert invalid.status_code==422
    proof=first.post(base+'/public-proof',json=body,headers={'Idempotency-Key':str(uuid4())})
    assert proof.status_code==201,proof.text
    admission={'expected_publication_version':1,'proof_id':proof.json()['proof_id'],'observation':observation(context).model_dump(mode='json'),'reason':'Independent synthetic complete scene/identity packets'}
    own=first.post(base+'/record-existing',json=admission,headers={'Idempotency-Key':str(uuid4())})
    assert own.status_code==403 and own.json()['detail']['code']=='INDEPENDENT_REVIEW_REQUIRED'
    headers={'Idempotency-Key':str(uuid4())}
    accepted=second.post(base+'/record-existing',json=admission,headers=headers)
    assert accepted.status_code==200,accepted.text
    assert accepted.headers['cache-control']=='private, no-store'
    assert second.post(base+'/record-existing',json=admission,headers=headers).json()==accepted.json()
    conflict=second.post(base+'/record-existing',json={**admission,'reason':'Different request body'},headers=headers)
    assert conflict.status_code==409 and conflict.json()['detail']['code']=='IDEMPOTENCY_CONFLICT'
