"""Small process-local admission bounds for public response construction."""
import asyncio
import copy
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException


def capacity_unavailable(detail):
    return HTTPException(503, detail, headers={'Retry-After': '1', 'Cache-Control': 'no-store'})


class BoundedFlights:
    """Coalesce misses without detached work borrowing a request's DB session.

    A leader executes in its calling task. Its cancellation fails followers and
    releases the key; cancelling a follower cannot cancel the leader. State is
    bounded across event loops, including non-HTTP callers.
    """
    def __init__(self, max_fills=8, max_followers=8):
        self.max_fills = max_fills
        self.max_followers = max_followers
        self._lock = threading.Lock()
        self._pending = {}

    async def run(self, key, operation):
        loop = asyncio.get_running_loop()
        identity = (loop, key)
        with self._lock:
            entry = self._pending.get(identity)
            leader = entry is None
            if leader:
                if len(self._pending) >= self.max_fills:
                    raise capacity_unavailable('Response construction capacity unavailable')
                future = loop.create_future()
                # Retrieve an unobserved failure when no followers remain.
                future.add_done_callback(lambda f: None if f.cancelled() else f.exception())
                entry = [future, 0]
                self._pending[identity] = entry
            else:
                if entry[1] >= self.max_followers:
                    raise capacity_unavailable('Response wait capacity unavailable')
                entry[1] += 1
        if not leader:
            try:
                return copy.deepcopy(await asyncio.shield(entry[0]))
            finally:
                with self._lock:
                    entry[1] -= 1
        try:
            result = await operation()
            entry[0].set_result(result)
            return result
        except BaseException as error:
            entry[0].set_exception(
                capacity_unavailable('Response construction interrupted; retry shortly')
                if isinstance(error, asyncio.CancelledError) else error)
            raise
        finally:
            with self._lock:
                del self._pending[identity]


class SingleWorker:
    """One physical blocking operation, no queued submissions after cancellation."""
    def __init__(self):
        self._slot = threading.BoundedSemaphore(1)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='regional-peers')

    async def run(self, operation):
        if not self._slot.acquire(blocking=False):
            raise capacity_unavailable('Peer observation read is still running; retry shortly')
        try:
            future = self._executor.submit(operation)
        except BaseException:
            self._slot.release()
            raise
        future.add_done_callback(lambda f: self._slot.release())
        waiter = asyncio.wrap_future(future)
        waiter.add_done_callback(lambda f: None if f.cancelled() else f.exception())
        return await asyncio.shield(waiter)

    def close(self):
        self._executor.shutdown(wait=True, cancel_futures=True)
