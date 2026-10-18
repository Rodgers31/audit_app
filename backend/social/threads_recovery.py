"""Human authority for Threads public outcomes; never provider/API proof.

Two distinct authenticated administrators independently inspect an anonymously
available post and retain captures in operator custody. The application checks
bindings and workflow authority, not the truth of a human's observation. See
THREADS_PUBLIC_OUTCOME.md for the explicit evidence and custody contract.
"""
from datetime import datetime, timedelta
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, field_validator
from sqlalchemy import or_, select, text

from .adapters.common import caption
from .adapters.threads import ThreadsAdapter
from .adapters.meta_http import remote_id
from .contracts import Hash, PositiveVersion, Reason, ResolvedPostPayload, StrictModel, canonical_hash
from .models import (SocialAccount, SocialAuditEvent, SocialCommandReceipt, SocialControls,
                     SocialPostRevision, SocialPostTarget, SocialPublication, SocialPublishAttempt)
from .service import SocialError, SocialService, iso, utc

Identity = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=64, pattern=r'^[0-9]{1,64}$'), AfterValidator(remote_id)]
Narrative = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=30, max_length=1000)]
PROPOSED = 'threads.public_proof_proposed'
ADMITTED = 'threads.public_proof_admitted'


def command_input(value):
    """Revalidate constructed models without serializer coercion (True -> 1)."""
    if isinstance(value, BaseModel):
        value = dict(value)
    if isinstance(value, dict):
        return {key: command_input(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [command_input(item) for item in value]
    return value


class PublicObservation(StrictModel):
    method: Literal['anonymous_browser']
    visibility: Literal['public']
    observed_at: datetime
    capture_sha256: Hash
    custody_reference: UUID
    external_account_id: Identity
    remote_id: Identity
    remote_url: Annotated[str, StringConstraints(strict=True, max_length=256)]
    text: Annotated[str, StringConstraints(strict=True, max_length=20000)]
    asset_sha256: Annotated[tuple[Hash, ...], Field(max_length=20)]
    account_identity_basis: Narrative
    review_notes: Narrative

    @field_validator('remote_url')
    @classmethod
    def permalink(cls, value):
        import re
        # urlsplit discards leading C0/space and embedded tab/CR/LF. Refuse
        # those original bytes before parsing; never attest a normalized URL.
        if not isinstance(value, str) or any(not 0x21 <= ord(char) <= 0x7E for char in value):
            raise ValueError('Use an exact printable ASCII Threads permalink without whitespace or controls')
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or parsed.netloc not in {'www.threads.com', 'threads.com', 'www.threads.net', 'threads.net'}
                or parsed.query or parsed.fragment
                or not re.fullmatch(r'/@[A-Za-z0-9_.]{1,64}/post/[A-Za-z0-9_-]{1,100}', parsed.path)):
            raise ValueError('Use the exact Threads post permalink without query or fragment')
        return value


class ProposePublicProof(StrictModel):
    expected_publication_version: PositiveVersion
    binding_hash: Hash
    observation: PublicObservation
    reason: Reason


class RecordExisting(StrictModel):
    expected_publication_version: PositiveVersion
    proof_id: UUID
    observation: PublicObservation
    reason: Reason


class PublicProofContext(StrictModel):
    target_id: UUID
    publication_id: UUID
    publication_version: PositiveVersion
    revision_id: UUID
    approved_hash: Hash
    payload_hash: Hash
    account_id: UUID
    external_account_id: Identity
    binding_hash: Hash
    caption: str
    asset_sha256: tuple[Hash, ...]
    known_remote_id: Identity | None
    state: str


class PublicProofDTO(StrictModel):
    proof_id: UUID
    target_id: UUID
    binding_hash: Hash
    expires_at: datetime
    state: Literal['awaiting_independent_review']


class SettlementDTO(StrictModel):
    target_id: UUID
    proof_id: UUID
    state: Literal['published']
    remote_id: Identity
    remote_url: str
    publication_version: PositiveVersion


class ThreadsRecoveryService(SocialService):
    """All writes must run inside this service's atomic operator command."""
    _in_operator_command = False

    def command(self, *, actor, route, key, body, request_id, action, status=200):
        if not all(isinstance(v, UUID) for v in (actor, key, request_id)) or self.db.in_transaction():
            raise SocialError('OPERATOR_COMMAND_REQUIRED', 'Use an authenticated, isolated idempotent operator command.', 403)
        self.actor, self.request_id = actor, request_id
        request_hash = canonical_hash(body)
        with self.db.begin():
            # Same first data lock as worker admission and social commands. It
            # serializes duplicate captures/remote identities across all targets.
            controls = self.db.scalar(select(SocialControls).where(SocialControls.id == 1).with_for_update().execution_options(populate_existing=True))
            if controls is None:
                raise SocialError('SOCIAL_SCHEMA_UNAVAILABLE', 'Publishing controls are required for recovery.', 503)
            old = self.db.scalar(select(SocialCommandReceipt).where(SocialCommandReceipt.actor_key == str(actor),
                SocialCommandReceipt.route_key == route, SocialCommandReceipt.idempotency_key == key))
            if old:
                if old.request_hash != request_hash:
                    raise SocialError('IDEMPOTENCY_CONFLICT', 'Command key was already used with different input.')
                return old.http_status, old.response
            before = set(self.db.new)
            self._in_operator_command = True
            try:
                result = action()
            finally:
                self._in_operator_command = False
            receipt = SocialCommandReceipt(id=uuid4(), actor_key=str(actor), route_key=route, idempotency_key=key,
                request_hash=request_hash, http_status=status, response=result,
                resource_id=UUID(result['target_id']), expires_at=self.now()+timedelta(days=30))
            self.db.add(receipt)
            # Save the exact expected writes, not just an ORM success verdict.
            audits = [obj for obj in self.db.new if isinstance(obj, SocialAuditEvent) and obj not in before]
            expected = [(obj, {c.name: getattr(obj, c.name) for c in obj.__table__.columns
                         if getattr(obj, c.name) is not None}) for obj in [*audits, receipt]]
            self.db.flush()
            if self.db.bind.dialect.name == 'postgresql':
                self.db.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
            def primitive(value):
                if isinstance(value, UUID):
                    return str(value)
                if isinstance(value, datetime):
                    return iso(value)
                return value
            for obj, values in expected:
                saved = self.db.execute(select(obj.__table__).where(obj.__table__.c.id == obj.id)).mappings().one_or_none()
                if saved is None or any(canonical_hash(primitive(saved[k])) != canonical_hash(primitive(v)) for k, v in values.items()):
                    raise SocialError('RECOVERY_PERSISTENCE_FAILED', 'Operator evidence was not durably stored as required.', 503)
            self._verify_settlement(result)
        return status, result

    def _require_command(self):
        if not self._in_operator_command or not self.db.in_transaction() or not isinstance(self.actor, UUID):
            raise SocialError('OPERATOR_COMMAND_REQUIRED', 'Use the authenticated idempotent operator command.', 403)

    def _load(self, target_id, version=None, *, lock=False):
        initial = self.db.get(SocialPostTarget, target_id)
        if initial is None:
            raise SocialError('NOT_FOUND', 'This destination was not found.', 404)
        def row(model, identity):
            query = select(model).where(model.id == identity).execution_options(populate_existing=True)
            return self.db.scalar(query.with_for_update() if lock else query)
        account = row(SocialAccount, initial.account_id)
        publication = row(SocialPublication, initial.publication_id)
        target = row(SocialPostTarget, target_id)
        revision = row(SocialPostRevision, publication.revision_id)
        if version is not None and publication.version != version:
            raise SocialError('VERSION_CONFLICT', 'Publication changed. Obtain fresh evidence.')
        try:
            payload = ResolvedPostPayload.model_validate(target.resolved_payload)
            remote_id(payload.external_account_id)
            if (account.platform != 'threads' or payload.platform != 'threads' or payload.account_id != account.id
                    or payload.external_account_id != account.external_account_id or payload.api_product != account.api_product
                    or canonical_hash(payload.model_dump(mode='json', exclude={'content_hash'})) != target.payload_hash
                    or payload.content_hash != target.payload_hash or publication.approved_hash != revision.content_hash
                    or revision.content_hash != canonical_hash({'document':revision.document, 'evidence_snapshot':revision.evidence_snapshot})):
                raise ValueError('Immutable binding mismatch')
            ThreadsAdapter._checkpoint(payload, target.checkpoint)
            if not isinstance(target.remote_refs, dict):
                raise ValueError('Invalid remote references')
            for identity in (target.primary_remote_id, target.remote_refs.get('post_id')):
                if identity is not None:
                    remote_id(identity)
        except (ValueError, TypeError, AttributeError):
            raise SocialError('PROOF_BINDING_INVALID', 'Approved Threads identity or payload is inconsistent.') from None
        if target.state not in {'processing', 'reconciling', 'outcome_unknown'} or target.submit_count < 1:
            raise SocialError('RECONCILIATION_REQUIRED', 'Only an attempted unresolved Threads target can be settled.')
        dispatched = self.db.scalar(select(SocialPublishAttempt).where(SocialPublishAttempt.target_id == target.id,
            SocialPublishAttempt.operation == 'publish', SocialPublishAttempt.dispatch_started_at.is_not(None))
            .order_by(SocialPublishAttempt.sequence.desc()).limit(1))
        intent = dispatched.receipt.get('intent') if dispatched and isinstance(dispatched.receipt, dict) else None
        if (not isinstance(intent, dict) or intent.get('publication_capable') is not True
                or intent.get('mutating') is not True or intent.get('safe_replay_class') != 'requires_reconciliation'):
            raise SocialError('RECONCILIATION_REQUIRED', 'A durable public dispatch intent is required.')
        if (any(getattr(target, k) is not None for k in ('lease_owner','lease_token','lease_expires_at'))
                or any(getattr(account, k) is not None for k in ('publish_lease_target_id','publish_lease_token','publish_lease_expires_at'))
                or self.db.scalar(select(SocialPublishAttempt.id).where(SocialPublishAttempt.target_id == target.id, SocialPublishAttempt.completed_at.is_(None)).limit(1))):
            raise SocialError('RECOVERY_BUSY', 'Finish worker recovery and drain operations before recording proof.')
        snapshot = dict(target_id=str(target.id), account_id=str(account.id), publication_id=str(publication.id),
            revision_id=str(revision.id), approved_hash=publication.approved_hash, payload_hash=target.payload_hash,
            external_account_id=account.external_account_id, api_product=account.api_product,
            publication_version=publication.version, state=target.state, lease_epoch=target.lease_epoch,
            submit_count=target.submit_count, checkpoint=target.checkpoint, remote_refs=target.remote_refs,
            remote_id=target.primary_remote_id, remote_url=target.remote_url, updated_at=iso(target.updated_at),
            dispatch_attempt_id=str(dispatched.id))
        return account, publication, target, payload, snapshot

    def context(self, target_id):
        account, pub, target, payload, snapshot = self._load(target_id)
        return dict(target_id=str(target.id), publication_id=str(pub.id), publication_version=pub.version,
            revision_id=str(pub.revision_id), approved_hash=pub.approved_hash, payload_hash=target.payload_hash,
            account_id=str(account.id), external_account_id=account.external_account_id,
            binding_hash=canonical_hash(snapshot), caption=caption(payload), asset_sha256=[a.sha256 for a in payload.assets],
            known_remote_id=target.primary_remote_id, state=target.state)

    def _observation(self, observation, account, target, payload):
        observation = PublicObservation.model_validate(command_input(observation))
        now = self.now()
        if not now-timedelta(minutes=30) <= observation.observed_at <= now:
            raise SocialError('PROOF_EXPIRED', 'Observe public availability within the last thirty minutes.')
        known = [target.primary_remote_id, target.remote_refs.get('post_id'), (target.checkpoint or {}).get('post_id')]
        if (observation.external_account_id != account.external_account_id or any(v is not None and v != observation.remote_id for v in known)
                or observation.text != caption(payload) or observation.asset_sha256 != tuple(a.sha256 for a in payload.assets)
                or (target.remote_url is not None and target.remote_url != observation.remote_url)):
            raise SocialError('PROOF_MISMATCH', 'Observation must match the exact approved content, owner and existing remote identity.')
        duplicate = self.db.scalar(select(SocialPostTarget.id).join(SocialAccount, SocialAccount.id == SocialPostTarget.account_id).where(
            SocialAccount.platform == 'threads', SocialAccount.external_account_id == account.external_account_id,
            SocialPostTarget.id != target.id, or_(SocialPostTarget.primary_remote_id == observation.remote_id,
                SocialPostTarget.remote_refs['post_id'].as_string() == observation.remote_id,
                SocialPostTarget.checkpoint['post_id'].as_string() == observation.remote_id)).limit(1))
        reused = self.db.scalar(select(SocialAuditEvent.id).where(SocialAuditEvent.action.in_((PROPOSED, ADMITTED)),
            (SocialAuditEvent.details['capture_sha256'].as_string() == observation.capture_sha256)
            | (SocialAuditEvent.details['observation']['custody_reference'].as_string() == str(observation.custody_reference))).limit(1))
        if duplicate or reused:
            raise SocialError('PROOF_REPLAY', 'This remote publication or capture is already recorded.')

    def propose(self, target_id, body):
        self._require_command()
        body = ProposePublicProof.model_validate(command_input(body))
        account, pub, target, payload, snapshot = self._load(target_id, body.expected_publication_version, lock=True)
        if body.binding_hash != canonical_hash(snapshot):
            raise SocialError('VERSION_CONFLICT', 'Target evidence changed. Obtain a fresh binding.')
        self._observation(body.observation, account, target, payload)
        proof_id, expires = uuid4(), body.observation.observed_at+timedelta(minutes=30)
        self.db.add(SocialAuditEvent(id=proof_id, post_id=pub.post_id, target_id=target.id, account_id=account.id,
            actor_kind='admin', actor_id=self.actor, request_id=str(self.request_id), action=PROPOSED, reason=body.reason,
            previous_state=target.state, new_state=target.state,
            details={'contract':'threads-two-admin-public-v1','binding':snapshot,'binding_hash':body.binding_hash,
                     'expires_at':iso(expires),'observation':body.observation.model_dump(mode='json'),
                     'capture_sha256':body.observation.capture_sha256}))
        return dict(proof_id=str(proof_id), target_id=str(target.id), binding_hash=body.binding_hash,
            expires_at=iso(expires), state='awaiting_independent_review')

    def record_existing(self, target_id, body):
        self._require_command()
        body = RecordExisting.model_validate(command_input(body))
        account, pub, target, payload, snapshot = self._load(target_id, body.expected_publication_version, lock=True)
        proof = self.db.get(SocialAuditEvent, body.proof_id)
        if not proof or proof.action != PROPOSED or proof.target_id != target.id or proof.account_id != account.id or proof.post_id != pub.post_id:
            raise SocialError('PROOF_MISMATCH', 'Proposal does not identify this target.')
        if proof.actor_kind != 'admin' or proof.actor_id is None or proof.actor_id == self.actor:
            raise SocialError('INDEPENDENT_REVIEW_REQUIRED', 'A different administrator must independently observe and admit proof.', 403)
        try:
            original = PublicObservation.model_validate(proof.details['observation'])
            expires = datetime.fromisoformat(proof.details['expires_at'].replace('Z','+00:00'))
            if (proof.details['contract'] != 'threads-two-admin-public-v1' or expires.tzinfo is None
                    or self.now() >= expires or proof.details['binding_hash'] != canonical_hash(snapshot)
                    or canonical_hash(proof.details['binding']) != canonical_hash(snapshot)):
                raise ValueError('Stale evidence')
        except (ValueError, TypeError, KeyError):
            raise SocialError('PROOF_EXPIRED', 'Proposal is stale or invalid; collect fresh public proof.') from None
        self._observation(body.observation, account, target, payload)
        if (original.remote_id != body.observation.remote_id or original.remote_url != body.observation.remote_url
                or original.capture_sha256 == body.observation.capture_sha256
                or original.custody_reference == body.observation.custody_reference):
            raise SocialError('PROOF_MISMATCH', 'Independent captures must identify the same post with separate custody records.')
        previous, now = target.state, self.now()
        target.state, target.visibility_state, target.confirmation_kind = 'published', 'public', 'threads_two_admin_public_v1'
        target.primary_remote_id, target.remote_url, target.published_at = body.observation.remote_id, body.observation.remote_url, now
        target.error_code = target.safe_error_message = target.next_action = target.next_action_at = None
        target.updated_at = now
        # Preserve all checkpoint/attempt history and unrelated account holds.
        if account.hold_reason == 'RECONCILIATION_REQUIRED:' + str(target.id):
            account.hold_reason, account.updated_at = None, now
        pub.version, pub.updated_at = pub.version+1, now
        self.db.add(SocialAuditEvent(id=uuid4(), post_id=pub.post_id, target_id=target.id, account_id=account.id,
            actor_kind='admin', actor_id=self.actor, request_id=str(self.request_id), action=ADMITTED, reason=body.reason,
            previous_state=previous, new_state='published',
            details={'contract':'threads-two-admin-public-v1','proof_id':str(proof.id),'binding':snapshot,
                     'observation':body.observation.model_dump(mode='json'),'capture_sha256':body.observation.capture_sha256}))
        self._expected_settlement = (target.id, target.primary_remote_id, target.remote_url, pub.id, pub.version, account.id, account.hold_reason,
                                     target.checkpoint, target.remote_refs, target.submit_count, iso(now))
        return dict(target_id=str(target.id), proof_id=str(proof.id), state='published', remote_id=target.primary_remote_id,
                    remote_url=target.remote_url, publication_version=pub.version)

    def _verify_settlement(self, result):
        if result['state'] != 'published':
            return
        target_id, remote_id, url, pub_id, version, account_id, hold, checkpoint, refs, count, when = self._expected_settlement
        self.db.expire_all()
        target, pub, account = self.db.get(SocialPostTarget, target_id), self.db.get(SocialPublication, pub_id), self.db.get(SocialAccount, account_id)
        if (target.state != 'published' or target.primary_remote_id != remote_id or target.remote_url != url
                or target.confirmation_kind != 'threads_two_admin_public_v1' or target.visibility_state != 'public'
                or iso(target.published_at) != when or target.next_action is not None or target.next_action_at is not None
                or target.error_code is not None or target.safe_error_message is not None
                or canonical_hash(target.checkpoint) != canonical_hash(checkpoint) or canonical_hash(target.remote_refs) != canonical_hash(refs)
                or target.submit_count != count or pub.version != version or account.hold_reason != hold):
            raise SocialError('RECOVERY_PERSISTENCE_FAILED', 'Settlement was not durably stored as required.', 503)
