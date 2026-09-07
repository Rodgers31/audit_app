"""Redis caching utilities for API responses."""

import json
import logging
import os
import time
import weakref
from functools import wraps
from typing import Any, Callable, Optional

import redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def _json_default(obj: Any) -> Any:
    """Encode the one type endpoint handlers legitimately hand the cache.

    A FastAPI handler that declares ``response_model`` returns the MODEL — the
    framework validates and serialises it on the way out. ``json.dumps`` does
    not know how to encode one, so before issue #184 the write raised
    ``TypeError``, was swallowed, and the endpoint ran uncached forever.

    ``mode="json"`` resolves nested models, datetimes, Decimals and enums to
    JSON-native types, so what lands in Redis is what FastAPI would have sent
    for that same model.

    Deliberately narrow. Anything that is NOT a model still raises, and the
    caller counts and reports it — a cache that quietly re-encodes whatever it
    is given cannot tell you when a value is wrong.
    """
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _sanitise_namespace(value: str) -> str:
    """Keys are colon-separated, so a namespace may not contain one."""
    return "".join(c for c in value.strip() if c.isalnum() or c in "-_.")


def _resolve_cache_namespace() -> tuple:
    """Which build's cache entries this process may read, and where that came from.

    Redis outlives a deploy. Since #184 made the model-returning endpoints
    genuinely cacheable, a cached value is a dict that FastAPI re-validates
    against ``response_model`` on the way out — so an entry written before a
    model changed can be read by the build that changed it. Observed on this
    branch by planting one under the live key of ``/economic/population/latest``:
    a missing required field or a wrong type answers **500**, and a missing
    OPTIONAL field answers **200 with a field the previous build never set**.
    That last one does not fail; it publishes a false provenance claim until
    the TTL expires.

    Scoping the key to the build makes it impossible rather than unlikely.

    Deliberately NOT derived from ``settings.APP_VERSION``: that is the string
    "1.0.0" and nothing bumps it, so it would look like versioning while
    providing none — a guard that cannot fire is worse than no guard, because
    it stops anyone looking.
    """
    explicit = os.getenv("CACHE_VERSION")
    if explicit and _sanitise_namespace(explicit):
        return _sanitise_namespace(explicit), "CACHE_VERSION"

    # Render sets this on every deploy, so the scope advances without anyone
    # remembering to bump anything.
    commit = os.getenv("RENDER_GIT_COMMIT")
    if commit and _sanitise_namespace(commit):
        return _sanitise_namespace(commit)[:12], "RENDER_GIT_COMMIT"

    return "dev", "fallback (neither CACHE_VERSION nor RENDER_GIT_COMMIT is set)"


#: Resolved once per process. Reported by health_check() and logged at import,
#: because a namespace that quietly falls back to a constant is inert while
#: looking exactly like a working one.
CACHE_NAMESPACE, CACHE_NAMESPACE_SOURCE = _resolve_cache_namespace()
logger.info(
    "Cache keys scoped to namespace %r (source: %s)",
    CACHE_NAMESPACE,
    CACHE_NAMESPACE_SOURCE,
)


class RedisCache:
    """Redis cache manager with fallback to in-memory cache."""

    #: Every instance ever built, so test teardown can clear all of them.
    #: There are three module-level singletons (cache.redis_cache.cache,
    #: main.redis_cache, routers.money_flow._redis_cache) and
    #: main.clear_all_caches() used to know about only the first two — the
    #: money-flow one kept 30-minute entries alive across tests, so a test's
    #: result depended on whether an earlier test had warmed that endpoint.
    #: Registering here means a new instance can never be forgotten again.
    #: Weak refs so the registry can never itself become a leak.
    _instances: "weakref.WeakSet[RedisCache]" = weakref.WeakSet()

    #: How many values were dropped because they can NEVER be serialised.
    #: Class-level defaults so an instance built without __init__ still reports.
    #: This is a PERMANENT condition, unlike a Redis outage, and health_check()
    #: surfaces it separately for exactly that reason — see set().
    _unserialisable_values: int = 0
    _last_unserialisable: Optional[str] = None

    #: Build scope for every key this instance reads or writes. Class-level
    #: defaults so an instance built without __init__ still scopes its keys.
    namespace: str = CACHE_NAMESPACE
    namespace_source: str = CACHE_NAMESPACE_SOURCE

    #: Whether REDIS_URL was actually set. Without it, `redis_url` falls back
    #: to redis://localhost:6379 and "using the in-memory cache" is
    #: indistinguishable between "no Redis in development" (normal) and "Redis
    #: was configured but unreachable at startup" (an incident: every endpoint
    #: is running uncached). health_check() reports it so the caller can tell.
    redis_url_configured: bool = False

    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.client: Optional[redis.Redis] = None
        self._memory_cache = {}  # {key: (value, expiry_timestamp)}
        self._memory_cache_max_size = 1024
        self._unserialisable_values = 0
        self._last_unserialisable = None
        self.namespace = CACHE_NAMESPACE
        self.namespace_source = CACHE_NAMESPACE_SOURCE
        self.redis_url_configured = bool(redis_url or os.getenv("REDIS_URL"))
        RedisCache._instances.add(self)
        self._initialize()

    def _initialize(self):
        """Initialize Redis connection with error handling."""
        try:
            self.client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # Test connection
            self.client.ping()
            logger.info("Redis cache connected")
        except Exception as e:
            logger.info(
                "Redis not configured — using in-memory cache (this is normal without a Redis add-on)"
            )
            self.client = None

    def _scoped(self, key: str) -> str:
        """Prefix ``key`` with the build scope.

        Applied inside RedisCache rather than in the decorators because this
        codebase has three separate ``cached`` implementations
        (cache.redis_cache, main, routers.money_flow) that all funnel here.
        Scoping at the choke point means none of them has to remember.
        """
        return f"{self.namespace}:{key}"

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        try:
            if self.client:
                value = self.client.get(self._scoped(key))
                if value:
                    return json.loads(value)
            else:
                # Fallback to memory cache
                entry = self._memory_cache.get(self._scoped(key))
                if entry is not None:
                    value, expiry = entry
                    if time.time() < expiry:
                        return value
                    else:
                        del self._memory_cache[self._scoped(key)]  # Expired
        except Exception as e:
            logger.error(f"Cache get error: {e}")
        return None

    def set(self, key: str, value: Any, ttl: int = 3600):
        """Set value in cache with TTL.

        Serialisation and transport are attempted separately because they fail
        for opposite reasons and need opposite responses:

        * **Serialisation** failure is PERMANENT. The value can never be
          cached, so the endpoint re-runs its query on every request until the
          code changes. It is counted, not just logged.
        * **Transport** failure is TRANSIENT. Redis is unreachable now and the
          next write may well succeed.

        One ``except Exception`` used to cover both and log them identically as
        ``Cache set error``, so four model-returning endpoints ran uncached in
        production and the only symptom read like a Redis blip (issue #184).
        """
        try:
            payload = json.dumps(value, default=_json_default)
        except (TypeError, ValueError) as exc:
            self._unserialisable_values += 1
            self._last_unserialisable = f"{key}: {type(exc).__name__}: {exc}"
            logger.error(
                "Cache set SKIPPED — the value for %r can never be serialised "
                "(%s: %s). This is not a Redis outage and will not heal on its "
                "own: this key re-runs its query on every request until the "
                "value is made JSON-serialisable. Total such values: %d",
                key,
                type(exc).__name__,
                exc,
                self._unserialisable_values,
            )
            return

        try:
            if self.client:
                self.client.setex(self._scoped(key), ttl, payload)
            else:
                # Fallback to memory cache with TTL
                if len(self._memory_cache) >= self._memory_cache_max_size:
                    # Evict expired entries first
                    now = time.time()
                    expired_keys = [k for k, (_, exp) in self._memory_cache.items() if now >= exp]
                    for k in expired_keys:
                        del self._memory_cache[k]
                    # If still full, evict oldest entry
                    if len(self._memory_cache) >= self._memory_cache_max_size:
                        oldest_key = next(iter(self._memory_cache))
                        del self._memory_cache[oldest_key]
                # Store what Redis WOULD have stored, not the live object.
                # Development and CI have no Redis, so this branch is the only
                # one they ever take; keeping it un-normalised is precisely why
                # #184 was invisible everywhere except production. A cache hit
                # now yields the same shape here as it does on Render.
                self._memory_cache[self._scoped(key)] = (json.loads(payload), time.time() + ttl)
        except Exception as e:
            logger.error(f"Cache set error (transport) for {key!r}: {e}")

    def delete(self, key: str):
        """Delete key from cache."""
        try:
            if self.client:
                self.client.delete(self._scoped(key))
            else:
                self._memory_cache.pop(self._scoped(key), None)
        except Exception as e:
            logger.error(f"Cache delete error: {e}")

    def clear_pattern(self, pattern: str):
        """Clear all keys matching pattern."""
        # Only this build's keys. A previous build's entries are unreachable
        # anyway and expire on their own TTL.
        scoped_pattern = self._scoped(pattern)
        try:
            if self.client:
                keys = self.client.keys(scoped_pattern)
                if keys:
                    self.client.delete(*keys)
            else:
                # Memory cache - clear matching keys
                keys_to_delete = [
                    k for k in self._memory_cache if scoped_pattern.replace("*", "") in k
                ]
                for key in keys_to_delete:
                    self._memory_cache.pop(key, None)
        except Exception as e:
            logger.error(f"Cache clear error: {e}")

    def health_check(self) -> dict:
        """Check Redis health status.

        ``unserialisable_values`` is reported on EVERY path, including the
        healthy one. A connected, responsive Redis that is being handed values
        it can never store is exactly the production state issue #184 sat in
        for months, and a health report that only describes the connection
        cannot distinguish it from a cache that is working.
        """
        diagnostics = {
            "unserialisable_values": self._unserialisable_values,
            "cache_namespace": self.namespace,
            "cache_namespace_source": self.namespace_source,
            "redis_configured": self.redis_url_configured,
        }
        if self._last_unserialisable:
            diagnostics["last_unserialisable"] = self._last_unserialisable

        try:
            if self.client:
                self.client.ping()
                info = self.client.info()
                return {
                    "status": "healthy",
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory": info.get("used_memory_human", "unknown"),
                    "uptime_seconds": info.get("uptime_in_seconds", 0),
                    **diagnostics,
                }
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")

        return {
            "status": "unavailable" if self.client else "using_memory_cache",
            "message": "Using in-memory fallback cache",
            **diagnostics,
        }


# Global cache instance
cache = RedisCache()


_SKIP_CACHE_KEY_TYPES: tuple = ()  # populated at import time below

def _is_cacheable_param(value: Any) -> bool:
    """Return True if the value should be part of a cache key.

    SQLAlchemy Sessions, Requests, and other non-serialisable DI objects
    are excluded so the cache key stays stable across requests.
    """
    global _SKIP_CACHE_KEY_TYPES
    if not _SKIP_CACHE_KEY_TYPES:
        skip = []
        try:
            from sqlalchemy.orm import Session
            skip.append(Session)
        except ImportError:
            pass
        try:
            from starlette.requests import Request
            skip.append(Request)
        except ImportError:
            pass
        _SKIP_CACHE_KEY_TYPES = tuple(skip) if skip else (type(None),)
    return not isinstance(value, _SKIP_CACHE_KEY_TYPES)



# ── Transient-failure detection (issue #141) ────────────────────────
# How long a body describing an UNREADABLE source may be cached. Short
# enough that a recovered source is picked up promptly, long enough that a
# database in trouble is not hammered by every request.
TRANSIENT_FAILURE_TTL = 30

# Markers the API already emits to say "the source could not be READ".
#
# Deliberately narrow. A body saying the source was read and holds nothing
# (`database_empty`, `not_yet_seeded`) is a DURABLE answer and keeps the
# normal TTL — an empty table does not fill in the next thirty seconds, and
# re-querying it on every request would be load for no new information.
# Treating every degraded body as transient would trade a stale-cache bug
# for a thundering herd.
_TRANSIENT_MARKERS = {
    "data_source": {"database_unavailable"},
    "reason": {"source_unavailable", "database_not_configured"},
    "status": {"error", "unavailable"},
}


def is_transient_failure(result: object) -> bool:
    """True when ``result`` says the data source could not be read.

    The signal already exists in every degraded response the API builds, so
    this reads it rather than inventing a new convention for handlers to
    remember to set.
    """
    if not isinstance(result, dict):
        return False
    for field, bad_values in _TRANSIENT_MARKERS.items():
        value = result.get(field)
        if isinstance(value, str) and value in bad_values:
            return True
    return False


def cached(ttl: int = 3600, key_prefix: str = ""):
    """Decorator for caching function results.

    Args:
        ttl: Time to live in seconds
        key_prefix: Prefix for cache key
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments,
            # excluding non-serialisable DI objects (db sessions, requests)
            cache_key_parts = [key_prefix or func.__name__]

            for arg in args:
                if _is_cacheable_param(arg):
                    cache_key_parts.append(str(arg))

            for k, v in sorted(kwargs.items()):
                if _is_cacheable_param(v):
                    cache_key_parts.append(f"{k}={v}")

            cache_key = ":".join(cache_key_parts)

            # Try to get from cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached_value

            # Call function and cache result
            logger.debug(f"Cache miss: {cache_key}")
            result = await func(*args, **kwargs)

            if result is not None:
                # A body describing an unreadable source gets a short TTL, so
                # a recovered source is visible in seconds rather than hours.
                # Observed in production 2026-09-03: /debt/national served
                # `database_unavailable` from cache long after the database
                # recovered, because the failure had been stored with the
                # endpoint's full 12-hour TTL (issue #141).
                effective_ttl = (
                    min(ttl, TRANSIENT_FAILURE_TTL)
                    if is_transient_failure(result)
                    else ttl
                )
                if effective_ttl != ttl:
                    logger.info(
                        "Caching transient failure briefly (%ss instead of %ss): %s",
                        effective_ttl,
                        ttl,
                        cache_key,
                    )
                cache.set(cache_key, result, effective_ttl)

            return result

        return wrapper

    return decorator


def invalidate_cache(pattern: str):
    """Invalidate cache entries matching pattern."""
    cache.clear_pattern(pattern)
    logger.info(f"Invalidated cache pattern: {pattern}")
