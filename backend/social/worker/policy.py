"""Pure bounded retry and adapter-shape safety checks."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import random
import math

from ..contracts import OperationPlan, OperationResult, RetryDecision

BLOCK_CODES = frozenset({"TOKEN_EXPIRED", "TOKEN_REVOKED", "PERMISSION_DENIED", "ACCOUNT_INELIGIBLE",
                         "BUDGET_EXHAUSTED", "AUTHORIZATION_REQUIRED", "RECONNECT_REQUIRED"})
RETRY_CODES = frozenset({"TEMPORARY_REJECTION", "RATE_LIMITED", "NOT_SENT", "CONNECTION_NOT_SENT"})


def bounded_json(value, *, max_bytes=65536):
    if type(max_bytes) is not int or not 1 <= max_bytes <= 65536:
        raise ValueError("JSON ceiling must be a positive bounded integer")
    if not isinstance(value, dict):
        raise ValueError("Checkpoint/receipt must be an object")
    def check(item, depth=0):
        if depth > 12:
            raise ValueError("Checkpoint/receipt nesting is too deep")
        if isinstance(item, dict):
            if not all(isinstance(key, str) for key in item):
                raise ValueError("Checkpoint/receipt keys must be strings")
            for child in item.values():
                check(child, depth+1)
        elif isinstance(item, (list, tuple)):
            for child in item:
                check(child, depth+1)
        elif item is not None and not isinstance(item, (str, int, float, bool)):
            raise ValueError("Checkpoint/receipt must be JSON")
    check(value)
    if len(json.dumps(value, allow_nan=False).encode()) > max_bytes:
        raise ValueError("Checkpoint/receipt exceeds its bounded size")
    return value


def validate_plan(plan: OperationPlan, checkpoint: dict):
    bounded_json(plan.checkpoint)
    if plan.checkpoint != checkpoint:
        raise ValueError("Adapter plan must name its exact checkpoint input")
    read = plan.operation in ("poll", "reconcile")
    if read != (plan.safe_replay_class == "read_only") or (read and plan.publication_capable):
        raise ValueError("Read operation cannot acquire a public permit")
    if plan.operation == "publish" and not plan.publication_capable:
        raise ValueError("Publish must acquire a public permit")
    if plan.operation == "delete":
        raise ValueError("Deletion is outside the batch-one dispatcher")


def retry_decision(result: OperationResult, *, now: datetime, submit_count: int,
                   first_started_at: datetime, retry_deadline: datetime | None,
                   content_valid_until: datetime | None, max_submissions=5,
                   lifetime_seconds=86400, random_fraction=None) -> RetryDecision:
    if type(submit_count) is not int or not 0 <= submit_count <= 5:
        raise ValueError("Submission count must be an integer between zero and five")
    if type(max_submissions) is not int or not 1 <= max_submissions <= 5:
        raise ValueError("Submission limit must be bounded to five")
    if type(lifetime_seconds) is not int or not 0 < lifetime_seconds <= 86400:
        raise ValueError("Retry lifetime must be bounded to 24 hours")
    for value in (now, first_started_at, retry_deadline, content_valid_until):
        if value is not None and (not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Retry times must be timezone-aware datetimes")
    if not isinstance(now, datetime) or not isinstance(first_started_at, datetime) or first_started_at > now:
        raise ValueError("Retry origin cannot be absent or in the future")
    if random_fraction is not None and (isinstance(random_fraction, bool) or not isinstance(random_fraction, (float, int)) or not math.isfinite(random_fraction) or not 0 <= random_fraction <= 1):
        raise ValueError("Jitter fraction must be finite and between zero and one")
    if result.outcome == "ambiguous":
        return RetryDecision(action="reconcile", reason="ACCEPTANCE_UNCERTAIN")
    if result.error_code in BLOCK_CODES:
        return RetryDecision(action="block", reason=result.error_code)
    if result.error_code not in RETRY_CODES:
        return RetryDecision(action="fail", reason=result.error_code or "PERMANENT_REJECTION")
    if not result.retry_safe:
        return RetryDecision(action="reconcile", reason="ACCEPTANCE_UNCERTAIN")
    deadline = min(d for d in (first_started_at+timedelta(seconds=lifetime_seconds),
                              retry_deadline, content_valid_until) if d is not None)
    if submit_count >= max_submissions:
        return RetryDecision(action="block", reason="SUBMISSION_LIMIT")
    # nondeterminism-ok: jitter schedules operational retries; it never supplies a published financial figure.
    jitter = (random_fraction if random_fraction is not None else random.random())
    next_at = now+timedelta(seconds=max(1, jitter * min(3600, 30 * 2 ** max(0, submit_count-1))))
    if result.next_action_at:
        if result.next_action_at.tzinfo is None:
            return RetryDecision(action="block", reason="INVALID_PROVIDER_RETRY_TIME")
        next_at = max(next_at, result.next_action_at)
    if next_at >= deadline:
        return RetryDecision(action="block", reason="RETRY_DEADLINE_EXCEEDED")
    return RetryDecision(action="retry", reason=result.error_code or "SAFE_RETRY", next_action_at=next_at)
