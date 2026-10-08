"""Bounded collection uses fake drivers; no production configuration or services."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'scripts/verification'))
import social_operating_collect as collect
import social_operating_prepare as prepare
import evaluate_social_operating_budget as budget

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
PAST = NOW-timedelta(days=30)


@pytest.fixture
def config():
    return {'schema_version': 1, 'project_id': 'a'*20, 'database_name': 'postgres',
            'expected_database_oid': 5, 'stats_schema': 'public',
            'queries': [{'userid': 10, 'queryid': -123, 'toplevel': True}]}


@pytest.fixture
def private_file(tmp_path):
    cert = tmp_path/'ca.crt'; cert.write_text('fixture certificate')
    credentials = tmp_path/'credentials.json'
    credentials.write_text(json.dumps({'user': 'egress_reader', 'password': 'SECRET_SENTINEL', 'sslrootcert': str(cert)}))
    credentials.chmod(0o600)
    return credentials


class Driver:
    def __init__(self):
        self.rows = []
        self.executed = []
        self.closed = self.rolled_back = False
        self.identity = (NOW, 'postgres', 5, 'egress_reader', 'egress_reader', 'on', '5s', '1s', 170000, False, False, False, False)
        self.extension = ('public', '1.11', True, True)
        self.info = (NOW+timedelta(seconds=1), PAST, 0)
        self.query = (NOW+timedelta(seconds=2), 10, 20, PAST)
        self.end = (NOW+timedelta(seconds=3),)
        self.fail = None
        self.extra = False
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def cursor(self): return self
    def execute(self, sql, params=None):
        self.executed.append((sql,params))
        if self.fail: raise RuntimeError('SECRET_SENTINEL dsn=private-token')
        if sql == collect.BEGIN: self.rows = []
        elif sql == collect.IDENTITY_SQL: self.rows = [self.identity]
        elif sql == collect.EXTENSION_SQL: self.rows = [self.extension]
        elif sql == collect.INFO_SQL['public']: self.rows = [self.info]
        elif sql == collect.CLOCK_SQL: self.rows = [self.end]
        elif sql in [collect.STATS_SQL['public'].format(history=h) for h in ['stats_since','NULL::timestamptz']]:
            assert params == (5,10,-123,True)
            self.rows = [self.query] if self.query else []
        else: raise AssertionError('SQL outside fixed allowlist')
        if self.extra: self.rows = self.rows*3
    def fetchmany(self, size):
        assert size == 3
        return self.rows[:size]
    def rollback(self): self.rolled_back = True
    def close(self): self.closed = True


def run(config, private_file, driver=None):
    driver = driver or Driver()
    kwargs = []
    def connect(**values): kwargs.append(values); return driver
    report = collect.collect(config, credential_file=private_file, execute=True, connect=connect)
    assert driver.closed and driver.rolled_back
    assert 'SECRET_SENTINEL' not in json.dumps(report)
    assert report['production_authorized'] is False
    return report, kwargs, driver


def test_actual_path_guards_identity_and_emitted_binding(config, private_file):
    report, kwargs, driver = run(config, private_file)
    assert report['status'] == 'OBSERVED_COUNTERS_ONLY'
    assert report['session_observation'] == 'INJECTED_TEST_DRIVER'
    assert report['artifact_authentication'] == 'UNVERIFIED_WHEN_IMPORTED'
    assert not report['provider_meter_authenticated'] and not report['caller_attribution_verified']
    assert report['payload_sha256'] == budget.content_hash(report['snapshot'])
    assert budget.instant(report['captured_at']) >= budget.instant(report['snapshot']['snapshot_end'])
    assert kwargs[0]['sslmode'] == 'verify-full' and kwargs[0]['connect_timeout'] == 5
    assert kwargs[0]['host'] == 'db.'+'a'*20+'.supabase.co'
    assert kwargs[0]['application_name'] == 'auditgava-egress-readonly'
    assert driver.executed[0] == (collect.BEGIN,None)


def test_default_is_inert_even_with_absent_credentials(config, monkeypatch):
    monkeypatch.setattr(collect, '_read_private', lambda *a: pytest.fail('credential read'))
    report = collect.collect(config, credential_file=None, connect=lambda **k: pytest.fail('network'))
    assert report['status'] == 'PLAN_ONLY'


@pytest.mark.parametrize('bad', [None,[],{},True,1,'garbage',float('nan')])
def test_invalid_configs_never_connect(config, bad):
    report = collect.collect(bad,credential_file=None,execute=True,connect=lambda **k: pytest.fail('network'))
    assert report['status'] == 'BLOCKED'


@pytest.mark.parametrize('field,bad', [
    ('schema_version',True), ('schema_version',2), ('project_id','x; SELECT * FROM audits'),
    ('database_name','postgres\nSECRET_SENTINEL'), ('expected_database_oid',True),
    ('expected_database_oid',0), ('expected_database_oid',float('nan')),
    ('stats_schema','public; DROP TABLE audits'), ('queries',None), ('queries',[]),
    ('queries',[{}]), ('queries',[{'userid':10,'queryid':1,'toplevel':1}]),
    ('queries',[{'userid':False,'queryid':1,'toplevel':True}]),
    ('queries',[{'userid':10,'queryid':float('inf'),'toplevel':True}]),
    ('queries',[{'userid':10,'queryid':2**63,'toplevel':True}]),
])
def test_allowlist_shape_sql_and_numbers(config, field, bad):
    config[field] = bad
    assert collect.collect(config,credential_file=None,execute=True)['status'] == 'BLOCKED'


def test_query_count_and_duplicate_caps(config):
    config['queries'] *= 51
    assert collect.collect(config,credential_file=None,execute=True)['unknowns'] == ['QUERY_ALLOWLIST_REQUIRED']
    config['queries'] = config['queries'][:2]
    assert collect.collect(config,credential_file=None,execute=True)['unknowns'] == ['DUPLICATE_QUERY_ID']


@pytest.mark.parametrize('index,bad', [(1,'other'),(2,6),(2,True),(3,'postgres'),(4,'other'),(5,'off'),(6,'0'),(7,'0'),(9,True),(10,True),(11,True),(12,True),(9,None)])
def test_wrong_scope_privileges_and_guards(config, private_file, index, bad):
    driver=Driver(); values=list(driver.identity); values[index]=bad; driver.identity=tuple(values)
    assert run(config, private_file,driver)[0]['status'] == 'BLOCKED'


@pytest.mark.parametrize('index,bad', [(1,True),(1,-1),(1,None),(2,float('nan')),(3,NOW+timedelta(seconds=1)),(0,None)])
def test_invalid_counter_rows(config,private_file,index,bad):
    driver=Driver(); values=list(driver.query); values[index]=bad; driver.query=tuple(values)
    assert run(config,private_file,driver)[0]['status'] == 'BLOCKED'


def test_missing_query_and_unsupported_history_stay_partial(config,private_file):
    driver=Driver(); driver.query=None
    assert run(config,private_file,driver)[0]['status'] == 'PARTIAL_OBSERVATION'
    driver=Driver(); driver.extension=('public','1.10',False,False); driver.query=(*driver.query[:3],None)
    result=run(config,private_file,driver)[0]
    assert result['status'] == 'PARTIAL_OBSERVATION'
    assert result['snapshot']['info_before'] is None


def test_row_cap_and_failure_redaction(config,private_file):
    driver=Driver(); driver.extra=True
    assert run(config,private_file,driver)[0]['unknowns'] == ['SOURCE_ROW_CAP_EXCEEDED']
    driver=Driver(); driver.fail=True
    assert run(config,private_file,driver)[0]['unknowns'] == ['COLLECTION_FAILED']


@pytest.mark.parametrize('kind',['absent','empty','malformed','duplicate','broad_mode','symlink','fifo','privileged'])
def test_private_files_refused_sanitized(config,private_file,tmp_path,kind):
    if kind=='absent': private_file.unlink()
    elif kind=='empty': private_file.write_text('')
    elif kind=='malformed': private_file.write_text('{"password":"SECRET_SENTINEL",')
    elif kind=='duplicate': private_file.write_text('{"password":"SECRET_SENTINEL","password":"x"}')
    elif kind=='broad_mode': private_file.chmod(0o644)
    elif kind=='symlink':
        other=tmp_path/'link.json'; other.symlink_to(private_file); private_file=other
    elif kind=='fifo': private_file.unlink(); os.mkfifo(private_file)
    elif kind=='privileged':
        data=json.loads(private_file.read_text()); data['user']='postgres'; private_file.write_text(json.dumps(data))
    result=collect.collect(config,credential_file=private_file,execute=True,connect=lambda **k: pytest.fail('connection'))
    assert result['status']=='BLOCKED' and 'SECRET_SENTINEL' not in json.dumps(result)


def test_private_decoder_has_no_exception_context(private_file):
    private_file.write_text('{"password":"SECRET_SENTINEL",')
    with pytest.raises(budget.EvidenceError) as caught: collect._read_private(private_file)
    assert caught.value.__context__ is None and 'SECRET_SENTINEL' not in str(caught.value)


def test_libpq_environment_cannot_redirect(config,private_file,monkeypatch):
    monkeypatch.setenv('PGHOSTADDR','192.0.2.1')
    assert collect.collect(config,credential_file=private_file,execute=True)['unknowns']==['LIBPQ_ENVIRONMENT_REFUSED']


def test_cli_no_side_effect_default_and_exclusive_output(config,tmp_path):
    source=tmp_path/'config.json'; source.write_text(json.dumps(config))
    tool=ROOT/'scripts/verification/social_operating_collect.py'
    proc=subprocess.run([sys.executable,str(tool),'--config',str(source),'--credential-file','ABSENT'],capture_output=True,text=True,timeout=5)
    assert proc.returncode==0 and json.loads(proc.stdout)['status']=='PLAN_ONLY'
    source_before=source.read_bytes()
    proc=subprocess.run([sys.executable,str(tool),'--config',str(source),'--out',str(source)],capture_output=True,text=True,timeout=5)
    assert proc.returncode==2 and source.read_bytes()==source_before
    for args in [[],['--config','SECRET_SENTINEL'],['--bad','SECRET_SENTINEL']]:
        proc=subprocess.run([sys.executable,str(tool),*args],capture_output=True,text=True,timeout=5)
        assert proc.returncode==2 and 'SECRET_SENTINEL' not in proc.stdout+proc.stderr


def snapshots(config,private_file):
    before=run(config,private_file)[0]
    after=deepcopy(before)
    snap=after['snapshot']
    for key in ('snapshot_start','snapshot_end'): snap[key]=(budget.instant(snap[key])+timedelta(days=1)).isoformat()
    for key in ('info_before','info_after'): snap[key]['observed_at']=(budget.instant(snap[key]['observed_at'])+timedelta(days=1)).isoformat()
    for entry in snap['entries']:
        entry['observed_at']=(budget.instant(entry['observed_at'])+timedelta(days=1)).isoformat()
        entry['calls']+=2; entry['rows']+=3
    after['captured_at']=snap['snapshot_end']; after['payload_sha256']=budget.content_hash(snap)
    return before,after


def get_delta(before,after):
    return prepare.delta(before,after,expected_database_sha256=before['snapshot']['database_sha256'],
        start_at=before['snapshot']['snapshot_end'],end_at=after['snapshot']['snapshot_start'],
        as_of=NOW+timedelta(days=1,seconds=30))


def test_delta_positive_is_unverified_bracket_not_bill(config,private_file):
    before,after=snapshots(config,private_file)
    # Actual capture can be later than this hypothetical as-of: give an explicit
    # time beyond both retained captures, without altering endpoint evidence.
    before['captured_at']=before['snapshot']['snapshot_end']
    result=get_delta(before,after)
    assert result['status']=='DECLARED_COUNTER_DELTA_ONLY'
    assert result['entries'][0]['calls_delta']==2 and result['entries'][0]['rows_delta']==3
    assert result['interval_exact'] is False and not result['query_counters_are_billed_bytes']
    assert result['evidence_authentication']=='UNVERIFIED_OPERATOR_ASSERTIONS'


@pytest.mark.parametrize('mutation',['payload','wrong_database','reset','eviction','stats_since','decrease','missing','widened','copied','future_capture'])
def test_bad_imported_deltas(config,private_file,mutation):
    before,after=snapshots(config,private_file); before['captured_at']=before['snapshot']['snapshot_end']
    snap=after['snapshot']
    if mutation=='payload': snap['entries'][0]['calls']+=1
    elif mutation=='wrong_database': snap['source_identity']['database_oid']=6; snap['database_sha256']=budget.content_hash(snap['source_identity'])
    elif mutation=='reset': snap['info_after']['stats_reset']=(PAST+timedelta(days=1)).isoformat()
    elif mutation=='eviction': snap['info_after']['dealloc']+=1
    elif mutation=='stats_since': snap['entries'][0]['stats_since']=(PAST+timedelta(days=1)).isoformat()
    elif mutation=='decrease': snap['entries'][0]['calls']=0
    elif mutation=='missing': snap['entries'][0]['stats_since']=None
    elif mutation=='widened': snap['snapshot_start']=before['snapshot']['snapshot_start']
    elif mutation=='copied': after=deepcopy(before); snap=after['snapshot']
    elif mutation=='future_capture': after['captured_at']='2027-01-01T00:00:00Z'
    if mutation!='payload': after['payload_sha256']=budget.content_hash(snap)
    assert get_delta(before,after)['status']=='BLOCKED'


@pytest.fixture
def declared():
    packet=json.loads((ROOT/'docs/infrastructure/supabase-egress/fixtures/social-operating-synthetic.json').read_text())
    packet['identity']['organization_id']='test-org'; packet['identity']['project_id']='test-project'
    for day in packet['days']:
        for key in ('provider','activity','social'):
            section=day[key]; receipt=section['receipt']; receipt['synthetic']=False; receipt['observer']='test-observer'
            receipt['identity_sha256']=budget.content_hash(packet['identity'])
            receipt['payload_sha256']=budget.content_hash({k:v for k,v in section.items() if k!='receipt'})
    return packet


def covered(packet):
    return prepare.coverage(packet['days'],expected_identity=packet['identity'],first_day=packet['days'][0]['date'],
        as_of=datetime(2026,10,15,12,tzinfo=timezone.utc))


def test_coverage_seven_declared_days_still_never_accepts(declared):
    result=covered(declared)
    assert result['covered_days']==7 and result['status']=='BLOCKED'
    assert result['production_authorized'] is False


def test_seven_complete_slots_expose_missing_ordinary_workload(declared):
    for day in declared['days']:
        activity=day['activity']
        for key in ('api_requests','cache_hits','cache_misses','restarts','deployments','worker_publications'):
            activity[key]=0
        activity['receipt']['payload_sha256']=budget.content_hash({k:v for k,v in activity.items() if k!='receipt'})
    result=covered(declared)
    assert set(result['window_missing']) == {'REPRESENTATIVE_ACTIVITY_MISSING','RESTART_PROFILE_NOT_OBSERVED','CACHE_ACTIVITY_MISSING'}
    assert set(result['window_missing']) <= set(result['unknowns'])


def test_partial_coverage_preserves_missing_and_historical_spike(declared):
    first=declared['days'][0]; first['provider']['total_uncached']['value']=6_000_000_000
    first['provider']['services']['shared_pooler']['value']=6_000_000_000
    first['provider']['receipt']['payload_sha256']=budget.content_hash({k:v for k,v in first['provider'].items() if k!='receipt'})
    result=prepare.coverage([first],expected_identity=declared['identity'],first_day=first['date'],as_of=datetime(2026,10,15,12,tzinfo=timezone.utc))
    assert result['covered_days']==1 and result['ledger'][0]['provider_byte_bounds'][1]==6_000_000_000
    assert all(d['provider_byte_bounds'] is None for d in result['ledger'][1:])
    assert all(d['missing']==['DAY_MISSING'] for d in result['ledger'][1:])


@pytest.mark.parametrize('key',['provider','social','activity'])
def test_missing_sections_and_copied_days(declared,key):
    declared['days'][1][key]=deepcopy(declared['days'][0][key])
    assert covered(declared)['unknowns']==['RECEIPT_PERIOD_MISMATCH']
    declared['days'][1][key]=None
    assert covered(declared)['covered_days']==6


@pytest.mark.parametrize('mutate',['duplicate','not_closed','actions_off','no_worker','wrong_unit','bool','null','nan','wrong_scope'])
def test_coverage_hostile_shapes(declared,mutate):
    section=declared['days'][0]['activity']
    if mutate=='duplicate': declared['days'].append(deepcopy(declared['days'][0]))
    elif mutate=='not_closed': declared['days'][0]['complete']=False
    elif mutate=='actions_off': section['actions_enabled']=False
    elif mutate=='no_worker': section['worker_covered_seconds']=0
    elif mutate=='wrong_unit': declared['days'][0]['provider']['total_uncached']['unit']='KiB'
    elif mutate=='bool': section['api_requests']=True
    elif mutate=='null': section['api_requests']=None
    elif mutate=='nan': section['api_requests']=float('nan')
    elif mutate=='wrong_scope': declared['days'][0]['provider']['meter_scope']='project_only'
    section['receipt']['payload_sha256']=budget.content_hash({k:v for k,v in section.items() if k!='receipt'}) if mutate!='nan' else 'f'*64
    result=covered(declared)
    assert result.get('covered_days',0)<7 and result['status']=='BLOCKED'


@pytest.mark.parametrize('first,length',[('2026-03-07',82800),('2026-10-31',90000)])
def test_real_dst_slots(declared,first,length):
    identity=declared['identity']
    identity['timezone']='America/Chicago'
    identity['cycle_start']='2026-03-01' if first.startswith('2026-03') else '2026-10-08'
    identity['cycle_end']='2026-04-01' if first.startswith('2026-03') else '2026-11-08'
    as_of=datetime(2026,3,15,12,tzinfo=timezone.utc) if first.startswith('2026-03') else datetime(2026,11,8,0,tzinfo=timezone.utc)
    result=prepare.coverage([],expected_identity=identity,first_day=first,as_of=as_of)
    assert result['ledger'][1]['civil_seconds']==length
    assert sum(d['civil_seconds'] for d in result['ledger'])==6*86400+length
    assert result['covered_days']==0
