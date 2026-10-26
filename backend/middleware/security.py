"""Security middleware for rate limiting, CORS, and audit logging."""

import asyncio
import logging
import os
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Callable

import redis.asyncio as aioredis
from config.settings import settings
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .request_resources import RequestResourceMiddleware, cheap_health

logger = logging.getLogger(__name__)

# Per-request audit entries default to DEBUG so production logs aren't
# flooded with one INFO line per GET (thousands/hour at modest traffic).
# Set AUDIT_LOG_LEVEL=INFO to surface them, e.g. while investigating abuse.
_AUDIT_LOG_LEVEL = (
    logging.INFO if os.getenv("AUDIT_LOG_LEVEL", "DEBUG").upper() == "INFO" else logging.DEBUG
)


def _memory_allows(clients, client_ip, calls, period, capacity, *, record=True):
    """Bound accepted timestamps and client identities without evicting live budgets."""
    now = time.monotonic()
    cutoff = now - period
    # Entries are ordered by their last accepted request. Expired clients
    # leave once, so a saturated map does not require a full scan per request.
    while clients:
        oldest = next(iter(clients))
        if clients[oldest][-1] > cutoff:
            break
        clients.popitem(last=False)
    timestamps = clients.get(client_ip)
    if timestamps is None:
        if len(clients) >= capacity:
            return False
        timestamps = []
    timestamps = [stamp for stamp in timestamps if stamp > cutoff]
    if len(timestamps) >= calls:
        return False
    if record:
        timestamps.append(now)
        clients[client_ip] = timestamps
        clients.move_to_end(client_ip)
    return True


class _ProcessRateLimitMiddleware(BaseHTTPMiddleware):
    """Bound per-peer and aggregate process budgets; no IP/header exemptions."""
    _MAX_MEMORY_CLIENTS = 10_000

    def __init__(self, app, calls: int = 100, period: int = 60, status=None, aggregate_calls=None):
        super().__init__(app)
        if type(calls) is not int or type(period) is not int or calls < 1 or period < 1:
            raise ValueError("Positive rate budgets required")
        self.calls, self.period = calls, period
        self.aggregate_calls = calls * 10 if aggregate_calls is None else aggregate_calls
        if type(self.aggregate_calls) is not int or self.aggregate_calls < 1:
            raise ValueError('Positive aggregate rate budget required')
        self.clients = OrderedDict()
        self.aggregate = OrderedDict()
        self.status = status if status is not None else {}
        self.status.update(rate_limit_mode='memory', calls=calls, period=period,
                           aggregate_calls=self.aggregate_calls, process_scope='one_worker',
                           identity_scope='coarse_socket_peer')
        self._last_warning = None

    async def _check_memory_rate_limit(self, client_ip):
        return _memory_allows(self.clients, client_ip, self.calls,
                              self.period, self._MAX_MEMORY_CLIENTS)

    async def _remote_allows(self, client_ip):
        return True  # This class deliberately has no remote storage contract.

    async def dispatch(self, request: Request, call_next: Callable):
        if cheap_health(request.scope):
            return await call_next(request)
        # Uvicorn's separately configured trusted-proxy boundary owns scope
        # identity. Never accept client-supplied forwarding headers here.
        client_ip = request.client.host if request.client else 'unknown'
        # Check shared room before allocating peer state, then debit only
        # admitted peers. One peer's refusals cannot consume everybody else's
        # quota; a full process window cannot grow the peer map either.
        room = _memory_allows(self.aggregate, 'all', self.aggregate_calls,
                              self.period, 1, record=False)
        local = room and await self._check_memory_rate_limit(client_ip)
        aggregate = local and _memory_allows(self.aggregate, 'all',
                                            self.aggregate_calls, self.period, 1)
        if aggregate and await self._remote_allows(client_ip):
            return await call_next(request)
        now = time.monotonic()
        if self._last_warning is None or now - self._last_warning >= self.period:
            logger.warning('Request admission rate budget exceeded')
            self._last_warning = now
        return JSONResponse(status_code=429,
            content={'detail': f'Rate limit exceeded. Max {self.calls} requests per {self.period} seconds.'},
            headers={'Retry-After': str(self.period), 'Cache-Control':'no-store'})


class RateLimitMiddleware(_ProcessRateLimitMiddleware):
    """Legacy memory-only guard; wrapping it does not replace the Redis guard."""


class RedisRateLimitMiddleware(_ProcessRateLimitMiddleware):
    """Optional existing Redis IP counter with bounded, visible local degradation.

    Local budgets always run first, so an outage/recovery cannot grant a fresh
    local budget. This is not a distributed aggregate/concurrency guarantee.
    The admitted serving topology remains one instance and one worker.
    """
    def __init__(self, app, calls: int = 100, period: int = 60, status=None, aggregate_calls=None):
        super().__init__(app, calls=calls, period=period, status=status, aggregate_calls=aggregate_calls)
        self.redis_client = None
        self.memory_fallback = self.clients
        self.use_redis = False
        self.redis_timeout = .2
        self._initializing = asyncio.Lock()
        self._attempted = False
        self.status['rate_limit_mode'] = 'redis_pending'

    def _degrade(self):
        self.use_redis = False
        self.status['rate_limit_mode'] = 'degraded_memory'
        logger.warning('Redis limiter unavailable; bounded single-process admission remains active')

    async def init_redis(self):
        async with self._initializing:
            if self._attempted:
                return
            self._attempted = True
            try:
                async with asyncio.timeout(self.redis_timeout):
                    self.redis_client = aioredis.from_url(settings.REDIS_URL,
                        encoding='utf-8', decode_responses=True, socket_connect_timeout=.2,
                        socket_timeout=.2, max_connections=8, retry_on_timeout=False)
                    await self.redis_client.ping()
                self.use_redis = True
                self.status['rate_limit_mode'] = 'redis'
            except Exception:
                self._degrade()
                await self.shutdown()

    async def _remote_allows(self, client_ip):
        if self.redis_client is None and settings.REDIS_URL:
            await self.init_redis()
        if self.use_redis:
            try:
                return await self._check_redis_rate_limit(client_ip)
            except Exception:
                self._degrade()
        # dispatch already debited both bounded local budgets exactly once.
        return True

    async def _check_redis_rate_limit(self, client_ip):
        async with asyncio.timeout(self.redis_timeout):
            pipe = self.redis_client.pipeline()
            key = f'rate_limit:{client_ip}'
            pipe.incr(key)
            pipe.expire(key, self.period)
            result = await pipe.execute()
        if type(result) is not list or not result or type(result[0]) is not int or result[0] < 1:
            raise ValueError('Invalid limiter storage counter')
        return result[0] <= self.calls

    async def shutdown(self):
        if self.redis_client is not None and hasattr(self.redis_client, 'aclose'):
            try:
                async with asyncio.timeout(self.redis_timeout):
                    await self.redis_client.aclose()
            except Exception:
                logger.warning('Redis limiter connection cleanup incomplete')


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Log all API requests for audit trail."""

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip OPTIONS (CORS preflight) — not useful to audit
        if request.method == "OPTIONS":
            return await call_next(request)

        start_time = time.time()

        # Get client info
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")

        # Get user from auth token if available
        user_id = "anonymous"
        auth_header = request.headers.get("authorization", "")
        if auth_header:
            # Extract user from token (simplified - actual implementation in auth.py)
            try:
                # This would decode JWT and extract user
                user_id = "authenticated"  # Placeholder
            except Exception:
                pass

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration = time.time() - start_time

        # Log audit entry
        if __package__ == 'backend.middleware':
            from ..social.http_policy import private_social_path, social_log_path
        else:
            from social.http_policy import private_social_path, social_log_path

        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "client_ip": client_ip,
            "method": request.method,
            "path": social_log_path(request.url.path),
            "query_params": (
                "[redacted]" if private_social_path(request.url.path)
                else str(request.query_params)
            ),
            "status_code": response.status_code,
            "duration_ms": round(duration * 1000, 2),
            "user_agent": user_agent,
        }

        logger.log(_AUDIT_LOG_LEVEL, f"AUDIT: {audit_entry}")

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        # CSP: allow API responses to be consumed cross-origin (frontend on different port)
        response.headers["Content-Security-Policy"] = "default-src 'self'; connect-src *"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )

        return response


def install_security(app):
    """Required serving protections: construction/import errors stop startup."""
    if os.getenv('WEB_CONCURRENCY', '1') != '1':
        raise RuntimeError('Single-worker request admission requires WEB_CONCURRENCY=1')
    state = {}
    app.state.security_limits = state
    # The environment backend must explicitly configure Redis; its localhost
    # settings default is not evidence that a remote limiter was provisioned.
    configured_redis = bool(settings.REDIS_URL) and (
        settings.SECRET_BACKEND != 'env' or bool(os.getenv('REDIS_URL')))
    selected = RedisRateLimitMiddleware if configured_redis else RateLimitMiddleware
    # Socket peers may be shared Render proxies. Keep a coarse peer ceiling
    # with separate process headroom; both can bind before the 1000-request
    # worker recycle. This is not an end-user or cross-restart quota.
    app.add_middleware(selected, calls=600, aggregate_calls=900, period=60, status=state)
    app.add_middleware(AuditLogMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestResourceMiddleware, status=state)
    logger.info('Required request/security middleware registered; one-process admission active')
