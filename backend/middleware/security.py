"""Security middleware for rate limiting, CORS, and audit logging."""

import logging
import os
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional

import redis.asyncio as aioredis
from config.settings import settings
from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Per-request audit entries default to DEBUG so production logs aren't
# flooded with one INFO line per GET (thousands/hour at modest traffic).
# Set AUDIT_LOG_LEVEL=INFO to surface them, e.g. while investigating abuse.
_AUDIT_LOG_LEVEL = (
    logging.INFO if os.getenv("AUDIT_LOG_LEVEL", "DEBUG").upper() == "INFO" else logging.DEBUG
)


def _memory_allows(clients, client_ip, calls, period, capacity):
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
    timestamps.append(now)
    clients[client_ip] = timestamps
    clients.move_to_end(client_ip)
    return True


class RedisRateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-backed rate limiting middleware for production use.

    Falls back to in-memory if Redis is unavailable.
    """

    def __init__(self, app, calls: int = 100, period: int = 60):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.redis_client: Optional[aioredis.Redis] = None
        self.memory_fallback: Dict[str, list] = OrderedDict()
        self.use_redis = False

    async def init_redis(self):
        """Initialize Redis connection."""
        if self.redis_client is None:
            try:
                self.redis_client = await aioredis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=5,
                )
                # Test connection
                await self.redis_client.ping()
                self.use_redis = True
                logger.info("Redis rate limiter initialized")
            except Exception as e:
                logger.info("Redis not configured — using in-memory rate limiting")
                self.use_redis = False

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip OPTIONS (CORS preflight) — let CORSMiddleware handle it
        if request.method == "OPTIONS":
            return await call_next(request)

        # Initialize Redis on first request
        if self.redis_client is None and settings.REDIS_URL:
            await self.init_redis()

        # Get client IP
        client_ip = request.client.host if request.client else "unknown"

        # Skip rate limiting for loopback (local dev traffic from same machine — SSR
        # prefetch, HMR reloads, React Query hydration, and Strict-Mode double-invocation
        # legitimately generate bursts that would trip a public-facing rate limit).
        if client_ip in ("127.0.0.1", "::1", "localhost", "unknown"):
            return await call_next(request)

        # Skip rate limiting for health checks
        if request.url.path in ["/", "/health", "/metrics"]:
            return await call_next(request)

        # Use Redis or memory fallback
        if self.use_redis and self.redis_client:
            allowed = await self._check_redis_rate_limit(client_ip)
        else:
            allowed = await self._check_memory_rate_limit(client_ip)

        if not allowed:
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            # NB: return, don't raise. BaseHTTPMiddleware.dispatch runs outside
            # Starlette's ExceptionMiddleware, so a raised HTTPException never
            # becomes a response — the caller would get a bare 500 with no
            # Retry-After instead of the 429 this branch intends.
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": f"Rate limit exceeded. Max {self.calls} requests per {self.period} seconds."
                },
                headers={"Retry-After": str(self.period)},
            )

        return await call_next(request)

    async def _check_redis_rate_limit(self, client_ip: str) -> bool:
        """Check rate limit using Redis."""
        try:
            key = f"rate_limit:{client_ip}"
            pipe = self.redis_client.pipeline()

            # Increment counter
            pipe.incr(key)
            # Set expiry
            pipe.expire(key, self.period)

            result = await pipe.execute()
            count = result[0]

            return count <= self.calls
        except Exception as e:
            logger.error(f"Redis rate limit check failed: {e}")
            # Fall back to memory
            self.use_redis = False
            return await self._check_memory_rate_limit(client_ip)

    _MAX_MEMORY_CLIENTS = 10_000

    async def _check_memory_rate_limit(self, client_ip: str) -> bool:
        """Check rate limit using in-memory storage (fallback)."""
        return _memory_allows(self.memory_fallback, client_ip, self.calls,
                              self.period, self._MAX_MEMORY_CLIENTS)

    async def shutdown(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()


# Keep old middleware for backward compatibility
class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiting middleware.

    For production, use RedisRateLimitMiddleware instead.
    """

    _MAX_MEMORY_CLIENTS = 10_000

    def __init__(self, app, calls: int = 100, period: int = 60):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.clients: Dict[str, list] = OrderedDict()

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip OPTIONS (CORS preflight) — let CORSMiddleware handle it
        if request.method == "OPTIONS":
            return await call_next(request)

        # Get client IP
        client_ip = request.client.host if request.client else "unknown"

        # Skip rate limiting for loopback (local dev traffic from same machine)
        if client_ip in ("127.0.0.1", "::1", "localhost", "unknown"):
            return await call_next(request)

        # Skip rate limiting for health checks
        if request.url.path in ["/", "/health", "/metrics"]:
            return await call_next(request)

        if not _memory_allows(self.clients, client_ip, self.calls,
                              self.period, self._MAX_MEMORY_CLIENTS):
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            # NB: return, don't raise. BaseHTTPMiddleware.dispatch runs outside
            # Starlette's ExceptionMiddleware, so a raised HTTPException never
            # becomes a response — the caller would get a bare 500 with no
            # Retry-After instead of the 429 this branch intends.
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": f"Rate limit exceeded. Max {self.calls} requests per {self.period} seconds."
                },
                headers={"Retry-After": str(self.period)},
            )

        return await call_next(request)


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
