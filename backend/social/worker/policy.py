"""Pure bounded retry and adapter-shape safety checks."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import random

from ..contracts import OperationPlan, OperationResult, RetryDecision

BLOCK_CODES = frozenset({"TOKEN_EXPIRED", "TOKEN_REVOKED", "PERMISSION_DENIED", "ACCOUNT_INELIGIBLE",
                         "BUDGET_EXHAUSTED", "AUTHORIZATION_REQUIRED", "RECONNECT_REQUIRED"})
RETRY_CODES = frozenset({"TEMPORARY_REJECTION", "RATE_LIMITED", "NOT_SENT", "CONNECTION_NOT_SENT"})


def bounded_json(value, *, max_bytes=65536):
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
    jitter = (random_fraction if random_fraction is not None else random.random())
    next_at = now+timedelta(seconds=max(1, jitter * min(3600, 30 * 2 ** max(0, submit_count-1))))
    if result.next_action_at:
        if result.next_action_at.tzinfo is None:
            return RetryDecision(action="block", reason="INVALID_PROVIDER_RETRY_TIME")
        next_at = max(next_at, result.next_action_at)
    if next_at >= deadline:
        return RetryDecision(action="block", reason="RETRY_DEADLINE_EXCEEDED")
    return RetryDecision(action="retry", reason=result.error_code or "SAFE_RETRY", next_action_at=next_at)
