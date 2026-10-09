"""Bounded administrator audit payload policy, independent of storage/auth."""
import re
from datetime import datetime
from typing import Any, Mapping


def safe_audit_payload(action: str, payload: Any) -> dict:
    """Keep only bounded evidence fields used by current callers, also on read.

    Unknown fields/actions are omitted rather than guessing whether an arbitrary
    string contains credentials. Existing legacy rows receive the same policy.
    Redirects may carry recovery tokens even in paths, so never retain them.
    """
    if not isinstance(payload, Mapping):
        return {"_redacted": "Unsupported payload"}
    result: dict[str, Any] = {}
    if action == "users.update_roles":
        for key in ("old", "new"):
            roles = payload.get(key)
            if isinstance(roles, list) and len(roles) <= 20:
                result[key] = [r if isinstance(r, str) and r in {"admin", "citizen"} else "[redacted role]" for r in roles]
    elif action in {"users.delete", "users.send_reset"}:
        key = "deleted_email" if action == "users.delete" else "email"
        email = payload.get(key)
        if isinstance(email, str) and len(email) <= 255 and re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", email):
            result[key] = email
        if action == "users.delete":
            value = payload.get("deleted_created_at")
            if isinstance(value, str) and len(value) <= 40:
                try:
                    result["deleted_created_at"] = datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
                except ValueError:
                    pass
        elif "redirect_to" in payload:
            result["redirect_to"] = "[redacted]" if payload["redirect_to"] else None
    elif action == "etl.trigger":
        job_id = payload.get("job_id")
        if type(job_id) is int and 0 < job_id <= 2**31 - 1:
            result["job_id"] = job_id
        if type(payload.get("dry_run")) is bool:
            result["dry_run"] = payload["dry_run"]
    if set(payload) - set(result):
        result["_redacted"] = "Unsupported fields omitted"
    return result

