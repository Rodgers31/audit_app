"""Media fixture safety is checked before any engine or connection exists."""
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2

import test_media_cleanup as cleanup


class EngineIntercepted(Exception):
    pass


@pytest.mark.parametrize('query', [
    'host=production.invalid', 'hostaddr=192.0.2.1', 'service=production',
    'port=5432', 'dbname=production', 'options=-csearch_path%3Dpublic',
    'host=127.0.0.1&host=production.invalid', '', 'host=', 'hostaddr=', 'service=',
])
@pytest.mark.parametrize('variable,database', [('SOCIAL_WORKER_TEST_DATABASE_URL', 'social_worker_test'), ('SOCIAL_TEST_DATABASE_URL', 'social_domain_test')])
def test_media_fixture_refuses_override_before_engine_creation(monkeypatch, query, variable, database):
    captured = []
    def intercept(*args, **kwargs):
        captured.append(True)
        raise EngineIntercepted
    monkeypatch.setattr(cleanup, 'create_engine', intercept)
    monkeypatch.delenv('SOCIAL_WORKER_TEST_DATABASE_URL', raising=False)
    monkeypatch.delenv('SOCIAL_TEST_DATABASE_URL', raising=False)
    monkeypatch.setenv(variable, 'postgresql://fixture:fake@localhost:62124/' + database + '?' + query)
    fixture = cleanup.media_pg.__wrapped__((SimpleNamespace(runtime=None), None))
    with pytest.raises(ValueError):
        next(fixture)
    assert not captured


@pytest.mark.parametrize('variable,database', [('SOCIAL_WORKER_TEST_DATABASE_URL', 'social_worker_test'), ('SOCIAL_TEST_DATABASE_URL', 'social_domain_test')])
def test_media_fixture_pins_effective_host_address_despite_environment(monkeypatch, variable, database):
    captured = []
    def intercept(url, *args, **kwargs):
        captured.append(PGDialect_psycopg2().create_connect_args(url)[1])
        raise EngineIntercepted
    monkeypatch.setattr(cleanup, 'create_engine', intercept)
    monkeypatch.setenv('PGHOSTADDR', '192.0.2.1')
    monkeypatch.setenv('PGSERVICE', 'production')
    monkeypatch.delenv('SOCIAL_WORKER_TEST_DATABASE_URL', raising=False)
    monkeypatch.delenv('SOCIAL_TEST_DATABASE_URL', raising=False)
    monkeypatch.setenv(variable, 'postgresql://fixture:fake@localhost:62124/' + database)
    fixture = cleanup.media_pg.__wrapped__((SimpleNamespace(runtime=None), None))
    with pytest.raises(EngineIntercepted):
        next(fixture)
    assert captured == [{
        'host': '127.0.0.1', 'hostaddr': '127.0.0.1', 'port': 62124,
        'dbname': database, 'user': 'fixture', 'password': 'fake',
    }]
