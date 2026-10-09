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
from typing import Any, Mapping, Optional

from models import AdminAuditLog
from sqlalchemy.orm import Session

from supabase_auth import AdminUser
from .audit_policy import safe_audit_payload

logger = logging.getLogger(__name__)

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
