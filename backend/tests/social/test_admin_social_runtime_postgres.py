"""Batch 6-owned current-schema actual-app API and inert worker integration."""
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

import test_integration_pipeline as pipeline


def local_client(app):
    async def loopback(scope, receive, send):
        await app({**scope, 'client': ('127.0.0.1', 0)}, receive, send)
    return TestClient(loopback, raise_server_exceptions=False)


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
    root = create_engine(url, hide_parameters=True, isolation_level='AUTOCOMMIT',
                         pool_size=2, max_overflow=0)
    database = 'admin_social_batch6_' + uuid4().hex
    with root.connect() as conn:
        conn.execute(text('CREATE DATABASE ' + database))
    engine = create_engine(url.set(database=database), hide_parameters=True, pool_size=2, max_overflow=0,
                           connect_args={'options':'-clock_timeout=5000 -cstatement_timeout=15000'})
    try:
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            scripts = ScriptDirectory(str(Path(__file__).parents[2] / 'alembic'))
            for revision in reversed(list(scripts.walk_revisions(base='base', head='a706b17a0001'))):
                revision.module.upgrade()
        yield engine
    finally:
        engine.dispose()
        with root.connect() as conn:
            conn.execute(text('DROP DATABASE ' + database))
        root.dispose()


@pytest.fixture
def actual_app_pipeline(monkeypatch):
    import main
    original = pipeline.setup_client
    original_plan = pipeline.ExplicitFake.next_operation
    def local_plan(adapter, payload, checkpoint):
        plan = original_plan(adapter, payload, checkpoint)
        return plan.model_copy(update={'estimated_cost_microusd': 1}) if payload.platform == 'x' else plan
    monkeypatch.setattr(pipeline.ExplicitFake, 'next_operation', local_plan)
    def setup(engine, platforms=('facebook','threads')):
        fixture, accounts = original(engine, platforms)
        # The current worker requires both global and per-account spending
        # admission for the inert X adapter's synthetic reservation.
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO social_platform_budgets "
                "(account_id,access_verified,enabled,limit_microusd) "
                "SELECT id,true,true,1000 FROM social_accounts WHERE platform='x'"))
        main.app.dependency_overrides.update(fixture.app.dependency_overrides)
        return local_client(main.app), accounts
    monkeypatch.setattr(pipeline, 'setup_client', setup)
    yield main.app
    main.app.dependency_overrides.clear()


def test_current_main_app_manual_cascade_target_retry_and_safe_history(runtime_engine, actual_app_pipeline):
    pipeline.test_migrated_manual_cascade_and_retry_never_reposts_success(runtime_engine)
    with runtime_engine.connect() as connection:
        assert connection.execute(text('SELECT reserved_microusd FROM social_platform_budgets')).scalar_one() == 2


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
    client = local_client(app)
    def mounted_routes(values, depth=0):
        assert depth < 10, 'Unexpected router nesting'
        for route in values:
            candidates = getattr(route, 'effective_candidates', None)
            if candidates is not None:
                assert callable(candidates), 'Unknown included router shape'
                yield from mounted_routes(candidates(), depth + 1)
                continue
            assert isinstance(route.path, str), 'Unknown mounted route shape'
            if route.path.startswith('/api/v1/admin/social'):
                assert route.methods, 'Admin route has no HTTP inventory'
                for method in route.methods:
                    yield method, route.path

    routes = list(mounted_routes(app.routes))
    expected = {tuple(line.split(' ', 1)) for line in """
GET /accounts
GET /accounts/{account_id}/health
GET /automation/decisions
GET /automation/policy-controls
GET /automation/policy-decisions
GET /automation/rules
GET /connections/meta/flows/{flow_id}
GET /connections/meta/status
GET /generation/controls
GET /media/assets
GET /media/assets/{asset_id}/preview
GET /media/assets/{asset_id}/retirement-scope
GET /media/capabilities
GET /media/maintenance
GET /platform-connections/{provider}/accounts/{account_id}/creator-settings
GET /platform-connections/{provider}/accounts/{account_id}/health
GET /platform-connections/{provider}/flows/{flow_id}
GET /platform-connections/{provider}/status
GET /platforms
GET /posts
GET /posts/{post_id}
GET /posts/{post_id}/evidence
GET /posts/{post_id}/history
GET /posts/{post_id}/status
GET /privacy/plans/{plan_id}
GET /privacy/requests
GET /privacy/requests/{receipt_id}
GET /studio/analytics/{target_id}
GET /studio/calendar
GET /studio/capabilities
GET /studio/jobs
GET /studio/jobs/{job_id}
GET /studio/jobs/{job_id}/preview
GET /studio/jobs/{job_id}/transcript
GET /system/status
GET /targets/{target_id}/meta-reels/public-proof
GET /targets/{target_id}/public-proof
PATCH /automation/policy-controls
PATCH /controls
PATCH /generation/controls
PATCH /posts/{post_id}
POST /accounts/{account_id}/disconnect
POST /accounts/{account_id}/rotate-key
POST /automation/operating-evidence
POST /automation/policy-snapshots
POST /automation/rules/{rule_id}/versions
POST /connections/meta/complete
POST /connections/meta/flows/{flow_id}/select
POST /connections/meta/start
POST /generation/detect
POST /generation/detect-reports
POST /media/assets/{asset_id}/retire
POST /media/uploads
POST /media/uploads/{asset_id}/complete
POST /media/uploads/{asset_id}/reconcile-owned
POST /platform-connections/{provider}/accounts/{account_id}/disconnect
POST /platform-connections/{provider}/accounts/{account_id}/refresh
POST /platform-connections/{provider}/accounts/{account_id}/rotate-key
POST /platform-connections/{provider}/complete
POST /platform-connections/{provider}/flows/{flow_id}/confirm
POST /platform-connections/{provider}/start
POST /platform-events/prune
POST /posts
POST /posts/{post_id}/approve
POST /posts/{post_id}/archive
POST /posts/{post_id}/cancel
POST /posts/{post_id}/duplicate
POST /posts/{post_id}/policy-authorize
POST /posts/{post_id}/policy-schedule
POST /posts/{post_id}/publish
POST /posts/{post_id}/publish-now
POST /posts/{post_id}/reject
POST /posts/{post_id}/reschedule
POST /posts/{post_id}/resume
POST /posts/{post_id}/schedule
POST /posts/{post_id}/shadow
POST /posts/{post_id}/submit
POST /posts/{post_id}/validate
POST /privacy/plans
POST /privacy/plans/{plan_id}/decision
POST /privacy/plans/{plan_id}/execute
POST /privacy/plans/{plan_id}/reconcile
POST /studio/jobs
POST /studio/jobs/{job_id}/approve
POST /studio/jobs/{job_id}/attach
POST /studio/jobs/{job_id}/cancel
POST /studio/jobs/{job_id}/retry
POST /targets/{target_id}/meta-reels/public-proof
POST /targets/{target_id}/meta-reels/record-existing
POST /targets/{target_id}/public-proof
POST /targets/{target_id}/record-existing
POST /targets/{target_id}/retry
""".strip().splitlines()}
    assert len(routes) == len(set(routes)) == 92
    assert {(method, path.removeprefix('/api/v1/admin/social')) for method, path in routes} == expected
    for status in (401,403):
        def denied():
            raise HTTPException(status, 'Inert unauthorized identity')
        app.dependency_overrides[require_admin] = denied
        for method,path in routes:
            import re
            path = re.sub(r'\{[^}]+\}', lambda _: str(uuid4()), path.replace('{provider}', 'threads'))
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
    privacy = client.get('/api/v1/admin/social/privacy/requests')
    assert privacy.status_code == 200, privacy.text
    assert privacy.json()['workflow_enabled'] is False
    assert privacy.json()['execution_enabled'] is False
    # Accepted admin privacy workflow stays authenticated; public callback
    # ingress still requires its separate explicit configuration.
    from social.privacy.api import DATA_PATH, DEAUTH_PATH, STATUS_PATH
    assert client.post(DATA_PATH).status_code == 404
    assert client.post(DEAUTH_PATH).status_code == 404
    assert client.get(STATUS_PATH).status_code == 404
