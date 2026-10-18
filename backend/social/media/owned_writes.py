"""Owned R2 writers with complete admission history from object allocation.

Only a local signer whose bearer never escaped, and an acknowledged synchronous
finalizer, supply terminal proof here. Issued grants, lost replies and process
death remain unsupported. This does not certify arbitrary/off-system writers.
"""
from uuid import uuid4
from uuid import UUID
from urllib.parse import urlsplit

from sqlalchemy import case, func, select, text

from ..contracts import canonical_hash
from ..models import SocialAuditEvent
from ..service import SocialError
from .models import SocialMediaBudget, SocialMediaUpload, SocialMediaWriteAttempt, SocialMediaWriteOwner
from .storage import R2Storage

MAX_ATTEMPTS = 32


def refused():
    return SocialError('MEDIA_WRITE_QUIESCENCE_UNCONFIRMED',
        'Complete owned write history is unavailable. Capacity remains held.', 503)


def binding(service, asset, upload):
    storage, config = service.runtime.storage, service.config
    # This protocol relies on the concrete local-only signer and bounded
    # synchronous finalizer. A capability Boolean on an arbitrary port is not proof.
    if (not config.owned_quiescence_enabled or type(storage) is not R2Storage
            or asset.storage_provider != 'r2' or storage.bucket != asset.bucket
            or config.bucket != asset.bucket or storage.origin != urlsplit(config.endpoint).hostname):
        raise refused()
    return canonical_hash({'protocol': 'owned_r2_v1', 'asset_id': str(asset.id),
        'actor_id': str(upload.actor_id), 'provider': asset.storage_provider,
        'bucket': asset.bucket, 'quarantine': upload.quarantine_key,
        'original': asset.storage_key, 'endpoint': config.endpoint,
        # Bind rotation without storing or returning credential material.
        'credential': canonical_hash({'access': config.access_key, 'secret': config.secret_key})})


def allocate(service, asset, upload):
    if service.config.owned_quiescence_enabled:
        generation, digest = uuid4(), binding(service, asset, upload)
        service.db.add(SocialMediaWriteOwner(asset_id=asset.id, generation=generation,
            binding_hash=digest, state='open'))
        service.db.flush()
        row = service.db.get(SocialMediaWriteOwner, asset.id, populate_existing=True)
        if row is None or (row.generation, row.binding_hash, row.state) != (generation, digest, 'open'):
            raise refused()


def owner(service, asset, upload):
    row = service.db.get(SocialMediaWriteOwner, asset.id, populate_existing=True)
    if row is not None and row.binding_hash != binding(service, asset, upload):
        raise refused()
    return row


def admit(service, asset, upload, kind, epoch):
    row = owner(service, asset, upload)
    if row is None:
        return None  # Historical uploads never acquire invented coverage.
    attempts = list(service.db.scalars(select(SocialMediaWriteAttempt).where(
        SocialMediaWriteAttempt.asset_id == asset.id).limit(MAX_ATTEMPTS + 1)))
    if (row.state != 'open' or type(epoch) is not int or epoch < 1
            or kind not in ('grant', 'finalize') or len(attempts) >= MAX_ATTEMPTS):
        raise refused()
    attempt = SocialMediaWriteAttempt(asset_id=asset.id, kind=kind, epoch=epoch,
        operation_id=uuid4(), state='admitted')
    service.db.add(attempt)
    service.db.flush()
    # Read back before allowing an effect; triggers may suppress an insert.
    found = service.db.get(SocialMediaWriteAttempt, (asset.id, kind, epoch), populate_existing=True)
    if found is None or found.operation_id != attempt.operation_id or found.state != 'admitted':
        raise refused()
    return attempt.operation_id


def finish(service, asset, upload, kind, epoch, operation_id, state):
    if operation_id is None:
        return
    owner(service, asset, upload)
    row = service.db.get(SocialMediaWriteAttempt, (asset.id, kind, epoch), populate_existing=True)
    allowed = {'grant': {'not_issued', 'issued'}, 'finalize': {'completed'}}
    if (row is None or row.operation_id != operation_id or row.state != 'admitted'
            or state not in allowed[kind]):
        raise refused()
    row.state = state
    service.db.flush()
    service.db.refresh(row)
    if row.state != state:
        raise refused()


def close(service, asset, upload):
    row = owner(service, asset, upload)
    if row is not None:
        if row.state == 'settled':
            raise refused()
        row.state = 'closed'
        service.db.flush()
        service.db.refresh(row)
        if row.state != 'closed':
            raise refused()


def manifest(service, asset, upload, scope, *, settled=False):
    row = owner(service, asset, upload)
    if row is None or row.state != ('settled' if settled else 'closed'):
        raise refused()
    attempts = list(service.db.scalars(select(SocialMediaWriteAttempt).where(
        SocialMediaWriteAttempt.asset_id == asset.id).order_by(
            SocialMediaWriteAttempt.kind, SocialMediaWriteAttempt.epoch).limit(MAX_ATTEMPTS + 1)))
    grants = [a for a in attempts if a.kind == 'grant']
    finalizers = [a for a in attempts if a.kind == 'finalize']
    if (type(upload.grant_epoch) is not int or not 1 <= upload.grant_epoch <= MAX_ATTEMPTS
            or not attempts or len(attempts) > MAX_ATTEMPTS
            or [a.epoch for a in grants] != list(range(1, upload.grant_epoch + 1))
            or any(a.state != 'not_issued' for a in grants)
            or any(a.state != 'completed' for a in finalizers)
            or (upload.finalization_epoch is None) != (not finalizers)
            or finalizers and finalizers[-1].epoch != upload.finalization_epoch):
        raise refused()
    return canonical_hash({'scope': scope.model_dump(mode='json'),
        'generation': str(row.generation), 'binding_hash': row.binding_hash,
        'accounting': {name: getattr(upload, name) for name in (
            'reserved_bytes', 'pending_released', 'reservation_released',
            'quarantine_cleaned', 'write_protocol', 'fenced_copies')},
        'attempts': [{'id': str(a.operation_id), 'kind': a.kind, 'epoch': a.epoch,
                      'state': a.state} for a in attempts]})


def audit_readback(service, event):
    expected = {k: getattr(event, k) for k in
        ('id', 'actor_id', 'actor_kind', 'action', 'previous_state', 'new_state', 'details', 'request_id')}
    def digest(values):
        return canonical_hash({k: str(v) if type(v) is UUID else v for k, v in values.items()})
    # Freeze the expected bytes before flushing: details is mutable and flush
    # hooks must not rewrite both the evidence and the expected value by alias.
    expected_digest = digest(expected)
    service.db.flush()
    if service.db.bind.dialect.name == 'postgresql':
        service.db.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
    stored = service.db.get(SocialAuditEvent, event.id, populate_existing=True)
    if stored is None or digest({k: getattr(stored, k) for k in expected}) != expected_digest:
        raise refused()


def check_accounting(service, actor, budgets):
    if len(budgets) != 2 or [b.scope for b in budgets] != ['global', 'actor:' + str(actor)]:
        raise refused()
    for budget in budgets:
        query = select(func.coalesce(func.sum(SocialMediaUpload.reserved_bytes), 0),
            func.coalesce(func.sum(case((SocialMediaUpload.pending_released == 0, 1), else_=0)), 0))
        if budget.scope != 'global':
            query = query.where(SocialMediaUpload.actor_id == actor)
        if tuple(service.db.execute(query).one()) != (budget.bytes_used, budget.pending_count):
            raise refused()


def result_digest(result, event):
    audit = {k: getattr(event, k) for k in ('id', 'actor_id', 'actor_kind', 'action',
        'previous_state', 'new_state', 'details', 'request_id')}
    return canonical_hash({'result': result.model_dump(mode='json'),
        'audit': {k: str(v) if type(v) is UUID else v for k, v in audit.items()}})


def settled_result(service, asset, upload, row):
    result = service._dto(asset, upload)
    events = list(service.db.scalars(select(SocialAuditEvent).where(
        SocialAuditEvent.action == 'media.writes_reconciled',
        SocialAuditEvent.details['receipt_id'].as_string() == str(row.receipt_id)).limit(2)
        .execution_options(populate_existing=True)))
    if (len(events) != 1 or upload.grant_settled_epoch != upload.grant_epoch
            or upload.finalization_epoch is not None and upload.finalization_settled != 1
            or upload.write_quiescence_receipt_hash != manifest(service, asset, upload,
                service._scope(asset, upload), settled=True)
            or row.result_hash != result_digest(result, events[0])):
        raise refused()
    return result


def reconcile_owned(service, actor, asset_id, key, body, request_id):
    from .reconciliation import ReconcileUpload, WriteQuiescenceReceipt
    from .reconciliation import ReconcileOwnedUpload
    from uuid import UUID
    if any(type(value) is not UUID or not value.int for value in (actor, asset_id, key, request_id)):
        raise refused()
    body = ReconcileOwnedUpload.model_validate(body)
    command_hash = canonical_hash(body.model_dump(mode='json'))
    with service.db.begin():
        service._budgets(service._upload_actor(asset_id))
        asset, upload = service._rows(asset_id)
        row = owner(service, asset, upload)
        if row is None:
            raise refused()
        if row.state == 'settled':
            if row.receipt_id != key or row.command_hash != command_hash:
                raise refused()
            check_accounting(service, upload.actor_id, service._budgets(upload.actor_id))
            return settled_result(service, asset, upload, row)
    # Freeze first in the existing service, then construct evidence from the
    # locked database inventory. No client-supplied statement of drainage.
    return service.reconcile(actor, asset_id, ReconcileUpload(
        **body.model_dump(), receipt=WriteQuiescenceReceipt(receipt_id=key,
            evidence_hash=command_hash)), request_id, _owned_command_hash=command_hash)


class OwnedWriteQuiescenceVerifier:
    """Database observations of the concrete owned protocol, never HEAD/time."""
    def __init__(self, service):
        self.service = service

    def issue(self, scope, identity):
        from .reconciliation import WriteQuiescenceReceipt
        with self.service.db.begin():
            asset, upload = self.service._rows(scope.asset_id)
            if self.service._scope(asset, upload) != scope:
                raise refused()
            return WriteQuiescenceReceipt(receipt_id=identity,
                evidence_hash=manifest(self.service, asset, upload, scope))

    def verify(self, scope, receipt):
        from .reconciliation import WriteQuiescenceEvidence
        expected = self.issue(scope, receipt.receipt_id)
        if receipt != expected:
            return None
        with self.service.db.begin():
            verified_at = self.service.now()
        return WriteQuiescenceEvidence(scope=scope, receipt=receipt, verified_at=verified_at)


def settle(service, asset, upload, key, command_hash, result, event, scope, budget_snapshot):
    row = owner(service, asset, upload)
    if row is None or row.state != 'closed':
        raise refused()
    row.state, row.receipt_id, row.command_hash = 'settled', key, command_hash
    expected_result_hash = result_digest(result, event)
    row.result_hash = expected_result_hash
    service.db.flush()
    service.db.refresh(row)
    if (row.state, row.receipt_id, row.command_hash, row.result_hash) != (
            'settled', key, command_hash, expected_result_hash):
        raise refused()
    service.db.refresh(asset)
    service.db.refresh(upload)
    if service._scope(asset, upload) != scope:
        raise refused()
    settled_result(service, asset, upload, row)
    budgets = list(service.db.scalars(select(SocialMediaBudget).where(
        SocialMediaBudget.scope.in_([item[0] for item in budget_snapshot]))
        .execution_options(populate_existing=True)))
    if sorted((b.scope, b.bytes_used, b.pending_count) for b in budgets) != sorted(budget_snapshot):
        raise refused()
