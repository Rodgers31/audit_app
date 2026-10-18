"""Selective policy authority; no provider I/O, scheduler, or independent queue.

All writers take SocialControls first. That existing dispatch ordering lock also
serializes source supersession, policy selection and account cadence reservations.
Callers own the transaction and command receipt.
"""
import os
from decimal import Decimal
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from pydantic import ValidationError
from sqlalchemy import select, func
from ..contracts import PostDocument, canonical_hash
from ..models import SocialControls, SocialAccount, SocialPost, SocialPostRevision, SocialPublication, SocialPostTarget
from ..service import SocialError, utc, iso
from ..validation import validate_document, capability_for
from ..generation.models import AutomationRuleVersion, ShadowDecision, SourceEvent, SourceCursor
from ..generation.contracts import RuleCommand, SourceObservation
from ..generation.service import _insert, render, semantic_fingerprint, verify_generated_revision, TEMPLATE_VERSION, DETECTOR_VERSION
from .contracts import OperatingEvidenceCommand, SnapshotCommand, PolicyControlsCommand, AuthorizePolicyCommand, SchedulePolicyCommand
from .models import OperatingEvidence, AuthorizedPolicySnapshot, PolicyDecision, PolicySelection


def ceiling():
    return os.environ.get('SOCIAL_POLICY_AUTOMATION_ENABLED') == 'true'


def global_controls(db):
    _insert(db, SocialControls, dict(id=1, version=1, publishing_enabled=False, generation_enabled=False, auto_approve_enabled=False, auto_schedule_enabled=False, auto_publish_enabled=False, platform_controls={}, budget_controls={}), ['id'])
    return db.scalar(select(SocialControls).where(SocialControls.id == 1).with_for_update().execution_options(populate_existing=True))


def fresh(db, model, identity):
    return db.get(model, identity, populate_existing=True)


def require(condition, code='POLICY_AUTHORITY_INVALID'):
    if not condition:
        raise SocialError(code, 'Policy authority is unavailable; retain human review.', 409)


def source_scope(observation):
    # Initial rollout is one deterministic, actual dataset announcement. Approved
    # source/entity/metric/period/comparison semantics cannot drift with new values.
    require(observation.category == 'dataset_availability' and len(observation.facts) == 1, 'HUMAN_REVIEW_REQUIRED')
    fact = observation.facts[0]
    require(fact.classification == 'actual', 'HUMAN_REVIEW_REQUIRED')
    values = fact.model_dump(mode='json', exclude={'value', 'published_on', 'retrieved_at', 'verified_at', 'document_checksum'})
    return canonical_hash({'source_type': observation.source_type, 'source_key': observation.source_key, 'category': observation.category, 'title': observation.title, 'fact': values})


def current_rule(db, rule_id, version, digest):
    row = db.scalar(select(AutomationRuleVersion).where(AutomationRuleVersion.rule_id == rule_id, AutomationRuleVersion.version == version).execution_options(populate_existing=True))
    latest = db.scalar(select(func.max(AutomationRuleVersion.version)).where(AutomationRuleVersion.rule_id == rule_id))
    require(row is not None and latest == version, 'POLICY_RULE_CHANGED')
    require(row.definition_hash == digest == canonical_hash(row.definition))
    definition = RuleCommand.model_validate({'expected_version': version - 1, **row.definition})
    require(definition.mode == 'shadow', 'POLICY_RULE_DISABLED')
    require(definition.freshness_hours <= 24, 'POLICY_FRESHNESS_TOO_BROAD')
    return row, definition


def snapshot_value(db, identity, now):
    row = fresh(db, AuthorizedPolicySnapshot, identity)
    require(row is not None and now < utc(row.valid_until), 'POLICY_SNAPSHOT_EXPIRED')
    require(row.snapshot_hash == canonical_hash(row.snapshot))
    value = row.snapshot
    rule, definition = current_rule(db, UUID(value['rule_id']), row.version, value['rule_hash'])
    evidence = fresh(db, OperatingEvidence, row.operating_evidence_id)
    require(evidence is not None and evidence.evidence_hash == canonical_hash(evidence.evidence) == value['operating_evidence_hash'])
    require(evidence.rule_version_id == row.rule_version_id == rule.id and value['definition'] == rule.definition)
    require(value['valid_until'] == iso(row.valid_until) and value['version'] == row.version and str(row.approved_by) == value['approved_by'])
    return row, definition


def controls_dto(db):
    cfg = fresh(db, SocialControls, 1)
    selection = fresh(db, PolicySelection, 1)
    return dict(version=cfg.version if cfg else 1, snapshot_id=str(selection.snapshot_id) if selection and selection.snapshot_id else None, environment_enabled=ceiling(), auto_approve_enabled=bool(cfg and cfg.auto_approve_enabled), auto_schedule_enabled=bool(cfg and cfg.auto_schedule_enabled), auto_publish_enabled=bool(cfg and cfg.auto_publish_enabled))


def runtime_gates(db, cfg, snapshot, *, scheduling=False, dispatch=False):
    require(ceiling(), 'POLICY_AUTOMATION_DISABLED')
    require(cfg is not None and cfg.auto_approve_enabled is True, 'POLICY_APPROVAL_DISABLED')
    if scheduling:
        require(cfg.auto_schedule_enabled is True, 'POLICY_SCHEDULING_DISABLED')
    if dispatch:
        require(cfg.auto_publish_enabled is True, 'POLICY_PUBLISHING_DISABLED')
    selected = fresh(db, PolicySelection, 1)
    require(selected is not None and selected.snapshot_id == snapshot.id, 'POLICY_SELECTION_CHANGED')


def require_unattended_product(account, cap, evidence):
    require(evidence is not None and evidence.evidence.get('tiktok_unattended_product') == account.api_product
        and cap.feature_states.get('unattended_publication') == 'supported', 'TIKTOK_UNATTENDED_UNACCEPTED')


def candidate_gates(svc, post, revision, snapshot, definition, now, *, selected_account=None):
    db = svc.db
    verify_generated_revision(db, post, revision, lock=False)
    require(post.origin_type == 'generated' and post.content_type == 'dataset_availability' and post.editorial_state in {'pending_review', 'approved'}, 'HUMAN_REVIEW_REQUIRED')
    require(canonical_hash({'document': revision.document, 'evidence_snapshot': revision.evidence_snapshot}) == revision.content_hash, 'REVISION_INTEGRITY_FAILED')
    event = fresh(db, SourceEvent, post.source_event_id)
    require(event is not None)
    observation = SourceObservation.model_validate(event.observation)
    require(observation.committed and observation.publishable and not observation.fixture and not observation.quarantined and not observation.correction_pending, 'SOURCE_NOT_ELIGIBLE')
    require(observation.category in definition.categories and observation.source_type in definition.source_allowlist, 'SOURCE_NOT_ALLOWLISTED')
    require(source_scope(observation) in snapshot.snapshot['source_scopes'], 'SOURCE_SCOPE_CHANGED')
    prior = db.scalar(select(SourceEvent).where(SourceEvent.cursor_id == event.cursor_id, SourceEvent.sequence == event.sequence - 1))
    require(prior is not None, 'MATERIALITY_REVIEW_REQUIRED')
    prior_observation = SourceObservation.model_validate(prior.observation)
    require(source_scope(prior_observation) == source_scope(observation), 'MATERIALITY_REVIEW_REQUIRED')
    threshold = snapshot.snapshot['minimum_absolute_change']
    require(type(threshold) is str and Decimal(threshold).is_finite() and Decimal(threshold) > 0)
    require(abs(Decimal(observation.facts[0].value) - Decimal(prior_observation.facts[0].value)) >= Decimal(threshold), 'BELOW_MATERIALITY')
    require(semantic_fingerprint(observation) == event.fingerprint == revision.evidence_snapshot.get('fingerprint'))
    require(revision.generator_metadata == {'template_version': TEMPLATE_VERSION, 'detector_version': DETECTOR_VERSION, 'fact_ids': [f.fact_id for f in observation.facts]})
    document = PostDocument.model_validate(revision.document)
    require(document.master.text == render(observation) and document.master.link == observation.facts[0].canonical_url and not document.master.media and not document.master.hashtags and all(not t.overrides.model_fields_set for t in document.targets), 'GENERATED_COPY_EDITED')
    expiry = min(utc(f.verified_at) + timedelta(hours=definition.freshness_hours) for f in observation.facts)
    require(now < expiry and all(utc(f.verified_at) <= now and utc(f.retrieved_at) <= now for f in observation.facts), 'EVIDENCE_STALE')
    accounts = sorted(str(t.account_id) for t in document.targets)
    require(accounts and set(accounts) <= {str(a) for a in definition.account_allowlist}, 'ACCOUNT_NOT_ALLOWLISTED')
    cfg = fresh(db, SocialControls, 1)
    require(cfg is not None and cfg.publishing_enabled is True, 'PUBLISHING_PAUSED')
    targets = tuple(t for t in document.targets if selected_account is None or t.account_id == selected_account)
    require(bool(targets), 'ACCOUNT_NOT_ALLOWLISTED')
    result = validate_document(db, document.model_copy(update={'targets': targets}), revision.evidence_snapshot, svc.available_adapters)
    require(result.valid and not result.warnings and all(not t.warnings for t in result.targets), 'TARGET_VALIDATION_FAILED')
    for target in targets:
        account = fresh(db, SocialAccount, target.account_id)
        require(account is not None and account.publishing_enabled is True and account.connection_state == 'connected' and not account.hold_reason, 'ACCOUNT_UNAVAILABLE')
        require(account.capabilities_checked_at is not None and now - timedelta(hours=24) <= utc(account.capabilities_checked_at) <= now, 'CAPABILITY_STALE')
        require(not (cfg.platform_controls.get(account.platform, {}).get('publishing_enabled') is False), 'PLATFORM_PAUSED')
        cap = capability_for(account, svc.available_adapters)
        # No paid budget reservation implementation is invented by this lane.
        require(account.platform != 'x' and cap.price_class == 'free', 'BUDGET_UNAVAILABLE')
        if account.platform == 'tiktok':
            evidence = fresh(db, OperatingEvidence, snapshot.operating_evidence_id)
            require_unattended_product(account, cap, evidence)
    return result, accounts, min(expiry, utc(snapshot.valid_until)), event


def cadence_due(db, accounts, definition, now, valid_until, *, exclude_publication=None):
    # Immutable authorization reservations survive cancellation and restart. They
    # also count unscheduled approvals, so repeated approval cannot hoard slots.
    rows = list(db.scalars(select(PolicyDecision).where(PolicyDecision.created_at >= now - timedelta(days=2)).order_by(PolicyDecision.created_at.desc()).limit(1001)))
    require(len(rows) <= 1000, 'CADENCE_HISTORY_LIMIT')
    excluded = None
    if exclude_publication:
        excluded = exclude_publication.policy_decision_id
    reserved = [r for r in rows if r.id != excluded and set(accounts) & set(r.inputs['account_ids'])]
    due = now
    interval = timedelta(minutes=definition.min_interval_minutes)
    for _ in range(1002):
        next_due = due
        for account_id in accounts:
            times = sorted(utc(datetime.fromisoformat(r.inputs['scheduled_for'])) for r in reserved if account_id in r.inputs['account_ids'])
            # Each account may have future reservations. Preserve spacing on both sides.
            for at in times:
                if abs((due - at).total_seconds()) < interval.total_seconds():
                    next_due = max(next_due, at + interval)
            # Check rolling windows ending both now and at later reservations;
            # inserting an earlier slot must not overfill a future window.
            for end in [due, *(at for at in times if due <= at < due + timedelta(days=1))]:
                window = [at for at in times if end - timedelta(days=1) < at <= end]
                if len(window) >= definition.max_per_day:
                    next_due = max(next_due, window[0] + timedelta(days=1))
        if next_due == due:
            require(due < valid_until, 'CADENCE_OUTSIDE_VALIDITY')
            return due
        due = next_due
    raise SocialError('CADENCE_HISTORY_LIMIT', 'Cadence cannot be resolved within its bounded history.')


class AutomationService:
    def __init__(self, svc):
        self.svc, self.db = svc, svc.db

    def accept_operating_evidence(self, body):
        body = OperatingEvidenceCommand.model_validate(body.model_dump(mode='json'))
        global_controls(self.db)
        require(self.svc.actor_kind == 'admin' and self.svc.actor is not None, 'HUMAN_ACCEPTANCE_REQUIRED')
        rule, definition = current_rule(self.db, body.rule_id, body.rule_version, body.rule_hash)
        scopes, outcomes = set(), []
        for identity in body.shadow_decision_ids:
            decision = fresh(self.db, ShadowDecision, identity)
            require(decision is not None and decision.rule_version_id == rule.id and decision.outcome == 'would_allow', 'OPERATING_EVIDENCE_INVALID')
            publication = self.db.scalar(select(SocialPublication).where(SocialPublication.revision_id == decision.revision_id))
            require(publication is not None and publication.authorization_kind == 'human' and publication.approved_by is not None and publication.approved_hash == decision.content_hash and publication.revoked_at is None and publication.cancel_requested_at is None, 'HUMAN_OUTCOME_REQUIRED')
            targets = self.svc._targets(publication)
            require(targets and sorted(str(t.account_id) for t in targets) == sorted(decision.account_ids) and all(t.state == 'published' and t.published_at is not None and t.primary_remote_id and t.visibility_state == 'public' and t.confirmation_kind for t in targets), 'PUBLISHED_HUMAN_OUTCOME_REQUIRED')
            revision = fresh(self.db, SocialPostRevision, decision.revision_id)
            post = fresh(self.db, SocialPost, decision.post_id)
            verify_generated_revision(self.db, post, revision)
            observation = SourceObservation.model_validate(revision.evidence_snapshot['source'])
            require(not observation.correction_pending and not observation.fixture and observation.publishable and not observation.quarantined, 'OPERATING_EVIDENCE_INVALID')
            require(revision.content_hash == canonical_hash({'document': revision.document, 'evidence_snapshot': revision.evidence_snapshot}) == decision.content_hash)
            scopes.add(source_scope(observation))
            outcomes.append(dict(shadow_decision_id=str(decision.id), publication_id=str(publication.id), content_hash=decision.content_hash, revision_id=str(revision.id)))
        value = {**body.model_dump(mode='json'), 'human_outcomes': outcomes, 'source_scopes': sorted(scopes), 'approved_by': str(self.svc.actor)}
        row = OperatingEvidence(id=uuid4(), rule_version_id=rule.id, evidence=value, evidence_hash=canonical_hash(value), approved_by=self.svc.actor)
        self.db.add(row)
        self.svc.audit('automation.operating_evidence_accepted', reason=body.reason, details={'operating_evidence_id': str(row.id), 'evidence_hash': row.evidence_hash})
        self.db.flush()
        return dict(id=str(row.id), evidence_hash=row.evidence_hash)

    def authorize_snapshot(self, body):
        body = SnapshotCommand.model_validate(body.model_dump(mode='json'))
        global_controls(self.db)
        require(self.svc.actor_kind == 'admin' and self.svc.actor is not None, 'HUMAN_ACCEPTANCE_REQUIRED')
        rule, definition = current_rule(self.db, body.rule_id, body.rule_version, body.rule_hash)
        evidence = fresh(self.db, OperatingEvidence, body.operating_evidence_id)
        require(evidence is not None and evidence.rule_version_id == rule.id and evidence.evidence_hash == canonical_hash(evidence.evidence), 'OPERATING_EVIDENCE_REQUIRED')
        now = self.svc.now()
        require(now < utc(body.valid_until) <= now + timedelta(days=30), 'INVALID_POLICY_VALIDITY')
        value = dict(rule_id=str(rule.rule_id), version=rule.version, rule_hash=rule.definition_hash, definition=rule.definition, operating_evidence_hash=evidence.evidence_hash, source_scopes=evidence.evidence['source_scopes'], minimum_absolute_change=body.minimum_absolute_change, approved_by=str(self.svc.actor), valid_until=iso(body.valid_until))
        row = AuthorizedPolicySnapshot(id=uuid4(), rule_version_id=rule.id, operating_evidence_id=evidence.id, version=rule.version, snapshot=value, snapshot_hash=canonical_hash(value), approved_by=self.svc.actor, valid_until=body.valid_until)
        self.db.add(row)
        self.svc.audit('automation.policy_snapshot_authorized', reason=body.reason, details={'snapshot_id': str(row.id), 'snapshot_hash': row.snapshot_hash})
        self.db.flush()
        return dict(id=str(row.id), snapshot_hash=row.snapshot_hash)

    def set_controls(self, body):
        body = PolicyControlsCommand.model_validate(body.model_dump(mode='json'))
        cfg = global_controls(self.db)
        require(cfg.version == body.expected_version, 'VERSION_CONFLICT')
        if body.auto_approve_enabled:
            require(ceiling(), 'POLICY_AUTOMATION_DISABLED')
            snapshot_value(self.db, body.snapshot_id, self.svc.now())
        _insert(self.db, PolicySelection, dict(id=1, snapshot_id=None), ['id'])
        selection = fresh(self.db, PolicySelection, 1)
        selection.snapshot_id = body.snapshot_id
        for key in ('auto_approve_enabled', 'auto_schedule_enabled', 'auto_publish_enabled'):
            setattr(cfg, key, getattr(body, key))
        cfg.version += 1
        cfg.updated_by, cfg.updated_at = self.svc.actor, self.svc.now()
        self.svc.audit('automation.controls_updated', reason=body.reason, details=body.model_dump(mode='json'))
        self.db.flush()
        return controls_dto(self.db)

    def authorize(self, post_id, body):
        body = AuthorizePolicyCommand.model_validate(body.model_dump(mode='json'))
        require(ceiling(), 'POLICY_AUTOMATION_DISABLED')
        cfg = global_controls(self.db)
        post, revision, publication = self.svc._locked(post_id, body.expected_version)
        require(publication is None, 'AUTHORIZATION_ALREADY_EXISTS')
        require(revision.id == body.revision_id and revision.content_hash == body.content_hash, 'VERSION_CONFLICT')
        now = self.svc.now()
        snapshot, definition = snapshot_value(self.db, body.snapshot_id, now)
        runtime_gates(self.db, cfg, snapshot)
        validation, accounts, valid_until, event = candidate_gates(self.svc, post, revision, snapshot, definition, now)
        due = cadence_due(self.db, accounts, definition, now, valid_until)
        inputs = dict(snapshot_hash=snapshot.snapshot_hash, operating_evidence_id=str(snapshot.operating_evidence_id), controls_version=cfg.version, account_ids=accounts, source_event_id=str(event.id), source_sequence=event.sequence, scheduled_for=iso(due), valid_until=iso(valid_until), payload_hashes={str(t.account_id): t.resolved_preview.content_hash for t in validation.targets}, content_hash=revision.content_hash, revision_id=str(revision.id), post_id=str(post.id), snapshot_id=str(snapshot.id), policy_version=snapshot.version)
        decision = PolicyDecision(id=uuid4(), snapshot_id=snapshot.id, policy_version=snapshot.version, post_id=post.id, revision_id=revision.id, content_hash=revision.content_hash, inputs=inputs, decision_hash=canonical_hash(inputs))
        self.db.add(decision)
        self.db.flush()
        publication = self.svc._store_authorization(post, revision, validation, authorization_kind='policy', policy_id=snapshot.id, policy_version=snapshot.version, policy_decision_id=decision.id)
        publication.content_valid_until = valid_until
        self.svc._touch(post)
        self.svc.audit('automation.revision_authorized', post=post, details={'decision_id': str(decision.id), **inputs})
        self.db.flush()
        return self.svc.detail(post.id)

    def schedule(self, post_id, body):
        body = SchedulePolicyCommand.model_validate(body.model_dump(mode='json'))
        require(ceiling(), 'POLICY_AUTOMATION_DISABLED')
        global_controls(self.db)
        post, revision, publication = self.svc._locked(post_id, body.expected_version)
        require(publication is not None and publication.id == body.publication_id and publication.version == body.expected_publication_version and publication.revision_id == body.revision_id and publication.approved_hash == body.content_hash and publication.policy_id == body.snapshot_id, 'VERSION_CONFLICT')
        require(publication.dispatch_requested_at is None and not publication.cancel_requested_at and not publication.revoked_at, 'POLICY_ALREADY_SCHEDULED')
        validation, decision, snapshot, definition = verify_authority(self.svc, publication, self.svc.now(), scheduling=True)
        due = utc(datetime.fromisoformat(decision.inputs['scheduled_for']))
        require(self.svc.now() <= due + timedelta(minutes=5), 'POLICY_RESERVATION_EXPIRED')
        # Missed reservations are never shifted into another reserved slot.
        due = max(due, self.svc.now())
        require(cadence_due(self.db, decision.inputs['account_ids'], definition, due, utc(publication.content_valid_until), exclude_publication=publication) == due, 'CADENCE_RESERVATION_CONFLICT')
        return self.svc._queue_authorization(post, publication, validation, due, timezone='UTC', local_time=due.replace(tzinfo=None).isoformat())


def verify_authority(svc, publication, now, *, scheduling=False, dispatch=False, selected_account=None):
    db = svc.db
    require(publication.authorization_kind == 'policy' and publication.approved_by is None and publication.approved_at is not None and publication.policy_decision_id is not None)
    require(not publication.cancel_requested_at and not publication.revoked_at, 'CANCELLED')
    decision = fresh(db, PolicyDecision, publication.policy_decision_id)
    require(decision is not None and decision.decision_hash == canonical_hash(decision.inputs))
    require((decision.post_id, decision.revision_id, decision.content_hash, decision.snapshot_id, decision.policy_version) == (publication.post_id, publication.revision_id, publication.approved_hash, publication.policy_id, publication.policy_version))
    require(decision.inputs['post_id'] == str(publication.post_id) and decision.inputs['revision_id'] == str(publication.revision_id) and decision.inputs['content_hash'] == publication.approved_hash and decision.inputs['snapshot_id'] == str(publication.policy_id) and decision.inputs['policy_version'] == publication.policy_version)
    snapshot, definition = snapshot_value(db, publication.policy_id, now)
    require(decision.inputs['snapshot_hash'] == snapshot.snapshot_hash and decision.inputs['operating_evidence_id'] == str(snapshot.operating_evidence_id))
    require(publication.content_valid_until is not None and iso(publication.content_valid_until) == decision.inputs['valid_until'] and now < utc(publication.content_valid_until), 'CONTENT_EXPIRED')
    runtime_gates(db, fresh(db, SocialControls, 1), snapshot, scheduling=scheduling, dispatch=dispatch)
    post, revision = fresh(db, SocialPost, publication.post_id), fresh(db, SocialPostRevision, publication.revision_id)
    require(post is not None and revision is not None and post.current_revision_id == revision.id)
    validation, accounts, valid_until, event = candidate_gates(svc, post, revision, snapshot, definition, now, selected_account=selected_account)
    require(accounts == decision.inputs['account_ids'] and str(event.id) == decision.inputs['source_event_id'] and event.sequence == decision.inputs['source_sequence'] and iso(valid_until) == decision.inputs['valid_until'])
    require(all(decision.inputs['payload_hashes'].get(str(t.account_id)) == t.resolved_preview.content_hash for t in validation.targets), 'POLICY_PAYLOAD_CHANGED')
    return validation, decision, snapshot, definition


def dispatch_cadence(db, publication, account_id, definition, now):
    from ..models import SocialPublishAttempt
    rows = db.execute(select(SocialPostTarget.publication_id,
        func.max(SocialPublishAttempt.dispatch_started_at), func.max(SocialPostTarget.published_at))
        .join(SocialPublishAttempt, SocialPublishAttempt.target_id == SocialPostTarget.id)
        .join(SocialPublication, SocialPublication.id == SocialPostTarget.publication_id)
        .where(SocialPostTarget.account_id == account_id, SocialPublication.authorization_kind == 'policy',
            SocialPostTarget.publication_id != publication.id,
            (SocialPublishAttempt.dispatch_started_at >= now - timedelta(days=1)) | (SocialPostTarget.published_at >= now - timedelta(days=1)))
        .group_by(SocialPostTarget.publication_id).limit(1001)).all()
    require(len(rows) < definition.max_per_day, 'DAILY_CADENCE_LIMIT')
    require(all(max(utc(t) for t in (started, published) if t is not None) <= now - timedelta(minutes=definition.min_interval_minutes) for _, started, published in rows), 'MINIMUM_INTERVAL')


def worker_gate(conn, publication_id, account_id, platform, now, *, public):
    from sqlalchemy.orm import Session
    from ..service import SocialService
    try:
        with Session(bind=conn, join_transaction_mode='rollback_only') as db:
            publication = fresh(db, SocialPublication, publication_id)
            svc = SocialService(db, available_adapters={platform})
            validation, decision, snapshot, definition = verify_authority(svc, publication, now, scheduling=True, dispatch=True, selected_account=account_id)
            require(publication.scheduled_for is not None and utc(publication.scheduled_for) <= now and publication.dispatch_requested_at is not None, 'POLICY_NOT_DUE')
            if public:
                dispatch_cadence(db, publication, account_id, definition, now)
        return None
    except SocialError as error:
        return error.code
    except (ValueError, TypeError, KeyError, AttributeError):
        return 'POLICY_AUTHORITY_INVALID'


def maybe_automate_generated(svc, post):
    """Existing committed-event caller invokes this once; never a scanning service.

    A policy refusal preserves the pending human draft and records the reason.
    Unexpected storage/runtime failures propagate and roll back the entire event.
    """
    if not ceiling():
        return
    cfg = fresh(svc.db, SocialControls, 1)
    if cfg is None or cfg.auto_approve_enabled is not True:
        return
    selected = fresh(svc.db, PolicySelection, 1)
    try:
        with svc.db.begin_nested():
            require(selected is not None and selected.snapshot_id is not None, 'POLICY_SELECTION_CHANGED')
            revision = svc._revision(post)
            body = AuthorizePolicyCommand(expected_version=post.row_version, revision_id=revision.id, content_hash=revision.content_hash, snapshot_id=selected.snapshot_id)
            AutomationService(svc).authorize(post.id, body)
            if cfg.auto_schedule_enabled:
                publication = svc._publication(post)
                body = SchedulePolicyCommand(expected_version=post.row_version, revision_id=revision.id, content_hash=revision.content_hash, snapshot_id=selected.snapshot_id, publication_id=publication.id, expected_publication_version=publication.version)
                AutomationService(svc).schedule(post.id, body)
    except (SocialError, ValidationError) as error:
        # Only an understood policy refusal degrades to review. No false success
        # verdict is returned for a failed DB write or other runtime exception.
        svc.audit('automation.human_review_required', post=post, details={'code': error.code if isinstance(error, SocialError) else 'POLICY_DATA_INVALID'})
        svc.db.flush()
