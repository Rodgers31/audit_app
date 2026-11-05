"""One saved-grant read budget, shared by every page and response body."""
from contextlib import contextmanager
from contextvars import ContextVar
import math
from time import monotonic

from ..service import SocialError
from .verification_protocol import CLEANUP_SECONDS, OPERATION_SECONDS


MAX_REQUESTS = 44
MAX_BODY_BYTES = 1_000_000
MAX_TOTAL_BYTES = 8_000_000
current_budget = ContextVar('meta_saved_grant_budget', default=None)


def exhausted():
    return SocialError('GRANT_VERIFICATION_BUDGET_EXCEEDED',
        'Saved-grant verification exceeded its read or time allowance. '
        'Keep this command key when checking or retrying the operation.', 503,
        retryable=False)


class VerificationBudget:
    def __init__(self, *, deadline=None, clock=monotonic):
        if not callable(clock):
            raise exhausted()
        self.clock = clock
        now = clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise exhausted()
        self.deadline = now + OPERATION_SECONDS if deadline is None else deadline
        if (type(self.deadline) not in (int, float)
                or not math.isfinite(self.deadline)
                or not now < self.deadline <= now + OPERATION_SECONDS):
            raise exhausted()
        self.requests = self.bytes_read = 0

    def remaining(self):
        value = self.deadline - self.clock()
        if not math.isfinite(value) or value <= 0:
            raise exhausted()
        return value

    def request(self, method):
        self.remaining()
        if method != 'GET' or self.requests >= MAX_REQUESTS:
            raise exhausted()
        self.requests += 1

    def body(self, size):
        self.remaining()
        if type(size) is not int or size < 0 or self.bytes_read + size > MAX_TOTAL_BYTES:
            raise exhausted()
        self.bytes_read += size

    @contextmanager
    def activate(self):
        self.remaining()
        token = current_budget.set(self)
        try:
            yield self
            self.remaining()
        finally:
            current_budget.reset(token)
