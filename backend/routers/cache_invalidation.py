"""POST /api/v1/system/cache/invalidate: the nightly's call to clear API caches.

The seed workflow calls this after seed AND validate succeed, and BEFORE it
revalidates the frontend pages. The order matters: a page regenerated while
this cache is still warm is rebuilt from the pre-seed response (issue #231).

Auth is the same scheme as ``frontend/app/api/revalidate/route.ts``:
HMAC-SHA256 of the raw body with ``REVALIDATE_SECRET``, hex, in
``x-revalidate-signature``. The body also has to carry ``ts`` (unix seconds)
within ``MAX_SKEW_SECONDS`` of now, so a captured request cannot be replayed
to keep emptying the cache. An unset secret disables the endpoint with a 503
instead of leaving it open.

Every failure answers non-2xx with a stable ``error`` slug, and the workflow
fails the job on anything but 200.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import logging
import math
import os
import time

from fastapi import APIRouter, HTTPException, Request, Response

from cache.invalidation import InvalidationError, generation_status, invalidate_all

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/system", tags=["system"])

MAX_SKEW_SECONDS = 300


def _refuse(status: int, error: str, **extra) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": error, **extra})


async def _signed_body(request: Request) -> dict:
    secret = os.getenv("REVALIDATE_SECRET") or ""
    if not secret:
        raise _refuse(503, "invalidation_not_configured")

    raw = await request.body()
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    given = request.headers.get("x-revalidate-signature", "")
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise _refuse(401, "invalid_signature")

    try:
        body = json.loads(raw or b"{}")
        if not isinstance(body, dict):
            raise TypeError("body must be an object")
        ts = body["ts"]
        if isinstance(ts, bool) or not isinstance(ts, (int, float)):
            raise TypeError("ts must be a number")
        ts = float(ts)
        if not math.isfinite(ts):
            raise ValueError("ts must be finite")
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise _refuse(400, "malformed_body", detail=str(exc))
    skew = abs(time.time() - ts)
    if skew > MAX_SKEW_SECONDS:
        raise _refuse(401, "stale_request", skew_seconds=int(skew))
    return body


@router.post("/cache/status")
async def cache_status(request: Request, response: Response):
    """Signed per-worker observation for the release acceptance experiment."""
    await _signed_body(request)
    response.headers["Cache-Control"] = "no-store"
    try:
        return generation_status()
    except InvalidationError as exc:
        raise _refuse(500, exc.reason)


@router.post("/cache/invalidate")
async def invalidate_caches(request: Request):
    body = await _signed_body(request)

    try:
        result = invalidate_all()
    except InvalidationError as exc:
        logger.error("cache invalidation FAILED (%s): %s", exc.reason, exc.detail)
        raise _refuse(500, exc.reason, detail=exc.detail)

    logger.info(
        "cache invalidated (reason=%r): %s",
        body.get("reason"),
        result,
    )
    return {
        "invalidated": True,
        "reason": body.get("reason"),
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        **result,
    }
