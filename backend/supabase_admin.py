"""
Thin client for the Supabase Auth Admin REST API.

We deliberately don't take a dependency on ``supabase-py`` for this —
the admin endpoints we need are a handful of simple REST calls and
the project doesn't otherwise use the SDK. ``httpx`` is already a
transitive dep of FastAPI, so this is zero-cost.

Auth model
----------
Every call sends two headers: ``apikey`` and
``Authorization: Bearer <key>``. Both must be the **service role key**
(not the anon key). Supabase will accept either header on its own in
some endpoints and both in others; sending both keeps things uniform.

The service role key bypasses RLS and can read/modify any user, so it
must NEVER be exposed to the browser. It is read from the environment
on first use and cached in a module-level variable.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional
from urllib.parse import quote

import httpx

_ENV_URL = "SUPABASE_URL"
_ENV_SERVICE_KEY = "SUPABASE_SERVICE_ROLE_KEY"


class SupabaseAdminError(RuntimeError):
    """Wraps non-2xx responses from the Supabase Auth Admin API."""

    def __init__(self, status_code: int, body: Any):
        super().__init__(f"Supabase admin API returned {status_code}: {body}")
        self.status_code = status_code
        self.body = body


def _config() -> tuple[str, str]:
    url = os.getenv(_ENV_URL)
    key = os.getenv(_ENV_SERVICE_KEY)
    if not url or not key:
        raise SupabaseAdminError(
            500,
            f"{_ENV_URL} and {_ENV_SERVICE_KEY} must both be set",
        )
    return url.rstrip("/"), key


def _headers() -> dict:
    _, key = _config()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _admin_url(path: str) -> str:
    base, _ = _config()
    return f"{base}/auth/v1/admin{path}"


def _rest_url(path: str) -> str:
    base, _ = _config()
    return f"{base}/rest/v1{path}"


def _request(method: str, path: str, **kwargs) -> dict:
    """Make an authenticated request to /auth/v1/admin and unwrap the JSON."""
    return _raw_request(method, _admin_url(path), **kwargs)


def _raw_request(method: str, url: str, **kwargs):
    """Make an authenticated request to an arbitrary URL and unwrap.

    Returns the parsed JSON body, or ``{}`` for empty/204 responses.
    Lists come through as lists. Raises ``SupabaseAdminError`` on
    any 4xx/5xx.
    """
    with httpx.Client(timeout=15.0) as client:
        resp = client.request(method, url, headers=_headers(), **kwargs)
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            raise SupabaseAdminError(resp.status_code, body)
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()


# ── Public API ──────────────────────────────────────────────────────────


def list_users(*, page: int = 1, per_page: int = 50) -> dict:
    """List Supabase auth users. Returns the raw {users: [...], aud, ...} payload."""
    return _request("GET", "/users", params={"page": page, "per_page": per_page})


def get_user(user_id: str) -> dict:
    """Fetch a single user by Supabase UUID."""
    return _request("GET", f"/users/{user_id}")


def update_user(user_id: str, body: dict) -> dict:
    """
    Update a user. Body fields supported by Supabase include
    ``email``, ``password``, ``email_confirm``, ``ban_duration``,
    ``app_metadata``, ``user_metadata``. Pass only the fields you
    intend to change.
    """
    return _request("PUT", f"/users/{user_id}", json=body)


def delete_user(user_id: str) -> dict:
    """Permanently delete a user. The associated ``profiles`` row
    cascades via the FK + ON DELETE CASCADE that Supabase sets up
    by default in its starter migrations."""
    return _request("DELETE", f"/users/{user_id}")


def generate_recovery_link(email: str, redirect_to: Optional[str] = None) -> dict:
    """
    Generate a password-recovery link for ``email``. Useful for the
    "send the user a reset email on their behalf" admin action.

    Returns the raw response which includes ``action_link`` (the URL
    the user would click in the email) and ``email_otp`` etc. We
    return the whole thing so callers can decide what to do — but
    the typical UX is to let Supabase email it: pass
    ``redirect_to`` and Supabase fires the email automatically.
    """
    body: dict = {"type": "recovery", "email": email}
    if redirect_to:
        body["redirect_to"] = redirect_to
    return _request("POST", "/generate_link", json=body)


# ── Profiles (REST against /rest/v1) ────────────────────────────────────
#
# ``profiles`` lives in the same Supabase project as auth.users, NOT in
# the FastAPI data DB. Querying via REST + service role keeps things on
# the right side of the project boundary.


def get_profile(user_id: str) -> Optional[dict]:
    """Fetch a single profile row by id, or return None."""
    rows = _raw_request(
        "GET",
        _rest_url(f"/profiles?select=id,email,display_name,roles,created_at&id=eq.{user_id}"),
    )
    if isinstance(rows, list) and rows:
        return rows[0]
    return None


def get_profiles(user_ids: List[str]) -> List[dict]:
    """Bulk-fetch profile rows for a list of user IDs."""
    if not user_ids:
        return []
    # Supabase PostgREST ``in`` syntax: id=in.(uuid1,uuid2,...)
    joined = ",".join(user_ids)
    rows = _raw_request(
        "GET",
        _rest_url(f"/profiles?select=id,email,display_name,roles,created_at&id=in.({joined})"),
    )
    return rows if isinstance(rows, list) else []


def update_profile_roles(user_id: str, roles: List[str]) -> dict:
    """Set ``profiles.roles`` for ``user_id``. Returns the updated row."""
    rows = _raw_request(
        "PATCH",
        _rest_url(f"/profiles?id=eq.{user_id}"),
        json={"roles": roles},
        # ``return=representation`` makes Supabase echo back the row
        # so we can reuse it to build the API response.
        headers={**_headers(), "Prefer": "return=representation"},
    )
    if isinstance(rows, list) and rows:
        return rows[0]
    raise SupabaseAdminError(404, f"No profile with id={user_id}")


def count_profiles(
    column: Optional[str] = None,
    op: Optional[str] = None,
    value: Optional[str] = None,
) -> int:
    """
    Count rows in ``profiles``, optionally filtered.

    To filter, pass ``column``/``op``/``value`` (e.g.
    ``column="roles", op="cs", value="{admin}"`` for "rows whose roles
    array contains admin", or ``column="created_at", op="gte",
    value="2026-04-25"``). The value is URL-encoded — callers must
    NOT pre-encode. Without those args, returns the unfiltered count.

    The count comes back via PostgREST's ``Content-Range`` header
    when ``Prefer: count=exact`` is set. We use GET with
    ``Range: 0-0`` rather than HEAD because (a) some Supabase
    deployments don't propagate the count headers correctly on HEAD
    responses, and (b) ``Range: 0-0`` keeps the body to a single
    row so the bandwidth cost is negligible.
    """
    base, _ = _config()
    url = _rest_url("/profiles?select=id")
    if column and op and value is not None:
        # Encode the value but leave the operator and column alone —
        # those have no special chars in practice and PostgREST is
        # picky about the ``op.value`` format.
        url += f"&{column}={op}.{quote(value, safe='')}"

    request_headers = {
        **_headers(),
        "Prefer": "count=exact",
        "Range": "0-0",
    }
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, headers=request_headers)
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            raise SupabaseAdminError(resp.status_code, body)
        cr = resp.headers.get("content-range") or ""
        if "/" in cr:
            try:
                return int(cr.split("/", 1)[1])
            except ValueError:
                pass
        return 0
