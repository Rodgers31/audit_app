"""
Helper for writing rows to ``admin_audit_log``.

Why a helper, not a FastAPI dependency
--------------------------------------
A dependency would record the action at request *start*, before we
know whether the action succeeded. That produces noisy logs of
attempted-but-failed mutations and forces every endpoint to either
add a "rollback this audit row" path on failure or accept the
inaccuracy.

Callers decide when their action succeeded. This helper preserves their
independent audit transaction; a row does not prove a later worker executed.

Failures are swallowed
----------------------
A failure to write the audit log must never roll back the
underlying admin action. The action already happened — failing the
request would be a worse outcome than a missing log row. We log a fixed
failure message so a missing-audit incident remains observable without
exposing exception text, SQL parameters or caller payloads.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Mapping, Optional

from models import AdminAuditLog
from sqlalchemy.orm import Session

from supabase_auth import AdminUser

logger = logging.getLogger(__name__)


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


def record_admin_action(
    db: Session,
    *,
    actor: AdminUser,
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    payload: Optional[Mapping[str, Any]] = None,
) -> None:
    """
    Append a row to ``admin_audit_log``.

    Opens a *separate* short-lived ``SessionLocal()`` to write the row
    so the audit write is fully decoupled from the caller's session:

      * If the caller's transaction later rolls back, the audit row
        still persists. We want a record that the admin attempted /
        completed the action.
      * Conversely, a failure here can't poison the caller's pending
        work. The failure is swallowed and logged with a fixed message rather
        than exception details; the underlying admin action already happened, and
        failing the request because we couldn't audit it would be a
        worse outcome than a missing log row.

    The ``db`` parameter is kept in the signature so callers don't
    need to know we manage our own session — it's intentionally
    unused at the moment but reserved for a future flag like
    ``share_session=True``.
    """
    # Local import to avoid a circular at module-load time
    # (utils.audit ← models ← database, and we'd hit it from there).
    from database import SessionLocal

    del db  # explicitly unused — see docstring
    audit_db: Optional[Session] = None
    try:
        audit_db = SessionLocal()
        row = AdminAuditLog(
            actor_id=actor.id,
            actor_email=actor.email,
            action=action,
            target_type=target_type,
            target_id=target_id,
            payload=safe_audit_payload(action, payload) if payload is not None else {},
        )
        audit_db.add(row)
        audit_db.commit()
    except Exception:
        # SQLAlchemy exceptions can include the full INSERT parameters. Keep
        # failure evidence without attaching exception text, traceback or PII.
        logger.error("Failed to write admin_audit_log row")
        # Do not re-raise; see module docstring.
        if audit_db is not None:
            try:
                audit_db.rollback()
            except Exception:
                pass
    finally:
        if audit_db is not None:
            try:
                audit_db.close()
            except Exception:
                pass
