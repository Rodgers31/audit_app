"""Bounded per-job retention telemetry, separate from observation authority.

No payloads, URLs, storage keys or provider messages enter this summary. Missing
historical telemetry is unknown, never evidence that retention succeeded.
"""
from contextvars import ContextVar


_COUNTS = ("observed", "retained", "missing", "recovered", "retry_requests")
_LIMIT = 1_000_000
_scope = ContextVar("receipt_retention_scope", default=None)
_retries = ContextVar("receipt_capture_retries", default=None)


def safe_retention_summary(raw):
    """Project only coherent bounded counters; malformed evidence stays unknown."""
    if not isinstance(raw, dict) or set(raw) != {"state", *_COUNTS}:
        return {"state": "unverified"}
    if any(type(raw.get(key)) is not int or not 0 <= raw[key] <= _LIMIT for key in _COUNTS):
        return {"state": "unverified"}
    if (raw["observed"] != raw["retained"] + raw["missing"]
            or raw["recovered"] > min(raw["retained"], raw["retry_requests"])
            or (raw["retry_requests"] and not raw["missing"] and not raw["recovered"])):
        return {"state": "unverified"}
    state = "missing_bytes" if raw["missing"] else ("confirmed" if raw["observed"] else "not_observed")
    if raw["state"] != state or (not raw["observed"] and raw["retry_requests"]):
        return {"state": "unverified"}
    return {"state": state, **{key: raw[key] for key in _COUNTS}}


class RetentionScope:
    def __init__(self):
        self.counts = dict.fromkeys(_COUNTS, 0)
        self.closed = False
        self.token = _scope.set(self)

    def summary(self):
        state = "missing_bytes" if self.counts["missing"] else ("confirmed" if self.counts["observed"] else "not_observed")
        return safe_retention_summary({"state": state, **self.counts})

    def close(self):
        if not self.closed:
            self.closed = True
            _scope.reset(self.token)


def begin_capture():
    return _retries.set(0)


def record_retry():
    current = _retries.get()
    if current is not None:
        _retries.set(current + 1)


def finish_capture(token, *, matched):
    retries = _retries.get() or 0
    _retries.reset(token)
    scope = _scope.get()
    if scope is not None and not scope.closed:
        return CaptureOutcome(scope, matched, retries)
    return None


class CaptureOutcome:
    """One capability's worst observed retention result, shared by parser copies.

    The scope keeps only fixed counters, not a registry of acquisitions. This
    token is not serialized and cannot confer acquisition/publication authority.
    """
    def __init__(self, scope, matched, retries):
        self.scope, self.matched = scope, matched
        self.recovered = matched and retries > 0
        scope.counts["observed"] += 1
        scope.counts["retained" if matched else "missing"] += 1
        scope.counts["recovered"] += int(self.recovered)
        scope.counts["retry_requests"] += retries

    def recheck(self, *, matched, retries=0):
        if self.scope.closed or _scope.get() is not self.scope:
            return
        counts = self.scope.counts
        counts["retry_requests"] += retries
        if not matched and self.matched:
            counts["retained"] -= 1
            counts["missing"] += 1
            counts["recovered"] -= int(self.recovered)
            self.matched, self.recovered = False, False
        elif matched and self.matched and retries and not self.recovered:
            self.recovered = True
            counts["recovered"] += 1
        # A later successful read cannot hide an earlier missing DB snapshot.


def finish_recheck(token, outcome, *, matched):
    retries = _retries.get() or 0
    _retries.reset(token)
    scope = _scope.get()
    if scope is None or scope.closed:
        return outcome
    if outcome is None or outcome.scope is not scope:
        return CaptureOutcome(scope, matched, retries)
    outcome.recheck(matched=matched, retries=retries)
    return outcome
