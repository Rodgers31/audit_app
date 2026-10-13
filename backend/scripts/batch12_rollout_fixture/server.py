"""Real ETL router/auth decoder over HTTP, with an owned profile lookup seam.

This app omits backend.main lifespan. It does not establish deployed startup,
JWKS/provider authentication, or production profile-role acceptance.
"""
import os

from fastapi import FastAPI
import supabase_auth
from routers import etl_admin

if os.environ.get("BATCH12_INERT_PROCESS") != "true":
    raise RuntimeError("Owned fixture required")


def owned_roles(user_id):
    roles = ["admin"] if user_id == os.environ["BATCH12_ADMIN_SUBJECT"] else ["user"]
    return "owned@example.invalid", roles


supabase_auth._fetch_roles = owned_roles
app = FastAPI()
app.include_router(etl_admin.router)
