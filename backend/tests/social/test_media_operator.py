"""Execute read-only inventory/ledger preparation without storage calls."""
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import sessionmaker

from social.media.maintenance import main, report_once
from social.media.models import SocialMediaBudget, SocialMediaUpload
from social.media.operator import prepare_reconciliation
from social.models import SocialMediaAsset
from social.service import SocialError
from test_media_support import ACTOR, intent, media, media_db, png, settle_writes, upload_ready


def test_report_preserves_unknown_epochs_two_copy_quota_and_makes_no_object_call(media):
    svc, store = media
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    with svc.db.begin():
        upload = svc.db.get(SocialMediaUpload, grant.asset.id)
        upload.finalization_epoch = 7
        upload.finalization_settled = 0
        upload.expires_at = svc.now() - timedelta(seconds=1)
    calls, statements = list(store.operations), []
    def trace(conn, cursor, statement, parameters, context, many): statements.append(statement)
    event.listen(svc.db.bind, 'before_cursor_execute', trace)
    try:
        report = report_once(sessionmaker(svc.db.bind), svc.runtime)
    finally:
        event.remove(svc.db.bind, 'before_cursor_execute', trace)
    assert store.operations == calls
    assert all(statement.lstrip().upper().startswith('SELECT') for statement in statements)
    assert report.ledger_reserved_bytes == report.upload_reserved_bytes == 2 * len(png())
    assert report.ledger_pending_uploads == report.upload_pending_held == 1
    assert report.actor_ledger_discrepancies == 0 and report.reason_codes == ()
    row, = report.uploads
    assert (row.asset_id, row.upload_version, row.grant_epoch, row.finalization_epoch) == (grant.asset.id, 1, 1, 7)
    assert row.reason_codes == ('BROWSER_WRITE_PROOF_REQUIRED', 'SERVER_WRITE_PROOF_REQUIRED')
    assert not report.quota_release_authorized and not report.write_quiescence_proven
    assert all(secret not in report.model_dump_json() for secret in ('quarantine/', 'ready/', 'fixture=', 'actual.png', str(ACTOR)))
    assert svc.cleanup() == 0


def test_report_does_not_invent_missing_ledger_or_repair_released_legacy_hazard(media):
    svc, _ = media
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    with svc.db.begin():
        upload = svc.db.get(SocialMediaUpload, grant.asset.id)
        upload.reserved_bytes = 0
        upload.reservation_released = upload.pending_released = upload.quarantine_cleaned = 1
        for budget in list(svc.db.scalars(select(SocialMediaBudget))): svc.db.delete(budget)
    report = prepare_reconciliation(svc)
    assert not report.global_ledger_present
    assert report.legacy_released_write_hazards == report.actor_ledger_discrepancies == 1
    assert 'GLOBAL_LEDGER_MISSING' in report.reason_codes
    assert 'LEGACY_WRITE_ACCOUNTING_GAP' in report.reason_codes
    assert report.ledger_reserved_bytes == report.upload_reserved_bytes == 0
    assert 'LEGACY_RELEASED_WRITE_HAZARD' in report.uploads[0].reason_codes
    with svc.db.begin(): assert list(svc.db.scalars(select(SocialMediaBudget))) == []


def test_report_detects_actor_and_global_drift_unmanaged_assets_and_surplus_scopes(media):
    svc, _ = media
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    with svc.db.begin():
        svc.db.get(SocialMediaBudget, 'global').bytes_used += 1
        svc.db.get(SocialMediaBudget, 'actor:' + str(ACTOR)).pending_count += 1
        svc.db.add(SocialMediaBudget(scope='actor:' + str(uuid4()), bytes_used=0, pending_count=0))
        svc.db.add(SocialMediaAsset(id=uuid4(), storage_provider='r2', bucket='other', storage_key='unmanaged/private-key', original_filename='private-filename', created_by=ACTOR, state='pending', lease_epoch=0, codec_metadata={}))
    report = prepare_reconciliation(svc)
    assert report.actor_ledger_discrepancies == 2 and report.assets_without_upload_ledger == 1
    assert set(report.reason_codes) == {'GLOBAL_LEDGER_MISMATCH', 'ACTOR_LEDGER_MISMATCH', 'ASSETS_WITHOUT_UPLOAD_LEDGER'}
    assert report.uploads[0].actor_upload_pending == 1 and report.uploads[0].actor_ledger_pending == 2
    assert report.uploads[0].asset_id == grant.asset.id


def test_report_has_bounded_keyset_pages_and_reloads_changed_epochs(media):
    svc, _ = media
    ids = [svc.initiate(uuid4(), uuid4(), intent(), uuid4()).asset.id for _ in range(4)]
    first = prepare_reconciliation(svc, limit=2)
    second = prepare_reconciliation(svc, limit=2, after_asset_id=first.next_after_asset_id)
    assert [r.asset_id for r in first.uploads + second.uploads] == sorted(ids)
    assert first.next_after_asset_id and second.next_after_asset_id is None
    with svc.db.begin(): svc.db.get(SocialMediaUpload, ids[0]).grant_epoch += 1
    refreshed = prepare_reconciliation(svc)
    assert next(r for r in refreshed.uploads if r.asset_id == ids[0]).grant_epoch == 2


def test_ready_cleanup_report_retains_original_and_actor_global_one_copy(media):
    svc, _ = media
    ready = upload_ready(media)
    with svc.db.begin(): svc.db.get(SocialMediaUpload, ready.id).expires_at = svc.now() - timedelta(seconds=1)
    settle_writes(svc, ready.id)
    before = prepare_reconciliation(svc)
    assert before.uploads[0].reason_codes == ('SETTLED_QUARANTINE_CLEANUP_CANDIDATE',)
    assert svc.cleanup() == 1
    after = prepare_reconciliation(svc)
    assert after.ledger_reserved_bytes == after.upload_reserved_bytes == len(png())
    assert after.ledger_pending_uploads == after.upload_pending_held == 0
    assert after.uploads[0].actor_ledger_bytes == len(png())
    assert after.uploads[0].state == 'ready' and not after.ready_original_deletion_authorized


@pytest.mark.parametrize('limit', [None, True, False, 0, 21, -1, 1.0, float('nan'), float('inf'), [], {}])
def test_direct_report_limit_is_strict_before_session(limit):
    def denied(): raise AssertionError('opened session')
    with pytest.raises(SocialError): report_once(denied, None, limit=limit)


@pytest.mark.parametrize('cursor', [True, 1, '', 'bad', str(uuid4()), [], {}])
def test_direct_report_cursor_is_strict_before_session(cursor):
    def denied(): raise AssertionError('opened session')
    with pytest.raises(SocialError): report_once(denied, None, after_asset_id=cursor)


@pytest.mark.parametrize('extra', [ ['--prepare-reconciliation', '--allow-cleanup'], ['--after-asset-id', str(uuid4())], ['--prepare-reconciliation', '--after-asset-id', 'private-invalid'] ])
def test_cli_refuses_mutating_or_invalid_preparation_before_engine(monkeypatch, capsys, extra):
    monkeypatch.setattr('social.media.maintenance.create_worker_engine', lambda _: (_ for _ in ()).throw(AssertionError('connection attempted')))
    assert main(['--database-url', 'postgresql://private-secret@localhost/db', *extra]) == 1
    assert 'private' not in capsys.readouterr().out
