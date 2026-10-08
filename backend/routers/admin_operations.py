"""Safe operational projections; stored runner diagnostics stay private."""
from datetime import datetime

from fastapi import HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
import logging
import re
from sqlalchemy import case, func

from models import IngestionJob

PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "Vary": "Authorization"}
DIAGNOSTIC_NOTICE = "Diagnostic withheld; inspect the dedicated runner logs."
DISPATCH_REASON = "Manual execution is unavailable: no dedicated worker dispatch is connected. No job was accepted."
DISPATCH_ERROR = {"code": "manual_dispatch_unavailable", "message": DISPATCH_REASON}
logger = logging.getLogger(__name__)


class OperationsRoute(APIRoute):
    """Keep dependency, validation and storage failures private and non-cacheable."""
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def private_handler(request):
            try:
                response = await handler(request)
            except RequestValidationError:
                response = JSONResponse(status_code=422, content={"detail": "Invalid operations parameters"})
            except HTTPException as exc:
                detail = exc.detail
                if exc.status_code >= 500 and detail != DISPATCH_ERROR:
                    detail = "Operations data unavailable"
                response = JSONResponse(status_code=exc.status_code, content={"detail": detail}, headers=exc.headers)
            except Exception:
                logger.warning("admin_operations_request_unavailable")
                response = JSONResponse(status_code=503, content={"detail": "Operations data unavailable"})
            response.headers.update(PRIVATE_HEADERS)
            return response

        return private_handler


def private_operations_response(response: Response):
    response.headers.update(PRIVATE_HEADERS)


def bounded_integer(value, minimum, maximum):
    """Route callables must not bypass SQL limits by skipping FastAPI validation."""
    if type(value) is not int or not minimum <= value <= maximum:
        raise HTTPException(status_code=422, detail="Invalid operations parameters", headers=PRIVATE_HEADERS)


def bounded_domain(value):
    if value is not None and (not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", value)):
        raise HTTPException(status_code=422, detail="Invalid operations parameters", headers=PRIVATE_HEADERS)


def error_count_expression(db):
    """Count diagnostics in SQL without transferring their bodies."""
    if db.get_bind().dialect.name == "postgresql":
        kind = func.jsonb_typeof(IngestionJob.errors)
        length = func.jsonb_array_length(IngestionJob.errors)
    else:
        kind = func.json_type(IngestionJob.errors)
        length = func.json_array_length(IngestionJob.errors)
    return case(
        (kind == "array", length),
        (IngestionJob.errors.is_(None), 0),
        (kind == "null", 0),
        else_=1,
    ).label("error_count")


def safe_job_metadata(raw):
    """Only public operational flags, never arbitrary strings or nested payloads."""
    if not isinstance(raw, dict):
        return {}
    result = {}
    mode = raw.get("source_mode")
    if isinstance(mode, str) and mode in {"live", "fixture", "unknown", "unavailable", "stale", "refused"}:
        result["source_mode"] = mode
    for key in ("manual_trigger", "dropped_by_global_budget", "dry_run"):
        if type(raw.get(key)) is bool:
            result[key] = raw[key]
    since = raw.get("since")
    if isinstance(since, str) and len(since) <= 40:
        try:
            result["since"] = datetime.fromisoformat(since).isoformat()
        except ValueError:
            pass
    return result


def job_projection(job, *, error_count, metadata=None):
    duration = None
    if job.status.value != "pending" and job.finished_at and job.started_at:
        elapsed = (job.finished_at - job.started_at).total_seconds()
        duration = elapsed if elapsed >= 0 else None
    return dict(
        id=job.id, domain=job.domain, status=job.status.value, dry_run=job.dry_run,
        started_at=job.started_at, finished_at=job.finished_at, duration_seconds=duration,
        items_processed=job.items_processed, items_created=job.items_created,
        items_updated=job.items_updated, created_at=job.created_at,
        errors=[DIAGNOSTIC_NOTICE] if error_count else [], error_count=error_count,
        metadata=safe_job_metadata(metadata), diagnostics_redacted=True,
    )
