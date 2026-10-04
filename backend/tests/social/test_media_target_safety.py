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
def test_media_fixture_refuses_override_before_engine_creation(monkeypatch, query):
    captured = []
    def intercept(*args, **kwargs):
        captured.append(True)
        raise EngineIntercepted
    monkeypatch.setattr(cleanup, 'create_engine', intercept)
    monkeypatch.setenv('SOCIAL_WORKER_TEST_DATABASE_URL',
                       'postgresql://fixture:fake@localhost:62124/social_worker_test?' + query)
    fixture = cleanup.media_pg.__wrapped__((SimpleNamespace(runtime=None), None))
    with pytest.raises(ValueError):
        next(fixture)
    assert not captured


def test_media_fixture_pins_effective_host_address_despite_environment(monkeypatch):
    captured = []
    def intercept(url, *args, **kwargs):
        captured.append(PGDialect_psycopg2().create_connect_args(url)[1])
        raise EngineIntercepted
    monkeypatch.setattr(cleanup, 'create_engine', intercept)
    monkeypatch.setenv('PGHOSTADDR', '192.0.2.1')
    monkeypatch.setenv('PGSERVICE', 'production')
    monkeypatch.setenv('SOCIAL_WORKER_TEST_DATABASE_URL',
                       'postgresql://fixture:fake@localhost:62124/social_worker_test')
    fixture = cleanup.media_pg.__wrapped__((SimpleNamespace(runtime=None), None))
    with pytest.raises(EngineIntercepted):
        next(fixture)
    assert captured == [{
        'host': '127.0.0.1', 'hostaddr': '127.0.0.1', 'port': 62124,
        'dbname': 'social_worker_test', 'user': 'fixture', 'password': 'fake',
    }]
