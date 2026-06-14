"""
Admin audit-log API.

Read-only endpoint over the ``admin_audit_log`` table that backs the
/admin/audit-log UI. Filterable by actor, action, target, and date
range; paginated. Writes to the table are made by
``backend.utils.audit.record_admin_action`` from inside other admin
endpoints — there is intentionally no POST here.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from database import get_db
from fastapi import APIRouter, Depends, Query
from models import AdminAuditLog
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc
from sqlalchemy.orm import Session

from supabase_auth import require_admin

router = APIRouter(
    prefix="/api/v1/admin/audit-log",
    tags=["Admin"],
    dependencies=[Depends(require_admin)],
)


class AuditLogEntry(BaseModel):
    id: int
    actor_id: str
    actor_email: Optional[str]
    action: str
    target_type: Optional[str]
    target_id: Optional[str]
    payload: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogList(BaseModel):
    entries: List[AuditLogEntry]
    total: int
    page: int
    page_size: int
    has_more: bool


@router.get("", response_model=AuditLogList, summary="List admin audit-log entries")
async def list_audit_log(
    actor_id: Optional[str] = Query(None, description="Filter by actor (admin) UUID"),
    action: Optional[str] = Query(None, description="Filter by action key"),
    target_type: Optional[str] = Query(None, description="Filter by target type"),
    target_id: Optional[str] = Query(None, description="Filter by target id"),
    days: Optional[int] = Query(30, ge=0, description="Look-back window in days; 0 = all time"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(AdminAuditLog)
    if actor_id:
        q = q.filter(AdminAuditLog.actor_id == actor_id)
    if action:
        q = q.filter(AdminAuditLog.action == action)
    if target_type:
        q = q.filter(AdminAuditLog.target_type == target_type)
    if target_id:
        q = q.filter(AdminAuditLog.target_id == target_id)
    if days and days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        q = q.filter(AdminAuditLog.created_at >= cutoff)

    total = q.count()
    rows = (
        q.order_by(desc(AdminAuditLog.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return AuditLogList(
        entries=[AuditLogEntry.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )
