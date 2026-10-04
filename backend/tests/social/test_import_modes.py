"""New social modules preserve both supported launches without network access."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]

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
def test_connected_feature_first_registers_complete_schema_and_single_public_prefix(package):
    prefix = 'backend.' if package else ''
    script = f'''import socket
socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError("network"))
import {prefix}social.connections.models as feature
import {prefix}social.models as domain
import {prefix}social.api as api
assert feature.SocialCredential.metadata is domain.Base.metadata
assert {{t.name for t in domain.SOCIAL_TABLES}} == {{name for name in domain.Base.metadata.tables if name.startswith('social_')}}
assert len(domain.SOCIAL_TABLES) == len({{t.name for t in domain.SOCIAL_TABLES}})
assert next(iter(domain.SocialAccount.__table__.c.credential_id.foreign_keys)).column.table is feature.SocialCredential.__table__
paths = [route.path for route in api.router.routes]
assert '/api/v1/admin/social/connections/meta/status' in paths
assert '/api/v1/admin/social/accounts' in paths
assert not any('/social/api/v1/' in path for path in paths)
'''
    env = {**os.environ, 'DATABASE_URL': 'postgresql+psycopg2://test:test@127.0.0.1/unused'}
    env.pop('PYTHONPATH', None)
    result = subprocess.run([sys.executable, '-c', script], cwd=ROOT if package else ROOT/'backend', env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
