"""Grant, operator reconciliation and maintenance recovery use explicit fakes."""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import threading
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session, sessionmaker

from social.media.maintenance import main, run_once
from social.media.models import SocialMediaBudget, SocialMediaUpload
from social.media.reconciliation import ReconcileUpload, WriteQuiescenceEvidence, WriteQuiescenceReceipt
from social.media.service import MediaService
from social.models import SocialAuditEvent, SocialMediaAsset, SocialRevisionAsset
from social.service import SocialError, SocialService
from test_media_support import ACTOR, ConfirmedFakeQuiescence, intent, media, media_db, png, settle_writes, upload_ready
from test_media_cleanup import media_pg


def request_for(svc, identity):
    with svc.db.begin():
        upload = svc.db.get(SocialMediaUpload, identity)
        return ReconcileUpload(expected_version=upload.version, expected_grant_epoch=upload.grant_epoch, expected_finalization_epoch=upload.finalization_epoch, receipt=WriteQuiescenceReceipt(receipt_id=uuid4(), evidence_hash='b' * 64))


def expire(svc, *identities):
    with svc.db.begin():
        for identity in identities:
            svc.db.get(SocialMediaUpload, identity).expires_at = svc.now() - timedelta(seconds=1)


def ledger(svc):
    with svc.db.begin():
        budget = svc.db.get(SocialMediaBudget, 'global')
        return budget.bytes_used, budget.pending_count


def legacy_cleaned_ready(media, pending_released, copies=1):
    """A historical DELETE reduced bytes but an old grant can recreate them."""
    svc, store = media
    ready = upload_ready(media)
    with svc.db.begin():
        upload = svc.db.get(SocialMediaUpload, ready.id)
        upload.version = 2 if pending_released else 1
        upload.grant_expires_at = None
        upload.quarantine_cleaned = 1
        upload.pending_released = pending_released
        upload.reserved_bytes = copies * upload.declared_size
        upload.expires_at = svc.now() - timedelta(seconds=1)
        for budget in svc.db.scalars(select(SocialMediaBudget)):
            budget.bytes_used -= (2 - copies) * upload.declared_size
            budget.pending_count -= pending_released
        quarantine = upload.quarantine_key
    store.objects.pop(quarantine)
    # The old acknowledgement cannot exclude a browser PUT admitted earlier.
    store.objects[quarantine] = (png(), 'image/png', None)
    return ready


@pytest.mark.parametrize('pending_released', [0, 1])
@pytest.mark.parametrize('copies', [1, 2])
def test_legacy_cleaned_ready_requires_trusted_evidence_without_releasing_capacity(media, pending_released, copies):
    svc, store = media
    ready = legacy_cleaned_ready(media, pending_released, copies)
    before = ledger(svc)
    with pytest.raises(SocialError, match='MEDIA_WRITE_QUIESCENCE_UNCONFIRMED'):
        svc.reconcile(ACTOR, ready.id, request_for(svc, ready.id), uuid4())
    assert ledger(svc) == before == (copies * len(png()), 1 - pending_released)
    assert svc.backlog().unknown_browser_writes == 1
    assert svc.cleanup() == 0 and 'delete' not in store.operations
    with svc.db.begin():
        upload = svc.db.get(SocialMediaUpload, ready.id)
        assert upload.quarantine_cleaned == 1 and upload.grant_settled_epoch == 0


@pytest.mark.parametrize('pending_released', [0, 1])
@pytest.mark.parametrize('copies', [1, 2])
def test_legacy_ready_recovery_requires_a_fresh_delete_and_retains_original_reservation(media, pending_released, copies):
    svc, store = media
    ready = legacy_cleaned_ready(media, pending_released, copies)
    originals = {key: value for key, value in store.objects.items() if key.startswith('ready/')}
    reconciled = settle_writes(svc, ready.id)
    assert reconciled.state == 'ready'
    assert ledger(svc) == (copies * len(png()), 1 - pending_released)
    with svc.db.begin():
        upload = svc.db.get(SocialMediaUpload, ready.id)
        assert upload.quarantine_cleaned == 0 and upload.grant_settled_epoch == upload.grant_epoch
        assert upload.reserved_bytes == copies * upload.declared_size
    store.fail = 'delete'
    assert svc.cleanup() == 0 and ledger(svc) == (copies * len(png()), 1 - pending_released)
    with svc.db.begin():
        svc.db.get(SocialMediaAsset, ready.id).lease_expires_at = svc.now() - timedelta(seconds=1)
    store.fail = None
    assert svc.cleanup() == 1 and svc.cleanup() == 0
    assert ledger(svc) == (len(png()), 0)
    assert store.objects == originals and svc.preview(ready.id).asset.sha256 == ready.sha256


def test_settled_cleaned_ready_cannot_reopen_cleanup_or_release_original_again(media):
    svc, _ = media
    ready = upload_ready(media)
    expire(svc, ready.id)
    settle_writes(svc, ready.id)
    assert svc.cleanup() == 1
    verifier = svc.runtime.write_quiescence_verifier
    calls = len(verifier.calls)
    with pytest.raises(SocialError, match='UPLOAD_NOT_PENDING'):
        svc.reconcile(ACTOR, ready.id, request_for(svc, ready.id), uuid4())
    assert len(verifier.calls) == calls and svc.cleanup() == 0
    assert ledger(svc) == (len(png()), 0)


def test_expired_browser_write_remains_reserved_after_late_put(media):
    svc, store = media
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    quarantine = store.last_key
    with svc.db.begin():
        svc.db.get(SocialMediaUpload, grant.asset.id).expires_at = svc.now() - timedelta(seconds=1)
    # A request admitted before signature expiry can finish after DELETE.
    assert svc.cleanup() == 0
    store.objects[quarantine] = (png(), 'image/png', None)
    with svc.db.begin():
        budget = svc.db.get(SocialMediaBudget, 'global')
        assert budget.bytes_used == 2 * len(png()) and budget.pending_count == 1


def test_grant_marker_is_durable_before_signing_and_expiration_before_return(media):
    svc, store = media
    def signing(operation):
        if operation == 'authorize':
            assert not svc.db.in_transaction()
            with Session(svc.db.bind) as another:
                upload = another.scalar(select(SocialMediaUpload))
                assert upload.grant_epoch == 1 and upload.grant_settled_epoch == 0
                assert upload.grant_expires_at is None
                assert another.get(SocialMediaBudget, 'global').pending_count == 1
    store.hook = signing
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    with svc.db.begin():
        upload = svc.db.get(SocialMediaUpload, grant.asset.id)
        assert upload.grant_expires_at.replace(tzinfo=timezone.utc) == grant.expires_at
        assert upload.expires_at > upload.grant_renewal_deadline


def test_replay_never_extends_original_grant_renewal_window(media, monkeypatch):
    svc, store = media
    command = uuid4()
    grant = svc.initiate(ACTOR, command, intent(), uuid4())
    with svc.db.begin():
        upload = svc.db.get(SocialMediaUpload, grant.asset.id)
        deadline = upload.grant_renewal_deadline.replace(tzinfo=timezone.utc)
    monkeypatch.setattr(svc, 'now', lambda: deadline - timedelta(seconds=120))
    original_signer = store.authorize_upload
    monkeypatch.setattr(store, 'authorize_upload', lambda *args: replace(original_signer(*args), expires_at=deadline))
    replay = svc.initiate(ACTOR, command, intent(), uuid4())
    assert replay.expires_at <= deadline
    with svc.db.begin():
        assert svc.db.get(SocialMediaUpload, grant.asset.id).grant_renewal_deadline.replace(tzinfo=timezone.utc) == deadline
    before = len(store.operations)
    monkeypatch.setattr(svc, 'now', lambda: deadline)
    with pytest.raises(SocialError, match='UPLOAD_GRANT_EXPIRED'):
        svc.initiate(ACTOR, command, intent(), uuid4())
    assert len(store.operations) == before and ledger(svc) == (2 * len(png()), 1)


def test_delayed_signing_cannot_return_a_grant_after_its_window(media, monkeypatch):
    svc, store = media
    with svc.db.begin():
        now = svc.now()
    def delayed(operation):
        if operation == 'authorize':
            monkeypatch.setattr(svc, 'now', lambda: now + timedelta(seconds=svc.config.upload_ttl + 1))
    store.hook = delayed
    with pytest.raises(SocialError, match='UPLOAD_GRANT_EXPIRED'):
        svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    assert svc.backlog().unknown_browser_writes == 1
    assert ledger(svc) == (2 * len(png()), 1)


@pytest.mark.parametrize('failure', ['storage', 'missing_expiry', 'crash_after_sign'])
def test_signing_failure_or_crash_survives_restart_as_unknown(media, monkeypatch, failure):
    svc, store = media
    if failure == 'storage':
        store.fail = 'authorize'
    else:
        original = store.authorize_upload
        def failing(*args):
            access = original(*args)
            if failure == 'missing_expiry':
                return replace(access, expires_at=None)
            monkeypatch.setattr(svc, '_rows', lambda identity: (_ for _ in ()).throw(RuntimeError('private DB failure')))
            return access
        monkeypatch.setattr(store, 'authorize_upload', failing)
    with pytest.raises(RuntimeError if failure == 'crash_after_sign' else SocialError):
        svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    with Session(svc.db.bind, expire_on_commit=False) as restarted:
        service = MediaService(restarted, svc.runtime)
        assert service.backlog().unknown_browser_writes == 1
        with restarted.begin():
            upload = restarted.scalar(select(SocialMediaUpload))
            upload.expires_at = service.now() - timedelta(seconds=1)
            assert upload.grant_expires_at is None
        assert service.cleanup() == 0
    assert ledger(svc) == (2 * len(png()), 1)


def test_default_operator_verifier_does_not_clear_positive_head_or_expired_writes(media):
    svc, store = media
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    store.objects[store.last_key] = (png(), 'image/png', None)
    expire(svc, grant.asset.id)
    with pytest.raises(SocialError, match='MEDIA_WRITE_QUIESCENCE_UNCONFIRMED'):
        svc.reconcile(ACTOR, grant.asset.id, request_for(svc, grant.asset.id), uuid4())
    assert 'head' not in store.operations and 'delete' not in store.operations
    with svc.db.begin():
        upload = svc.db.get(SocialMediaUpload, grant.asset.id)
        assert upload.grant_epoch == 1 and upload.grant_settled_epoch == 0
        assert upload.write_quiescence_receipt_hash is None
        assert upload.pending_released == 0
    assert svc.cleanup() == 0 and ledger(svc) == (2 * len(png()), 1)


def test_confirmed_operator_abandon_settles_hazards_without_releasing_ledger(media):
    svc, store = media
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    store.objects[store.last_key] = (png(), 'image/png', None)
    with svc.db.begin():
        upload = svc.db.get(SocialMediaUpload, grant.asset.id)
        upload.finalization_epoch = 1
        upload.finalization_settled = 0
    expire(svc, grant.asset.id)
    result = settle_writes(svc, grant.asset.id)
    assert result.state == 'archived' and result.version == 2
    assert ledger(svc) == (2 * len(png()), 1)
    backlog = svc.backlog()
    assert backlog.eligible_cleanup == 1 and backlog.unknown_browser_writes == backlog.unknown_finalizations == 0
    assert svc.cleanup() == 1 and svc.cleanup() == 0
    assert ledger(svc) == (0, 0)
    with svc.db.begin():
        upload = svc.db.get(SocialMediaUpload, grant.asset.id)
        assert upload.pending_released == upload.reservation_released == 1
        event_row = svc.db.scalar(select(SocialAuditEvent).where(SocialAuditEvent.action == 'media.writes_reconciled'))
        assert event_row.actor_id == ACTOR and event_row.details['evidence_hash'] == 'a' * 64
        assert 'fixture=' not in str(event_row.details)


def test_ready_original_identity_is_retained_after_operator_quarantine_recovery(media):
    svc, store = media
    ready = upload_ready(media)
    original = {key: value for key, value in store.objects.items() if key.startswith('ready/')}
    expire(svc, ready.id)
    reconciled = settle_writes(svc, ready.id)
    assert reconciled.state == 'ready' and reconciled.sha256 == ready.sha256
    assert ledger(svc) == (2 * len(png()), 1)
    assert svc.cleanup() == 1 and ledger(svc) == (len(png()), 0)
    assert store.objects == original
    assert svc.preview(ready.id).asset.sha256 == ready.sha256


@pytest.mark.parametrize('shape', ['boolean', 'wrong_asset', 'wrong_provider', 'wrong_bucket', 'wrong_grant', 'wrong_finalization', 'wrong_receipt', 'stale', 'future', 'exception'])
def test_unbound_or_untrusted_evidence_cannot_settle_quota(media, shape):
    svc, store = media
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    class HostileVerifier:
        def verify(self, scope, receipt):
            assert not svc.db.in_transaction()
            if shape == 'boolean': return True
            if shape == 'exception': raise RuntimeError('private receipt or credential')
            changes = {'wrong_asset': {'asset_id': uuid4()}, 'wrong_provider': {'storage_provider': 'attacker'}, 'wrong_bucket': {'bucket': 'another'}, 'wrong_grant': {'grant_epoch': scope.grant_epoch + 1}, 'wrong_finalization': {'finalization_epoch': 99}}
            scope = scope.model_copy(update=changes.get(shape, {}))
            if shape == 'wrong_receipt': receipt = receipt.model_copy(update={'evidence_hash': 'c' * 64})
            at = datetime.now(timezone.utc)
            if shape == 'stale': at -= timedelta(hours=1)
            if shape == 'future': at += timedelta(hours=1)
            return WriteQuiescenceEvidence(scope=scope, receipt=receipt, verified_at=at)
    svc.runtime = replace(svc.runtime, write_quiescence_verifier=HostileVerifier())
    with pytest.raises(SocialError, match='MEDIA_WRITE_QUIESCENCE_UNCONFIRMED') as error:
        svc.reconcile(ACTOR, grant.asset.id, request_for(svc, grant.asset.id), uuid4())
    assert 'private' not in error.value.message
    assert ledger(svc) == (2 * len(png()), 1)
    assert svc.backlog().unknown_browser_writes == 1
    assert 'head' not in store.operations and 'delete' not in store.operations


@pytest.mark.parametrize('change', ['version', 'grant_epoch', 'finalization_epoch', 'lease', 'state'])
def test_reconciliation_rechecks_fenced_state_after_external_verification(media, change):
    svc, _ = media
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    class RacingVerifier:
        def verify(self, scope, receipt):
            with svc.db.begin():
                upload = svc.db.get(SocialMediaUpload, grant.asset.id)
                asset = svc.db.get(SocialMediaAsset, grant.asset.id)
                if change == 'version': upload.version += 1
                if change == 'grant_epoch': upload.grant_epoch += 1
                if change == 'finalization_epoch': upload.finalization_epoch = 1
                if change == 'lease': asset.lease_epoch += 1; asset.lease_token = uuid4()
                if change == 'state': asset.state = 'failed'
            return WriteQuiescenceEvidence(scope=scope, receipt=receipt, verified_at=datetime.now(timezone.utc))
    svc.runtime = replace(svc.runtime, write_quiescence_verifier=RacingVerifier())
    with pytest.raises(SocialError, match='MEDIA_RECONCILIATION_FENCED'):
        svc.reconcile(ACTOR, grant.asset.id, request_for(svc, grant.asset.id), uuid4())
    assert ledger(svc) == (2 * len(png()), 1)
    assert svc.backlog().unknown_browser_writes == 1


def test_signer_cannot_return_after_operator_freezes_renewal(media):
    svc, store = media
    def reconcile_during_sign(operation):
        if operation != 'authorize': return
        store.hook = None
        with svc.db.begin(): identity = svc.db.scalar(select(SocialMediaUpload.asset_id))
        settle_writes(svc, identity)
    store.hook = reconcile_during_sign
    with pytest.raises(SocialError, match='MEDIA_GRANT_FENCED'):
        svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    assert ledger(svc) == (2 * len(png()), 1)


@pytest.mark.parametrize('crash_after', [1, 2])
def test_cleanup_crash_during_each_delete_retains_ledger_until_confirmed_retry(media, crash_after):
    svc, store = media
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    expire(svc, grant.asset.id)
    settle_writes(svc, grant.asset.id)
    original = store.delete
    deletes = []
    def crash(key):
        original(key)
        deletes.append(key)
        if len(deletes) == crash_after: raise RuntimeError('process crashed after remote ACK')
    store.delete = crash
    with pytest.raises(RuntimeError): svc.cleanup()
    assert ledger(svc) == (2 * len(png()), 1)
    with svc.db.begin(): svc.db.get(SocialMediaAsset, grant.asset.id).lease_expires_at = svc.now() - timedelta(seconds=1)
    store.delete = original
    assert svc.cleanup() == 1 and ledger(svc) == (0, 0)
    assert svc.cleanup() == 0


def test_settled_candidate_not_starved_by_earlier_browser_unknown(media):
    svc, _ = media
    unknown = svc.initiate(ACTOR, uuid4(), intent(), uuid4()).asset
    settled = svc.initiate(ACTOR, uuid4(), intent(), uuid4()).asset
    expire(svc, unknown.id, settled.id)
    settle_writes(svc, settled.id)
    assert svc.cleanup(limit=1) == 1 and ledger(svc) == (2 * len(png()), 1)
    assert svc.backlog().unknown_browser_writes == 1


def test_report_only_port_has_no_storage_operation_and_cleanup_requires_opt_in(media):
    svc, store = media
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    expire(svc, grant.asset.id)
    settle_writes(svc, grant.asset.id)
    before = list(store.operations)
    factory = sessionmaker(svc.db.bind, expire_on_commit=False)
    report = run_once(factory, svc.runtime)
    assert not report.cleanup_enabled and report.cleaned == 0 and report.backlog.eligible_cleanup == 1
    assert store.operations == before
    cleaned = run_once(factory, svc.runtime, allow_cleanup=True, limit=1)
    assert cleaned.cleaned == 1 and cleaned.backlog.reserved_bytes == 0
    assert 'fixture=' not in cleaned.model_dump_json()


@pytest.mark.parametrize('value', [True, False, 0, 21, None, 1.0])
def test_maintenance_limits_reject_invalid_shape_before_opening_session(value):
    def factory(): raise AssertionError('must reject before DB access')
    with pytest.raises(SocialError): run_once(factory, None, limit=value)


@pytest.mark.parametrize('value', [None, 0, 1, {}, [], 'true'])
def test_maintenance_opt_in_is_an_explicit_boolean(value):
    def factory(): raise AssertionError('must reject before DB access')
    with pytest.raises(SocialError): run_once(factory, None, allow_cleanup=value)


@pytest.mark.parametrize('value', [None, True, -1, 3, float('inf'), float('nan'), 1.0])
def test_local_signer_retries_are_bounded_for_direct_callers(media, value):
    svc, store = media
    with pytest.raises(SocialError): svc.initiate(ACTOR, uuid4(), intent(), uuid4(), _grant_retries=value)
    assert store.operations == []
    assert svc.backlog().reserved_bytes == 0


@pytest.mark.parametrize('field,value', [('expected_version', True), ('expected_version', 0), ('expected_grant_epoch', True), ('expected_grant_epoch', -1), ('expected_grant_epoch', float('nan')), ('expected_finalization_epoch', 0), ('expected_finalization_epoch', True)])
def test_internal_reconciliation_command_has_strict_epoch_shapes(media, field, value):
    from pydantic import ValidationError
    svc, _ = media
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    body = request_for(svc, grant.asset.id).model_dump()
    body[field] = value
    with pytest.raises(ValidationError): svc.reconcile(ACTOR, grant.asset.id, body, uuid4())
    assert ledger(svc) == (2 * len(png()), 1)


def test_entrypoint_masks_dsn_and_never_opens_storage_on_invalid_config(monkeypatch, capsys):
    monkeypatch.setattr('social.media.maintenance.media_runtime', lambda: (_ for _ in ()).throw(AssertionError('storage runtime must not be reached')))
    assert main(['--database-url', 'postgresql://private-secret@localhost/db', '--limit', '21']) == 1
    assert capsys.readouterr().out.strip() == '{"error_code": "INVALID_REQUEST"}'
    assert main(['--database-url', 'sqlite://private-secret', '--once']) == 1
    assert capsys.readouterr().out.strip() == '{"error_code": "MEDIA_MAINTENANCE_FAILED"}'


def test_already_released_legacy_uncertainty_remains_visible_without_inventing_quota(media):
    svc, _ = media
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    with svc.db.begin():
        upload = svc.db.get(SocialMediaUpload, grant.asset.id)
        upload.reservation_released = upload.pending_released = upload.quarantine_cleaned = 1
        upload.reserved_bytes = 0
        for budget in svc.db.scalars(select(SocialMediaBudget)):
            budget.bytes_used = budget.pending_count = 0
    backlog = svc.backlog()
    assert backlog.unknown_browser_writes == 1
    assert backlog.eligible_cleanup == backlog.reserved_bytes == backlog.pending_uploads == 0


def test_reconciliation_keeps_a_legacy_historical_nonready_reference(media):
    from social.contracts import CreatePost
    from social.models import SocialPost, SocialRevisionAsset
    from social.service import SocialService
    from uuid import UUID
    svc, store = media
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    body = CreatePost.model_validate({'title': 'Historical evidence', 'content_type': 'announcement', 'document': {'schema_version': 1, 'master': {}, 'targets': []}})
    domain = SocialService(svc.db)
    _, created = domain.command(actor=ACTOR, route='fixture.legacy', key=uuid4(), body=body.model_dump(mode='json'), request_id=uuid4(), action=lambda: domain.create(body))
    with svc.db.begin():
        post = svc.db.get(SocialPost, UUID(created['id']))
        svc.db.add(SocialRevisionAsset(revision_id=post.current_revision_id, asset_id=grant.asset.id))
    expire(svc, grant.asset.id)
    svc.runtime = replace(svc.runtime, write_quiescence_verifier=ConfirmedFakeQuiescence(grant.asset.id))
    with pytest.raises(SocialError, match='MEDIA_REFERENCED'):
        svc.reconcile(ACTOR, grant.asset.id, request_for(svc, grant.asset.id), uuid4())
    assert svc.runtime.write_quiescence_verifier.calls == []
    assert svc.cleanup() == 0 and 'delete' not in store.operations
    assert svc.backlog().protected_references == 1
    assert ledger(svc) == (2 * len(png()), 1)


def test_wrong_storage_bucket_cannot_consume_limit_or_release_a_reservation(media):
    svc, _ = media
    wrong = svc.initiate(ACTOR, uuid4(), intent(), uuid4()).asset
    correct = svc.initiate(ACTOR, uuid4(), intent(), uuid4()).asset
    expire(svc, wrong.id, correct.id)
    settle_writes(svc, wrong.id)
    settle_writes(svc, correct.id)
    with svc.db.begin():
        svc.db.get(SocialMediaAsset, wrong.id).bucket = 'different-private-bucket'
    assert svc.cleanup(limit=1) == 1 and ledger(svc) == (2 * len(png()), 1)
    with svc.db.begin():
        assert svc.db.get(SocialMediaUpload, wrong.id).reservation_released == 0


def test_pg_two_grant_signers_keep_one_intent_and_reservation(media_pg):
    engine, runtime = media_pg
    barrier, counter_lock = threading.Barrier(2), threading.Lock()
    signatures = []
    def signing(operation):
        if operation != 'authorize': return
        with counter_lock:
            signatures.append(operation)
            first_pair = len(signatures) <= 2
        if first_pair: barrier.wait(timeout=5)
    runtime.storage.hook = signing
    command = uuid4()
    def initiate():
        with Session(engine, expire_on_commit=False) as db:
            return MediaService(db, runtime).initiate(ACTOR, command, intent(), uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: initiate(), range(2)))
    runtime.storage.hook = None
    assert first.asset.id == second.asset.id
    with Session(engine) as db:
        upload = db.get(SocialMediaUpload, first.asset.id)
        budget = db.get(SocialMediaBudget, 'global')
        assert upload.grant_epoch >= 3 and upload.grant_settled_epoch == 0
        assert budget.bytes_used == 2 * len(png()) and budget.pending_count == 1


def test_pg_reconciliation_accepts_receipt_between_its_locked_transactions(media_pg, monkeypatch):
    """The lower bound is first-tx time; future evidence uses second-tx time."""
    engine, runtime = media_pg
    sampled, verified = [], []

    class DatabaseClockVerifier:
        def verify(self, scope, receipt):
            with engine.connect() as conn:
                at = conn.scalar(select(func.clock_timestamp()))
            verified.append(at)
            return WriteQuiescenceEvidence(scope=scope, receipt=receipt, verified_at=at)

    runtime = replace(runtime, write_quiescence_verifier=DatabaseClockVerifier())
    with Session(engine, expire_on_commit=False) as db:
        service = MediaService(db, runtime)
        grant = service.initiate(ACTOR, uuid4(), intent(), uuid4())
        body = request_for(service, grant.asset.id)
        original_now = service.now

        def clock():
            at = original_now()
            sampled.append(at)
            return at

        monkeypatch.setattr(service, 'now', clock)
        result = service.reconcile(ACTOR, grant.asset.id, body, uuid4())
        assert result.state == 'archived'
        assert len(sampled) == 2 and sampled[0] < verified[0] < sampled[1]
        assert ledger(service) == (2 * len(png()), 1)


def test_pg_reconciliation_freeze_blocks_other_reconciler_and_cleanup_then_releases_once(media_pg):
    engine, runtime = media_pg
    started, release = threading.Event(), threading.Event()
    with Session(engine, expire_on_commit=False) as db:
        service = MediaService(db, runtime)
        grant = service.initiate(ACTOR, uuid4(), intent(), uuid4())
        expire(service, grant.asset.id)
        body = request_for(service, grant.asset.id)
    class PausedVerifier:
        def verify(self, scope, receipt):
            started.set()
            assert release.wait(5)
            return WriteQuiescenceEvidence(scope=scope, receipt=receipt, verified_at=datetime.now(timezone.utc))
    runtime = replace(runtime, write_quiescence_verifier=PausedVerifier())
    def reconcile():
        with Session(engine, expire_on_commit=False) as db:
            return MediaService(db, runtime).reconcile(ACTOR, grant.asset.id, body, uuid4())
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(reconcile)
        assert started.wait(5)
        try:
            with Session(engine, expire_on_commit=False) as db:
                service = MediaService(db, runtime)
                with pytest.raises(SocialError, match='VERSION_CONFLICT'):
                    service.reconcile(ACTOR, grant.asset.id, body, uuid4())
                assert service.cleanup() == 0
                assert ledger(service) == (2 * len(png()), 1)
        finally: release.set()
        assert future.result(timeout=5).state == 'archived'
    def clean():
        with Session(engine, expire_on_commit=False) as db:
            return MediaService(db, runtime).cleanup()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: clean(), range(2)))
    assert sorted(results) == [0, 1]
    with Session(engine, expire_on_commit=False) as db:
        assert ledger(MediaService(db, runtime)) == (0, 0)


def test_pg_revision_asset_lock_precedes_ready_quarantine_cleanup_and_retains_history(media_pg):
    from social.contracts import CreatePost
    engine, runtime = media_pg
    with Session(engine, expire_on_commit=False) as db:
        service = MediaService(db, runtime)
        ready = upload_ready((service, runtime.storage))
        expire(service, ready.id)
        settle_writes(service, ready.id)
    held, release, cleanup_attempt = threading.Event(), threading.Event(), threading.Event()
    domain_thread = threading.local()
    def pause_locked_asset(conn, cursor, statement, params, context, many):
        sql = statement.lower()
        if getattr(domain_thread, 'revising', False) and 'from social_media_assets' in sql and 'for update' in sql:
            assert 'order by social_media_assets.id' in sql
            held.set()
            assert release.wait(5)
    event.listen(engine, 'after_cursor_execute', pause_locked_asset)
    class Domain(SocialService):
        def _new_revision(self, *args):
            domain_thread.revising = True
            try: return super()._new_revision(*args)
            finally: domain_thread.revising = False
    class Cleaner(MediaService):
        def _rows(self, identity):
            cleanup_attempt.set()
            return super()._rows(identity)
    body = CreatePost.model_validate({'title': 'Historical evidence', 'content_type': 'announcement', 'document': {'master': {'media': [{'asset_id': str(ready.id)}]}, 'targets': []}})
    def revise():
        with Session(engine, expire_on_commit=False) as db:
            domain = Domain(db)
            return domain.command(actor=ACTOR, route='fixture.reference', key=uuid4(), body=body.model_dump(mode='json'), request_id=uuid4(), action=lambda: domain.create(body))
    def clean():
        with Session(engine, expire_on_commit=False) as db:
            return Cleaner(db, runtime).cleanup()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(revise)
            try:
                assert held.wait(1), 'Revision insertion must acquire the shared asset row lock'
                cleaner = pool.submit(clean)
                assert cleanup_attempt.wait(1)
                with pytest.raises(TimeoutError): cleaner.result(timeout=0.1)
            finally: release.set()
            writer.result(timeout=5)
            assert cleaner.result(timeout=5) == 1
    finally:
        release.set()
        event.remove(engine, 'after_cursor_execute', pause_locked_asset)
    with Session(engine, expire_on_commit=False) as db:
        assert db.scalar(select(func.count()).select_from(SocialRevisionAsset).where(SocialRevisionAsset.asset_id == ready.id)) == 1
        asset = db.get(SocialMediaAsset, ready.id)
        assert asset.state == 'ready' and asset.deleted_at is None and asset.sha256 == ready.sha256
        assert any(key.startswith('ready/') for key in runtime.storage.objects)


def test_pg_archived_cleanup_rejects_concurrent_revision_before_delete_ack(media_pg):
    from social.contracts import CreatePost
    engine, runtime = media_pg
    with Session(engine, expire_on_commit=False) as db:
        service = MediaService(db, runtime)
        grant = service.initiate(ACTOR, uuid4(), intent(), uuid4())
        expire(service, grant.asset.id)
        settle_writes(service, grant.asset.id)
    deleting, release = threading.Event(), threading.Event()
    def pause_delete(operation):
        if operation == 'delete':
            deleting.set()
            assert release.wait(5)
    runtime.storage.hook = pause_delete
    def clean():
        with Session(engine, expire_on_commit=False) as db:
            return MediaService(db, runtime).cleanup()
    body = CreatePost.model_validate({'title': 'Concurrent unusable reference', 'content_type': 'announcement', 'document': {'master': {'media': [{'asset_id': str(grant.asset.id)}]}, 'targets': []}})
    with ThreadPoolExecutor(max_workers=1) as pool:
        cleaner = pool.submit(clean)
        assert deleting.wait(5)
        try:
            with Session(engine, expire_on_commit=False) as db:
                domain = SocialService(db)
                with pytest.raises(SocialError, match='TARGET_VALIDATION_FAILED'):
                    domain.command(actor=ACTOR, route='fixture.reference', key=uuid4(), body=body.model_dump(mode='json'), request_id=uuid4(), action=lambda: domain.create(body))
        finally: release.set()
        assert cleaner.result(timeout=5) == 1
    runtime.storage.hook = None
    with Session(engine, expire_on_commit=False) as db:
        assert db.scalar(select(func.count()).select_from(SocialRevisionAsset).where(SocialRevisionAsset.asset_id == grant.asset.id)) == 0
    with Session(engine, expire_on_commit=False) as db:
        assert ledger(MediaService(db, runtime)) == (0, 0)
