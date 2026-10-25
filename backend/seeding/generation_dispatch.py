"""Default-off post-commit generation; financial and draft outcomes stay distinct."""
import logging
import json
import os
import re

from models import IngestionJob, IngestionStatus
from .generation_capabilities import capability
from services.generation_outcome import refusal_counts, confirmed_counts
from .source_observations import SourceObservationUnavailable, read_county_budget_record_ids

logger = logging.getLogger("seeding.generation")
COUNTERS = ("processed", "drafts_created", "baselines", "unchanged", "refused")


def _result(state, reason):
    return {"state": state, "reason": reason, **dict.fromkeys(COUNTERS, 0)}


def _unverified(reason):
    return {"state": "failed", "reason": reason, "execution_unverified": True,
            **dict.fromkeys(COUNTERS, None)}


def _invoke(factory, record_ids, ingestion_id):
    # Import only after the explicit environment ceiling and committed-source
    # guards. An older installation needs no social schema/import to ingest.
    from social.generation.integration import maybe_generate_committed
    return maybe_generate_committed(factory, record_ids=record_ids, ingestion_id=ingestion_id)


def _invoke_reports(factory, record_ids, ingestion_id):
    from social.generation.integration import maybe_generate_reports_committed
    return maybe_generate_reports_committed(factory, record_ids=record_ids, ingestion_id=ingestion_id)


def _validate_result(value, expected):
    if type(expected) is not int or not 0 <= expected <= 1000:
        raise ValueError('Bounded expected cohort required')
    if type(value) is dict and value.get('execution_unverified') is True:
        if (set(value) != {'state', 'reason', 'execution_unverified', 'confirmed', *COUNTERS}
                or value['state'] != 'failed' or type(value['reason']) is not str
                or not re.fullmatch(r'[A-Za-z_]{1,160}', value['reason'])
                or any(value[k] is not None for k in COUNTERS)):
            raise ValueError('Invalid uncertain generation outcome')
        confirmed_counts(value['confirmed'], expected)
        return dict(value)
    if (type(value) is not dict or set(value) - {"refusal_reasons"} != {"state", "reason", *COUNTERS}
            or value["state"] not in ("disabled", "completed", "unavailable", "failed")
            or type(value["reason"]) is not str
            or not re.fullmatch(r"[A-Za-z_]{1,160}", value["reason"])
            or any(type(value[k]) is not int or not 0 <= value[k] <= expected for k in COUNTERS)
            or sum(value[k] for k in COUNTERS[1:]) != value["processed"]
            or value["state"] == "completed" and (value["processed"] != expected or value["refused"] != 0)):
        raise ValueError("Invalid generation outcome")
    if 'refusal_reasons' in value:
        refusal_counts(value['refusal_reasons'], value['refused'])
    return dict(value)


def dispatch_committed_generation(factory, *, domain, ingestion_id, dry_run, include_reports=True):
    """Called after CLI session closure; never changes financial terminal status.

    No automatic retry follows an uncertain generation outcome. The operator's
    idempotent detect command is the recovery path. The hook owns its own atomic
    event/audit transactions; this module writes only separate job telemetry.
    """
    if type(include_reports) is not bool:
        raise ValueError('Explicit report phase selection required')
    if dry_run is not False:
        return None
    if type(ingestion_id) is not int or not 0 < ingestion_id <= 2147483647:
        raise ValueError("Positive bounded ingestion ID required")
    selected = capability(domain)
    flag = os.environ.get("SOCIAL_GENERATION_HOOK_ENABLED", "false")
    if flag == "false":
        return None
    if flag != "true":
        outcome = _result("unavailable", "invalid_generation_hook_flag")
    elif not selected.financial:
        outcome = _result('unavailable', selected.reason)
    else:
        invoked = False
        try:
            record_ids = read_county_budget_record_ids(factory, ingestion_id=ingestion_id)
            if record_ids:
                invoked = True
                outcome = _validate_result(_invoke(factory, record_ids, ingestion_id), len(record_ids))
            else:
                outcome = _result("completed", "no_new_record_lineage")
        except SourceObservationUnavailable:
            outcome = (_unverified("generation_execution_unverified") if invoked
                       else _result("unavailable", "source_lineage_unavailable"))
        except ModuleNotFoundError:
            # Conservatively retain unknown progress: an installed hook could
            # have committed a record before a later lazy import failed.
            outcome = _unverified("generation_dependency_execution_unverified")
        except Exception:
            logger.warning("post_commit_generation_failed")
            outcome = (_unverified("generation_execution_unverified") if invoked
                       else _result("failed", "generation_source_read_failed"))
    _record_outcome(factory, domain, ingestion_id, outcome)
    if selected.reports and include_reports and flag == 'true' and os.environ.get('SOCIAL_REPORT_GENERATION_ENABLED', 'false') != 'false':
        dispatch_committed_report_generation(factory, domain=domain, ingestion_id=ingestion_id, dry_run=dry_run)
    return outcome


def dispatch_committed_report_generation(factory, *, domain, ingestion_id, dry_run):
    """Independent telemetry; never combine report and financial record counters."""
    if domain != 'counties_budget' or dry_run is not False or os.environ.get('SOCIAL_GENERATION_HOOK_ENABLED','false') != 'true':
        return None
    if type(ingestion_id) is not int or not 0 < ingestion_id <= 2147483647:
        raise ValueError('Positive bounded ingestion ID required')
    flag = os.environ.get('SOCIAL_REPORT_GENERATION_ENABLED', 'false')
    if flag != 'true':
        outcome = _result('disabled' if flag == 'false' else 'unavailable',
            'report_environment_disabled' if flag == 'false' else 'invalid_report_hook_flag')
        _record_outcome(factory, domain, ingestion_id, outcome, key='post_commit_report_generation')
        return outcome
    invoked = False
    try:
        records = read_county_budget_record_ids(factory, ingestion_id=ingestion_id)
        if records:
            invoked = True
            outcome = _validate_result(_invoke_reports(factory, records, ingestion_id), len(records))
        else:
            outcome = _result('completed', 'no_new_record_lineage')
    except SourceObservationUnavailable:
        outcome = (_unverified('report_generation_execution_unverified') if invoked
                   else _result('unavailable', 'source_lineage_unavailable'))
    except Exception:
        logger.warning('post_commit_report_generation_failed')
        outcome = (_unverified('report_generation_execution_unverified') if invoked
                   else _result('failed', 'report_source_read_failed'))
    _record_outcome(factory, domain, ingestion_id, outcome, key='post_commit_report_generation')
    return outcome


def record_generation_timeout(factory, *, domain, ingestion_id, financial_outcome=None, reports_started=None):
    if domain != "counties_budget" or type(ingestion_id) is not int or not 0 < ingestion_id <= 2147483647:
        raise ValueError("Bounded CoB ingestion identity required")
    outcome = _unverified("generation_timeout_execution_unverified")
    if financial_outcome is not None:
        try:
            if type(financial_outcome) is not dict:
                raise ValueError('Confirmed result must be a dictionary')
            processed = (financial_outcome['confirmed']['processed'] if financial_outcome.get('execution_unverified') is True else financial_outcome['processed'])
            if type(processed) is not int or not 0 <= processed <= 1000:
                raise ValueError('Bounded confirmed result required')
            outcome = _validate_result(financial_outcome, processed)
        except (KeyError, TypeError, ValueError):
            logger.error('generation_timeout_financial_result_unverified')
    _record_outcome(factory, domain, ingestion_id, outcome)
    if os.environ.get('SOCIAL_REPORT_GENERATION_ENABLED', 'false') != 'false':
        report = (_result('unavailable','report_generation_not_started') if reports_started is False
                  else _unverified('report_generation_timeout_execution_unverified'))
        _record_outcome(factory, domain, ingestion_id, report, key='post_commit_report_generation')
    return outcome


def _record_outcome(factory, domain, ingestion_id, outcome, *, key='post_commit_generation'):
    if key not in {'post_commit_generation', 'post_commit_report_generation'}:
        raise ValueError('Known generation telemetry key required')
    try:
        with factory.begin() as db:
            from .source_observations import _read_limits
            if db.get_bind().dialect.name == "postgresql":
                _read_limits(db)
            job = db.get(IngestionJob, ingestion_id, with_for_update=True)
            if (job is None or job.domain != domain or job.dry_run is not False
                    or job.status != IngestionStatus.COMPLETED):
                raise ValueError("Committed job required for generation telemetry")
            preserved = {c.key: getattr(job, c.key) for c in IngestionJob.__mapper__.column_attrs
                         if c.key not in {'meta', 'errors'}}
            expected_errors = json.dumps(job.errors, sort_keys=True, allow_nan=False)
            metadata = {**(job.meta or {}), key: outcome}
            # Freeze intended bytes before ORM/database callbacks can change
            # either the assigned JSON or an aliased outcome object.
            expected_metadata = json.dumps(metadata, sort_keys=True, allow_nan=False)
            job.meta = metadata
            db.flush()
            if db.get_bind().dialect.name == 'postgresql':
                from sqlalchemy import text
                db.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
            db.refresh(job)
            if (json.dumps(job.meta, sort_keys=True, allow_nan=False) != expected_metadata
                    or json.dumps(job.errors, sort_keys=True, allow_nan=False) != expected_errors
                    or any(type(getattr(job, key)) is not type(value) or getattr(job, key) != value
                           for key, value in preserved.items())):
                raise ValueError('Generation telemetry readback differs')
    except Exception:
        # Facts were committed before this boundary. A telemetry write failure
        # cannot truthfully become an ETL rollback/failure or release uncertainty.
        logger.error("post_commit_generation_receipt_unavailable")
