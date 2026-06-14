"""
Helper for writing rows to ``admin_audit_log``.

Why a helper, not a FastAPI dependency
--------------------------------------
A dependency would record the action at request *start*, before we
know whether the action succeeded. That produces noisy logs of
attempted-but-failed mutations and forces every endpoint to either
add a "rollback this audit row" path on failure or accept the
inaccuracy.

Calling ``record_admin_action`` explicitly *after* the action
succeeds keeps the log honest: every row in ``admin_audit_log``
represents a mutation that actually committed.

Failures are swallowed
----------------------
A failure to write the audit log must never roll back the
underlying admin action. The action already happened — failing the
request would be a worse outcome than a missing log row. We log the
exception to the application logger so a missing-audit incident is
still investigable.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from models import AdminAuditLog
from sqlalchemy.orm import Session

from supabase_auth import AdminUser

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
        work. The exception is swallowed and logged rather than
        re-raised; the underlying admin action already happened, and
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
            payload=dict(payload) if payload else {},
        )
        audit_db.add(row)
        audit_db.commit()
    except Exception:
        logger.exception(
            "Failed to write admin_audit_log row",
            extra={
                "actor_id": actor.id,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
            },
        )
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
