"""Owned-database design prototype, deliberately disconnected from production.

This is not an Alembic migration. Its schema installer only accepts the owned
fixture endpoint. Activation, history sealing and restore certification remain
separate requirements; the existing product xmin guard is unchanged.
"""

from datetime import datetime, timedelta, timezone
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, text

from database import get_db
from models import AdminAuditLog
from routers.admin_audit_log import AuditLogEntry, AuditLogList, PrivateAuditRoute, utc
from supabase_auth import require_admin
from utils.audit import safe_audit_payload

CAPTURE_BODY = """BEGIN
  IF NEW.root_xid IS NOT NULL THEN
    RAISE EXCEPTION 'audit provenance is database assigned';
  END IF;
  NEW.root_xid := pg_catalog.pg_current_xact_id();
  RETURN NEW;
END"""
IMMUTABLE_BODY = """BEGIN
  RAISE EXCEPTION 'audit history is append only';
END"""
TOKEN_ID = "61100000-0000-4000-8000-000000000001"


def snapshot8(value):
    if (
        type(value) is not str
        or len(value) > 4096
        or not re.fullmatch(
            r"[0-9]{1,20}:[0-9]{1,20}:(?:[0-9]{1,20}(?:,[0-9]{1,20})*)?", value
        )
    ):
        raise HTTPException(422, "Invalid audit visibility snapshot.")
    low, high, active = value.split(":")
    low, high = int(low), int(high)
    ids = [int(i) for i in active.split(",")] if active else []
    if (
        not 3 <= low <= high <= 2**64 - 1
        or ids != sorted(set(ids))
        or any(i < low or i >= high for i in ids)
    ):
        raise HTTPException(422, "Invalid audit visibility snapshot.")
    return value


def bookmark(value):
    if type(value) is not str or len(value) > 4096:
        raise HTTPException(422, "Invalid audit visibility snapshot.")
    parts = value.split(":", 2)
    if len(parts) != 3 or parts[0] != "v2":
        raise HTTPException(422, "Refresh to obtain an audit visibility snapshot.")
    try:
        if str(UUID(parts[1])) != parts[1]:
            raise ValueError("Noncanonical scope")
    except ValueError:
        raise HTTPException(422, "Invalid audit visibility snapshot.") from None
    return parts[1], snapshot8(parts[2])


def install_owned(engine):
    url = engine.url
    if (url.host, url.port, url.database, url.username) != (
        "127.0.0.1",
        55534,
        "issue611",
        "inert",
    ):
        raise RuntimeError(
            "Prototype schema is restricted to the owned issue611 fixture"
        )
    with engine.begin() as db:
        db.execute(text("ALTER TABLE public.admin_audit_log ADD COLUMN root_xid xid8"))
        # Existing records intentionally retain NULL. No historical xid is inferred.
        db.execute(
            text(
                "CREATE TABLE public.issue611_capability (scope uuid PRIMARY KEY, ready boolean NOT NULL)"
            )
        )
        db.execute(
            text("INSERT INTO public.issue611_capability VALUES (:scope, true)"),
            {"scope": TOKEN_ID},
        )
        db.execute(
            text(
                f"CREATE FUNCTION public.issue611_capture() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$ {CAPTURE_BODY} $$"
            )
        )
        db.execute(
            text(
                f"CREATE FUNCTION public.issue611_immutable() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$ {IMMUTABLE_BODY} $$"
            )
        )
        db.execute(
            text(
                "CREATE TRIGGER issue611_capture BEFORE INSERT ON public.admin_audit_log FOR EACH ROW EXECUTE FUNCTION public.issue611_capture()"
            )
        )
        db.execute(
            text(
                "CREATE TRIGGER issue611_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON public.admin_audit_log FOR EACH STATEMENT EXECUTE FUNCTION public.issue611_immutable()"
            )
        )
        db.execute(
            text(
                "ALTER TABLE public.admin_audit_log ENABLE ALWAYS TRIGGER issue611_capture"
            )
        )
        db.execute(
            text(
                "ALTER TABLE public.admin_audit_log ENABLE ALWAYS TRIGGER issue611_immutable"
            )
        )
        db.execute(text("ALTER TABLE public.admin_audit_log ENABLE ROW LEVEL SECURITY"))
        for role in ("issue611_reader", "issue611_writer", "issue611_untrusted"):
            db.execute(
                text(
                    f"CREATE ROLE {role} LOGIN PASSWORD 'inert' NOSUPERUSER NOBYPASSRLS"
                )
            )
            db.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
        db.execute(
            text(
                "CREATE POLICY issue611_read ON public.admin_audit_log FOR SELECT TO issue611_reader, issue611_writer USING (true)"
            )
        )
        db.execute(
            text(
                "CREATE POLICY issue611_write ON public.admin_audit_log FOR INSERT TO issue611_writer WITH CHECK (true)"
            )
        )
        db.execute(
            text(
                "GRANT SELECT ON public.admin_audit_log, public.issue611_capability TO issue611_reader"
            )
        )
        db.execute(text("GRANT SELECT ON public.admin_audit_log TO issue611_writer"))
        db.execute(
            text(
                "GRANT INSERT(actor_id,actor_email,action,target_type,target_id,payload,created_at) ON public.admin_audit_log TO issue611_writer"
            )
        )
        db.execute(
            text(
                "GRANT USAGE ON SEQUENCE public.admin_audit_log_id_seq TO issue611_writer"
            )
        )
        db.execute(
            text(
                "REVOKE ALL ON public.admin_audit_log, public.issue611_capability FROM PUBLIC"
            )
        )
        db.execute(
            text(
                "REVOKE ALL ON FUNCTION public.issue611_capture(), public.issue611_immutable() FROM PUBLIC"
            )
        )


def capability(db):
    # Keep ordinary concurrent schema alterations out while validating and reading.
    db.execute(
        text(
            "LOCK TABLE public.admin_audit_log, public.issue611_capability IN ACCESS SHARE MODE"
        )
    )
    if (
        db.scalar(
            text(
                "SELECT to_regclass('admin_audit_log') = 'public.admin_audit_log'::regclass"
            )
        )
        is not True
    ):
        raise HTTPException(503, "Audit visibility evidence is unavailable.")
    role = db.execute(
        text("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")
    ).one()
    if role.rolsuper or role.rolbypassrls:
        raise HTTPException(503, "Audit visibility evidence is unavailable.")
    checks = db.execute(text("""SELECT c.relrowsecurity,
        c.relowner = (SELECT oid FROM pg_roles WHERE rolname=current_user) AS owns,
        a.atttypid = 'xid8'::regtype AND NOT a.attisdropped AS xid8,
        has_table_privilege('public.admin_audit_log','UPDATE,DELETE,TRUNCATE,TRIGGER') AS mutates,
        has_any_column_privilege('public.admin_audit_log','UPDATE') AS updates_column,
        row_security_active('public.admin_audit_log') AS rls
        FROM pg_class c JOIN pg_attribute a ON a.attrelid=c.oid AND a.attname='root_xid'
        WHERE c.oid='public.admin_audit_log'::regclass""")).one()
    if (
        not checks.relrowsecurity
        or checks.owns
        or not checks.xid8
        or checks.mutates
        or checks.updates_column
        or not checks.rls
    ):
        raise HTTPException(503, "Audit visibility evidence is unavailable.")
    policies = db.execute(
        text(
            """SELECT polname,polcmd,polpermissive,
        ARRAY(SELECT rolname::text FROM pg_roles WHERE oid=ANY(polroles) ORDER BY rolname) AS roles,
        pg_get_expr(polqual,polrelid) AS qualifier, pg_get_expr(polwithcheck,polrelid) AS checked
        FROM pg_policy WHERE polrelid='public.admin_audit_log'::regclass ORDER BY polname"""
        )
    ).all()
    if [tuple(p) for p in policies] != [
        (
            "issue611_read",
            "r",
            True,
            ["issue611_reader", "issue611_writer"],
            "true",
            None,
        ),
        ("issue611_write", "a", True, ["issue611_writer"], None, "true"),
    ]:
        raise HTTPException(503, "Audit visibility evidence is unavailable.")
    triggers = db.execute(
        text(
            """SELECT t.tgname, t.tgenabled, t.tgtype, p.prosrc, p.prosecdef, p.proconfig
        FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid
        WHERE t.tgrelid='public.admin_audit_log'::regclass AND NOT t.tgisinternal"""
        )
    ).all()
    expected = {
        "issue611_capture": (7, CAPTURE_BODY),
        "issue611_immutable": (58, IMMUTABLE_BODY),
    }
    if len(triggers) != len(expected):
        raise HTTPException(503, "Audit visibility evidence is unavailable.")
    for trigger in triggers:
        if trigger.tgname not in expected:
            raise HTTPException(503, "Audit visibility evidence is unavailable.")
        kind, body = expected[trigger.tgname]
        if (
            trigger.tgenabled != "A"
            or trigger.tgtype != kind
            or trigger.prosrc.strip() != body
            or trigger.prosecdef
            or trigger.proconfig != ["search_path=pg_catalog"]
        ):
            raise HTTPException(503, "Audit visibility evidence is unavailable.")
    rows = db.execute(
        text("SELECT scope::text,ready FROM public.issue611_capability")
    ).all()
    if len(rows) != 1 or rows[0].ready is not True:
        raise HTTPException(503, "Audit visibility evidence is unavailable.")
    # This prototype has no certified legacy seal. It refuses the whole dataset,
    # rather than omitting unknown rows and reporting a successful empty result.
    if (
        db.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM public.admin_audit_log WHERE root_xid IS NULL)"
            )
        )
        is not False
    ):
        raise HTTPException(503, "Audit visibility evidence is unavailable.")
    return rows[0].scope


router = APIRouter(
    prefix="/api/v1/admin/audit-log",
    dependencies=[Depends(require_admin)],
    route_class=PrivateAuditRoute,
)


@router.get("", response_model=AuditLogList)
async def read(
    actor_id: str | None = Query(None, max_length=64),
    action: str | None = Query(None, max_length=80),
    target_type: str | None = Query(None, max_length=40),
    target_id: str | None = Query(None, max_length=64),
    days: int = Query(30, ge=0, le=36500),
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    snapshot_id: int | None = Query(None, ge=0, le=2**31 - 1),
    as_of: datetime | None = None,
    visibility_snapshot: str | None = Query(None, max_length=4096),
    since: datetime | None = None,
    until: datetime | None = None,
    db=Depends(get_db),
):
    now = datetime.now(timezone.utc)
    captured = utc(as_of) if as_of is not None else now
    if captured.year < 1970 or captured > now + timedelta(seconds=5):
        raise HTTPException(422, "Invalid audit snapshot.")
    if now - captured > timedelta(minutes=15):
        raise HTTPException(422, "Audit snapshot expired. Refresh the log.")
    fields = [
        snapshot_id is not None,
        as_of is not None,
        visibility_snapshot is not None,
    ]
    if any(fields) and not all(fields):
        raise HTTPException(422, "All audit snapshot fields are required together.")
    supplied = (
        bookmark(visibility_snapshot) if visibility_snapshot is not None else None
    )
    start, end = utc(since) if since is not None else None, (
        utc(until) if until is not None else None
    )
    if start is not None and end is not None and start > end:
        raise HTTPException(422, "Invalid audit date range.")
    scope = capability(db)
    current = snapshot8(db.scalar(text("SELECT pg_current_snapshot()::text")))
    if supplied and supplied[0] != scope:
        raise HTTPException(422, "Audit snapshot changed. Refresh the log.")
    visible = supplied[1] if supplied else current
    if int(visible.split(":")[1]) > int(current.split(":")[1]):
        raise HTTPException(422, "Audit snapshot changed. Refresh the log.")
    q = (
        db.query(AdminAuditLog)
        .filter(
            text(
                "pg_visible_in_snapshot(public.admin_audit_log.root_xid, CAST(:visible AS pg_snapshot))"
            )
        )
        .params(visible=visible)
    )
    ceiling = (
        snapshot_id
        if snapshot_id is not None
        else (q.with_entities(func.max(AdminAuditLog.id)).scalar() or 0)
    )
    q = q.filter(
        AdminAuditLog.id <= ceiling,
        AdminAuditLog.created_at <= captured.replace(tzinfo=None),
    )
    for column, value in (
        (AdminAuditLog.actor_id, actor_id),
        (AdminAuditLog.action, action),
        (AdminAuditLog.target_type, target_type),
        (AdminAuditLog.target_id, target_id),
    ):
        if value:
            q = q.filter(column == value)
    if days:
        q = q.filter(
            AdminAuditLog.created_at
            >= (captured - timedelta(days=days)).replace(tzinfo=None)
        )
    if start is not None:
        q = q.filter(AdminAuditLog.created_at >= start.replace(tzinfo=None))
    if end is not None:
        q = q.filter(AdminAuditLog.created_at <= end.replace(tzinfo=None))
    total = q.count()
    rows = (
        q.order_by(desc(AdminAuditLog.created_at), desc(AdminAuditLog.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return AuditLogList(
        entries=[
            AuditLogEntry(
                id=r.id,
                actor_id=r.actor_id,
                actor_email=r.actor_email,
                action=r.action,
                target_type=r.target_type,
                target_id=r.target_id,
                payload=safe_audit_payload(r.action, r.payload),
                created_at=utc(r.created_at),
            )
            for r in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        has_more=page * page_size < total,
        snapshot_id=ceiling,
        as_of=captured,
        visibility_snapshot=f"v2:{scope}:{visible}",
    )
