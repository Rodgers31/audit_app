"""Bridge to the independently approved privacy workflow, without owning keys.

Imported lazily so the media candidate remains testable before the predecessor
privacy migration lands. Both migrations and the privacy workflow are required
for actual composition. Reconciliation is a database-only observation; it never
repeats a storage mutation or converts missing history to completed deletion.
"""
from dataclasses import replace
from datetime import datetime, timezone
import re
from uuid import UUID, uuid5

from sqlalchemy import select

from ..contracts import canonical_hash
from .deletion import (MediaDeletionAuthority, MediaDeletionExecutor,
    PrivacyMediaDeletionCommand, completed_deletion_matches)
from .models import SocialMediaDeletion


def _approved_plan(db, command, approved_hashes, ledger):
    from ..privacy.workflow_models import PrivacyPlan, PrivacyDecision, PrivacyExecution
    plan = db.get(PrivacyPlan, command.authority_id)
    decision = db.scalar(select(PrivacyDecision).where(PrivacyDecision.plan_id == command.authority_id))
    execution = db.scalar(select(PrivacyExecution).where(PrivacyExecution.plan_id == command.authority_id))
    if (plan is None or decision is None or execution is None or decision.decision != 'approved'
            or decision.approved_by == plan.proposed_by or decision.plan_hash != plan.plan_hash
            or plan.policy_hash not in approved_hashes or command.plan_hash != plan.plan_hash
            or command.policy_hash != plan.policy_hash or type(plan.scope) is not dict):
        return None
    if plan.plan_hash != canonical_hash({'receipt_id': str(plan.receipt_id), 'policy_key': plan.policy_key,
            'policy_hash': plan.policy_hash, 'evidence': plan.evidence, 'scope': plan.scope}):
        return None
    assets = plan.scope.get('media_assets')
    if (type(assets) is not list or not assets or len(assets) > 500
            or any(type(item) is not dict or set(item) != {'id', 'scope_hash'}
                   or type(item['id']) is not str or type(item['scope_hash']) is not str
                   or re.fullmatch('[0-9a-f]{64}', item['scope_hash']) is None for item in assets)
            or sum(item['id'] == str(command.asset_id) for item in assets) != 1):
        return None
    if ledger is None:
        return None
    from ..privacy.deletion_ledger import validate_intent
    intent = ledger.read(execution.id)
    validate_intent(intent)
    if (intent['operation_id'] != str(execution.id) or intent['plan_id'] != str(plan.id)
            or intent['plan_hash'] != plan.plan_hash or intent['policy_hash'] != plan.policy_hash
            or canonical_hash(intent['scope']) != canonical_hash(plan.scope)):
        return None
    return plan, execution


class DatabaseMediaDeletionAuthority:
    """Exact durable approval plus separately configured storage-policy digest.

    Policy approval must cover exclusive conditional writers, unversioned R2,
    no lifecycle/key removal, retained minimal fence bytes and remaining history.
    This configuration is separate from the privacy policy allowlist: neither
    permission alone authorizes a media effect.
    """
    def __init__(self, session_factory, approved_hashes, ledger):
        self.session_factory, self.approved_hashes, self.ledger = session_factory, approved_hashes, ledger

    def verify(self, command, scope):
        with self.session_factory() as db, db.begin():
            found = _approved_plan(db, command, self.approved_hashes, self.ledger)
            if found is None:
                return None
            plan, execution = found
            approved_scope = next(item['scope_hash'] for item in plan.scope['media_assets'] if item['id'] == str(command.asset_id))
            if (plan.receipt_id != command.receipt_id or execution.state != 'executing'
                    or command.expected_scope_hash != approved_scope
                    or uuid5(execution.id, str(command.asset_id)) != command.operation_id):
                return None
            return MediaDeletionAuthority(command=command, scope_hash=scope.scope_hash,
                policy_hash=plan.policy_hash, verified_at=datetime.now(timezone.utc))


class PrivacyWorkflowMediaAdapter:
    def __init__(self, session_factory, runtime, ledger=None):
        self.session_factory, self.runtime, self.ledger = session_factory, runtime, ledger

    def inspect_scope(self, asset_id):
        return MediaDeletionExecutor(self.session_factory, self.runtime).inspect_scope(asset_id)

    def authorized_runtime(self):
        return replace(self.runtime, deletion_authority=DatabaseMediaDeletionAuthority(
            self.session_factory, self.runtime.config.retirement_policy_hashes, self.ledger))

    def _command(self, command, *, read_only=False):
        from ..privacy.media_port import PrivacyMediaDeletionCommand as WorkflowCommand
        if (type(command) is not WorkflowCommand
                or any(type(getattr(command, name)) is not UUID or not getattr(command, name).int
                       for name in ('operation_id', 'authority_id', 'asset_id'))
                or any(type(getattr(command, name)) is not str or re.fullmatch('[0-9a-f]{64}', getattr(command, name)) is None
                       for name in ('plan_hash', 'policy_hash'))):
            raise ValueError('Invalid privacy media command')
        if not self.runtime.config.fenced_retirement_enabled:
            return None
        with self.session_factory() as db, db.begin():
            found = _approved_plan(db, command, self.runtime.config.retirement_policy_hashes, self.ledger)
            if found is None:
                return None
            plan, execution = found
            if execution.id != command.operation_id or execution.state not in (
                    {'executing', 'outcome_unknown', 'completed'} if read_only else {'executing'}):
                return None
            approved_scope = next(item['scope_hash'] for item in plan.scope['media_assets'] if item['id'] == str(command.asset_id))
            return PrivacyMediaDeletionCommand(operation_id=uuid5(command.operation_id, str(command.asset_id)),
                authority_id=command.authority_id, receipt_id=plan.receipt_id, asset_id=command.asset_id,
                plan_hash=command.plan_hash, policy_hash=command.policy_hash, expected_scope_hash=approved_scope)

    @staticmethod
    def _result(command, state):
        from ..privacy.media_port import PrivacyMediaDeletionResult
        return PrivacyMediaDeletionResult(operation_id=command.operation_id, asset_id=command.asset_id,
            state=state, verified_deleted=state == 'verified_deleted')

    def execute(self, command):
        internal = self._command(command)
        if internal is None:
            return self._result(command, 'blocked')
        result = MediaDeletionExecutor(self.session_factory, self.authorized_runtime()).execute_privacy_deletion(internal)
        state = 'verified_deleted' if result.verified_deleted is True else 'outcome_unknown' if result.state == 'uncertain' else 'blocked'
        return self._result(command, state)

    def reconcile(self, command):
        internal = self._command(command, read_only=True)
        if internal is None:
            return self._result(command, 'blocked')
        with self.session_factory() as db, db.begin():
            job = db.get(SocialMediaDeletion, internal.operation_id)
            if completed_deletion_matches(job, internal):
                return self._result(command, 'verified_deleted')
        return self._result(command, 'outcome_unknown')
