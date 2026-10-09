"""Real PostgreSQL concurrency/payload checks; explicit lane-local opt-in."""
import os
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import get_db
from models import AdminAuditLog
from routers.admin_audit_log import router
from supabase_auth import AdminUser, get_current_user


@pytest.fixture()
def pg_audit():
    if os.getenv('ADMIN_OVERVIEW_AUDIT_POSTGRES') != '1':
        pytest.skip('explicit disposable PostgreSQL lane opt-in required')
    engine = create_engine('postgresql+psycopg2://inert:inert@127.0.0.1:55473/admin_overview_audit')
    AdminAuditLog.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: AdminUser(id='inert-admin', email=None, roles=['admin'])
    def sessions():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = sessions
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, factory
    finally:
        AdminAuditLog.__table__.drop(engine)
        engine.dispose()


def row():
    return AdminAuditLog(actor_id='inert-admin', action='etl.trigger', payload={'job_id': 1, 'dry_run': True}, created_at=datetime.now(timezone.utc))


def test_late_commit_of_earlier_allocated_id_cannot_change_snapshot(pg_audit):
    client, factory = pg_audit
    with factory() as early:
        early_row = row()
        early.add(early_row)
        early.flush()
        with factory() as later:
            later.add(row())
            later.commit()
        first = client.get('/api/v1/admin/audit-log?days=0&page_size=1').json()
        assert first['total'] == 1
        early.commit()
    params = {'days': 0, 'page_size': 1, 'page': 2, 'snapshot_id': first['snapshot_id'], 'as_of': first['as_of']}
    if first.get('visibility_snapshot') is not None:
        params['visibility_snapshot'] = first['visibility_snapshot']
    second = client.get('/api/v1/admin/audit-log', params=params).json()
    assert second['total'] == first['total']
    assert second['entries'] == []


def test_postgres_jsonb_private_serialization_and_route_has_no_write(pg_audit):
    client, factory = pg_audit
    with factory() as db:
        item = row()
        item.payload['access_token'] = 'INERT_SECRET'
        db.add(item)
        db.commit()
    response = client.get('/api/v1/admin/audit-log?days=0')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'private, no-store'
    assert 'INERT_SECRET' not in response.text
    assert response.json()['entries'][0]['created_at'].endswith('Z')
    assert client.post('/api/v1/admin/audit-log', json={}).status_code == 405


def test_visibility_unicode_digits_are_invalid_filters(pg_audit):
    client, _ = pg_audit
    response = client.get('/api/v1/admin/audit-log', params={'snapshot_id': 0, 'as_of': datetime.now(timezone.utc).isoformat(), 'visibility_snapshot': '٣:٤:'})
    assert response.status_code == 422
    assert response.headers['cache-control'] == 'private, no-store'
