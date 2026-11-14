"""Fail-closed cache eligibility and bounded diagnostics for one native run.

This does not relax required_refresh_failures or grant source authority. It is
consumed only after actual CLI execution; database integrity/bootstrap are
separate direct Actions dependencies. All projected strings have closed vocabularies.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from .source_plan import environment_plan, validate_plan
from .refresh_completion import REQUIRED_DOMAINS, accepted_records, fiscal_components_complete, audit_inventory_complete, required_refresh_failures

SCHEMA_HEAD = 'a756b20a0001'
MAX_JOBS = 18
PRIOR_STEPS = frozenset(('checkout', 'python', 'ocr', 'setup_python', 'dependencies', 'writer_tls',
    'database', 'pdf_cache_period', 'restore_pdfs', 'native_boundary', 'cli',
    'pdf_cache_state', 'save_pdfs'))


def prior_steps_success(steps, job_status, plan):
    """Check actual outcomes too: continued failures have conclusion=success.

    job.status covers the runner's aggregate state; the exact identified-step
    inventory makes a failed-but-continued action visible. Only the conditional
    restore/save steps may be skipped. This witness grants no source acceptance.
    """
    validate_plan(plan)
    if job_status != 'success' or type(steps) is not dict or set(steps) != PRIOR_STEPS:
        return False
    for name, step in steps.items():
        if type(step) is not dict or type(step.get('outputs')) is not dict:
            return False
        pair = (step.get('outcome'), step.get('conclusion'))
        if pair == ('success', 'success'):
            continue
        allowed_skip = name == 'save_pdfs' or (name == 'restore_pdfs' and
            (plan.reacquire_pending_pdf or bool(plan.audits_source_acceptance)))
        if not allowed_skip or pair != ('skipped', 'skipped'):
            return False
    return True


def plan_identity(plan):
    validate_plan(plan)
    return hashlib.sha256(json.dumps(asdict(plan), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _hex(value, length):
    return type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is not None


def _number(value, *, positive=False):
    return type(value) is int and (1 if positive else 0) <= value <= 2**53 - 1


def source_diagnostics(job):
    """Closed diagnostic projection for delivered CoG/debt metadata.

    Missing legacy metadata is explicitly unverified. A present malformed or
    contradictory contract refuses cache eligibility. This never supplies
    financial values, original source authority or publication permission.
    """
    if job.domain not in ('county_officials','debt_timeline'):
        return None, True
    output={'version':1,'generated_by':'backend/seeding/current_run.py',
        'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'source_sha':os.environ.get('GITHUB_SHA') if _hex(os.environ.get('GITHUB_SHA'),40) else None,
        'domain':job.domain,'job_id':job.id if _number(job.id,positive=True) else None,
        'scope':'diagnostic_schema_only','source_acceptance':False,
        'validation':'legacy_unverified'}
    meta=job.meta if type(job.meta) is dict else {}
    key='source_status' if job.domain=='county_officials' else 'year_coverage'
    def refused():
        output['validation']='refused'
        return output,False
    if type(job.meta) is not dict:return refused()
    if key not in meta:return output, True
    value=meta[key]
    if type(value) is not dict:return refused()
    if key=='source_status':
        state=value.get('state')
        if value.get('fixture_used') is not False:return refused()
        if state=='unavailable':
            if set(value)!={'state','fixture_used','stored_governors_retained','dated_stored_governors','oldest_age_seconds','newest_age_seconds'}:
                return refused()
            count,dated=value['stored_governors_retained'],value['dated_stored_governors']
            old,new=value['oldest_age_seconds'],value['newest_age_seconds']
            if (not _number(count) or count>47 or not _number(dated) or dated>count
                    or any(type(getattr(job,k,None)) is not int or getattr(job,k)!=0
                           for k in ('items_processed','items_created','items_updated'))):return refused()
            if dated==0:
                if old is not None or new is not None:return refused()
            elif (any(type(age) not in (int,float) or not math.isfinite(age) or not 0<=age<=2**53-1 for age in (old,new))
                    or new>old):return refused()
        elif state in ('live','partial'):
            if (set(value)!={'state','fixture_used','governors_observed','deputies_state'}
                    or type(value.get('governors_observed')) is not int or value['governors_observed']!=47
                    or value.get('deputies_state')!=('live' if state=='live' else 'unavailable')
                    or meta.get('source_mode')!=state
                    or type(job.items_processed) is not int or job.items_processed!=47):return refused()
        else:return refused()
        output['source_status']=dict(value)
    else:
        base_fields={'contract','years','note'}
        requirement_fields={'required_stock_years','required_gdp_years','unpublished_gdp_years'}
        with_requirements=set(value)==base_fields|requirement_fields
        if (set(value) not in (base_fields,base_fields|requirement_fields)
                or value.get('contract')!='debt-calendar-observation-coverage-v1'
                or type(value.get('note')) is not str or len(value['note'])>1024
                or type(value.get('years')) is not list or not 1<=len(value['years'])<=200):return refused()
        current_year=datetime.now(timezone.utc).year
        projected=[];seen=set()
        states={'observed_this_run','observed_unretained','retained_qualified','unqualified'}
        measure_fields={'state','absence_reason','period','period_kind','stock_as_of_month','unit','basis',
                        'source_url','source_digest','acquired_at','locator','publication_date','vintage_date'}
        if with_requirements:measure_fields|={'required','publication_requirement'}
        for row in value['years']:
            if type(row) is not dict or set(row)!={'year','measures','ratio'}:return refused()
            year=row['year'];measures=row['measures'];ratio=row['ratio']
            if (type(year) is not int or not 1900<=year<=datetime.now(timezone.utc).year or year in seen
                    or type(measures) is not dict or set(measures)!={'external','domestic','total','gdp'}
                    or type(ratio) is not dict or set(ratio)!={'state','stock_as_of_month','gdp_calendar_year','year_end_stock','reason'}):return refused()
            seen.add(year);parts={}
            for name,part in measures.items():
                if (type(part) is not dict or set(part)!=measure_fields or type(part.get('state')) is not str or part['state'] not in states
                        or part.get('period')!=str(year) or part.get('unit')!='KES'
                        or part.get('basis')!=('current_prices' if name=='gdp' else 'actual')
                        or part.get('period_kind')!=('calendar_year' if name=='gdp' else 'latest_observed_month_in_calendar_year')
                        or part.get('publication_date') is not None or part.get('vintage_date') is not None):return refused()
                if with_requirements:
                    required=not (name=='gdp' and year>=current_year)
                    if (type(part['required']) is not bool or part['required'] is not required
                            or part['publication_requirement']!=('required_published_period' if required else 'annual_period_not_ended')):
                        return refused()
                month=part.get('stock_as_of_month')
                if month is not None and (type(month) is not str or not re.fullmatch(str(year)+r'-(0[1-9]|1[0-2])',month)):return refused()
                if name=='gdp' and month is not None:return refused()
                if part['source_digest'] is not None and not _hex(part['source_digest'],64):return refused()
                url, timestamp, locator = part['source_url'], part['acquired_at'], part['locator']
                if url is not None:
                    if type(url) is not str or len(url)>2048:return refused()
                    try:
                        parsed=urlsplit(url)
                        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:return refused()
                    except ValueError:return refused()
                if timestamp is not None:
                    if type(timestamp) is not str or len(timestamp)>64:return refused()
                    try:
                        acquired=datetime.fromisoformat(timestamp.replace('Z','+00:00'))
                        if acquired.tzinfo is None:return refused()
                    except ValueError:return refused()
                if locator is not None:
                    if type(locator) is not dict:return refused()
                    try:
                        if len(json.dumps(locator,allow_nan=False))>16384:return refused()
                    except (ValueError,TypeError,RecursionError):return refused()
                if part['state']!='unqualified' and (not _hex(part['source_digest'],64)
                        or url is None or timestamp is None or not locator):return refused()
                reason=part.get('absence_reason')
                if reason not in (None,'annual_period_not_ended','not_observed_in_selected_source'):return refused()
                if part['state']=='unqualified' and reason is None or part['state']!='unqualified' and reason is not None:return refused()
                parts[name]={'state':part['state'],'absence_reason':reason,'stock_as_of_month':month,
                             'publication_date':None,'vintage_date':None}
            month=ratio['stock_as_of_month']
            if (ratio['state'] not in ('qualified_derived_pair','unavailable') or type(ratio['gdp_calendar_year']) is not int
                    or ratio['gdp_calendar_year']!=year or type(ratio['year_end_stock']) is not bool
                    or month!=parts['total']['stock_as_of_month'] or ratio['year_end_stock']!=(month==f'{year}-12')
                    or ratio['reason']!=(None if ratio['state']=='qualified_derived_pair' else 'stock_denominator_pair_unqualified')):return refused()
            if ratio['state']=='qualified_derived_pair' and any(parts[m]['state'] not in ('observed_this_run','retained_qualified') for m in ('total','gdp')):return refused()
            projected.append({'year':year,'measures':parts,'ratio':dict(ratio)})
        if with_requirements:
            expected_requirements={
                'required_stock_years':sorted(seen),
                'required_gdp_years':sorted(year for year in seen if year<current_year),
                'unpublished_gdp_years':sorted(year for year in seen if year>=current_year),
            }
            for name,expected in expected_requirements.items():
                years=value[name]
                if type(years) is not list or any(type(year) is not int for year in years) or years!=expected:
                    return refused()
        output['year_coverage']={'contract':value['contract'],'years':sorted(projected,key=lambda r:r['year'])}
    output['validation']='valid'
    return output,True


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


def load_current_jobs(session, floor):
    """Read jobs and their timestamps in the same snapshot as each other."""
    from sqlalchemy import func, select
    from models import IngestionJob

    fields = [IngestionJob]
    postgres = session.get_bind().dialect.name == 'postgresql'
    if postgres:
        # As in the ownership check, PostgreSQL stores these columns in the
        # session time zone. Recover the original instants before comparing
        # them with the UTC workflow timestamps.
        time_zone = func.current_setting('TimeZone')
        fields.extend(func.timezone(time_zone, timestamp) for timestamp
                      in (IngestionJob.started_at, IngestionJob.finished_at))
    query = (select(*fields).where(IngestionJob.id > floor)
             .order_by(IngestionJob.id.desc()).limit(MAX_JOBS + 1)
             .execution_options(populate_existing=True))
    rows = session.execute(query).all()
    jobs = [row[0] for row in rows]
    times = {job.id: (start, end) for job, start, end in rows} if postgres else None
    return jobs, times


def _within_cli_window(job, started, finished, job_times):
    times = (job.started_at, job.finished_at) if job_times is None else job_times.get(job.id)
    if times is None or started is None or finished is None:
        return False
    start, end = times
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        return False

    def utc_naive(value):
        if value.utcoffset() is not None:
            value = value.astimezone(timezone.utc)
        return value.replace(tzinfo=None)

    return started <= utc_naive(start) <= utc_naive(end) < finished.replace(microsecond=999999)


def classify(jobs, plan, context, *, job_times=None):
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
    if not prior_steps_success(context.get('prior_steps'), context.get('prior_job_status'), plan):
        reasons.append('prior_steps_unverified')
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
                or not _within_cli_window(job, started, finished, job_times)):
            reasons.append('job_result_refused'); continue
        if not source_diagnostics(job)[1]:
            reasons.append('source_diagnostic_refused')
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
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate step-context key')
            result[key] = value
        return result
    try:
        raw = os.environ.get('SEED_PRIOR_STEPS', '')
        steps = json.loads(raw, object_pairs_hook=unique_pairs) if len(raw.encode()) <= 65536 else None
    except (TypeError, ValueError):
        steps = None
    return {'floor': int(raw_floor) if re.fullmatch(r'[0-9]{1,18}', raw_floor) else None,
            'prior_steps': steps, 'prior_job_status': os.environ.get('SEED_PRIOR_JOB_STATUS'),
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
    print('Current-run classification: ' + report['classification'] + '; cache_eligible=' + values['cache_eligible'])
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            stream.writelines(f'{key}={value}\n' for key, value in values.items())



def publish_diagnostics(jobs, report, context, *, job_times=None):
    """A separate diagnostic side channel; it never changes refresh eligibility.

    Preserve CoG last-good ages even when its zero-result makes execution unsafe.
    Reduce debt contracts to coverage counts; no financial values cross this
    reporting boundary. Unknown/mismatched execution identity produces no packet.
    """
    if (type(report) is not dict or not _hex(report.get('source_sha'), 40)
            or not _hex(report.get('plan_sha256'), 64) or not _number(report.get('job_floor'))
            or type(report.get('run_id')) is not str or re.fullmatch('[1-9][0-9]{0,17}', report['run_id']) is None
            or type(report.get('run_attempt')) is not str or re.fullmatch('[1-9][0-9]{0,4}', report['run_attempt']) is None
            or any(reason in report.get('refusals', []) for reason in (
                'identity_refused', 'execution_window_refused', 'execution_identity_refused', 'boundary_refused',
                'inventory_refused', 'job_identity_refused', 'selected_inventory_mismatch'))
            or type(jobs) is not list or not 1 <= len(jobs) <= MAX_JOBS):
        return None
    if report.get('cli_executed') is not True or type(context) is not dict:
        return None
    try:
        started = datetime.strptime(context['cli_started'], '%Y-%m-%dT%H:%M:%SZ')
        finished = datetime.strptime(context['cli_finished'], '%Y-%m-%dT%H:%M:%SZ')
        if finished < started or any(not _within_cli_window(job, started, finished, job_times) for job in jobs):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    selected = report.get('selected_domains')
    if (type(selected) is not list or len(jobs) != len(selected)
            or sorted(job.domain for job in jobs) != sorted(selected)
            or len({job.domain for job in jobs}) != len(jobs)
            or len({job.id for job in jobs}) != len(jobs)
            or any(not _number(job.id, positive=True) or job.id <= report['job_floor'] for job in jobs)):
        return None
    rows = []
    for job in jobs:
        diagnostic, _ = source_diagnostics(job)
        if diagnostic is None:
            continue
        row = {key: diagnostic[key] for key in ('domain', 'job_id', 'validation')}
        if diagnostic['validation'] == 'valid':
            if 'source_status' in diagnostic:
                row['source_status'] = diagnostic['source_status']
            elif 'year_coverage' in diagnostic:
                years = diagnostic['year_coverage']['years']
                states = dict.fromkeys(('observed_this_run', 'observed_unretained', 'retained_qualified', 'unqualified'), 0)
                for year in years:
                    for part in year['measures'].values():
                        states[part['state']] += 1
                row['debt_coverage'] = {'years': len(years), 'measures': states,
                    'qualified_ratios': sum(year['ratio']['state'] == 'qualified_derived_pair' for year in years),
                    'unavailable_ratios': sum(year['ratio']['state'] == 'unavailable' for year in years)}
        rows.append(row)
    packet = {'version': 1, 'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        **{key: report[key] for key in ('source_sha', 'plan_sha256', 'run_id', 'run_attempt', 'job_floor')},
        'scope': 'diagnostics_only_not_source_acceptance', 'rows': rows}
    raw = json.dumps(packet, separators=(',', ':'), allow_nan=False)
    if len(raw.encode()) > 16000:
        raise ValueError('Source diagnostics exceed reporting bound')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            stream.write('source_diagnostics=' + raw + '\n')
    return packet


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
