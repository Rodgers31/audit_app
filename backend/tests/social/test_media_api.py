from uuid import UUID, uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from social.http_boundary import AdminUser, get_db, require_admin
from social.media.api import router, service
from social.media.runtime import MediaRuntime
from social.media.config import MediaConfig
from social.media.service import MediaService
from test_media_support import ACTOR, intent, media, media_db, png

BASE = '/api/v1/admin/social/media'


def client(media, actor=ACTOR):
    svc, _ = media; app = FastAPI(); app.include_router(router)
    def database():
        with Session(svc.db.bind, expire_on_commit=False) as session: yield session
    def feature(db=Depends(get_db)): return MediaService(db, svc.runtime)
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[service] = feature
    if actor:
        app.dependency_overrides[require_admin] = lambda: AdminUser(id=str(actor), email=None, roles=['admin'])
    return TestClient(app, raise_server_exceptions=False)


def header(key=None): return {'Idempotency-Key': str(key or uuid4())}


@pytest.mark.parametrize('method,path,body', [('get','/capabilities',None), ('get','/assets',None), ('get',f'/assets/{uuid4()}/preview',None), ('post','/uploads',intent()), ('post',f'/uploads/{uuid4()}/complete',{'expected_version':1})])
def test_every_route_requires_admin_and_private_errors(media, method, path, body):
    response = client(media, None).request(method, BASE + path, json=body, headers=header())
    assert response.status_code in {401, 403}
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['x-request-id']
    assert response.json()['detail']['code'] in {'AUTHENTICATION_REQUIRED','PERMISSION_DENIED'}


def test_actual_api_workflow_replays_and_cross_admin_library(media, caplog):
    _, storage = media; api = client(media); key = header()
    capabilities = api.get(BASE + '/capabilities')
    assert capabilities.status_code == 200 and capabilities.json()['upload_available']
    grant = api.post(BASE + '/uploads', json=intent(alt_text='Shared description'), headers=key)
    assert grant.status_code == 201, grant.text
    asset_id = grant.json()['asset']['id']
    assert grant.json()['asset']['sha256'] is None
    assert api.post(BASE + '/uploads', json=intent(alt_text='Shared description'), headers=key).json()['asset']['id'] == asset_id
    storage.objects[storage.last_key] = (png(), 'image/png', None)
    complete_key = header(); path = BASE + '/uploads/' + asset_id + '/complete'
    assert client(media, uuid4()).post(path,json={'expected_version':1},headers=complete_key).status_code == 403
    completed = api.post(path, json={'expected_version':1}, headers=complete_key)
    assert completed.status_code == 200, completed.text
    assert completed.json()['state'] == 'ready' and completed.json()['width'] == 64
    assert api.post(path,json={'expected_version':1},headers=complete_key).json() == completed.json()
    shared = client(media, uuid4())
    assert shared.get(BASE + '/assets').json()['assets'][0]['id'] == asset_id
    preview = shared.get(BASE + '/assets/' + asset_id + '/preview')
    assert preview.status_code == 200
    assert 'storage_key' not in completed.text and 'url' not in shared.get(BASE + '/assets').text
    assert 'fixture=' not in caplog.text and 'preview-secret' not in caplog.text
    for response in [grant, completed, preview]: assert response.headers['cache-control'] == 'private, no-store'


@pytest.mark.parametrize('data', [{**intent(),'declared_size':True}, {**intent(),'declared_size':0}, {**intent(),'filename':'../secret'}, {**intent(),'url':'https://evil.test'}, {**intent(),'declared_mime_type':'text/html'}])
def test_strict_upload_requests_reject_unsupported_fields(media, data):
    response = client(media).post(BASE + '/uploads',json=data,headers=header())
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'INVALID_REQUEST'


def test_idempotency_version_pagination_and_schema_errors(media):
    api=client(media)
    assert api.post(BASE + '/uploads',json=intent()).status_code == 422
    key=header(); first=api.post(BASE + '/uploads',json=intent(),headers=key)
    assert api.post(BASE + '/uploads',json=intent(filename='changed.png'),headers=key).json()['detail']['code'] == 'IDEMPOTENCY_CONFLICT'
    path=BASE + '/uploads/' + first.json()['asset']['id'] + '/complete'
    assert api.post(path,json={'expected_version':True},headers=header()).status_code == 422
    for query in ['?page_size=51','?kind=caption','?page=0']:
        assert api.get(BASE+'/assets'+query).status_code == 422
    engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
    svc,_=media; original=svc.db.bind; svc.db.bind=engine
    response=client(media).get(BASE+'/assets')
    assert response.status_code == 503 and response.json()['detail']['code'] == 'SOCIAL_SCHEMA_UNAVAILABLE'
    assert 'SELECT' not in response.text
    svc.db.bind=original; engine.dispose()


def test_unconfigured_runtime_never_advertises_or_grants_upload(media):
    svc,_=media
    svc.runtime=MediaRuntime(MediaConfig(),None,None,'Media storage has not been enabled.')
    api=client(media)
    data=api.get(BASE+'/capabilities').json()
    assert not data['upload_available'] and data['allowed_mime_types'] == []
    response=api.post(BASE+'/uploads',json=intent(),headers=header())
    assert response.status_code == 503 and response.json()['detail']['code']=='MEDIA_UNAVAILABLE'
