"""Executable generated-event, immutable-review and advisory-policy contracts."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from social.contracts import PatchPost, ApproveCommand, PublishCommand
from social.models import SocialPost, SocialPostRevision, SocialPublication, SocialPostTarget, SocialControls
from social.generation.contracts import SourceObservation, GenerationControlsCommand, RuleCommand, EvaluateCommand
from social.generation.models import SourceCursor, SourceEvent, AutomationRuleVersion, ShadowDecision
from social.generation.service import GenerationService, consume_observation, semantic_fingerprint
from social.service import SocialError
from test_domain_support import db, account, call, ACTOR


def observation(version=1, value='123.45', **changes):
    now = datetime.now(timezone.utc) - timedelta(minutes=1)
    fact = dict(fact_id='county:1:budget', entity='County fixture', metric='Approved budget', period='FY2025/26', comparison_basis='County total', value=value, unit='KES', scale='millions', classification='actual', source_document_id=1, document_url='https://example.gov/report.pdf', locator='page 12, table 4', document_checksum='a'*64, publisher='Controller of Budget', published_on='2026-01-01', retrieved_at=now.isoformat(), verified_at=now.isoformat(), canonical_url='https://www.auditgava.com/counties/1')
    raw = dict(schema_version=1, source_type='cob', source_key='county:1:budget:2025', evidence_version=version, ingestion_id='job:42', category='dataset_availability', title='County expenditure dataset', committed=True, fixture=False, quarantined=False, publishable=True, facts=[fact])
    raw.update(changes)
    return SourceObservation.model_validate(raw)


def configure(db, accounts=(), *, drafts=True, shadow=True):
    body = GenerationControlsCommand(expected_version=1, drafts_enabled=drafts, shadow_enabled=shadow, source_allowlist=['cob'], targets=[dict(account_id=a.id, format='text') for a in accounts], reason='Owned fixture controls')
    return call(db, body, lambda s: GenerationService(s).set_controls(body))[1]


def consume(db, value, *, backfill=False):
    return call(db, value, lambda svc: consume_observation(svc, value, backfill=backfill))[1]


def rule(db, accounts, **changes):
    raw = dict(expected_version=0, name='Dataset shadow', mode='shadow', categories=['dataset_availability'], source_allowlist=['cob'], account_allowlist=[a.id for a in accounts], reason='Owned shadow fixture')
    raw.update(changes)
    body = RuleCommand.model_validate(raw)
    return call(db, body, lambda s: GenerationService(s).save_rule(uuid4(), body))[1]


def evaluate(db, post, policy):
    body = EvaluateCommand(expected_version=post['version'], revision_id=post['revision_id'], rule_id=policy['id'], rule_version=policy['version'])
    return call(db, body, lambda s: GenerationService(s).evaluate(UUID(post['id']), body))[1]


def test_off_by_default_and_no_baseline_flood(db):
    with pytest.raises(SocialError, match='GENERATION_DISABLED'):
        consume(db, observation())
    configure(db)
    assert consume(db, observation())['status'] == 'baseline'
    assert consume(db, observation())['status'] == 'unchanged'
    assert db.scalar(select(func.count()).select_from(SocialPost)) == 0
    db.rollback()
    created = consume(db, observation(2, '124.00'))
    assert created['sequence'] == 1
    assert consume(db, observation(2, '124.00'))['status'] == 'unchanged'
    assert consume(db, observation(3, '123.45'))['sequence'] == 2
    assert db.scalar(select(func.count()).select_from(SocialPost)) == 2
    assert db.scalar(select(func.count()).select_from(SourceEvent)) == 2
    assert db.scalar(select(func.count()).select_from(SocialPublication)) == 0
    assert db.scalar(select(func.count()).select_from(SocialPostTarget)) == 0


def test_explicit_versions_and_atomic_rollback(db):
    configure(db)
    consume(db, observation())
    with pytest.raises(SocialError, match='EVIDENCE_VERSION_CONFLICT'):
        consume(db, observation(1, '999'))
    with pytest.raises(ValidationError):
        consume(db, observation(0))


def test_failed_render_rolls_back_cursor_event_and_post(db):
    configure(db)
    consume(db, observation())
    with pytest.raises(SocialError, match='UNRESOLVED_TEMPLATE'):
        consume(db, observation(2, title='[TODO value]'))
    assert db.scalar(select(SourceCursor)).sequence == 0
    assert db.scalar(select(func.count()).select_from(SourceEvent)) == 0
    assert db.scalar(select(func.count()).select_from(SocialPost)) == 0
    db.rollback()
    assert consume(db, observation(2))['status'] == 'unchanged'


@pytest.mark.parametrize('field,value', [('committed', False), ('fixture', True), ('quarantined', True), ('publishable', False)])
def test_ineligible_evidence_is_never_consumed(db, field, value):
    configure(db)
    with pytest.raises(SocialError, match='SOURCE_NOT_ELIGIBLE'):
        consume(db, observation(**{field: value}))
    assert db.scalar(select(func.count()).select_from(SourceCursor)) == 0


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity', True, 123.45, '', '1e9', '1,000', '0.123456789'])
def test_decimal_contract_rejects_invented_or_lossy_values(value):
    with pytest.raises(ValidationError):
        observation(value=value)


def test_fingerprint_ignores_observation_timing_but_not_classification():
    first = observation()
    second = observation(2, ingestion_id='job:43')
    assert semantic_fingerprint(first) == semantic_fingerprint(second)
    raw = second.model_dump(mode='json')
    raw['facts'][0]['classification'] = 'projected'
    assert semantic_fingerprint(first) != semantic_fingerprint(SourceObservation.model_validate(raw))


def test_generated_edit_preserves_factual_provenance_and_requires_attestation(db):
    a = account(db)
    configure(db, [a])
    created = consume(db, observation(), backfill=True)
    post = call(db, observation(), lambda s: s.detail(UUID(created['post_id'])))[1]
    assert post['origin_type'] == 'generated' and post['editorial_state'] == 'pending_review'
    before = db.get(SocialPostRevision, UUID(post['revision_id'])).evidence_snapshot
    db.rollback()
    edit = PatchPost(expected_version=post['version'], title='Reviewed dataset title')
    updated = call(db, edit, lambda s: s.patch(UUID(post['id']), edit))[1]
    revision = db.get(SocialPostRevision, UUID(updated['revision_id']))
    assert revision.evidence_snapshot['source'] == before['source']
    assert revision.evidence_snapshot['source_event_id'] == before['source_event_id']
    db.rollback()
    approve = ApproveCommand(expected_version=updated['version'], revision_id=updated['revision_id'])
    with pytest.raises(SocialError, match='REVIEW_ATTESTATION_REQUIRED'):
        call(db, approve, lambda s: s.approve(UUID(post['id']), approve))
    approve = approve.model_copy(update={'review_attestation': __import__('social.contracts', fromlist=['ReviewAttestation']).ReviewAttestation(facts_checked=True, sources_checked=True)})
    accepted = call(db, approve, lambda s: s.approve(UUID(post['id']), approve))[1]
    assert accepted['editorial_state'] == 'approved'
    assert db.scalar(select(SocialPublication)).authorization_kind == 'human'
    assert db.scalar(select(SocialPostTarget)).state == 'ready'
    assert db.get(SocialControls, 1) is None or db.get(SocialControls, 1).auto_publish_enabled is False


def test_shadow_dedup_cadence_and_no_authorization(db):
    a = account(db)
    configure(db, [a])
    created = consume(db, observation(), backfill=True)
    post = call(db, observation(), lambda s: s.detail(UUID(created['post_id'])))[1]
    policy = rule(db, [a])
    decision = evaluate(db, post, policy)
    assert decision['outcome'] == 'would_allow'
    assert evaluate(db, post, policy)['id'] == decision['id']
    assert db.scalar(select(func.count()).select_from(ShadowDecision)) == 1
    assert db.scalar(select(func.count()).select_from(SocialPublication)) == 0
    db.rollback()
    created2 = consume(db, observation(2, '125'))
    post2 = call(db, observation(), lambda s: s.detail(UUID(created2['post_id'])))[1]
    decision2 = evaluate(db, post2, policy)
    assert decision2['outcome'] == 'human_review'
    assert 'MINIMUM_INTERVAL' in decision2['reasons']
    assert db.scalar(select(func.count()).select_from(SocialPostTarget)) == 0


def test_rules_are_versioned_and_constraints_cannot_enable_live(db):
    a = account(db)
    configure(db, [a])
    policy = rule(db, [a], mode='disabled')
    body = RuleCommand.model_validate(dict(expected_version=1, **{**policy['definition'], 'mode': 'shadow'}))
    updated = call(db, body, lambda s: GenerationService(s).save_rule(UUID(policy['id']), body))[1]
    assert updated['version'] == 2
    old = db.scalar(select(AutomationRuleVersion).where(AutomationRuleVersion.version == 1))
    assert old.definition['mode'] == 'disabled'
    old.definition_hash = 'f'*64
    with pytest.raises(ValueError, match='immutable'):
        db.flush()
    db.rollback()
    for change in (dict(mode='live'), dict(max_per_day=True), dict(max_per_day=4), dict(min_interval_minutes=0), dict(categories=['correction'])):
        with pytest.raises(ValidationError):
            RuleCommand.model_validate({**body.model_dump(mode='json'), **change})


def test_patch_cannot_discard_attached_generated_evidence(db):
    """Regression: original manual patch rebuilt references and lost source facts."""
    from social.contracts import canonical_hash
    from test_domain_support import draft_body
    document = draft_body().document.model_dump(mode='json')
    evidence = {'references': [{'url': 'https://example.gov/report.pdf', 'label': 'Page 12'}], 'source': observation().model_dump(mode='json'), 'source_event_id': str(uuid4()), 'evidence_version': 1}
    post = SocialPost(id=uuid4(), origin_type='generated', creation_method='pipeline', title='Generated', content_type='dataset_availability', editorial_state='pending_review')
    db.add(post)
    db.flush()
    rev = SocialPostRevision(id=uuid4(), post_id=post.id, revision_no=1, document=document, evidence_snapshot=evidence, content_hash=canonical_hash({'document': document, 'evidence_snapshot': evidence}), generator_metadata={'template_version': 'factual-v1'})
    db.add(rev)
    db.flush()
    post.current_revision_id = rev.id
    post_id = post.id
    db.commit()
    edit = PatchPost(expected_version=1, title='Human reviewed title')
    edited = call(db, edit, lambda svc: svc.patch(post_id, edit))[1]
    new = db.get(SocialPostRevision, UUID(edited['revision_id']))
    assert new.evidence_snapshot == evidence, 'Editing a generated draft discarded its factual provenance'
    assert new.generator_metadata == {'template_version': 'factual-v1'}


def test_explicit_backfill_after_baseline_creates_once(db):
    configure(db)
    assert consume(db, observation())['status'] == 'baseline'
    assert consume(db, observation(), backfill=True)['status'] == 'draft_created'
    assert consume(db, observation(), backfill=True)['status'] == 'unchanged'


def test_target_placeholder_cannot_be_human_authorized(db):
    a = account(db)
    configure(db, [a])
    created = consume(db, observation(), backfill=True)
    post = call(db, observation(), lambda s: s.detail(UUID(created['post_id'])))[1]
    document = deepcopy(post['document'])
    document['targets'][0]['overrides'] = {'text': {'mode': 'replace', 'value': '{{MISSING_FIGURE}}'}}
    edit = PatchPost(expected_version=post['version'], document=document)
    changed = call(db, edit, lambda s: s.patch(UUID(post['id']), edit))[1]
    approval = ApproveCommand(expected_version=changed['version'], revision_id=changed['revision_id'], review_attestation={'facts_checked': True, 'sources_checked': True})
    with pytest.raises(SocialError, match='UNRESOLVED_TEMPLATE'):
        call(db, approval, lambda s: s.approve(UUID(post['id']), approval))


def test_shadow_rechecks_expiry_supersession_and_preserves_decisions(db, monkeypatch):
    from social.service import SocialService
    a = account(db)
    configure(db, [a])
    created = consume(db, observation(), backfill=True)
    post = call(db, observation(), lambda s: s.detail(UUID(created['post_id'])))[1]
    policy = rule(db, [a])
    original = evaluate(db, post, policy)
    assert original['outcome'] == 'would_allow'
    clock = SocialService.now
    monkeypatch.setattr(SocialService, 'now', lambda self: datetime.now(timezone.utc) + timedelta(days=2))
    stale = evaluate(db, post, policy)
    assert stale['outcome'] == 'human_review' and 'EVIDENCE_STALE' in stale['reasons']
    monkeypatch.setattr(SocialService, 'now', clock)
    consume(db, observation(2, '456'))
    superseded = evaluate(db, post, policy)
    assert superseded['outcome'] == 'human_review' and 'SOURCE_SUPERSEDED' in superseded['reasons']
    old = db.get(ShadowDecision, UUID(original['id']))
    assert old.outcome == 'would_allow'


def test_boolean_schema_version_is_not_a_version():
    raw = observation().model_dump(mode='json')
    with pytest.raises(ValidationError):
        SourceObservation.model_validate({**raw, 'schema_version': True})
