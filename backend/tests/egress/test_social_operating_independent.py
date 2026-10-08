"""Independent execution probes: supplied artifacts never authenticate themselves."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'scripts/verification'))
collector = importlib.import_module('social_operating_collect')
prepare = importlib.import_module('social_operating_prepare')
budget = collector.budget


def snapshot(start='2026-10-07T23:59:50Z', calls=10, rows=20):
    begin = budget.instant(start)
    source = {'project_endpoint': 'db.'+'a'*20+'.supabase.co',
              'database_name_sha256': 'a'*64, 'database_oid': 123,
              'reader_sha256': 'b'*64, 'server_version_num': 120000,
              'stats_schema': 'extensions', 'extension_version': '1.11',
              'tls_verification': 'verify-full'}
    return {'source_identity': source, 'database_sha256': budget.content_hash(source),
            'snapshot_start': begin.isoformat(),
            'snapshot_end': (begin+timedelta(seconds=4)).isoformat(),
            'info_before': {'observed_at': (begin+timedelta(seconds=1)).isoformat(),
                            'stats_reset': '2026-10-01T00:00:00+00:00', 'dealloc': 0},
            'info_after': {'observed_at': (begin+timedelta(seconds=3)).isoformat(),
                           'stats_reset': '2026-10-01T00:00:00+00:00', 'dealloc': 0},
            'entries': [{'query_sha256': 'c'*64,
                         'observed_at': (begin+timedelta(seconds=2)).isoformat(),
                         'calls': calls, 'rows': rows,
                         'stats_since': '2026-10-01T00:00:00+00:00'}],
            'unknowns': []}


def artifact(snap):
    report = collector._report()
    report.update(status='OBSERVED_COUNTERS_ONLY', snapshot=deepcopy(snap),
                  session_observation='INJECTED_TEST_DRIVER',
                  payload_sha256=budget.content_hash(snap), unknowns=deepcopy(snap['unknowns']),
                  captured_at=(budget.instant(snap['snapshot_end'])+timedelta(seconds=1)).isoformat())
    return report


@pytest.fixture
def pair():
    return artifact(snapshot()), artifact(snapshot('2026-10-09T00:00:10Z', 25, 50))


def delta(pair, **kwargs):
    return prepare.delta(*pair,
        expected_database_sha256=(kwargs['expected_database_sha256'] if 'expected_database_sha256' in kwargs
                                  else pair[0]['snapshot']['database_sha256']),
        start_at=kwargs.get('start_at', '2026-10-08T00:00:00Z'),
        end_at=kwargs.get('end_at', '2026-10-09T00:00:00Z'),
        as_of=kwargs.get('as_of', datetime(2026, 10, 9, 1, tzinfo=timezone.utc)))


def reseal(report):
    report['payload_sha256'] = budget.content_hash(report['snapshot'])
    report['unknowns'] = deepcopy(report['snapshot']['unknowns'])
    return report


@pytest.mark.parametrize('mutation', ['missing_infos', 'partial_infos', 'missing_since',
                                    'missing_query', 'changed_deallocation', 'changed_reset'])
def test_observed_red_validator_cannot_accept_missing_history_as_complete(mutation):
    value = snapshot()
    if mutation == 'missing_infos': value['info_before'] = value['info_after'] = None
    elif mutation == 'partial_infos': value['info_before'] = None
    elif mutation == 'missing_since': value['entries'][0]['stats_since'] = None
    elif mutation == 'missing_query':
        value['entries'][0].update(observed_at=None, calls=None, rows=None, stats_since=None)
    elif mutation == 'changed_deallocation': value['info_after']['dealloc'] = 1
    elif mutation == 'changed_reset': value['info_after']['stats_reset'] = '2026-10-02T00:00:00+00:00'
    with pytest.raises(budget.EvidenceError): collector.validate_snapshot(value)


@pytest.mark.parametrize('mutation', ['missing_infos', 'missing_since', 'missing_query', 'changed_deallocation'])
def test_declared_partial_history_remains_valid_without_certifying_completeness(mutation):
    value = snapshot()
    if mutation == 'missing_infos':
        value['info_before'] = value['info_after'] = None
        value['unknowns'] = ['RESET_AND_DEALLOCATION_UNAVAILABLE']
    elif mutation == 'missing_since':
        value['entries'][0]['stats_since'] = None
        value['unknowns'] = ['STATS_SINCE_UNAVAILABLE']
    elif mutation == 'missing_query':
        value['entries'][0].update(observed_at=None, calls=None, rows=None, stats_since=None)
        value['unknowns'] = ['ALLOWLISTED_QUERY_MISSING']
    else:
        value['info_after']['dealloc'] = 1
        value['unknowns'] = ['HISTORY_CHANGED_DURING_CAPTURE']
    assert collector.validate_snapshot(value) == value


def test_resealed_fabricated_delta_retains_unverified_authority(pair):
    pair[1]['snapshot']['entries'][0].update(calls=1_000_000, rows=2_000_000)
    reseal(pair[1])
    pair[0]['session_observation'] = pair[1]['session_observation'] = 'TLS_DATABASE_SESSION_READBACK'
    result = delta(pair)
    assert result['status'] == 'DECLARED_COUNTER_DELTA_ONLY'
    assert result['evidence_authentication'] == 'UNVERIFIED_OPERATOR_ASSERTIONS'
    assert result['production_authorized'] is False
    assert result['caller_attribution_verified'] is False
    assert result['provider_meter_authenticated'] is False
    assert result['interval_exact'] is False
    assert result['query_counters_are_billed_bytes'] is False
    assert 'IMPORTED_RECEIPTS_UNAUTHENTICATED' in result['unknowns']


def test_observed_red_equivalent_reset_offsets_do_not_invent_capture_reset():
    value = snapshot()
    value['info_after']['stats_reset'] = '2026-10-01T03:00:00+03:00'
    assert collector.validate_snapshot(value) == value


@pytest.mark.parametrize('history', ['stats_reset', 'stats_since'])
def test_observed_red_equivalent_history_offsets_preserve_declared_counter_delta(pair, history):
    if history == 'stats_reset':
        for key in ('info_before', 'info_after'):
            pair[1]['snapshot'][key][history] = '2026-10-01T03:00:00+03:00'
    else:
        pair[1]['snapshot']['entries'][0][history] = '2026-10-01T03:00:00+03:00'
    reseal(pair[1])
    result = delta(pair)
    assert result['status'] == 'DECLARED_COUNTER_DELTA_ONLY'
    assert result['production_authorized'] is False


@pytest.mark.parametrize('mutation', ['payload_tamper', 'claimed_authority', 'removed_infos',
                                    'missing_since', 'deallocation', 'counter_reset',
                                    'query_identity', 'wrong_database', 'counter_decrease'])
def test_counter_delta_blocks_tampering_resets_evictions_and_wrong_scope(pair, mutation):
    second = pair[1]
    if mutation == 'payload_tamper': second['snapshot']['entries'][0]['calls'] += 1
    elif mutation == 'claimed_authority': second['production_authorized'] = True
    elif mutation == 'removed_infos':
        second['snapshot']['info_before'] = second['snapshot']['info_after'] = None
        reseal(second)
    elif mutation == 'missing_since':
        second['snapshot']['entries'][0]['stats_since'] = None; reseal(second)
    elif mutation == 'deallocation':
        for key in ('info_before', 'info_after'): second['snapshot'][key]['dealloc'] = 1
        reseal(second)
    elif mutation == 'counter_reset':
        for key in ('info_before', 'info_after'): second['snapshot'][key]['stats_reset'] = '2026-10-02T00:00:00Z'
        reseal(second)
    elif mutation == 'query_identity':
        second['snapshot']['entries'][0]['query_sha256'] = 'f'*64; reseal(second)
    elif mutation == 'wrong_database':
        second['snapshot']['source_identity']['database_oid'] = 456
        second['snapshot']['database_sha256'] = budget.content_hash(second['snapshot']['source_identity'])
        reseal(second)
    elif mutation == 'counter_decrease':
        second['snapshot']['entries'][0]['calls'] = 9; reseal(second)
    result = delta(pair)
    assert result['status'] == 'BLOCKED'
    assert result['production_authorized'] is False


@pytest.mark.parametrize('field,value', [
    ('start_at', '2026-10-07T23:59:53Z'), ('end_at', '2026-10-09T00:00:11Z'),
    ('start_at', '2026-10-09T00:00:00Z'), ('start_at', None),
    ('end_at', '2026-11-01T01:30:00'), ('expected_database_sha256', 'f'*64),
    ('as_of', None), ('as_of', datetime(2026, 10, 9)),
])
def test_delta_rejects_widened_reverse_naive_or_unknown_bounds(pair, field, value):
    assert delta(pair, **{field: value})['status'] == 'BLOCKED'


@pytest.mark.parametrize('container', [None, [], True, 'FAKE_SECRET_SENTINEL', {}])
def test_delta_wrong_containers_are_sanitized(pair, container):
    result = delta((container, pair[1]), expected_database_sha256=pair[1]['snapshot']['database_sha256'])
    assert result['status'] == 'BLOCKED'
    assert 'FAKE_SECRET_SENTINEL' not in json.dumps(result)


@pytest.mark.parametrize('field,value', [('calls', None), ('rows', True), ('calls', -1),
                                       ('rows', float('nan')), ('rows', float('inf'))])
def test_delta_hostile_counter_values(pair, field, value):
    pair[1]['snapshot']['entries'][0][field] = value
    if isinstance(value, float):
        result = delta(pair)
    else:
        reseal(pair[1]); result = delta(pair)
    assert result['status'] == 'BLOCKED'


def declared_days():
    packet = json.loads((ROOT/'docs/infrastructure/supabase-egress/fixtures/social-operating-synthetic.json').read_text())
    packet['identity']['organization_id'] = 'operator-declared-org'
    packet['identity']['project_id'] = 'operator-declared-project'
    for day in packet['days']:
        for key in ('provider', 'activity', 'social'):
            receipt = day[key]['receipt']
            receipt.update(synthetic=False, observer='operator-declared-observer',
                identity_sha256=budget.content_hash(packet['identity']),
                payload_sha256=budget.content_hash({k:v for k,v in day[key].items() if k!='receipt'}))
    return packet['days'], packet['identity']


def coverage(days, identity=None, first_day='2026-10-08', as_of=None):
    return prepare.coverage(days, expected_identity=identity or declared_days()[1],
                            first_day=first_day,
                            as_of=as_of or datetime(2026,10,15,12,tzinfo=timezone.utc))


def seal_day(day, identity):
    for key in ('provider', 'activity', 'social'):
        if day[key] is not None:
            day[key]['receipt']['identity_sha256'] = budget.content_hash(identity)
            day[key]['receipt']['payload_sha256'] = budget.content_hash({k:v for k,v in day[key].items() if k!='receipt'})


def test_fabricated_coverage_does_not_authenticate_or_authorize():
    days, identity = declared_days()
    result = coverage(days, identity)
    assert result['covered_days'] == 7
    assert result['status'] == 'BLOCKED'
    assert result['production_authorized'] is False
    assert result['evidence_authentication'] == 'UNVERIFIED_OPERATOR_ASSERTIONS'
    assert 'FULL_OPERATING_ACCEPTANCE_PENDING' in result['unknowns']
    assert 'IMPORTED_RECEIPTS_UNAUTHENTICATED' in result['unknowns']


@pytest.mark.parametrize('section', ['provider', 'activity', 'social'])
def test_coverage_rejects_copied_daily_receipts(section):
    days, identity = declared_days()
    days[1][section] = deepcopy(days[0][section])
    result = coverage(days, identity)
    assert result['status'] == 'BLOCKED'
    assert result['unknowns'] == ['RECEIPT_PERIOD_MISMATCH']


@pytest.mark.parametrize('mutation', ['actions_disabled', 'nightly_missing', 'worker_missing',
                                    'incomplete_logs', 'zero_protocol', 'provider_missing'])
def test_coverage_marks_incomplete_or_contradictory_workloads(mutation):
    days, identity = declared_days()
    day = days[0]
    if mutation == 'actions_disabled': day['activity']['actions_enabled'] = False
    elif mutation == 'nightly_missing': day['activity']['nightly_runs'] = 0
    elif mutation == 'worker_missing': day['activity']['worker_covered_seconds'] = 0
    elif mutation == 'incomplete_logs': day['activity']['coverage_complete'] = False
    elif mutation == 'zero_protocol':
        for measured_day in days:
            measured_day['social']['measurement'] = 'protocol_bytes'
            measured_day['social']['receipt']['kind'] = 'social_protocol_measurement'
            seal_day(measured_day, identity)
        day['social']['transfer']['value'] = 0
    elif mutation == 'provider_missing': day['provider'] = None
    seal_day(day, identity)
    result = coverage(days, identity)
    assert result['covered_days'] == 6
    assert result['ledger'][0]['missing']


def test_coverage_blocks_mixed_social_measurement_bases():
    days, identity = declared_days()
    days[0]['social']['measurement'] = 'protocol_bytes'
    days[0]['social']['receipt']['kind'] = 'social_protocol_measurement'
    seal_day(days[0], identity)
    result = coverage(days, identity)
    assert result['status'] == 'BLOCKED'
    assert result['unknowns'] == ['SOCIAL_MEASUREMENT_SCOPE_MISMATCH']
    assert result['production_authorized'] is False


@pytest.mark.parametrize('mutation', ['duplicate_day', 'wrong_deployment', 'wrong_unit', 'bool',
                                    'negative', 'nan', 'missing_key', 'secret', 'wrong_shape'])
def test_coverage_rejects_hostile_shapes(mutation):
    days, identity = declared_days()
    if mutation == 'duplicate_day': days[1] = deepcopy(days[0])
    elif mutation == 'wrong_deployment': days[0]['deployment_sha'] = 'f'*40
    elif mutation == 'wrong_unit': days[0]['provider']['total_uncached']['unit'] = 'MiB'
    elif mutation == 'bool': days[0]['activity']['api_requests'] = True
    elif mutation == 'negative': days[0]['activity']['api_requests'] = -1
    elif mutation == 'nan': days[0]['activity']['api_requests'] = float('nan')
    elif mutation == 'missing_key': del days[0]['activity']['api_requests']
    elif mutation == 'secret': days[0]['password'] = 'FAKE_SECRET_SENTINEL'
    elif mutation == 'wrong_shape': days[0]['provider'] = ['FAKE_SECRET_SENTINEL']
    result = coverage(days, identity)
    assert result['status'] == 'BLOCKED'
    assert 'ledger' not in result
    assert 'FAKE_SECRET_SENTINEL' not in json.dumps(result)


@pytest.mark.parametrize('first_day,cycle_end,expected_seconds', [
    ('2026-03-05', '2026-04-05', 82800), ('2026-10-29', '2026-11-29', 90000),
])
def test_partial_coverage_preserves_real_civil_dst_seconds(first_day, cycle_end, expected_seconds):
    identity = declared_days()[1]
    identity.update(timezone='America/Chicago', cycle_start=first_day, cycle_end=cycle_end)
    result = coverage([], identity, first_day, budget.instant(cycle_end+'T00:00:00Z')-timedelta(days=1))
    assert len(result['ledger']) == 7 and result['covered_days'] == 0
    assert expected_seconds in [day['civil_seconds'] for day in result['ledger']]
    assert sum(day['civil_seconds'] for day in result['ledger']) == 6*86400+expected_seconds


def test_coverage_today_cannot_invent_post_rollout_complete_days():
    identity = declared_days()[1]
    result = coverage([], identity, as_of=datetime(2026,10,8,20,tzinfo=timezone.utc))
    assert result['covered_days'] == 0
    assert result['next_calendar_close'] == '2026-10-15T00:00:00+00:00'
    assert all(day['missing'] == ['DAY_MISSING'] for day in result['ledger'])


def test_direct_collector_plan_never_reads_credentials_or_opens_connection(monkeypatch):
    def forbidden(*args, **kwargs): pytest.fail('plan touched credential or connection')
    monkeypatch.setattr(collector, '_read_private', forbidden)
    config = {'schema_version':1, 'project_id':'a'*20, 'database_name':'postgres',
              'expected_database_oid':123, 'stats_schema':'extensions',
              'queries':[{'userid':111,'queryid':222,'toplevel':True}]}
    result = collector.collect(config, credential_file='/FAKE_SECRET_SENTINEL', connect=forbidden)
    assert result['status'] == 'PLAN_ONLY'
    assert result['production_authorized'] is False
    assert 'FAKE_SECRET_SENTINEL' not in json.dumps(result)


def private_credentials(tmp_path):
    cert = tmp_path/'reader-ca.pem'
    cert.write_text('FAKE CERTIFICATE FOR INJECTED DRIVER ONLY')
    file = tmp_path/'reader.json'
    file.write_text(json.dumps({'user':'egress_reader', 'password':'FAKE_SECRET_SENTINEL',
                                'sslrootcert':str(cert)}))
    file.chmod(0o600)
    return file


@pytest.mark.parametrize('case', ['missing', 'empty', 'bad_json', 'duplicate', 'nan', 'bad_shape',
                                 'extra_secret', 'privileged', 'bool_user', 'null_password',
                                 'large_password', 'null_certificate', 'public_mode', 'symlink',
                                 'directory', 'fifo', 'device', 'oversize'])
def test_private_credential_reader_rejects_hostile_inputs_without_secret_context(tmp_path, case):
    file = private_credentials(tmp_path)
    value = json.loads(file.read_text())
    if case == 'missing': file.unlink()
    elif case == 'empty': file.write_text('')
    elif case == 'bad_json': file.write_text('{FAKE_SECRET_SENTINEL')
    elif case == 'duplicate': file.write_text('{"user":"FAKE_SECRET_SENTINEL","user":"egress_reader"}')
    elif case == 'nan': file.write_text('{"password":NaN}')
    elif case == 'bad_shape': file.write_text('["FAKE_SECRET_SENTINEL"]')
    elif case == 'extra_secret': value['token']='FAKE_SECRET_SENTINEL'; file.write_text(json.dumps(value))
    elif case == 'privileged': value['user']='postgres'; file.write_text(json.dumps(value))
    elif case == 'bool_user': value['user']=True; file.write_text(json.dumps(value))
    elif case == 'null_password': value['password']=None; file.write_text(json.dumps(value))
    elif case == 'large_password': value['password']='x'*1025; file.write_text(json.dumps(value))
    elif case == 'null_certificate': value['sslrootcert']=None; file.write_text(json.dumps(value))
    elif case == 'public_mode': file.chmod(0o644)
    elif case == 'symlink':
        original=file; file=tmp_path/'link.json'; file.symlink_to(original)
    elif case == 'directory': file.unlink(); file.mkdir()
    elif case == 'fifo': file.unlink(); os.mkfifo(file, 0o600)
    elif case == 'device': file=Path('/dev/null')
    elif case == 'oversize': file.write_text('x'*8193)
    with pytest.raises(budget.EvidenceError) as error: collector._read_private(file)
    assert 'FAKE_SECRET_SENTINEL' not in str(error.value)
    assert error.value.__context__ is None


def test_plan_cli_no_sockets_or_credential_reads_in_hostile_environment(tmp_path, monkeypatch, capsys):
    config = {'schema_version':1, 'project_id':'a'*20, 'database_name':'postgres',
              'expected_database_oid':123, 'stats_schema':'extensions',
              'queries':[{'userid':111,'queryid':222,'toplevel':True}]}
    source=tmp_path/'config.json'; source.write_text(json.dumps(config))
    monkeypatch.setattr(socket, 'socket', lambda *a, **k: pytest.fail('plan opened a socket'))
    monkeypatch.setattr(collector, '_read_private', lambda *a, **k: pytest.fail('plan read credentials'))
    monkeypatch.setenv('DATABASE_URL', 'FAKE_SECRET_SENTINEL')
    monkeypatch.setenv('PGPASSWORD', 'FAKE_SECRET_SENTINEL')
    assert collector.main(['--config',str(source),'--credential-file',str(tmp_path/'missing.json')]) == 0
    output=capsys.readouterr().out
    assert json.loads(output)['status']=='PLAN_ONLY' and 'FAKE_SECRET_SENTINEL' not in output


@pytest.mark.parametrize('case', ['missing_config', 'hostile_argument', 'fifo', 'malformed', 'nonfinite', 'duplicate_key'])
def test_collector_cli_hostile_input_is_fast_sanitized_and_offline(tmp_path, case):
    source=tmp_path/'FAKE_SECRET_SENTINEL.json'
    arguments=['--config',str(source)]
    if case == 'hostile_argument': arguments=['--FAKE_SECRET_SENTINEL=token']
    elif case == 'fifo': os.mkfifo(source)
    elif case == 'malformed': source.write_text('{FAKE_SECRET_SENTINEL')
    elif case == 'nonfinite': source.write_text('{"bytes":Infinity}')
    elif case == 'duplicate_key': source.write_text('{"x":1,"x":2}')
    result=subprocess.run([sys.executable,str(ROOT/'scripts/verification/social_operating_collect.py'),*arguments],
                          capture_output=True,text=True,timeout=2,
                          env={**os.environ,'PYTHON_DOTENV_DISABLED':'1'})
    assert result.returncode==2
    assert json.loads(result.stdout)['status']=='BLOCKED'
    assert 'FAKE_SECRET_SENTINEL' not in result.stdout+result.stderr


def test_prepare_cli_fabricated_coverage_always_returns_nonacceptance(tmp_path):
    days,identity=declared_days()
    source=tmp_path/'days.json'; source.write_text(json.dumps(days))
    expected=tmp_path/'identity.json'; expected.write_text(json.dumps(identity))
    result=subprocess.run([sys.executable,str(ROOT/'scripts/verification/social_operating_prepare.py'),
        '--records',str(source),'--expected-identity',str(expected),'--first-day','2026-10-08',
        '--as-of','2026-10-15T12:00:00Z'],capture_output=True,text=True,timeout=2,
        env={**os.environ,'PYTHON_DOTENV_DISABLED':'1','DATABASE_URL':'FAKE_SECRET_SENTINEL'})
    report=json.loads(result.stdout)
    assert result.returncode==1 and report['covered_days']==7 and report['status']=='BLOCKED'
    assert report['production_authorized'] is False
    assert 'IMPORTED_RECEIPTS_UNAUTHENTICATED' in report['unknowns']
    assert 'FAKE_SECRET_SENTINEL' not in result.stdout+result.stderr
