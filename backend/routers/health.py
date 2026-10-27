"""Detailed health endpoint for monitoring.

Scope note. This module used to define ``/health``, ``/health/live`` and
``/health/ready`` as well. ``main.py`` already serves all three, and routers are
included at main.py:1734 — ahead of those ``@app.api_route`` declarations at
2036 — so registering this file would have SHADOWED them. Measured: readiness
went from ``503 {"status": "starting"}`` to ``200 {"status": "ready"}``, i.e.
Render would have routed traffic to an instance whose reference-data bootstrap
had not finished. This file's ``/health/ready`` also returned a ``(dict, int)``
tuple, which FastAPI serialises as a 200 JSON array, never a 503.

So the duplicates are gone and ``main.py`` keeps the probes. This router
contributes the one thing main.py does not have: a component-level report,
including the cache diagnostics added for issue #184.
``tests/test_health_detailed_reports_cache.py`` fails if the duplicates return.
"""

from datetime import datetime, timezone
import logging

from cache.redis_cache import cache
from config.settings import settings
from database import request_engine as engine, get_db
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

router = APIRouter()


def _pool_status() -> dict:
    """Connection-pool counters, best effort.

    Not every pool implementation exposes these (NullPool does not), so each is
    read defensively — a health endpoint that raises is worse than one that
    reports a field as unknown.
    """
    pool = engine.pool
    status_out = {}
    for name in ("size", "checkedout", "checkedin", "overflow"):
        probe = getattr(pool, name, None)
        try:
            status_out[name] = probe() if callable(probe) else None
        except Exception:  # noqa: BLE001 - never let a counter break the probe
            status_out[name] = None
    return status_out


@router.get("/health/detailed", status_code=status.HTTP_200_OK)
async def detailed_health_check(request: Request = None, db: Session = Depends(get_db)):
    """Component-level health: database, cache, ETL."""

    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "components": {},
    }

    # Check database
    try:
        # text() is required: SQLAlchemy 2.0 raises ArgumentError on a bare
        # string, so the previous `db.execute("SELECT 1")` reported a healthy
        # database as unhealthy on every single call.
        db.execute(text("SELECT 1"))
        health_status["components"]["database"] = {
            "status": "healthy",
            **_pool_status(),
        }
    except Exception as exc:
        logging.error("Database health check failed (%s)", type(exc).__name__)
        health_status["status"] = "degraded"
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "error": "Database connectivity check failed",
        }

    # Check cache. Beyond connectivity this reports `unserialisable_values`
    # (values that can NEVER be cached — a permanent condition a Redis-outage
    # log line cannot express) and the build scope keys are written under, so
    # a silent fallback to the shared 'dev' namespace is visible. See #184.
    redis_health = cache.health_check()
    health_status["components"]["cache"] = redis_health
    #  "using_memory_cache" means opposite things depending on whether Redis
    #  was ever configured: the normal development mode, or an outage in which
    #  every endpoint is silently running uncached. Only the latter is degraded
    #  — calling both degraded is noise an operator learns to ignore, and
    #  calling both healthy hides a production incident.
    cache_ok = redis_health.get("status") == "healthy" or (
        redis_health.get("status") == "using_memory_cache"
        and not redis_health.get("redis_configured")
    )
    if not cache_ok:
        health_status["status"] = "degraded"

    health_status["components"]["etl"] = {
        "status": "not_implemented",
    }

    limits = getattr(request.app.state, 'security_limits', None) if request is not None else None
    if limits is not None:
        health_status['components']['request_security'] = dict(limits)
        if limits.get('rate_limit_mode') in {'degraded_memory', 'redis_pending'}:
            health_status['status'] = 'degraded'

    return health_status
