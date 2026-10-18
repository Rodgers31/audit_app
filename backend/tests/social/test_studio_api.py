from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from social.api import get_db, require_admin
from social.studio.api import router
from social.studio.runner import run_job
from supabase_auth import AdminUser
from test_domain_support import ACTOR, db
from test_studio import composition, runtime, source


def client(db, runtime, authenticated=True):
    app = FastAPI()
    app.include_router(router)
    app.state.social_studio_runtime = runtime
    def isolated_db():
        with Session(db.bind, expire_on_commit=False) as session:
            yield session
    app.dependency_overrides[get_db] = isolated_db
    if authenticated:
        app.dependency_overrides[require_admin] = lambda: AdminUser(id=str(ACTOR), email=None, roles=['admin'])
    return TestClient(app, raise_server_exceptions=False)


def key():
    return {'Idempotency-Key': str(uuid4())}


def test_http_auth_no_store_real_preview_idempotency_and_approval(db, runtime):
    api = client(db, runtime)
    base = '/api/v1/admin/social/studio'
    unauth = client(db, runtime, False).get(base + '/capabilities')
    assert unauth.status_code in {401, 403}
    assert unauth.headers['cache-control'] == 'private, no-store'
    post = source(db)
    body = composition(post['revision_id']).model_dump(mode='json')
    headers = key()
    created = api.post(base + '/jobs', json=body, headers=headers)
    assert created.status_code == 201, created.text
    assert api.post(base + '/jobs', json=body, headers=headers).json() == created.json()
    assert api.post(base + '/jobs', json={**body, 'title': 'Changed'}, headers=headers).status_code == 409
    job_id = created.json()['id']
    assert api.get(base + f'/jobs/{job_id}/preview').status_code == 409
    assert run_job(sessionmaker(bind=db.bind), runtime, UUID(job_id)) == 'ready'
    dto = api.get(base + f'/jobs/{job_id}').json()
    preview = api.get(base + f'/jobs/{job_id}/preview')
    assert preview.status_code == 200 and preview.content.startswith(b'\x89PNG')
    assert preview.headers['x-content-sha256'] == dto['sha256']
    assert preview.headers['cache-control'] == 'private, no-store'
    transcript = api.get(base + f'/jobs/{job_id}/transcript').json()
    assert transcript['sha256'] == dto['sha256'] and transcript['entries'][0]['fact_id'] == 'report'
    approval = {'expected_version': dto['version'], 'sha256': dto['sha256'], 'review_attestation': {'facts_checked': True, 'sources_checked': True}}
    rejected = api.post(base + f'/jobs/{job_id}/approve', json={**approval, 'review_attestation': {'facts_checked': False, 'sources_checked': True}}, headers=key())
    assert rejected.status_code == 422
    accepted = api.post(base + f'/jobs/{job_id}/approve', json=approval, headers=key())
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['approved_sha256'] == dto['sha256']
    malformed = api.get(base + '/jobs?page=0')
    assert malformed.status_code == 422 and malformed.headers['cache-control'] == 'private, no-store'
