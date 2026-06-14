"""
Supabase JWT authentication for FastAPI admin endpoints.

The legacy ``backend/auth.py`` is HS256 against a local SECRET_KEY and
is no longer in use — the frontend authenticates against Supabase
directly. This module verifies the JWTs Supabase issues so that
admin endpoints have real auth (not the env-gated no-op the existing
admin routers had via ``ADMIN_API_AUTH_REQUIRED``).

How it works
------------
Modern Supabase projects sign access tokens with an asymmetric key
(ECC P-256 / ES256 by default in 2025+). The private key never leaves
Supabase; the public key is published at
``<SUPABASE_URL>/auth/v1/.well-known/jwks.json`` and we verify
against that — fetched once, cached for an hour, refreshed on a
``kid`` cache miss.

A pre-2024 project that still uses the legacy symmetric secret
(HS256, ``SUPABASE_JWT_SECRET``) is supported as a fallback: if the
token's header carries ``alg=HS256`` and the env var is set, we
verify symmetrically. New ECC-signed tokens take the JWKS path.

After verifying the signature we pull the user's ``sub`` claim
(their UUID) and query the ``profiles`` table for their ``roles``
array to authorise. The frontend's ``AuthProvider`` reads roles
from the same column, so the two stay in sync.

Why we don't trust roles in the JWT itself
------------------------------------------
Supabase's default JWT only carries a ``role`` claim of
``"authenticated"`` (the Postgres role). App-level roles like
``"admin"`` live in our own ``profiles.roles`` column. We could
mirror them into ``app_metadata`` and read from the JWT, but that
adds a write path that has to stay synchronised with the DB. One
source of truth is simpler.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import List, Optional

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

import supabase_admin

_security = HTTPBearer(auto_error=True)

# JWKS cache (process-local). The endpoint changes very rarely — when
# a new signing key is rotated in — so 1h is a safe TTL.
_jwks_cache: Optional[dict] = None
_jwks_cache_ts: float = 0.0
_JWKS_TTL_SECONDS = 3600.0


def _supabase_url() -> str:
    url = os.getenv("SUPABASE_URL")
    if not url:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_URL is not configured on the server",
        )
    return url.rstrip("/")


def _fetch_jwks(force_refresh: bool = False) -> dict:
    """Return the project's JWKS, fetching + caching as needed."""
    global _jwks_cache, _jwks_cache_ts
    now = time.time()
    if (
        not force_refresh
        and _jwks_cache is not None
        and (now - _jwks_cache_ts) < _JWKS_TTL_SECONDS
    ):
        return _jwks_cache
    try:
        resp = httpx.get(
            f"{_supabase_url()}/auth/v1/.well-known/jwks.json",
            timeout=5.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch Supabase JWKS: {e}",
        )
    _jwks_cache = resp.json()
    _jwks_cache_ts = now
    return _jwks_cache


@dataclass
class AdminUser:
    """Minimal representation of an authenticated admin caller."""

    id: str  # Supabase user UUID (the JWT ``sub``)
    email: Optional[str]
    roles: List[str]


def _decode_supabase_jwt(token: str) -> dict:
    """Verify the Supabase JWT and return its claims, or raise 401."""
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token header: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    alg = unverified_header.get("alg")
    kid = unverified_header.get("kid")

    # Legacy HS256 path: pre-asymmetric-keys projects, or projects
    # mid-migration that still issue HS256 tokens. Only taken when
    # the env var is explicitly set; otherwise we fall through to
    # JWKS which is the modern path.
    if alg == "HS256":
        legacy_secret = os.getenv("SUPABASE_JWT_SECRET")
        if not legacy_secret:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "Token uses legacy HS256 signing but SUPABASE_JWT_SECRET "
                    "is not configured on the server."
                ),
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            return jwt.decode(
                token,
                legacy_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid or expired token: {e}",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Asymmetric path (ES256 / RS256). Look up the signing key by
    # ``kid`` in the JWKS, with a one-shot refresh if the cache
    # doesn't know about it yet — covers the case of a key rotation
    # happening during the cache lifetime.
    jwks = _fetch_jwks()
    key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if key is None:
        jwks = _fetch_jwks(force_refresh=True)
        key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"No matching JWK for kid={kid}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return jwt.decode(
            token,
            key,
            # Honour the JWK's declared alg if present, otherwise fall
            # back to the token header. Defending against a token
            # specifying a weaker alg than the key was minted for.
            algorithms=[key.get("alg") or alg],
            # Supabase issues tokens with ``aud=authenticated``;
            # verifying the audience guards against a token from a
            # different Supabase project being accepted.
            audience="authenticated",
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _fetch_roles(user_id: str) -> tuple[Optional[str], List[str]]:
    """
    Look up the caller's email + roles array from ``profiles``.

    ``profiles`` lives in the auth Supabase project — which may be a
    different project from the one the FastAPI backend's SQLAlchemy
    session connects to. To stay project-agnostic we fetch via the
    Supabase REST API using the service-role key, rather than a
    direct DB query.
    """
    try:
        row = supabase_admin.get_profile(user_id)
    except supabase_admin.SupabaseAdminError:
        return None, []
    if not row:
        return None, []
    return row.get("email"), list(row.get("roles") or [])


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> AdminUser:
    """
    Resolve the calling user from the Bearer token. Raises 401 if the
    token is missing/invalid; the role lookup is best-effort and
    returns an empty roles list if the profile can't be fetched
    (which ``require_admin`` will then reject as 403).
    """
    claims = _decode_supabase_jwt(credentials.credentials)
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has no subject",
        )

    email, roles = _fetch_roles(user_id)
    return AdminUser(id=user_id, email=email or claims.get("email"), roles=roles)


def require_admin(current_user: AdminUser = Depends(get_current_user)) -> AdminUser:
    """FastAPI dependency that 403s anyone without ``admin`` in roles."""
    if "admin" not in current_user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return current_user
