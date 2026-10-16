"""Human-authorized local erasure, durable intent before effects, no remote APIs."""
from datetime import datetime, timezone
import hashlib
from uuid import UUID, uuid4
from sqlalchemy import func, select
from ..connections.models import SocialCredential, SocialOAuthFlow
from ..connections.service import ConnectionService
from ..contracts import canonical_hash
from ..models import SocialAccount, SocialAuditEvent
from ..service import SocialError, utc
from .models import SocialPrivacyOwnership, SocialPrivacyReceipt
from .workflow_models import PrivacyPlan, PrivacyDecision, PrivacyExecution, PrivacyExecutionEvent
from .workflow_contracts import PrivacyProposal, PrivacyApproval, PrivacyWorkflowConfig
from .deletion_ledger import validate_intent


def refuse(code='PRIVACY_AUTHORITY_REQUIRED', message='An approved current policy and exact scope are required.'):
    return SocialError(code, message, 409)


def flow_hash(flow):
    return canonical_hash({'status': flow.status, 'key_version': flow.key_version,
        'verifier': hashlib.sha256(flow.encrypted_verifier or b'').hexdigest(),
        'pending': hashlib.sha256(flow.encrypted_pending_grant or b'').hexdigest()})


def flow_identity_hash(flow):
    return canonical_hash({'id': str(flow.id), 'actor_id': str(flow.actor_id), 'provider': flow.provider,
        'state_hash': flow.state_hash, 'binding_hash': flow.binding_hash, 'redirect_uri': flow.redirect_uri,
        'expires_at': utc(flow.expires_at).isoformat(), 'reconnect_account_id': str(flow.reconnect_account_id) if flow.reconnect_account_id else None})


class PrivacyWorkflow:
    def __init__(self, db, config, *, cipher=None, ledger=None, media=None):
        if type(config) is not PrivacyWorkflowConfig:
            raise ValueError('PRIVACY_WORKFLOW_CONFIGURATION_INVALID')
        config.validate()
        self.db, self.config, self.cipher, self.ledger, self.media = db, config, cipher, ledger, media

    def _enabled(self, execution=False):
        if not self.config.enabled or (execution and not self.config.execution_enabled):
            raise SocialError('PRIVACY_WORKFLOW_DISABLED', 'Privacy execution is disabled pending operator approval.', 503)

    def _policy(self, key, digest):
        if (key, digest) not in self.config.policies:
            raise refuse('PRIVACY_POLICY_UNAPPROVED')

    def _actor(self, actor):
        if type(actor) is not UUID or actor.int == 0:
            raise SocialError('PERMISSION_DENIED', 'A valid administrator identity is required.', 403)

    def propose(self, actor, command_id, command):
        self._enabled()
        self._actor(actor)
        if type(command_id) is not UUID or command_id.int == 0 or type(command) is not PrivacyProposal:
            raise refuse()
        self._policy(command.policy_key, command.policy_hash)
        media_scopes = []
        for asset_id in sorted(command.media_assets):
            if self.media is None:
                raise refuse('PRIVACY_MEDIA_PORT_UNAVAILABLE')
            inspected = self.media.inspect_scope(asset_id)
            import re
            if (type(inspected) is not dict or set(inspected) != {'asset_id', 'scope_hash'}
                    or inspected['asset_id'] != str(asset_id) or type(inspected['scope_hash']) is not str
                    or re.fullmatch('[a-f0-9]{64}', inspected['scope_hash']) is None):
                raise refuse('PRIVACY_MEDIA_SCOPE_UNAVAILABLE')
            media_scopes.append({'id': str(asset_id), 'scope_hash': inspected['scope_hash']})
        with self.db.begin():
            ConnectionService(self.db, None)._controls_lock()
            prior = self.db.get(PrivacyPlan, command_id)
            if prior:
                if prior.proposed_by != actor or prior.evidence != command.evidence or prior.receipt_id != command.receipt_id or prior.policy_key != command.policy_key or prior.policy_hash != command.policy_hash or any(
                    sorted(e['id'] for e in prior.scope[k]) != sorted(str(i) for i in ids) for k, ids in (
                        ('credentials', command.erase_credentials), ('flows', command.erase_flows), ('media_assets', command.media_assets))):
                    raise refuse('IDEMPOTENCY_CONFLICT')
                return self._plan(prior)
            receipt = self.db.get(SocialPrivacyReceipt, command.receipt_id)
            if receipt is None or receipt.kind != 'data_deletion' or not receipt.affected or not receipt.resolution.startswith('indexed_partial'):
                raise refuse('PRIVACY_OWNERSHIP_UNRESOLVED')
            # Frozen callback mappings bound the candidate credential/flow set.
            credentials = {UUID(r['credential_id']) for r in receipt.affected if r['credential_id']}
            flows = {UUID(r['flow_id']) for r in receipt.affected}
            if not set(command.erase_credentials) <= credentials or not set(command.erase_flows) <= flows:
                raise refuse('PRIVACY_SCOPE_UNRESOLVED')
            scope = {'credentials': [], 'flows': [], 'media_assets': media_scopes}
            for identity in sorted(command.erase_credentials):
                row = self.db.get(SocialCredential, identity, populate_existing=True)
                if row is None or row.revoked_at is None or row.refresh_lease_token:
                    raise refuse('PRIVACY_CREDENTIAL_BUSY')
                # No unrelated ownership may be erased by shared grant identity.
                owners = self.db.scalars(select(SocialPrivacyOwnership).where(SocialPrivacyOwnership.credential_id == identity)).all()
                if any(o.app_id != receipt.app_id or (o.digest_version, o.subject_digest) != (receipt.digest_version, receipt.subject_digest)
                       and str(o.id) not in {r['ownership_id'] for r in receipt.affected} for o in owners):
                    raise refuse('PRIVACY_SCOPE_UNRESOLVED')
                scope['credentials'].append({'id': str(identity), 'version': row.version})
            for identity in sorted(command.erase_flows):
                row = self.db.get(SocialOAuthFlow, identity, populate_existing=True)
                if row is None or row.status == 'exchanging':
                    raise refuse('PRIVACY_FLOW_BUSY')
                scope['flows'].append({'id': str(identity), 'content_hash': flow_hash(row), 'identity_hash': flow_identity_hash(row)})
            if not any(scope.values()):
                raise refuse('PRIVACY_EMPTY_SCOPE')
            digest = canonical_hash({'receipt_id': str(receipt.id), 'policy_key': command.policy_key,
                'policy_hash': command.policy_hash, 'evidence': command.evidence, 'scope': scope})
            plan = PrivacyPlan(id=command_id, receipt_id=receipt.id, proposed_by=actor, policy_key=command.policy_key,
                policy_hash=command.policy_hash, evidence=command.evidence, scope=scope, plan_hash=digest)
            self.db.add(plan)
            self._audit(actor, 'privacy.proposed', plan.id, {'plan_hash': digest})
            self.db.flush()
            result = self._plan(plan)
        return result

    def decide(self, actor, plan_id, command):
        self._enabled()
        self._actor(actor)
        if actor not in self.config.approvers or type(command) is not PrivacyApproval:
            raise SocialError('PERMISSION_DENIED', 'An explicitly configured privacy approver is required.', 403)
        with self.db.begin():
            ConnectionService(self.db, None)._controls_lock()
            plan = self.db.get(PrivacyPlan, plan_id)
            if plan is None:
                raise SocialError('NOT_FOUND', 'Privacy plan was not found.', 404)
            self._policy(plan.policy_key, plan.policy_hash)
            if actor == plan.proposed_by or command.plan_hash != plan.plan_hash:
                raise refuse('PRIVACY_INDEPENDENT_APPROVAL_REQUIRED')
            prior = self.db.scalar(select(PrivacyDecision).where(PrivacyDecision.plan_id == plan.id))
            if prior:
                if (prior.approved_by, prior.decision, prior.reason, prior.plan_hash) != (actor, command.decision, command.reason, command.plan_hash):
                    raise refuse('PRIVACY_DECISION_CONFLICT')
            else:
                self.db.add(PrivacyDecision(plan_id=plan.id, approved_by=actor, plan_hash=plan.plan_hash, decision=command.decision, reason=command.reason))
                if command.decision == 'approved':
                    self.db.add(PrivacyExecution(plan_id=plan.id, state='prepared', result={}))
                self._audit(actor, 'privacy.' + command.decision, plan.id, {'plan_hash': plan.plan_hash})
            self.db.flush()
        return self.get(plan_id)

    @staticmethod
    def _plan(plan):
        return {'id': str(plan.id), 'receipt_id': str(plan.receipt_id), 'proposed_by': str(plan.proposed_by),
            'policy_key': plan.policy_key, 'policy_hash': plan.policy_hash, 'plan_hash': plan.plan_hash,
            'evidence': plan.evidence, 'scope': plan.scope}

    def get(self, plan_id):
        with self.db.begin():
            plan = self.db.get(PrivacyPlan, plan_id)
            if plan is None:
                raise SocialError('NOT_FOUND', 'Privacy plan was not found.', 404)
            result = self._plan(plan)
            decision = self.db.scalar(select(PrivacyDecision).where(PrivacyDecision.plan_id == plan.id))
            execution = self.db.scalar(select(PrivacyExecution).where(PrivacyExecution.plan_id == plan.id))
            result.update(decision=decision.decision if decision else 'pending_review', approved_by=str(decision.approved_by) if decision else None,
                execution={'id': str(execution.id), 'state': execution.state, 'version': execution.version, 'result': execution.result} if execution else None)
        return result

    def _audit(self, actor, action, plan_id, details):
        self.db.add(SocialAuditEvent(actor_kind='human', actor_id=actor, action=action, request_id=str(plan_id), details=details))

    def _persist(self, records):
        def stable(value):
            if isinstance(value, UUID):
                return str(value)
            if isinstance(value, datetime):
                return utc(value).isoformat()
            if type(value) is bytes:
                return {'bytes_sha256': hashlib.sha256(value).hexdigest()}
            return value
        expected = [(record, {c.name: stable(getattr(record, c.name)) for c in record.__table__.columns
            if c.name not in {'created_at', 'updated_at'} and getattr(record, c.name) is not None}) for record in records]
        self.db.flush()
        if self.db.bind.dialect.name == 'postgresql':
            from sqlalchemy import text
            self.db.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
        for record, fields in expected:
            self.db.refresh(record)
            if canonical_hash({key: stable(getattr(record, key)) for key in fields}) != canonical_hash(fields):
                raise refuse('PRIVACY_PERSISTENCE_UNCONFIRMED')

    def _event(self, execution, state, details):
        execution.state, execution.version, execution.result = state, execution.version + 1, details
        execution.updated_at = datetime.now(timezone.utc)
        self.db.add(PrivacyExecutionEvent(execution_id=execution.id, state=state, details=details))
        self._persist([execution])

    def execute(self, actor, plan_id, expected_version):
        self._enabled(execution=True)
        self._actor(actor)
        if actor not in self.config.approvers or type(expected_version) is not int or expected_version <= 0:
            raise refuse()
        if self.cipher is None or self.ledger is None:
            raise refuse('PRIVACY_CUSTODY_UNAVAILABLE')
        with self.db.begin():
            ConnectionService(self.db, None)._controls_lock()
            plan = self.db.get(PrivacyPlan, plan_id)
            decision = self.db.scalar(select(PrivacyDecision).where(PrivacyDecision.plan_id == plan_id))
            execution = self.db.scalar(select(PrivacyExecution).where(PrivacyExecution.plan_id == plan_id).with_for_update().execution_options(populate_existing=True))
            if plan is None or decision is None or decision.decision != 'approved' or execution is None or decision.plan_hash != plan.plan_hash:
                raise refuse()
            self._policy(plan.policy_key, plan.policy_hash)
            if execution.state == 'completed':
                return {'state': 'completed', 'scope_completed': True, 'request_completed': False}
            if execution.version != expected_version:
                raise refuse('VERSION_CONFLICT')
            # Unknown or interrupted execution never automatically repeats media writes.
            if execution.state != 'prepared':
                raise refuse('PRIVACY_RECONCILIATION_REQUIRED')
            if plan.scope['media_assets'] and self.media is None:
                raise refuse('PRIVACY_MEDIA_PORT_UNAVAILABLE')
            intent = {'schema_version': 1, 'operation_id': str(execution.id), 'plan_id': str(plan.id),
                'plan_hash': plan.plan_hash, 'policy_hash': plan.policy_hash, 'scope': plan.scope}
            validate_intent(intent)
            operation = execution.id
            # Commit public-send intent before external custody or object operations.
            self._event(execution, 'executing', {'stage': 'intent_required'})
        try:
            ledger_hash = self.ledger.persist(intent)
            if type(ledger_hash) is not str or len(ledger_hash) != 64:
                raise ValueError('PRIVACY_LEDGER_REFUSED')
            # Credential and pending-flow erasure commits atomically; failure leaves
            # the external intent authoritative and is replayable after restart.
            with self.db.begin():
                ConnectionService(self.db, None)._controls_lock()
                self.apply_intent(intent, strict=True)
            media_results = self._media_execute(intent)
            if not all(r['verified'] for r in media_results):
                raise refuse('PRIVACY_MEDIA_OUTCOME_UNKNOWN')
            with self.db.begin():
                execution = self.db.get(PrivacyExecution, operation, with_for_update=True, populate_existing=True)
                self._event(execution, 'completed', {'ledger_sha256': ledger_hash, 'local_erasure_verified': True,
                    'media': media_results, 'scope_completed': True, 'request_completed': False,
                    'retained': ['audit', 'delivery', 'ownership', 'financial_provenance', 'backups_pending_policy']})
                self._audit(actor, 'privacy.scope_completed', plan_id, {'operation_id': str(operation)})
        except Exception:
            # No fake success. A failed completion persist retains executing and
            # the separately fsynced intent; the next process must reconcile.
            self.db.rollback()
            with self.db.begin():
                execution = self.db.get(PrivacyExecution, operation, with_for_update=True, populate_existing=True)
                if execution.state != 'completed':
                    self._event(execution, 'outcome_unknown', {'stage': 'reconciliation_required'})
            raise SocialError('PRIVACY_RECONCILIATION_REQUIRED', 'Execution needs reconciliation. The approved intent and history are retained.', 409) from None
        return self.get(plan_id)

    def _media_execute(self, intent):
        # The media lane implements the typed port; no raw storage delete lives here.
        if not intent['scope']['media_assets']:
            return []
        from .media_port import PrivacyMediaDeletionCommand, PrivacyMediaDeletionResult
        results = []
        for asset in intent['scope']['media_assets']:
            command = PrivacyMediaDeletionCommand(operation_id=UUID(intent['operation_id']), authority_id=UUID(intent['plan_id']),
                asset_id=UUID(asset['id']), plan_hash=intent['plan_hash'], policy_hash=intent['policy_hash'])
            result = self.media.execute(command)
            if type(result) is not PrivacyMediaDeletionResult or result.operation_id != command.operation_id or result.asset_id != command.asset_id:
                raise refuse('PRIVACY_MEDIA_OUTCOME_UNKNOWN')
            results.append({'asset_id': asset['id'], 'verified': result.verified_deleted, 'state': result.state})
        return results

    def apply_intent(self, intent, *, strict=False):
        """Inside a caller transaction, reapply an authenticated external intent.

        A later credential generation cannot be silently erased by old authority.
        A pre-deletion backup can have an earlier version and MUST be suppressed.
        """
        validate_intent(intent)
        now = datetime.now(timezone.utc)
        changed = []
        for item in intent['scope']['credentials']:
            row = self.db.get(SocialCredential, UUID(item['id']), with_for_update=True, populate_existing=True)
            if row is None:
                if strict:
                    raise refuse('PRIVACY_SCOPE_CHANGED')
                continue
            marker = {'privacy_erased': True, 'authority_id': intent['plan_id']}
            existing = self.cipher.decrypt(row.id, row.credential_kind, row.key_version, row.encrypted_bundle)
            if existing == marker:
                continue
            if row.version > item['version'] or (strict and row.version != item['version']) or row.refresh_lease_token:
                raise refuse('PRIVACY_SCOPE_CHANGED')
            accounts = self.db.scalars(select(SocialAccount).where(SocialAccount.credential_id == row.id).with_for_update().execution_options(populate_existing=True)).all()
            if any(a.publish_lease_token or a.publish_lease_target_id or a.publish_lease_expires_at for a in accounts):
                raise refuse('PRIVACY_CREDENTIAL_BUSY')
            row.key_version, row.encrypted_bundle = self.cipher.encrypt(row.id, row.credential_kind, marker)
            row.revoked_at, row.version, row.updated_at = now, row.version + 1, now
            changed.append(row)
            for account in accounts:
                account.publishing_enabled, account.connection_state = False, 'revoked'
                account.hold_reason, account.updated_at = 'PRIVACY_APPROVED_ERASURE', now
                changed.append(account)
        for item in intent['scope']['flows']:
            row = self.db.get(SocialOAuthFlow, UUID(item['id']), with_for_update=True, populate_existing=True)
            if row is None:
                if strict:
                    raise refuse('PRIVACY_SCOPE_CHANGED')
                continue
            if row.status in {'failed', 'expired', 'completed'} and row.encrypted_verifier is None and row.encrypted_pending_grant is None:
                continue
            if flow_identity_hash(row) != item['identity_hash'] or (strict and flow_hash(row) != item['content_hash']) or row.status == 'exchanging':
                raise refuse('PRIVACY_SCOPE_CHANGED')
            row.status, row.encrypted_verifier, row.encrypted_pending_grant = 'failed', None, None
            row.privacy_blocked_at, row.updated_at = now, now
            changed.append(row)
        self._persist(changed)
        # Ciphertext and flow NULL outcomes must be observed from storage.
        for item in intent['scope']['credentials']:
            row = self.db.get(SocialCredential, UUID(item['id']))
            if row is not None and self.cipher.decrypt(row.id, row.credential_kind, row.key_version, row.encrypted_bundle) != {'privacy_erased': True, 'authority_id': intent['plan_id']}:
                raise refuse('PRIVACY_PERSISTENCE_UNCONFIRMED')
        for item in intent['scope']['flows']:
            row = self.db.get(SocialOAuthFlow, UUID(item['id']))
            if row is not None and (row.encrypted_verifier is not None or row.encrypted_pending_grant is not None):
                raise refuse('PRIVACY_PERSISTENCE_UNCONFIRMED')

    def reconcile(self, actor, plan_id, expected_version):
        """Explicit read-only media reconciliation; never resends object deletion."""
        self._enabled(execution=True)
        self._actor(actor)
        if actor not in self.config.approvers or type(expected_version) is not int or expected_version <= 0 or self.ledger is None or self.cipher is None:
            raise refuse()
        with self.db.begin():
            ConnectionService(self.db, None)._controls_lock()
            plan = self.db.get(PrivacyPlan, plan_id)
            execution = self.db.scalar(select(PrivacyExecution).where(PrivacyExecution.plan_id == plan_id).with_for_update().execution_options(populate_existing=True))
            decision = self.db.scalar(select(PrivacyDecision).where(PrivacyDecision.plan_id == plan_id))
            if plan is None or execution is None or decision is None or decision.decision != 'approved' or decision.plan_hash != plan.plan_hash:
                raise refuse()
            self._policy(plan.policy_key, plan.policy_hash)
            if execution.state == 'completed':
                return {'state': 'completed', 'scope_completed': True, 'request_completed': False}
            if execution.version != expected_version or execution.state not in {'executing', 'outcome_unknown'}:
                raise refuse('VERSION_CONFLICT')
            intent = self.ledger.read(execution.id)
            if intent['plan_hash'] != plan.plan_hash or intent['plan_id'] != str(plan.id) or intent['scope'] != plan.scope:
                raise refuse('PRIVACY_LEDGER_MISMATCH')
            self.apply_intent(intent)
            operation = execution.id
        from .media_port import PrivacyMediaDeletionCommand, PrivacyMediaDeletionResult
        results = []
        for item in intent['scope']['media_assets']:
            if self.media is None:
                raise refuse('PRIVACY_MEDIA_PORT_UNAVAILABLE')
            command = PrivacyMediaDeletionCommand(operation, plan_id, UUID(item['id']), intent['plan_hash'], intent['policy_hash'])
            result = self.media.reconcile(command)
            if type(result) is not PrivacyMediaDeletionResult or result.operation_id != operation or result.asset_id != command.asset_id or result.verified_deleted is not True:
                raise refuse('PRIVACY_RECONCILIATION_REQUIRED')
            results.append({'asset_id': item['id'], 'verified': True, 'state': result.state})
        with self.db.begin():
            execution = self.db.get(PrivacyExecution, operation, with_for_update=True, populate_existing=True)
            if execution.state != 'completed':
                self._event(execution, 'completed', {'local_erasure_verified': True, 'media': results,
                    'scope_completed': True, 'request_completed': False, 'reconciled': True,
                    'retained': ['audit', 'delivery', 'ownership', 'financial_provenance', 'backups_pending_policy']})
                self._audit(actor, 'privacy.scope_reconciled', plan_id, {'operation_id': str(operation)})
        return self.get(plan_id)
