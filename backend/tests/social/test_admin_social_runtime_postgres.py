"""Batch 6-owned current-schema actual-app API and inert worker integration."""
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

import test_integration_pipeline as pipeline


@pytest.fixture
def runtime_engine():
    value = os.environ.get('SOCIAL_ADMIN_RUNTIME_TEST_DATABASE_URL')
    if not value:
        pytest.skip('Supply the Batch 6 social disposable database explicitly')
    url = make_url(value)
    if (url.drivername != 'postgresql+psycopg2' or url.host != '127.0.0.1' or url.port != 55474
            or url.database != 'social_admin_runtime_test' or url.username != 'socialbatch6' or url.query):
        raise ValueError('Refused unassigned social runtime test database')
    url = url.set(query={'hostaddr':'127.0.0.1'})
    root = create_engine(url, hide_parameters=True)
    schema = 'admin_social_batch6_' + uuid4().hex
    with root.begin() as conn:
        conn.execute(text('CREATE SCHEMA ' + schema))
    engine = create_engine(url, hide_parameters=True, pool_size=5, max_overflow=0,
                           connect_args={'options':'-csearch_path=' + schema + ' -clock_timeout=5000 -cstatement_timeout=15000'})
    try:
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            for name in ('f38c61a9d203_social_manual_domain_queue.py','c96d13e2f411_social_meta_credentials.py',
                         'a42b86e1d310_social_private_media_intake.py','b73e19a4f602_social_media_write_settlement.py',
                         'd8f4a619b203_social_privacy_receipts.py'):
                spec = importlib.util.spec_from_file_location('admin_social_batch6_' + name, Path(__file__).parents[2] / 'alembic/versions' / name)
                migration = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(migration)
                migration.upgrade()
        yield engine
    finally:
        engine.dispose()
        with root.begin() as conn:
            conn.execute(text('DROP SCHEMA ' + schema + ' CASCADE'))
        root.dispose()


@pytest.fixture
def actual_app_pipeline(monkeypatch):
    import main
    original = pipeline.setup_client
    def setup(engine, platforms=('facebook','threads')):
        fixture, accounts = original(engine, platforms)
        main.app.dependency_overrides.update(fixture.app.dependency_overrides)
        return TestClient(main.app, raise_server_exceptions=False), accounts
    monkeypatch.setattr(pipeline, 'setup_client', setup)
    yield main.app
    main.app.dependency_overrides.clear()


def test_current_main_app_manual_cascade_target_retry_and_safe_history(runtime_engine, actual_app_pipeline):
    pipeline.test_migrated_manual_cascade_and_retry_never_reposts_success(runtime_engine)


def test_current_schema_freezes_approved_history(runtime_engine, actual_app_pipeline):
    pipeline.test_actual_migration_prevents_approved_history_mutation(runtime_engine)


def test_current_main_routes_auth_and_disabled_defaults(runtime_engine, actual_app_pipeline):
    from fastapi import HTTPException
    from sqlalchemy.orm import Session
    from social.api import get_db, require_admin
    from supabase_auth import AdminUser
    from social.media.runtime import media_runtime
    app = actual_app_pipeline
    def local_db():
        with Session(runtime_engine) as session:
            yield session
    app.dependency_overrides[get_db] = local_db
    client = TestClient(app, raise_server_exceptions=False)
    routes = [(method,route.path) for route in app.routes if hasattr(route,'methods')
              for method in route.methods if route.path.startswith('/api/v1/admin/social')]
    assert len(routes) == len(set(routes)) == 35
    for status in (401,403):
        def denied():
            raise HTTPException(status, 'Inert unauthorized identity')
        app.dependency_overrides[require_admin] = denied
        for method,path in routes:
            path = path.replace('{post_id}',str(uuid4())).replace('{target_id}',str(uuid4())).replace('{flow_id}',str(uuid4())).replace('{account_id}',str(uuid4())).replace('{asset_id}',str(uuid4()))
            response = client.request(method,path)
            assert response.status_code == status, (method,path,response.text)
            assert response.headers['cache-control'] == 'private, no-store'
    app.dependency_overrides[require_admin] = lambda: AdminUser(id=str(uuid4()),email=None,roles=['admin'])
    media_runtime.cache_clear()
    response = client.get('/api/v1/admin/social/system/status')
    assert response.status_code == 200, response.text
    value = response.json()
    assert value['publishing_enabled'] is False
    assert value['adapters_available'] == [] and value['media_upload_available'] is False
    assert value['worker']['state'] == 'unavailable'
    assert all(value[key] is False for key in ('generation_enabled','auto_approve_enabled','auto_schedule_enabled','auto_publish_enabled'))
    assert client.get('/api/v1/admin/social/connections/meta/status').json()['available'] is False
    assert client.get('/api/v1/admin/social/media/capabilities').json()['upload_available'] is False
    assert all('privacy' not in path for _,path in routes)
