"""Redis caching utilities for API responses."""

import asyncio
import hashlib
import inspect
import json
import logging
import os
import re
import threading
import time
import weakref
from collections import Counter
from functools import wraps
from typing import Any, Callable, Optional

import redis
from fastapi.encoders import jsonable_encoder
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


def _tracks_the_commit(value: str, commit: str) -> bool:
    """True when ``value`` visibly follows ``commit``, so the scope still
    advances per deploy.

    ``CACHE_VERSION=$RENDER_GIT_COMMIT`` in the start command is the
    recommended configuration when the commit is not otherwise on the
    process's environment, and warning about it would be a false positive on
    the one setup we tell people to use. A 7-character floor keeps a short
    namespace from matching hex by coincidence.
    """
    shorter, longer = sorted((value, commit), key=len)
    return len(shorter) >= 7 and shorter in longer


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
    explicit = _sanitise_namespace(os.getenv("CACHE_VERSION") or "")
    # Render sets this on every deploy, so the scope advances without anyone
    # remembering to bump anything.
    commit = _sanitise_namespace(os.getenv("RENDER_GIT_COMMIT") or "")

    if explicit:
        warning = None
        if commit and not _tracks_the_commit(explicit, commit):
            warning = (
                f"CACHE_VERSION={explicit!r} PINS the cache scope. It overrides "
                f"RENDER_GIT_COMMIT ({commit[:12]!r}), which advances on every "
                "deploy, with a value that does not. Entries written by one "
                "build will be read by the next — which is the whole thing this "
                "scope exists to prevent, and the health report will still read "
                "'source: CACHE_VERSION' as though it were configured correctly. "
                "Unset CACHE_VERSION, or set it to $RENDER_GIT_COMMIT."
            )
        return explicit, "CACHE_VERSION", warning

    if commit:
        return commit[:12], "RENDER_GIT_COMMIT", None

    return "dev", "fallback (neither CACHE_VERSION nor RENDER_GIT_COMMIT is set)", None


#: Resolved once per process. Reported by health_check() and logged at import,
#: because a namespace that quietly falls back to a constant is inert while
#: looking exactly like a working one.
CACHE_NAMESPACE, CACHE_NAMESPACE_SOURCE, CACHE_NAMESPACE_WARNING = (
    _resolve_cache_namespace()
)
logger.info(
    "Cache keys scoped to namespace %r (source: %s)",
    CACHE_NAMESPACE,
    CACHE_NAMESPACE_SOURCE,
)
if CACHE_NAMESPACE_WARNING:
    logger.warning("%s", CACHE_NAMESPACE_WARNING)


class RedisCache:
    """Redis cache manager with fallback to in-memory cache."""

    # Also cover test instances constructed with __new__.
    _memory_lock = threading.RLock()
    _metrics = Counter()

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

    #: Set when the resolved namespace is self-defeating — see
    #: _resolve_cache_namespace(). Reported by health_check() as well as
    #: logged, because a log line alone is what let #184 hide.
    namespace_warning: Optional[str] = CACHE_NAMESPACE_WARNING

    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.client: Optional[redis.Redis] = None
        self._memory_cache = {}  # {key: (value, expiry_timestamp)}
        self._memory_cache_max_size = 1024
        self._memory_cache_max_bytes = 16 * 1024 * 1024
        self._memory_cache_max_entry_bytes = 2 * 1024 * 1024
        self._memory_lock = threading.RLock()
        self._metrics = Counter()
        self._unserialisable_values = 0
        self._last_unserialisable = None
        self.namespace = CACHE_NAMESPACE
        self.namespace_source = CACHE_NAMESPACE_SOURCE
        self.redis_url_configured = bool(redis_url or os.getenv("REDIS_URL"))
        self.namespace_warning = CACHE_NAMESPACE_WARNING
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
                    self.record("hit")
                    return json.loads(value)
            else:
                # Fallback to memory cache
                with self._memory_lock:
                    entry = self._memory_cache.get(self._scoped(key))
                    if entry is not None:
                        value, expiry = entry[:2]
                        if time.time() < expiry:
                            self.record("hit")
                            return value
                        del self._memory_cache[self._scoped(key)]
                        self.record("expired")
        except Exception as e:
            logger.error("Cache get error (%s)", type(e).__name__)
        self.record("miss")
        return None

    def record(self, event: str) -> None:
        """Fixed-name counters; keys and public query values are never labels."""
        if event in {"hit", "miss", "expired", "evicted", "oversized", "lock_contention"}:
            with self._memory_lock:
                self._metrics[event] += 1

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
            key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
            match = re.fullmatch(
                r"Object of type ([A-Za-z_][A-Za-z0-9_]*) is not JSON serializable",
                str(exc),
            )
            failure_type = match.group(1) if match else type(exc).__name__
            self._last_unserialisable = f"key_sha256={key_hash}: {failure_type}"
            logger.error(
                "Cache set SKIPPED — key_sha256=%s cannot be serialised "
                "(%s). Total such values: %d",
                key_hash,
                failure_type,
                self._unserialisable_values,
            )
            return

        try:
            if self.client:
                self.client.setex(self._scoped(key), ttl, payload)
            else:
                # Fallback to memory cache with TTL
                size = len(payload.encode("utf-8"))
                with self._memory_lock:
                    entry_limit = getattr(self, "_memory_cache_max_entry_bytes", 2 * 1024 * 1024)
                    total_limit = getattr(self, "_memory_cache_max_bytes", 16 * 1024 * 1024)
                    if size > entry_limit or size > total_limit:
                        self.record("oversized")
                        return
                    scoped = self._scoped(key)
                    self._memory_cache.pop(scoped, None)
                    now = time.time()
                    for stale, entry in list(self._memory_cache.items()):
                        if now >= entry[1]:
                            del self._memory_cache[stale]
                    used = sum(
                        entry[2] if len(entry) > 2 else 0
                        for entry in self._memory_cache.values()
                    )
                    while self._memory_cache and (
                        len(self._memory_cache) >= self._memory_cache_max_size
                        or used + size > total_limit
                    ):
                        oldest, removed = next(iter(self._memory_cache.items()))
                        del self._memory_cache[oldest]
                        used -= removed[2] if len(removed) > 2 else 0
                        self.record("evicted")
                    # Store the JSON shape Redis would return, not the live model.
                    self._memory_cache[scoped] = (json.loads(payload), now + ttl, size)
        except Exception as e:
            logger.error("Cache set error (transport): %s", type(e).__name__)

    def delete(self, key: str):
        """Delete key from cache."""
        try:
            if self.client:
                self.client.delete(self._scoped(key))
            else:
                with self._memory_lock:
                    self._memory_cache.pop(self._scoped(key), None)
        except Exception as e:
            logger.error("Cache delete error (%s)", type(e).__name__)

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
                with self._memory_lock:
                    keys_to_delete = [
                        k for k in self._memory_cache if scoped_pattern.replace("*", "") in k
                    ]
                    for key in keys_to_delete:
                        self._memory_cache.pop(key, None)
        except Exception as e:
            logger.error("Cache clear error (%s)", type(e).__name__)

    def health_check(self) -> dict:
        """Check Redis health status.

        ``unserialisable_values`` is reported on EVERY path, including the
        healthy one. A connected, responsive Redis that is being handed values
        it can never store is exactly the production state issue #184 sat in
        for months, and a health report that only describes the connection
        cannot distinguish it from a cache that is working.
        """
        with self._memory_lock:
            memory_entries = len(self._memory_cache)
            memory_payload_bytes = sum(
                entry[2] if len(entry) > 2 else 0
                for entry in self._memory_cache.values()
            )
            counters = dict(self._metrics)
        diagnostics = {
            "unserialisable_values": self._unserialisable_values,
            "cache_namespace": self.namespace,
            "cache_namespace_source": self.namespace_source,
            "redis_configured": self.redis_url_configured,
            "response_cache_counters": counters,
            "memory_entries": memory_entries,
            "memory_payload_bytes": memory_payload_bytes,
        }
        if self._last_unserialisable:
            diagnostics["last_unserialisable"] = self._last_unserialisable
        if self.namespace_warning:
            diagnostics["cache_namespace_warning"] = self.namespace_warning

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
            logger.error("Redis health check failed (%s)", type(e).__name__)

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
    if isinstance(result, BaseModel):
        result = result.model_dump(mode="json")
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
        signature = inspect.signature(func)
        sync_locks = [threading.Lock() for _ in range(64)]
        loop_locks: "weakref.WeakKeyDictionary[Any, list[asyncio.Lock]]" = (
            weakref.WeakKeyDictionary()
        )
        loop_locks_guard = threading.Lock()
        prefix = key_prefix or func.__name__

        def key_for(args, kwargs):
            bound = signature.bind_partial(*args, **kwargs)
            bound.apply_defaults()
            parameters = {
                name: jsonable_encoder(value)
                for name, value in bound.arguments.items()
                if name not in {"db", "request", "background_tasks"}
                and _is_cacheable_param(value)
            }
            # The generation is part of the logical key. An in-flight read
            # completed after invalidation can only write its OLD generation.
            from cache.invalidation import generation_identity

            payload = json.dumps(
                {"arguments": parameters, "generation": generation_identity()},
                sort_keys=True,
                separators=(",", ":"),
            )
            digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            return f"{prefix}:{digest}", int(digest[:8], 16) % 64

        def store(key, result):
            if result is None:
                return
            effective_ttl = (
                min(ttl, TRANSIENT_FAILURE_TTL)
                if is_transient_failure(result)
                else ttl
            )
            cache.set(key, result, effective_ttl)

        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                key, stripe = key_for(args, kwargs)
                hit = await asyncio.to_thread(cache.get, key)
                if hit is not None:
                    return hit
                loop = asyncio.get_running_loop()
                with loop_locks_guard:
                    locks = loop_locks.get(loop)
                    if locks is None:
                        locks = [asyncio.Lock() for _ in range(64)]
                        loop_locks[loop] = locks
                if locks[stripe].locked() and hasattr(cache, "record"):
                    await asyncio.to_thread(cache.record, "lock_contention")
                async with locks[stripe]:
                    hit = await asyncio.to_thread(cache.get, key)
                    if hit is not None:
                        return hit
                    result = await func(*args, **kwargs)
                    await asyncio.to_thread(store, key, result)
                    return result
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                key, stripe = key_for(args, kwargs)
                hit = cache.get(key)
                if hit is not None:
                    return hit
                lock = sync_locks[stripe]
                if lock.locked() and hasattr(cache, "record"):
                    cache.record("lock_contention")
                with lock:
                    hit = cache.get(key)
                    if hit is not None:
                        return hit
                    result = func(*args, **kwargs)
                    store(key, result)
                    return result

        return wrapper

    return decorator


def invalidate_cache(pattern: str):
    """Invalidate cache entries matching pattern."""
    cache.clear_pattern(pattern)
    logger.info("Invalidated cache pattern")
