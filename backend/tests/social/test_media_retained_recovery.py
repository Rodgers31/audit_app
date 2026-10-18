from dataclasses import replace
import json
from datetime import timedelta
from uuid import uuid4

import pytest

from social.media.models import SocialMediaBudget, SocialMediaUpload
from social.media.retention import MARKER, recover_retained, retain_ready
from social.media.runtime import MediaRuntime
from social.media.service import MediaService
from social.media.storage import StorageFailure
from social.models import SocialMediaAsset
from social.service import SocialError
from test_media_support import ACTOR, media, media_db, png, intent


def retained(media):
    original, storage = media
    config = replace(original.config, retained_writes_enabled=True)
    storage.retained_create_only = True
    return MediaService(original.db, MediaRuntime(config, storage, original.runtime.inspector)), storage


def historical(media):
    """Record the conditional protocol at admission, without retaining yet."""
    original, storage = media
    storage.retained_create_only = storage.permanent_payload_fence = True
    config = replace(original.config, fenced_retirement_enabled=True)
    return MediaService(original.db, replace(original.runtime, config=config)), storage


def initiate(svc, storage):
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    storage.objects[storage.last_key] = (png(), 'image/png', None)
    return grant.asset.id, uuid4()


def test_completion_frees_pending_but_retains_both_copies_and_all_bytes(media):
    svc, storage = retained(media)
    for _ in range(4):
        identity, key = initiate(svc, storage)
        ready = svc.complete(ACTOR, identity, key, 1, uuid4())
        assert ready.version == 2
        assert svc.complete(ACTOR, identity, key, 1, uuid4()) == ready
    with svc.db.begin():
        budget = svc.db.get(SocialMediaBudget, 'global')
        assert budget.pending_count == 0 and budget.bytes_used == 8 * len(png())
        upload = svc.db.get(SocialMediaUpload, identity)
        assert upload.reserved_bytes == 2 * len(png())
        assert upload.grant_settled_epoch == 0 and upload.grant_epoch == 1
        assert not upload.reservation_released and not upload.quarantine_cleaned
        assert json.loads(upload.retained_write_fence)['version'] == 1
    assert len(storage.objects) == 8 and 'delete' not in storage.operations


def test_retained_fence_never_becomes_cleanup_after_expiry(media):
    svc, storage = retained(media); identity, key = initiate(svc, storage)
    svc.complete(ACTOR, identity, key, 1, uuid4())
    with svc.db.begin():
        row = svc.db.get(SocialMediaUpload, identity)
        row.expires_at = svc.now() - timedelta(days=20)
        # Database constraints forbid marking this retained fence as drained.
    before = dict(storage.objects)
    assert svc.cleanup() == 0
    assert before == storage.objects and 'delete' not in storage.operations


def test_unknown_creation_is_explicitly_recovered_with_same_original(media):
    svc, storage = retained(media); identity, key = initiate(svc, storage)
    original = storage.finalize
    def lost(*args):
        original(*args)
        raise StorageFailure('lost response')
    storage.finalize = lost
    with pytest.raises(SocialError, match='MEDIA_FINALIZATION_UNKNOWN'):
        svc.complete(ACTOR, identity, key, 1, uuid4())
    before = dict(storage.objects)
    storage.finalize = original
    with svc.db.begin():
        asset = svc.db.get(SocialMediaAsset, identity)
        asset.lease_expires_at = svc.now() - timedelta(seconds=1)
        upload = svc.db.get(SocialMediaUpload, identity)
        expected = {'expected_version':upload.version,'expected_grant_epoch':upload.grant_epoch,
            'expected_finalization_epoch':upload.finalization_epoch}
        upload.expires_at = svc.now() - timedelta(days=1)
    with pytest.raises(SocialError, match='MEDIA_FINALIZATION_UNKNOWN'):
        svc.complete(ACTOR, identity, key, 1, uuid4())
    ready = recover_retained(svc, ACTOR, identity, expected, uuid4())
    assert ready.state == 'ready' and ready.version == 2
    assert storage.objects == before and 'delete' not in storage.operations
    with svc.db.begin():
        assert svc.db.get(SocialMediaBudget, 'global').pending_count == 0
        assert svc.db.get(SocialMediaBudget, 'global').bytes_used == 2 * len(png())


@pytest.mark.parametrize('damage', ['quarantine_missing','quarantine_changed','original_changed','lease_lost','version_changed','ledger_drift'])
def test_failed_retention_keeps_pending_and_all_bytes(media, damage):
    original, storage = historical(media)
    identity, key = initiate(original, storage)
    original.complete(ACTOR, identity, key, 1, uuid4())
    svc, _ = retained(media)
    with svc.db.begin():
        upload = svc.db.get(SocialMediaUpload, identity)
        asset = svc.db.get(SocialMediaAsset, identity)
        quarantine, final = upload.quarantine_key, asset.storage_key
    if damage == 'quarantine_missing': storage.objects.pop(quarantine)
    if damage == 'quarantine_changed': storage.objects[quarantine] = (b'x'*len(png()),'image/png',None)
    if damage == 'original_changed': storage.objects[final] = (b'x'*len(png()),'image/png','a'*64)
    def hook(operation):
        if operation == 'download' and damage in {'lease_lost','version_changed','ledger_drift'}:
            storage.hook = None
            with svc.db.begin():
                if damage == 'lease_lost': svc.db.get(SocialMediaAsset, identity).lease_expires_at = svc.now()-timedelta(seconds=1)
                if damage == 'version_changed': svc.db.get(SocialMediaUpload, identity).version += 1
                if damage == 'ledger_drift': svc.db.get(SocialMediaUpload, identity).reserved_bytes -= 1
    storage.hook = hook
    with pytest.raises(SocialError): retain_ready(svc, ACTOR, identity, 2, uuid4())
    with svc.db.begin():
        assert svc.db.get(SocialMediaBudget, 'global').pending_count == 1
        assert svc.db.get(SocialMediaUpload, identity).retained_write_fence is None
    assert 'delete' not in storage.operations


def test_metadata_io_occurs_outside_transactions_and_default_stays_off(media):
    svc, storage = historical(media); identity, key = initiate(svc, storage)
    svc.complete(ACTOR, identity, key, 1, uuid4())
    with pytest.raises(SocialError, match='MEDIA_RECOVERY_UNAVAILABLE'):
        retain_ready(svc, ACTOR, identity, 2, uuid4())
    svc, _ = retained(media)
    storage.hook = lambda op: pytest.fail('I/O inside transaction') if svc.db.in_transaction() else None
    assert retain_ready(svc, ACTOR, identity, 2, uuid4()).state == 'ready'


@pytest.mark.parametrize('field', ['expected_version','expected_grant_epoch','expected_finalization_epoch'])
def test_recovery_rejects_stale_scope_and_boolean_versions(media, field):
    svc, storage = retained(media); identity, key = initiate(svc, storage)
    svc.complete(ACTOR, identity, key, 1, uuid4())
    with svc.db.begin():
        row = svc.db.get(SocialMediaUpload, identity)
        values = {'expected_version':row.version,'expected_grant_epoch':row.grant_epoch,
            'expected_finalization_epoch':row.finalization_epoch}
    values[field] = True
    with pytest.raises(Exception): recover_retained(svc, ACTOR, identity, values, uuid4())


@pytest.mark.parametrize('scope', ['global', f'actor:{ACTOR}'])
def test_repeated_retention_refuses_lost_byte_accounting(media, scope):
    svc, storage = retained(media); identity, key = initiate(svc, storage)
    svc.complete(ACTOR, identity, key, 1, uuid4())
    with svc.db.begin():
        svc.db.get(SocialMediaBudget, scope).bytes_used = 0
    with pytest.raises(SocialError, match='MEDIA_RETENTION_INVALID'):
        retain_ready(svc, ACTOR, identity, 2, uuid4())


def test_reconciliation_cannot_invalidate_retained_history(media):
    from social.media.reconciliation import WriteQuiescenceReceipt
    svc, storage = retained(media); identity, key = initiate(svc, storage)
    first = svc.complete(ACTOR, identity, key, 1, uuid4())
    scope = {'expected_version': 2, 'expected_grant_epoch': 1, 'expected_finalization_epoch': 1}
    with pytest.raises(SocialError, match='MEDIA_RETENTION_INVALID'):
        svc.reconcile(ACTOR, identity, {**scope, 'receipt': WriteQuiescenceReceipt(
            receipt_id=uuid4(), evidence_hash='a'*64)}, uuid4())
    assert recover_retained(svc, ACTOR, identity, scope, uuid4()) == first


def test_retention_rechecks_both_byte_ledgers_after_storage_io(media):
    original, storage = historical(media)
    identity, key = initiate(original, storage)
    original.complete(ACTOR, identity, key, 1, uuid4())
    svc, _ = retained(media)
    def drift(operation):
        if operation == 'download':
            storage.hook = None
            with svc.db.begin():
                svc.db.get(SocialMediaBudget, 'global').bytes_used = 0
    storage.hook = drift
    with pytest.raises(SocialError, match='MEDIA_RETENTION_INVALID'):
        retain_ready(svc, ACTOR, identity, 2, uuid4())
    with svc.db.begin():
        assert svc.db.get(SocialMediaUpload, identity).retained_write_fence is None
        assert svc.db.get(SocialMediaBudget, 'global').pending_count == 1


@pytest.mark.parametrize('value', [True, 1.0])
def test_corrupt_retained_marker_version_never_certifies_success(media, value):
    from sqlalchemy import update
    svc, storage = retained(media); identity, key = initiate(svc, storage)
    svc.complete(ACTOR, identity, key, 1, uuid4())
    # SQLite permits raw privileged corruption; real PostgreSQL's immutable
    # trigger additionally rejects this update. The reader must still refuse it.
    with svc.db.begin():
        upload = svc.db.get(SocialMediaUpload, identity)
        marker = json.loads(upload.retained_write_fence)
        marker['version'] = value
        svc.db.execute(update(SocialMediaUpload).where(SocialMediaUpload.asset_id == identity)
            .values(retained_write_fence=json.dumps(marker)))
    with pytest.raises(SocialError, match='MEDIA_RETENTION_INVALID'):
        retain_ready(svc, ACTOR, identity, 2, uuid4())
