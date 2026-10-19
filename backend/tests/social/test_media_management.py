from uuid import uuid4
from datetime import timedelta

import pytest
from sqlalchemy import select, func, text

from social.media.models import SocialMediaBudget, SocialMediaUpload
from social.models import SocialAuditEvent, SocialMediaAsset, SocialPost, SocialPostRevision, SocialRevisionAsset
from social.service import SocialError
from test_media_support import ACTOR, media, media_db, upload_ready, settle_writes


def archive(svc, asset, key=None, version=None):
    return svc.archive_asset(ACTOR, asset.id, key or uuid4(),
        {'expected_version': version or asset.version, 'reason': 'Unused editorial asset'}, uuid4())


def settled(media):
    svc, storage = media
    asset = upload_ready(media)
    asset = settle_writes(svc, asset.id)
    return asset


def test_unused_archive_retains_bytes_quota_audit_and_replays(media):
    svc, storage = media
    asset = settled(media)
    before_objects = dict(storage.objects)
    before_io = list(storage.operations)
    with svc.db.begin():
        before_budget = [(b.scope, b.bytes_used, b.pending_count) for b in svc.db.scalars(select(SocialMediaBudget).order_by(SocialMediaBudget.scope))]
    usage = svc.asset_usage(asset.id)
    assert usage.total == 0 and usage.archive_eligible
    key = uuid4()
    result = archive(svc, asset, key)
    assert result.state == 'archived' and result.version == asset.version + 1
    assert archive(svc, asset, key) == result
    assert svc.library().total == 0
    assert not svc.asset_usage(asset.id).archive_eligible
    assert storage.objects == before_objects and storage.operations == before_io
    with svc.db.begin():
        svc.db.get(SocialMediaUpload, asset.id).expires_at = svc.now() - timedelta(days=30)
    assert svc.cleanup(20) == 0
    assert storage.objects == before_objects and storage.operations == before_io
    with svc.db.begin():
        assert [(b.scope, b.bytes_used, b.pending_count) for b in svc.db.scalars(select(SocialMediaBudget).order_by(SocialMediaBudget.scope))] == before_budget
        assert svc.db.scalar(select(func.count()).select_from(SocialAuditEvent).where(SocialAuditEvent.action == 'media.asset_archived')) == 1


def referenced(svc, asset):
    with svc.db.begin():
        p = SocialPost(id=uuid4(), title='Historical evidence', content_type='announcement', origin_type='manual', creation_method='admin', editorial_state='archived', created_by=ACTOR)
        svc.db.add(p); svc.db.flush()
        for number in range(1, 4):
            r = SocialPostRevision(id=uuid4(), post_id=p.id, revision_no=number, document={}, content_hash=str(number)*64, evidence_snapshot={}, created_by=ACTOR)
            svc.db.add(r); svc.db.flush()
            svc.db.add(SocialRevisionAsset(revision_id=r.id, asset_id=asset.id))
    return p


def test_historical_reference_detail_is_bounded_and_protects_archive(media):
    svc, _ = media; asset = settled(media); p = referenced(svc, asset)
    usage = svc.asset_usage(asset.id, page=2, page_size=2)
    assert usage.total == 3 and len(usage.references) == 1 and not usage.has_more
    assert usage.references[0].post_id == p.id
    assert not usage.archive_eligible
    with pytest.raises(SocialError, match='MEDIA_ARCHIVE_BLOCKED'): archive(svc, asset)


def test_unknown_or_active_writes_refuse_without_storage_io(media):
    svc, storage = media; asset = upload_ready(media); before = list(storage.operations)
    assert not svc.asset_usage(asset.id).archive_eligible
    with pytest.raises(SocialError, match='MEDIA_ARCHIVE_BLOCKED'): archive(svc, asset)
    assert storage.operations == before


def test_stale_version_and_changed_replay_input_refuse(media):
    svc, _ = media; asset = settled(media)
    with pytest.raises(SocialError, match='VERSION_CONFLICT'): archive(svc, asset, version=asset.version+1)
    key = uuid4(); archive(svc, asset, key)
    with pytest.raises(SocialError, match='IDEMPOTENCY_CONFLICT'): archive(svc, asset, key, asset.version+1)


@pytest.mark.parametrize('page,size', [(True, 20), (0, 20), (1_000_001, 20), (1, 51), (1, False)])
def test_direct_pagination_guards(media, page, size):
    svc, _ = media; asset = settled(media)
    with pytest.raises(SocialError, match='INVALID_REQUEST'): svc.asset_usage(asset.id, page, size)


def test_audit_failure_rolls_back_asset_and_receipt(media):
    svc, _ = media; asset = settled(media)
    with svc.db.begin():
        svc.db.execute(text("CREATE TRIGGER suppress_archive_audit BEFORE INSERT ON social_audit_events WHEN NEW.action='media.asset_archived' BEGIN SELECT RAISE(IGNORE); END"))
    with pytest.raises(SocialError, match='MEDIA_ARCHIVE_AUDIT_FAILED'): archive(svc, asset)
    with svc.db.begin(): assert svc.db.get(SocialMediaAsset, asset.id, populate_existing=True).state == 'ready'


def test_private_http_usage_archive_and_validation(media):
    from test_media_api import client, BASE, header
    svc, _ = media; asset = settled(media)
    path = BASE + '/assets/' + str(asset.id)
    api = client(media)
    usage = api.get(path + '/usage')
    assert usage.status_code == 200 and usage.json()['total'] == 0
    assert usage.headers['cache-control'] == 'private, no-store'
    body = {'expected_version': asset.version, 'reason': 'Unused asset'}
    for endpoint, method in [('/usage', 'get'), ('/archive', 'post')]:
        response = client(media, None).request(method, path + endpoint, json=body, headers=header())
        assert response.status_code in (401, 403)
        assert response.headers['cache-control'] == 'private, no-store'
    assert api.get(path + '/usage?page=1000001').status_code == 422
    for update in [{'expected_version': True}, {'reason': ' '}, {'reason': 'bad\nreason'}, {'extra': 'bad'}]:
        assert api.post(path + '/archive', json={**body, **update}, headers=header()).status_code == 422
    key = header()
    response = api.post(path + '/archive', json=body, headers=key)
    assert response.status_code == 200 and response.json()['state'] == 'archived', response.text
    assert api.post(path + '/archive', json=body, headers=key).json() == response.json()


def test_metadata_management_works_with_upload_and_storage_runtime_off(media):
    from social.media.config import MediaConfig
    from social.media.runtime import MediaRuntime
    from social.media.service import MediaService
    svc, storage = media; asset = settled(media); operations = list(storage.operations)
    disabled = MediaService(svc.db, MediaRuntime(MediaConfig(), None, None))
    assert not disabled.capabilities().upload_available
    assert disabled.asset_usage(asset.id).archive_eligible
    assert archive(disabled, asset).state == 'archived'
    assert storage.operations == operations
