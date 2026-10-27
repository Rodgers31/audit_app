"""Read-only bounded eligibility preview. No cursors, receipts, drafts or audits.

This is an observation of eligibility, not a reservation. Detection re-reads and
serializes source state using its existing command and cursor locks.
"""
from importlib import import_module
from collections import Counter

from sqlalchemy import select, text, tuple_
from pydantic import ValidationError

if __package__.startswith('backend.'):
    from backend.seeding.generation_capabilities import capability, CAPABILITIES
    from backend.services.generation_outcome import REFUSAL_REASONS
else:
    from seeding.generation_capabilities import capability, CAPABILITIES
    from services.generation_outcome import REFUSAL_REASONS
from .contracts import SourceObservation, PreviewCommand
from .models import GenerationControls, SourceCursor, SourceEvent
from ..service import SocialError
from .service import render, semantic_fingerprint, report_release_state, valid_report_release_state, DETECTOR_VERSION


def capabilities_dto():
    return [dict(domain=c.domain, financial=c.financial, reports=c.reports, reason=c.reason)
            for c in CAPABILITIES.values()]


def _decision(observation, cursor, old, *, backfill):
    """Mirror detector identity/version/release guards without any mutation."""
    if cursor is None:
        return ('eligible_change', 'explicit_backfill') if backfill else ('baseline', 'first_observation')
    fingerprint = semantic_fingerprint(observation)
    release = report_release_state(observation)
    if release:
        if not valid_report_release_state(cursor.report_state):
            return 'refused', 'evidence_integrity_failed'
        if any(release[k] < cursor.report_state[k] for k in ('published_on','period_start','period_end')):
            return 'refused', 'report_release_regression'
    if observation.evidence_version < cursor.evidence_version or (fingerprint != cursor.fingerprint and observation.evidence_version <= cursor.evidence_version):
        return 'refused', 'evidence_version_conflict'
    refresh = bool(release and backfill and old and (old.fingerprint != fingerprint or any(
        old.observation['report'][k] != getattr(observation.report, k)
        for k in ('source_record_id','authority_fingerprint'))))
    if refresh and observation.evidence_version <= old.evidence_version:
        return 'refused', 'evidence_version_conflict'
    if fingerprint == cursor.fingerprint and not (backfill and cursor.sequence == 0) and not refresh:
        return 'unchanged', 'semantic_evidence_unchanged'
    if release and not backfill and release['release_hash'] == cursor.report_state['release_hash']:
        return 'unchanged', 'report_release_unchanged'
    return 'eligible_change', 'explicit_backfill' if backfill else 'semantic_evidence_changed'


def preview(factory, body):
    body = PreviewCommand.model_validate(body.model_dump(mode='json') if isinstance(body, PreviewCommand) else body)
    from .integration import _remaining_ms, _transaction_limits
    import time
    deadline = time.monotonic() + 30
    selected = capability(body.domain)
    if not (selected.reports if body.reports else selected.financial):
        return dict(drafts_enabled=False, results=[dict(record_id=r, status='unsupported_source',
            reason=selected.reason, source_document_id=None) for r in body.record_ids])
    adapter = import_module('backend.seeding.source_observations' if __package__.startswith('backend.') else 'seeding.source_observations')
    read = getattr(adapter, selected.report_reader if body.reports else selected.financial_reader)
    values, results = [], []
    for record_id in body.record_ids:
        _remaining_ms(deadline)
        try:
            value = SourceObservation.model_validate(read(factory, record_id=record_id, ingestion_id=body.ingestion_id))
            if not value.committed or value.fixture or value.quarantined or not value.publishable:
                raise ValueError('Ineligible observation')
            _remaining_ms(deadline)
            values.append((record_id, value))
        except adapter.SourceObservationUnavailable as error:
            code = getattr(error, 'code', 'source_evidence_ineligible')
            if getattr(error, 'operational', False):
                raise SocialError(code.upper(), 'The committed source reader is unavailable.', 503) from None
            results.append(dict(record_id=record_id, status='refused', reason=code if code in REFUSAL_REASONS else 'source_evidence_ineligible', source_document_id=None))
        except (ValidationError, ValueError):
            results.append(dict(record_id=record_id, status='refused', reason='source_evidence_ineligible', source_document_id=None))
    series = Counter((v.source_type, v.source_key) for _, v in values)
    unique = []
    for record_id, value in values:
        if series[(value.source_type, value.source_key)] > 1:
            results.append(dict(record_id=record_id, status='refused', reason='duplicate_source_series', source_document_id=None))
        else:
            unique.append((record_id, value))
    values = unique
    _remaining_ms(deadline)
    db = factory()
    if db.in_transaction() or db.new or db.dirty or db.deleted or db.identity_map:
        raise ValueError('Fresh preview session required')
    with db:
        _remaining_ms(deadline)
        if db.get_bind().dialect.name == 'postgresql':
            db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        _transaction_limits(db, deadline)
        cfg = db.get(GenerationControls, 1)
        _remaining_ms(deadline)
        source_type = {'counties_budget':'cob','national_budget':'cob','revenue_by_source':'kra','audits':'oag','pending_bills':'cob'}.get(body.domain)
        enabled = bool(cfg and cfg.drafts_enabled is True and source_type in cfg.source_allowlist)
        from ..service import SocialService, utc
        now = SocialService(db).now()
        _transaction_limits(db, deadline)
        # Two bounded projections replace per-record cursor/event queries.
        identities = {(v.source_type, v.source_key) for _, v in values}
        cursors = list(db.scalars(select(SourceCursor).where(
            tuple_(SourceCursor.source_type, SourceCursor.source_key).in_(identities),
            SourceCursor.detector_version == DETECTOR_VERSION))) if identities else []
        _transaction_limits(db, deadline)
        by_identity = {(c.source_type, c.source_key): c for c in cursors}
        event_keys = [(c.id, c.sequence) for c in cursors if c.sequence]
        events = list(db.scalars(select(SourceEvent).where(tuple_(SourceEvent.cursor_id,
            SourceEvent.sequence).in_(event_keys)))) if event_keys else []
        by_cursor = {e.cursor_id: e for e in events}
        _remaining_ms(deadline)
        for record_id, value in values:
            cursor = by_identity.get((value.source_type, value.source_key))
            from .service import evidence_items
            status, reason = (('refused','source_chronology_invalid') if any(utc(f.verified_at)>now or utc(f.retrieved_at)>now for f in evidence_items(value))
                else _decision(value, cursor, by_cursor.get(cursor.id) if cursor else None, backfill=body.backfill))
            if status == 'eligible_change':
                try:
                    render(value)
                except SocialError as error:
                    if error.code != 'UNRESOLVED_TEMPLATE':
                        raise
                    status, reason = 'refused', 'unresolved_template'
            results.append(dict(record_id=record_id, status=status, reason=reason,
                source_document_id=(value.report or value.facts[0]).source_document_id))
    _remaining_ms(deadline)
    by_id = {r['record_id']: r for r in results}
    return dict(drafts_enabled=enabled, results=[by_id[r] for r in body.record_ids])
