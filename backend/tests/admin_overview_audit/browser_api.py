"""Loopback fixture: real admin routers/auth, inert Supabase transport, SQLite.

Only this executable owns its disposable resources. No startup, worker, email
or external storage is run. Control routes exist only in this harness.
"""
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
ROOT = Path(tempfile.mkdtemp(prefix="batch6-admin-overview-audit-"))
os.environ.update(DATABASE_URL=f"sqlite:///{ROOT / 'audit.sqlite'}", PYTHON_DOTENV_DISABLED="1", SUPABASE_JWT_SECRET="admin-overview-audit-inert-key")

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

@compiles(JSONB, "sqlite")
def jsonb_sqlite(element, compiler, **kw):
    return "TEXT"

import database
import supabase_admin
import admin_users_provider
from dev_fixtures import block_external_http
from models import AdminAuditLog, IngestionJob
from routers import admin, admin_audit_log, admin_users, etl_admin
from supabase_auth import _decode_supabase_jwt

block_external_http()
AdminAuditLog.__table__.create(database.engine)
IngestionJob.__table__.create(database.engine)
ACTOR = "00000000-0000-4000-8000-000000000001"
CITIZEN = "00000000-0000-4000-8000-000000000002"
UNPROFILED = "00000000-0000-4000-8000-000000000003"
NOW = datetime.now(timezone.utc)
with database.SessionLocal() as db:
    for i in range(1, 29):
        db.add(AdminAuditLog(actor_id=ACTOR, actor_email="admin@example.invalid", action="etl.trigger", target_type="etl_source", target_id="cob", payload={"job_id": i, "dry_run": True, "access_token": "INERT_SECRET"}, created_at=NOW))
    db.commit()

def profile(uid):
    return {"id": uid, "email": "admin@example.invalid", "display_name": "Inert fixture", "roles": ["admin"] if uid == ACTOR else ["citizen"]}
supabase_admin.get_profile = profile
supabase_admin.count_profiles = lambda **kwargs: 1 if kwargs.get("column") == "roles" else 2
# The users router enumerates Auth identities rather than profile counts. Keep
# one unprofiled identity so the real combined producer tests that distinction.
AUTH_USERS = [{"id": uid, "email": "inert@example.invalid", "created_at": NOW.isoformat(),
               "app_metadata": {}, "user_metadata": {}} for uid in (ACTOR, CITIZEN, UNPROFILED)]
admin_users_provider.list_users = lambda *, page=1, per_page=100: {"users": AUTH_USERS[(page - 1) * per_page:page * per_page]}
admin_users_provider.get_profiles = lambda ids: [profile(uid) for uid in ids if uid in {ACTOR, CITIZEN}]
# The real calendar scheduler reads no deployment state for schedule summaries.
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:3153"], allow_methods=["GET", "POST"], allow_headers=["*"])
for router in (admin.router, admin_audit_log.router, admin_users.router, etl_admin.router):
    app.include_router(router)
MODE = "normal"

@app.middleware("http")
async def modes(request, call_next):
    if request.url.path == "/api/v1/admin/audit-log" and MODE == "audit-error":
        return JSONResponse({"detail": "Audit evidence is unavailable."}, status_code=503, headers=admin_audit_log.PRIVATE)
    if request.url.path == "/api/v1/admin/audit-log" and MODE == "audit-malformed":
        return JSONResponse({"entries": [], "total": -1}, headers=admin_audit_log.PRIVATE)
    return await call_next(request)

@app.get('/health')
def health():
    return {"fixture": "admin-overview-audit", "external_io": False}

@app.post('/__fixture/mode/{mode}')
def mode(mode: str):
    global MODE
    if mode not in {"normal", "audit-error", "audit-malformed"}:
        raise HTTPException(400, "Unsupported fixture mode")
    MODE = mode
    return {"mode": MODE}

def identity(request):
    bearer = request.headers.get("authorization", "")
    if not bearer.startswith("Bearer "):
        raise HTTPException(401)
    return _decode_supabase_jwt(bearer[7:])["sub"]

@app.get('/auth/v1/user')
def user(request: Request):
    uid = identity(request)
    return {"id": uid, "aud": "authenticated", "role": "authenticated", "email": "admin@example.invalid", "app_metadata": {}, "user_metadata": {}, "created_at": NOW.isoformat()}

@app.get('/rest/v1/profiles')
def profiles(request: Request):
    return JSONResponse(profile(identity(request)), headers={"Cache-Control": "private, no-store"})

@app.post('/auth/v1/logout')
def logout():
    return {}

@app.get('/api/v1/admin/social/system/status')
def social_status(request: Request):
    if profile(identity(request))["roles"] != ["admin"]:
        raise HTTPException(403)
    return JSONResponse({"publishing_enabled": False, "worker": {"state": "unavailable", "heartbeat_at": None, "last_scan_at": None}, "queue_counts": {}}, headers=admin_audit_log.PRIVATE)

if __name__ == '__main__':
    import shutil
    import uvicorn
    try:
        uvicorn.run(app, host="127.0.0.1", port=8153, access_log=False)
    finally:
        database.engine.dispose()
        shutil.rmtree(ROOT)
