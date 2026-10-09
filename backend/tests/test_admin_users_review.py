"""Coordinator review regressions: real signed auth and provider execution."""
import asyncio
from datetime import datetime, timedelta, timezone
import importlib
import os
from pathlib import Path
import subprocess
import sys
import threading

import httpx
import pytest
from jose import jwt
from fastapi import FastAPI

import supabase_auth
import supabase_admin as shared_provider
from routers import admin_users
from test_admin_users_boundaries import ACTOR, TARGET, ROOT, harness


@pytest.mark.parametrize('row', [
    {'id': ACTOR, 'roles': {'admin': False}}, {'id': ACTOR, 'roles': 'admin'},
    {'id': ACTOR, 'roles': ['admin', None]}, {'id': ACTOR, 'roles': ['admin', True]},
    {'id': ACTOR, 'roles': ['admin', '']}, {'id': ACTOR, 'roles': ['admin', ' ']},
    {'id': TARGET, 'roles': ['admin']}, {'roles': ['admin']},
    {'id': ACTOR, 'roles': None}, ['admin'], 'admin', 1,
])
def test_signed_auth_rejects_bad_profile(harness, monkeypatch, row):
    harness.app.dependency_overrides.pop(supabase_auth.get_current_user)
    monkeypatch.setenv('SUPABASE_JWT_SECRET', 'inert-review-secret')
    monkeypatch.setattr(shared_provider, 'get_profile', lambda _uid: row)
    token = jwt.encode({'sub': ACTOR, 'aud': 'authenticated', 'exp': datetime.now(timezone.utc) + timedelta(minutes=5)}, 'inert-review-secret', algorithm='HS256')
    response = harness.client.get(ROOT, headers={'Authorization': 'Bearer '+token})
    assert response.status_code == 403
    assert harness.provider.calls == []


@pytest.mark.parametrize('roles,status', [(['admin'], 200), (['citizen','admin','legacy-role'],200), (['citizen'],403), ([],403)])
def test_signed_auth_preserves_legitimate_role_arrays(harness, monkeypatch, roles, status):
    harness.app.dependency_overrides.pop(supabase_auth.get_current_user)
    monkeypatch.setenv('SUPABASE_JWT_SECRET', 'inert-review-secret')
    monkeypatch.setattr(shared_provider, 'get_profile', lambda _uid: {'id': ACTOR, 'roles':roles})
    token=jwt.encode({'sub': ACTOR,'aud':'authenticated','exp':datetime.now(timezone.utc)+timedelta(minutes=5)},'inert-review-secret',algorithm='HS256')
    assert harness.client.get(ROOT,headers={'Authorization':'Bearer '+token}).status_code==status


@pytest.mark.parametrize('mode', ['backend.admin_users_provider', 'admin_users_provider'])
def test_users_provider_fresh_import_modes(mode, tmp_path):
    tree=Path(__file__).resolve().parents[2]
    search=tree if mode.startswith('backend.') else tree/'backend'
    command=f'import {mode} as p; p.record_admin_action(None,actor=type("Actor",(),{{"id":"{ACTOR}","email":None}})(),action="users.fixture")'
    env={**os.environ,'PYTHONPATH':str(search),'DATABASE_URL':'sqlite:///'+str(tmp_path/'imports.sqlite'),'PYTHON_DOTENV_DISABLED':'1'}
    result=subprocess.run([sys.executable,'-c',command],env=env,cwd=tmp_path,capture_output=True,text=True)
    assert result.returncode==0, result.stderr


async def _verify_provider_barrier(app, path, started, release):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://fixture') as client:
        task = asyncio.create_task(client.get(path))
        try:
            assert await asyncio.to_thread(started.wait, 3), 'Provider did not enter its bounded barrier'
            assert not task.done() and not release.is_set(), 'Provider completed before unrelated request'
            response = await asyncio.wait_for(client.get('/review-health'), timeout=1)
            assert response.status_code == 200
            assert not task.done() and not release.is_set(), 'Provider completed before unrelated request'
        finally:
            release.set()
            response = await asyncio.wait_for(task, timeout=3)
        assert response.status_code == 200


@pytest.mark.parametrize('path', [ROOT, ROOT+'/stats', ROOT+'/'+TARGET])
def test_slow_provider_does_not_stall_unrelated_requests(harness, monkeypatch, path):
    started = threading.Event()
    release = threading.Event()
    method='get_user' if path.endswith(TARGET) else 'list_users'
    original=getattr(admin_users.supabase_admin,method)
    def slow(*args,**kwargs):
        started.set()
        assert release.wait(5), 'Provider barrier was not released'
        return original(*args,**kwargs)
    monkeypatch.setattr(admin_users.supabase_admin,method,slow)
    @harness.app.get('/review-health')
    async def health():
        return {'ok':True}
    asyncio.run(_verify_provider_barrier(harness.app, path, started, release))


def test_provider_barrier_rejects_an_event_loop_blocking_handler():
    app = FastAPI()
    started = threading.Event()
    release = threading.Event()

    @app.get('/blocked-provider')
    async def blocked_provider():
        started.set()
        assert release.wait(3)
        return {'fixture': True}

    @app.get('/review-health')
    async def health():
        return {'ok': True}

    # This watchdog only bounds the deliberately faulty handler. The probe
    # must notice it could not answer health while that handler was blocked.
    watchdog = threading.Timer(1, release.set)
    watchdog.start()
    try:
        with pytest.raises(AssertionError, match='Provider completed before unrelated request'):
            asyncio.run(_verify_provider_barrier(app, '/blocked-provider', started, release))
    finally:
        release.set()
        watchdog.cancel()
        watchdog.join(timeout=2)

@pytest.mark.parametrize('status',[401,403,500,503])
def test_private_users_auth_failures_hide_internal_detail(harness,status):
    from fastapi import HTTPException
    def fail():
        raise HTTPException(status,'PRIVATE_REVIEW_JWKS_MARKER',headers={'WWW-Authenticate':'Bearer'})
    harness.app.dependency_overrides[supabase_auth.get_current_user]=fail
    response=harness.client.get(ROOT)
    assert response.status_code==(503 if status>=500 else status)
    assert 'PRIVATE_REVIEW_JWKS_MARKER' not in response.text
    assert 'no-store' in response.headers.get('cache-control','')
    assert response.headers.get('vary')=='Authorization'


def test_invalid_reset_input_is_not_reflected(harness):
    response=harness.client.post(ROOT+'/'+TARGET+'/send-reset',json={'redirect_to':{'token':'PRIVATE_REVIEW_RESET_MARKER'}})
    assert response.status_code==422
    assert 'PRIVATE_REVIEW_RESET_MARKER' not in response.text


@pytest.mark.parametrize('redirect',[None,'https://fixture.invalid/reset?inert=a%20b#fragment'])
def test_recover_matches_official_query_redirect_contract(monkeypatch,redirect):
    captured=[]
    def handler(request):
        import json
        captured.append(request)
        assert json.loads(request.content)=={'email':'inert@example.invalid'}
        assert request.url.params.get('redirect_to')==redirect
        return httpx.Response(200,json={})
    real=httpx.Client
    monkeypatch.setenv('SUPABASE_URL','https://fixture.invalid')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY','inert-review-key')
    monkeypatch.setattr(admin_users.supabase_admin.httpx,'Client',lambda **kwargs:real(transport=httpx.MockTransport(handler),**kwargs))
    assert admin_users.supabase_admin.send_password_reset('inert@example.invalid',redirect)=={}
    assert len(captured)==1
