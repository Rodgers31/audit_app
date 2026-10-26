"""Optional existing-ETL post-commit hook. No worker, scheduler or live action.

Each event/draft commits independently; the result explicitly retains partial
progress. Replaying the complete known record cohort is safe after uncertainty.
"""
import logging
import os
import time

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ..service import SocialError, SocialService
from .models import GenerationControls
from .service import consume_observation

if __package__.startswith('backend.'):
    from backend.services.generation_outcome import COUNTERS, REFUSAL_REASONS
else:
    from services.generation_outcome import COUNTERS, REFUSAL_REASONS

logger = logging.getLogger(__name__)


class GenerationDeadlineExceeded(TimeoutError):
    pass


def _remaining_ms(deadline):
    import math
    remaining = deadline - time.monotonic()
    if not math.isfinite(remaining) or remaining <= 0:
        raise GenerationDeadlineExceeded('Generation deadline exceeded')
    return max(1, int(remaining * 1000))


def _transaction_limits(db, deadline):
    remaining = _remaining_ms(deadline)
    if db.get_bind().dialect.name == 'postgresql':
        # Preserve stricter inherited bounds; zero means previously unlimited.
        rows = db.execute(text("""SELECT name, set_config(name,
            CASE WHEN setting::bigint=0 THEN bounds.ms
                 ELSE LEAST(setting::bigint,bounds.ms) END::text, true)
            FROM pg_settings CROSS JOIN LATERAL (
                SELECT CASE WHEN name='lock_timeout' THEN :lock ELSE :statement END AS ms
            ) bounds WHERE name IN ('statement_timeout','lock_timeout')"""),
            {'lock': min(2000, remaining), 'statement': min(5000, remaining)}).all()
        if {row[0] for row in rows} != {'statement_timeout', 'lock_timeout'}:
            raise RuntimeError('Generation transaction bounds unavailable')


def _result(state, reason, *, processed=0, drafts_created=0, baselines=0, unchanged=0, refused=0, refusal_reasons=None):
    details = {"refusal_reasons": dict(refusal_reasons)} if refusal_reasons else {}
    return dict(**details, state=state, reason=reason, processed=processed, drafts_created=drafts_created, baselines=baselines, unchanged=unchanged, refused=refused)


def _consume_records(factory, record_ids, ingestion_id, deadline, counts, adapters, progress, *, reports=False, domain="counties_budget"):
    from importlib import import_module
    adapter = import_module('backend.seeding.source_observations' if __package__.startswith('backend.') else 'seeding.source_observations')
    if __package__.startswith('backend.'):
        from backend.seeding.generation_capabilities import capability
    else:
        from seeding.generation_capabilities import capability
    selected = capability(domain)
    read = getattr(adapter, selected.report_reader if reports else selected.financial_reader)
    # Reads occur before each separate mutation transaction, so one pooled
    # connection is sufficient. ETL's completed transaction is never borrowed.
    for offset in range(0, len(record_ids), 25):
        for record_id in record_ids[offset:offset + 25]:
            _remaining_ms(deadline)
            try:
                observation = read(factory, record_id=record_id, ingestion_id=ingestion_id)
            except adapter.SourceObservationUnavailable as error:
                code = getattr(error, 'code', 'source_evidence_ineligible')
                if getattr(error, 'operational', False):
                    return _result('failed', code.upper(), **counts)
                code = code if code in REFUSAL_REASONS else 'source_evidence_ineligible'
                counts['refusal_reasons'][code] = counts['refusal_reasons'].get(code, 0) + 1
                counts['processed'] += 1
                counts['refused'] += 1
                _remaining_ms(deadline)
                continue
            _remaining_ms(deadline)
            db = factory()
            if db.in_transaction() or db.new or db.dirty or db.deleted or db.identity_map:
                return _result('unavailable', 'FRESH_SESSION_REQUIRED', **counts)
            progress['uncertain'] = True
            phase = 'body'
            try:
                with db:
                    svc = SocialService(db, available_adapters=adapters)
                    svc.actor_kind = 'pipeline'
                    svc.request_id = f'etl-{"report" if reports else "generation"}:{ingestion_id}:{record_id}'
                    with db.begin():
                        _transaction_limits(db, deadline)
                        result = consume_observation(svc, observation)
                        _remaining_ms(deadline)
                        phase = 'commit'
            except GenerationDeadlineExceeded:
                if phase == 'body':
                    progress['uncertain'] = False
                raise
            except (SocialError, ValidationError) as error:
                if phase != 'body':
                    raise
                code = error.code.lower() if isinstance(error, SocialError) else 'source_evidence_ineligible'
                if code not in REFUSAL_REASONS:
                    raise
                # The context has rolled this record's cursor/event/draft back.
                # A known evidence refusal is processed; later records may still
                # be eligible. Database/unknown failures retain the outer path.
                progress['uncertain'] = False
                counts['processed'] += 1
                counts['refused'] += 1
                counts['refusal_reasons'][code] = counts['refusal_reasons'].get(code, 0) + 1
                _remaining_ms(deadline)
                continue
            progress['uncertain'] = False
            counts['processed'] += 1
            counts[{'draft_created': 'drafts_created', 'baseline': 'baselines', 'unchanged': 'unchanged'}[result['status']]] += 1
            _remaining_ms(deadline)
    if counts['refused']:
        logger.warning('generation_hook_evidence_unavailable', extra={'refused_count': counts['refused'], 'processed_count': counts['processed']})
        return _result('unavailable', 'SOURCE_EVIDENCE_INELIGIBLE', **counts)
    return _result('completed', 'COMMITTED_EVIDENCE_CONSUMED', **counts)


def maybe_generate_committed(factory, *, record_ids, ingestion_id, native_registration=None, domain="counties_budget"):
    return _generate_committed(factory, record_ids=record_ids, ingestion_id=ingestion_id, native_registration=native_registration, reports=False, domain=domain)


def maybe_generate_reports_committed(factory, *, record_ids, ingestion_id, native_registration=None, domain="counties_budget"):
    """Separate default-off neutral report path; financial observations stay intact."""
    return _generate_committed(factory, record_ids=record_ids, ingestion_id=ingestion_id, native_registration=native_registration, reports=True, domain=domain)


def _generate_committed(factory, *, record_ids, ingestion_id, native_registration, reports, domain):
    """Only call after a successful live non-dry county-budget fact commit.

    The source adapter independently rechecks that prerequisite. Environment and
    runtime controls both start off; enabling safe drafts grants no live action.
    At most1000 explicit unique record IDs are accepted; never silently truncate.
    """
    if (type(ingestion_id) is not int or not 1 <= ingestion_id <= 2147483647
            or not isinstance(record_ids, (list, tuple)) or not 1 <= len(record_ids) <= 1000
            or any(type(v) is not int or not 1 <= v <= 2147483647 for v in record_ids)
            or len(set(record_ids)) != len(record_ids)):
        return _result('unavailable', 'INVALID_RECORD_COHORT')
    flag = os.environ.get('SOCIAL_GENERATION_HOOK_ENABLED', 'false')
    if flag not in {'true', 'false'}:
        return _result('unavailable', 'INVALID_HOOK_FLAG')
    if flag != 'true':
        return _result('disabled', 'ENVIRONMENT_DISABLED')
    if reports:
        report_flag = os.environ.get('SOCIAL_REPORT_GENERATION_ENABLED', 'false')
        if report_flag not in {'true', 'false'}:
            return _result('unavailable', 'INVALID_REPORT_HOOK_FLAG')
        if report_flag != 'true':
            return _result('disabled', 'REPORT_ENVIRONMENT_DISABLED')
    if __package__.startswith('backend.'):
        from backend.seeding.generation_capabilities import capability
    else:
        from seeding.generation_capabilities import capability
    selected = capability(domain)
    if not (selected.reports if reports else selected.financial):
        return _result('unavailable', 'UNSUPPORTED_SOURCE')
    source_type = {'national_budget':'cob','revenue_by_source':'kra','audits':'oag','pending_bills':'cob','counties_budget':'cob'}[domain]
    counts = dict(processed=0, drafts_created=0, baselines=0, unchanged=0, refused=0, refusal_reasons={})
    deadline = time.monotonic() + 30
    progress = {'uncertain': False}
    def failure(reason):
        if not progress['uncertain']:
            return _result('failed', reason, **counts)
        details = {'refusal_reasons': dict(counts['refusal_reasons'])} if counts['refusal_reasons'] else {}
        return dict(**details, state='failed', reason=reason, execution_unverified=True,
            **dict.fromkeys(COUNTERS, None), confirmed={k:counts[k] for k in COUNTERS})
    try:
        _remaining_ms(deadline)
        reader = factory()
        if reader.in_transaction() or reader.new or reader.dirty or reader.deleted or reader.identity_map:
            return _result('unavailable', 'FRESH_SESSION_REQUIRED')
        with reader:
            _transaction_limits(reader, deadline)
            cfg = reader.get(GenerationControls, 1)
            _remaining_ms(deadline)
            if cfg is None or cfg.drafts_enabled is not True or source_type not in cfg.source_allowlist:
                return _result('disabled', 'RUNTIME_SOURCE_DISABLED')
            engine = reader.get_bind()
            policy_requested = False
            if os.environ.get('SOCIAL_POLICY_AUTOMATION_ENABLED') == 'true':
                from ..models import SocialControls
                policy = reader.get(SocialControls, 1)
                policy_requested = policy is not None and policy.auto_approve_enabled is True
        def consume(adapters):
            if reports:
                return _consume_records(factory, record_ids, ingestion_id, deadline, counts, adapters, progress, reports=True, domain=domain)
            return _consume_records(factory, record_ids, ingestion_id, deadline, counts, adapters, progress, domain=domain)
        if not policy_requested:
            return consume({})  # Draft-only never loads native rules/material.
        from ..adapters.validation_registry import load_native_validation_registry, registry_adapters
        reason = None
        try:
            # Borrow a caller-owned installation, or construct only the exact
            # native content rules. Neither path owns a client or event loop.
            registration = native_registration
            if registration is None:
                registration = load_native_validation_registry()
            if registration is None:
                reason = 'NATIVE_REGISTRY_UNAVAILABLE'
                adapters = {}
            else:
                adapters = registry_adapters(registration, engine, borrowed=native_registration is not None)
        except SocialError as error:
            if error.code not in {'NATIVE_CONFIGURATION_INVALID', 'NATIVE_REGISTRY_INVALID'}:
                raise
            reason = 'NATIVE_REGISTRY_UNAVAILABLE' if error.code == 'NATIVE_CONFIGURATION_INVALID' else error.code
            adapters = {}
            logger.error('generation_native_validation_unavailable', extra={'error_code': error.code})
        _remaining_ms(deadline)
        result = consume(adapters)
        if reason and result['state'] == 'completed':
            return _result('unavailable', reason, **counts)
        return result
    except GenerationDeadlineExceeded:
        logger.error('generation_hook_deadline_exceeded', extra={'processed_count': counts['processed']})
        return failure('GENERATION_DEADLINE_EXCEEDED')
    except SocialError as error:
        if progress['uncertain']:
            return failure(error.code)
        if error.code == 'GENERATION_DISABLED':
            return _result('disabled', 'RUNTIME_SOURCE_DISABLED', **counts)
        logger.error('generation_hook_refused', extra={'error_code': error.code, 'processed_count': counts['processed']})
        return _result('unavailable', error.code, **counts)
    except ModuleNotFoundError as error:
        expected = error.name in {'seeding.source_observations', 'backend.seeding.source_observations'}
        logger.error('generation_hook_dependency_unavailable', extra={'expected_adapter': expected})
        if progress['uncertain']:
            return failure('GENERATION_DEPENDENCY_FAILED')
        return _result('unavailable' if expected else 'failed', 'SOURCE_ADAPTER_UNAVAILABLE' if expected else 'GENERATION_DEPENDENCY_FAILED', **counts)
    except DBAPIError:
        logger.error('generation_hook_database_unavailable', extra={'processed_count': counts['processed']})
        return failure('GENERATION_DATABASE_UNAVAILABLE')
    except Exception as error:
        logger.error('generation_hook_failed', extra={'error_type': type(error).__name__, 'processed_count': counts['processed']})
        return failure('GENERATION_FAILED')
