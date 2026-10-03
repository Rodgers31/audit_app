"""Allowlisted operational events exclude content, URLs and credentials."""
import json
import logging
import re
from uuid import UUID

_ALLOWED = frozenset({
    "worker_id", "post_id", "revision_id", "publication_id", "target_id",
    "account_id", "operation_id", "operation", "lease_epoch", "attempt_sequence",
    "duration_ms", "outcome", "error_code", "active_claims",
})


def event(logger: logging.Logger, name: str, **fields) -> None:
    safe = {key: str(value) if isinstance(value, UUID) else value
            for key, value in fields.items() if key in _ALLOWED and
            (value is None or isinstance(value, (str, int, bool, UUID)))}
    if "error_code" in safe and safe["error_code"] is not None:
        if not isinstance(safe["error_code"], str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", safe["error_code"]):
            safe["error_code"] = "ADAPTER_ERROR"
    logger.info(json.dumps({"event": name, **safe}, sort_keys=True))
