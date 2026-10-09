"""PR review reproductions, using backend-only packaging and inert auth."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from fastapi import HTTPException

import supabase_auth
from test_admin_operations_lane import AUTH, operations


_decode_supabase_jwt = supabase_auth._decode_supabase_jwt
OPERATIONS_ROUTES = [
    ("ingestion-jobs", "get"), ("ingestion-jobs/1", "get"),
    ("ingestion-jobs/stats/summary", "get"), ("etl/schedule", "get"),
    ("etl/schedule/summary", "get"), ("etl/schedule/source/oag", "get"),
    ("etl/health", "get"), ("etl/trigger/oag", "post"),
]


def test_backend_only_image_layout_serves_all_calendar_reads(tmp_path):
    """COPY ./backend to /app must not require the repository's sibling etl."""
    source = Path(__file__).resolve().parents[1]
    packaged = tmp_path / "app"
    shutil.copytree(source, packaged, ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc", ".env", ".env.*", "venv", ".venv", ".venv313",
        ".pytest_cache", "*.sqlite", "*.sqlite3", "*.db", "*.log", "downloads",
        "uploads", "logs", "node_modules",
    ))
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "PYTHONPATH": str(packaged), "PYTHON_DOTENV_DISABLED": "1",
           "DATABASE_URL": "sqlite:///" + str(tmp_path / "packaged.sqlite")}
    script = """
import etl, seeding
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers import etl_admin
from supabase_auth import AdminUser, require_admin
assert etl.__file__.startswith(__import__('os').getcwd())
assert seeding.__file__.startswith(__import__('os').getcwd())
app = FastAPI()
app.include_router(etl_admin.router)
app.dependency_overrides[require_admin] = lambda: AdminUser('inert', None, ['admin'])
with TestClient(app) as client:
    responses = [client.get('/api/v1/admin/etl/' + path) for path in
                 ['schedule', 'schedule/summary', 'schedule/source/oag', 'health']]
    assert [r.status_code for r in responses] == [200, 200, 200, 200]
    assert responses[0].json()['evidence'] == 'calendar_plan'
    assert len(responses[0].json()['sources']) == 6
    assert responses[1].json()['total_sources'] == 6
    assert responses[2].json()['source'] == 'oag'
    assert responses[3].json()['plan_status'] == 'available'
    assert responses[3].json()['worker_status'] == 'unverified'
    assert client.post('/api/v1/admin/etl/trigger/oag', json={'dry_run': True}).status_code == 503
print('packaged_calendar 6 200,200,200,200 unverified')
"""
    result = subprocess.run([sys.executable, "-c", script], cwd=packaged,
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "packaged_calendar 6 200,200,200,200 unverified"


def test_repository_planner_import_and_direct_script_remain_available(tmp_path):
    root = Path(__file__).resolve().parents[2]
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "PYTHONPATH": str(root), "PYTHON_DOTENV_DISABLED": "1"}
    script = """
from etl.smart_scheduler import SmartScheduler, should_run_etl
scheduler = SmartScheduler()
report = scheduler.generate_schedule_report()
assert set(report) == {'treasury', 'cob', 'oag', 'knbs', 'opendata', 'cra'}
for source in report:
    assert should_run_etl(source) == scheduler.should_run(source)
print('root_planner 6')
"""
    result = subprocess.run([sys.executable, "-c", script], cwd=tmp_path,
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "root_planner 6"
    result = subprocess.run([sys.executable, str(root / "etl/smart_scheduler.py")],
                            cwd=tmp_path, env={"PATH": env["PATH"], "PYTHON_DOTENV_DISABLED": "1"},
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "SMART ETL SCHEDULER - Current Status" in result.stdout
    assert all("📊 " + source.upper() in result.stdout for source in
               ["treasury", "cob", "oag", "knbs", "opendata", "cra"])


@pytest.mark.parametrize("route,method", OPERATIONS_ROUTES)
def test_actual_jwt_unknown_key_diagnostic_is_not_returned(operations, monkeypatch, route, method):
    client, _, _ = operations
    monkeypatch.setattr(supabase_auth, "_decode_supabase_jwt", _decode_supabase_jwt)
    monkeypatch.setattr(supabase_auth, "_fetch_jwks", lambda **kwargs: {"keys": []})
    header = base64.urlsafe_b64encode(json.dumps(
        {"alg": "ES256", "kid": "INERT_PRIVATE_KEY_IDENTIFIER"}).encode()).rstrip(b"=").decode()
    response = getattr(client, method)("/api/v1/admin/" + route,
        headers={"Authorization": "Bearer " + header + ".e30.invalid"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
    assert "INERT_PRIVATE_KEY_IDENTIFIER" not in response.text
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Authorization"


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize("route,method", OPERATIONS_ROUTES)
def test_all_auth_dependency_error_bodies_are_static(operations, status, route, method):
    client, _, _ = operations

    def diagnostic_failure():
        raise HTTPException(status_code=status,
            detail={"diagnostic": "INERT_PRIVATE_AUTH_DIAGNOSTIC"},
            headers={"WWW-Authenticate": "Bearer"})

    client.app.dependency_overrides[supabase_auth.require_admin] = diagnostic_failure
    response = getattr(client, method)("/api/v1/admin/" + route, headers=AUTH)
    assert response.status_code == status
    assert response.json() == {"detail": "Authentication required" if status == 401 else "Admin access required"}
    assert "INERT_PRIVATE_AUTH_DIAGNOSTIC" not in response.text
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["cache-control"] == "private, no-store"
