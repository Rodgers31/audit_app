"""New social modules preserve both supported launches without network access."""
import os
import inspect
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _assert_complete_public_prefix(app):
    from fastapi.testclient import TestClient

    # FastAPI may defer include_router rather than flatten router.routes.
    # OpenAPI resolves the complete app contract; HTTP proves dispatch and
    # the administrator boundary without opening a database/provider session.
    paths = app.openapi()['paths']
    required = (
        '/api/v1/admin/social/media/capabilities',
        '/api/v1/admin/social/connections/meta/status',
        '/api/v1/admin/social/accounts',
    )
    assert all(path in paths and 'get' in paths[path] for path in required), paths
    assert not any('/social/api/v1/' in path for path in paths), paths
    assert all(path.startswith('/api/v1/admin/social/') for path in paths), paths
    with TestClient(app) as client:
        for path in required:
            response = client.get(path)
            assert response.status_code in {401, 403}, (path, response.text)
            assert response.headers['cache-control'] == 'private, no-store'
            assert response.json()['detail']['code'] in {
                'AUTHENTICATION_REQUIRED', 'PERMISSION_DENIED'
            }

@pytest.mark.parametrize('name', ['models', 'api'])
@pytest.mark.parametrize('package', [False, True])
def test_social_import_uses_launch_mode_identity(name, package):
    prefix = 'backend.' if package else ''
    script = f'''import socket
socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError("network"))
import {prefix}models as app_models
import {prefix}social.{name} as subject
import {prefix}social.models as social_models
assert social_models.Base is app_models.Base
assert social_models.SocialPost.metadata is app_models.Base.metadata
'''
    if name == 'api':
        script += f'''import {prefix}database as database
import {prefix}supabase_auth as auth
assert subject.get_db is database.get_db
assert subject.require_admin is auth.require_admin
'''
    env = {**os.environ, 'DATABASE_URL':'postgresql+psycopg2://test:test@127.0.0.1/unused'}
    env.pop('PYTHONPATH', None)
    result = subprocess.run([sys.executable,'-c',script],cwd=ROOT if package else ROOT/'backend',env=env,capture_output=True,text=True)
    assert result.returncode == 0, result.stderr

def test_package_model_does_not_reuse_preloaded_top_level_metadata():
    script=f'''import sys
sys.path.insert(0,{str(ROOT/'backend')!r})
import models as top
import backend.models as package
import backend.social.models as subject
assert top.Base is not package.Base
assert subject.Base is package.Base
'''
    result=subprocess.run([sys.executable,'-c',script],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode==0, result.stderr

def test_api_test_module_does_not_rewrite_database_configuration():
    script=f'''import os,sys
sys.path[:0]=[{str(ROOT/'backend')!r},{str(ROOT/'backend/tests/social')!r}]
os.environ['DATABASE_URL']='postgresql+psycopg2://test:test@127.0.0.1/unused'
import test_api_admin
assert os.environ['DATABASE_URL']=='postgresql+psycopg2://test:test@127.0.0.1/unused'
'''
    result=subprocess.run([sys.executable,'-c',script],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode==0, result.stderr

@pytest.mark.parametrize('package', [False, True])
@pytest.mark.parametrize('first_feature', ['connections', 'media'])
def test_connected_feature_first_registers_complete_schema_and_single_public_prefix(package, first_feature):
    prefix = 'backend.' if package else ''
    script = f'''import socket
socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError("network"))
import {prefix}social.{first_feature}.models as first
import {prefix}social.connections.models as feature
import {prefix}social.media.models as media
import {prefix}social.models as domain
import {prefix}social.api as api
assert feature.SocialCredential.metadata is domain.Base.metadata
assert {{t.name for t in domain.SOCIAL_TABLES}} == {{name for name in domain.Base.metadata.tables if name.startswith('social_')}}
assert len(domain.SOCIAL_TABLES) == len({{t.name for t in domain.SOCIAL_TABLES}})
assert next(iter(domain.SocialAccount.__table__.c.credential_id.foreign_keys)).column.table is feature.SocialCredential.__table__
assert next(iter(media.SocialMediaUpload.__table__.c.asset_id.foreign_keys)).column.table is domain.SocialMediaAsset.__table__
from fastapi import FastAPI
app = FastAPI()
app.include_router(api.router)
'''
    script += inspect.getsource(_assert_complete_public_prefix)
    script += '\n_assert_complete_public_prefix(app)\n'
    env = {**os.environ, 'DATABASE_URL': 'postgresql+psycopg2://test:test@127.0.0.1/unused'}
    env.pop('PYTHONPATH', None)
    result = subprocess.run([sys.executable, '-c', script], cwd=ROOT if package else ROOT/'backend', env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('broken_registration', ['double_prefix', 'missing_connections', 'missing_media'])
def test_public_route_assertion_rejects_incomplete_or_double_prefixed_apps(broken_registration):
    from fastapi import FastAPI
    from social import api

    app = FastAPI()
    if broken_registration == 'double_prefix':
        app.include_router(api.router, prefix='/api/v1/admin/social')
    else:
        app.include_router(api._editorial_router)
        app.include_router(
            api.media_router if broken_registration == 'missing_connections'
            else api.connection_router
        )
    with pytest.raises(AssertionError):
        _assert_complete_public_prefix(app)
