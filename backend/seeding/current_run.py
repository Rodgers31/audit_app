"""Fail-closed cache eligibility and bounded diagnostics for one native run.

This does not relax required_refresh_failures or grant source authority. It is
consumed only after actual CLI execution; database integrity/bootstrap are
separate direct Actions dependencies. All projected strings have closed vocabularies.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import os
import re
from pathlib import Path

from .source_plan import environment_plan, validate_plan
from .refresh_completion import REQUIRED_DOMAINS, accepted_records, fiscal_components_complete, audit_inventory_complete, required_refresh_failures

SCHEMA_HEAD = 'a756b20a0001'
MAX_JOBS = 18


def plan_identity(plan):
    validate_plan(plan)
    return hashlib.sha256(json.dumps(asdict(plan), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _hex(value, length):
    return type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is not None


def _number(value, *, positive=False):
    return type(value) is int and (1 if positive else 0) <= value <= 2**53 - 1


def _held_document(doc):
    """Accept only the native protected reconciliation subtype, never arbitrary errors."""
    attempt = doc.get('extraction_attempt')
    proposal = attempt.get('proposal') if type(attempt) is dict else None
    if (type(proposal) is not dict or not _number(doc.get('doc_id'), positive=True)
            or doc.get('parser_id') not in ('oag_blue_book', 'oag_county_audit')
            or doc.get('extraction_outcome') != 'pending'):
        return None
    identity = doc['doc_id']
    if (proposal.get('document_id') != identity or type(proposal.get('document_id')) is not int
            or attempt.get('status') != 'partial'
            or not _hex(proposal.get('source_sha256'), 64)
            or attempt.get('source_sha256') != proposal['source_sha256']
            or not _hex(proposal.get('candidate_sha256'), 64)
            or not _hex(proposal.get('previous_sha256'), 64)):
        return None
    for key in ('retire_ids', 'update_ids'):
        values = proposal.get(key)
        if (type(values) is not list or len(values) > 100000
                or any(not _number(n, positive=True) for n in values)
                or len(set(values)) != len(values)):
            return None
    retired, revised = len(proposal['retire_ids']), len(proposal['update_ids'])
    if retired + revised == 0:
        return None
    message = (f'document {identity}: reconciliation review required; {retired} retirements, '
               f'{revised} revisions; published evidence preserved')
    if attempt.get('error') != 'ReconciliationRequired: ' + message:
        return None
    return ({'document_id': identity, 'source_sha256': proposal['source_sha256'],
             'candidate_sha256': proposal['candidate_sha256'], 'previous_sha256': proposal['previous_sha256'],
             'retirements': retired, 'revisions': revised}, f'extract failed for doc {identity}: {message}')


def _audit_holds(job):
    meta = job.meta
    docs = meta.get('documents')
    completion = meta.get('refresh_completion')
    if (type(docs) is not list or not 1 <= len(docs) <= 2000 or type(completion) is not dict
            or completion.get('complete') is not False or completion.get('deferred') is not False):
        return None
    held, accepted, errors, seen = [], [], [], set()
    for doc in docs:
        if (type(doc) is not dict or not _number(doc.get('doc_id'), positive=True)
                or doc['doc_id'] in seen):
            return None
        seen.add(doc['doc_id'])
        if 'extraction_attempt' in doc:
            outcome = _held_document(doc)
            if outcome is None:
                return None
            held.append(outcome[0]); errors.append(outcome[1])
        else:
            accepted.append(doc)
    if (not 1 <= len(held) <= 16 or type(completion.get('errors')) is not int or completion['errors'] != len(errors)
            or job.errors != errors):
        return None
    adjusted = dict(completion, complete=True, errors=0)
    if not audit_inventory_complete(dict(meta, documents=accepted), adjusted, job.items_processed):
        return None
    return held


def _fiscal_gap(job):
    """The native fiscal writer and source-component partition must agree."""
    completion = job.meta.get('refresh_completion')
    components = job.meta.get('refresh_components')
    if (type(completion) is not dict or completion.get('complete') is not False
            or type(components) is not dict or job.meta.get('source_mode') != 'partial'
            or job.meta.get('source_fallback_reason') != 'fiscal_components_incomplete'
            or getattr(job.status, 'value', job.status) != 'completed' or job.errors
            or accepted_records(job.items_processed, job.items_created, job.items_updated) != job.items_processed
            or type(completion.get('accepted_records')) is not int
            or completion['accepted_records'] != job.items_processed):
        return False
    years = completion.get('accepted_years')
    if (type(years) is not list or len(years) != job.items_processed or not years
            or any(type(y) is not str or not re.fullmatch(r'FY 20[0-9]{2}/[0-9]{2}', y)
                   or (int(y[3:7])+1) % 100 != int(y[-2:]) for y in years)
            or len(set(years)) != len(years)):
        return False
    for key in ('budget', 'revenue', 'framework'):
        if type(components.get(key)) is not dict or components[key].get('state') not in ('live', 'partial', 'unavailable'):
            return False
    revenue, framework = components['revenue'], components['framework']
    refreshed, missing = revenue.get('refreshed_years'), revenue.get('missing_years')
    if (any(type(v) is not list or any(type(y) is not str or y not in years for y in v)
            or len(set(v)) != len(v) for v in (refreshed, missing))
            or set(refreshed) & set(missing) or set(refreshed) | set(missing) != set(years)
            or revenue['state'] != ('live' if not missing else 'partial' if refreshed else 'unavailable')):
        return False
    unreadable, gaps = framework.get('unreadable_editions'), framework.get('unconfirmed_years')
    if (type(unreadable) is not dict or type(gaps) is not dict or len(unreadable) > 100 or len(gaps) > len(years)
            or any(type(k) is not str or not 1 <= len(k) <= 2048 or type(v) is not str or not 1 <= len(v) <= 256
                   for k, v in unreadable.items())
            or any(type(k) is not str or k not in years or type(v) is not str or not 1 <= len(v) <= 256
                   for k, v in gaps.items())
            or framework['state'] == 'live' and (unreadable or gaps)
            or fiscal_components_complete(components, years)):
        return False
    return True


def classify(jobs, plan, context):
    """Unknown/malformed execution is unsafe; required coverage remains independently red."""
    validate_plan(plan)
    reasons = []
    identity = plan_identity(plan)
    sha = context.get('source_sha')
    if (not _hex(sha, 40) or context.get('admitted_sha') != sha
            or context.get('planned_sha') != sha or context.get('schema_head') != SCHEMA_HEAD
            or context.get('planned_identity') != identity):
        reasons.append('identity_refused')
    if (context.get('prior_success') != 'true' or context.get('cli_outcome') != 'success'
            or context.get('cli_executed') != 'true' or context.get('cli_exit') != '0'):
        reasons.append('execution_unverified')
    floor = context.get('floor')
    started, finished = context.get('cli_started'), context.get('cli_finished')
    try:
        started = datetime.strptime(started, '%Y-%m-%dT%H:%M:%SZ')
        finished = datetime.strptime(finished, '%Y-%m-%dT%H:%M:%SZ')
        if finished < started:
            raise ValueError('reversed execution window')
    except (TypeError, ValueError):
        reasons.append('execution_window_refused'); started = finished = None
    if (type(context.get('run_id')) is not str or not re.fullmatch(r'[1-9][0-9]{0,17}', context['run_id'])
            or type(context.get('run_attempt')) is not str or not re.fullmatch(r'[1-9][0-9]{0,4}', context['run_attempt'])
            or context.get('cli_run_id') != context.get('run_id')
            or context.get('cli_run_attempt') != context.get('run_attempt')
            or context.get('cli_floor') != str(floor)):
        reasons.append('execution_identity_refused')
    if not _number(floor):
        reasons.append('boundary_refused')
    if type(jobs) is not list or not 1 <= len(jobs) <= MAX_JOBS:
        reasons.append('inventory_refused')
        jobs = []
    domains, ids, rows = [], [], []
    for job in jobs:
        domain, job_id = job.domain, job.id
        # Never put unknown domain strings in the bounded report.
        if domain not in plan.domains or not _number(job_id, positive=True) or not _number(floor) or job_id <= floor:
            reasons.append('job_identity_refused'); continue
        domains.append(domain); ids.append(job_id)
        meta = job.meta
        counts = (job.items_processed, job.items_created, job.items_updated)
        result = getattr(job.status, 'value', job.status)
        if (type(meta) is not dict or type(job.errors) is not list
                or any(type(e) is not str for e in job.errors) or len(job.errors) > 2000
                or any(not _number(n) for n in counts) or counts[0] <= 0
                or counts[1] + counts[2] > counts[0]
                or job.dry_run is not plan.dry_run
                or result not in ('completed', 'completed_with_errors')
                or not isinstance(job.started_at, datetime) or not isinstance(job.finished_at, datetime)
                or job.finished_at < job.started_at
                or started is None or finished is None
                or job.started_at.replace(tzinfo=None) < started
                or job.finished_at.replace(tzinfo=None) >= finished.replace(microsecond=999999)):
            reasons.append('job_result_refused'); continue
        execution = meta.get('execution_plan')
        if (type(execution) is not dict or execution.get('planned_domains') != list(plan.domains)
                or type(execution.get('execution_order')) is not list
                or len(execution['execution_order']) != len(plan.domains)
                or any(type(d) is not str for d in execution['execution_order'])
                or set(execution['execution_order']) != set(plan.domains)):
            reasons.append('job_plan_refused')
        mode = meta.get('source_mode')
        nonpublisher = domain == 'learning_hub' and mode == 'fixture' and meta.get('source_fallback_reason') == 'no_live_source'
        held = []
        if nonpublisher:
            expected = ['served from fixture, not the publisher (reason=no_live_source)']
            if result != 'completed_with_errors' or job.errors != expected:
                reasons.append('job_errors_refused')
        elif domain == 'audits' and result == 'completed_with_errors' and mode == 'partial':
            held = _audit_holds(job)
            if held is None or meta.get('source_fallback_reason') != 'audit_refresh_incomplete':
                reasons.append('job_errors_refused'); held = []
        elif result != 'completed' or job.errors:
            reasons.append('job_errors_refused')
        if type(mode) is not str or mode not in ('live', 'partial') and not nonpublisher:
            reasons.append('source_mode_refused')
        completion = meta.get('refresh_completion')
        required = domain in REQUIRED_DOMAINS
        required_state = 'not_required'
        if required:
            if type(completion) is not dict or type(completion.get('complete')) is not bool:
                reasons.append('completion_unknown'); required_state = 'unknown'
            else:
                required_state = 'incomplete' if required_refresh_failures([job], dry_run=plan.dry_run) else 'complete'
                # False claims of complete coverage are malformed, not the known subtype.
                if completion['complete'] and required_state != 'complete':
                    reasons.append('completion_inconsistent')
                if required_state == 'incomplete' and not held and not (domain == 'fiscal_summary' and _fiscal_gap(job)):
                    reasons.append('incomplete_subtype_unknown')
        from services.receipt_retention import safe_retention_summary
        retention = safe_retention_summary(meta.get('receipt_retention'))
        docs = meta.get('documents')
        doc_count = len(docs) if type(docs) is list and len(docs) <= 2000 else None
        accepted_docs = completion.get('accepted_documents') if type(completion) is dict else None
        if not _number(accepted_docs): accepted_docs = None
        rows.append({'domain': domain, 'job_id': job_id, 'status': result, 'source_mode': mode if type(mode) is str and mode in ('live','partial','fixture') else 'unknown',
                     'processed': counts[0], 'created': counts[1], 'updated': counts[2], 'error_count': len(job.errors),
                     'required_completion': required_state, 'document_count': doc_count,
                     'accepted_documents': accepted_docs, 'held_proposals': held, 'retention': retention})
    if (len(domains) != len(plan.domains) or len(set(domains)) != len(domains)
            or set(domains) != set(plan.domains) or len(set(ids)) != len(ids)):
        reasons.append('selected_inventory_mismatch')
    incomplete = any(row['required_completion'] == 'incomplete' for row in rows)
    classification = 'unsafe' if reasons else ('required_source_incomplete' if incomplete else 'complete')
    return {'version': 1, 'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'source_sha': sha if _hex(sha, 40) else None,
            'schema_head': SCHEMA_HEAD if context.get('schema_head') == SCHEMA_HEAD else None,
            'plan_sha256': identity, 'selected_domains': list(plan.domains), 'dry_run': plan.dry_run,
            'bootstrap_selected': plan.bootstrap, 'job_floor': floor if _number(floor) else None,
            'run_id': context.get('run_id') if 'execution_identity_refused' not in reasons else None,
            'run_attempt': context.get('run_attempt') if 'execution_identity_refused' not in reasons else None,
            'cli_executed': context.get('cli_executed') == 'true', 'cli_exit_zero': context.get('cli_exit') == '0',
            'cli_exit': int(context['cli_exit']) if type(context.get('cli_exit')) is str and re.fullmatch(r'[0-9]{1,3}', context['cli_exit']) and int(context['cli_exit']) <= 255 else None,
            'classification': classification, 'cache_eligible': not reasons and not plan.dry_run,
            'refusals': sorted(set(reasons)), 'jobs': rows}


def environment_context():
    raw_floor = os.environ.get('SEED_JOB_FLOOR', '')
    return {'floor': int(raw_floor) if re.fullmatch(r'[0-9]{1,18}', raw_floor) else None,
            **{key: os.environ.get(env) for key, env in {
                'source_sha': 'GITHUB_SHA', 'admitted_sha': 'SEED_ADMITTED_SHA', 'planned_sha': 'SEED_PLANNED_SHA',
                'schema_head': 'SEED_SCHEMA_HEAD', 'planned_identity': 'SEED_PLANNED_IDENTITY',
                'prior_success': 'SEED_PRIOR_SUCCESS', 'cli_outcome': 'SEED_CLI_OUTCOME',
                'cli_executed': 'SEED_CLI_EXECUTED', 'cli_exit': 'SEED_CLI_EXIT',
                'run_id': 'GITHUB_RUN_ID', 'run_attempt': 'GITHUB_RUN_ATTEMPT',
                'cli_run_id': 'SEED_CLI_RUN_ID', 'cli_run_attempt': 'SEED_CLI_RUN_ATTEMPT',
                'cli_floor': 'SEED_CLI_FLOOR', 'cli_started': 'SEED_CLI_STARTED', 'cli_finished': 'SEED_CLI_FINISHED'}.items()}}


def publish(report):
    """Only typed/projection output crosses the Actions/notification boundary."""
    values = {'report': json.dumps(report, separators=(',', ':')), 'report_version': '1',
              'cache_eligible': str(report['cache_eligible']).lower(), 'classification': report['classification'],
              'source_sha': report['source_sha'] or '', 'schema_head': report['schema_head'] or '',
              'plan_sha256': report['plan_sha256']}
    if len(values['report'].encode('utf-8')) > 60000:
        raise ValueError('Current-run report exceeds bounded output')
    print('CURRENT_RUN_REPORT_V1 ' + values['report'])
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            stream.writelines(f'{key}={value}\n' for key, value in values.items())
    print('Current-run classification: ' + report['classification'] + '; cache_eligible=' + values['cache_eligible'])


def main():
    plan = environment_plan()
    if not _hex(os.environ.get('GITHUB_SHA'), 40):
        raise SystemExit('Current source identity refused')
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write('plan_sha256=' + plan_identity(plan) + '\n')
        output.write('source_sha=' + os.environ['GITHUB_SHA'] + '\n')
        output.write('dry_run=' + str(plan.dry_run).lower() + '\n')


if __name__ == '__main__':
    main()
