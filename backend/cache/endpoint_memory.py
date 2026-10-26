"""Bounded response retention when the RedisCache helper cannot initialize.

This store has no Redis or bootstrap imports. It retains serialized JSON bytes,
not arbitrary Python objects; entry count bounds key/container overhead while
the byte limits apply to the exact retained payloads.
"""

import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any, Callable

from pydantic import BaseModel


def _model_json(value: Any) -> Any:
    # Match RedisCache's model handling without importing its singleton, whose
    # initialization is the failure this independent fallback must survive.
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


class BoundedResponseCache:
    """One thread-safe TTL/LRU store with a shared serialized payload budget."""

    def __init__(
        self,
        *,
        max_entries: int = 1024,
        max_bytes: int = 16 * 1024 * 1024,
        max_entry_bytes: int = 3 * 1024 * 1024,
        clock: Callable[[], float] = time.monotonic,
    ):
        if min(max_entries, max_bytes, max_entry_bytes) < 1:
            raise ValueError("Response cache limits must be positive")
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._max_entry_bytes = max_entry_bytes
        self._clock = clock
        self._entries: OrderedDict[str, tuple[bytes, float]] = OrderedDict()
        self._payload_bytes = 0
        self._lock = threading.RLock()

    @staticmethod
    def _key(key: str) -> str:
        # Query text must not enlarge retained keys beyond the count budget.
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def _expire(self, now: float) -> None:
        for key, (payload, expiry) in list(self._entries.items()):
            if now >= expiry:
                del self._entries[key]
                self._payload_bytes -= len(payload)

    def get(self, key: str) -> Any:
        digest = self._key(key)
        with self._lock:
            self._expire(self._clock())
            entry = self._entries.get(digest)
            if entry is None:
                return None
            self._entries.move_to_end(digest)
            payload = entry[0]
        # Each caller gets an independent JSON value. Neither the loader's
        # object nor a previous reader can mutate a future cached response.
        return json.loads(payload)

    def set(self, key: str, value: Any, ttl: int) -> bool:
        if ttl <= 0:
            return False
        try:
            payload = json.dumps(value, default=_model_json, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, OverflowError, RecursionError):
            # Responses, streams, unsupported objects and invalid JSON remain
            # available to the handler/framework, but are never retained.
            return False
        size = len(payload)
        if size > min(self._max_entry_bytes, self._max_bytes):
            return False
        digest = self._key(key)
        with self._lock:
            now = self._clock()
            self._expire(now)
            previous = self._entries.pop(digest, None)
            if previous is not None:
                self._payload_bytes -= len(previous[0])
            while self._entries and (
                len(self._entries) >= self._max_entries
                or self._payload_bytes + size > self._max_bytes
            ):
                _, (removed, _) = self._entries.popitem(last=False)
                self._payload_bytes -= len(removed)
            self._entries[digest] = (payload, now + ttl)
            self._payload_bytes += size
        return True

    def clear(self) -> int:
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            self._payload_bytes = 0
            return count

    def __len__(self) -> int:
        with self._lock:
            self._expire(self._clock())
            return len(self._entries)

    @property
    def payload_bytes(self) -> int:
        with self._lock:
            self._expire(self._clock())
            return self._payload_bytes
