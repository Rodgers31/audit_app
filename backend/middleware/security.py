"""Security middleware for rate limiting, CORS, and audit logging."""

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional

import redis.asyncio as aioredis
from config.settings import settings
from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RedisRateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-backed rate limiting middleware for production use.

    Falls back to in-memory if Redis is unavailable.
    """

    def __init__(self, app, calls: int = 100, period: int = 60):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.redis_client: Optional[aioredis.Redis] = None
        self.memory_fallback: Dict[str, list] = defaultdict(list)
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
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Max {self.calls} requests per {self.period} seconds.",
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

    async def _check_memory_rate_limit(self, client_ip: str) -> bool:
        """Check rate limit using in-memory storage (fallback)."""
        now = time.time()

        # Clean old entries
        self.memory_fallback[client_ip] = [
            timestamp
            for timestamp in self.memory_fallback[client_ip]
            if now - timestamp < self.period
        ]

        # Check limit
        if len(self.memory_fallback[client_ip]) >= self.calls:
            return False

        # Add current request
        self.memory_fallback[client_ip].append(now)
        return True

    async def shutdown(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()


# Keep old middleware for backward compatibility
class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiting middleware.

    For production, use RedisRateLimitMiddleware instead.
    """

    def __init__(self, app, calls: int = 100, period: int = 60):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.clients: Dict[str, list] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip OPTIONS (CORS preflight) — let CORSMiddleware handle it
        if request.method == "OPTIONS":
            return await call_next(request)

        # Get client IP
        client_ip = request.client.host if request.client else "unknown"

        # Skip rate limiting for health checks
        if request.url.path in ["/", "/health", "/metrics"]:
            return await call_next(request)

        # Clean old entries
        now = time.time()
        self.clients[client_ip] = [
            timestamp
            for timestamp in self.clients[client_ip]
            if now - timestamp < self.period
        ]

        # Check rate limit
        if len(self.clients[client_ip]) >= self.calls:
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Max {self.calls} requests per {self.period} seconds.",
                headers={"Retry-After": str(self.period)},
            )

        # Add current request
        self.clients[client_ip].append(now)

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
        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "client_ip": client_ip,
            "method": request.method,
            "path": request.url.path,
            "query_params": str(request.query_params),
            "status_code": response.status_code,
            "duration_ms": round(duration * 1000, 2),
            "user_agent": user_agent,
        }

        logger.info(f"AUDIT: {audit_entry}")

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
