"""Benchmark targets must be explicit and local before any connection exists."""
import importlib.util
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine

import harness
from harness import local_url


@pytest.mark.parametrize('url',[
    '', 'sqlite://', 'mysql://localhost/social_worker_test',
    'postgresql+asyncpg://localhost:62124/social_worker_test',
    'postgresql://user:PRIVATE@production.invalid:62124/social_worker_test',
    'postgresql://localhost:5432/social_worker_test',
    'postgresql://localhost:62124/audit_app',
    'postgresql://localhost:62124/social_domain_test',
])
def test_benchmark_rejects_every_unassigned_target_without_connecting(url):
    with pytest.raises(ValueError):
        local_url(url)


def test_benchmark_names_synchronous_driver_for_explicit_assigned_target():
    assert local_url('postgresql://localhost:62124/social_worker_test').drivername=='postgresql+psycopg2'


def test_encoded_password_question_mark_is_not_query_syntax():
    url=local_url('postgresql://fixture:p%3Fss@localhost:62124/social_worker_test')
    engine=create_engine(url)
    try:
        _,parameters=engine.dialect.create_connect_args(url)
        assert parameters['password']=='p?ss'
        assert parameters['host']==parameters['hostaddr']=='127.0.0.1'
    finally:
        engine.dispose()


@pytest.mark.parametrize('query',[
    'host=remote.invalid', 'hostaddr=192.0.2.1', 'service=production',
    '', 'host=', 'hostaddr=', 'service=',
    'port=5432', 'dbname=production', 'database=production',
    '%68ost=remote.invalid', 'host=127.0.0.1&host=remote.invalid',
    'options=-csearch_path%3Dpublic', 'sslmode=disable',
])
def test_query_options_are_rejected_before_any_engine_is_created(monkeypatch,query):
    def forbidden_engine(*args,**kwargs):
        raise AssertionError('No engine may be constructed for unvalidated query options')
    monkeypatch.setattr(harness,'create_engine',forbidden_engine)
    with pytest.raises(ValueError):
        with harness.isolated_engine('postgresql://localhost:62124/social_worker_test?'+query):
            pytest.fail('An unvalidated target reached the fixture')


@pytest.mark.parametrize('authority,expected',[
    ('localhost','127.0.0.1'), ('127.0.0.1','127.0.0.1'), ('[::1]','::1'),
])
def test_effective_driver_arguments_pin_loopback_despite_libpq_environment(monkeypatch,authority,expected):
    # Inspect actual dialect arguments without opening a database connection.
    for key,value in {'PGHOST':'remote.invalid','PGHOSTADDR':'192.0.2.1',
                      'PGPORT':'5432','PGDATABASE':'production','PGSERVICE':'production'}.items():
        monkeypatch.setenv(key,value)
    url=local_url('postgresql://'+authority+':62124/social_worker_test')
    engine=create_engine(url)
    try:
        positional,parameters=engine.dialect.create_connect_args(url)
        assert positional==[]
        assert parameters['host']==expected
        assert parameters.get('hostaddr')==expected
        assert parameters['port']==62124 and parameters['dbname']=='social_worker_test'
        assert 'service' not in parameters
    finally:
        engine.dispose()


def test_benchmark_cli_rejects_override_before_all_measurement_paths(monkeypatch,capsys):
    path=Path(__file__).resolve().parents[3]/'docs/infrastructure/supabase-egress/batch2-egress/benchmark.py'
    spec=importlib.util.spec_from_file_location('egress_guarded_benchmark',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entered=[]
    def forbidden_measurement(*args):
        entered.append(True)
        raise AssertionError('An unsafe connection reached measurement')
    for name in ('measure_stats','measure_writers','measure_worker'):
        monkeypatch.setattr(module,name,forbidden_measurement)
    monkeypatch.setenv('DATABASE_URL','explicit-unused-fixture-value')
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED','1')
    monkeypatch.setattr('sys.argv',['benchmark.py','--database-url',
        'postgresql://fake:PRIVATE_PASSWORD@localhost:62124/social_worker_test?hostaddr=192.0.2.1'])
    assert module.main()==1
    assert entered==[]
    output=capsys.readouterr()
    assert json.loads(output.err)=={'outcome':'benchmark_failed','error_type':'ValueError'}
    assert output.out=='' and 'PRIVATE_PASSWORD' not in output.err
