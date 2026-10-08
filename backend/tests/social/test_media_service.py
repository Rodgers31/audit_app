from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from social.media.contracts import UploadIntent
from social.media.models import SocialMediaBudget, SocialMediaUpload
from social.media.runtime import MediaRuntime
from social.media.service import MediaService
from social.models import SocialAuditEvent, SocialMediaAsset
from social.service import SocialError
from test_media_support import ACTOR, intent, media, media_db, png, upload_ready, settle_writes


def test_actual_upload_replay_library_private_preview_and_audit(media):
    svc, storage = media; key = uuid4(); data = png()
    grant = svc.initiate(ACTOR, key, intent(alt_text='Green field'), uuid4())
    assert grant.asset.state == 'pending'
    assert grant.asset.sha256 is None and grant.asset.mime_type is None and grant.asset.byte_size is None
    assert svc.initiate(ACTOR, key, intent(alt_text='Green field'), uuid4()).asset == grant.asset
    storage.objects[storage.last_key] = (data, 'image/png', None)
    completion = uuid4()
    result = svc.complete(ACTOR, grant.asset.id, completion, 1, uuid4())
    assert result.state == 'ready' and result.version == 2 and result.width == 64 and result.height == 32
    assert result.byte_size == len(data) and len(result.sha256) == 64
    assert svc.complete(ACTOR, grant.asset.id, completion, 1, uuid4()) == result
    assert svc.library(query='actual', kind='image').assets == (result,)
    assert svc.library(query='%').total == 0
    preview = svc.preview(result.id)
    assert 'preview-secret' in preview.url and 'url' not in result.model_dump()
    assert result.default_alt_text == 'Green field'
    with svc.db.begin():
        assert svc.db.get(SocialMediaBudget, 'global').pending_count == 1
        events = svc.db.scalars(select(SocialAuditEvent)).all()
        assert [e.action for e in events] == ['media.upload_initiated', 'media.inspection_started', 'media.inspection_ready']
        assert 'secret' not in str([e.details for e in events])


def test_cross_admin_reuse_but_not_complete(media):
    svc, storage = media
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    with pytest.raises(SocialError) as error: svc.complete(uuid4(), grant.asset.id, uuid4(), 1, uuid4())
    assert error.value.status == 403
    storage.objects[storage.last_key] = (png(), 'image/png', None)
    result = svc.complete(ACTOR, grant.asset.id, uuid4(), 1, uuid4())
    assert svc.library().assets[0].id == result.id
    assert svc.preview(result.id).asset.id == result.id


def test_quota_idempotency_conflicts_and_wrong_versions(media):
    svc, storage = media; key = uuid4()
    grant = svc.initiate(ACTOR, key, intent(), uuid4())
    with pytest.raises(SocialError, match='IDEMPOTENCY_CONFLICT'): svc.initiate(ACTOR, key, intent(filename='different.png'), uuid4())
    with pytest.raises(SocialError, match='VERSION_CONFLICT'): svc.complete(ACTOR, grant.asset.id, uuid4(), 2, uuid4())
    for _ in range(2): svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    with pytest.raises(SocialError, match='MEDIA_QUOTA_EXCEEDED'): svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    small = replace(svc.config, actor_quota_bytes=len(png()), total_quota_bytes=len(png()))
    limited = MediaService(svc.db, MediaRuntime(small, storage, svc.runtime.inspector))
    with pytest.raises(SocialError, match='MEDIA_QUOTA_EXCEEDED'): limited.initiate(uuid4(), uuid4(), intent(), uuid4())


def test_storage_retry_preserves_key_and_no_database_transaction_during_io(media):
    svc, storage = media
    storage.hook = lambda operation: (_ for _ in ()).throw(AssertionError('I/O inside SQL transaction')) if svc.db.in_transaction() else None
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4()); key = uuid4()
    with pytest.raises(SocialError, match='MEDIA_STORAGE_UNAVAILABLE'): svc.complete(ACTOR, grant.asset.id, key, 1, uuid4())
    with pytest.raises(SocialError, match='IDEMPOTENCY_CONFLICT'): svc.complete(ACTOR, grant.asset.id, uuid4(), 1, uuid4())
    storage.objects[storage.last_key] = (png(), 'image/png', None)
    assert svc.complete(ACTOR, grant.asset.id, key, 1, uuid4()).state == 'ready'


def test_failed_bytes_are_never_library_ready_and_keep_unknown_browser_capacity(media):
    svc, storage = media; bad = b'not actually PNG'
    grant = svc.initiate(ACTOR, uuid4(), intent(bad), uuid4())
    storage.objects[storage.last_key] = (bad, 'image/png', None); key = uuid4()
    for _ in range(2):
        with pytest.raises(SocialError, match='MEDIA_INSPECTION_FAILED'): svc.complete(ACTOR, grant.asset.id, key, 1, uuid4())
    assert svc.library().total == 0
    with svc.db.begin():
        assert svc.db.get(SocialMediaBudget, 'global').pending_count == 1
        asset = svc.db.get(SocialMediaAsset, grant.asset.id)
        assert asset.state == 'failed' and asset.sha256 is None


def test_active_and_stale_lease_fences(media):
    svc, storage = media; grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4()); key = uuid4()
    with svc.db.begin():
        asset = svc.db.get(SocialMediaAsset, grant.asset.id)
        asset.lease_token = uuid4(); asset.lease_expires_at = svc.now() + timedelta(seconds=60)
    with pytest.raises(SocialError, match='MEDIA_INSPECTION_BUSY'): svc.complete(ACTOR, grant.asset.id, key, 1, uuid4())
    with svc.db.begin():
        asset.lease_expires_at = svc.now() - timedelta(seconds=1)
    storage.objects[storage.last_key] = (png(), 'image/png', None)
    def expired(operation):
        if operation == 'finalize':
            with svc.db.begin():
                svc.db.get(SocialMediaAsset, grant.asset.id).lease_expires_at = svc.now() - timedelta(seconds=1)
    storage.hook = expired
    with pytest.raises(SocialError, match='MEDIA_LEASE_LOST'): svc.complete(ACTOR, grant.asset.id, key, 1, uuid4())
    assert svc.library().total == 0
    storage.hook = None
    assert svc.complete(ACTOR, grant.asset.id, key, 1, uuid4()).state == 'ready'


def test_expiry_cleanup_budget_storage_failure_and_ready_retention(media):
    svc, storage = media
    ready = upload_ready(media)
    pending = svc.initiate(ACTOR, uuid4(), intent(), uuid4()).asset
    with svc.db.begin():
        for row in svc.db.scalars(select(SocialMediaUpload)): row.expires_at = svc.now() - timedelta(seconds=1)
    with pytest.raises(SocialError, match='UPLOAD_EXPIRED'): svc.complete(ACTOR, pending.id, uuid4(), 1, uuid4())
    ready = settle_writes(svc, ready.id)
    settle_writes(svc, pending.id)
    assert svc.cleanup() == 2
    assert svc.library().assets == (ready,)
    assert svc.preview(ready.id).asset.state == 'ready'
    assert svc.cleanup() == 0  # ready quarantine should not starve later orphan batches.
    with svc.db.begin():
        assert svc.db.get(SocialMediaBudget, 'global').bytes_used == len(png())
        assert svc.db.get(SocialMediaBudget, 'global').pending_count == 0


def test_storage_identity_change_prevents_preview(media):
    svc, storage = media; ready = upload_ready(media)
    key = next(k for k in storage.objects if k.startswith('ready/'))
    storage.objects[key] = (b'changed bytes', 'image/png', ready.sha256)
    with pytest.raises(SocialError, match='MEDIA_STORAGE_UNAVAILABLE'): svc.preview(ready.id)


@pytest.mark.parametrize('value', [True, False, 0, -1, float('nan'), float('inf'), None])
def test_direct_service_guards(media, value):
    svc, _ = media
    with pytest.raises(SocialError): svc.complete(ACTOR, uuid4(), uuid4(), value, uuid4())
    with pytest.raises(SocialError): svc.library(page_size=value)
    with pytest.raises(SocialError): svc.cleanup(value)
