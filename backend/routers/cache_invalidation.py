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
import asyncio
import hashlib
import hmac
import json
import logging
import math
import os
import re
import time

from fastapi import APIRouter, HTTPException, Request, Response

from cache.invalidation import InvalidationError, generation_status, invalidate_all, serving_census

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/system", tags=["system"])

MAX_SKEW_SECONDS = 300


def _refuse(status: int, error: str, **extra) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": error, **extra})


async def _signed_body(request: Request) -> dict:
    secret = os.getenv("REVALIDATE_SECRET") or ""
    if not secret:
        raise _refuse(503, "invalidation_not_configured")

    given = request.headers.get("x-revalidate-signature", "")
    if re.fullmatch('[0-9a-f]{64}', given) is None:
        raise _refuse(401, "invalid_signature")
    async def read_bounded():
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 8192:
                raise _refuse(413, "body_too_large")
            chunks.append(chunk)
        return b''.join(chunks)
    try:
        raw = await asyncio.wait_for(read_bounded(), timeout=5)
    except asyncio.TimeoutError:
        raise _refuse(408, "body_timeout") from None
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
    return body, raw


def _refresh_context(body):
    """Legacy callers keep their API; nightly v2 cannot downgrade its proof."""
    if not any(key in body for key in ('protocol', 'context', 'nonce')):
        return None
    context = body.get('context')
    if (set(body) != {'protocol', 'ts', 'nonce', 'context'}
            or body.get('protocol') != 'nightly-refresh-v2'
            or type(body.get('nonce')) is not str or re.fullmatch('[0-9a-f]{32}', body['nonce']) is None
            or type(context) is not dict
            or set(context) != {'source_sha', 'plan_sha256', 'run_id', 'run_attempt', 'schema_head'}
            or any(type(context[k]) is not str or re.fullmatch(pattern, context[k]) is None for k, pattern in {
                'source_sha': '[0-9a-f]{40}', 'plan_sha256': '[0-9a-f]{64}',
                'run_id': '[1-9][0-9]{0,17}', 'run_attempt': '[1-9][0-9]{0,4}'}.items())
            or context['schema_head'] != 'a756b20a0001'):
        raise _refuse(400, 'refresh_context_refused')
    if context['source_sha'] != os.getenv('RENDER_GIT_COMMIT'):
        raise _refuse(409, 'serving_source_mismatch')
    return context


def _refresh_reply(request_bytes, context, result):
    raw = json.dumps({'protocol': 'nightly-refresh-v2', 'context': context,
        'request_sha256': hashlib.sha256(request_bytes).hexdigest(),
        'at': int(time.time()), 'result': result}, separators=(',', ':'), allow_nan=False).encode()
    signature = hmac.new(os.environ['REVALIDATE_SECRET'].encode(), raw, hashlib.sha256).hexdigest()
    return Response(raw, media_type='application/json', headers={
        'Cache-Control': 'no-store', 'x-revalidate-response-signature': signature})


@router.post("/cache/status")
async def cache_status(request: Request, response: Response):
    """Signed per-worker observation for the release acceptance experiment."""
    body, request_bytes = await _signed_body(request)
    context = _refresh_context(body)
    response.headers["Cache-Control"] = "no-store"
    try:
        result = generation_status()
        if context is not None:
            result["census"] = serving_census()
            return _refresh_reply(request_bytes, context, result)
        return result
    except InvalidationError as exc:
        raise _refuse(500, exc.reason)


@router.post("/cache/invalidate")
async def invalidate_caches(request: Request):
    body, request_bytes = await _signed_body(request)
    context = _refresh_context(body)

    try:
        census = serving_census() if context is not None else None
        result = invalidate_all()
    except InvalidationError as exc:
        logger.error("cache invalidation FAILED (%s): %s", exc.reason, exc.detail)
        raise _refuse(500, exc.reason, detail=exc.detail)

    logger.info(
        "cache invalidated (reason=%r): %s",
        body.get("reason"),
        result,
    )
    result = {
        "invalidated": True,
        "reason": body.get("reason"),
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        **result,
    }

    if context is not None:
        if serving_census() != census:
            raise _refuse(409, 'serving_census_changed')
        result.update(census=census, commit=os.getenv('RENDER_GIT_COMMIT'))
        return _refresh_reply(request_bytes, context, result)
    return result
