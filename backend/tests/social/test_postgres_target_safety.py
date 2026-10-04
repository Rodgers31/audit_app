"""Exercise fixture entry points without opening any database connection."""
import importlib

import pytest
from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2
from sqlalchemy.engine import make_url

from local_postgres import local_postgres_url


FIXTURES = (
    ('test_domain_postgres', 'pg_engine', 'SOCIAL_TEST_DATABASE_URL', 'social_domain_test'),
    ('test_queue_postgres', 'engine', 'SOCIAL_WORKER_TEST_DATABASE_URL', 'social_worker_test'),
    ('test_integration_pipeline', 'migrated_engine', 'SOCIAL_INTEGRATION_DATABASE_URL', 'auditgava_social_test'),
    ('test_connections_postgres', 'connection_pg_engine', 'SOCIAL_CONNECTIONS_TEST_DATABASE_URL', 'social_worker_test'),
)


class EngineIntercepted(Exception):
    """Stops execution before an engine or connection can exist."""


def intercept_engine(monkeypatch, module, captured):
    def intercept(value, *args, **kwargs):
        value = value.database_url if hasattr(value, 'database_url') else value
        captured.append(PGDialect_psycopg2().create_connect_args(make_url(value))[1])
        raise EngineIntercepted
    name = 'create_worker_engine' if module.__name__ == 'test_queue_postgres' else 'create_engine'
    monkeypatch.setattr(module, name, intercept)


@pytest.mark.parametrize('module_name,fixture_name,variable,database', FIXTURES)
@pytest.mark.parametrize('query', [
    'host=production.invalid', 'hostaddr=192.0.2.1', 'service=production',
    'port=5432', 'dbname=production', 'options=-csearch_path%3Dpublic',
    'host=127.0.0.1&host=production.invalid',
    '', 'host=', 'hostaddr=', 'service=',
])
def test_fixture_rejects_connection_overrides_before_engine_creation(
    monkeypatch, module_name, fixture_name, variable, database, query,
):
    module = importlib.import_module(module_name)
    captured = []
    intercept_engine(monkeypatch, module, captured)
    monkeypatch.setenv(variable, f'postgresql://fixture:fake@localhost:62124/{database}?{query}')
    generator = getattr(module, fixture_name).__wrapped__()
    with pytest.raises(ValueError):
        next(generator)
    assert captured == []


@pytest.mark.parametrize('module_name,fixture_name,variable,database', FIXTURES)
def test_fixture_pins_host_and_hostaddr_before_engine_creation(
    monkeypatch, module_name, fixture_name, variable, database,
):
    module = importlib.import_module(module_name)
    captured = []
    intercept_engine(monkeypatch, module, captured)
    monkeypatch.setenv('PGHOSTADDR', '192.0.2.1')
    monkeypatch.setenv('PGSERVICE', 'production')
    monkeypatch.setenv(variable, f'postgresql://fixture:fake@localhost:62124/{database}')
    generator = getattr(module, fixture_name).__wrapped__()
    with pytest.raises(EngineIntercepted):
        next(generator)
    assert captured == [{
        'host': '127.0.0.1', 'hostaddr': '127.0.0.1', 'port': 62124,
        'dbname': database, 'user': 'fixture', 'password': 'fake',
    }]


@pytest.mark.parametrize('value', [
    None, True, '', 'not a URL', 'sqlite://',
    'postgresql+asyncpg://localhost:62124/social_worker_test',
    'mysql://localhost:62124/social_worker_test',
    'postgresql://production.invalid:62124/social_worker_test',
    'postgresql://localhost:5432/social_worker_test',
    'postgresql://localhost:62124/production',
    'postgresql://localhost:62124/social_domain_test',
    'postgresql:///social_worker_test',
    'postgresql://localhost:broken/social_worker_test',
    'postgresql://localhost:62124/social_worker_test?host=',
    'postgresql://localhost:62124/social_worker_test?hostaddr=',
    'postgresql://localhost:62124/social_worker_test?service=',
    'postgresql://localhost:62124/social_worker_test?',
    'postgresql://localhost:62124/social_worker_test?sslmode=require',
])
def test_direct_guard_rejects_unassigned_or_overridden_targets_without_disclosing_dsn(value):
    with pytest.raises(ValueError) as failure:
        local_postgres_url(value, 'social_worker_test')
    assert str(failure.value) == 'Use only the assigned loopback test database on port 62124 without connection query options'


@pytest.mark.parametrize('host', ['localhost', '127.0.0.1', '[::1]'])
def test_direct_guard_normalizes_all_supported_loopback_authorities(host):
    url = local_postgres_url(f'postgresql://fixture:fake@{host}:62124/social_worker_test', 'social_worker_test')
    assert url.drivername == 'postgresql+psycopg2'
    assert url.host == '127.0.0.1'
    assert url.query == {'hostaddr': '127.0.0.1'}


def test_percent_encoded_question_mark_in_password_is_preserved():
    url = local_postgres_url('postgresql://fixture:fake%3Fvalue@localhost:62124/social_worker_test', 'social_worker_test')
    assert url.password == 'fake?value'


def test_actual_crash_child_uses_the_validated_parent_endpoint(monkeypatch, tmp_path):
    import ast
    import os
    import subprocess
    from types import SimpleNamespace
    from unittest.mock import patch

    import test_queue_postgres as queue
    import social.worker.config as config_module

    raw_dsn = 'postgresql://fixture:fake@localhost:62124/social_worker_test'
    monkeypatch.setenv('SOCIAL_WORKER_TEST_DATABASE_URL', raw_dsn)
    monkeypatch.setenv('PGHOSTADDR', '192.0.2.1')
    monkeypatch.setattr(queue, 'seed', lambda engine: {'targets': ['unused']})
    captured = []

    def intercept_child(argv, **kwargs):
        script = ast.parse(argv[2])
        engine_index = next(i for i, node in enumerate(script.body)
                            if isinstance(node, ast.Assign)
                            and any(isinstance(target, ast.Name) and target.id == 'engine'
                                    for target in node.targets))
        prefix = ast.Module(body=script.body[:engine_index + 1], type_ignores=[])
        def intercept_engine(config):
            captured.append(PGDialect_psycopg2().create_connect_args(make_url(config.database_url))[1])
            raise EngineIntercepted
        # Execute the actual child configuration prefix, stopping at its engine
        # call. No subprocess, SQL engine or external connection is created.
        with patch.dict(os.environ, kwargs['env'], clear=True), patch.object(config_module, 'create_worker_engine', intercept_engine):
            exec(compile(prefix, '<intercepted crash-test child>', 'exec'), {})

    monkeypatch.setattr(subprocess, 'Popen', intercept_child)
    parent = SimpleNamespace(url=local_postgres_url(raw_dsn, 'social_worker_test'))
    with pytest.raises(EngineIntercepted):
        queue.test_actual_process_kill_after_fake_remote_acceptance_recovers_without_republish(parent, tmp_path)
    assert captured[0]['host'] == captured[0].get('hostaddr') == '127.0.0.1'
    assert captured[0]['port'] == 62124
    assert captured[0]['dbname'] == 'social_worker_test'
    assert os.environ['SOCIAL_WORKER_TEST_DATABASE_URL'] == raw_dsn
