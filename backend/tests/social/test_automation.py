"""Dormant policy authority is distinct from advisory rules and human approval."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func
from social.models import SocialControls, SocialPublication, SocialPostTarget
from social.service import SocialError, SocialService
from test_domain_support import db, account, call
from test_generation import configure, consume, observation, rule, evaluate


def test_policy_entry_exists_and_defaults_closed(db):
    from social.automation.contracts import AuthorizePolicyCommand
    from social.automation.service import AutomationService
    a = account(db)
    configure(db, [a])
    created = consume(db, observation(), backfill=True)
    post = call(db, observation(), lambda s: s.detail(UUID(created['post_id'])))[1]
    candidate = rule(db, [a])
    evaluate(db, post, candidate)
    body = AuthorizePolicyCommand(expected_version=post['version'], revision_id=post['revision_id'], content_hash='a'*64, snapshot_id=uuid4())
    with pytest.raises(SocialError, match='POLICY_AUTOMATION_DISABLED'):
        call(db, body, lambda s: AutomationService(s).authorize(UUID(post['id']), body))
    assert db.scalar(select(func.count()).select_from(SocialPublication)) == 0
    assert db.scalar(select(func.count()).select_from(SocialPostTarget)) == 0


def accepted_snapshot(db, a, monkeypatch, *, enable=True):
    """Synthetic operating outcomes ONLY; never a production acceptance receipt."""
    from unit_source_authority_fixture import install_unit_source_authority
    if db.get_bind().dialect.name == 'sqlite':
        install_unit_source_authority(monkeypatch, db)
    from social.automation.contracts import OperatingEvidenceCommand, SnapshotCommand, PolicyControlsCommand
    from social.automation.service import AutomationService
    from social.contracts import ApproveCommand
    a.capabilities_checked_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    db.commit()
    configure(db, [a])
    created = consume(db, observation(), backfill=True)
    sample = call(db, observation(), lambda s: s.detail(UUID(created['post_id'])))[1]
    policy = rule(db, [a])
    decision = evaluate(db, sample, policy)
    approval = ApproveCommand(expected_version=sample['version'], revision_id=sample['revision_id'], review_attestation={'facts_checked': True, 'sources_checked': True})
    call(db, approval, lambda s: s.approve(UUID(sample['id']), approval))
    target = db.scalar(select(SocialPostTarget))
    target.state, target.published_at, target.primary_remote_id, target.visibility_state, target.confirmation_kind = 'published', datetime.now(timezone.utc), 'inert-fixture-outcome', 'public', 'fixture-only'
    db.commit()
    body = OperatingEvidenceCommand(rule_id=policy['id'], rule_version=1, rule_hash=policy['definition_hash'], shadow_decision_ids=[decision['id']], evidence_url='https://example.test/owned-operating-fixture', evidence_sha256='e'*64, accuracy_accepted=True, reliability_accepted=True, corrections_reviewed=True, reason='Synthetic local contract fixture, no live acceptance')
    evidence = call(db, body, lambda s: AutomationService(s).accept_operating_evidence(body))[1]
    body = SnapshotCommand(operating_evidence_id=evidence['id'], rule_id=policy['id'], rule_version=1, rule_hash=policy['definition_hash'], valid_until=datetime.now(timezone.utc)+timedelta(days=1), reason='Synthetic local policy fixture')
    snapshot = call(db, body, lambda s: AutomationService(s).authorize_snapshot(body))[1]
    if enable:
        monkeypatch.setenv('SOCIAL_POLICY_AUTOMATION_ENABLED', 'true')
        cfg = db.get(SocialControls, 1)
        cfg.publishing_enabled = True
        db.commit()
        body = PolicyControlsCommand(expected_version=cfg.version, snapshot_id=snapshot['id'], auto_approve_enabled=True, auto_schedule_enabled=True, auto_publish_enabled=True, reason='Inert isolated fixture only')
        call(db, body, lambda s: AutomationService(s).set_controls(body))
    return snapshot, policy, evidence


def candidate(db, value='200', version=2):
    from unittest.mock import patch
    with patch.dict('os.environ', {'SOCIAL_POLICY_AUTOMATION_ENABLED': 'false'}):
        created = consume(db, observation(version, value))
    return call(db, observation(), lambda s: s.detail(UUID(created['post_id'])))[1]


def authorize(db, post, snapshot):
    from social.automation.contracts import AuthorizePolicyCommand
    from social.automation.service import AutomationService
    revision = db.get(__import__('social.models', fromlist=['SocialPostRevision']).SocialPostRevision, UUID(post['revision_id']))
    body = AuthorizePolicyCommand(expected_version=post['version'], revision_id=post['revision_id'], content_hash=revision.content_hash, snapshot_id=snapshot['id'])
    return call(db, body, lambda s: AutomationService(s).authorize(UUID(post['id']), body))[1]


def schedule(db, post):
    from social.automation.contracts import SchedulePolicyCommand
    from social.automation.service import AutomationService
    pub = db.get(SocialPublication, UUID(post['publication']['id']))
    body = SchedulePolicyCommand(expected_version=post['version'], revision_id=post['revision_id'], content_hash=pub.approved_hash, snapshot_id=pub.policy_id, publication_id=pub.id, expected_publication_version=pub.version)
    return call(db, body, lambda s: AutomationService(s).schedule(UUID(post['id']), body))[1]


def test_exact_policy_authority_queues_through_shared_engine(db, monkeypatch):
    from social.automation.models import PolicyDecision, AuthorizedPolicySnapshot, OperatingEvidence
    from social.automation.service import verify_authority
    a = account(db)
    snapshot, _, _ = accepted_snapshot(db, a, monkeypatch)
    post = candidate(db)
    authorized = authorize(db, post, snapshot)
    pub = db.get(SocialPublication, UUID(authorized['publication']['id']))
    assert pub.authorization_kind == 'policy' and pub.approved_by is None
    assert pub.policy_id == UUID(snapshot['id']) and pub.policy_decision_id is not None
    decision = db.get(PolicyDecision, pub.policy_decision_id)
    assert decision.revision_id == pub.revision_id and decision.content_hash == pub.approved_hash
    assert db.scalar(select(SocialPostTarget).where(SocialPostTarget.publication_id == pub.id)).state == 'ready'
    assert authorized['publication']['approved_by'] is None
    db.rollback()
    result = schedule(db, authorized)
    assert result['status'] == 'queued'
    target = db.scalar(select(SocialPostTarget).where(SocialPostTarget.publication_id == pub.id))
    assert target.state == 'queued' and target.next_action == 'publish'
    verify_authority(SocialService(db, available_adapters={'facebook'}), pub, SocialService(db).now(), scheduling=True, dispatch=True)
    for model in (PolicyDecision, AuthorizedPolicySnapshot, OperatingEvidence):
        row = db.scalar(select(model))
        if model is PolicyDecision:
            row.decision_hash = '0'*64
        elif model is OperatingEvidence:
            row.evidence_hash = '0'*64
        else:
            row.snapshot_hash = '0'*64
        with pytest.raises(ValueError, match='immutable'):
            db.flush()
        db.rollback()


def test_arbitrary_rule_and_shadow_are_not_sufficient_authority(db, monkeypatch):
    from social.automation.contracts import SnapshotCommand
    from social.automation.service import AutomationService
    a = account(db)
    configure(db, [a])
    policy = rule(db, [a])
    monkeypatch.setenv('SOCIAL_POLICY_AUTOMATION_ENABLED', 'true')
    body = SnapshotCommand(operating_evidence_id=uuid4(), rule_id=policy['id'], rule_version=1, rule_hash=policy['definition_hash'], valid_until=datetime.now(timezone.utc)+timedelta(hours=1), reason='Missing operating evidence')
    with pytest.raises(SocialError, match='OPERATING_EVIDENCE_REQUIRED'):
        call(db, body, lambda s: AutomationService(s).authorize_snapshot(body))
    assert db.scalar(select(func.count()).select_from(SocialPublication)) == 0


@pytest.mark.parametrize('change,code', [('global','PUBLISHING_PAUSED'), ('account','TARGET_VALIDATION_FAILED'), ('capability','CAPABILITY_STALE'), ('ceiling','POLICY_AUTOMATION_DISABLED'), ('approval','POLICY_APPROVAL_DISABLED'), ('schedule','POLICY_SCHEDULING_DISABLED'), ('selection','POLICY_SELECTION_CHANGED')])
def test_schedule_rechecks_current_controls_and_account(db, monkeypatch, change, code):
    from social.automation.models import PolicySelection
    a = account(db)
    snapshot, _, _ = accepted_snapshot(db, a, monkeypatch)
    approved = authorize(db, candidate(db), snapshot)
    cfg = db.get(SocialControls, 1)
    if change == 'global': cfg.publishing_enabled = False
    if change == 'account': a.publishing_enabled = False
    if change == 'capability': a.capabilities_checked_at = None
    if change == 'ceiling': monkeypatch.delenv('SOCIAL_POLICY_AUTOMATION_ENABLED')
    if change == 'approval': cfg.auto_publish_enabled = cfg.auto_schedule_enabled = cfg.auto_approve_enabled = False
    if change == 'schedule': cfg.auto_publish_enabled = cfg.auto_schedule_enabled = False
    if change == 'selection': db.get(PolicySelection, 1).snapshot_id = None
    db.commit()
    with pytest.raises(SocialError, match=code): schedule(db, approved)
    pub = db.get(SocialPublication, UUID(approved['publication']['id']))
    assert pub.dispatch_requested_at is None
    assert db.scalar(select(SocialPostTarget).where(SocialPostTarget.publication_id == pub.id)).state == 'ready'


def test_changed_copy_category_and_evidence_require_human(db, monkeypatch):
    from social.contracts import PatchPost
    a = account(db)
    snapshot, _, _ = accepted_snapshot(db, a, monkeypatch)
    post = candidate(db)
    body = PatchPost(expected_version=post['version'], content_type='allegation')
    changed = call(db, body, lambda s: s.patch(UUID(post['id']), body))[1]
    with pytest.raises(SocialError, match='HUMAN_REVIEW_REQUIRED'): authorize(db, changed, snapshot)
    assert db.scalar(select(func.count()).select_from(SocialPublication).where(SocialPublication.authorization_kind=='policy')) == 0


def test_no_human_queue_command_can_reuse_policy_approval(db, monkeypatch):
    from social.contracts import PublishCommand, ApproveCommand, RescheduleCommand
    a = account(db)
    snapshot, _, _ = accepted_snapshot(db, a, monkeypatch)
    post = authorize(db, candidate(db), snapshot)
    body = PublishCommand(expected_version=post['version'], revision_id=post['revision_id'], review_attestation={'facts_checked': True, 'sources_checked': True})
    with pytest.raises(SocialError, match='POLICY_COMMAND_REQUIRED'):
        call(db, body, lambda s: s.publish(UUID(post['id']), body))


def test_cadence_reservation_survives_cancel_and_restarts(db, monkeypatch):
    from social.contracts import VersionCommand
    from social.automation.models import PolicyDecision
    a = account(db)
    snapshot, _, _ = accepted_snapshot(db, a, monkeypatch)
    first = authorize(db, candidate(db), snapshot)
    first_pub = db.get(SocialPublication, UUID(first['publication']['id']))
    first_at = db.get(PolicyDecision, first_pub.policy_decision_id).inputs['scheduled_for']
    body = VersionCommand(expected_version=first['version'])
    call(db, body, lambda s: s.cancel(UUID(first['id']), body))
    second = authorize(db, candidate(db, value='300', version=3), snapshot)
    second_pub = db.get(SocialPublication, UUID(second['publication']['id']))
    second_at = db.get(PolicyDecision, second_pub.policy_decision_id).inputs['scheduled_for']
    assert datetime.fromisoformat(second_at) - datetime.fromisoformat(first_at) >= timedelta(hours=1)


def test_http_policy_routes_auth_defaults_and_idempotency(db):
    from test_api_admin import make_client, key
    client = make_client(db.bind)
    path = '/api/v1/admin/social/automation/policy-controls'
    result = client.get(path)
    assert result.status_code == 200 and result.json()['environment_enabled'] is False
    assert not result.json()['auto_approve_enabled'] and result.headers['cache-control'] == 'private, no-store'
    body = dict(expected_version=1, snapshot_id=None, auto_approve_enabled=False, auto_schedule_enabled=False, auto_publish_enabled=False, reason='Keep dormant')
    headers = key()
    first = client.patch(path, json=body, headers=headers)
    assert first.status_code == 200
    assert client.patch(path, json=body, headers=headers).json() == first.json()
    assert make_client(db.bind, authenticated=False).patch(path, json=body, headers=key()).status_code in {401,403}
    body['auto_approve_enabled'] = True
    body['snapshot_id'] = str(uuid4())
    body['expected_version'] = 2
    refused = client.patch(path, json=body, headers=key())
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'POLICY_AUTOMATION_DISABLED'


@pytest.mark.parametrize('value', [True, 0, -1, 1.5, float('nan'), float('inf'), '1', None])
def test_policy_direct_boundary_rejects_hostile_versions(value):
    from social.automation.contracts import AuthorizePolicyCommand
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        AuthorizePolicyCommand(expected_version=value, revision_id=uuid4(), content_hash='a'*64, snapshot_id=uuid4())


def test_existing_source_pipeline_invokes_dormant_policy_and_shared_schedule(db, monkeypatch):
    a = account(db)
    snapshot, _, _ = accepted_snapshot(db, a, monkeypatch)
    created = consume(db, observation(2, '250'))
    pub = db.scalar(select(SocialPublication).where(SocialPublication.post_id == UUID(created['post_id'])))
    assert pub is not None and pub.authorization_kind == 'policy'
    assert pub.dispatch_requested_at is not None and pub.scheduled_for is not None
    assert db.scalar(select(SocialPostTarget).where(SocialPostTarget.publication_id == pub.id)).state == 'queued'


def test_pipeline_policy_refusal_retains_pending_draft_and_durable_reason(db, monkeypatch):
    from social.models import SocialPost, SocialAuditEvent
    a = account(db)
    snapshot, _, _ = accepted_snapshot(db, a, monkeypatch)
    a.capabilities_checked_at = None
    db.commit()
    created = consume(db, observation(2, '250'))
    assert db.get(SocialPost, UUID(created['post_id'])).editorial_state == 'pending_review'
    assert db.scalar(select(SocialPublication).where(SocialPublication.post_id == UUID(created['post_id']))) is None
    audit = db.scalar(select(SocialAuditEvent).where(SocialAuditEvent.action == 'automation.human_review_required'))
    assert audit.details['code'] == 'CAPABILITY_STALE'


def test_later_cadence_reservation_does_not_displace_valid_earlier_slot():
    from types import SimpleNamespace
    from social.automation.service import cadence_due
    now = datetime.now(timezone.utc)
    later = SimpleNamespace(id=uuid4(), inputs={'account_ids':['owned'], 'scheduled_for':(now+timedelta(hours=3)).isoformat()})
    class DB:
        def scalars(self, query): return [later]
    definition = SimpleNamespace(min_interval_minutes=60, max_per_day=3)
    assert cadence_due(DB(), ['owned'], definition, now, now+timedelta(days=1)) == now


def test_storage_refuses_null_policy_version_and_missing_authority(db):
    from sqlalchemy.exc import IntegrityError
    from test_domain_support import draft_body
    body = draft_body()
    post = call(db, body, lambda s: s.create(body))[1]
    row = SocialPublication(post_id=UUID(post['id']), revision_id=UUID(post['revision_id']), authorization_kind='policy', approved_by=None, approved_at=datetime.now(timezone.utc), approved_hash='a'*64, policy_id=uuid4(), policy_decision_id=uuid4(), policy_version=None)
    db.add(row)
    with pytest.raises(IntegrityError): db.commit()
    db.rollback()


def test_policy_materiality_refuses_tiny_or_document_only_changes(db, monkeypatch):
    a = account(db)
    snapshot, _, _ = accepted_snapshot(db, a, monkeypatch)
    post = candidate(db, value='123.46')
    with pytest.raises(SocialError, match='BELOW_MATERIALITY'):
        authorize(db, post, snapshot)
    assert db.scalar(select(func.count()).select_from(__import__('social.automation.models', fromlist=['PolicyDecision']).PolicyDecision)) == 0


def test_snapshot_materiality_rejects_zero_and_lossy_shapes():
    from social.automation.contracts import SnapshotCommand
    from pydantic import ValidationError
    base = dict(operating_evidence_id=uuid4(), rule_id=uuid4(), rule_version=1, rule_hash='a'*64, valid_until=datetime.now(timezone.utc)+timedelta(days=1), reason='Owned shape matrix')
    for value in ('0', '-1', 'NaN', 'Infinity', True, 1, 1.5, None):
        with pytest.raises(ValidationError):
            SnapshotCommand(**base, minimum_absolute_change=value)


def test_shared_queue_preserves_manual_publish_now_audit_action(db):
    from test_domain_support import draft_body
    from social.contracts import PublishCommand
    from social.models import SocialAuditEvent
    a = account(db)
    db.add(SocialControls(id=1, publishing_enabled=True))
    db.commit()
    body = draft_body([a])
    post = call(db, body, lambda s: s.create(body))[1]
    body = PublishCommand(expected_version=post['version'], revision_id=post['revision_id'])
    call(db, body, lambda s: s.publish(UUID(post['id']), body))
    assert db.scalar(select(func.count()).select_from(SocialAuditEvent).where(SocialAuditEvent.action=='post.publish_requested')) == 1
