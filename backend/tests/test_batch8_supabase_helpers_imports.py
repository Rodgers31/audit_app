"""Fresh supported imports execute both provider consumers with no sockets."""

from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("prefix", ["", "backend."])
def test_profile_read_and_safe_error_contract_survives_fresh_import_modes(prefix, tmp_path):
    tree = Path(__file__).resolve().parents[2]
    code = '''
from datetime import datetime, timedelta, timezone
import importlib
import os
import socket
import httpx
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt

def deny(*args, **kwargs):
    raise AssertionError("No socket transport is permitted")
socket.socket.connect = deny
socket.socket.connect_ex = deny
prefix = os.environ["IMPORT_PREFIX"]
shared = importlib.import_module(prefix + "supabase_admin")
auth = importlib.import_module(prefix + "supabase_auth")
active = importlib.import_module(prefix + "admin_users_provider")
assert auth.supabase_admin is shared
assert active.SupabaseAdminError is shared.SupabaseAdminError
uid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
row = {"id": uid, "roles": ["admin"], "email": "fixture@example.invalid"}
response = httpx.Response(200, json=[row])
requests = []
def transport(request):
    requests.append(request)
    assert request.url.host == "batch8-helper.invalid"
    return response
real = httpx.Client
httpx.Client = lambda **kwargs: real(transport=httpx.MockTransport(transport), **kwargs)
assert shared.get_profile(uid) == row
assert shared.get_profiles([uid]) == [row]
assert active.get_profile(uid) == row
token = jwt.encode({"sub": uid, "aud": "authenticated",
                   "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                  "inert-batch8-jwt-secret", algorithm="HS256")
credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
assert auth.require_admin(auth.get_current_user(credentials)).roles == ["admin"]
response = httpx.Response(503, json={"message": "inert-sensitive-diagnostic-marker"})
for provider in (shared, active):
    try:
        provider.get_profile(uid)
    except shared.SupabaseAdminError as error:
        assert error.status_code == 503 and error.body is None
        assert str(error) == "Supabase admin API returned 503"
    else:
        raise AssertionError("Provider errors must fail")
assert auth.get_current_user(credentials).roles == []
assert len(requests) == 7
print("7 memory calls: profile single/bulk, active provider, signed auth, safe errors; no sockets")
'''
    environment = {
        "PATH": "/usr/bin:/bin", "PYTHONPATH": str(tree if prefix else tree / "backend"),
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHON_DOTENV_DISABLED": "1",
        "DATABASE_URL": "sqlite:///" + str(tmp_path / "imports.sqlite"),
        "SUPABASE_URL": "https://batch8-helper.invalid",
        "SUPABASE_SERVICE_ROLE_KEY": "inert-batch8-service-key",
        "SUPABASE_JWT_SECRET": "inert-batch8-jwt-secret", "IMPORT_PREFIX": prefix,
    }
    result = subprocess.run([sys.executable, "-c", code], env=environment, cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "7 memory calls" in result.stdout
