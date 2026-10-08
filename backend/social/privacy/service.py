"""Atomic frozen receipts and conservative local revocation; no remote writes."""
import hashlib
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import func, or_, select
from ..connections.crypto import CredentialCipher
from ..connections.models import SocialCredential, SocialOAuthFlow
from ..connections.service import ConnectionService
from ..connections.signed_requests import verify_signed_request, SignedRequestError
from ..contracts import canonical_hash
from ..models import SocialAccount, SocialAuditEvent
from ..service import SocialError, utc
from .models import SocialPrivacyOwnership, SocialPrivacyReceipt, SocialPrivacyRequestVariant
from .subjects import SubjectDigester

MAX_REFERENCES = 500
STATUS_MESSAGE = 'Your request was received. Ownership and the data retention policy are under review. Deletion has not been completed.'


def invalid():
    return SocialError('PRIVACY_REQUEST_INVALID', 'The privacy request is invalid.', 400)


@dataclass(frozen=True)
class PrivacyConfig:
    app_id: str
    app_secret: str = field(repr=False)
    status_url_base: str
    enabled: bool = False

    def validate(self):
        try:
            url = urlsplit(self.status_url_base)
            valid = (type(self.enabled) is bool and type(self.app_id) is str
                     and re.fullmatch(r'[1-9][0-9]{0,63}', self.app_id)
                     and type(self.app_secret) is str and 1 <= len(self.app_secret) <= 256
                     and all(33 <= ord(c) <= 126 for c in self.app_secret)
                     and type(self.status_url_base) is str and len(self.status_url_base) <= 2048
                     and self.status_url_base.startswith('https://')
                     and url.hostname and url.port in {None, 443} and not url.username and not url.password
                     and not url.query and not url.fragment and '?' not in self.status_url_base and '#' not in self.status_url_base
                     and not self.status_url_base.endswith('/')
                     and '\\' not in self.status_url_base and all(33 <= ord(c) <= 126 for c in self.status_url_base))
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise SocialError('PRIVACY_CONFIGURATION_INVALID', 'Explicit privacy configuration is unavailable.', 503)


class PrivacyService:
    def __init__(self, db, config, *, digester, cipher):
        if (type(config) is not PrivacyConfig or not isinstance(digester, SubjectDigester)
                or not isinstance(cipher, CredentialCipher)):
            raise SocialError('PRIVACY_CONFIGURATION_INVALID', 'Explicit privacy dependencies are required.', 503)
        config.validate()
        self.db, self.config, self.digester, self.cipher = db, config, digester, cipher

    def _response(self, row):
        if row.kind != 'data_deletion':
            return {'receipt_id': str(row.id), 'state': row.state, 'resolution': row.resolution}
        code = self.cipher.decrypt(row.id, 'privacy_confirmation', row.confirmation_key_version, row.encrypted_confirmation)['code']
        return {'url': row.status_url_base + '?code=' + code, 'confirmation_code': code}

    def receive(self, signed_request, *, kind):
        if self.config.enabled is not True:
            raise SocialError('PRIVACY_UNAVAILABLE', 'Privacy callbacks are unavailable.', 503)
        if type(kind) is not str or kind not in {'data_deletion', 'deauthorization'}:
            raise invalid()
        try:
            verified = verify_signed_request(signed_request, app_secret=self.config.app_secret, expected_app_id=self.config.app_id)
        except SignedRequestError:
            raise invalid() from None
        # All reads deciding a persist occur inside this transaction. The common
        # control lock serializes ownership insert/rotation/reconnect and receipt
        # insertion, including the first receipt before a singleton exists.
        with self.db.begin():
            ConnectionService(self.db, None)._controls_lock()
            existing = self.db.scalar(select(SocialPrivacyReceipt).join(SocialPrivacyRequestVariant).where(
                SocialPrivacyRequestVariant.app_id == self.config.app_id,
                SocialPrivacyRequestVariant.kind == kind,
                SocialPrivacyRequestVariant.fingerprint == verified.payload_fingerprint))
            if existing:
                return self._response(existing)
            candidates = self.digester.candidates(self.config.app_id, verified.app_scoped_user_id)
            # Canonical verified fields deduplicate whitespace, JSON key order,
            # padding and optional explicit matching app_id. Timestamps define
            # separate events, never request encoding or connection generation.
            keys = [(v, d, canonical_hash([kind, self.config.app_id, d, verified.issued_at, verified.expires_at])) for v, d in candidates]
            existing = self.db.scalar(select(SocialPrivacyReceipt).where(
                SocialPrivacyReceipt.app_id == self.config.app_id, SocialPrivacyReceipt.kind == kind,
                or_(*( (SocialPrivacyReceipt.digest_version == v) & (SocialPrivacyReceipt.event_key == e) for v, _, e in keys))))
            if existing:
                self._variant(existing, verified.payload_fingerprint)
                return self._response(existing)
            now = utc(self.db.scalar(select(func.clock_timestamp()))) if self.db.bind.dialect.name == 'postgresql' else datetime.now(timezone.utc)
            if verified.issued_at and verified.issued_at > int(now.timestamp()) + 300:
                raise invalid()
            versions = set(self.db.scalars(select(SocialPrivacyOwnership.digest_version).where(
                SocialPrivacyOwnership.app_id == self.config.app_id).distinct().limit(17)))
            versions.update(self.db.scalars(select(SocialPrivacyReceipt.digest_version).where(
                SocialPrivacyReceipt.app_id == self.config.app_id).distinct().limit(17)))
            unresolved_keys = not versions <= set(self.digester.keys)
            match = (SocialPrivacyOwnership.app_id == self.config.app_id) & or_(*(
                (SocialPrivacyOwnership.digest_version == v) & (SocialPrivacyOwnership.subject_digest == d)
                for v, d in candidates))
            query = select(SocialPrivacyOwnership).where(match)
            cutoff = verified.issued_at if verified.issued_at is not None else verified.expires_at
            ambiguous = False
            newer = False
            if cutoff is not None:
                from datetime import timedelta
                boundary = datetime.fromtimestamp(cutoff, timezone.utc)
                query = query.where(SocialPrivacyOwnership.generation_at <= boundary)
                ambiguous = self.db.scalar(select(SocialPrivacyOwnership.id).where(match,
                    SocialPrivacyOwnership.generation_at > boundary,
                    SocialPrivacyOwnership.generation_at < boundary + timedelta(seconds=1)).limit(1)) is not None
                newer = self.db.scalar(select(SocialPrivacyOwnership.id).where(match,
                    SocialPrivacyOwnership.generation_at > boundary).limit(1)) is not None
            owners = list(self.db.scalars(query.order_by(SocialPrivacyOwnership.id).limit(MAX_REFERENCES + 1)))
            overflow = len(owners) > MAX_REFERENCES
            if unresolved_keys or overflow:
                owners = []
            resolution = ('digest_key_unavailable' if unresolved_keys else 'reference_limit_exceeded' if overflow
                          else 'indexed_partial_timestamp_ambiguous' if owners and ambiguous
                          else 'indexed_partial' if owners else 'ownership_timestamp_ambiguous' if ambiguous
                          else 'issued_before_indexed_generation' if newer else 'unknown_or_legacy')
            credential_pairs = {(o.credential_id, o.credential_version) for o in owners if o.credential_id}
            related = list(self.db.scalars(select(SocialPrivacyOwnership).where(
                or_(*((SocialPrivacyOwnership.credential_id == c) & (SocialPrivacyOwnership.credential_version == v)
                      for c, v in credential_pairs))).limit(MAX_REFERENCES + 1))) if credential_pairs else []
            if (len(related) > MAX_REFERENCES or any(o.app_id != self.config.app_id
                    or (o.digest_version, o.subject_digest) not in candidates for o in related)):
                owners, resolution = [], 'conflicting_ownership'
            affected = [{'ownership_id': str(o.id), 'flow_id': str(o.flow_id),
                         'credential_id': str(o.credential_id) if o.credential_id else None,
                         'credential_version': o.credential_version,
                         'account_id': str(o.account_id) if o.account_id else None,
                         'page_id': o.page_id} for o in owners]
            state = 'pending_retention_review' if kind == 'data_deletion' else 'blocked_future_mutations' if owners else 'ownership_unresolved'
            # Data deletion also quarantines mapped grants while the policy seam
            # remains pending. Neither kind deletes delivery or credential history.
            changed_versions, blocked = self._block(owners, now)
            if kind == 'deauthorization' and not blocked:
                state = 'ownership_unresolved'
            if changed_versions:
                resolution = 'indexed_partial_version_changed'
            receipt_id, audit_id = uuid4(), uuid4()
            self.db.add(SocialAuditEvent(id=audit_id, actor_kind='provider', action='privacy.received',
                request_id=str(receipt_id), new_state=state,
                details={'receipt_id': str(receipt_id), 'kind': kind, 'affected_count': len(affected), 'resolution': resolution}))
            version, subject, event_key = next(k for k in keys if k[0] == self.digester.active_version)
            row = SocialPrivacyReceipt(id=receipt_id, app_id=self.config.app_id, kind=kind,
                digest_version=version, subject_digest=subject, event_key=event_key,
                request_fingerprint=verified.payload_fingerprint, issued_at=verified.issued_at,
                provider_expires=verified.expires_at, affected=affected, resolution=resolution, state=state, audit_id=audit_id)
            if kind == 'data_deletion':
                code = secrets.token_hex(32)
                row.confirmation_hash = hashlib.sha256(code.encode('ascii')).hexdigest()
                row.confirmation_key_version, row.encrypted_confirmation = self.cipher.encrypt(row.id, 'privacy_confirmation', {'code': code})
                row.status_url_base = self.config.status_url_base
            self.db.add(row)
            self.db.flush()
            self._variant(row, verified.payload_fingerprint)
            result = self._response(row)
        # Transaction exit/commit precedes any acknowledgment returned to ingress.
        return result

    def _variant(self, receipt, fingerprint):
        # Never acknowledge a new exact identity that cannot be persisted.
        # Already retained exact identities bypass this bounded variant insert.
        count = self.db.scalar(select(func.count()).select_from(SocialPrivacyRequestVariant).where(SocialPrivacyRequestVariant.receipt_id == receipt.id))
        if count >= 64:
            raise SocialError('PRIVACY_VARIANT_LIMIT', 'This callback variant cannot be durably accepted. Contact an operator for receipt reconciliation.', 503)
        if count < 64:
            self.db.add(SocialPrivacyRequestVariant(app_id=self.config.app_id, kind=receipt.kind, fingerprint=fingerprint, receipt_id=receipt.id))
            self.db.flush()

    def _block(self, owners, now):
        credentials = {o.credential_id: o.credential_version for o in owners if o.credential_id}
        # More than one historical version may map the same UUID. Only its exact
        # currently indexed version can revoke it; keep all versions frozen.
        versions = {}
        for owner in owners:
            if owner.credential_id:
                versions.setdefault(owner.credential_id, set()).add(owner.credential_version)
        account_ids = {o.account_id for o in owners if o.account_id}
        accounts = list(self.db.scalars(select(SocialAccount).where(SocialAccount.id.in_(account_ids)).order_by(SocialAccount.id).with_for_update().execution_options(populate_existing=True))) if account_ids else []
        rows = list(self.db.scalars(select(SocialCredential).where(SocialCredential.id.in_(credentials)).order_by(SocialCredential.id).with_for_update().execution_options(populate_existing=True))) if credentials else []
        valid = set()
        changed = False
        for credential in rows:
            if credential.version not in versions[credential.id]:
                changed = True
                continue
            valid.add(credential.id)
            if credential.revoked_at is None:
                credential.revoked_at, credential.version, credential.updated_at = now, credential.version + 1, now
        for account in accounts:
            if account.credential_id in valid:
                account.connection_state, account.publishing_enabled = 'revoked', False
                account.hold_reason, account.updated_at = 'PRIVACY_CALLBACK', now
                # Lease, target, intent/checkpoint and remote receipts survive.
        flows = {o.flow_id for o in owners}
        blocked_flow = False
        for flow in self.db.scalars(select(SocialOAuthFlow).where(SocialOAuthFlow.id.in_(flows)).order_by(SocialOAuthFlow.id).with_for_update().execution_options(populate_existing=True)) if flows else []:
            if flow.status in {'exchanging', 'awaiting_selection'}:
                flow.privacy_blocked_at = now
                blocked_flow = True
        return changed, bool(valid) or blocked_flow

    def status(self, confirmation_code):
        # One indistinguishable miss response; no UUID, subject, affected count,
        # timestamp or ownership coverage exposed. Possession of 256 random bits
        # is the capability; never accept receipt IDs as public lookup keys.
        if type(confirmation_code) is not str or not re.fullmatch(r'[0-9a-f]{64}', confirmation_code):
            raise SocialError('NOT_FOUND', 'Request status was not found.', 404)
        with self.db.begin():
            found = self.db.scalar(select(SocialPrivacyReceipt.id).where(
                SocialPrivacyReceipt.confirmation_hash == hashlib.sha256(confirmation_code.encode('ascii')).hexdigest(),
                SocialPrivacyReceipt.kind == 'data_deletion'))
            if found is None:
                raise SocialError('NOT_FOUND', 'Request status was not found.', 404)
            return {'status': 'pending_review', 'message': STATUS_MESSAGE, 'deletion_completed': False}
