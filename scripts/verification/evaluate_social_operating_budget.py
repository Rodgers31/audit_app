#!/usr/bin/env python3
"""Evaluate explicit, sanitized local operating evidence. No live collection."""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_BYTES = 262_144
TOTAL_DAILY_TARGET = 120_000_000
SOCIAL_MONTHLY_TARGET = 200_000_000
FRESHNESS = timedelta(hours=48)
IDENTITY_KEYS = {'organization_id', 'project_id', 'deployment_sha', 'cycle_start',
                 'cycle_end', 'timezone', 'uncached_allowance_bytes', 'required_reserve_bytes',
                 'database_fingerprint_sha256'}
SERVICES = {'shared_pooler', 'database', 'auth', 'storage', 'other_uncached'}
ACTIVITY_COUNTS = {'api_requests', 'cache_hits', 'cache_misses', 'nightly_runs',
                   'worker_covered_seconds', 'worker_uptime_seconds', 'worker_scans',
                   'worker_heartbeats', 'worker_publications', 'restarts', 'deployments'}
TRAFFIC_COUNTS = ('worker_scans', 'worker_heartbeats', 'worker_publications')
PERIOD_KEYS = {'period_start', 'period_end'}


class EvidenceError(ValueError):
    """Codes contain no caller values, filenames or underlying exceptions."""


def require(condition, code):
    if not condition:
        raise EvidenceError(code)


def shape(value, keys):
    require(type(value) is dict and set(value) == set(keys), 'INVALID_SHAPE')
    return value


def integer(value, maximum=10**15):
    require(type(value) is int and 0 <= value <= maximum, 'INVALID_INTEGER')
    return value


def label(value):
    require(type(value) is str and re.fullmatch(r'[A-Za-z0-9_.:-]{1,80}', value), 'INVALID_LABEL')
    return value


def digest(value, size=64):
    require(type(value) is str and re.fullmatch(r'[0-9a-f]{%d}' % size, value), 'INVALID_HASH')
    return value


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                          allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, OverflowError):
        raise EvidenceError('INVALID_JSON') from None


def content_hash(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def instant(value):
    require(type(value) is str and re.fullmatch(
        r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})', value),
        'INVALID_TIMESTAMP')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(result.utcoffset() is not None, 'INVALID_TIMESTAMP')
        return result.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise EvidenceError('INVALID_TIMESTAMP') from None


def civil_date(value):
    require(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value), 'INVALID_DATE')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise EvidenceError('INVALID_DATE') from None


def identity(value):
    shape(value, IDENTITY_KEYS)
    label(value['organization_id']); label(value['project_id']); digest(value['deployment_sha'], 40)
    digest(value['database_fingerprint_sha256'])
    start, end = civil_date(value['cycle_start']), civil_date(value['cycle_end'])
    require(1 <= (end - start).days <= 366, 'INVALID_CYCLE')
    require(type(value['timezone']) is str and len(value['timezone']) <= 64, 'INVALID_TIMEZONE')
    try:
        zone = ZoneInfo(value['timezone'])
    except (ZoneInfoNotFoundError, ValueError):
        raise EvidenceError('INVALID_TIMEZONE') from None
    quota = integer(value['uncached_allowance_bytes'])
    reserve = integer(value['required_reserve_bytes'])
    require(quota > reserve > 0, 'INVALID_RESERVE')
    return start, end, zone


def amount(value):
    """Inclusive conservative byte interval; MB/GB are decimal provider units."""
    shape(value, {'value', 'unit', 'rounding', 'resolution'})
    require(value['unit'] in ('B', 'MB', 'GB'), 'INVALID_UNIT')
    numbers = []
    for key in ('value', 'resolution'):
        raw = value[key]
        require(type(raw) is int or (type(raw) is str and re.fullmatch(r'\d{1,16}(?:\.\d{1,9})?', raw)), 'INVALID_AMOUNT')
        try:
            number = Decimal(raw)
        except (InvalidOperation, ValueError):
            raise EvidenceError('INVALID_AMOUNT') from None
        require(number.is_finite() and 0 <= number <= 10**15, 'INVALID_AMOUNT')
        numbers.append(number)
    reported, resolution = numbers
    mode = value['rounding']
    require(mode in ('exact', 'nearest', 'up', 'down'), 'INVALID_ROUNDING')
    require((mode == 'exact') == (resolution == 0), 'INVALID_RESOLUTION')
    scale = {'B': 1, 'MB': 1_000_000, 'GB': 1_000_000_000}[value['unit']]
    lower = reported - (resolution / 2 if mode == 'nearest' else resolution if mode == 'up' else 0)
    upper = reported + (resolution / 2 if mode == 'nearest' else resolution if mode == 'down' else 0)
    require(upper * scale <= 10**15, 'INVALID_AMOUNT')
    return max(Decimal(0), lower) * scale, upper * scale


def receipt(section, kinds, binding, synthetic, end, as_of, period=None):
    if period is not None:
        require((instant(section['period_start']), instant(section['period_end'])) == period,
                'RECEIPT_PERIOD_MISMATCH')
    evidence = shape(section['receipt'], {'kind', 'identity_sha256', 'source_sha256',
        'payload_sha256', 'captured_at', 'observer', 'synthetic'})
    require(evidence['kind'] in kinds, 'WRONG_EVIDENCE_KIND')
    label(evidence['observer'])
    require(synthetic or not evidence['observer'].upper().startswith('SYNTHETIC-'), 'SYNTHETIC_MARKERS_REMAIN')
    digest(evidence['source_sha256']); digest(evidence['payload_sha256']); digest(evidence['identity_sha256'])
    require(evidence['identity_sha256'] == binding, 'RECEIPT_IDENTITY_MISMATCH')
    require(evidence['payload_sha256'] == content_hash({k: v for k, v in section.items() if k != 'receipt'}), 'RECEIPT_PAYLOAD_MISMATCH')
    require(type(evidence['synthetic']) is bool and evidence['synthetic'] == synthetic, 'SYNTHETIC_IDENTITY_MISMATCH')
    captured = instant(evidence['captured_at'])
    require(end <= captured <= as_of, 'RECEIPT_TIME_MISMATCH')


def ceiling(value):
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def _evaluate(packet, expected, as_of, report):
    shape(packet, {'schema_version', 'synthetic', 'identity', 'representative', 'days',
                   'hosting', 'future_increments', 'query_counters', 'cycle_usage', 'cycle_social'})
    require(type(packet['schema_version']) is int and packet['schema_version'] == 1, 'INVALID_VERSION')
    require(type(packet['synthetic']) is bool and type(packet['representative']) is bool, 'INVALID_BOOLEAN')
    start, end, zone = identity(expected)
    identity(packet['identity'])
    require(packet['identity'] == expected, 'IDENTITY_MISMATCH')
    require(type(as_of) is datetime and as_of.utcoffset() is not None, 'INVALID_AS_OF')
    as_of = as_of.astimezone(timezone.utc)
    cycle_start = datetime.combine(start, time(), zone).astimezone(timezone.utc)
    cycle_end = datetime.combine(end, time(), zone).astimezone(timezone.utc)
    require(cycle_start <= as_of <= cycle_end, 'AS_OF_OUTSIDE_CYCLE')
    binding, synthetic = content_hash(expected), packet['synthetic']
    report.update({'synthetic': synthetic, 'identity': expected, 'evaluation_as_of': as_of.isoformat()})
    unknowns = report['unknowns']
    if synthetic: unknowns.append('SYNTHETIC_EVIDENCE')
    if not synthetic and any(value.upper().startswith('SYNTHETIC-') for value in
                             (expected['organization_id'], expected['project_id'])):
        unknowns.append('SYNTHETIC_MARKERS_REMAIN')
    if not packet['representative']: unknowns.append('WORKLOAD_NOT_REPRESENTATIVE')
    days = packet['days']
    require(type(days) is list and 7 <= len(days) <= 31, 'SEVEN_DAYS_REQUIRED')
    dates, totals, total_lowers, social, activities = [], [], [], [], []
    for day in days:
        shape(day, {'date', 'deployment_sha', 'complete', 'provider', 'activity', 'social'})
        current = civil_date(day['date'])
        require(start <= current < end, 'DAY_OUTSIDE_CYCLE')
        require(day['deployment_sha'] == expected['deployment_sha'], 'DEPLOYMENT_MISMATCH')
        require(type(day['complete']) is bool and day['complete'], 'INCOMPLETE_DAY')
        finish = datetime.combine(current + timedelta(days=1), time(), zone).astimezone(timezone.utc)
        begin = datetime.combine(current, time(), zone).astimezone(timezone.utc)
        require(finish <= as_of, 'DAY_NOT_CLOSED')
        seconds = int((finish - begin).total_seconds())
        provider = shape(day['provider'], {'total_uncached', 'services', 'meter_scope', 'receipt'} | PERIOD_KEYS)
        require(provider['meter_scope'] == 'organization_uncached', 'METER_SCOPE_MISMATCH')
        receipt(provider, {'provider_dashboard'}, binding, synthetic, finish, as_of, (begin, finish))
        lower, upper = amount(provider['total_uncached'])
        shape(provider['services'], SERVICES)
        ranges = [amount(value) for value in provider['services'].values()]
        service_lower = sum((v[0] for v in ranges), Decimal(0))
        service_upper = sum((v[1] for v in ranges), Decimal(0))
        require(service_lower <= upper and lower <= service_upper, 'SERVICE_TOTAL_MISMATCH')
        # A breakdown is not another charge. Use the conservative larger bound.
        totals.append(max(upper, service_upper))
        total_lowers.append(max(lower, service_lower))
        activity = shape(day['activity'], ACTIVITY_COUNTS | {'actions_enabled', 'coverage_complete', 'receipt'} | PERIOD_KEYS)
        receipt(activity, {'runtime_logs'}, binding, synthetic, finish, as_of, (begin, finish))
        for key in ACTIVITY_COUNTS: integer(activity[key])
        for key in ('actions_enabled', 'coverage_complete'): require(type(activity[key]) is bool, 'INVALID_BOOLEAN')
        require(activity['worker_covered_seconds'] <= seconds and activity['worker_uptime_seconds'] <= seconds, 'INVALID_WORKER_DURATION')
        if not activity['coverage_complete']: unknowns.append('INCOMPLETE_ACTIVITY_COVERAGE')
        if not activity['actions_enabled'] or activity['nightly_runs'] == 0: unknowns.append('NIGHTLY_PROFILE_NOT_OBSERVED')
        if activity['worker_covered_seconds'] != seconds or not all(activity[k] > 0 for k in ('worker_uptime_seconds', 'worker_scans', 'worker_heartbeats')):
            unknowns.append('WORKER_PROFILE_NOT_OBSERVED')
        activities.append(activity)
        measured = shape(day['social'], {'measurement', 'transfer', 'receipt', 'direction'} | PERIOD_KEYS)
        require(measured['measurement'] in ('provider_bytes', 'protocol_bytes', 'decoded_estimate', 'cumulative_counter'), 'INVALID_MEASUREMENT')
        require(measured['direction'] == 'database_to_worker', 'SOCIAL_DIRECTION_MISMATCH')
        receipt(measured, {'social_provider_meter', 'social_protocol_measurement'}, binding, synthetic, finish, as_of, (begin, finish))
        require((measured['measurement'] == 'provider_bytes') == (measured['receipt']['kind'] == 'social_provider_meter') or measured['measurement'] in ('decoded_estimate', 'cumulative_counter'), 'MEASUREMENT_KIND_MISMATCH')
        social_upper = amount(measured['transfer'])[1]
        if measured['measurement'] == 'provider_bytes': require(social_upper <= totals[-1], 'SOCIAL_EXCEEDS_TOTAL')
        if measured['measurement'] == 'protocol_bytes' and social_upper == 0 and any(activity[k] for k in TRAFFIC_COUNTS):
            unknowns.append('PROTOCOL_TRANSFER_CONTRADICTS_ACTIVITY')
        if measured['measurement'] not in ('provider_bytes', 'protocol_bytes'): unknowns.append('SOCIAL_TRANSFER_NOT_MEASURED')
        social.append(social_upper)
        dates.append(current)
    require(all(b == a + timedelta(days=1) for a, b in zip(dates, dates[1:])), 'DAYS_NOT_CONSECUTIVE')
    window_start = datetime.combine(dates[0], time(), zone).astimezone(timezone.utc)
    window_end = datetime.combine(dates[-1] + timedelta(days=1), time(), zone).astimezone(timezone.utc)
    require(as_of - window_end <= FRESHNESS, 'STALE_WINDOW')
    accrued = shape(packet['cycle_usage'], {'total_uncached', 'meter_scope', 'receipt'} | PERIOD_KEYS)
    require(accrued['meter_scope'] == 'organization_uncached', 'METER_SCOPE_MISMATCH')
    receipt(accrued, {'provider_dashboard'}, binding, synthetic, as_of, as_of, (cycle_start, as_of))
    accrued_upper = amount(accrued['total_uncached'])[1]
    require(accrued_upper >= sum(total_lowers, Decimal(0)), 'ACCRUED_USAGE_CONTRADICTS_DAYS')
    accrued_social = shape(packet['cycle_social'], {'measurement', 'direction', 'transfer', 'receipt'} | PERIOD_KEYS)
    require(accrued_social['direction'] == 'database_to_worker', 'SOCIAL_DIRECTION_MISMATCH')
    require(accrued_social['measurement'] in ('provider_bytes', 'protocol_bytes', 'decoded_estimate', 'cumulative_counter'), 'INVALID_MEASUREMENT')
    receipt(accrued_social, {'social_provider_meter', 'social_protocol_measurement'}, binding, synthetic, as_of, as_of, (cycle_start, as_of))
    require((accrued_social['measurement'] == 'provider_bytes') == (accrued_social['receipt']['kind'] == 'social_provider_meter') or accrued_social['measurement'] in ('decoded_estimate', 'cumulative_counter'), 'MEASUREMENT_KIND_MISMATCH')
    social_accrued_upper = amount(accrued_social['transfer'])[1]
    if accrued_social['measurement'] == 'protocol_bytes' and social_accrued_upper == 0 and any(a[k] for a in activities for k in TRAFFIC_COUNTS):
        unknowns.append('PROTOCOL_TRANSFER_CONTRADICTS_ACTIVITY')
    social_basis = days[0]['social']['measurement']
    require(all(day['social']['measurement'] == social_basis for day in days)
            and accrued_social['measurement'] == social_basis, 'SOCIAL_MEASUREMENT_SCOPE_MISMATCH')
    require(social_accrued_upper >= sum((amount(day['social']['transfer'])[0] for day in days), Decimal(0)), 'ACCRUED_SOCIAL_CONTRADICTS_DAYS')
    if social_basis == 'provider_bytes': require(social_accrued_upper <= accrued_upper, 'ACCRUED_SOCIAL_CONTRADICTS_DAYS')
    if accrued_social['measurement'] not in ('provider_bytes', 'protocol_bytes'): unknowns.append('SOCIAL_TRANSFER_NOT_MEASURED')
    if not all(sum(a[key] for a in activities) > 0 for key in ('api_requests', 'worker_publications', 'deployments')):
        unknowns.append('REPRESENTATIVE_ACTIVITY_MISSING')
    if sum(a['restarts'] for a in activities) == 0: unknowns.append('RESTART_PROFILE_NOT_OBSERVED')
    if sum(a['cache_hits'] + a['cache_misses'] for a in activities) == 0: unknowns.append('CACHE_ACTIVITY_MISSING')
    hosting = shape(packet['hosting'], {'owner', 'always_on', 'cost_accepted', 'deployment_sha',
                                       'deployed_at', 'processes', 'capacity', 'receipt'})
    label(hosting['owner'])
    if not synthetic and hosting['owner'].upper().startswith('SYNTHETIC-'): unknowns.append('SYNTHETIC_MARKERS_REMAIN')
    for key in ('always_on', 'cost_accepted'): require(type(hosting[key]) is bool, 'INVALID_BOOLEAN')
    require(hosting['deployment_sha'] == expected['deployment_sha'] and instant(hosting['deployed_at']) <= window_start, 'HOST_DEPLOYMENT_MISMATCH')
    receipt(hosting, {'hosting_readback'}, binding, synthetic, window_end, as_of)
    require(as_of - instant(hosting['receipt']['captured_at']) <= FRESHNESS, 'STALE_HOSTING')
    if not hosting['always_on'] or not hosting['cost_accepted']: unknowns.append('HOSTING_NOT_ACCEPTED')
    capacity = shape(hosting['capacity'], {'limit_kind', 'verified_limit', 'reserved_connections'})
    require(capacity['limit_kind'] in ('pooler_client_connections', 'direct_database_connections'), 'INVALID_CAPACITY_KIND')
    limit = integer(capacity['verified_limit'], 1_000_000)
    reserve = integer(capacity['reserved_connections'], 1_000_000)
    require(limit > 0 and reserve > 0, 'CAPACITY_RESERVE_REQUIRED')
    processes = hosting['processes']
    require(type(processes) is list and len(processes) == 4, 'PROCESS_COVERAGE_REQUIRED')
    roles, demand = set(), 0
    for process in processes:
        shape(process, {'role', 'replicas', 'processes_per_replica', 'pool_size', 'overflow', 'connection_kind'})
        role = process['role']
        require(role in ('web', 'worker', 'etl', 'admin') and role not in roles, 'INVALID_PROCESS_ROLE')
        require(process['connection_kind'] == capacity['limit_kind'], 'CAPACITY_KIND_MISMATCH')
        replicas = integer(process['replicas'], 100)
        count = integer(process['processes_per_replica'], 100)
        pool = integer(process['pool_size'], 1024); overflow = integer(process['overflow'], 1024)
        require((replicas == 0) == (count == 0) and (replicas == 0) == (pool + overflow == 0), 'INVALID_PROCESS_INVENTORY')
        if role in ('web', 'worker'): require(replicas > 0 and count > 0 and pool > 0, 'REQUIRED_PROCESS_MISSING')
        if role == 'web': require(pool == 5 and overflow == 10, 'WEB_POOL_MISMATCH')
        if role == 'worker': require(pool == 2 and overflow == 0, 'WORKER_POOL_MISMATCH')
        demand += replicas * count * (pool + overflow)
        roles.add(role)
    increments = packet['future_increments']
    require(type(increments) is list and len(increments) <= 16, 'INVALID_INCREMENT_COUNT')
    workloads, extra, social_extra, included, included_social = set(), Decimal(0), Decimal(0), Decimal(0), Decimal(0)
    protocol_extra, protocol_included = Decimal(0), Decimal(0)
    for increment in increments:
        shape(increment, {'workload', 'measurement', 'bytes_per_unit', 'remaining_units', 'inclusion', 'receipt'} | PERIOD_KEYS)
        workload = increment['workload']
        require(workload in ('nightly', 'social_worker', 'public_api', 'cache_warmup') and workload not in workloads, 'INCREMENT_OVERLAP')
        require(increment['inclusion'] in ('already_in_provider_total', 'additional_future'), 'INCREMENT_INCLUSION_REQUIRED')
        require(increment['measurement'] in ('provider_bytes', 'protocol_bytes', 'decoded_estimate'), 'INVALID_MEASUREMENT')
        if workload == 'social_worker' and increment['measurement'] != 'decoded_estimate':
            require(increment['measurement'] == social_basis, 'SOCIAL_MEASUREMENT_SCOPE_MISMATCH')
        receipt(increment, {'future_measurement'}, binding, synthetic, window_end, as_of, (window_start, window_end))
        units = integer(increment['remaining_units'], 1_000_000)
        cost = amount(increment['bytes_per_unit'])[1] * units
        if workload == 'social_worker' and increment['measurement'] == 'protocol_bytes' and units > 0 and cost == 0:
            unknowns.append('FUTURE_PROTOCOL_TRANSFER_CONTRADICTS_UNITS')
        if increment['measurement'] == 'decoded_estimate': unknowns.append('FUTURE_TRANSFER_NOT_MEASURED')
        if increment['inclusion'] == 'additional_future':
            extra += cost
            if increment['measurement'] == 'protocol_bytes': protocol_extra += cost
            if workload == 'social_worker': social_extra += cost
        else:
            included += cost
            if increment['measurement'] == 'protocol_bytes': protocol_included += cost
            if workload == 'social_worker': included_social += cost
        workloads.add(workload)
    counters = packet['query_counters']
    if counters is None:
        unknowns.append('QUERY_ATTRIBUTION_UNAVAILABLE')
    else:
        shape(counters, {'kind', 'start_at', 'end_at', 'start_reset', 'end_reset',
                         'before_database_sha256', 'after_database_sha256', 'before_dealloc', 'after_dealloc',
                         'before', 'after', 'receipt'})
        receipt(counters, {'query_stats_snapshots'}, binding, synthetic, instant(counters['end_at']), as_of)
        require(counters['kind'] in ('snapshot_delta', 'cumulative'), 'INVALID_COUNTER_KIND')
        require(digest(counters['before_database_sha256']) == digest(counters['after_database_sha256']) == expected['database_fingerprint_sha256'], 'QUERY_DB_IDENTITY_MISMATCH')
        require(instant(counters['start_at']) <= window_start and instant(counters['end_at']) >= window_end and instant(counters['end_at']) <= as_of, 'COUNTER_WINDOW_MISMATCH')
        require(instant(counters['start_reset']) <= instant(counters['start_at']) and instant(counters['end_reset']) <= instant(counters['end_at']), 'COUNTER_RESET_TIME_INVALID')
        unchanged_dealloc = integer(counters['before_dealloc']) == integer(counters['after_dealloc'])
        snapshots = []
        for key in ('before', 'after'):
            entries = counters[key]
            require(type(entries) is list and 1 <= len(entries) <= 50, 'INVALID_COUNTER_COUNT')
            selected = {}
            for entry in entries:
                shape(entry, {'query_sha256', 'calls', 'rows', 'stats_since'})
                query = digest(entry['query_sha256'])
                require(query not in selected, 'DUPLICATE_QUERY_SHAPE')
                selected[query] = (integer(entry['calls']), integer(entry['rows']), instant(entry['stats_since']))
            snapshots.append(selected)
        before, after = snapshots
        matched = set(before) == set(after)
        monotonic = matched and all(after[key][i] >= before[key][i] for key in before for i in (0, 1))
        unchanged_history = matched and all(before[key][2] == after[key][2] <= instant(counters['start_at']) for key in before)
        valid_delta = (counters['kind'] == 'snapshot_delta' and monotonic and unchanged_dealloc
                       and unchanged_history and instant(counters['start_reset']) == instant(counters['end_reset']))
        report['query_attribution'] = {'available': valid_delta, 'scope': 'SUPPLIED_QUERY_SHAPES_ONLY',
            'authentication': 'UNVERIFIED_OPERATOR_ASSERTIONS',
            'shape_count': len(before),
            'calls_delta': sum(after[key][0] - before[key][0] for key in before) if valid_delta else None,
            'rows_delta': sum(after[key][1] - before[key][1] for key in before) if valid_delta else None,
            'interval_start': counters['start_at'], 'interval_end': counters['end_at']}
        if not valid_delta:
            unknowns.append('QUERY_DELTA_UNVERIFIED')
    total = sum(totals, Decimal(0))
    mean = total / len(days)
    window_seconds = Decimal(int((window_end - window_start).total_seconds()))
    cycle_seconds = int((cycle_end - cycle_start).total_seconds())
    remaining_seconds = Decimal(int((cycle_end - as_of).total_seconds()))
    remaining_total = total * remaining_seconds / window_seconds
    remaining_social = sum(social, Decimal(0)) * remaining_seconds / window_seconds
    require(included <= remaining_total and included_social <= remaining_social, 'INCLUSION_CONTRADICTS_BASELINE')
    cycle_projection = ceiling(accrued_upper + remaining_total + extra)
    social_cycle = ceiling(social_accrued_upper + remaining_social + social_extra)
    report['projection_basis'] = {'total': 'DECLARED_PROVIDER_BASELINE_PLUS_FUTURE_PLANNING_INCREMENTS',
        'social': social_basis, 'protocol_future': 'CONSERVATIVE_PLANNING_PROXY_NOT_BILLED_BYTES'}
    report['measurements'] = {'days': len(days), 'cycle_days': (end - start).days,
        'uncached_upper_bytes': ceiling(total), 'mean_daily_upper_bytes': ceiling(mean),
        'peak_daily_upper_bytes': ceiling(max(totals)),
        'peak_days': [str(d) for d, n in zip(dates, totals) if n == max(totals)],
        'accrued_cycle_upper_bytes': ceiling(accrued_upper), 'accrued_social_upper_bytes': ceiling(social_accrued_upper),
        'cycle_seconds': cycle_seconds,
        'remaining_cycle_seconds': int(remaining_seconds), 'window_seconds': int(window_seconds),
        'additional_future_upper_bytes': ceiling(extra), 'additional_social_upper_bytes': ceiling(social_extra),
        'additional_future_protocol_proxy_upper_bytes': ceiling(protocol_extra),
        'included_future_protocol_proxy_upper_bytes_not_added': ceiling(protocol_included),
        'included_future_upper_bytes_not_added': ceiling(included),
        'cycle_projection_upper_bytes': cycle_projection,
        'remaining_cycle_headroom_bytes': expected['uncached_allowance_bytes'] - cycle_projection,
        'social_cycle_upper_bytes': social_cycle, 'connection_demand': demand,
        'connection_reserve': reserve, 'connection_limit': limit,
        'query_counters_are_billed_bytes': False}
    exceeded = []
    if mean > TOTAL_DAILY_TARGET: exceeded.append('TOTAL_DAILY_TARGET_EXCEEDED')
    if social_cycle > SOCIAL_MONTHLY_TARGET: exceeded.append('SOCIAL_MONTHLY_TARGET_EXCEEDED')
    if cycle_projection + expected['required_reserve_bytes'] > expected['uncached_allowance_bytes']: exceeded.append('CYCLE_RESERVE_EXCEEDED')
    if demand + reserve > limit: exceeded.append('CONNECTION_CAPACITY_EXCEEDED')
    report['exceeded'] = exceeded
    report['unknowns'] = sorted(set(unknowns))
    report['status'] = 'BLOCKED' if unknowns else 'OVER_BUDGET' if exceeded else 'CANDIDATE_FOR_OWNER_REVIEW'


def _report():
    return {'status': 'BLOCKED', 'production_authorized': False, 'synthetic': None,
        'evidence_authentication': 'UNVERIFIED_OPERATOR_ASSERTIONS', 'unknowns': [], 'exceeded': [],
        'generated_by': 'scripts/verification/evaluate_social_operating_budget.py',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'input_sha256': None, 'expected_identity_sha256': None}


def evaluate(packet, *, expected_identity, as_of):
    """Validate declared evidence, never authenticate it or grant authorization."""
    report = _report()
    try:
        raw = canonical(packet)
        require(len(raw) <= MAX_BYTES, 'INPUT_TOO_LARGE')
        report['input_sha256'] = hashlib.sha256(raw).hexdigest()
        require(len(canonical(expected_identity)) <= MAX_BYTES, 'INPUT_TOO_LARGE')
        report['expected_identity_sha256'] = content_hash(expected_identity)
        _evaluate(packet, expected_identity, as_of, report)
    except (EvidenceError, TypeError, KeyError, OverflowError, RecursionError):
        error = sys.exc_info()[1]
        report['status'] = 'BLOCKED'
        report['unknowns'] = sorted(set(report['unknowns'] + [str(error) if isinstance(error, EvidenceError) else 'INVALID_INPUT']))
    return report


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def load_json(path):
    failure = None
    try:
        require(type(path) is str or isinstance(path, Path), 'INVALID_FILE_PATH')
        source = Path(path)
        require(source.suffix == '.json', 'JSON_FILE_REQUIRED')
        descriptor = os.open(source, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'rb') as stream:
            metadata = os.fstat(stream.fileno())
            require(stat.S_ISREG(metadata.st_mode), 'REGULAR_FILE_REQUIRED')
            require(0 < metadata.st_size <= MAX_BYTES, 'INPUT_TOO_LARGE_OR_EMPTY')
            raw = stream.read(MAX_BYTES + 1)
        require(0 < len(raw) <= MAX_BYTES, 'INPUT_TOO_LARGE_OR_EMPTY')
        return json.loads(raw, object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(EvidenceError('NONFINITE_JSON')))
    except EvidenceError as error:
        failure = str(error)
    except (OSError, UnicodeError, ValueError, RecursionError, TypeError):
        failure = 'JSON_READ_FAILED'
    # Raise outside the handler: even exception context cannot retain source
    # bytes, caller filenames or the operating system's original exception.
    raise EvidenceError(failure)


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise EvidenceError('CLI_ARGUMENTS_INVALID')


def main(argv=None):
    try:
        parser = SafeParser(description=__doc__)
        parser.add_argument('--packet', required=True)
        parser.add_argument('--expected-identity', required=True)
        parser.add_argument('--as-of', required=True, help='Explicit timezone-aware evaluation time')
        parser.add_argument('--out', help='Optional new JSON report; existing files are never overwritten')
        args = parser.parse_args(argv)
        packet, expected = load_json(args.packet), load_json(args.expected_identity)
        report = evaluate(packet, expected_identity=expected, as_of=instant(args.as_of))
        if args.out:
            destination = Path(args.out)
            require(destination.suffix == '.json', 'JSON_FILE_REQUIRED')
            require(destination.resolve() not in (Path(args.packet).resolve(), Path(args.expected_identity).resolve()), 'OUTPUT_INPUT_COLLISION')
            with destination.open('x', encoding='utf-8') as stream:
                json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
                stream.write('\n')
            require(load_json(destination) == report, 'OUTPUT_READBACK_FAILED')
        print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
        return 0 if report['status'] == 'CANDIDATE_FOR_OWNER_REVIEW' else 1
    except (EvidenceError, OSError, ValueError, TypeError):
        error = sys.exc_info()[1]
        failure = _report()
        failure['unknowns'] = [str(error) if isinstance(error, EvidenceError) else 'CLI_FAILED']
        print(json.dumps(failure))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
