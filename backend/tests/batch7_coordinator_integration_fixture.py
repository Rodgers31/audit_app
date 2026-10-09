"""Loopback-only coordinator fixture: real routes, PostgreSQL and native worker.

Only identities/provider endpoints and the separately registered native domain
handler are synthetic. No product lifespan, dispatch implementation or receipts
are replaced. Never put this module on a deployed application's import path.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, StrictBool
from sqlalchemy import text
from tests.ci_browser_database import browser_database_port

BACKEND = Path(__file__).resolve().parents[1]
DATABASE_PORT = browser_database_port(55483)
URL = f"postgresql+psycopg2://batch7_coordinator:batch7-inert-coordinator-local@127.0.0.1:{DATABASE_PORT}/batch7_coordinator"
ADMIN = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
SERVICE_KEY = "batch7-coordinator-inert-service-key"

if os.environ.get("BATCH7_COORDINATOR_INTEGRATION") != "true" or os.environ.get("DATABASE_URL") != URL:
    raise RuntimeError("Explicit owned coordinator fixture environment required")

_connect = socket.socket.connect


def local_only(sock, address):
    if not isinstance(address, tuple) or address[:2] not in (("127.0.0.1", DATABASE_PORT), ("127.0.0.1", 8163)):
        raise RuntimeError("External transport refused by coordinator fixture")
    return _connect(sock, address)


socket.socket.connect = local_only

from database import SessionLocal, engine  # noqa: E402
from models import AdminAuditLog, Base, IngestionJob  # noqa: E402
from routers import admin, etl_admin  # noqa: E402
import supabase_auth  # noqa: E402

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:3163"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])
app.include_router(etl_admin.router)
app.include_router(admin.router)
workers: list[subprocess.Popen] = []
role = "admin"


def required_coordinator_migrations():
    """Require the exact additive migrations belonging to the actual models."""
    migrations = [("etl_dispatch_commands", "e554d7c9a001_etl_dedicated_dispatch.py")]
    if "seeding_domain_claims" in Base.metadata.tables:
        migrations.append(("seeding_domain_claims", "e572b8c9a001_shared_seeding_exclusion.py"))
    paths = [(table, BACKEND / "alembic/versions" / name) for table, name in migrations]
    for _, path in paths:
        if not path.is_file():
            raise RuntimeError("Missing required coordinator fixture migration: " + path.name)
    return paths


def prepare_database():
    """Existing observation/audit schema plus the actual declared migrations."""
    paths = required_coordinator_migrations()
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    migrations = []
    for table, path in paths:
        spec = importlib.util.spec_from_file_location("coordinator_migration_" + path.stem, path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migrations.append((table, migration))
    Base.metadata.create_all(engine, tables=[IngestionJob.__table__, AdminAuditLog.__table__])
    with engine.begin() as connection:
        for table, migration in migrations:
            if not connection.scalar(text("SELECT to_regclass(:table)"), {"table": "public." + table}):
                with Operations.context(MigrationContext.configure(connection)):
                    migration.upgrade()
        connection.execute(text("CREATE TABLE IF NOT EXISTS batch7_coordinator_control (mode text NOT NULL CHECK (mode IN ('normal','failure','before','after')))"))
        connection.execute(text("CREATE TABLE IF NOT EXISTS batch7_coordinator_effects (job_id integer NOT NULL REFERENCES ingestion_jobs(id))"))
        connection.execute(text("CREATE TABLE IF NOT EXISTS batch7_coordinator_markers (stage text NOT NULL, job_id integer NOT NULL REFERENCES ingestion_jobs(id))"))
        if not connection.scalar(text("SELECT count(*) FROM batch7_coordinator_control")):
            connection.execute(text("INSERT INTO batch7_coordinator_control VALUES ('normal')"))


def stop_workers():
    while workers:
        process = workers.pop()
        try:
            os.killpg(process.pid, signal.SIGCONT)
            os.killpg(process.pid, signal.SIGINT)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=3)
        # A supervisor may already have exited while its native child remains.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def start_worker():
    if any(process.poll() is None for process in workers):
        raise HTTPException(409, "An owned worker is already running")
    runtime = Path(os.environ["BATCH7_COORDINATOR_ARTIFACTS"]) / "native-runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHON_DOTENV_DISABLED": "1", "PYTHONPATH": str(BACKEND / "tests/batch7_coordinator_integration_worker") + os.pathsep + str(BACKEND),
           "DATABASE_URL": URL, "ADMIN_ETL_DISPATCH_ENABLED": "true",
           "BATCH7_COORDINATOR_INERT_WORKER": "true", "SEED_STORAGE_PATH": str(runtime / "storage"),
           "SEED_CACHE_PATH": str(runtime / "cache")}
    if DATABASE_PORT == 55494:
        env.update(BATCH9_CI_BROWSER="true", BROWSER_FIXTURE_POSTGRES_PORT="55494")
    process = subprocess.Popen([sys.executable, "-m", "admin_etl_dispatch_worker"], env=env, cwd=BACKEND,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=True)
    workers.append(process)
    return {"pid": process.pid}


def actor(request: Request):
    token = request.headers.get("authorization", "").removeprefix("Bearer ")
    claims = supabase_auth._decode_supabase_jwt(token)
    if claims.get("sub") not in (ADMIN, OTHER):
        raise HTTPException(401, "Unknown inert identity")
    return claims["sub"]


@app.middleware("http")
async def fixture_boundary(request: Request, call_next):
    if request.url.path.startswith("/fixture/") and request.client.host != "127.0.0.1":
        raise HTTPException(404, "Not found")
    response = await call_next(request)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Authorization"
    return response


@app.get("/auth/v1/user")
def auth_user(request: Request):
    return {"id": actor(request), "aud": "authenticated", "role": "authenticated",
            "email": "coordinator@example.invalid", "app_metadata": {}, "user_metadata": {},
            "created_at": "2026-01-01T00:00:00Z"}


@app.get("/rest/v1/profiles")
def profile(request: Request):
    if request.headers.get("authorization") == "Bearer " + SERVICE_KEY:
        identity = request.query_params.get("id", "").removeprefix("eq.")
        if identity not in (ADMIN, OTHER):
            return []
    else:
        identity = actor(request)
    data = {"id": identity, "email": "coordinator@example.invalid", "display_name": "Inert coordinator administrator", "roles": [role]}
    return data if "object+json" in request.headers.get("accept", "") else [data]


@app.get("/fixture/health")
def fixture_health():
    return {"fixture": "actual-router-postgresql-native-worker", "owned_database_port": DATABASE_PORT}


@app.post("/fixture/reset")
def fixture_reset():
    global role
    stop_workers()
    os.environ["ADMIN_ETL_DISPATCH_ENABLED"] = "false"
    role = "admin"
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE batch7_coordinator_markers,batch7_coordinator_effects,etl_dispatch_domains,etl_dispatch_commands,etl_dispatch_worker,admin_audit_log,ingestion_jobs RESTART IDENTITY CASCADE"))
        connection.execute(text("UPDATE batch7_coordinator_control SET mode='normal'"))
    return {"fixture": True, "enabled": False}


class FixtureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool | None = None
    mode: str | None = None
    profile_role: str | None = None
    expire_worker: StrictBool = False


@app.post("/fixture/config")
def configure(value: FixtureConfig):
    global role
    if value.mode is not None and value.mode not in ("normal", "failure", "before", "after"):
        raise HTTPException(422, "Unknown inert mode")
    if value.profile_role is not None and value.profile_role not in ("admin", "citizen"):
        raise HTTPException(422, "Unknown inert role")
    if value.enabled is not None:
        os.environ["ADMIN_ETL_DISPATCH_ENABLED"] = "true" if value.enabled else "false"
    if value.profile_role is not None:
        role = value.profile_role
    with engine.begin() as connection:
        if value.mode is not None:
            connection.execute(text("UPDATE batch7_coordinator_control SET mode=:mode"), {"mode": value.mode})
        if value.expire_worker:
            connection.execute(text("UPDATE etl_dispatch_worker SET last_seen_at=clock_timestamp()-interval '2 seconds', expires_at=clock_timestamp()-interval '1 second'"))
    return {"fixture": True}


@app.post("/fixture/worker/start")
def fixture_start():
    return start_worker()


@app.post("/fixture/worker/stop")
def fixture_stop():
    stop_workers()
    return {"fixture": True}


@app.post("/fixture/worker/pause-supervisor")
def pause_supervisor():
    if not workers or workers[-1].poll() is not None:
        raise HTTPException(409, "No owned supervisor")
    os.kill(workers[-1].pid, signal.SIGSTOP)
    return {"fixture": True}


@app.get("/fixture/state")
def fixture_state():
    with SessionLocal() as db:
        counts = {name: db.scalar(text("SELECT count(*) FROM " + table)) for name, table in (
            ("commands", "etl_dispatch_commands"), ("audits", "admin_audit_log"),
            ("jobs", "ingestion_jobs"), ("effects", "batch7_coordinator_effects"))}
        observations = db.execute(text("SELECT id,status::text,dry_run,metadata->>'dispatch_command_id' AS command_id,items_created FROM ingestion_jobs ORDER BY id")).mappings().all()
        audits = db.execute(text("SELECT actor_id,action,target_id,payload FROM admin_audit_log ORDER BY id")).mappings().all()
        domains = db.execute(text("SELECT domain,command_id::text,claim_token::text FROM etl_dispatch_domains")).mappings().all()
        markers = db.execute(text("SELECT stage,job_id FROM batch7_coordinator_markers")).mappings().all()
        commands = db.execute(text("SELECT id::text,actor_id,idempotency_key::text,source,dry_run,generation::text,claim_token::text,execution_started,status,version,job_id,audit_id,outcome FROM etl_dispatch_commands ORDER BY created_at,id")).mappings().all()
        return {"counts": counts, "observations": [dict(v) for v in observations], "audits": [dict(v) for v in audits],
                "domains": [dict(v) for v in domains], "markers": [dict(v) for v in markers],
                "commands": [dict(v) for v in commands],
                "workers": [{"pid": p.pid, "exit_code": p.poll()} for p in workers]}


if __name__ == "__main__":
    prepare_database()
    if "--prepare-database" not in sys.argv:
        import uvicorn
        try:
            uvicorn.run(app, host="127.0.0.1", port=8163)
        finally:
            stop_workers()
            engine.dispose()
