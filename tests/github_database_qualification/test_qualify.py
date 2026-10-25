import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parents[2] / 'scripts/verification/github_database_qualify.py'
spec = importlib.util.spec_from_file_location('github_qualify', PATH)
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)
URL = 'postgresql://postgres.'+q.PROJECT+':private-fixture@aws-1-eu-central-1.pooler.supabase.com:6543/postgres'


@pytest.mark.parametrize('value', [None, '', True, 4, 'host=x', URL+'?hostaddr=127.0.0.1',
    URL+'?sslmode=disable', URL+'?sslmode=require&sslmode=require', URL+'?service=other',
    URL.replace(q.PROJECT, 'otherproject'), URL.replace(':6543', ':5433'),
    URL.replace('/postgres', '/other'), URL+'#extra', URL+'?sslmode',
    URL+'?sslmode=%ZZ', URL.replace('private-fixture', ''), URL+'\n',
    URL.replace('/postgres', '/%70ostgres'), URL.replace('private-fixture','raw@password')])
def test_wrong_target_and_options_refuse_before_connect(value):
    with pytest.raises(q.Refused):
        q.connection_options(value)


@pytest.mark.parametrize('suffix', ['', '?sslmode=require', '?sslmode=verify-full'])
def test_expected_pooler_uses_verified_tls_and_bounded_read_only_startup(suffix):
    options = q.connection_options(URL+suffix)
    assert options['sslmode'] == 'verify-full'
    assert options['hostaddr'] == '' and options['gssencmode'] == 'disable'
    assert options['connect_timeout'] == 5
    assert options['options'] == '-c default_transaction_read_only=on -c statement_timeout=3000'
    assert options['password'] == 'private-fixture'


def test_direct_project_endpoint_is_also_pinned():
    value = f'postgresql://postgres:private-fixture@db.{q.PROJECT}.supabase.co:5432/postgres'
    assert q.connection_options(value)['host'] == f'db.{q.PROJECT}.supabase.co'


class Connection:
    def __init__(self, results=None, tls=True):
        self.results = results if results is not None else [
            [('postgres','postgres','postgres',5,170006,'on','repeatable read',False)],
            [(q.CLUSTER,)], [(q.REVISION,)], [(12345,)]]
        self.info = SimpleNamespace(ssl_in_use=tls, ssl_attribute=lambda name:'TLSv1.3',
            dsn_parameters={'sslmode':'verify-full','sslrootcert':'/owned/fixture-ca'})
        self.commands = []
        self.closed = self.rolled_back = False

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, sql):
        self.commands.append(sql)

    def fetchmany(self, count):
        assert count == 2
        return self.results.pop(0)

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_four_reads_close_and_rollback_before_success():
    connection = Connection()
    result = q.collect(connection)
    assert result['read_only'] is result['tls_verified'] is True
    assert result['catalog_reads'] == 4
    assert connection.closed and connection.rolled_back
    assert connection.commands == ['BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY',
                                    *q.SETTINGS, *q.READS]


@pytest.mark.parametrize('which,value', [(0, []), (0, [('other',)*8]), (1, [('other',)]),
    (2, []), (2, [(q.REVISION,), (q.REVISION,)]), (2, [('other',)]),
    (3, []), (3, [(True,)]), (3, [(0,)]), (3, [(-1,)]), (3, [(float('nan'),)]),
    (3, [(float('inf'),)]), (3, [(2**63,)])])
def test_partial_or_wrong_catalog_never_passes(which, value):
    connection = Connection()
    connection.results[which] = value
    with pytest.raises(q.Refused):
        q.collect(connection)
    assert connection.closed and connection.rolled_back


@pytest.mark.parametrize('change', [{3:True}, {4:True}, {5:'off'}, {7:0}])
def test_hostile_identity_types_and_writable_session_refuse(change):
    connection = Connection()
    identity = list(connection.results[0][0])
    for index,value in change.items():
        identity[index] = value
    connection.results[0] = [tuple(identity)]
    with pytest.raises(q.Refused):
        q.collect(connection)


def test_missing_tls_and_failed_cleanup_cannot_report_success():
    connection = Connection(tls=False)
    with pytest.raises(q.Refused):
        q.collect(connection)
    connection = Connection()
    def refuse():
        raise RuntimeError('synthetic cleanup refusal')
    connection.rollback = refuse
    with pytest.raises(RuntimeError):
        q.collect(connection)
    assert connection.closed


@pytest.mark.parametrize('result', [SimpleNamespace(returncode=2,stdout='private-fixture',stderr='private-fixture'),
    SimpleNamespace(returncode=0,stdout='{}',stderr=''),
    SimpleNamespace(returncode=0,stdout='not-json',stderr='')])
def test_bad_child_output_is_sanitized(monkeypatch, capsys, result):
    monkeypatch.setattr(q.subprocess, 'run', lambda *a,**kw: result)
    assert q.main(['--all']) == 2
    output = capsys.readouterr().out
    assert 'private-fixture' not in output
    assert json.loads(output)['qualification'] == 'refused'


def test_child_timeout_is_refused(monkeypatch, capsys):
    monkeypatch.setattr(q.tls, 'connection_args', lambda:{'sslmode':'verify-full'})
    def run(*args, **kwargs):
        assert kwargs['timeout'] == 20
        assert 'DATABASE_POOLER_URL' not in kwargs['env']
        raise q.subprocess.TimeoutExpired('private-fixture',20)
    monkeypatch.setattr(q.subprocess, 'run', run)
    assert q.main(['--seed']) == 2
    assert 'private-fixture' not in capsys.readouterr().out


def test_direct_collector_does_not_certify_unverified_tls():
    connection = Connection()
    connection.info.dsn_parameters['sslmode'] = 'require'
    with pytest.raises(q.Refused, match='TLS_REFUSED'):
        q.collect(connection)
    assert connection.closed and connection.rolled_back
