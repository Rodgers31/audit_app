"""Inert regressions: stored keys cannot redirect recovery or deletion."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from social.media.models import SocialMediaBudget, SocialMediaUpload
from social.media.operator import prepare_reconciliation
from social.models import SocialMediaAsset
from social.service import SocialError
from test_media_support import ACTOR, intent, media, media_db, png, settle_writes, upload_ready


def snapshot(svc):
    with svc.db.begin():
        return (
            [(u.asset_id, u.version, u.reserved_bytes, u.pending_released,
              u.reservation_released, u.quarantine_cleaned, u.grant_epoch,
              u.grant_settled_epoch, u.finalization_epoch, u.finalization_settled)
             for u in svc.db.scalars(select(SocialMediaUpload).order_by(SocialMediaUpload.asset_id))],
            [(a.id, a.state, a.lease_token, a.lease_epoch, a.deleted_at)
             for a in svc.db.scalars(select(SocialMediaAsset).order_by(SocialMediaAsset.id))],
            [(b.scope, b.bytes_used, b.pending_count)
             for b in svc.db.scalars(select(SocialMediaBudget).order_by(SocialMediaBudget.scope))],
        )


def test_cleanup_cannot_delete_another_ready_original_via_quarantine_key(media):
    svc, store = media
    victim = upload_ready(media)
    target = svc.initiate(ACTOR, uuid4(), intent(), uuid4()).asset
    settle_writes(svc, target.id)
    with svc.db.begin():
        row = svc.db.get(SocialMediaUpload, target.id)
        row.quarantine_key = f'ready/{victim.id}/original'
        row.expires_at = svc.now() - timedelta(days=1)
    objects, calls, before = dict(store.objects), list(store.operations), snapshot(svc)
    assert svc.cleanup() == 0
    assert store.objects == objects and store.operations == calls
    assert snapshot(svc) == before
    assert svc.preview(victim.id).asset.state == 'ready'


@pytest.mark.parametrize('column,value', [
    ('quarantine_key', 'quarantine/wrong-actor/source'),
    ('quarantine_key', 'ready/unrelated/original'),
    ('storage_key', 'quarantine/arbitrary/source'),
    ('storage_key', 'ready/../original'),
])
@pytest.mark.parametrize('command', ['initiate', 'complete', 'reconcile'])
def test_mutation_refuses_wrong_object_identity_before_io_or_accounting(media, column, value, command):
    svc, store = media
    initiation = uuid4()
    target = svc.initiate(ACTOR, initiation, intent(), uuid4()).asset
    store.objects[store.last_key] = (png(), 'image/png', None)
    with svc.db.begin():
        model = SocialMediaUpload if column == 'quarantine_key' else SocialMediaAsset
        setattr(svc.db.get(model, target.id), column, value)
    before, objects, calls = snapshot(svc), dict(store.objects), list(store.operations)
    for _ in range(2):
        with pytest.raises(SocialError, match='MEDIA_OBJECT_IDENTITY_MISMATCH'):
            if command == 'initiate':
                svc.initiate(ACTOR, initiation, intent(), uuid4())
            elif command == 'complete':
                svc.complete(ACTOR, target.id, uuid4(), 1, uuid4())
            else:
                from social.media.reconciliation import WriteQuiescenceReceipt
                svc.reconcile(ACTOR, target.id, {
                    'expected_version': 1, 'expected_grant_epoch': 1,
                    'expected_finalization_epoch': None,
                    'receipt': WriteQuiescenceReceipt(receipt_id=uuid4(), evidence_hash='a'*64),
                }, uuid4())
        assert store.operations == calls and store.objects == objects
        assert snapshot(svc) == before


def test_malformed_oldest_candidate_does_not_starve_valid_cleanup(media):
    svc, store = media
    bad = svc.initiate(ACTOR, uuid4(), intent(), uuid4()).asset
    good = svc.initiate(ACTOR, uuid4(), intent(), uuid4()).asset
    for asset in (bad, good): settle_writes(svc, asset.id)
    with svc.db.begin():
        row = svc.db.get(SocialMediaUpload, bad.id)
        row.quarantine_key = 'ready/private-victim/original'
        row.expires_at = svc.now() - timedelta(days=2)
        svc.db.get(SocialMediaUpload, good.id).expires_at = svc.now() - timedelta(days=1)
    store.objects['ready/private-victim/original'] = (png(), 'image/png', None)
    before = prepare_reconciliation(svc)
    observation = next(row for row in before.uploads if row.asset_id == bad.id)
    assert 'OBJECT_IDENTITY_MISMATCH' in observation.reason_codes
    assert not any('CLEANUP_CANDIDATE' in code for code in observation.reason_codes)
    assert 'private-victim' not in before.model_dump_json()
    assert svc.backlog().eligible_cleanup == 1
    assert svc.cleanup(limit=1) == 1 and svc.cleanup(limit=1) == 0
    assert 'ready/private-victim/original' in store.objects
    with svc.db.begin():
        assert svc.db.get(SocialMediaUpload, bad.id).reservation_released == 0
        assert svc.db.get(SocialMediaUpload, good.id).reservation_released == 1
        assert svc.db.get(SocialMediaBudget, 'global').bytes_used == 2 * len(png())
