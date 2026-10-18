"""Historical recovery requires admission-time protocol, never today's port flag."""
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from social.media.fencing import WRITE_PROTOCOL
from social.media.models import SocialMediaBudget, SocialMediaUpload
from social.media.retention import recover_retained, retain_ready
from social.media.runtime import MediaRuntime
from social.media.service import MediaService
from social.media.storage import StorageFailure
from social.models import SocialMediaAsset
from social.service import SocialError
from test_media_support import ACTOR, intent, media, media_db, png


def legacy(media, *, known):
    svc, storage = media
    storage.retained_create_only = True
    # A historical, recorded protocol is inserted at original allocation, not
    # backfilled during recovery. The production DB forbids later changes.
    if known:
        storage.permanent_payload_fence = True
        config = replace(svc.config, fenced_retirement_enabled=True)
        svc = MediaService(svc.db, replace(svc.runtime, config=config))
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    storage.objects[storage.last_key] = (png(), 'image/png', None)
    return svc, storage, grant.asset.id, uuid4()


def recovery_service(svc):
    config = replace(svc.config, retained_writes_enabled=True)
    return MediaService(svc.db, replace(svc.runtime, config=config))


def observed(svc, identity):
    with svc.db.begin():
        u = svc.db.get(SocialMediaUpload, identity)
        return dict(expected_version=u.version, expected_grant_epoch=u.grant_epoch,
                    expected_finalization_epoch=u.finalization_epoch)


@pytest.mark.parametrize('entry', ['retain', 'recover', 'complete_replay'])
def test_current_storage_capability_never_certifies_unknown_legacy_history(media, entry):
    svc, storage, identity, key = legacy(media, known=False)
    svc.complete(ACTOR, identity, key, 1, uuid4())
    svc = recovery_service(svc)
    before = list(storage.operations)
    with pytest.raises(SocialError, match='MEDIA_WRITE_HISTORY_UNPROVEN'):
        if entry == 'retain':
            retain_ready(svc, ACTOR, identity, 2, uuid4())
        elif entry == 'recover':
            recover_retained(svc, ACTOR, identity, observed(svc, identity), uuid4())
        else:
            svc.complete(ACTOR, identity, key, 1, uuid4())
    assert storage.operations == before
    with svc.db.begin():
        u = svc.db.get(SocialMediaUpload, identity)
        assert u.write_protocol is None and u.retained_write_fence is None
        assert not u.pending_released and not u.reservation_released
        assert svc.db.get(SocialMediaBudget, 'global').bytes_used == 2 * len(png())


def test_unknown_legacy_lost_reply_is_refused_before_another_put(media):
    svc, storage, identity, key = legacy(media, known=False)
    finalize = storage.finalize
    def lost(*args):
        finalize(*args)
        raise StorageFailure('synthetic lost acknowledgement')
    storage.finalize = lost
    with pytest.raises(SocialError, match='MEDIA_FINALIZATION_UNKNOWN'):
        svc.complete(ACTOR, identity, key, 1, uuid4())
    storage.finalize = finalize
    with svc.db.begin():
        svc.db.get(SocialMediaAsset, identity).lease_expires_at = svc.now() - timedelta(seconds=1)
    svc = recovery_service(svc)
    body = observed(svc, identity)
    before = list(storage.operations)
    with pytest.raises(SocialError, match='MEDIA_WRITE_HISTORY_UNPROVEN'):
        recover_retained(svc, ACTOR, identity, body, uuid4())
    assert storage.operations == before
    assert observed(svc, identity) == body


def test_recorded_historical_conditional_upload_recovers_and_replays(media):
    svc, storage, identity, key = legacy(media, known=True)
    svc.complete(ACTOR, identity, key, 1, uuid4())
    svc = recovery_service(svc)
    result = recover_retained(svc, ACTOR, identity, observed(svc, identity), uuid4())
    assert result.state == 'ready'
    assert recover_retained(svc, ACTOR, identity, observed(svc, identity), uuid4()) == result
    assert 'delete' not in storage.operations
    with svc.db.begin():
        u = svc.db.get(SocialMediaUpload, identity)
        assert u.write_protocol == WRITE_PROTOCOL and u.retained_write_fence
        assert u.pending_released and not u.reservation_released
        assert svc.db.get(SocialMediaBudget, 'global').bytes_used == 2 * len(png())


def test_new_retained_allocations_record_protocol_before_any_bearer(media):
    svc, storage = media
    storage.retained_create_only = True
    svc = recovery_service(svc)
    def check(operation):
        if operation == 'authorize':
            from sqlalchemy import select
            with svc.db.begin():
                assert svc.db.scalar(select(SocialMediaUpload.write_protocol)) == WRITE_PROTOCOL
    storage.hook = check
    svc.initiate(ACTOR, uuid4(), intent(), uuid4())


def test_suppressed_protocol_insert_never_issues_an_upload_bearer(media):
    from sqlalchemy import event
    svc, storage = media
    storage.retained_create_only = True
    svc = recovery_service(svc)
    def suppress(mapper, connection, row):
        row.write_protocol = None
    event.listen(SocialMediaUpload, 'before_insert', suppress)
    try:
        with pytest.raises(SocialError, match='MEDIA_WRITE_HISTORY_UNPROVEN'):
            svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    finally:
        event.remove(SocialMediaUpload, 'before_insert', suppress)
    assert storage.operations == []


def test_old_pending_intent_never_renews_without_recorded_history(media):
    svc, storage = media
    key = uuid4()
    result = svc.initiate(ACTOR, key, intent(), uuid4())
    storage.retained_create_only = True
    svc = recovery_service(svc)
    before = list(storage.operations)
    with pytest.raises(SocialError, match='MEDIA_WRITE_HISTORY_UNPROVEN'):
        svc.initiate(ACTOR, key, intent(), uuid4())
    assert storage.operations == before
    with svc.db.begin():
        u = svc.db.get(SocialMediaUpload, result.asset.id)
        assert u.write_protocol is None and u.grant_epoch == 1
