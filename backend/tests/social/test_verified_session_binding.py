"""Social OAuth reuses verified Supabase session identity, not unverified claims."""
import time
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt

import supabase_auth


def credentials(monkeypatch, session_id):
    secret = 'local-social-auth-fixture-key-only'
    monkeypatch.setenv('SUPABASE_JWT_SECRET', secret)
    monkeypatch.setattr(supabase_auth, '_fetch_roles', lambda user_id: ('fixture@example.test', ['admin']))
    claims = {'sub': str(uuid4()), 'aud': 'authenticated', 'exp': int(time.time()) + 300,
              'session_id': session_id}
    token = jwt.encode(claims, secret, algorithm='HS256')
    return HTTPAuthorizationCredentials(scheme='Bearer', credentials=token), claims


def test_existing_admin_carries_only_verified_session_identity(monkeypatch):
    session_id = str(uuid4())
    bearer, claims = credentials(monkeypatch, session_id)
    admin = supabase_auth.get_current_user(bearer)
    assert admin.id == claims['sub']
    assert getattr(admin, 'session_id', None) == session_id
    assert supabase_auth.require_admin(admin) is admin


def test_forged_session_cannot_reach_current_admin(monkeypatch):
    bearer, claims = credentials(monkeypatch, str(uuid4()))
    claims['session_id'] = str(uuid4())
    forged = jwt.encode(claims, 'a-different-fixture-key', algorithm='HS256')
    with pytest.raises(HTTPException) as rejected:
        supabase_auth.get_current_user(HTTPAuthorizationCredentials(scheme='Bearer', credentials=forged))
    assert rejected.value.status_code == 401


def test_legacy_admin_callers_keep_optional_session_identity():
    admin = supabase_auth.AdminUser(id=str(uuid4()), email=None, roles=['admin'])
    assert getattr(admin, 'session_id', None) is None
