"""Allowlisted structured events; never serialize content or exception objects."""
import json
import logging
from uuid import UUID

logger = logging.getLogger("social")
_ALLOWED = {"request_id", "worker_id", "post_id", "revision_id", "publication_id", "target_id", "account_id", "asset_id", "flow_id", "platform", "operation_id", "operation", "lease_epoch", "attempt_sequence", "duration_ms", "result", "error_code", "error_type", "action"}


def log_event(event: str, **fields):
    payload = {"event": event}
    for key, value in fields.items():
        if key in _ALLOWED and (value is None or isinstance(value, (str, int, bool, UUID))):
            payload[key] = str(value) if isinstance(value, UUID) else value
    logger.info(json.dumps(payload, sort_keys=True, separators=(",", ":")))
