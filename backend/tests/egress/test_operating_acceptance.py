"""Offline budgets validate assertions; these tests provide no live acceptance."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / 'scripts/verification/evaluate_social_operating_budget.py'
FIXTURE = ROOT / 'docs/infrastructure/supabase-egress/fixtures/social-operating-synthetic.json'
SPEC = importlib.util.spec_from_file_location('operating_budget', TOOL)
budget = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(budget)
AS_OF = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def sections(packet):
    for day in packet['days']:
        yield from (day['provider'], day['activity'], day['social'])
    yield packet['hosting']
    yield packet['cycle_usage']
    yield packet['cycle_social']
    yield from packet['future_increments']
    if packet['query_counters'] is not None:
        yield packet['query_counters']


def reseal(packet):
    """Explicit test assertions can be rehashed; hashing is not authentication."""
    for section in sections(packet):
        receipt = section['receipt']
        receipt['identity_sha256'] = budget.content_hash(packet['identity'])
        receipt['payload_sha256'] = budget.content_hash({k: v for k, v in section.items() if k != 'receipt'})
    return packet


@pytest.fixture
def declared():
    packet = json.loads(FIXTURE.read_text())
    packet['synthetic'] = False
    packet['identity']['organization_id'] = 'operator-declared-test-org'
    packet['identity']['project_id'] = 'operator-declared-test-project'
    packet['hosting']['owner'] = 'operator-declared-test-owner'
    for section in sections(packet):
        section['receipt']['synthetic'] = False
        section['receipt']['observer'] = 'operator-declared-test-observer'
    return reseal(packet)


def evaluate(packet, as_of=AS_OF, expected=None):
    result = budget.evaluate(packet, expected_identity=packet['identity'] if expected is None else expected, as_of=as_of)
    assert result['production_authorized'] is False
    assert result['evidence_authentication'] == 'UNVERIFIED_OPERATOR_ASSERTIONS'
    return result


def quantity(value, unit='B', rounding='exact', resolution=0):
    return {'value': value, 'unit': unit, 'rounding': rounding, 'resolution': resolution}


def at(packet, path):
    current = packet
    for key in path[:-1]: current = current[key]
    return current, path[-1]


def test_synthetic_fixture_is_visibly_blocked():
    packet = json.loads(FIXTURE.read_text())
    report = evaluate(packet)
    assert packet['synthetic'] is True
    assert report['status'] == 'BLOCKED'
    assert report['unknowns'] == ['SYNTHETIC_EVIDENCE']
    assert all(section['receipt']['synthetic'] for section in sections(packet))


def test_candidate_is_unverified_owner_review_with_exact_cycle_and_deltas(declared):
    report = evaluate(declared)
    assert report['status'] == 'CANDIDATE_FOR_OWNER_REVIEW'
    assert report['unknowns'] == []
    measured = report['measurements']
    assert measured['cycle_days'] == 31
    assert measured['cycle_projection_upper_bytes'] == 3_100_000_000
    assert measured['social_cycle_upper_bytes'] == 124_000_000
    assert measured['accrued_cycle_upper_bytes'] == 750_000_000
    assert measured['connection_demand'] == 19 and measured['connection_reserve'] == 5
    assert measured['query_counters_are_billed_bytes'] is False
    assert report['query_attribution']['calls_delta'] == 200
    assert report['query_attribution']['rows_delta'] == 5000
    assert report['query_attribution']['scope'] == 'SUPPLIED_QUERY_SHAPES_ONLY'
    assert report['input_sha256'] == budget.content_hash(declared)
    assert report['generator_sha256'] == budget.hashlib.sha256(TOOL.read_bytes()).hexdigest()


@pytest.mark.parametrize('section', ['provider', 'activity', 'social'])
def test_observed_red_copied_receipt_cannot_supply_another_day(declared, section):
    # First draft accepted the same common-identity payload on all seven days.
    declared['days'][1][section] = deepcopy(declared['days'][0][section])
    report = evaluate(declared)
    assert report['status'] == 'BLOCKED' and 'RECEIPT_PERIOD_MISMATCH' in report['unknowns']


def test_observed_red_web_demand_cannot_understate_this_build(declared):
    declared['hosting']['processes'][0].update(pool_size=1, overflow=0)
    assert evaluate(reseal(declared))['unknowns'] == ['WEB_POOL_MISMATCH']


def test_observed_red_social_31_day_cycle_exceeds_200_mb(declared):
    for day in declared['days']: day['social']['transfer'] = quantity(6_500_000)
    declared['cycle_social']['transfer'] = quantity(48_750_000)
    report = evaluate(reseal(declared))
    assert report['status'] == 'OVER_BUDGET'
    assert report['measurements']['social_cycle_upper_bytes'] == 201_500_000
    assert report['exceeded'] == ['SOCIAL_MONTHLY_TARGET_EXCEEDED']


def test_observed_red_additional_social_growth_counts_in_both_budgets(declared):
    increment = declared['future_increments'][0]
    increment.update(inclusion='additional_future', remaining_units=1, bytes_per_unit=quantity(100_000_000))
    report = evaluate(reseal(declared))
    assert report['status'] == 'OVER_BUDGET'
    assert report['measurements']['cycle_projection_upper_bytes'] == 3_200_000_000
    assert report['measurements']['social_cycle_upper_bytes'] == 224_000_000


def test_observed_red_missing_accrued_usage_cannot_replace_historical_charges(declared):
    declared.pop('cycle_usage')
    assert evaluate(declared)['status'] == 'BLOCKED'


def test_over_quota_accrued_usage_remains_counted_despite_low_recent_average(declared):
    declared['identity']['cycle_start'] = '2026-10-01'
    declared['cycle_usage']['period_start'] = '2026-10-01T00:00:00Z'
    declared['cycle_social']['period_start'] = '2026-10-01T00:00:00Z'
    declared['cycle_usage']['total_uncached'] = quantity(6_000_000_000)
    report = evaluate(reseal(declared))
    assert report['status'] == 'OVER_BUDGET'
    assert report['measurements']['mean_daily_upper_bytes'] == 100_000_000
    assert report['measurements']['cycle_projection_upper_bytes'] == 8_350_000_000
    assert report['measurements']['remaining_cycle_headroom_bytes'] == -3_350_000_000


def test_accrued_social_spike_cannot_be_erased_by_the_quiet_window(declared):
    declared['cycle_social']['transfer'] = quantity(190_000_000)
    report = evaluate(reseal(declared))
    assert report['status'] == 'OVER_BUDGET'
    assert report['measurements']['social_cycle_upper_bytes'] == 284_000_000


def set_zero_social(packet, measurement, transfer):
    packet['future_increments'] = []
    for section in [*(day['social'] for day in packet['days']), packet['cycle_social']]:
        section['measurement'] = measurement
        section['receipt']['kind'] = 'social_protocol_measurement' if measurement == 'protocol_bytes' else 'social_provider_meter'
        section['transfer'] = deepcopy(transfer)
    return reseal(packet)


def test_observed_red_exact_zero_protocol_traffic_contradicts_active_worker(declared):
    report = evaluate(set_zero_social(declared, 'protocol_bytes', quantity(0)))
    assert report['status'] == 'BLOCKED'
    assert 'PROTOCOL_TRANSFER_CONTRADICTS_ACTIVITY' in report['unknowns']


@pytest.mark.parametrize('scope', ['daily', 'cycle'])
def test_daily_and_cycle_zero_protocol_declarations_are_checked_independently(declared, scope):
    set_zero_social(declared, 'provider_bytes', quantity(0))
    section = declared['days'][0]['social'] if scope == 'daily' else declared['cycle_social']
    section['measurement'] = 'protocol_bytes'
    section['receipt']['kind'] = 'social_protocol_measurement'
    report = evaluate(reseal(declared))
    assert report['status'] == 'BLOCKED'
    assert 'PROTOCOL_TRANSFER_CONTRADICTS_ACTIVITY' in report['unknowns']


def test_charged_provider_zero_is_not_assumed_to_be_zero_protocol_traffic(declared):
    report = evaluate(set_zero_social(declared, 'provider_bytes', quantity(0)))
    assert report['status'] == 'CANDIDATE_FOR_OWNER_REVIEW'


def test_rounded_protocol_zero_with_positive_upper_uncertainty_remains_reviewable(declared):
    report = evaluate(set_zero_social(declared, 'protocol_bytes', quantity(0, rounding='nearest', resolution=2)))
    assert report['status'] == 'CANDIDATE_FOR_OWNER_REVIEW'


def test_already_included_workloads_are_not_added_again(declared):
    report = evaluate(reseal(declared))
    assert report['status'] == 'CANDIDATE_FOR_OWNER_REVIEW'
    assert report['measurements']['additional_future_upper_bytes'] == 0
    assert report['measurements']['additional_social_upper_bytes'] == 0
    assert report['measurements']['included_future_upper_bytes_not_added'] == 92_000_000


def test_included_workload_cannot_claim_more_than_the_provider_baseline(declared):
    declared['future_increments'][0].update(bytes_per_unit=quantity(100_000_000), remaining_units=1000)
    report = evaluate(reseal(declared))
    assert report['status'] == 'BLOCKED'
    assert 'INCLUSION_CONTRADICTS_BASELINE' in report['unknowns']


def test_spike_remains_visible_without_replacing_average(declared):
    declared['days'][0]['provider']['total_uncached'] = quantity(200_000_000)
    declared['days'][0]['provider']['services']['shared_pooler'] = quantity(200_000_000)
    declared['cycle_usage']['total_uncached'] = quantity(850_000_000)
    report = evaluate(reseal(declared))
    assert report['status'] == 'CANDIDATE_FOR_OWNER_REVIEW'
    assert report['measurements']['peak_daily_upper_bytes'] == 200_000_000
    assert report['measurements']['peak_days'] == ['2026-10-08']


def test_conservative_rounding_crosses_the_daily_target(declared):
    for day in declared['days']:
        day['provider']['total_uncached'] = quantity('120', 'MB', 'nearest', '1')
        day['provider']['services']['shared_pooler'] = quantity('120', 'MB', 'nearest', '1')
    declared['cycle_usage']['total_uncached'] = quantity(900_000_000)
    report = evaluate(reseal(declared))
    assert report['status'] == 'OVER_BUDGET'
    assert report['measurements']['mean_daily_upper_bytes'] == 120_500_000
    assert 'TOTAL_DAILY_TARGET_EXCEEDED' in report['exceeded']


@pytest.mark.parametrize('path,value,code', [
    (('schema_version',), True, 'INVALID_VERSION'),
    (('representative',), 1, 'INVALID_BOOLEAN'),
    (('days', 0, 'complete'), False, 'INCOMPLETE_DAY'),
    (('days', 0, 'date'), '2026-02-30', 'INVALID_DATE'),
    (('days', 0, 'date'), '2026-11-08', 'DAY_OUTSIDE_CYCLE'),
    (('days', 0, 'deployment_sha'), 'a' * 40, 'DEPLOYMENT_MISMATCH'),
    (('days', 0, 'provider', 'total_uncached', 'unit'), 'MiB', 'INVALID_UNIT'),
    (('days', 0, 'provider', 'meter_scope'), 'project_uncached', 'METER_SCOPE_MISMATCH'),
    (('days', 0, 'provider', 'total_uncached', 'value'), True, 'INVALID_AMOUNT'),
    (('days', 0, 'provider', 'total_uncached', 'value'), 1.5, 'INVALID_AMOUNT'),
    (('days', 0, 'provider', 'total_uncached', 'value'), '-1', 'INVALID_AMOUNT'),
    (('days', 0, 'provider', 'total_uncached', 'resolution'), 1, 'INVALID_RESOLUTION'),
    (('days', 0, 'provider', 'services', 'auth', 'value'), 1_000_000, 'SERVICE_TOTAL_MISMATCH'),
    (('days', 0, 'activity', 'api_requests'), True, 'INVALID_INTEGER'),
    (('days', 0, 'activity', 'worker_uptime_seconds'), 86401, 'INVALID_WORKER_DURATION'),
    (('days', 0, 'social', 'direction'), 'worker_to_database', 'SOCIAL_DIRECTION_MISMATCH'),
    (('days', 0, 'social', 'measurement'), 'protocol_bytes', 'MEASUREMENT_KIND_MISMATCH'),
    (('days', 0, 'social', 'transfer', 'value'), 100_000_001, 'SOCIAL_EXCEEDS_TOTAL'),
    (('cycle_usage', 'period_end'), '2026-10-15T00:00:00Z', 'RECEIPT_PERIOD_MISMATCH'),
    (('cycle_usage', 'total_uncached', 'value'), 600_000_000, 'ACCRUED_USAGE_CONTRADICTS_DAYS'),
    (('hosting', 'deployed_at'), '2026-10-09T00:00:00Z', 'HOST_DEPLOYMENT_MISMATCH'),
    (('hosting', 'deployment_sha'), 'a' * 40, 'HOST_DEPLOYMENT_MISMATCH'),
    (('hosting', 'processes', 1, 'overflow'), 1, 'WORKER_POOL_MISMATCH'),
    (('hosting', 'processes', 1, 'replicas'), 0, 'INVALID_PROCESS_INVENTORY'),
    (('hosting', 'processes', 2, 'connection_kind'), 'direct_database_connections', 'CAPACITY_KIND_MISMATCH'),
    (('hosting', 'capacity', 'limit_kind'), 'pooler_backend_connections', 'INVALID_CAPACITY_KIND'),
    (('hosting', 'capacity', 'reserved_connections'), 0, 'CAPACITY_RESERVE_REQUIRED'),
    (('future_increments', 0, 'inclusion'), 'unknown', 'INCREMENT_INCLUSION_REQUIRED'),
    (('future_increments', 0, 'remaining_units'), True, 'INVALID_INTEGER'),
    (('query_counters', 'before', 0, 'calls'), -1, 'INVALID_INTEGER'),
])
def test_hostile_declared_shapes_fail_closed(declared, path, value, code):
    parent, key = at(declared, path); parent[key] = value
    assert code in evaluate(reseal(declared))['unknowns']


@pytest.mark.parametrize('path,value,code', [
    (('representative',), False, 'WORKLOAD_NOT_REPRESENTATIVE'),
    (('days', 0, 'activity', 'actions_enabled'), False, 'NIGHTLY_PROFILE_NOT_OBSERVED'),
    (('days', 0, 'activity', 'nightly_runs'), 0, 'NIGHTLY_PROFILE_NOT_OBSERVED'),
    (('days', 0, 'activity', 'coverage_complete'), False, 'INCOMPLETE_ACTIVITY_COVERAGE'),
    (('days', 0, 'activity', 'worker_covered_seconds'), 80000, 'WORKER_PROFILE_NOT_OBSERVED'),
    (('days', 0, 'social', 'measurement'), 'decoded_estimate', 'SOCIAL_TRANSFER_NOT_MEASURED'),
    (('days', 0, 'social', 'measurement'), 'cumulative_counter', 'SOCIAL_TRANSFER_NOT_MEASURED'),
    (('hosting', 'always_on'), False, 'HOSTING_NOT_ACCEPTED'),
    (('hosting', 'cost_accepted'), False, 'HOSTING_NOT_ACCEPTED'),
    (('future_increments', 0, 'measurement'), 'decoded_estimate', 'FUTURE_TRANSFER_NOT_MEASURED'),
    (('query_counters', 'kind'), 'cumulative', 'QUERY_DELTA_UNVERIFIED'),
    (('query_counters', 'end_reset'), '2026-10-10T00:00:00Z', 'QUERY_DELTA_UNVERIFIED'),
    (('query_counters', 'after', 0, 'calls'), 4999, 'QUERY_DELTA_UNVERIFIED'),
    (('query_counters', 'after', 0, 'query_sha256'), 'c' * 64, 'QUERY_DELTA_UNVERIFIED'),
])
def test_unavailable_evidence_is_blocked_not_a_budget_pass(declared, path, value, code):
    parent, key = at(declared, path); parent[key] = value
    report = evaluate(reseal(declared))
    assert report['status'] == 'BLOCKED' and code in report['unknowns']


@pytest.mark.parametrize('key', ['api_requests', 'worker_publications', 'deployments'])
def test_activity_totals_cannot_hide_absent_intended_work(declared, key):
    for day in declared['days']: day['activity'][key] = 0
    assert 'REPRESENTATIVE_ACTIVITY_MISSING' in evaluate(reseal(declared))['unknowns']


def test_observed_red_zero_restarts_cannot_represent_restart_traffic(declared):
    for day in declared['days']: day['activity']['restarts'] = 0
    report = evaluate(reseal(declared))
    assert report['status'] == 'BLOCKED'
    assert 'RESTART_PROFILE_NOT_OBSERVED' in report['unknowns']


def test_one_observed_restart_in_window_preserves_explicit_quiet_days(declared):
    for day in declared['days']: day['activity']['restarts'] = 0
    declared['days'][3]['activity']['restarts'] = 1
    report = evaluate(reseal(declared))
    assert report['status'] == 'CANDIDATE_FOR_OWNER_REVIEW'
    assert report['unknowns'] == []


def test_connection_replica_overflow_demand_and_reserve(declared):
    declared['hosting']['processes'][0].update(replicas=2, processes_per_replica=2)
    report = evaluate(reseal(declared))
    assert report['status'] == 'OVER_BUDGET'
    assert report['measurements']['connection_demand'] == 64
    assert 'CONNECTION_CAPACITY_EXCEEDED' in report['exceeded']


@pytest.mark.parametrize('size', [0, 6, 32])
def test_window_size_is_bounded(declared, size):
    declared['days'] = (declared['days'] * 5)[:size]
    assert evaluate(declared)['unknowns'] == ['SEVEN_DAYS_REQUIRED']


def test_gaps_duplicate_days_missing_processes_and_overlap_are_blocked(declared):
    copies = deepcopy(declared); copies['days'][1] = deepcopy(copies['days'][0])
    assert 'DAYS_NOT_CONSECUTIVE' in evaluate(copies)['unknowns']
    copies = deepcopy(declared); copies['hosting']['processes'].pop()
    assert 'PROCESS_COVERAGE_REQUIRED' in evaluate(reseal(copies))['unknowns']
    copies = deepcopy(declared); copies['future_increments'] *= 2
    assert 'INCREMENT_OVERLAP' in evaluate(reseal(copies))['unknowns']
    copies = deepcopy(declared); copies['query_counters'] = None
    assert 'QUERY_ATTRIBUTION_UNAVAILABLE' in evaluate(copies)['unknowns']


def test_day_must_be_closed_and_window_fresh(declared):
    # Earlier receipts stay admissible, so the test reaches the future day.
    for day in declared['days'][:-1]:
        for key in ('provider', 'activity', 'social'):
            day[key]['receipt']['captured_at'] = '2026-10-14T00:00:00Z'
    assert 'DAY_NOT_CLOSED' in evaluate(declared, datetime(2026, 10, 14, 12, tzinfo=timezone.utc))['unknowns']
    assert 'STALE_WINDOW' in evaluate(declared, AS_OF + timedelta(days=3))['unknowns']


@pytest.mark.parametrize('value', [None, True, '2026-10-15T12:00:00Z', datetime(2026, 10, 15)])
def test_explicit_as_of_has_strict_shape(declared, value):
    assert 'INVALID_AS_OF' in evaluate(declared, value)['unknowns']


@pytest.mark.parametrize('key,value', [('organization_id', 'wrong-org'), ('project_id', 'wrong-project'),
    ('deployment_sha', 'a' * 40), ('timezone', 'Africa/Nairobi'), ('cycle_start', '2026-10-01')])
def test_expected_identity_is_external_and_exact(declared, key, value):
    expected = deepcopy(declared['identity']); expected[key] = value
    assert 'IDENTITY_MISMATCH' in evaluate(declared, expected=expected)['unknowns']


@pytest.mark.parametrize('change,code', [('hash', 'RECEIPT_PAYLOAD_MISMATCH'), ('binding', 'RECEIPT_IDENTITY_MISMATCH'),
    ('time', 'RECEIPT_TIME_MISMATCH'), ('kind', 'WRONG_EVIDENCE_KIND'), ('synthetic', 'SYNTHETIC_IDENTITY_MISMATCH')])
def test_receipt_bindings_cannot_drift(declared, change, code):
    receipt = declared['days'][0]['provider']['receipt']
    receipt.update({'payload_sha256': 'a' * 64} if change == 'hash' else
        {'identity_sha256': 'a' * 64} if change == 'binding' else
        {'captured_at': '2026-10-16T00:00:00Z'} if change == 'time' else
        {'kind': 'source_storage_receipt'} if change == 'kind' else {'synthetic': True})
    assert code in evaluate(declared)['unknowns']


def test_secret_fields_nonfinite_and_excessive_inputs_are_sanitized(declared):
    secret = 'postgresql://private-user:DO-NOT-PRINT@remote.invalid/db'
    bad = deepcopy(declared); bad['password'] = secret
    report = evaluate(bad)
    assert report['status'] == 'BLOCKED' and secret not in json.dumps(report)
    for value in [float('nan'), float('inf')]:
        bad = deepcopy(declared); bad['days'][0]['activity']['api_requests'] = value
        assert evaluate(bad)['unknowns'] == ['INVALID_JSON']
    bad = deepcopy(declared); bad['extra'] = 'x' * budget.MAX_BYTES
    assert evaluate(bad)['unknowns'] == ['INPUT_TOO_LARGE']


def test_equivalent_utc_reset_instants_do_not_invent_a_reset(declared):
    declared['query_counters']['end_reset'] = '2026-04-22T23:29:28+03:00'
    assert evaluate(reseal(declared))['status'] == 'CANDIDATE_FOR_OWNER_REVIEW'


@pytest.mark.parametrize('field', ['before_database_sha256', 'after_database_sha256'])
def test_query_snapshot_database_identity_cannot_drift(declared, field):
    declared['query_counters'][field] = 'e' * 64
    assert 'QUERY_DB_IDENTITY_MISMATCH' in evaluate(reseal(declared))['unknowns']


def test_observed_red_absent_counter_history_cannot_establish_declared_delta(declared):
    counters = declared['query_counters']
    counters.pop('before_dealloc', None); counters.pop('after_dealloc', None)
    for key in ('before', 'after'):
        for entry in counters[key]: entry.pop('stats_since', None)
    report = evaluate(reseal(declared))
    assert report['status'] == 'BLOCKED'
    assert report.get('query_attribution', {}).get('available', False) is False


@pytest.mark.parametrize('path', [
    ('before_dealloc',), ('after_dealloc',), ('before', 0, 'stats_since'), ('after', 0, 'stats_since'),
])
def test_each_counter_history_field_is_required(declared, path):
    target, key = at(declared['query_counters'], path)
    target.pop(key)
    report = evaluate(reseal(declared))
    assert report['status'] == 'BLOCKED'
    assert report.get('query_attribution', {}).get('available', False) is False


@pytest.mark.parametrize('path,value', [
    (('after_dealloc',), 6), (('before_dealloc',), 6),
    (('after', 0, 'stats_since'), '2026-10-09T00:00:00Z'),
    (('before', 0, 'stats_since'), '2026-10-09T00:00:00Z'),
])
def test_changed_eviction_or_shape_history_cannot_establish_delta(declared, path, value):
    target, key = at(declared['query_counters'], path)
    target[key] = value
    report = evaluate(reseal(declared))
    assert report['status'] == 'BLOCKED' and 'QUERY_DELTA_UNVERIFIED' in report['unknowns']
    assert report['query_attribution']['available'] is False
    assert report['query_attribution']['calls_delta'] is None


def test_matching_shape_history_must_precede_snapshot_start(declared):
    for key in ('before', 'after'):
        declared['query_counters'][key][0]['stats_since'] = '2026-10-09T00:00:00Z'
    assert 'QUERY_DELTA_UNVERIFIED' in evaluate(reseal(declared))['unknowns']


def test_equivalent_offset_shape_history_does_not_invent_a_reset(declared):
    declared['query_counters']['after'][0]['stats_since'] = '2026-10-01T03:00:00+03:00'
    assert evaluate(reseal(declared))['status'] == 'CANDIDATE_FOR_OWNER_REVIEW'


@pytest.mark.parametrize('value', [True, -1, 1.0, '5', 10**15 + 1])
def test_eviction_counts_are_strict_bounded_integers(declared, value):
    declared['query_counters']['after_dealloc'] = value
    assert evaluate(reseal(declared))['status'] == 'BLOCKED'


def test_duplicate_empty_or_missing_query_shapes_cannot_establish_deltas(declared):
    candidate = deepcopy(declared); candidate['query_counters']['after'] = []
    assert 'INVALID_COUNTER_COUNT' in evaluate(reseal(candidate))['unknowns']
    candidate = deepcopy(declared); candidate['query_counters']['after'] *= 2
    assert 'DUPLICATE_QUERY_SHAPE' in evaluate(reseal(candidate))['unknowns']
    candidate = deepcopy(declared)
    candidate['query_counters']['after'].append({'query_sha256': 'f' * 64, 'calls': 10, 'rows': 1, 'stats_since': '2026-10-01T00:00:00Z'})
    assert 'QUERY_DELTA_UNVERIFIED' in evaluate(reseal(candidate))['unknowns']


def test_protocol_receipt_is_explicit_not_a_provider_bill(declared):
    for day in declared['days']:
        day['social']['measurement'] = 'protocol_bytes'
        day['social']['receipt']['kind'] = 'social_protocol_measurement'
    declared['cycle_social']['measurement'] = 'protocol_bytes'
    declared['cycle_social']['receipt']['kind'] = 'social_protocol_measurement'
    declared['future_increments'][0]['measurement'] = 'protocol_bytes'
    report = evaluate(reseal(declared))
    assert report['status'] == 'CANDIDATE_FOR_OWNER_REVIEW'
    assert report['evidence_authentication'] == 'UNVERIFIED_OPERATOR_ASSERTIONS'


@pytest.mark.parametrize('scope', ['daily', 'cycle', 'increment'])
def test_observed_red_mixed_social_measurement_bases_cannot_form_one_forecast(declared, scope):
    target = (declared['days'][0]['social'] if scope == 'daily' else declared['cycle_social']
              if scope == 'cycle' else declared['future_increments'][0])
    target['measurement'] = 'protocol_bytes'
    if scope != 'increment': target['receipt']['kind'] = 'social_protocol_measurement'
    report = evaluate(reseal(declared))
    assert report['status'] == 'BLOCKED'
    assert 'SOCIAL_MEASUREMENT_SCOPE_MISMATCH' in report['unknowns']


def test_observed_red_protocol_wire_transfer_is_independent_of_zero_charged_meter(declared):
    declared['future_increments'] = []
    for day in declared['days']:
        day['provider']['total_uncached'] = quantity(0)
        for key in day['provider']['services']: day['provider']['services'][key] = quantity(0)
        day['social'].update(measurement='protocol_bytes', transfer=quantity(1))
        day['social']['receipt']['kind'] = 'social_protocol_measurement'
    declared['cycle_usage']['total_uncached'] = quantity(0)
    declared['cycle_social'].update(measurement='protocol_bytes', transfer=quantity(8))
    declared['cycle_social']['receipt']['kind'] = 'social_protocol_measurement'
    report = evaluate(reseal(declared))
    assert report['status'] == 'CANDIDATE_FOR_OWNER_REVIEW'
    assert report['measurements']['cycle_projection_upper_bytes'] == 0
    assert report['measurements']['social_cycle_upper_bytes'] > 0


def test_observed_red_query_receipt_cannot_precede_its_own_snapshot_end(declared):
    declared['query_counters']['end_at'] = AS_OF.isoformat()
    declared['query_counters']['receipt']['captured_at'] = '2026-10-15T00:00:00Z'
    report = evaluate(reseal(declared))
    assert report['status'] == 'BLOCKED'
    assert 'RECEIPT_TIME_MISMATCH' in report['unknowns']
    assert report.get('query_attribution', {}).get('available', False) is False


def test_extended_query_interval_with_receipt_after_actual_end_remains_reviewable(declared):
    declared['query_counters']['end_at'] = AS_OF.isoformat()
    assert evaluate(reseal(declared))['status'] == 'CANDIDATE_FOR_OWNER_REVIEW'


def test_hosting_receipt_before_deployment_was_already_refused(declared):
    declared['hosting']['receipt']['captured_at'] = '2026-10-07T23:00:00Z'
    assert 'RECEIPT_TIME_MISMATCH' in evaluate(reseal(declared))['unknowns']


def test_protocol_future_proxy_is_explicit_and_never_claimed_as_provider_meter(declared):
    increment = declared['future_increments'][0]
    increment.update(workload='nightly', measurement='protocol_bytes', inclusion='additional_future',
                     bytes_per_unit=quantity(10_000_000), remaining_units=1)
    report = evaluate(reseal(declared))
    assert report['status'] == 'CANDIDATE_FOR_OWNER_REVIEW'
    assert report['measurements']['cycle_projection_upper_bytes'] == 3_110_000_000
    assert report['measurements']['additional_future_protocol_proxy_upper_bytes'] == 10_000_000
    assert report['projection_basis']['protocol_future'] == 'CONSERVATIVE_PLANNING_PROXY_NOT_BILLED_BYTES'


def protocol_profile(packet):
    for section in [*(day['social'] for day in packet['days']), packet['cycle_social']]:
        section['measurement'] = 'protocol_bytes'
        section['receipt']['kind'] = 'social_protocol_measurement'
    packet['future_increments'][0]['measurement'] = 'protocol_bytes'
    return packet


@pytest.mark.parametrize('inclusion', ['already_in_provider_total', 'additional_future'])
@pytest.mark.parametrize('rounding,resolution', [('exact', 0), ('up', 2)])
def test_observed_red_521_positive_future_worker_units_cannot_claim_zero_protocol(declared, inclusion, rounding, resolution):
    protocol_profile(declared)
    declared['future_increments'][0].update(inclusion=inclusion, remaining_units=100,
        bytes_per_unit=quantity(0, rounding=rounding, resolution=resolution))
    report = evaluate(reseal(declared))
    assert report['status'] == 'BLOCKED'
    assert 'FUTURE_PROTOCOL_TRANSFER_CONTRADICTS_UNITS' in report['unknowns']


@pytest.mark.parametrize('inclusion', ['already_in_provider_total', 'additional_future'])
@pytest.mark.parametrize('control', ['zero_units', 'provider_zero', 'rounded_protocol'])
def test_521_future_zero_controls_preserve_distinct_declared_meanings(declared, inclusion, control):
    if control != 'provider_zero': protocol_profile(declared)
    declared['future_increments'][0].update(inclusion=inclusion,
        remaining_units=0 if control == 'zero_units' else 100,
        bytes_per_unit=quantity(0, rounding='nearest', resolution=2) if control == 'rounded_protocol' else quantity(0))
    report = evaluate(reseal(declared))
    assert report['status'] == 'CANDIDATE_FOR_OWNER_REVIEW'
    assert report['measurements']['additional_future_upper_bytes'] == (100 if inclusion == 'additional_future' and control == 'rounded_protocol' else 0)


@pytest.mark.parametrize('start,cycle_end,as_of,window_seconds', [
    ('2026-10-08', '2026-11-08', datetime(2026, 10, 15, 12, tzinfo=ZoneInfo('America/New_York')), 604800),
    ('2026-10-28', '2026-11-28', datetime(2026, 11, 4, 12, tzinfo=ZoneInfo('America/New_York')), 608400),
])
def test_exact_cycle_and_civil_days_keep_dst_seconds(declared, start, cycle_end, as_of, window_seconds):
    zone = ZoneInfo('America/New_York')
    first = datetime.fromisoformat(start).replace(tzinfo=zone)
    declared['identity'].update(timezone='America/New_York', cycle_start=start, cycle_end=cycle_end)
    for index, day in enumerate(declared['days']):
        begin = first + timedelta(days=index); finish = begin + timedelta(days=1)
        seconds = int((finish.astimezone(timezone.utc) - begin.astimezone(timezone.utc)).total_seconds())
        day['date'] = begin.date().isoformat()
        for key in ('provider', 'activity', 'social'):
            day[key].update(period_start=begin.isoformat(), period_end=finish.isoformat())
        day['activity'].update(worker_uptime_seconds=seconds, worker_covered_seconds=seconds)
    for key in ('cycle_usage', 'cycle_social'):
        declared[key].update(period_start=first.isoformat(), period_end=as_of.isoformat())
    finish = first + timedelta(days=7)
    declared['hosting']['deployed_at'] = first.isoformat()
    declared['query_counters'].update(start_at=first.isoformat(), end_at=finish.isoformat())
    for increment in declared['future_increments']:
        increment.update(period_start=first.isoformat(), period_end=finish.isoformat())
    for section in sections(declared): section['receipt']['captured_at'] = as_of.isoformat()
    report = evaluate(reseal(declared), as_of)
    assert report['status'] == 'CANDIDATE_FOR_OWNER_REVIEW'
    assert report['measurements']['cycle_seconds'] == 31 * 86400 + 3600
    assert report['measurements']['window_seconds'] == window_seconds


@pytest.mark.parametrize('section', ['hosting', 'cycle_usage', 'cycle_social', 'query_counters'])
@pytest.mark.parametrize('value', [None, [], True, 'DO-NOT-PRINT'])
def test_wrong_section_shapes_return_sanitized_blocked(declared, section, value):
    declared[section] = value
    report = evaluate(declared)
    assert report['status'] == 'BLOCKED'
    assert 'DO-NOT-PRINT' not in json.dumps(report)


def test_removing_synthetic_flags_does_not_remove_visible_fixture_markers():
    packet = json.loads(FIXTURE.read_text()); packet['synthetic'] = False
    for section in sections(packet): section['receipt']['synthetic'] = False
    assert 'SYNTHETIC_MARKERS_REMAIN' in evaluate(reseal(packet))['unknowns']


@pytest.mark.parametrize('body,code', [('', 'INPUT_TOO_LARGE_OR_EMPTY'), ('{"x":1,"x":2}', 'DUPLICATE_JSON_KEY'),
    ('{"x":NaN}', 'NONFINITE_JSON'), ('{"x":Infinity}', 'NONFINITE_JSON'), ('{bad}', 'JSON_READ_FAILED'),
    ('x' * (budget.MAX_BYTES + 1), 'INPUT_TOO_LARGE_OR_EMPTY')])
def test_strict_json_reader(tmp_path, body, code):
    source = tmp_path / 'input.json'; source.write_text(body)
    with pytest.raises(budget.EvidenceError, match=code): budget.load_json(source)


def test_observed_root_red_named_pipe_is_rejected_without_waiting(tmp_path, declared):
    # Root's first-draft subprocess timed out while opening a .json FIFO.
    fifo = tmp_path / 'pipe.json'; os.mkfifo(fifo)
    args = cli_args(tmp_path, declared); args[1] = str(fifo)
    result = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=1)
    assert result.returncode == 2
    assert json.loads(result.stdout)['unknowns'] == ['REGULAR_FILE_REQUIRED']


def test_symlink_directory_device_missing_and_exception_context_are_safe(tmp_path):
    regular = tmp_path / 'regular.json'; regular.write_text('{}')
    symlink = tmp_path / 'link.json'; symlink.symlink_to(regular)
    directory = tmp_path / 'directory.json'; directory.mkdir()
    for path in (symlink, directory, Path('/dev/null'), tmp_path / 'DO-NOT-PRINT.json'):
        with pytest.raises(budget.EvidenceError) as error:
            budget.load_json(path)
        assert 'DO-NOT-PRINT' not in str(error.value)
        assert error.value.__context__ is None


def test_actual_device_descriptor_is_rejected_by_fstat(tmp_path, monkeypatch):
    original_open = os.open
    monkeypatch.setattr(budget.os, 'open', lambda path, flags: original_open('/dev/null', flags))
    with pytest.raises(budget.EvidenceError, match='REGULAR_FILE_REQUIRED'):
        budget.load_json(tmp_path / 'device.json')


def cli_args(tmp_path, packet):
    source, expected = tmp_path / 'packet.json', tmp_path / 'identity.json'
    source.write_text(json.dumps(packet)); expected.write_text(json.dumps(packet['identity']))
    return ['--packet', str(source), '--expected-identity', str(expected), '--as-of', AS_OF.isoformat()]


def test_cli_help_defaults_hostile_environment_and_no_external_calls(tmp_path, declared, monkeypatch, capsys):
    monkeypatch.setattr(socket, 'socket', lambda *a, **k: pytest.fail('offline evaluator opened a socket'))
    monkeypatch.setenv('DATABASE_URL', 'postgresql://DO-NOT-PRINT@remote.invalid/db')
    monkeypatch.setenv('PRODUCTION_DIAGNOSTIC_DATABASE_URL', 'postgresql://DO-NOT-PRINT@remote.invalid/db')
    assert budget.main([]) == 2
    assert 'CLI_ARGUMENTS_INVALID' in capsys.readouterr().out
    assert budget.main(cli_args(tmp_path, declared)) == 0
    assert 'DO-NOT-PRINT' not in capsys.readouterr().out
    help_result = subprocess.run([sys.executable, str(TOOL), '--help'], capture_output=True, text=True)
    assert help_result.returncode == 0 and 'No live collection' in help_result.stdout
    hostile = subprocess.run([sys.executable, str(TOOL), '--password=DO-NOT-PRINT'], capture_output=True, text=True)
    assert hostile.returncode == 2 and 'DO-NOT-PRINT' not in hostile.stdout + hostile.stderr


def test_cli_report_readback_provenance_and_no_overwrite(tmp_path, declared, capsys):
    args = cli_args(tmp_path, declared)
    out = tmp_path / 'report.json'
    assert budget.main(args + ['--out', str(out)]) == 0
    displayed = json.loads(capsys.readouterr().out)
    assert json.loads(out.read_text()) == displayed
    assert displayed['input_sha256'] == budget.content_hash(declared)
    before = out.read_bytes()
    assert budget.main(args + ['--out', str(out)]) == 2
    assert out.read_bytes() == before
    capsys.readouterr()
    assert budget.main(args + ['--out', args[1]]) == 2
    assert 'OUTPUT_INPUT_COLLISION' in capsys.readouterr().out


def test_cli_synthetic_nonexistent_malformed_paths_and_error_redaction(tmp_path, capsys):
    packet = json.loads(FIXTURE.read_text())
    assert budget.main(cli_args(tmp_path, packet)) == 1
    assert json.loads(capsys.readouterr().out)['unknowns'] == ['SYNTHETIC_EVIDENCE']
    args = cli_args(tmp_path, packet); args[1] = str(tmp_path / 'DO-NOT-PRINT.json')
    assert budget.main(args) == 2
    assert 'DO-NOT-PRINT' not in capsys.readouterr().out


@pytest.mark.parametrize('failure', ['arguments', 'input', 'output'])
def test_observed_red_cli_failures_retain_unverified_evidence_provenance(tmp_path, declared, capsys, failure):
    args = cli_args(tmp_path, declared)
    if failure == 'arguments': args = ['--unknown=DO-NOT-PRINT']
    elif failure == 'input': Path(args[1]).unlink()
    else:
        destination = tmp_path / 'existing.json'; destination.write_text('DO-NOT-PRINT')
        args += ['--out', str(destination)]
    assert budget.main(args) == 2
    displayed = capsys.readouterr().out
    report = json.loads(displayed)
    assert report['status'] == 'BLOCKED' and report['production_authorized'] is False
    assert report['evidence_authentication'] == 'UNVERIFIED_OPERATOR_ASSERTIONS'
    assert 'DO-NOT-PRINT' not in displayed
