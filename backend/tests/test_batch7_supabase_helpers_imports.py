"""Execute both supported import paths in fresh, owned, inert processes."""

from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("prefix", ["", "backend."])
def test_fresh_imports_execute_shared_auth_and_active_users_transports(prefix, tmp_path):
    tree = Path(__file__).resolve().parents[2]
    code = '''
from datetime import datetime, timedelta, timezone
import importlib
import os
from pathlib import Path
import socket

import httpx
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt

def refuse_socket(*args, **kwargs):
    raise AssertionError("No socket transport is permitted")
socket.socket.connect = refuse_socket

prefix = os.environ["IMPORT_PREFIX"]
shared = importlib.import_module(prefix + "supabase_admin")
auth = importlib.import_module(prefix + "supabase_auth")
active = importlib.import_module(prefix + "admin_users_provider")
assert auth.supabase_admin is shared
assert active.SupabaseAdminError is shared.SupabaseAdminError
assert Path(shared.__file__).resolve() == Path(os.environ["OWNED_BACKEND"]) / "supabase_admin.py"
uid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
row = {"id": uid, "roles": ["admin"], "email": "fixture@example.invalid"}
requests = []

def transport(request):
    requests.append(request)
    assert request.url.host == "batch7-helper.invalid"
    assert request.headers.get_list("apikey") == ["inert-batch7-service-key"]
    assert request.headers.get_list("authorization") == ["Bearer inert-batch7-service-key"]
    return httpx.Response(200, json=[row], headers={"Content-Range": "0-0/3"})

real_client = httpx.Client
httpx.Client = lambda **kwargs: real_client(transport=httpx.MockTransport(transport), **kwargs)
assert shared.update_profile_roles(uid, ["admin"]) == row
assert shared.count_profiles() == 3
token = jwt.encode({"sub": uid, "aud": "authenticated", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                   "inert-batch7-jwt-secret", algorithm="HS256")
actor = auth.get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
assert actor.id == uid and actor.roles == ["admin"]
assert active.update_profile_roles(uid, ["admin"]) == row
assert len(requests) == 4
assert [request.method for request in requests] == ["PATCH", "GET", "GET", "PATCH"]
assert requests[0].headers.get_list("prefer") == ["return=representation"]
assert requests[1].headers.get_list("prefer") == ["count=exact"]
assert requests[3].headers.get_list("prefer") == ["return=representation"]
print("4 memory transport calls; shared role/count, signed auth and active provider pass; no sockets")
'''
    environment = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(tree if prefix else tree / "backend"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHON_DOTENV_DISABLED": "1",
        "DATABASE_URL": "sqlite:///" + str(tmp_path / "imports.sqlite"),
        "SUPABASE_URL": "https://batch7-helper.invalid",
        "SUPABASE_SERVICE_ROLE_KEY": "inert-batch7-service-key",
        "SUPABASE_JWT_SECRET": "inert-batch7-jwt-secret",
        "IMPORT_PREFIX": prefix,
        "OWNED_BACKEND": str(tree / "backend"),
    }
    result = subprocess.run([sys.executable, "-c", code], env=environment, cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "4 memory transport calls" in result.stdout
