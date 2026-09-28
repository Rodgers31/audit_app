"""Loopback-only browser test API: real app, isolated SQLite, synthetic records.

Never connects to a deployment database and never starts ingestion/schedulers.
Control routes live only in this executable test harness, not the application.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PERSISTENT_DB = os.environ.get("AUDIT_BROWSER_FIXTURE_DB")
ROOT = Path(PERSISTENT_DB).parent if PERSISTENT_DB else Path(tempfile.mkdtemp(prefix="auditgava-browser-"))
ROOT.mkdir(parents=True, exist_ok=True)
os.environ.update(
    DATABASE_URL=f"sqlite:///{PERSISTENT_DB or ROOT / 'data.sqlite'}",
    REDIS_URL="",
    ENVIRONMENT="test",
    REVALIDATE_SECRET="browser-test-only-secret",
    CACHE_GENERATION_FILE=str(ROOT / "generation"),
    CORS_ORIGINS=os.environ.get("LOCAL_DEV_CORS_ORIGINS", "http://127.0.0.1:3125,http://localhost:3125"),
    DISABLE_RATE_LIMIT="true",
)

import database
from dev_fixtures import block_external_http, seed_local_fixture
from models import BudgetLine

seed_local_fixture(database)

import main
from contextlib import asynccontextmanager


@asynccontextmanager
async def _no_lifespan(app):
    yield


main.app.router.lifespan_context = _no_lifespan
main.app.router.on_startup.clear()
main.app.router.on_shutdown.clear()
block_external_http()


@main.app.middleware("http")
async def unavailable_debt_fixture(request, call_next):
    # Keep national prefetch absent so per-test browser fixtures are not hidden
    # by a successful hydrated no-data query with a one-hour staleTime.
    if request.url.path == "/api/v1/debt/national":
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {"status": "unavailable", "reason": "browser_fixture_absence"},
            status_code=503,
        )
    return await call_next(request)


@main.app.post("/__fixture/budget/{amount}")
def change_budget(amount: int):
    if amount not in {100000000000, 125000000000}:
        from fastapi import HTTPException

        raise HTTPException(
            400, "Only the two synthetic acceptance amounts are permitted"
        )
    with database.SessionLocal() as db:
        db.get(BudgetLine, 2).allocated_amount = amount
        db.commit()
    return {"amount": amount, "cache_cleared": False}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(main.app, host="127.0.0.1", port=int(os.environ.get("AUDIT_BROWSER_FIXTURE_PORT", "8125")))
