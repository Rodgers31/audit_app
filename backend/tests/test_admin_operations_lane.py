"""Operations routes executed with isolated storage and inert auth transports."""
import asyncio
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import database
import supabase_auth
from models import AdminAuditLog, IngestionJob, IngestionStatus
from routers import admin, etl_admin


@pytest.fixture
def operations(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'operations.sqlite'}", connect_args={"check_same_thread": False})
    IngestionJob.__table__.create(engine)
    AdminAuditLog.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "SessionLocal", factory)
    app = FastAPI()
    app.include_router(admin.router)
    app.include_router(etl_admin.router)
    monkeypatch.setattr(supabase_auth, "_decode_supabase_jwt", lambda token: {"sub": token})
    monkeypatch.setattr(supabase_auth, "_fetch_roles", lambda uid: ("inert@example.invalid", ["admin"] if uid == "admin" else ["user"]))
    with TestClient(app) as client:
        yield client, factory, engine
    engine.dispose()


AUTH = {"Authorization": "Bearer admin"}


def seed(factory, **overrides):
    with factory() as db:
        row = IngestionJob(domain="audits", status=IngestionStatus.COMPLETED,
            started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
            items_processed=3, items_created=2, items_updated=1,
            errors=[], meta={})
        for key, value in overrides.items():
            setattr(row, key, value)
        db.add(row)
        db.commit()
        return row.id


@pytest.mark.parametrize("dry_run", [False, True])
def test_unaccepted_trigger_never_inserts_or_records_success(operations, dry_run):
    client, factory, _ = operations
    for _ in range(2):
        response = client.post('/api/v1/admin/etl/trigger/oag', json={"dry_run": dry_run}, headers=AUTH)
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "manual_dispatch_unavailable"
        assert "no-store" in response.headers['cache-control']
    with factory() as db:
        assert db.query(IngestionJob).count() == 0
        assert db.query(AdminAuditLog).count() == 0


def test_health_does_not_certify_worker_from_calendar_calculation(operations):
    client, _, _ = operations
    body = client.get('/api/v1/admin/etl/health', headers=AUTH).json()
    assert body['scheduler_status'] == 'unverified'
    assert body['plan_status'] == 'available'
    assert body['manual_trigger']['available'] is False
    assert body['worker_status'] == 'unverified'
    assert body['data_freshness'] == 'unverified'


def test_schedule_decision_contract_and_summary_are_plan_only(operations):
    client, _, _ = operations
    body = client.get('/api/v1/admin/etl/schedule', headers=AUTH).json()
    assert body['evidence'] == 'calendar_plan'
    assert body['sources']
    assert all(type(v['should_run']) is bool for v in body['sources'].values())
    assert body['summary']['sources_running_today'] == sum(v['should_run'] for v in body['sources'].values())
    summary = client.get('/api/v1/admin/etl/schedule/summary', headers=AUTH).json()
    assert summary['evidence'] == 'calendar_plan'
    assert summary['running_today'] == body['summary']['sources_running_today']
    for name, decision in body['sources'].items():
        source = client.get(f'/api/v1/admin/etl/schedule/source/{name}', headers=AUTH).json()
        assert source['should_run_now'] == decision['should_run']
        assert source['evidence'] == 'calendar_plan'


@pytest.mark.parametrize('failure', ['exception', 'empty', 'malformed'])
def test_planner_failure_is_safe_and_never_healthy(operations, monkeypatch, failure):
    client, _, _ = operations
    class Broken:
        def __init__(self):
            if failure == 'exception':
                raise RuntimeError('postgres://user:PRIVATE_PASSWORD@private-host/db')
        def generate_schedule_report(self):
            return {} if failure == 'empty' else {'oag': {'should_run_now': 'false'}}
        def get_schedule_summary(self):
            return {'secret': 'PRIVATE_PASSWORD'}
    monkeypatch.setattr(etl_admin, 'SmartScheduler', Broken)
    for path in ['schedule', 'schedule/summary', 'schedule/source/oag']:
        response = client.get('/api/v1/admin/etl/' + path, headers=AUTH)
        assert response.status_code == 503
        assert 'PRIVATE_PASSWORD' not in response.text
    health = client.get('/api/v1/admin/etl/health', headers=AUTH)
    assert health.status_code == 200
    assert health.json()['plan_status'] == 'unavailable'
    assert health.json()['scheduler_status'] == 'unverified'
    assert 'PRIVATE_PASSWORD' not in health.text


@pytest.mark.parametrize('path', [
    'ingestion-jobs?days=-1', 'ingestion-jobs?days=0', 'ingestion-jobs?days=366',
    'ingestion-jobs?days=99999999999999999999', 'ingestion-jobs?page=10001',
    'ingestion-jobs?domain=' + 'x'*101, 'ingestion-jobs/stats/summary?days=-1',
    'ingestion-jobs/0', 'ingestion-jobs/2147483648',
])
def test_ingestion_query_bounds(operations, path):
    client, _, _ = operations
    assert client.get('/api/v1/admin/' + path, headers=AUTH).status_code == 422


def test_ingestion_projection_withholds_raw_diagnostics_and_tie_order_is_stable(operations):
    client, factory, engine = operations
    now = datetime.now(timezone.utc)
    first = seed(factory, started_at=now, errors=['Authorization: Bearer PRIVATE_TOKEN'],
                 meta={'password': 'PRIVATE_PASSWORD', 'source_mode': 'live', 'since': None})
    second = seed(factory, started_at=now)
    statements = []
    def capture(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith('SELECT'):
            statements.append(statement)
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        response = client.get('/api/v1/admin/ingestion-jobs?page_size=1', headers=AUTH)
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    assert response.status_code == 200
    assert response.json()['jobs'][0]['id'] == second
    assert response.json()['has_more'] is True
    assert not any('ingestion_jobs.metadata' in sql for sql in statements)
    assert not any('ingestion_jobs.errors AS' in sql for sql in statements)
    response = client.get(f'/api/v1/admin/ingestion-jobs/{first}', headers=AUTH)
    assert 'PRIVATE_' not in response.text
    assert response.json()['error_count'] == 1
    assert response.json()['metadata']['source_mode'] == 'live'
    assert response.json()['diagnostics_redacted'] is True
    assert 'no-store' in response.headers['cache-control']


def test_stats_are_equivalent_and_transfer_only_aggregates(operations):
    client, factory, engine = operations
    for index, status in enumerate(IngestionStatus):
        seed(factory, status=status, items_processed=index, errors=['PRIVATE_'+'x'*65536], meta={'private':'x'*65536})
    statements = []
    def capture(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith('SELECT'):
            statements.append(statement)
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        response = client.get('/api/v1/admin/ingestion-jobs/stats/summary', headers=AUTH)
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    assert response.status_code == 200
    data = response.json()
    assert data == {'total_jobs':5, **{status.value:1 for status in IngestionStatus},
        'total_items_processed':10, 'total_items_created':10, 'total_items_updated':5, 'domains':{'audits':5}}
    assert len(statements) == 1
    assert 'errors' not in statements[0] and 'metadata' not in statements[0]


@pytest.mark.parametrize('path,method', [
    ('ingestion-jobs','get'), ('ingestion-jobs/1','get'), ('ingestion-jobs/stats/summary','get'),
    ('etl/schedule','get'), ('etl/schedule/summary','get'), ('etl/schedule/source/oag','get'),
    ('etl/health','get'), ('etl/trigger/oag','post'),
])
def test_every_operations_route_rejects_anonymous_and_nonadmin(operations, path, method):
    client, _, _ = operations
    call = getattr(client, method)
    assert call('/api/v1/admin/'+path).status_code in (401,403)
    assert call('/api/v1/admin/'+path, headers={'Authorization':'Bearer viewer'}).status_code == 403


@pytest.mark.parametrize('payload', [{'dry_run':'false'}, {'dry_run':1}, {'dry_run':None}, {'unexpected':True}])
def test_trigger_rejects_malformed_commands(operations, payload):
    client, _, _ = operations
    assert client.post('/api/v1/admin/etl/trigger/oag', json=payload, headers=AUTH).status_code == 422


def test_unknown_and_missing_jobs_are_errors_not_empty_success(operations):
    client, _, _ = operations
    assert client.get('/api/v1/admin/ingestion-jobs/99', headers=AUTH).status_code == 404
    assert client.get('/api/v1/admin/ingestion-jobs?status=unrecognized', headers=AUTH).status_code == 400
    assert client.post('/api/v1/admin/etl/trigger/unknown', json={}, headers=AUTH).status_code == 404


def test_direct_stats_retains_legacy_all_time_control(operations):
    _, factory, _ = operations
    seed(factory)
    with factory() as db:
        assert asyncio.run(admin.get_ingestion_stats(days=None, db=db)).total_jobs == 1


def test_fresh_backend_import_resolves_the_calendar_without_shadowing_packages():
    backend = Path(__file__).resolve().parents[1]
    env = {"PATH": os.environ.get('PATH','/usr/bin:/bin'), "PYTHON_DOTENV_DISABLED":"1",
           "PYTHONPATH":str(backend), "DATABASE_URL":"sqlite:////tmp/operations-batch6-import-only.sqlite"}
    result = subprocess.run([sys.executable,'-c',
        "import asyncio; from routers.etl_admin import get_etl_schedule; p=asyncio.run(get_etl_schedule()); print(p['evidence'], len(p['sources']))"],
        cwd=backend, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'calendar_plan 6'


@pytest.mark.parametrize('counter', ['items_processed', 'items_created', 'items_updated'])
def test_negative_stored_counters_are_unavailable_not_success(operations, counter):
    client, factory, _ = operations
    job_id = seed(factory, **{counter:-1})
    for path in ['ingestion-jobs', f'ingestion-jobs/{job_id}', 'ingestion-jobs/stats/summary']:
        assert client.get('/api/v1/admin/'+path, headers=AUTH).status_code == 503


def test_reversed_recorded_timestamps_withhold_duration_instead_of_inventing_zero(operations):
    client, factory, _ = operations
    now = datetime.now(timezone.utc)
    job_id = seed(factory, started_at=now, finished_at=now-timedelta(seconds=2))
    for path in ['ingestion-jobs', f'ingestion-jobs/{job_id}']:
        response=client.get('/api/v1/admin/'+path, headers=AUTH)
        record=response.json()['jobs'][0] if path=='ingestion-jobs' else response.json()
        assert record['duration_seconds'] is None
