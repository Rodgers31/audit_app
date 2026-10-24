"""Actual PostgreSQL locks/API/native correlation; no government HTTP requests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text

from test_b17_opendata_native import opendata_url, opendata_pg, AUTH
from test_dispatch_qualification import policy_environment
from admin_etl_dispatch import accept, TriggerBody
from admin_etl_dispatch_worker import register_worker, claim, close_readiness, retire_inactive_readiness
from admin_etl_dispatch_adapter import execute
from admin_etl_qualification import qualification, QualificationRefused, POLICY_ENV
from models import AdminAuditLog, EtlDispatchCommand, EtlDispatchDomain, EtlDispatchWorker, IngestionJob, SeedingDomainClaim
from seeding.domains.opendata import source


def trigger(client, generation, dry=True, name='opendata', key=None):
    return client.post('/api/v1/admin/etl/trigger/' + name,
        headers={**AUTH, 'Idempotency-Key': key or str(uuid4())},
        json=dict(dry_run=dry, dispatch_generation=str(generation)))


def test_actual_one_intent_api_native_and_readiness_close(opendata_pg, policy_environment, monkeypatch):
    client, factory, engine, _ = opendata_pg
    policy = qualification()
    generation = register_worker(factory)
    assert generation == policy.generation
    cap = client.get('/api/v1/admin/etl/dispatch', headers=AUTH).json()
    assert cap['available'] is True and cap['execution_mode'] == 'qualification'
    assert [name for name, value in cap['sources'].items() if value['available']] == ['opendata']
    for name, dry in [('opendata', False), ('oag', True), ('cra', True)]:
        assert trigger(client, generation, dry, name).status_code == 409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(EtlDispatchCommand)) == 0
        assert db.scalar(select(func.count()).select_from(AdminAuditLog)) == 0
    key = str(uuid4())
    result = trigger(client, generation, key=key)
    assert result.status_code == 202, result.text
    command_id = UUID(result.json()['command']['id'])
    assert trigger(client, generation, key=key).json()['replayed'] is True
    assert trigger(client, generation).status_code == 409
    assert client.get('/api/v1/admin/etl/dispatch', headers=AUTH).json()['available'] is False
    owned = claim(factory, generation)
    assert owned[0] == command_id
    payload = (Path(__file__).parent / 'fixtures/opendata/Chapter-5-Public-Finance.xlsx').read_bytes()
    calls = []
    def fetch():
        calls.append('fetch')
        return payload, datetime.now(timezone.utc)
    monkeypatch.setattr(source, 'fetch_publication', fetch)
    assert execute(factory, engine, *owned, generation) == 0
    from admin_etl_dispatch_worker import finish
    assert finish(factory, generation, *owned, 0) is True
    assert close_readiness(factory, generation) is True
    assert calls == ['fetch']
    assert claim(factory, generation) is None
    with factory() as db:
        command = db.get(EtlDispatchCommand, command_id)
        job = db.get(IngestionJob, command.job_id)
        assert command.status == 'completed' and job.dry_run is True
        assert (job.items_processed, job.items_created, job.items_updated) == (2125, 0, 0)
        assert job.meta['dispatch_command_id'] == str(command_id)
        assert job.meta['dispatch_claim_token'] == str(owned[1])
        assert db.get(SeedingDomainClaim, owned[1]).released_at is not None
        assert all(row.ready is False and row.command_id is None and row.claim_token is None
                   for row in db.scalars(select(EtlDispatchDomain)))
        assert db.get(EtlDispatchWorker, 1).ready is False
        for table in ('source_documents', 'extractions', 'budget_lines'):
            assert db.scalar(text('SELECT count(*) FROM ' + table)) == 0
    with pytest.raises(QualificationRefused): register_worker(factory)


def test_actual_concurrent_actors_cannot_accept_two_intents(opendata_pg, policy_environment):
    client, factory, _, _ = opendata_pg
    generation = register_worker(factory)
    def submit(name):
        with factory() as db:
            try:
                receipt = accept(db, SimpleNamespace(id=name, email=name+'@example.invalid'), 'opendata',
                    TriggerBody(dry_run=True, dispatch_generation=str(generation)), str(uuid4()))
                return receipt.command.id
            except HTTPException as error:
                return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(submit, ['first-admin', 'second-admin']))
    assert sum(isinstance(v, UUID) for v in values) == 1
    assert values.count(409) == 1
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(EtlDispatchCommand)) == 1
        assert db.scalar(select(func.count()).select_from(AdminAuditLog)) == 1


def test_actual_operator_readiness_reconciliation_is_pinned(opendata_pg, monkeypatch):
    _, factory, _, _ = opendata_pg
    generation = register_worker(factory)
    with factory.begin() as db:
        row = db.get(EtlDispatchWorker, 1)
        row.ready = False
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        row.last_seen_at = row.expires_at - timedelta(seconds=1)
    monkeypatch.setenv('ADMIN_ETL_DISPATCH_ENABLED', 'false')
    with pytest.raises(QualificationRefused): retire_inactive_readiness(factory, uuid4())
    with factory() as db:
        assert any(row.ready for row in db.scalars(select(EtlDispatchDomain)))
    retire_inactive_readiness(factory, generation)
    with factory() as db:
        assert all(row.ready is False and row.command_id is None and row.claim_token is None
                   for row in db.scalars(select(EtlDispatchDomain)))


def test_operator_cannot_retire_live_worker(opendata_pg):
    _, factory, _, _ = opendata_pg
    generation = register_worker(factory)
    with pytest.raises(QualificationRefused): retire_inactive_readiness(factory, generation)


def test_stale_worker_ready_flag_cannot_be_adopted(opendata_pg, policy_environment):
    _, factory, _, _ = opendata_pg
    with factory.begin() as db:
        now = datetime.now(timezone.utc)
        db.add(EtlDispatchWorker(id=1, generation=uuid4(), ready=True,
            last_seen_at=now-timedelta(seconds=60), expires_at=now-timedelta(seconds=30)))
    with pytest.raises(QualificationRefused): register_worker(factory)


@pytest.mark.parametrize('status,same_generation,refused', [
    ('queued', False, True), ('running', False, True), ('interrupted', False, True),
    ('failed', False, False), ('completed', False, False),
    ('failed', True, True), ('completed', True, True),
])
def test_command_admission_uses_nonterminal_or_generation_history(
        opendata_pg, policy_environment, monkeypatch, status, same_generation, refused):
    """Isolate both OR branches: no other readiness/claim/job guard can refuse."""
    client, factory, engine, _ = opendata_pg
    _, value = policy_environment
    admitted = UUID(value['generation'])
    monkeypatch.delenv(POLICY_ENV)
    previous = register_worker(factory)
    result = trigger(client, previous)
    assert result.status_code == 202
    command_id = UUID(result.json()['command']['id'])
    close_readiness(factory, previous)
    with factory.begin() as db:
        now = datetime.now(timezone.utc)
        worker = db.get(EtlDispatchWorker, 1)
        worker.last_seen_at = now - timedelta(seconds=60)
        worker.expires_at = now - timedelta(seconds=30)
        command = db.get(EtlDispatchCommand, command_id)
        command.status = status
        command.generation = admitted if same_generation else previous
        command.updated_at = now
        if status in ('running', 'interrupted', 'completed'):
            command.started_at = now
            command.claim_token = uuid4()
        if status in ('interrupted', 'failed', 'completed'):
            command.finished_at = now
            command.outcome = {'interrupted':'execution_unverified','failed':'failed','completed':'completed'}[status]
        if status == 'completed':
            job = IngestionJob(domain='opendata', status='COMPLETED', dry_run=True,
                started_at=now, finished_at=now, items_processed=0, items_created=0, items_updated=0)
            db.add(job)
            db.flush([job])
            command.job_id = job.id
    with factory() as db:
        assert db.get(EtlDispatchWorker, 1).generation == previous != admitted
        assert db.get(EtlDispatchWorker, 1).ready is False
        assert all(d.ready is False and d.command_id is None and d.claim_token is None
                   for d in db.scalars(select(EtlDispatchDomain)))
        assert db.scalar(select(func.count()).select_from(SeedingDomainClaim)) == 0
        assert all(j.status.name == 'COMPLETED' for j in db.scalars(select(IngestionJob)))
    import json
    monkeypatch.setenv(POLICY_ENV, json.dumps(value))
    if refused:
        with pytest.raises(QualificationRefused): register_worker(factory)
    else:
        assert register_worker(factory) == admitted
    with factory() as db:
        assert db.get(EtlDispatchWorker, 1).generation == (previous if refused else admitted)
        assert db.get(EtlDispatchCommand, command_id).status == status
        assert db.scalar(select(func.count()).select_from(EtlDispatchCommand)) == 1
        assert db.scalar(select(func.count()).select_from(AdminAuditLog)) == 1
    print(f'admission status={status} same_generation={same_generation} refused={refused}')


@pytest.mark.parametrize('retained', ['domain_ready', 'token', 'command', 'job', 'claim'])
def test_retained_ownership_blocks_qualification_and_reconciliation(opendata_pg, policy_environment, monkeypatch, retained):
    client, factory, _, _ = opendata_pg
    # First create the standard durable rows, then make the old generation stale.
    monkeypatch.delenv(POLICY_ENV)
    generation = register_worker(factory)
    if retained in ('token', 'command'):
        assert trigger(client, generation).status_code == 202
        if retained == 'token': assert claim(factory, generation) is not None
    close_readiness(factory, generation)
    with factory.begin() as db:
        worker = db.get(EtlDispatchWorker, 1)
        worker.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        worker.last_seen_at = worker.expires_at - timedelta(seconds=1)
        domain = db.get(EtlDispatchDomain, 'opendata')
        if retained == 'domain_ready': domain.ready = True
        if retained == 'job': db.add(IngestionJob(domain='held', status='RUNNING', dry_run=True))
        if retained == 'claim':
            from seeding.exclusion import reserve
            assert reserve(db, 'opendata', uuid4())
    _, value = policy_environment
    import json
    monkeypatch.setenv(POLICY_ENV, json.dumps(value))
    with pytest.raises(QualificationRefused): register_worker(factory)
    monkeypatch.setenv('ADMIN_ETL_DISPATCH_ENABLED', 'false')
    if retained == 'domain_ready':
        retire_inactive_readiness(factory, generation)
    else:
        with pytest.raises(QualificationRefused): retire_inactive_readiness(factory, generation)


def test_finite_inline_worker_with_actual_transaction_bounds(opendata_pg, policy_environment, monkeypatch):
    client, _, _, url = opendata_pg
    from admin_etl_qualification_worker import bounded_engine, serve
    from sqlalchemy.orm import sessionmaker
    from test_b17_opendata_native import wait_for
    engine = bounded_engine(url)
    factory = sessionmaker(bind=engine)
    payload = (Path(__file__).parent / 'fixtures/opendata/Chapter-5-Public-Finance.xlsx').read_bytes()
    monkeypatch.setattr(source, 'fetch_publication', lambda: (payload, datetime.now(timezone.utc)))
    def submit():
        cap = wait_for(lambda: client.get('/api/v1/admin/etl/dispatch', headers=AUTH).json(), lambda v: v['available'])
        accepted = trigger(client, UUID(cap['generation']))
        assert accepted.status_code == 202, accepted.text
        return accepted.json()['command']['id']
    try:
        with engine.connect() as connection:
            values = tuple(connection.execute(text("SELECT current_setting('statement_timeout'),current_setting('lock_timeout'),current_setting('idle_in_transaction_session_timeout'),current_setting('work_mem')")).one())
            assert values == ('2s', '500ms', '5s', '64kB')
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(submit)
            result = serve(factory, engine)
            assert result['command_id'] == future.result(timeout=3)
        assert result['status'] == 'completed' and result['readiness_closed'] is True
        assert engine.pool.checkedout() == 0 and engine.pool.size() == 3
    finally:
        engine.dispose()
