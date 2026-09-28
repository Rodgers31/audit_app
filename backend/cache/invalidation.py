"""Clearing every API response cache after the nightly seed (issue #231).

The seed writes the database from GitHub Actions. The API process it has to
reach runs on Render and caches responses in three layers:

* **Redis**, when ``REDIS_URL`` is set. Shared by every worker.
* **In-process memory**, in each gunicorn worker: ``RedisCache._memory_cache``
  (which is what production actually uses, since production has no Redis),
  the per-endpoint fallback dicts in ``main.cached`` and
  ``routers.money_flow._cached``, and ``main.InternalAPIClient._cache``.

An HTTP call lands on ONE worker. That worker can clear Redis and its own
memory, but not a sibling's. So it also rewrites a **generation marker**, a
small file in the container's temp dir that all workers can see. Each worker
checks the marker at the start of every request (one ``os.stat``), and when
it has changed since that worker last looked, the worker clears its own
caches before serving. Every worker therefore drops its stale entries on the
first request it serves after the call, with no shared store needed.

Limits, stated rather than implied:

* The marker is per CONTAINER. Several Render instances with no Redis would
  each need their own call. Production runs one instance; set ``REDIS_URL``
  before scaling out.
* ``main._peers_cache`` is deliberately NOT cleared. It holds World Bank and
  IMF figures fetched live, not anything the seed writes, and clearing it
  would only force a slow external refetch.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import uuid
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_MARKER = os.path.join(tempfile.gettempdir(), "auditgava-cache-generation")


class InvalidationError(RuntimeError):
    """A cache layer could not be cleared. ``reason`` is a stable slug."""

    def __init__(self, reason: str, detail: str):
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def marker_path() -> str:
    """Read on every call so tests and operators can move it."""
    return os.getenv("CACHE_GENERATION_FILE") or _DEFAULT_MARKER


# ── Local (this process) caches ─────────────────────────────────────────

#: name -> function that clears that cache and returns how many entries it
#: dropped. Registered by the modules that own the caches, so this module
#: never has to import main.
_local_caches: Dict[str, Callable[[], int]] = {}


def register_local_cache(name: str, clear: Callable[[], int]) -> None:
    _local_caches[name] = clear


def _redis_instances() -> List[object]:
    from cache.redis_cache import RedisCache

    seen, out = set(), []
    for rc in list(RedisCache._instances):
        if id(rc) not in seen:
            seen.add(id(rc))
            out.append(rc)
    return out


def clear_local_caches() -> Dict[str, int]:
    """Empty every in-process cache in THIS worker. Returns entries dropped
    per cache. Cannot partially fail: these are dicts."""
    counts: Dict[str, int] = {}
    memory = 0
    for rc in _redis_instances():
        mem = getattr(rc, "_memory_cache", None)
        if mem is not None:
            with rc._memory_lock:
                memory += len(mem)
                mem.clear()
    counts["redis_cache_memory"] = memory
    for name, clear in _local_caches.items():
        counts[name] = int(clear() or 0)
    return counts


def clear_redis() -> Dict[str, object]:
    """Delete this build's keys from Redis, if Redis is in use.

    Unlike ``RedisCache.clear_pattern``, which logs a failure and returns as
    though it had worked, this RAISES, because the caller has to be able to
    tell a cleared cache from one that is still full.
    """
    clients = {}
    for rc in _redis_instances():
        client = getattr(rc, "client", None)
        if client is not None:
            # Instances pointing at one server share a client per namespace.
            clients.setdefault((id(client), rc.namespace), (client, rc.namespace))
    deleted = 0
    for client, namespace in clients.values():
        try:
            keys = list(client.scan_iter(match=f"{namespace}:*", count=500))
            if keys:
                deleted += int(client.delete(*keys) or 0)
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            raise InvalidationError(
                "redis_invalidation_failed", f"{type(exc).__name__}: {exc}"
            ) from exc
    return {"configured": bool(clients), "deleted": deleted}


# ── Cross-worker generation marker ──────────────────────────────────────

_lock = threading.Lock()
#: The marker as this process last saw it. ``None`` until the first check.
_seen: Optional[Tuple[int, int, int]] = None
_seen_initialised = False


def _stat_token() -> Optional[Tuple[int, int, int]]:
    """Identity of the marker file right now, or None if there is none.

    The file is replaced atomically on every bump, so its inode changes even
    if two bumps land in the same nanosecond.
    """
    try:
        st = os.stat(marker_path())
    except FileNotFoundError:
        return None
    return (st.st_ino, st.st_mtime_ns, st.st_size)


def generation_identity() -> Optional[Tuple[int, int, int]]:
    """Stable cache-key generation for an in-flight response.

    A loader keeps the identity it started with; after a marker bump its
    late write is unreachable by new requests, even in another worker.
    """
    try:
        return _stat_token()
    except OSError:
        # The request middleware reports the unreadable marker. Keep serving
        # via the existing fallback policy rather than turning every read 500.
        return None


def bump_generation() -> str:
    """Tell every worker in this container that its caches are stale.

    Raises ``InvalidationError`` when the marker cannot be written. If the
    other workers cannot be told, the call has not worked.
    """
    token = uuid.uuid4().hex
    path = marker_path()
    tmp = f"{path}.{os.getpid()}.{token[:8]}.tmp"
    try:
        with open(tmp, "w") as fh:
            fh.write(token)
        os.replace(tmp, path)
    except OSError as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise InvalidationError(
            "generation_marker_unwritable", f"{path}: {exc}"
        ) from exc
    return token


def sync_generation() -> bool:
    """Clear this worker's caches if another worker has bumped the marker
    since this worker last looked. Returns True when it cleared.

    Called at the start of every request. The first call in a process only
    records the marker, since a new process has nothing cached yet.
    """
    global _seen, _seen_initialised
    try:
        token = _stat_token()
    except OSError as exc:
        # Cannot see the marker, so cannot know whether to clear. Serve from
        # cache and say so. Refusing to serve would take the site down over
        # a freshness signal.
        logger.error("cache generation marker unreadable (%s): serving cached", exc)
        return False
    if _seen_initialised and token == _seen:
        return False
    with _lock:
        if _seen_initialised and token == _seen:
            return False
        first = not _seen_initialised
        _seen, _seen_initialised = token, True
        if first:
            return False
        counts = clear_local_caches()
    logger.info("cache generation changed; cleared this worker's caches: %s", counts)
    return True


def invalidate_all() -> Dict[str, object]:
    """Everything the nightly needs: Redis, this worker, then the marker
    that tells the other workers. Raises ``InvalidationError`` on the first
    layer that cannot be cleared."""
    global _seen, _seen_initialised
    redis_result = clear_redis()
    with _lock:
        local = clear_local_caches()
        generation = bump_generation()
        # This worker is already clean; do not clear it again on its next
        # request.
        _seen, _seen_initialised = _stat_token(), True
    return {
        "redis": redis_result,
        "local": {"cleared_entries": sum(local.values()), "by_cache": local},
        "generation": generation,
        "pid": os.getpid(),
    }
