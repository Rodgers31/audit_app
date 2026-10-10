"""Owned loopback API fixture for the durable design prototype."""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from contextlib import asynccontextmanager

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "backend"))
if (
    os.getenv("ISSUE611_OWNED_POSTGRES") != "1"
    or os.getenv("PYTHON_DOTENV_DISABLED") != "1"
):
    raise RuntimeError("Explicit owned fixture and disabled dotenv required")

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import supabase_admin
from database import get_db
from models import AdminAuditLog
from routers.admin_audit_log import PRIVATE
import prototype
from supabase_auth import _decode_supabase_jwt

ACTOR = "00000000-0000-4000-8000-000000000001"
owner = create_engine("postgresql+psycopg2://inert:inert@127.0.0.1:55534/issue611")
reader = create_engine(
    "postgresql+psycopg2://issue611_reader:inert@127.0.0.1:55534/issue611"
)
writer = create_engine(
    "postgresql+psycopg2://issue611_writer:inert@127.0.0.1:55534/issue611"
)
AdminAuditLog.__table__.create(owner)
prototype.install_owned(owner)
factory = sessionmaker(bind=writer)
with factory() as db:
    for i in range(28):
        db.add(
            AdminAuditLog(
                actor_id=ACTOR,
                action="etl.trigger",
                target_type="etl_source",
                target_id="cob",
                payload={
                    "job_id": i + 1,
                    "dry_run": True,
                    "access_token": "INERT_SECRET",
                },
                created_at=datetime.now(timezone.utc),
            )
        )
    db.commit()
supabase_admin.get_profile = lambda uid: {
    "id": uid,
    "roles": ["admin"] if uid == ACTOR else ["citizen"],
    "email": "admin@example.invalid",
}


CLEANED = False


def cleanup():
    global CLEANED
    if not CLEANED:
        reader.dispose()
        writer.dispose()
        with owner.begin() as db:
            db.execute(text("DROP TABLE IF EXISTS admin_audit_log,issue611_capability"))
            db.execute(text("DROP FUNCTION issue611_capture(),issue611_immutable()"))
            for role in ("issue611_reader", "issue611_writer", "issue611_untrusted"):
                db.execute(text(f"DROP OWNED BY {role}"))
                db.execute(text(f"DROP ROLE {role}"))
        owner.dispose()
        CLEANED = True


@asynccontextmanager
async def lifespan(app):
    try:
        yield
    finally:
        cleanup()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:13034"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(prototype.router)


def sessions():
    with sessionmaker(bind=reader)() as db:
        yield db


app.dependency_overrides[get_db] = sessions


@app.get("/health")
def health():
    with owner.connect() as db:
        return {
            "fixture": "issue611",
            "snapshot": db.scalar(text("SELECT pg_current_snapshot()::text")),
        }


@app.get("/rest/v1/profiles")
def profiles(request: Request):
    uid = identity(request)
    return JSONResponse(
        {
            "id": uid,
            "roles": ["admin"] if uid == ACTOR else ["citizen"],
            "email": "admin@example.invalid",
        },
        headers=PRIVATE,
    )


def identity(request):
    bearer = request.headers.get("authorization", "")
    if not bearer.startswith("Bearer "):
        raise HTTPException(401)
    return _decode_supabase_jwt(bearer[7:])["sub"]


@app.get("/auth/v1/user")
def user(request: Request):
    return {
        "id": identity(request),
        "aud": "authenticated",
        "role": "authenticated",
        "email": "admin@example.invalid",
        "app_metadata": {},
        "user_metadata": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/__fixture/unavailable")
def unavailable():
    with owner.begin() as db:
        db.execute(text("UPDATE issue611_capability SET ready=false"))
    return JSONResponse({"ready": False}, headers=PRIVATE)


@app.post("/__fixture/restore-ready")
def restore_ready():
    with owner.begin() as db:
        db.execute(text("UPDATE issue611_capability SET ready=true"))
    return JSONResponse({"ready": True}, headers=PRIVATE)


@app.post("/__fixture/cleanup")
def cleanup_endpoint():
    cleanup()
    with owner.connect() as db:
        tables = db.scalar(
            text("SELECT count(*) FROM pg_tables WHERE schemaname='public'")
        )
        roles = db.scalar(
            text(
                "SELECT count(*) FROM pg_roles WHERE rolname IN ('issue611_reader','issue611_writer','issue611_untrusted')"
            )
        )
    if tables != 0 or roles != 0:
        raise RuntimeError("Owned fixture cleanup readback failed")
    return {"tables": tables, "roles": roles}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=18034)
