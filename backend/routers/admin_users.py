"""
Admin user-management API.

Backs /admin/users in the frontend. Combines two data sources:

  - Supabase ``auth.users`` (via the Auth Admin REST API) — authoritative
    for identity (email, last_sign_in_at, banned_until, etc.) and for
    destructive operations (delete, ban, send-reset).
  - Our own ``profiles`` table (via SQLAlchemy / raw SQL) — owns the
    application-level ``roles`` array that the frontend reads.

A "user" in this API is the union of those two records. List/detail
endpoints return both halves; mutations write to whichever side owns
the field being changed (roles → profiles, ban/delete/email → auth).

Every mutation records a row in ``admin_audit_log`` via
``record_admin_action``.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

import supabase_admin
from supabase_auth import AdminUser, require_admin
from utils.audit import record_admin_action

router = APIRouter(
    prefix="/api/v1/admin/users",
    tags=["Admin"],
    dependencies=[Depends(require_admin)],
)


# ── Response models ─────────────────────────────────────────────────────


class AdminUserSummary(BaseModel):
    id: str
    email: Optional[str]
    display_name: Optional[str]
    roles: List[str]
    created_at: Optional[datetime]
    last_sign_in_at: Optional[datetime]
    email_confirmed: bool
    banned_until: Optional[datetime]


class AdminUserList(BaseModel):
    users: List[AdminUserSummary]
    total: int
    page: int
    page_size: int
    has_more: bool


class AdminUserDetail(AdminUserSummary):
    app_metadata: dict
    user_metadata: dict
    updated_at: Optional[datetime]


class AdminUserStats(BaseModel):
    total_users: int
    admin_users: int
    new_last_7_days: int
    new_last_30_days: int


class UpdateRolesBody(BaseModel):
    roles: List[str]


class SendResetBody(BaseModel):
    redirect_to: Optional[str] = None


# ── Helpers ─────────────────────────────────────────────────────────────


def _parse_iso(value) -> Optional[datetime]:
    """Best-effort ISO-8601 parse that tolerates Supabase's ``Z`` and
    fractional-second variations. Returns ``None`` for falsy inputs."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        # Supabase returns timestamps with trailing ``Z``; fromisoformat
        # only handles ``+00:00`` until Python 3.11+.
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _profile_map(user_ids: List[str]) -> dict:
    """Bulk-load profiles via the Supabase REST API. Returns id → row dict.

    Profiles live in the auth Supabase project, which may not be the
    same project as the FastAPI backend's SQLAlchemy DB — REST keeps
    this project-agnostic.
    """
    if not user_ids:
        return {}
    rows = supabase_admin.get_profiles(user_ids)
    return {
        str(r.get("id")): {
            "display_name": r.get("display_name"),
            "roles": list(r.get("roles") or []),
        }
        for r in rows
    }


def _to_summary(auth_user: dict, profile: Optional[dict]) -> AdminUserSummary:
    return AdminUserSummary(
        id=auth_user["id"],
        email=auth_user.get("email"),
        display_name=(profile or {}).get("display_name"),
        roles=(profile or {}).get("roles") or [],
        created_at=_parse_iso(auth_user.get("created_at")),
        last_sign_in_at=_parse_iso(auth_user.get("last_sign_in_at")),
        email_confirmed=bool(auth_user.get("email_confirmed_at")),
        banned_until=_parse_iso(auth_user.get("banned_until")),
    )


# ── Endpoints ───────────────────────────────────────────────────────────


@router.get("", response_model=AdminUserList, summary="List users")
async def list_users(
    q: Optional[str] = Query(None, description="Case-insensitive substring match on email"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    List all users with pagination.

    Note on filtering: the Supabase admin API doesn't expose a search
    parameter, so we paginate through it as-is and filter the
    returned page by email substring on our side. For ``q`` to be
    useful at scale we'd switch to querying ``profiles`` directly
    (which lives in our DB) and join Supabase for the auth bits —
    but for our user count that's premature.
    """
    sb = supabase_admin.list_users(page=page, per_page=page_size)
    raw = sb.get("users", []) or []
    if q:
        needle = q.lower().strip()
        raw = [u for u in raw if needle in (u.get("email") or "").lower()]

    profiles = _profile_map([u["id"] for u in raw])
    users = [_to_summary(u, profiles.get(u["id"])) for u in raw]

    # Supabase's list endpoint doesn't include a total — derive a usable
    # one from page-fullness. ``has_more`` is reliable; ``total`` is a
    # lower bound in the worst case.
    has_more = len(sb.get("users", []) or []) >= page_size
    total = (page - 1) * page_size + len(users) + (page_size if has_more else 0)

    return AdminUserList(
        users=users,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


@router.get("/stats", response_model=AdminUserStats, summary="User stats summary")
async def user_stats():
    """
    Aggregate counts for the admin overview card.

    Counts come from the ``profiles`` table in the auth Supabase
    project — queried via REST so we don't need a SQLAlchemy session
    bound to that project's DB. PostgREST returns the count via the
    ``Content-Range`` header when ``Prefer: count=exact`` is set.
    """
    today = datetime.now(timezone.utc).date()
    # Date-only cutoffs (no ``T``, no ``:``, no ``+``) keep the
    # PostgREST URL clean. Supabase compares timestamps against the
    # date as ``YYYY-MM-DD 00:00:00 UTC``, which is the right
    # granularity for "users created in the last N days".
    cutoff_7 = (today - timedelta(days=7)).isoformat()
    cutoff_30 = (today - timedelta(days=30)).isoformat()

    try:
        total = supabase_admin.count_profiles()
        admins = supabase_admin.count_profiles(
            column="roles", op="cs", value="{admin}"
        )
        new_7 = supabase_admin.count_profiles(
            column="created_at", op="gte", value=cutoff_7
        )
        new_30 = supabase_admin.count_profiles(
            column="created_at", op="gte", value=cutoff_30
        )
    except supabase_admin.SupabaseAdminError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e.body))

    return AdminUserStats(
        total_users=total,
        admin_users=admins,
        new_last_7_days=new_7,
        new_last_30_days=new_30,
    )


@router.get("/{user_id}", response_model=AdminUserDetail, summary="Get user details")
async def get_user(user_id: str):
    try:
        auth_user = supabase_admin.get_user(user_id)
    except supabase_admin.SupabaseAdminError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e.body))

    profiles = _profile_map([user_id])
    summary = _to_summary(auth_user, profiles.get(user_id))

    return AdminUserDetail(
        **summary.model_dump(),
        app_metadata=auth_user.get("app_metadata") or {},
        user_metadata=auth_user.get("user_metadata") or {},
        updated_at=_parse_iso(auth_user.get("updated_at")),
    )


@router.patch(
    "/{user_id}/roles",
    response_model=AdminUserDetail,
    summary="Update user roles (profiles.roles)",
)
async def update_user_roles(
    user_id: str,
    body: UpdateRolesBody,
    actor: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Replaces ``profiles.roles`` for the given user with ``body.roles``.

    Guardrail: an admin cannot remove their *own* admin role — that
    would lock them out of the admin UI. Use a separate admin
    account if you really mean to demote yourself.
    """
    new_roles = list({r.strip() for r in body.roles if r and r.strip()})

    if user_id == actor.id and "admin" not in new_roles:
        raise HTTPException(
            status_code=400,
            detail="You cannot remove the admin role from yourself.",
        )

    old_profile = supabase_admin.get_profile(user_id)
    if old_profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    old_roles = list(old_profile.get("roles") or [])

    try:
        supabase_admin.update_profile_roles(user_id, new_roles)
    except supabase_admin.SupabaseAdminError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e.body))

    record_admin_action(
        db,
        actor=actor,
        action="users.update_roles",
        target_type="user",
        target_id=user_id,
        payload={"old": old_roles, "new": new_roles},
    )

    return await get_user(user_id)


@router.delete("/{user_id}", summary="Delete a user")
async def delete_user(
    user_id: str,
    actor: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Permanently deletes the user from Supabase auth. The ``profiles``
    row cascades via the FK Supabase sets up by default.

    Guardrail: cannot delete yourself.
    """
    if user_id == actor.id:
        raise HTTPException(status_code=400, detail="You cannot delete yourself.")

    # Snapshot identifying info BEFORE the delete so the audit row
    # is meaningful even after the user is gone.
    try:
        snapshot = supabase_admin.get_user(user_id)
    except supabase_admin.SupabaseAdminError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e.body))

    try:
        supabase_admin.delete_user(user_id)
    except supabase_admin.SupabaseAdminError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e.body))

    record_admin_action(
        db,
        actor=actor,
        action="users.delete",
        target_type="user",
        target_id=user_id,
        payload={
            "deleted_email": snapshot.get("email"),
            "deleted_created_at": snapshot.get("created_at"),
        },
    )
    return {"ok": True}


@router.post("/{user_id}/send-reset", summary="Send password-reset email")
async def send_reset(
    user_id: str,
    body: SendResetBody,
    actor: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Triggers a password-reset email for ``user_id``. Implementation
    uses the Supabase ``generate_link`` admin endpoint with
    ``type=recovery``, which both returns the action link AND fires
    the actual email when ``redirect_to`` is passed.
    """
    try:
        u = supabase_admin.get_user(user_id)
    except supabase_admin.SupabaseAdminError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e.body))
    email = u.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="User has no email address.")

    try:
        supabase_admin.generate_recovery_link(email, redirect_to=body.redirect_to)
    except supabase_admin.SupabaseAdminError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e.body))

    record_admin_action(
        db,
        actor=actor,
        action="users.send_reset",
        target_type="user",
        target_id=user_id,
        payload={"email": email, "redirect_to": body.redirect_to},
    )
    return {"ok": True, "email": email}
