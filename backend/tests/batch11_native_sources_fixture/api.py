"""Real ETL HTTP router with explicit inert authentication and owned database."""
from fastapi import FastAPI
import supabase_auth
from routers import etl_admin

supabase_auth._decode_supabase_jwt = lambda token: {"sub": token}
supabase_auth._fetch_roles = lambda uid: ("batch11@example.invalid", ["admin"] if uid == "batch11-admin" else ["user"])
app = FastAPI()
app.include_router(etl_admin.router)
