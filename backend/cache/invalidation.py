"""Clearing every API response cache after the nightly seed (issue #231).

The seed writes the database from GitHub Actions. The API process it has to
reach runs on Render and caches responses in three layers:

* **Redis**, when ``REDIS_URL`` is set. Shared by every worker.
* **In-process memory**, in each gunicorn worker: ``RedisCache._memory_cache``
  (which is what production actually uses, since production has no Redis),
  the single shared bounded fallback in ``main.cached`` if cache setup fails,
  and the per-endpoint fallback dicts in ``routers.money_flow._cached``.

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
    token, _ = _publish_generation()
    return token


def _publish_generation() -> Tuple[str, Tuple[int, int, int]]:
    """Return the identity of OUR published file, not a competing bump."""
    token = uuid.uuid4().hex
    path = marker_path()
    tmp = f"{path}.{os.getpid()}.{token[:8]}.tmp"
    try:
        with open(tmp, "w") as fh:
            fh.write(token)
            fh.flush()
            st = os.fstat(fh.fileno())
            identity = (st.st_ino, st.st_mtime_ns, st.st_size)
        os.replace(tmp, path)
    except OSError as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise InvalidationError(
            "generation_marker_unwritable", f"{path}: {exc}"
        ) from exc
    return token, identity


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
        if first:
            _seen, _seen_initialised = token, True
            return False
        counts = clear_local_caches()
        # A failed callback leaves this generation unacknowledged. The next
        # request retries rather than permanently keeping a partially stale cache.
        _seen, _seen_initialised = token, True
    logger.info("cache generation changed; cleared this worker's caches: %s", counts)
    return True


def generation_status() -> Dict[str, object]:
    """Observe this worker's actual adoption, without writing a marker.

    Like ordinary request middleware, this may clear local caches after a bump.
    An unreadable marker or failed clear cannot certify successful adoption.
    A concurrent bump may produce synchronised=False; callers must retry and
    compare the non-null identity to the original invalidation acknowledgement.
    """
    try:
        sync_generation()
        with _lock:
            observed = _stat_token()
            adopted = _seen
            initialised = _seen_initialised
    except OSError as exc:
        raise InvalidationError(
            "generation_marker_unreadable", "Cannot observe the shared marker"
        ) from exc
    except Exception as exc:
        raise InvalidationError(
            "local_invalidation_failed", "This worker could not clear its caches"
        ) from exc
    return {
        "pid": os.getpid(),
        "commit": os.getenv("RENDER_GIT_COMMIT"),
        "marker_path": marker_path(),
        "observed_identity": observed,
        "adopted_identity": adopted,
        "synchronised": initialised and observed == adopted,
    }


def invalidate_all() -> Dict[str, object]:
    """Everything the nightly needs: Redis, this worker, then the marker
    that tells the other workers. Raises ``InvalidationError`` on the first
    layer that cannot be cleared."""
    global _seen, _seen_initialised
    redis_result = clear_redis()
    with _lock:
        local = clear_local_caches()
        generation, published_identity = _publish_generation()
        if _stat_token() != published_identity:
            raise InvalidationError(
                "generation_marker_changed", "Published marker disappeared or was replaced"
            )
        # This worker is already clean; do not clear it again on its next
        # request.
        _seen, _seen_initialised = published_identity, True
    return {
        "redis": redis_result,
        "local": {"cleared_entries": sum(local.values()), "by_cache": local},
        "generation": generation,
        "marker_identity": published_identity,
        "pid": os.getpid(),
    }


def _process(pid):
    """Kernel PID + start ticks prevent PID reuse from certifying a worker."""
    from pathlib import Path
    root = Path('/proc') / str(pid)
    raw = (root / 'stat').read_text()
    fields = raw.rsplit(') ', 1)[1].split()
    command = (root / 'cmdline').read_bytes()
    if len(command) > 32768 or not fields[19].isdigit() or not fields[1].isdigit():
        raise ValueError('Malformed process identity')
    return {'pid': pid, 'parent': int(fields[1]), 'identity': f'{pid}:{fields[19]}',
            'command': command.replace(b'\0', b' ').decode('utf-8', errors='strict')}



def _web_launch(command, module):
    """Recognize the actual console/module launch, never a path substring."""
    import re
    import shlex
    from pathlib import Path
    parts = shlex.split(command)
    if not parts:
        return False
    first = Path(parts[0]).name
    if module == 'gunicorn' and first == 'gunicorn:' and len(parts) > 1 and parts[1] in ('master', 'worker'):
        return True
    if first == module:
        return True
    return (re.fullmatch(r'python(?:[0-9]+(?:\.[0-9]+)*)?', first) is not None and len(parts) > 1
            and (parts[1:3] == ['-m', module] or Path(parts[1]).name == module))


def _other_web_processes(allowed):
    """Read kernel command inventories twice; unknown/changing scope refuses."""
    from pathlib import Path
    entries = sorted(p for p in Path('/proc').iterdir() if p.name.isdigit())
    if not 1 <= len(entries) <= 4096:
        raise ValueError('Process census exceeds bound')
    peers = []
    for entry in entries:
        if int(entry.name) in allowed:
            continue
        try:
            raw = (entry / 'cmdline').read_bytes()
        except FileNotFoundError:
            raise ValueError('Process inventory changed') from None
        if len(raw) > 32768:
            raise ValueError('Process command exceeds bound')
        command = raw.replace(b'\0', b' ').decode('utf-8', errors='strict')
        if _web_launch(command, 'uvicorn') or _web_launch(command, 'gunicorn'):
            peers.append(int(entry.name))
    if entries != sorted(p for p in Path('/proc').iterdir() if p.name.isdigit()):
        raise ValueError('Process inventory changed')
    return peers

def serving_census() -> Dict[str, object]:
    """Census the actual web workers in the current Linux container.

    Supported deployments are a Gunicorn master and its workers, or a PID1
    Uvicorn process (the repository container contract). Unknown supervisors,
    multi-process Uvicorn, process churn and unreadable procfs fail closed.
    This makes no claim about instances in other PID namespaces; deployment
    acceptance must separately verify the existing single-instance topology.
    """
    import hashlib
    import re
    from pathlib import Path
    try:
        me = _process(os.getpid())
        parent = _process(me['parent']) if me['parent'] > 0 else None
        if parent is not None and _web_launch(parent['command'], 'gunicorn'):
            supervisor = parent
            def workers():
                found = []
                # Read the supervisor's kernel child list, not a self-reported
                # environment count or a random sample of load-balanced HTTP.
                children = (Path('/proc') / str(parent['pid']) / 'task' / str(parent['pid']) / 'children').read_text().split()
                if not 1 <= len(children) <= 64:
                    raise ValueError('Empty/oversized web census')
                for pid in children:
                    item = _process(int(pid))
                    if item['parent'] != parent['pid'] or not _web_launch(item['command'], 'gunicorn'):
                        raise ValueError('Unrecognized supervisor child')
                    found.append(item['identity'])
                return sorted(found)
            before = workers()
            if before != workers():
                raise ValueError('Serving census changed')
        elif me['pid'] == 1 and me['parent'] == 0 and _web_launch(me['command'], 'uvicorn'):
            # Refuse an unaccounted parent/sibling topology. Uvicorn's spawned
            # worker command does not contain uvicorn and cannot enter here.
            count = re.search(r'--workers(?:=|\s+)(\S+)', me['command'])
            if (count is not None and count[1] != '1') or (count is None and os.getenv('WEB_CONCURRENCY', '1') != '1'):
                raise ValueError('Unqualified multi-process Uvicorn census')
            if _other_web_processes({me['pid']}) or _other_web_processes({me['pid']}):
                raise ValueError('Unaccounted web process peers')
            supervisor, before = me, [me['identity']]
        else:
            raise ValueError('Unknown web supervisor')
        if me['identity'] not in before or _process(supervisor['pid'])['identity'] != supervisor['identity']:
            raise ValueError('Serving process changed')
        allowed = {supervisor['pid'], *(int(worker.split(':')[0]) for worker in before)}
        if _other_web_processes(allowed) or _other_web_processes(allowed):
            raise ValueError('Unaccounted web master or worker')
        _listener_scope(allowed)
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        namespace = os.stat('/proc/self/ns/pid').st_ino
        instance = hashlib.sha256(f'{boot}:{namespace}:{supervisor["identity"]}'.encode()).hexdigest()
        return {'scope': 'container', 'instance': instance, 'supervisor': supervisor['identity'],
                'workers': before, 'worker': me['identity']}
    except (OSError, ValueError, IndexError, UnicodeError) as exc:
        raise InvalidationError('serving_census_unverified', 'Actual serving web-process census unavailable') from exc


def _tcp_listeners():
    """Bounded kernel TCP listener inventory: inode -> bound port."""
    from pathlib import Path
    listeners = {}
    for name in ('tcp', 'tcp6'):
        with (Path('/proc/net') / name).open() as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('Kernel TCP inventory exceeds bound')
        for line in raw.splitlines()[1:]:
            fields = line.split()
            if len(fields) < 10:
                raise ValueError('Malformed kernel TCP inventory')
            if fields[3] == '0A':
                inode, port = int(fields[9]), int(fields[1].rsplit(':', 1)[1], 16)
                if inode <= 0 or not 0 < port <= 65535 or inode in listeners:
                    raise ValueError('Malformed kernel listener')
                listeners[inode] = port
    return listeners


def _socket_inodes(pid, remaining):
    """Read descriptor links, never their content or another process's secrets."""
    from pathlib import Path
    import re
    found = set()
    directory = Path('/proc') / str(pid) / 'fd'
    for index, entry in enumerate(directory.iterdir()):
        remaining[0] -= 1
        if index >= 4096 or remaining[0] < 0:
            raise ValueError('Kernel descriptor inventory exceeds bound')
        try:
            link = os.readlink(entry)
        except FileNotFoundError:
            # Ordinary accepted connections can close during enumeration. The
            # LISTEN endpoint inventory is independently checked before/after.
            continue
        match = re.fullmatch(r'socket:\[([0-9]+)\]', link)
        if match:
            found.add(int(match[1]))
    return found


def _listener_scope(allowed):
    """Reject hidden masters/custom servers sharing the actual serving ports.

    SO_REUSEPORT creates different inodes, so matching only our inherited socket
    is insufficient. Inspect every listener on our bound ports and all of its
    holders. This proof is additional to exact supervisor/child/launch checks.
    """
    from pathlib import Path
    before = _tcp_listeners()
    own = _socket_inodes(os.getpid(), [4096]) & before.keys()
    if not own:
        raise ValueError('Actual serving listener absent')
    ports = {before[inode] for inode in own}
    targets = {inode: port for inode, port in before.items() if port in ports}
    def holders():
        result, remaining = set(), [100000]
        for index, entry in enumerate(Path('/proc').iterdir()):
            if index > 8192:
                raise ValueError('Kernel process inventory exceeds bound')
            if not entry.name.isdigit():
                continue
            try:
                inodes = _socket_inodes(int(entry.name), remaining)
            except FileNotFoundError:
                continue  # An exited non-serving process is not a live holder.
            if inodes & targets.keys():
                result.add(int(entry.name))
        return result
    first, second = holders(), holders()
    after = {inode: port for inode, port in _tcp_listeners().items() if port in ports}
    if first != second or after != targets or first != set(allowed):
        raise ValueError('Serving listener holders missing, changed or unaccounted')
