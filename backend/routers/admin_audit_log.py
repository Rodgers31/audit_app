"""Private, bounded read access to recorded administrator evidence."""
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import re

from database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from models import AdminAuditLog
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, func, text as sql_text
from sqlalchemy.orm import Session

from supabase_auth import require_admin
from utils.audit import safe_audit_payload

PRIVATE = {"Cache-Control": "private, no-store", "Vary": "Authorization"}


class PrivateAuditRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def private_handler(request):
            try:
                response = await handler(request)
            except RequestValidationError:
                return JSONResponse(status_code=422, content={"detail": "Invalid audit filters."}, headers=PRIVATE)
            except HTTPException as exc:
                if exc.status_code in {401, 403}:
                    exc.detail = "Administrator access required."
                elif exc.status_code >= 500:
                    exc.detail = "Audit evidence is unavailable."
                exc.headers = {**(exc.headers or {}), **PRIVATE}
                raise
            except Exception:
                # Storage/serialization failures must not masquerade as no
                # activity or expose SQL parameters in a client response.
                return JSONResponse(status_code=503, content={"detail": "Audit evidence is unavailable."}, headers=PRIVATE)
            response.headers.update(PRIVATE)
            return response
        return private_handler


router = APIRouter(prefix="/api/v1/admin/audit-log", tags=["Admin"],
                   dependencies=[Depends(require_admin)], route_class=PrivateAuditRoute)


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
    snapshot_id: int
    as_of: datetime
    visibility_snapshot: Optional[str] = None


def utc(value: datetime) -> datetime:
    # The existing column is timestamp without timezone; its writer uses UTC.
    try:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        raise HTTPException(422, "Invalid audit timestamp.") from None


def visibility_filter(snapshot: str) -> str:
    """Validate PostgreSQL's bounded xmin:xmax:xip representation.

    Current audit writers use top-level transactions. Fail closed after XID
    epoch wrap: interpreting the column's 32-bit xmin as xid8 would lie then.
    """
    if len(snapshot) > 4096 or not re.fullmatch(r"[0-9]{1,10}:[0-9]{1,10}:(?:[0-9]{1,10}(?:,[0-9]{1,10})*)?", snapshot):
        raise HTTPException(422, "Invalid audit visibility snapshot.")
    low, high, active = snapshot.split(':')
    low, high = int(low), int(high)
    ids = [int(i) for i in active.split(',')] if active else []
    if not 3 <= low <= high < 2**32 or ids != sorted(set(ids)) or any(i < low or i >= high for i in ids):
        raise HTTPException(422, "Unsupported audit visibility snapshot.")
    return snapshot


@router.get("", response_model=AuditLogList, summary="List admin audit-log entries")
async def list_audit_log(
    actor_id: Optional[str] = Query(None, max_length=64),
    action: Optional[str] = Query(None, max_length=80),
    target_type: Optional[str] = Query(None, max_length=40),
    target_id: Optional[str] = Query(None, max_length=64),
    days: int = Query(30, ge=0, le=36500, description="Look-back days; 0 = all time"),
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    snapshot_id: Optional[int] = Query(None, ge=0, le=2**31 - 1),
    as_of: Optional[datetime] = Query(None, description="UTC snapshot time returned on the first page"),
    since: Optional[datetime] = Query(None, description="Inclusive date-range start"),
    until: Optional[datetime] = Query(None, description="Inclusive date-range end"),
    visibility_snapshot: Optional[str] = Query(None, max_length=4096),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    captured = utc(as_of) if as_of is not None else now
    if captured.year < 1970 or captured > now + timedelta(seconds=5):
        raise HTTPException(422, "Invalid audit snapshot.")
    if (snapshot_id is None) != (as_of is None):
        raise HTTPException(422, "Both snapshot fields are required together.")
    if snapshot_id is None and visibility_snapshot is not None:
        raise HTTPException(422, "All audit snapshot fields are required together.")
    postgres = db.get_bind().dialect.name == 'postgresql'
    visibility = None
    if postgres:
        if snapshot_id is not None and visibility_snapshot is None:
            raise HTTPException(422, "Refresh to obtain an audit visibility snapshot.")
        if now - captured > timedelta(minutes=15):
            raise HTTPException(422, "Audit snapshot expired. Refresh the log.")
        if visibility_snapshot is not None:
            # Validate client metadata before performing a storage read.
            visibility = visibility_filter(visibility_snapshot)
        try:
            # xmin is only safe to interpret as xid8 while the current server
            # remains in epoch zero, even when reusing an older bookmark.
            current_visibility = visibility_filter(db.execute(sql_text('SELECT pg_current_snapshot()::text')).scalar_one())
        except HTTPException:
            raise HTTPException(503, "Audit visibility evidence is unavailable.") from None
        if visibility is None:
            visibility = current_visibility
    elif visibility_snapshot is not None:
        raise HTTPException(422, "Unsupported audit visibility snapshot.")
    start = utc(since) if since is not None else None
    end = utc(until) if until is not None else None
    if start is not None and end is not None and start > end:
        raise HTTPException(422, "Invalid audit date range.")
    q = db.query(AdminAuditLog)
    if visibility is not None:
        q = q.filter(sql_text('pg_visible_in_snapshot(CAST(CAST(admin_audit_log.xmin AS text) AS xid8), CAST(:audit_visibility AS pg_snapshot))')).params(audit_visibility=visibility)
    for column, value in ((AdminAuditLog.actor_id, actor_id), (AdminAuditLog.action, action),
                          (AdminAuditLog.target_type, target_type), (AdminAuditLog.target_id, target_id)):
        if value:
            q = q.filter(column == value)
    # Timestamp plus high-water ID stabilizes both moving day windows and new
    # backdated rows across offset pages. Rows are append-only by convention.
    ceiling = snapshot_id if snapshot_id is not None else (db.query(func.max(AdminAuditLog.id)).scalar() or 0)
    q = q.filter(AdminAuditLog.id <= ceiling, AdminAuditLog.created_at <= captured.replace(tzinfo=None))
    if days > 0:
        q = q.filter(AdminAuditLog.created_at >= (captured - timedelta(days=days)).replace(tzinfo=None))
    if start is not None:
        q = q.filter(AdminAuditLog.created_at >= start.replace(tzinfo=None))
    if end is not None:
        q = q.filter(AdminAuditLog.created_at <= end.replace(tzinfo=None))
    total = q.count()
    rows = q.order_by(desc(AdminAuditLog.created_at), desc(AdminAuditLog.id)).offset((page - 1) * page_size).limit(page_size).all()
    entries = [AuditLogEntry(id=r.id, actor_id=r.actor_id, actor_email=r.actor_email,
                            action=r.action, target_type=r.target_type, target_id=r.target_id,
                            payload=safe_audit_payload(r.action, r.payload), created_at=utc(r.created_at)) for r in rows]
    return AuditLogList(entries=entries, total=total, page=page, page_size=page_size,
                        has_more=page * page_size < total, snapshot_id=ceiling, as_of=captured, visibility_snapshot=visibility)
