"""Loopback-only browser test API: real app, isolated SQLite, synthetic records.

Never connects to a deployment database and never starts ingestion/schedulers.
Control routes live only in this executable test harness, not the application.
"""

import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
ROOT = Path(tempfile.mkdtemp(prefix="auditgava-browser-"))
os.environ.update(
    DATABASE_URL=f"sqlite:///{ROOT}/data.sqlite",
    REDIS_URL="",
    ENVIRONMENT="test",
    REVALIDATE_SECRET="browser-test-only-secret",
    CACHE_GENERATION_FILE=str(ROOT / "generation"),
    CORS_ORIGINS="http://127.0.0.1:3125,http://localhost:3125",
    DISABLE_RATE_LIMIT="true",
)

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB


@compiles(JSONB, "sqlite")
def _jsonb(element, compiler, **kw):
    return "TEXT"


import database
from models import (
    Base,
    Country,
    Entity,
    EntityType,
    FiscalPeriod,
    SourceDocument,
    DocumentType,
    BudgetLine,
)

Base.metadata.create_all(database.engine)
with database.SessionLocal() as db:
    db.add(
        Country(
            id=1,
            iso_code="KEN",
            name="Kenya",
            currency="KES",
            timezone="Africa/Nairobi",
            default_locale="en_KE",
        )
    )
    for pk, name, code in [(47, "Nairobi", "047"), (1, "Mombasa", "001")]:
        db.add(
            Entity(
                id=pk,
                country_id=1,
                type=EntityType.COUNTY,
                canonical_name=name,
                slug=name.lower(),
                meta={"county_code": code},
            )
        )
    for pk, label, year in [(1, "FY2024/25", 2024), (2, "FY2025/26 9M", 2025)]:
        db.add(
            FiscalPeriod(
                id=pk,
                country_id=1,
                label=label,
                start_date=datetime(year, 7, 1),
                end_date=datetime(year + 1, 3 if pk == 2 else 6, 30),
            )
        )
    db.add(
        SourceDocument(
            id=1,
            country_id=1,
            publisher="Controller of Budget",
            title="Synthetic CBIRR browser acceptance publication",
            url="https://cob.go.ke/browser-fixture.pdf",
            doc_type=DocumentType.BUDGET,
            fetch_date=datetime.now(timezone.utc),
            meta={"publication_date": datetime.now(timezone.utc).date().isoformat()},
        )
    )
    db.flush()
    for pk, period, amount in [(1, 1, 50000000000), (2, 2, 100000000000)]:
        db.add(
            BudgetLine(
                id=pk,
                entity_id=47,
                period_id=period,
                category="Total",
                line_type="total",
                allocated_amount=amount,
                actual_spent=0,
                currency="KES",
                source_document_id=1,
                publishable=True,
                page_ref="1",
            )
        )
    db.commit()

import main
from contextlib import asynccontextmanager


@asynccontextmanager
async def _no_lifespan(app):
    yield


main.app.router.lifespan_context = _no_lifespan
main.app.router.on_startup.clear()
main.app.router.on_shutdown.clear()
# A deterministic fixture must never reach a remote publisher, including APIs
# that use requests/httpx internally for optional comparisons.
import requests
import httpx
from urllib.parse import urlparse

_original_send = requests.Session.send


def _send(self, request, **kwargs):
    if urlparse(request.url).hostname not in {"localhost", "127.0.0.1"}:
        raise requests.ConnectionError("External network disabled in browser fixture")
    return _original_send(self, request, **kwargs)


requests.Session.send = _send
_original_async = httpx.AsyncHTTPTransport.handle_async_request
_original_sync = httpx.HTTPTransport.handle_request


async def _async(self, request):
    if request.url.host not in {"localhost", "127.0.0.1"}:
        raise httpx.ConnectError("External network disabled in browser fixture")
    return await _original_async(self, request)


def _sync(self, request):
    if request.url.host not in {"localhost", "127.0.0.1"}:
        raise httpx.ConnectError("External network disabled in browser fixture")
    return _original_sync(self, request)


httpx.AsyncHTTPTransport.handle_async_request = _async
httpx.HTTPTransport.handle_request = _sync


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

    uvicorn.run(main.app, host="127.0.0.1", port=8125)
