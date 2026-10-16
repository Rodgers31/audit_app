"""Default-off, authority-bound media payload deletion and durable effect ledger.

Public privacy completion is owned by privacy, not by this module. A complete
result covers only the two allocated storage payloads. Permanent fence bytes,
checksums, references, provider copies and backups are not erased by this port.
"""
from datetime import datetime, timedelta, timezone
import re
from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import field_validator
from sqlalchemy import select, text

from ..contracts import Hash, canonical_hash
from ..service import SocialError, utc
from .fencing import WRITE_PROTOCOL
from .models import SocialMediaDeletion
from .reconciliation import ReconciliationModel


class PrivacyMediaDeletionCommand(ReconciliationModel):
    authority_id: UUID
    receipt_id: UUID
    asset_id: UUID
    operation_id: UUID
    mode: Literal['all', 'quarantine'] = 'all'
    purpose: Literal['privacy_deletion', 'retention_expiry'] = 'privacy_deletion'
    plan_hash: Hash | None = None
    policy_hash: Hash | None = None
    expected_scope_hash: Hash | None = None

    @field_validator('authority_id', 'receipt_id', 'asset_id', 'operation_id')
    @classmethod
    def nonzero(cls, value):
        if not value.int:
            raise ValueError('Nonzero identities are required')
        return value


class MediaDeletionScope(ReconciliationModel):
    scope_hash: Hash
    storage_provider: str
    bucket: str
    asset_id: UUID
    upload_version: int
    grant_epoch: int
    finalization_epoch: int | None
    mode: Literal['all', 'quarantine']


class MediaDeletionAuthority(ReconciliationModel):
    command: PrivacyMediaDeletionCommand
    scope_hash: Hash
    policy_hash: Hash
    verified_at: datetime


class MediaDeletionAuthorityVerifier(Protocol):
    def verify(self, command: PrivacyMediaDeletionCommand, scope: MediaDeletionScope) -> MediaDeletionAuthority | None: ...


class UnsupportedMediaDeletionAuthority:
    def verify(self, command, scope):
        return None


class PrivacyMediaDeletionResult(ReconciliationModel):
    authority_id: UUID
    receipt_id: UUID
    asset_id: UUID
    operation_id: UUID
    state: Literal['complete', 'uncertain', 'blocked', 'disabled']
    verified_deleted: bool
    result_hash: Hash | None = None
    coverage: Literal['allocated_storage_payloads_only'] = 'allocated_storage_payloads_only'
    write_quiescence_proven: Literal[False] = False


class MediaDeletionInventory(ReconciliationModel):
    asset_id: UUID
    scope_hash: Hash


def inspect_deletion_scope(service, asset_id):
    if type(asset_id) is not UUID or not asset_id.int:
        raise SocialError('INVALID_REQUEST', 'A valid media identity is required.', 422)
    from ..models import SocialMediaAsset
    from .models import SocialMediaUpload
    from .identity import object_identity_matches
    asset, upload = service.db.get(SocialMediaAsset, asset_id), service.db.get(SocialMediaUpload, asset_id)
    if asset is None or upload is None or not object_identity_matches(asset, upload):
        raise SocialError('MEDIA_OBJECT_IDENTITY_MISMATCH', 'The media inventory requires review.', 409)
    return MediaDeletionInventory(asset_id=asset_id, scope_hash=_binding(asset, upload)).model_dump(mode='json')


def _result(command, state, digest=None):
    return PrivacyMediaDeletionResult(**{name: getattr(command, name) for name in
        ('authority_id', 'receipt_id', 'asset_id', 'operation_id')}, state=state,
        verified_deleted=state == 'complete' and command.mode == 'all', result_hash=digest)


def _binding(asset, upload):
    return canonical_hash({'asset': str(asset.id), 'actor': str(upload.actor_id),
        'provider': asset.storage_provider, 'bucket': asset.bucket,
        'quarantine': upload.quarantine_key, 'original': asset.storage_key,
        'version': upload.version, 'grant_epoch': upload.grant_epoch,
        'finalization_epoch': upload.finalization_epoch, 'protocol': upload.write_protocol,
        'state': asset.state, 'reserved_bytes': upload.reserved_bytes,
        'fenced_copies': upload.fenced_copies, 'declared_size': upload.declared_size,
        'sha256': asset.sha256, 'metadata': asset.codec_metadata,
        'created_at': utc(asset.created_at).isoformat(), 'expires_at': utc(upload.expires_at).isoformat()})


def _scope(asset, upload, command):
    return MediaDeletionScope(scope_hash=canonical_hash({'binding': _binding(asset, upload),
        'command': command.model_dump(mode='json')}), storage_provider=asset.storage_provider,
        bucket=asset.bucket, asset_id=asset.id, upload_version=upload.version,
        grant_epoch=upload.grant_epoch, finalization_epoch=upload.finalization_epoch, mode=command.mode)


def _locked_job(service, command, command_hash):
    row = service.db.scalar(select(SocialMediaDeletion).where(
        SocialMediaDeletion.operation_id == command.operation_id).with_for_update().execution_options(populate_existing=True))
    if row is not None and (row.command_hash != command_hash or
            (row.asset_id, row.authority_id, row.receipt_id, row.mode) !=
            (command.asset_id, command.authority_id, command.receipt_id, command.mode)):
        raise SocialError('IDEMPOTENCY_CONFLICT', 'This media deletion operation has another immutable scope.', 409)
    if row is not None and row.state == 'complete' and not completed_deletion_matches(row, command):
        raise SocialError('MEDIA_RETENTION_INVALID', 'The stored retirement result requires review.', 409)
    return row


def completed_deletion_matches(row, command):
    """Shared replay/observation boundary; no locks, effects or inferred proof."""
    return (row is not None and row.state == 'complete'
        and (row.operation_id, row.asset_id, row.authority_id, row.receipt_id, row.mode) ==
            (command.operation_id, command.asset_id, command.authority_id, command.receipt_id, command.mode)
        and row.command_hash == canonical_hash(command.model_dump(mode='json'))
        and (command.policy_hash is None or row.policy_hash == command.policy_hash)
        and (command.expected_scope_hash is None or row.scope_hash == canonical_hash({
            'binding': command.expected_scope_hash, 'command': command.model_dump(mode='json')}))
        and type(row.quarantine_fenced) is int and row.quarantine_fenced == 1
        and type(row.original_fenced) is int and (command.mode == 'quarantine' or row.original_fenced == 1)
        and all(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None
                for value in (row.result_hash, row.scope_hash, row.policy_hash, row.binding_hash))
        and isinstance(row.completed_at, datetime))


def _persist_exact(service, records):
    """Force deferred effects and read actual stored values before commit.

    Triggers can suppress or coherently alter ORM writes. A successful flush is
    insufficient to authorize an effect or a completion receipt. Capture before
    flushing; canonical JSON preserves bool/int distinctions in JSON columns.
    """
    def portable(value):
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, datetime):
            return utc(value).isoformat()
        if isinstance(value, dict):
            return {key: portable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [portable(item) for item in value]
        return value
    expected = []
    for record in records:
        values = {column.name: portable(getattr(record, column.name)) for column in record.__table__.columns
            if column.name not in {'updated_at', 'frame_rate'}
            and not (column.name == 'created_at' and getattr(record, column.name) is None)
            and not (column.primary_key and getattr(record, column.name) is None)}
        expected.append((record, values))
    service.db.flush()
    if service.db.bind.dialect.name == 'postgresql':
        service.db.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
    for record, values in expected:
        service.db.refresh(record)
        actual = {name: portable(getattr(record, name)) for name in values}
        if canonical_hash(actual) != canonical_hash(values):
            raise SocialError('MEDIA_RETIREMENT_PERSISTENCE_UNCONFIRMED',
                'Stored retirement authority or effects differ. Capacity and uncertainty remain held.', 503)


def execute_deletion(service, command):
    command = PrivacyMediaDeletionCommand.model_validate(command)
    if not service.config.fenced_retirement_enabled:
        return _result(command, 'disabled')
    storage = service._storage()
    if (getattr(storage, 'retained_create_only', None) is not True
            or getattr(storage, 'permanent_payload_fence', None) is not True):
        return _result(command, 'blocked')
    command_hash = canonical_hash(command.model_dump(mode='json'))
    with service.db.begin():
        service._budgets(service._upload_actor(command.asset_id))
        asset, upload = service._rows(command.asset_id)
        job = _locked_job(service, command, command_hash)
        if job is not None and job.state == 'complete':
            return _result(command, 'complete', job.result_hash)
        scope = _scope(asset, upload, command)
        if job is None and command.expected_scope_hash is not None and command.expected_scope_hash != _binding(asset, upload):
            return _result(command, 'blocked')
        observed_at = service.now()
    if job is None:
        # A supplied approval/Boolean is never authority. The installed verifier
        # must consult approved durable policy, including bucket writer/lifecycle
        # custody and exact deletion-ledger attribution.
        try:
            authority = service.runtime.deletion_authority.verify(command, scope)
            if not isinstance(authority, MediaDeletionAuthority):
                return _result(command, 'blocked')
            authority = MediaDeletionAuthority.model_validate(authority)
            if (authority.command != command or authority.scope_hash != scope.scope_hash
                    or authority.verified_at.tzinfo is None
                    or authority.verified_at < observed_at
                    or authority.verified_at > datetime.now(timezone.utc) + timedelta(seconds=1)):
                return _result(command, 'blocked')
        except Exception:
            return _result(command, 'blocked')
    with service.db.begin():
        budgets = service._budgets(service._upload_actor(command.asset_id))
        asset, upload = service._rows(command.asset_id)
        job = _locked_job(service, command, command_hash)
        if job is not None and job.state == 'complete':
            return _result(command, 'complete', job.result_hash)
        now = service.now()
        if ((asset.storage_provider, asset.bucket) != (storage.provider, storage.bucket)
                or upload.write_protocol != WRITE_PROTOCOL
                or upload.reservation_released or upload.quarantine_cleaned
                or (asset.lease_expires_at and utc(asset.lease_expires_at) > now)):
            return _result(command, 'blocked')
        if command.mode == 'all' and service._referenced(asset.id):
            return _result(command, 'blocked')
        if command.mode == 'quarantine' and asset.state != 'ready':
            return _result(command, 'blocked')
        admitted_audit = None
        if job is None:
            if _scope(asset, upload, command) != scope:
                return _result(command, 'blocked')
            # A different unresolved effect retains exclusive ownership forever
            # until its own exact operation is retried; no force-clear path.
            prior = list(service.db.scalars(select(SocialMediaDeletion).where(
                SocialMediaDeletion.asset_id == asset.id)))
            if any(row.state != 'complete' for row in prior):
                return _result(command, 'blocked')
            quarantine_done = any(row.quarantine_fenced for row in prior)
            original_done = any(row.original_fenced for row in prior)
            if original_done or command.mode == 'quarantine' and quarantine_done:
                return _result(command, 'blocked')
            if command.purpose == 'retention_expiry':
                deadline = (utc(asset.created_at) + timedelta(days=service.config.ready_retention_days)
                    if asset.state == 'ready' and command.mode == 'all' else utc(upload.expires_at))
                if deadline > now:
                    return _result(command, 'blocked')
            if command.mode == 'all':
                asset.state = 'archived'
            upload.grant_renewal_deadline = min(utc(upload.grant_renewal_deadline), now)
            upload.version += 1
            job = SocialMediaDeletion(operation_id=command.operation_id, asset_id=asset.id,
                authority_id=command.authority_id, receipt_id=command.receipt_id,
                command_hash=command_hash, scope_hash=scope.scope_hash, policy_hash=authority.policy_hash,
                binding_hash=_binding(asset, upload), mode=command.mode, state='admitted',
                quarantine_fenced=int(quarantine_done), original_fenced=int(original_done))
            service.db.add(job)
            admitted_audit = service._audit(None, command.operation_id, asset, 'media.payload_retirement_admitted', asset.state)
        elif job.binding_hash != _binding(asset, upload):
            return _result(command, 'blocked')
        # Ledger integrity must precede external destructive effects.
        if any(b.bytes_used < upload.reserved_bytes or
               b.pending_count < int(not upload.pending_released) for b in budgets):
            raise SocialError('MEDIA_RETENTION_INVALID', 'The media ledger requires operator review.', 409)
        token = uuid4()
        asset.lease_token, asset.lease_expires_at = token, now + timedelta(seconds=service.config.lease_seconds)
        asset.lease_epoch += 1
        epoch, actor, binding = asset.lease_epoch, upload.actor_id, job.binding_hash
        work = ([] if job.quarantine_fenced else [('quarantine', upload.quarantine_key)])
        if command.mode == 'all' and not job.original_fenced:
            work.append(('original', asset.storage_key))
        maximum = upload.declared_size
        _persist_exact(service, [asset, upload, job, *budgets] + ([admitted_audit] if admitted_audit is not None else []))
    evidence = []
    try:
        for component, key in work:
            snapshot = storage.retire_payload(key, command.operation_id, maximum)
            # Exact typed snapshots are checked by the real port; require the
            # same invariant from injected ports before crediting any bytes.
            from .storage import ObjectSnapshot
            from .fencing import FENCE_SHA256, FENCE_MIME
            if (type(snapshot) is not ObjectSnapshot or type(snapshot.size) is not int
                    or snapshot.size != 1 or snapshot.version is not None
                    or type(snapshot.etag) is not str or not snapshot.etag
                    or snapshot.sha256 != FENCE_SHA256 or snapshot.mime_type != FENCE_MIME):
                raise ValueError('Unconfirmed fence')
            evidence.append({'component': component, 'etag': snapshot.etag, 'sha256': snapshot.sha256})
    except Exception:
        with service.db.begin():
            service._budgets(actor)
            asset, upload = service._rows(command.asset_id)
            job = _locked_job(service, command, command_hash)
            if asset.lease_token == token and asset.lease_epoch == epoch:
                job.state = 'uncertain'
                asset.lease_token = asset.lease_expires_at = None
                service._audit(None, command.operation_id, asset, 'media.payload_retirement_uncertain', asset.state)
        return _result(command, 'uncertain')
    with service.db.begin():
        budgets = service._budgets(actor)
        asset, upload = service._rows(command.asset_id)
        job = _locked_job(service, command, command_hash)
        if (job is None or job.state == 'complete' or _binding(asset, upload) != binding
                or asset.lease_token != token or asset.lease_epoch != epoch
                or asset.lease_expires_at is None or utc(asset.lease_expires_at) <= service.now()
                or command.mode == 'all' and service._referenced(asset.id)):
            return _result(command, 'uncertain')
        if any(b.bytes_used < upload.reserved_bytes or b.pending_count < int(not upload.pending_released) for b in budgets):
            raise SocialError('MEDIA_RETENTION_INVALID', 'The media ledger changed during retirement.', 409)
        released = len(work) * (upload.declared_size - 1)
        for budget in budgets:
            budget.bytes_used -= released
        upload.reserved_bytes -= released
        upload.fenced_copies += len(work)
        service._release_pending(upload, budgets)
        job.quarantine_fenced = 1
        if command.mode == 'all':
            job.original_fenced = 1
            asset.deleted_at = service.now()
        job.state, job.completed_at = 'complete', service.now()
        job.result_hash = canonical_hash({'command_hash': command_hash, 'scope_hash': job.scope_hash,
            'policy_hash': job.policy_hash, 'evidence': evidence, 'reserved_bytes': upload.reserved_bytes})
        asset.lease_token = asset.lease_expires_at = None
        audit = service._audit(None, command.operation_id, asset, 'media.payload_retirement_complete', asset.state)
        _persist_exact(service, [asset, upload, job, *budgets, audit])
        return _result(command, 'complete', job.result_hash)


class MediaDeletionExecutor:
    def __init__(self, session_factory, runtime):
        self.session_factory, self.runtime = session_factory, runtime

    def execute_privacy_deletion(self, command):
        command = PrivacyMediaDeletionCommand.model_validate(command)
        from .service import MediaService
        with self.session_factory() as db:
            return execute_deletion(MediaService(db, self.runtime), command)

    def inspect_scope(self, asset_id):
        from .service import MediaService
        with self.session_factory() as db, db.begin():
            service = MediaService(db, self.runtime)
            # Read only: no budget creation, locks, leases or object calls.
            return inspect_deletion_scope(service, asset_id)
