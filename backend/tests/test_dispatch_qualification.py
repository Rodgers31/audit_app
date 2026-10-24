"""Executed one-intent and fenced readiness controls, with no external services."""
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

import admin_etl_dispatch_worker as worker
import admin_etl_dispatch_adapter as adapter


@pytest.mark.parametrize('successor', [False, True])
def test_actual_shutdown_closes_only_owned_readiness(monkeypatch, successor):
    generation = uuid4()
    current = SimpleNamespace(generation=uuid4() if successor else generation, ready=True)
    domains = [SimpleNamespace(ready=True, command_id=uuid4(), claim_token=uuid4())]
    retained = (domains[0].command_id, domains[0].claim_token)

    class DB:
        def scalar(self, statement):
            return current
        def scalars(self, statement):
            return domains if 'etl_dispatch_domains' in str(statement) else []

    class Factory:
        @contextmanager
        def begin(self):
            yield DB()

    class Keeper:
        def __init__(self, **kwargs): pass
        def start(self): pass
        def join(self, **kwargs): pass

    monkeypatch.setattr(worker, 'enabled', lambda: True)
    monkeypatch.setattr(adapter, 'supported_registry', lambda: True)
    monkeypatch.setattr(worker, 'register_worker', lambda factory: generation)
    monkeypatch.setattr(worker.threading, 'Thread', Keeper)
    worker.serve(Factory(), stop_requested=lambda: True)
    assert current.ready is successor
    assert domains[0].ready is successor
    assert (domains[0].command_id, domains[0].claim_token) == retained

from datetime import datetime, timedelta, timezone
import json
from admin_etl_qualification import qualification, QualificationRefused, POLICY_ENV


@pytest.fixture
def policy_environment(monkeypatch):
    now = datetime.now(timezone.utc)
    value = dict(version=1, generation=str(uuid4()),
                 issued_at=(now - timedelta(seconds=1)).isoformat().replace('+00:00', 'Z'),
                 expires_at=(now + timedelta(seconds=3599)).isoformat().replace('+00:00', 'Z'))
    monkeypatch.setenv('ADMIN_ETL_DISPATCH_ENABLED', 'true')
    monkeypatch.setenv('AUTO_SEEDER_ENABLED', 'false')
    monkeypatch.setenv('ADMIN_ETL_DISPATCH_SOURCES', 'opendata')
    monkeypatch.setenv('SEED_OPENDATA_INGESTION_ENABLED', 'true')
    monkeypatch.setenv('SEED_KNBS_RELEASE_DISCOVERY_ENABLED', 'false')
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'false')
    monkeypatch.setenv(POLICY_ENV, json.dumps(value))
    return now, value


@pytest.mark.parametrize('raw', ['', 'null', '[]', '{}', 'NaN', 'true', 'x' * 513])
def test_present_invalid_policy_never_falls_back(policy_environment, monkeypatch, raw):
    monkeypatch.setenv(POLICY_ENV, raw)
    with pytest.raises(QualificationRefused): qualification()
    from admin_etl_dispatch import enabled
    assert enabled() is False


@pytest.mark.parametrize('changes', [
    {'version': True}, {'version': 2}, {'generation': None}, {'generation': str(uuid4()).upper()},
    {'generation': '00000000-0000-0000-0000-000000000000'}, {'issued_at': '2026-02-30T00:00:00Z'},
    {'issued_at': None}, {'expires_at': '2026-10-24T00:00:00'}, {'extra': 1},
])
def test_policy_is_typed_and_bounded(policy_environment, monkeypatch, changes):
    _, value = policy_environment
    monkeypatch.setenv(POLICY_ENV, json.dumps(value | changes))
    with pytest.raises(QualificationRefused): qualification()


@pytest.mark.parametrize('name,value', [
    ('ADMIN_ETL_DISPATCH_SOURCES', 'oag'), ('ADMIN_ETL_DISPATCH_SOURCES', 'opendata,oag'),
    ('SEED_OPENDATA_INGESTION_ENABLED', 'false'), ('SEED_KNBS_RELEASE_DISCOVERY_ENABLED', 'true'),
    ('SOCIAL_GENERATION_HOOK_ENABLED', 'true'), ('SEED_OPENDATA_INGESTION_ENABLED', 'TRUE'),
])
def test_qualification_refuses_scope_widening(policy_environment, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(QualificationRefused): qualification()


def test_duplicate_and_expired_policy_refuse(policy_environment, monkeypatch):
    now, value = policy_environment
    with pytest.raises(QualificationRefused): qualification(now + timedelta(hours=1))
    with pytest.raises(QualificationRefused): qualification(now - timedelta(hours=1))
    monkeypatch.setenv(POLICY_ENV, json.dumps(value)[:-1] + ',"version":1}')
    with pytest.raises(QualificationRefused): qualification()


@pytest.mark.parametrize('source,dry,generation,at', [
    ('oag', True, 'same', 'now'), ('opendata', False, 'same', 'now'),
    ('opendata', 1, 'same', 'now'), ('opendata', True, 'different', 'now'),
    ('opendata', True, 'same', None), ('opendata', True, 'same', float('nan')),
])
def test_direct_permission_cannot_bypass_policy(policy_environment, source, dry, generation, at):
    now, _ = policy_environment
    policy = qualification(now)
    assert not policy.permits(source, dry, policy.generation if generation == 'same' else uuid4(), now if at == 'now' else at)


def test_qualification_refuses_unbounded_worker_entry(policy_environment, monkeypatch):
    monkeypatch.setattr(adapter, 'supported_registry', lambda: True)
    monkeypatch.setattr(worker, 'register_worker', lambda *a: pytest.fail('Must not register'))
    with pytest.raises(QualificationRefused, match='bounded worker'):
        worker.serve(None)


def test_watchdog_direct_call_requires_linux(policy_environment, monkeypatch):
    import admin_etl_qualification_watchdog as watchdog
    monkeypatch.setattr(watchdog.sys, 'platform', 'darwin')
    with pytest.raises(ValueError, match='Linux'):
        watchdog.supervise()
