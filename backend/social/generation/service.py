"""Transactional deterministic draft creation and advisory-only policy evaluation.

Callers own the transaction. PostgreSQL source-row locks serialize semantics;
unique event/post constraints remain the final duplicate boundary.
"""
from datetime import date, timedelta
import re
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..contracts import PostDocument, VersionCommand, canonical_hash, canonical_json
from ..models import SocialAccount, SocialControls, SocialPost, SocialPostRevision
from ..service import SocialError, SocialService, utc, iso
from ..validation import validate_document
from .contracts import SourceObservation, RuleCommand, GenerationControlsCommand, EvaluateCommand, CataloguedNativeReportEvidence
from .models import GenerationControls, SourceCursor, SourceEvent, AutomationRuleVersion, ShadowDecision

DETECTOR_VERSION = 1
TEMPLATE_VERSION = 'factual-v1'


def _insert(db, model, values, keys):
    dialect = db.bind.dialect.name
    if dialect not in {'postgresql', 'sqlite'}:
        raise SocialError('GENERATION_STORAGE_UNSUPPORTED', 'Generation requires a supported transactional database.', 503)
    stmt = (pg_insert if dialect == 'postgresql' else sqlite_insert)(model).values(**values).on_conflict_do_nothing(index_elements=keys)
    db.execute(stmt)


def controls(db, *, lock=False):
    _insert(db, GenerationControls, dict(id=1, version=1, drafts_enabled=False, shadow_enabled=False, source_allowlist=[], targets=[]), ['id'])
    stmt = select(GenerationControls).where(GenerationControls.id == 1)
    return db.scalar(stmt.with_for_update().execution_options(populate_existing=True) if lock else stmt)


def controls_dto(row):
    return {k: getattr(row, k) for k in ('version', 'drafts_enabled', 'shadow_enabled', 'source_allowlist', 'targets')}


def legacy_fingerprint(observation):
    value = observation.model_dump(mode='json')
    value.pop('financial', None)
    # Retrieval/verification/ingestion are observations, not a semantic change.
    for key in ('evidence_version', 'ingestion_id', 'committed', 'fixture', 'quarantined', 'publishable'):
        value.pop(key)
    for fact in value['facts']:
        fact.pop('retrieved_at')
        fact.pop('verified_at')
    if observation.report is None:
        value.pop('report', None)  # Preserve the fingerprint of delivered fact events.
    else:
        for key in ('retrieved_at', 'verified_at', 'publication_extraction_id', 'qualification_extraction_id', 'source_record_id', 'authority_fingerprint'):
            value['report'].pop(key)
    value['facts'].sort(key=lambda f: f['fact_id'])
    return canonical_hash({'detector': DETECTOR_VERSION, 'source': value})


def semantic_fingerprint(observation):
    if observation.report is not None:
        return legacy_fingerprint(observation)
    # A changed artifact is evidence to recheck, not a changed business fact.
    # Keep the immutable full observation on the event; compare only its scope
    # and exact business values here. Canonical decimal spelling avoids 1/1.00.
    from decimal import Decimal
    facts = []
    for fact in observation.facts:
        value = fact.model_dump(mode='json', include={
            'fact_id', 'entity', 'metric', 'period', 'comparison_basis', 'value',
            'unit', 'scale', 'classification'})
        number = Decimal(value['value'])
        value['value'] = '0' if number == 0 else format(number.normalize(), 'f')
        facts.append(value)
    return canonical_hash(dict(detector=DETECTOR_VERSION, financial_semantics=2,
        source_type=observation.source_type, source_key=observation.source_key,
        category=observation.category, correction_pending=observation.correction_pending,
        facts=sorted(facts, key=lambda f: f['fact_id'])))


def prior_financial_fingerprint(observation, cursor, old):
    """Upgrade known legacy evidence without replacing a silent baseline.

    An old baseline stores only a hash. If neither its original observation nor
    an exact legacy match is available, no algorithm can recover its values.
    Refuse instead of silently resetting it or manufacturing a change.
    """
    if observation.report is not None:
        return cursor.fingerprint
    state = cursor.report_state
    if valid_financial_state(state):
        if observation.financial is not None:
            current = financial_state(observation)
            if set(current) != set(state) or any(current[key] < state[key] for key in ('period_start','period_end','published_on')):
                raise SocialError('REPORT_RELEASE_REGRESSION', 'Financial reporting scope and publisher timing cannot regress.', 422)
        return cursor.fingerprint
    if state is not None:
        raise SocialError('EVIDENCE_INTEGRITY_FAILED', 'Financial cursor state is malformed.', 503)
    if old is not None:
        previous = SourceObservation.model_validate(old.observation)
        if old.fingerprint not in (legacy_fingerprint(previous), semantic_fingerprint(previous)):
            raise SocialError('EVIDENCE_INTEGRITY_FAILED', 'Legacy financial evidence differs.', 503)
        return semantic_fingerprint(previous)
    if legacy_fingerprint(observation) == cursor.fingerprint:
        return semantic_fingerprint(observation)
    raise SocialError('EVIDENCE_INTEGRITY_FAILED', 'Retain and reconcile the original financial baseline before migration.', 503)


def financial_state(observation):
    state = {'financial_semantics': 2}
    if observation.financial is not None:
        state.update({key:getattr(observation.financial,key).isoformat() for key in ('period_start','period_end','published_on')})
    return state


def valid_financial_state(state):
    if type(state) is not dict or type(state.get('financial_semantics')) is not int or state['financial_semantics'] != 2:
        return False
    if set(state) == {'financial_semantics'}:
        return True
    if set(state) != {'financial_semantics','period_start','period_end','published_on'}:
        return False
    try:
        dates = {k:date.fromisoformat(state[k]) for k in ('period_start','period_end','published_on')
                 if type(state[k]) is str and len(state[k])==10}
        return len(dates)==3 and all(dates[k].isoformat()==state[k] for k in dates) and dates['period_start']<=dates['period_end']<=dates['published_on']
    except (TypeError,ValueError):
        return False


def established_financial_source(db, observation, *, initialize=False):
    if observation.financial is None:
        return False
    identity = dict(source_type=observation.source_type,
        source_key=f'{observation.source_type}:financial:{observation.financial.native_domain}:baseline',
        detector_version=DETECTOR_VERSION)
    current={key:getattr(observation.financial,key).isoformat() for key in ('period_start','period_end','published_on')}
    if initialize:
        _insert(db, SourceCursor, dict(id=uuid4(), **identity, evidence_version=observation.evidence_version,
            sequence=0, fingerprint=canonical_hash(identity), report_state={'financial_baseline':1,**current}), list(identity))
    root = db.scalar(select(SourceCursor).filter_by(**identity))
    if root is None:
        return False
    if (root.sequence != 0 or type(root.report_state) is not dict or set(root.report_state) != {'financial_baseline',*current}
            or type(root.report_state['financial_baseline']) is not int or root.report_state['financial_baseline'] != 1
            or not valid_financial_state({'financial_semantics':2,**{k:root.report_state[k] for k in current}})
            or root.fingerprint != canonical_hash(identity)):
        raise SocialError('EVIDENCE_INTEGRITY_FAILED', 'Financial source baseline differs.', 503)
    if any(current[k]<root.report_state[k] for k in current):
        raise SocialError('REPORT_RELEASE_REGRESSION','Financial source reporting scope cannot regress.',422)
    if initialize:
        root.report_state={'financial_baseline':1,**current}
    return root.evidence_version < observation.evidence_version


def evidence_items(observation):
    return (observation.report,) if observation.report else observation.facts


def valid_report_release_state(value):
    if (type(value) is not dict or set(value) not in (
            {'release_hash', 'published_on', 'period_start', 'period_end'},
            {'release_hash', 'evidence_kind', 'catalogued_on', 'period_start', 'period_end'})
            or type(value['release_hash']) is not str or re.fullmatch('[a-f0-9]{64}', value['release_hash']) is None):
        return False
    if 'catalogued_on' in value and value['evidence_kind'] != 'publisher_catalogue':
        return False
    try:
        dates = {key: date.fromisoformat(value[key]) for key in value if key not in ('release_hash','evidence_kind')
            if type(value[key]) is str and len(value[key]) == 10}
        return (len(dates) == 3 and all(dates[key].isoformat() == value[key] for key in dates)
            and dates['period_start'] <= dates['period_end']
            and ('catalogued_on' not in dates or dates['period_end'] <= dates['catalogued_on']))
    except (ValueError, TypeError):
        return False


def report_release_regresses(current, previous):
    if not valid_report_release_state(current) or not valid_report_release_state(previous):
        return True
    # Existing publication states keep their exact historical bytes. Their
    # strict published_on schema unambiguously identifies publication evidence;
    # catalogue states carry an explicit discriminator and a distinct day.
    current_kind = current.get('evidence_kind','publisher_publication')
    previous_kind = previous.get('evidence_kind','publisher_publication')
    if current_kind != previous_kind:
        # A kind change is not another release of the same annual report, even
        # during explicit backfill. Never replace known publication timing with
        # unknown timing. A genuinely later *published* annual release has its
        # own path, with both period boundaries and the day strictly later.
        return not (current_kind == 'publisher_publication'
            and current['period_start'] > previous['period_start']
            and current['period_end'] > previous['period_end']
            and current['period_end'] <= current['published_on']
            and current['published_on'] > previous['catalogued_on'])
    day = 'catalogued_on' if current_kind == 'publisher_catalogue' else 'published_on'
    return any(current[key] < previous[key] for key in ('period_start','period_end',day))


def report_release_state(observation):
    if observation.report is None:
        return None
    report = observation.report
    identity = {key: getattr(report, key) for key in ('entity_id', 'entity', 'publisher', 'period')}
    key = 'catalogued_on' if isinstance(report,CataloguedNativeReportEvidence) else 'published_on'
    identity.update(period_start=report.period_start.isoformat(), period_end=report.period_end.isoformat())
    identity[key] = getattr(report,key).isoformat()
    state = {'release_hash': canonical_hash(identity), **{k: identity[k] for k in (key, 'period_start', 'period_end')}}
    if isinstance(report,CataloguedNativeReportEvidence):
        state['evidence_kind'] = 'publisher_catalogue'
    return state


def generator_metadata(observation):
    value = {'template_version': 'report-availability-v1' if observation.report else TEMPLATE_VERSION, 'detector_version': DETECTOR_VERSION, 'fact_ids': [f.fact_id for f in observation.facts]}
    if observation.report:
        value['report_source_document_id'] = observation.report.source_document_id
        if isinstance(observation.report,CataloguedNativeReportEvidence):
            value['template_version'] = 'catalogue-availability-v1'
    return value


def render(observation):
    """Only supplied verified strings and exact decimals enter factual copy."""
    if observation.report:
        report = observation.report
        copy = f'Report available from {report.publisher}. Verified reporting scope: {report.entity}, {report.period}.'
        if isinstance(report,CataloguedNativeReportEvidence):
            copy += f' Official KRA catalogue entry dated {report.catalogued_on.isoformat()}. Report publication date is not stated. Human review required.'
        else:
            copy += f' Publisher publication date: {report.published_on.isoformat()}.'
    elif observation.category == 'dataset_availability':
        copy = f'{observation.title} is available on AuditGava.'
    elif observation.category == 'new_report':
        copy = f'{observation.facts[0].publisher} published {observation.title}.'
    else:
        copy = observation.title + '.'
    lines = [copy]
    for fact in sorted(observation.facts, key=lambda f: f.fact_id):
        lines.append(f'{fact.entity} — {fact.metric}, {fact.period}: {fact.value} {fact.scale} {fact.unit} ({fact.classification}; {fact.comparison_basis}).')
    if unresolved_placeholders(lines):
        raise SocialError('UNRESOLVED_TEMPLATE', 'Supply complete factual evidence before creating a draft.', 422)
    return '\n'.join(lines)


def consume_observation(svc: SocialService, observation, *, backfill=False):
    """Internal typed post-commit seam; no untrusted HTTP fact submission.

    The ETL adapter must read committed records using the caller's fresh session.
    A failed caller transaction rolls cursor, event, draft and audit back together.
    """
    observation = SourceObservation.model_validate(observation.model_dump(mode='json') if isinstance(observation, SourceObservation) else observation)
    if type(backfill) is not bool:
        raise SocialError('INVALID_REQUEST', 'Backfill must be explicit.', 422)
    if not observation.committed or observation.fixture or observation.quarantined or not observation.publishable:
        raise SocialError('SOURCE_NOT_ELIGIBLE', 'Only committed, publishable, nonfixture evidence can generate drafts.', 422)
    now = svc.now()
    if any(utc(f.verified_at) > now or utc(f.retrieved_at) > now for f in evidence_items(observation)):
        raise SocialError('SOURCE_NOT_ELIGIBLE', 'Future evidence timestamps cannot certify a draft.', 422)
    cfg = controls(svc.db, lock=True)
    if not cfg.drafts_enabled or observation.source_type not in cfg.source_allowlist:
        raise SocialError('GENERATION_DISABLED', 'Draft generation is disabled for this source.')
    # Same first delivery lock as approval/cancellation/worker permits. A new
    # source version cannot slip between source verification and authorization.
    _insert(svc.db, SocialControls, dict(id=1, version=1, publishing_enabled=False, generation_enabled=False, auto_approve_enabled=False, auto_schedule_enabled=False, auto_publish_enabled=False, platform_controls={}, budget_controls={}), ['id'])
    svc.db.scalar(select(SocialControls).where(SocialControls.id == 1).with_for_update().execution_options(populate_existing=True))
    if observation.report is not None and getattr(observation.report, 'native_domain', None) is not None:
        from .authority import verify_report_authority
        verify_report_authority(svc.db, observation.model_dump(mode='json'))
    if observation.financial is not None:
        from .authority import verify_financial_authority
        verify_financial_authority(svc.db, observation.model_dump(mode='json'))
    render(observation)  # Reject unresolved copy even when business values match.
    fingerprint = semantic_fingerprint(observation)
    release = report_release_state(observation)
    identity = dict(source_type=observation.source_type, source_key=observation.source_key, detector_version=DETECTOR_VERSION)
    initial_id = uuid4()
    state = release if release else financial_state(observation)
    _insert(svc.db, SourceCursor, dict(id=initial_id, **identity, evidence_version=observation.evidence_version, sequence=0, fingerprint=fingerprint, report_state=state), list(identity))
    cursor = svc.db.scalar(select(SourceCursor).filter_by(**identity).with_for_update().execution_options(populate_existing=True))
    initial = cursor.id == initial_id
    old_event = svc.db.scalar(select(SourceEvent).where(SourceEvent.cursor_id == cursor.id, SourceEvent.sequence == cursor.sequence)) if cursor.sequence else None
    if not initial and observation.report is None:
        prior = prior_financial_fingerprint(observation, cursor, old_event)
        cursor.fingerprint, cursor.report_state = prior, state
    refresh_backfill = bool(release and backfill and old_event and (
        old_event.fingerprint != fingerprint or any(
            old_event.observation['report'][key] != getattr(observation.report, key)
            for key in ('source_record_id', 'authority_fingerprint'))))
    refresh_backfill = refresh_backfill or bool(observation.financial and backfill and old_event
        and old_event.observation != observation.model_dump(mode='json'))
    established = established_financial_source(svc.db, observation, initialize=True)
    if not initial:
        if release:
            if not valid_report_release_state(cursor.report_state):
                raise SocialError('EVIDENCE_INTEGRITY_FAILED', 'Report release state is unavailable.', 503)
            if report_release_regresses(release,cursor.report_state):
                raise SocialError('REPORT_RELEASE_REGRESSION', 'Report timing cannot regress, lose publication authority or change evidence kind for the same period.', 422)
        if observation.evidence_version < cursor.evidence_version or (fingerprint != cursor.fingerprint and observation.evidence_version <= cursor.evidence_version):
            raise SocialError('EVIDENCE_VERSION_CONFLICT', 'Changed or stale evidence requires an explicit newer evidence version.')
        if refresh_backfill and observation.evidence_version <= old_event.evidence_version:
            raise SocialError('EVIDENCE_VERSION_CONFLICT', 'Refreshed report authority requires a newer committed ingestion.')
        if fingerprint == cursor.fingerprint and not (backfill and cursor.sequence == 0) and not refresh_backfill:
            cursor.evidence_version = observation.evidence_version
            return {'status': 'unchanged', 'event_id': None, 'post_id': None, 'sequence': cursor.sequence}
    if initial and not backfill and not established:
        svc.audit('generation.baseline', details={**identity, 'evidence_version': observation.evidence_version, 'fingerprint': fingerprint})
        svc.db.flush()
        return {'status': 'baseline', 'event_id': None, 'post_id': None, 'sequence': 0}
    if cursor.sequence > 0:
        old_post = svc.db.scalar(select(SocialPost).where(SocialPost.source_event_id == old_event.id)) if old_event else None
        if old_post is not None and svc._publication(old_post) is not None:
            # Archive has already established terminal delivery state and retains
            # its authorization as evidence. Superseding source data must create
            # a new draft without reopening/cancelling that read-only history.
            if old_post.editorial_state != 'archived' and old_post.archived_at is None:
                svc.cancel(old_post.id, VersionCommand(expected_version=old_post.row_version))
            svc.audit('generation.source_superseded', post=old_post, reason='New explicit source evidence version', details={'source_event_id': str(old_event.id), 'new_evidence_version': observation.evidence_version})
        elif (observation.financial is not None and old_post is not None
                and old_post.editorial_state != 'archived' and old_post.archived_at is None):
            svc.archive(old_post.id, VersionCommand(expected_version=old_post.row_version))
            svc.audit('generation.source_superseded', post=old_post, reason='New current financial evidence requires human review',
                details={'source_event_id':str(old_event.id),'new_evidence_version':observation.evidence_version})
    if release and not backfill and release['release_hash'] == cursor.report_state['release_hash']:
        # A new acquisition/artifact can invalidate old authority without making
        # another report available. Preserve the release baseline; create no copy.
        cursor.evidence_version, cursor.fingerprint, cursor.observed_at = observation.evidence_version, fingerprint, now
        cursor.report_state = release
        svc.audit('generation.report_evidence_refreshed', details={**identity, 'evidence_version': observation.evidence_version, 'fingerprint': fingerprint})
        svc.db.flush()
        return {'status': 'unchanged', 'event_id': None, 'post_id': None, 'sequence': cursor.sequence}
    cursor.sequence += 1
    cursor.evidence_version, cursor.fingerprint, cursor.observed_at = observation.evidence_version, fingerprint, now
    cursor.report_state = state
    event = SourceEvent(id=uuid4(), cursor_id=cursor.id, sequence=cursor.sequence, evidence_version=observation.evidence_version, fingerprint=fingerprint, observation=observation.model_dump(mode='json'))
    svc.db.add(event)
    svc.db.flush()
    document = PostDocument.model_validate({'master': {'text': render(observation), 'link': evidence_items(observation)[0].canonical_url}, 'targets': cfg.targets})
    references = [{'url': f.document_url, 'label': f'{f.publisher} · {f.locator}'} for f in evidence_items(observation)]
    evidence = {'references': references, 'source_event_id': str(event.id), 'evidence_version': event.evidence_version, 'source': event.observation, 'fingerprint': fingerprint}
    from .worker_authority import capture_worker_authority
    witness = capture_worker_authority(svc.db, event.observation)
    if witness is not None:
        evidence['worker_authority'] = witness
    post = SocialPost(id=uuid4(), origin_type='generated', creation_method='pipeline', title=observation.title, content_type=observation.category, editorial_state='pending_review', source_event_id=event.id, created_by=svc.actor)
    svc.db.add(post)
    svc.db.flush()
    revision = svc._new_revision(post, document, references, 1, evidence_snapshot=evidence, generator_metadata=generator_metadata(observation))
    svc.audit('generation.draft_created', post=post, new='pending_review', details={'event_id': str(event.id), 'sequence': event.sequence, 'revision_id': str(revision.id), 'content_hash': revision.content_hash, 'backfill': backfill})
    svc.db.flush()
    from ..automation.service import maybe_automate_generated
    maybe_automate_generated(svc, post)
    return {'status': 'draft_created', 'event_id': str(event.id), 'post_id': str(post.id), 'sequence': event.sequence}


class GenerationService:
    def __init__(self, svc):
        self.svc, self.db = svc, svc.db

    def set_controls(self, body):
        body = GenerationControlsCommand.model_validate(body.model_dump(mode='json'))
        cfg = controls(self.db, lock=True)
        if cfg.version != body.expected_version:
            raise SocialError('VERSION_CONFLICT', 'Draft/shadow controls changed. Refresh before updating.')
        cfg.version += 1
        cfg.drafts_enabled, cfg.shadow_enabled = body.drafts_enabled, body.shadow_enabled
        cfg.source_allowlist = list(body.source_allowlist)
        cfg.targets = [t.model_dump(mode='json') for t in body.targets]
        self.svc.audit('generation.controls_updated', reason=body.reason, details=controls_dto(cfg))
        self.db.flush()
        return controls_dto(cfg)

    def save_rule(self, rule_id, body):
        body = RuleCommand.model_validate(body.model_dump(mode='json'))
        controls(self.db, lock=True)
        # Rule disable/supersession uses the same final ordering point as
        # source events, policy authorization and worker mutation permits.
        from ..automation.service import global_controls
        global_controls(self.db)
        latest = self.db.scalar(select(AutomationRuleVersion).where(AutomationRuleVersion.rule_id == rule_id).order_by(AutomationRuleVersion.version.desc()).limit(1))
        if (latest.version if latest else 0) != body.expected_version:
            raise SocialError('VERSION_CONFLICT', 'This rule changed. Refresh its immutable version history.')
        value = body.model_dump(mode='json', exclude={'expected_version'})
        row = AutomationRuleVersion(rule_id=rule_id, version=body.expected_version + 1, definition=value, definition_hash=canonical_hash(value), created_by=self.svc.actor)
        self.db.add(row)
        self.svc.audit('automation.rule_version_created', reason=body.reason, details={'rule_id': str(rule_id), 'version': row.version, 'definition_hash': row.definition_hash})
        self.db.flush()
        return rule_dto(row)

    def evaluate(self, post_id, body):
        body = EvaluateCommand.model_validate(body.model_dump(mode='json'))
        cfg = controls(self.db, lock=True)  # serializes all cadence decisions and control changes
        if not cfg.shadow_enabled:
            raise SocialError('SHADOW_DISABLED', 'Shadow evaluation is disabled.')
        post = self.svc._post(post_id)
        revision = self.svc._revision(post)
        if post.row_version != body.expected_version or revision.id != body.revision_id:
            raise SocialError('VERSION_CONFLICT', 'This draft changed. Refresh before evaluating.')
        rule = self.db.scalar(select(AutomationRuleVersion).where(AutomationRuleVersion.rule_id == body.rule_id, AutomationRuleVersion.version == body.rule_version))
        latest = self.db.scalar(select(func.max(AutomationRuleVersion.version)).where(AutomationRuleVersion.rule_id == body.rule_id))
        if not rule or latest != body.rule_version:
            raise SocialError('VERSION_CONFLICT', 'Choose the current immutable rule version.')
        reasons = []
        definition = RuleCommand.model_validate({'expected_version': rule.version - 1, **rule.definition})
        if canonical_hash(rule.definition) != rule.definition_hash:
            raise SocialError('RULE_INTEGRITY_FAILED', 'The rule definition hash does not match.', 503)
        if post.editorial_state in {'rejected', 'archived'}:
            reasons.append('EDITORIAL_REVIEW_REQUIRED')
        if definition.mode != 'shadow':
            reasons.append('RULE_DISABLED')
        event = self.db.get(SourceEvent, post.source_event_id) if post.source_event_id else None
        if post.origin_type != 'generated' or not event:
            reasons.append('GENERATED_SOURCE_REQUIRED')
        else:
            observation = SourceObservation.model_validate(event.observation)
            if isinstance(observation.report,CataloguedNativeReportEvidence):
                reasons.append('CATALOGUE_HUMAN_REVIEW_REQUIRED')
            cursor = self.db.get(SourceCursor, event.cursor_id)
            if cursor.sequence != event.sequence or observation.report and cursor.fingerprint != event.fingerprint:
                reasons.append('SOURCE_SUPERSEDED')
            if observation.report:
                from .authority import verify_report_authority
                try:
                    verify_report_authority(self.db, event.observation)
                except SocialError as error:
                    reasons.append(error.code)
            if observation.category not in definition.categories or observation.source_type not in definition.source_allowlist:
                reasons.append('SOURCE_CATEGORY_NOT_ALLOWLISTED')
            if revision.document.get('master', {}).get('text', '') != render(observation):
                reasons.append('GENERATED_COPY_EDITED')
            if observation.correction_pending or observation.category == 'correction':
                reasons.append('CORRECTION_REQUIRES_REVIEW')
            now = self.svc.now()
            if any(utc(f.verified_at) > now or utc(f.verified_at) < now - timedelta(hours=definition.freshness_hours) for f in evidence_items(observation)):
                reasons.append('EVIDENCE_STALE')
            if event.fingerprint not in (semantic_fingerprint(observation), legacy_fingerprint(observation)) or revision.evidence_snapshot.get('source_event_id') != str(event.id) or revision.evidence_snapshot.get('source') != event.observation:
                reasons.append('EVIDENCE_INTEGRITY_FAILED')
        if canonical_hash({'document': revision.document, 'evidence_snapshot': revision.evidence_snapshot}) != revision.content_hash:
            reasons.append('REVISION_INTEGRITY_FAILED')
        document = PostDocument.model_validate(revision.document)
        if any(t.overrides.model_fields_set for t in document.targets):
            reasons.append('CUSTOMIZATION_REQUIRES_REVIEW')
        accounts = sorted(str(t.account_id) for t in document.targets)
        if not accounts or not set(accounts) <= {str(a) for a in definition.account_allowlist}:
            reasons.append('ACCOUNT_NOT_ALLOWLISTED')
        result = validate_document(self.db, document, revision.evidence_snapshot, self.svc.available_adapters)
        if not result.valid:
            reasons.append('TARGET_VALIDATION_FAILED')
        for account_id in accounts:
            account = self.db.get(SocialAccount, UUID(account_id))
            if account is None or account.platform in {'x', 'tiktok'}:
                reasons.append('BUDGET_OR_AUTOMATION_ACCESS_UNVERIFIED')
        now = self.svc.now()
        # Reserve would-allow suggestions globally per account across all rules.
        recent = list(self.db.scalars(select(ShadowDecision).where(ShadowDecision.outcome == 'would_allow', ShadowDecision.created_at >= now - timedelta(days=1), ShadowDecision.revision_id != revision.id).order_by(ShadowDecision.created_at.desc()).limit(1001)))
        if len(recent) > 1000:
            reasons.append('CADENCE_HISTORY_LIMIT')
        for account_id in accounts:
            matching = [d for d in recent if account_id in d.account_ids]
            if len({d.revision_id for d in matching}) >= definition.max_per_day:
                reasons.append('DAILY_CADENCE_LIMIT')
            if any(utc(d.created_at) > now - timedelta(minutes=definition.min_interval_minutes) for d in matching):
                reasons.append('MINIMUM_INTERVAL')
        outcome = 'human_review' if reasons else 'would_allow'
        reasons = sorted(set(reasons)) or ['ALL_SHADOW_GATES_PASSED_HUMAN_APPROVAL_REQUIRED']
        inputs = {'controls_version': cfg.version, 'rule_hash': rule.definition_hash, 'source_event_id': str(event.id) if event else None, 'source_sequence': cursor.sequence if event else None, 'live_execution': False}
        context_hash = canonical_hash({'outcome': outcome, 'reasons': reasons, 'accounts': accounts, 'inputs': inputs})
        old = self.db.scalar(select(ShadowDecision).where(ShadowDecision.rule_version_id == rule.id, ShadowDecision.revision_id == revision.id, ShadowDecision.context_hash == context_hash))
        if old:
            return decision_dto(old)
        decision = ShadowDecision(rule_version_id=rule.id, post_id=post.id, revision_id=revision.id, content_hash=revision.content_hash, context_hash=context_hash, outcome=outcome, reasons=reasons, account_ids=accounts, inputs=inputs)
        self.db.add(decision)
        self.svc.audit('automation.shadow_decision', post=post, details={'rule_id': str(rule.rule_id), 'rule_version': rule.version, 'outcome': decision.outcome, 'reasons': decision.reasons, 'content_hash': revision.content_hash})
        self.db.flush()
        return decision_dto(decision)


def rule_dto(row):
    return {'id': str(row.rule_id), 'version': row.version, 'definition': row.definition, 'definition_hash': row.definition_hash, 'created_at': iso(row.created_at)}


def decision_dto(row):
    return {'id': str(row.id), 'post_id': str(row.post_id), 'revision_id': str(row.revision_id), 'rule_version_id': str(row.rule_version_id), 'content_hash': row.content_hash, 'outcome': row.outcome, 'reasons': row.reasons, 'account_ids': row.account_ids, 'inputs': row.inputs, 'created_at': iso(row.created_at)}


def verify_generated_revision(db, post, revision, *, lock=True):
    """An old or detached evidence event cannot authorize a generated revision."""
    if post.origin_type != 'generated':
        return
    event = db.get(SourceEvent, post.source_event_id) if post.source_event_id else None
    stmt = select(SourceCursor).where(SourceCursor.id == event.cursor_id).execution_options(populate_existing=True) if event else None
    cursor = db.scalar(stmt.with_for_update() if lock else stmt) if event else None
    if not event or not cursor or cursor.sequence != event.sequence:
        raise SocialError('SOURCE_REVIEW_REQUIRED', 'Source evidence changed. Review the newer generated draft.', 422)
    if event.observation.get('report') and cursor.fingerprint != event.fingerprint:
        raise SocialError('SOURCE_REVIEW_REQUIRED', 'The report artifact changed. Review its current evidence.', 422)
    if revision.evidence_snapshot.get('source_event_id') != str(event.id) or revision.evidence_snapshot.get('source') != event.observation:
        raise SocialError('EVIDENCE_INTEGRITY_FAILED', 'Generated provenance does not match its immutable source event.', 503)
    from .authority import verify_report_authority
    verify_report_authority(db, event.observation)
    if event.observation.get('financial') is not None:
        from .authority import verify_financial_authority
        verify_financial_authority(db, event.observation)
    source = event.observation
    native = (source.get('financial') is not None or source.get('report') is None
              or isinstance(source.get('report'), dict)
              and source['report'].get('native_domain') is not None)
    if native or revision.evidence_snapshot.get('worker_authority') is not None:
        from .worker_authority import verify_worker_authority
        verify_worker_authority(db, source, revision.evidence_snapshot.get('worker_authority'))
    if unresolved_placeholders(revision.document) or unresolved_placeholders(revision.evidence_snapshot):
        raise SocialError('UNRESOLVED_TEMPLATE', 'Resolve every placeholder before authorization.', 422)


def unresolved_placeholders(value):
    import re
    if isinstance(value, str):
        return re.search(r'\{\{|\}\}|\[(?:TODO|TBD|AMOUNT|VALUE|FIGURE|PERIOD|COUNTY)(?:\b|_)|<placeholder>', value, re.IGNORECASE) is not None
    if isinstance(value, dict):
        return any(unresolved_placeholders(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(unresolved_placeholders(v) for v in value)
    return False
