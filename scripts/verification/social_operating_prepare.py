#!/usr/bin/env python3
"""Prepare partial civil-day coverage or scoped counter deltas; no live I/O or acceptance."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

if __package__:
    from . import evaluate_social_operating_budget as budget
    from . import social_operating_collect as collector
else:
    import evaluate_social_operating_budget as budget
    import social_operating_collect as collector


def _report():
    return {'status': 'BLOCKED', 'production_authorized': False,
            'evidence_authentication': 'UNVERIFIED_OPERATOR_ASSERTIONS',
            'caller_attribution_verified': False, 'provider_meter_authenticated': False,
            'generated_by': 'scripts/verification/social_operating_prepare.py',
            'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'unknowns': []}


def _bounded(value):
    budget.require(len(budget.canonical(value)) <= budget.MAX_BYTES, 'INPUT_TOO_LARGE')


def _aware(value):
    budget.require(type(value) is datetime and value.utcoffset() is not None, 'INVALID_AS_OF')
    return value.astimezone(timezone.utc)


def _day(record, expected, begin, end, as_of):
    budget.shape(record, {'date', 'deployment_sha', 'complete', 'provider', 'activity', 'social'})
    budget.require(record['deployment_sha'] == expected['deployment_sha'], 'DEPLOYMENT_MISMATCH')
    budget.require(type(record['complete']) is bool, 'INVALID_BOOLEAN')
    missing = [] if record['complete'] and end <= as_of else ['DAY_NOT_COMPLETE_AND_CLOSED']
    binding = budget.content_hash(expected)
    ranges = None
    for key in ('provider', 'activity', 'social'):
        section = record[key]
        if section is None:
            missing.append(key.upper() + '_MISSING')
            continue
        if key == 'provider':
            budget.shape(section, {'total_uncached', 'services', 'meter_scope', 'receipt'} | budget.PERIOD_KEYS)
            budget.require(section['meter_scope'] == 'organization_uncached', 'METER_SCOPE_MISMATCH')
            budget.shape(section['services'], budget.SERVICES)
            low, high = budget.amount(section['total_uncached'])
            services = [budget.amount(x) for x in section['services'].values()]
            service_low, service_high = sum(x[0] for x in services), sum(x[1] for x in services)
            budget.require(service_low <= high and low <= service_high, 'SERVICE_TOTAL_MISMATCH')
            ranges = [budget.ceiling(max(low, service_low)), budget.ceiling(max(high, service_high))]
            kinds = {'provider_dashboard'}
        elif key == 'activity':
            budget.shape(section, budget.ACTIVITY_COUNTS | {'actions_enabled', 'coverage_complete', 'receipt'} | budget.PERIOD_KEYS)
            for count in budget.ACTIVITY_COUNTS: budget.integer(section[count])
            for flag in ('actions_enabled', 'coverage_complete'):
                budget.require(type(section[flag]) is bool, 'INVALID_BOOLEAN')
            seconds = int((end-begin).total_seconds())
            budget.require(section['worker_covered_seconds'] <= seconds and section['worker_uptime_seconds'] <= seconds, 'INVALID_WORKER_DURATION')
            if not section['coverage_complete']: missing.append('INCOMPLETE_ACTIVITY_COVERAGE')
            if not section['actions_enabled'] or section['nightly_runs'] == 0: missing.append('NIGHTLY_PROFILE_NOT_OBSERVED')
            if section['worker_covered_seconds'] != seconds or any(section[k] == 0 for k in ('worker_uptime_seconds', 'worker_scans', 'worker_heartbeats')):
                missing.append('WORKER_PROFILE_NOT_OBSERVED')
            kinds = {'runtime_logs'}
        else:
            budget.shape(section, {'measurement', 'direction', 'transfer', 'receipt'} | budget.PERIOD_KEYS)
            budget.require(section['direction'] == 'database_to_worker', 'SOCIAL_DIRECTION_MISMATCH')
            measurement = section['measurement']
            budget.require(measurement in ('provider_bytes', 'protocol_bytes', 'decoded_estimate', 'cumulative_counter'), 'INVALID_MEASUREMENT')
            kinds = {'social_provider_meter'} if measurement == 'provider_bytes' else {'social_protocol_measurement'}
            low, high = budget.amount(section['transfer'])
            if measurement not in ('provider_bytes', 'protocol_bytes'): missing.append('SOCIAL_TRANSFER_NOT_MEASURED')
            if measurement == 'protocol_bytes' and high == 0 and record['activity'] is not None and any(record['activity'][k] for k in budget.TRAFFIC_COUNTS):
                missing.append('PROTOCOL_TRANSFER_CONTRADICTS_ACTIVITY')
            if measurement == 'provider_bytes' and ranges is not None:
                budget.require(high <= ranges[1], 'SOCIAL_EXCEEDS_TOTAL')
        budget.receipt(section, kinds, binding, False, end, as_of, (begin, end))
    return {'missing': sorted(set(missing)), 'provider_byte_bounds': ranges}


def coverage(records, *, expected_identity, first_day, as_of):
    """Seven slots, with missing days left missing; never assemble fabricated days."""
    report = _report()
    try:
        _bounded(records); _bounded(expected_identity)
        cycle_start, cycle_end, zone = budget.identity(expected_identity)
        current = budget.civil_date(first_day)
        as_of = _aware(as_of)
        budget.require(type(records) is list and len(records) <= 31, 'INVALID_DAY_COUNT')
        budget.require(cycle_start <= current and current + timedelta(days=7) <= cycle_end, 'WINDOW_OUTSIDE_CYCLE')
        budget.require(datetime.combine(cycle_start, time(), zone).astimezone(timezone.utc) <= as_of <=
                       datetime.combine(cycle_end, time(), zone).astimezone(timezone.utc), 'AS_OF_OUTSIDE_CYCLE')
        by_date = {}
        for record in records:
            budget.require(type(record) is dict and 'date' in record, 'INVALID_DAY')
            day = budget.civil_date(record['date'])
            budget.require(current <= day < current + timedelta(days=7), 'DAY_OUTSIDE_WINDOW')
            budget.require(day not in by_date, 'DUPLICATE_DAY')
            by_date[day] = record
        ledger = []
        for offset in range(7):
            day = current + timedelta(days=offset)
            begin = datetime.combine(day, time(), zone).astimezone(timezone.utc)
            end = datetime.combine(day+timedelta(days=1), time(), zone).astimezone(timezone.utc)
            result = _day(by_date[day], expected_identity, begin, end, as_of) if day in by_date else {
                'missing': ['DAY_MISSING'], 'provider_byte_bounds': None}
            ledger.append({'date': str(day), 'period_start': begin.isoformat(), 'period_end': end.isoformat(),
                           'civil_seconds': int((end-begin).total_seconds()), **result})
        report.update(ledger=ledger, evaluation_as_of=as_of.isoformat(),
                      identity_sha256=budget.content_hash(expected_identity),
                      input_sha256=budget.content_hash(records),
                      covered_days=sum(not entry['missing'] for entry in ledger),
                      next_calendar_close=ledger[-1]['period_end'])
        # Readiness/hosting/accrued charges/counter continuity are still checked
        # only by the unchanged full evaluator, never by these seven slots.
        report['unknowns'] = ['FULL_OPERATING_ACCEPTANCE_PENDING', 'IMPORTED_RECEIPTS_UNAUTHENTICATED']
        if report['covered_days'] != 7: report['unknowns'].append('SEVEN_REPRESENTATIVE_DAYS_MISSING')
        activities = [record['activity'] for record in records if record['activity'] is not None]
        missing = []
        if not all(sum(a[k] for a in activities) > 0 for k in ('api_requests', 'worker_publications', 'deployments')):
            missing.append('REPRESENTATIVE_ACTIVITY_MISSING')
        if sum(a['restarts'] for a in activities) == 0: missing.append('RESTART_PROFILE_NOT_OBSERVED')
        if sum(a['cache_hits']+a['cache_misses'] for a in activities) == 0: missing.append('CACHE_ACTIVITY_MISSING')
        bases = {record['social']['measurement'] for record in records if record['social'] is not None}
        budget.require(len(bases) <= 1, 'SOCIAL_MEASUREMENT_SCOPE_MISMATCH')
        report['window_missing'] = missing
        report['unknowns'].extend(missing)
    except (budget.EvidenceError, TypeError, KeyError, OverflowError, RecursionError):
        error = sys.exc_info()[1]
        report = _report()
        report['unknowns'] = [str(error) if isinstance(error, budget.EvidenceError) else 'INVALID_INPUT']
    return report


def _import_snapshot(report):
    budget.shape(report, set(collector._report()) | {'session_observation'})
    budget.require(report['schema_version'] == 1 and type(report['schema_version']) is int, 'INVALID_VERSION')
    budget.require(report['status'] in ('OBSERVED_COUNTERS_ONLY', 'PARTIAL_OBSERVATION'), 'SNAPSHOT_NOT_OBSERVED')
    budget.require(report['production_authorized'] is False and report['provider_meter_authenticated'] is False
                   and report['caller_attribution_verified'] is False, 'FALSE_AUTHORITY')
    budget.require(report['artifact_authentication'] == 'UNVERIFIED_WHEN_IMPORTED' and
                   report['generated_by'] == 'scripts/verification/social_operating_collect.py', 'INVALID_PROVENANCE')
    budget.require(report['session_observation'] in ('TLS_DATABASE_SESSION_READBACK', 'INJECTED_TEST_DRIVER'), 'INVALID_PROVENANCE')
    budget.digest(report['generator_sha256'])
    snapshot = collector.validate_snapshot(report['snapshot'])
    budget.require(budget.digest(report['payload_sha256']) == budget.content_hash(snapshot), 'SNAPSHOT_PAYLOAD_MISMATCH')
    budget.require(budget.instant(report['captured_at']) >= budget.instant(snapshot['snapshot_end']), 'CAPTURE_BEFORE_SNAPSHOT_END')
    budget.require(report['unknowns'] == snapshot['unknowns'], 'SNAPSHOT_STATUS_MISMATCH')
    return snapshot


def delta(before, after, *, expected_database_sha256, start_at, end_at, as_of):
    """Only supplied shapes, exact per-shape endpoint times, no caller/byte inference."""
    report = _report()
    try:
        _bounded(before); _bounded(after)
        first, last = _import_snapshot(before), _import_snapshot(after)
        budget.require(first['database_sha256'] == last['database_sha256'] == budget.digest(expected_database_sha256), 'DATABASE_IDENTITY_MISMATCH')
        start, end, now = budget.instant(start_at), budget.instant(end_at), _aware(as_of)
        budget.require(budget.instant(first['snapshot_end']) <= start < end <= budget.instant(last['snapshot_start'])
                       and budget.instant(last['snapshot_end']) <= now
                       and budget.instant(after['captured_at']) <= now
                       and budget.instant(before['captured_at']) <= now, 'COUNTER_WINDOW_MISMATCH')
        infos = [first['info_before'], first['info_after'], last['info_before'], last['info_after']]
        budget.require(all(info is not None for info in infos), 'COUNTER_HISTORY_MISSING')
        budget.require(len({(budget.instant(info['stats_reset']), info['dealloc']) for info in infos}) == 1, 'COUNTER_HISTORY_CHANGED')
        budget.require(not first['unknowns'] and not last['unknowns'], 'COUNTER_OBSERVATION_PARTIAL')
        old, new = ({e['query_sha256']: e for e in snap['entries']} for snap in (first, last))
        budget.require(set(old) == set(new), 'QUERY_SHAPES_CHANGED')
        entries = []
        for key, entry in old.items():
            other = new[key]
            budget.require(entry['observed_at'] is not None and other['observed_at'] is not None
                           and entry['stats_since'] is not None and other['stats_since'] is not None
                           and budget.instant(entry['stats_since']) == budget.instant(other['stats_since']), 'QUERY_HISTORY_CHANGED')
            budget.require(other['calls'] >= entry['calls'] and other['rows'] >= entry['rows'], 'COUNTER_DECREASED')
            entries.append({'query_sha256': key, 'calls_delta': other['calls']-entry['calls'],
                'rows_delta': other['rows']-entry['rows'], 'observed_start': entry['observed_at'],
                'observed_end': other['observed_at']})
        report.update(status='DECLARED_COUNTER_DELTA_ONLY', entries=entries,
            requested_start=start_at, requested_end=end_at, interval_exact=False,
            query_counters_are_billed_bytes=False, scope='ALLOWLISTED_SHAPES_ONLY',
            database_sha256=expected_database_sha256,
            input_sha256=budget.content_hash([before, after]),
            unknowns=['CALLER_ATTRIBUTION_UNVERIFIED', 'IMPORTED_RECEIPTS_UNAUTHENTICATED',
                      'PROVIDER_BYTES_NOT_MEASURED', 'ENDPOINT_BRACKETS_NOT_EXACT_WORKLOAD_INTERVAL'])
    except (budget.EvidenceError, TypeError, KeyError, OverflowError, RecursionError):
        error = sys.exc_info()[1]
        report = _report()
        report['unknowns'] = [str(error) if isinstance(error, budget.EvidenceError) else 'INVALID_INPUT']
    return report


def main(argv=None):
    try:
        parser = budget.SafeParser(description=__doc__)
        parser.add_argument('--records', required=True, help='Partial evaluator-shaped days JSON list')
        parser.add_argument('--expected-identity', required=True)
        parser.add_argument('--first-day', required=True)
        parser.add_argument('--as-of', required=True)
        args = parser.parse_args(argv)
        report = coverage(budget.load_json(args.records), expected_identity=budget.load_json(args.expected_identity),
                          first_day=args.first_day, as_of=budget.instant(args.as_of))
        print(json.dumps(report, sort_keys=True))
        return 1  # Preparing evidence is never an acceptance success.
    except (budget.EvidenceError, OSError, ValueError, TypeError):
        error = sys.exc_info()[1]
        report = _report()
        report['unknowns'] = [str(error) if isinstance(error, budget.EvidenceError) else 'CLI_FAILED']
        print(json.dumps(report, sort_keys=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
