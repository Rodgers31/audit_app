"""Mounted admin APIs: inert media, human review and idempotent queue acceptance.

SQLite/controlled storage exercise the browser-facing contracts together. Native
worker/role PostgreSQL tests separately exercise provider delivery and restart.
No runtime defaults, production credentials or external connections are used.
"""
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from social import api as social_api
from social.http_boundary import AdminUser, get_db, require_admin
from social.media import api as media_api
from social.media.config import MediaConfig
from social.media.runtime import MediaRuntime
from social.media.service import MediaService
from social.models import SocialControls, SocialPostTarget, SocialPublication, SocialPublishAttempt
from social.service import SocialService
from test_account_publishing import connected as account, REGISTRY
from test_media_support import ACTOR, intent, media, media_db, png

BASE = '/api/v1/admin/social'


def headers():
    return {'Idempotency-Key': str(uuid4())}


def mounted_client(media):
    svc, _ = media
    app = FastAPI()
    app.include_router(social_api.router)
    app.include_router(media_api.router)

    def database():
        with Session(svc.db.bind, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[require_admin] = lambda: AdminUser(id=str(ACTOR), email=None, roles=['admin'])
    app.dependency_overrides[social_api.service] = lambda db=Depends(get_db): SocialService(
        db, available_adapters=REGISTRY, media_runtime=svc.runtime)
    app.dependency_overrides[media_api.service] = lambda db=Depends(get_db): MediaService(db, svc.runtime)
    return TestClient(app, raise_server_exceptions=False)


def automated_flags_are_off(client):
    result = client.get(BASE + '/system/status')
    assert result.status_code == 200, result.text
    status = result.json()
    for field in ('generation_enabled', 'auto_approve_enabled', 'auto_schedule_enabled', 'auto_publish_enabled'):
        assert status[field] is False
    return status


@pytest.mark.parametrize('separate_review', [False, True])
def test_add_media_review_then_explicit_publish_works_without_automation(media, separate_review):
    svc, storage = media
    destination = account(svc.db)
    client = mounted_client(media)
    assert automated_flags_are_off(client)['publishing_enabled'] is False
    readiness=client.get(BASE+'/accounts/'+str(destination.id)+'/publishing')
    assert readiness.status_code==200, readiness.text
    observed=readiness.json()
    account_key=headers()
    enabled=client.patch(BASE+'/accounts/'+str(destination.id)+'/publishing', json={
        'expected_controls_version':observed['controls_version'], 'expected_state':observed['state_token'],
        'publishing_enabled':True, 'reason':'Synthetic human account consent'}, headers=account_key)
    assert enabled.status_code==200, enabled.text
    assert enabled.json()['publishing_enabled'] is True
    assert enabled.json()['global_publishing_enabled'] is False


    upload_key = headers()
    grant = client.post(BASE + '/media/uploads', json=intent(), headers=upload_key)
    assert grant.status_code == 201, grant.text
    asset = grant.json()['asset']
    repeated = client.post(BASE + '/media/uploads', json=intent(), headers=upload_key)
    assert repeated.status_code == 201, repeated.text
    # Replays may issue a shorter-lived signed grant; the asset is immutable.
    assert repeated.json()['asset'] == asset
    storage.objects[storage.last_key] = (png(), 'image/png', None)
    completed = client.post(BASE + '/media/uploads/' + asset['id'] + '/complete',
                            json={'expected_version': 1}, headers=headers())
    assert completed.status_code == 200, completed.text
    assert completed.json()['state'] == 'ready'
    assert completed.json()['sha256'] is not None
    preview = client.get(BASE + '/media/assets/' + asset['id'] + '/preview')
    assert preview.status_code == 200, preview.text

    document = {
        'master': {'text': 'Review this county report on AuditGava.',
                   'link': 'https://www.auditgava.com/counties/mombasa-county?tab=budget#pending-bills',
                   'hashtags': ['Mombasa', 'PendingBills'],
                   'media': [{'asset_id': asset['id'], 'alt_text': 'A green inspection fixture'}]},
        'targets': [{'account_id': str(destination.id), 'format': 'image', 'overrides': {}}],
    }
    created = client.post(BASE + '/posts', json={'title': 'Human-reviewed county report',
                          'content_type': 'announcement', 'document': document, 'references': []}, headers=headers())
    assert created.status_code == 201, created.text
    post = created.json()
    path = BASE + '/posts/' + post['id']
    validation = client.post(path + '/validate', json={'expected_version': post['version']})
    assert validation.status_code == 200, validation.text
    result = validation.json()
    assert result['valid'] is True
    resolved = result['targets'][0]['resolved_preview']
    assert resolved['link'] == document['master']['link']
    assert resolved['hashtags'] == document['master']['hashtags']
    assert resolved['assets'][0]['sha256'] == completed.json()['sha256']
    assert resolved['assets'][0]['asset_id'] == asset['id']

    if separate_review:
        pending = client.post(path + '/submit', json={'expected_version': post['version']}, headers=headers())
        assert pending.status_code == 200, pending.text
        post = pending.json()
        assert post['editorial_state'] == 'pending_review'
        approved = client.post(path + '/approve', json={'expected_version': post['version'],
                                'revision_id': post['revision_id']}, headers=headers())
        assert approved.status_code == 200, approved.text
        post = approved.json()
        assert post['targets'][0]['state'] == 'ready'

    command = {'expected_version': post['version'], 'revision_id': post['revision_id'],
               'acknowledged_warning_codes': sorted({w['code'] for w in result['warnings']} |
                   {w['code'] for t in result['targets'] for w in t['warnings']})}
    paused = client.post(path + '/publish', json=command, headers=headers())
    assert paused.status_code == 409, paused.text
    assert paused.json()['detail']['code'] == 'PUBLISHING_PAUSED'
    svc.db.expire_all()
    assert svc.db.scalar(select(func.count()).select_from(SocialPublishAttempt)) == 0
    svc.db.rollback()

    # Explicit test-local operator action; no environment/default activation.
    enabled = client.patch(BASE + '/controls', json={'expected_version': automated_flags_are_off(client)['controls_version'],
                           'publishing_enabled': True, 'reason': 'Inert mounted-API fixture only'}, headers=headers())
    assert enabled.status_code == 200, enabled.text
    publish_key = headers()
    accepted = client.post(path + '/publish', json=command, headers=publish_key)
    assert accepted.status_code == 202, accepted.text
    assert client.post(path + '/publish', json=command, headers=publish_key).json() == accepted.json()
    assert accepted.json()['status'] == 'queued'
    assert accepted.json()['targets'][0]['status'] == 'queued'
    detail = client.get(path)
    assert detail.status_code == 200, detail.text
    assert detail.json()['targets'][0]['state'] == 'queued'
    assert detail.json()['targets'][0]['published_at'] is None
    assert automated_flags_are_off(client)['publishing_enabled'] is True
    svc.db.expire_all()
    publication = svc.db.get(SocialPublication, UUID(accepted.json()['publication_id']))
    assert publication.authorization_kind == 'human'
    assert publication.approved_by == ACTOR
    assert svc.db.scalar(select(func.count()).select_from(SocialPublication)) == 1
    assert svc.db.scalar(select(func.count()).select_from(SocialPostTarget)) == 1
    assert svc.db.scalar(select(func.count()).select_from(SocialPublishAttempt)) == 0


def test_disabled_media_runtime_does_not_grant_uploads_or_change_publishing(media):
    svc, storage = media
    svc.runtime = MediaRuntime(MediaConfig(), None, None, 'Uploads are paused.')
    client = mounted_client(media)
    before = automated_flags_are_off(client)
    assert before['media_upload_available'] is False
    response = client.post(BASE + '/media/uploads', json=intent(), headers=headers())
    assert response.status_code == 503, response.text
    assert response.json()['detail']['code'] == 'MEDIA_UNAVAILABLE'
    after = automated_flags_are_off(client)
    assert after['publishing_enabled'] is False
    assert storage.operations == []
    assert svc.db.get(SocialControls, 1) is None
