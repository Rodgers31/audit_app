"""Private inventory decision seam. No retention approval or deletion executor."""
from dataclasses import dataclass
from uuid import UUID
from sqlalchemy import func, select
from ..connections.models import SocialCredential, SocialOAuthFlow
from ..models import SocialAccount, SocialPostTarget, SocialPublishAttempt
from ..service import SocialError
from .models import SocialPrivacyReceipt


@dataclass(frozen=True)
class RetentionDecision:
    state: str = 'pending_review'
    deletion_authorized: bool = False
    deletion_completed: bool = False


PENDING_RETENTION = RetentionDecision()


def inventory_for_review(db, receipt_id):
    """Bounded private references/counts, never encrypted material or raw subjects.

    Caller supplies a server-authorized receipt UUID. This is deliberately absent
    from public routers. Counts describe attributed records, not legal permission
    to retain them; media/backup/subprocessor attribution remains unknown.
    """
    if type(receipt_id) is not UUID or receipt_id.int == 0:
        raise SocialError('NOT_FOUND', 'Privacy receipt was not found.', 404)
    receipt = db.get(SocialPrivacyReceipt, receipt_id)
    if receipt is None:
        raise SocialError('NOT_FOUND', 'Privacy receipt was not found.', 404)
    refs = receipt.affected
    if type(refs) is not list or len(refs) > 500 or any(type(r) is not dict for r in refs):
        raise SocialError('PRIVACY_INVENTORY_UNRESOLVED', 'The private inventory is unavailable.', 409)
    def ids(name):
        try:
            return {UUID(r[name]) for r in refs if r.get(name)}
        except (ValueError, TypeError, AttributeError):
            raise SocialError('PRIVACY_INVENTORY_UNRESOLVED', 'The private inventory is unavailable.', 409) from None
    credentials, accounts, flows = ids('credential_id'), ids('account_id'), ids('flow_id')
    def count(model, criterion):
        return db.scalar(select(func.count()).select_from(model).where(criterion))
    targets = select(SocialPostTarget.id).where(SocialPostTarget.account_id.in_(accounts))
    return {'decision': PENDING_RETENTION, 'resolution': receipt.resolution,
            'credential_envelopes': count(SocialCredential, SocialCredential.id.in_(credentials)),
            'pending_flow_envelopes': count(SocialOAuthFlow, SocialOAuthFlow.id.in_(flows) & SocialOAuthFlow.encrypted_pending_grant.is_not(None)),
            'account_metadata': count(SocialAccount, SocialAccount.id.in_(accounts)),
            'delivery_targets': count(SocialPostTarget, SocialPostTarget.account_id.in_(accounts)),
            'delivery_attempts': count(SocialPublishAttempt, SocialPublishAttempt.target_id.in_(targets)),
            'unknown_categories': ('unindexed_legacy_ownership', 'media_attribution', 'backup_copies', 'subprocessors', 'legal_retention_basis')}
