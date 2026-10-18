"""Authenticate externally retained intents before restored credentials can be used."""
import hashlib
from uuid import UUID, uuid4
from sqlalchemy import select
from ..connections.service import ConnectionService
from ..models import SocialAuditEvent
from ..service import SocialError
from .deletion_ledger import verify_entry
from .workflow import PrivacyWorkflow
from .workflow_contracts import PrivacyWorkflowConfig


def reapply_deletion_ledger(db, signed_entries, *, public_key, cipher, apply=False):
    """Bounded restore suppression, not new deletion/retirement authority.

    The trusted public key MUST come from independent operator configuration.
    Inputs are verified before the transaction; one malformed entry applies none.
    Media intents remain unresolved until the media-owned read-only port verifies
    permanent fences. Publication stays paused even after local erasure succeeds.
    """
    if type(apply) is not bool or type(signed_entries) is not list or not 1 <= len(signed_entries) <= 1000:
        raise ValueError('PRIVACY_RESTORE_REFUSED')
    if any(type(entry) is not bytes for entry in signed_entries) or sum(len(entry) for entry in signed_entries) > 64_000_000:
        raise ValueError('PRIVACY_RESTORE_REFUSED')
    intents = [verify_entry(entry, public_key) for entry in signed_entries]
    if len({i['operation_id'] for i in intents}) != len(intents):
        raise ValueError('PRIVACY_RESTORE_REFUSED')
    if not apply:
        return {'state': 'VALIDATED_ONLY', 'entries': len(intents), 'local_erasure_applied': False,
                'publishing_authorized': False, 'deletion_completed': False}
    service = PrivacyWorkflow(db, PrivacyWorkflowConfig(), cipher=cipher)
    with db.begin():
        controls = ConnectionService(db, None)._controls_lock()
        if controls.publishing_enabled is not False:
            raise SocialError('RECOVERY_PAUSE_REQUIRED', 'Pause publication before reapplying the external deletion ledger.', 409)
        # A logical generation conflict blocks the whole batch. No force-clear.
        for raw, intent in zip(signed_entries, intents):
            service.apply_intent(intent)
            existing = db.scalar(select(SocialAuditEvent.id).where(SocialAuditEvent.action == 'privacy.restore_suppression', SocialAuditEvent.request_id == intent['operation_id']))
            if existing is None:
                db.add(SocialAuditEvent(actor_kind='system', action='privacy.restore_suppression', request_id=intent['operation_id'],
                    details={'plan_id': intent['plan_id'], 'plan_hash': intent['plan_hash'], 'policy_hash': intent['policy_hash'],
                        'external_entry_sha256': hashlib.sha256(raw).hexdigest(), 'media_reconciliation_required': bool(intent['scope']['media_assets'])}))
    return {'state': 'LOCAL_SUPPRESSION_REAPPLIED', 'entries': len(intents), 'local_erasure_applied': True,
            'media_reconciliation_required': any(i['scope']['media_assets'] for i in intents),
            'publishing_authorized': False, 'deletion_completed': False, 'retirement_authorized': False}
