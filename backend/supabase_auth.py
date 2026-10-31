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

import json
import math
import os
import threading
import time
from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

if __package__:
    from . import supabase_admin
    from .database import get_db
    from .models import User
else:
    import supabase_admin
    from database import get_db
    from models import User

_security = HTTPBearer(auto_error=True)

# JWKS cache (process-local). The endpoint changes very rarely — when
# a new signing key is rotated in — so 1h is a safe TTL.
_jwks_cache: Optional[dict] = None
_jwks_cache_ts: float = 0.0
_JWKS_TTL_SECONDS = 3600.0
_JWKS_REFRESH_COOLDOWN_SECONDS = 30.0
_JWKS_MAX_RESPONSE_BYTES = 64 * 1024
_JWKS_READ_BUDGET_SECONDS = 5.0
_JWKS_MAX_KEYS = 20
_jwks_last_attempt_ts: Optional[float] = None
_jwks_refresh_in_flight = False
_jwks_lock = threading.Lock()
_jwks_clock = time.monotonic


def _supabase_url() -> str:
    url = os.getenv("SUPABASE_URL")
    if not url:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_URL is not configured on the server",
        )
    return url.rstrip("/")


def _read_jwks() -> dict:
    """Read identity-encoded JSON with a byte cap before parsing or publication."""
    started = _jwks_clock()

    def check_elapsed():
        if not 0 <= _jwks_clock() - started < _JWKS_READ_BUDGET_SECONDS:
            raise ValueError("Key response exceeded its elapsed budget")

    with httpx.stream(
        "GET",
        f"{_supabase_url()}/auth/v1/.well-known/jwks.json",
        timeout=5.0,
        headers={"Accept-Encoding": "identity"},
        follow_redirects=False,
    ) as response:
        response.raise_for_status()
        check_elapsed()
        if any(
            value.strip().lower() != "identity"
            for value in response.headers.get_list("content-encoding")
        ):
            raise ValueError("Encoded key response is unsupported")
        declared = response.headers.get("content-length")
        if declared is not None:
            declared = declared.strip()
            if (
                not declared.isascii()
                or not declared.isdecimal()
                or len(declared) > 10
                or int(declared) > _JWKS_MAX_RESPONSE_BYTES
            ):
                raise ValueError("Invalid key response length")
        raw = bytearray()
        for chunk in response.iter_raw():
            check_elapsed()
            if len(raw) + len(chunk) > _JWKS_MAX_RESPONSE_BYTES:
                raise ValueError("Key response is too large")
            raw.extend(chunk)
        check_elapsed()
        if declared is not None and len(raw) != int(declared):
            raise ValueError("Key response length differs")
    return _validated_jwks(json.loads(raw))


def _fetch_jwks(force_refresh: bool = False) -> dict:
    """Share one attempt budget without making followers wait for provider I/O.

    A fresh cache remains usable during refresh. Cold/expired followers refuse
    temporarily; new keys and failed-provider recovery can wait up to 30 seconds.
    """
    global _jwks_cache, _jwks_cache_ts, _jwks_last_attempt_ts
    global _jwks_refresh_in_flight
    with _jwks_lock:
        now = _jwks_clock()
        fresh = (
            _jwks_cache is not None and 0 <= now - _jwks_cache_ts < _JWKS_TTL_SECONDS
        )
        if fresh and not force_refresh:
            return _jwks_cache
        cooling_down = (
            _jwks_last_attempt_ts is not None
            and 0 <= now - _jwks_last_attempt_ts < _JWKS_REFRESH_COOLDOWN_SECONDS
        )
        if _jwks_refresh_in_flight or cooling_down:
            if fresh:
                return _jwks_cache
            # The first request owns the one permitted provider fetch. Cold
            # followers still refuse immediately, but safe readers can retry
            # after that fetch completes. A failed-provider cooldown advertises
            # its real remaining duration instead of inviting a retry storm.
            delay = 1 if _jwks_refresh_in_flight else max(
                1, math.ceil(_JWKS_REFRESH_COOLDOWN_SECONDS - (now - _jwks_last_attempt_ts))
            )
            raise HTTPException(503, "Authentication keys temporarily unavailable",
                                headers={"Retry-After": str(delay), "Cache-Control": "no-store"})
        _jwks_last_attempt_ts = now
        _jwks_refresh_in_flight = True
    try:
        document = _read_jwks()
        with _jwks_lock:
            _jwks_cache = document
            _jwks_cache_ts = _jwks_clock()
        return document
    except (httpx.HTTPError, ValueError, TypeError, RecursionError):
        # The cooldown starts at the attempted fetch, not at its failure.
        with _jwks_lock:
            remaining = max(1, math.ceil(
                _JWKS_REFRESH_COOLDOWN_SECONDS - (_jwks_clock() - _jwks_last_attempt_ts)
            ))
        raise HTTPException(
            503, "Authentication keys temporarily unavailable",
            headers={"Retry-After": str(remaining),
                     "Cache-Control": "no-store"},
        ) from None
    finally:
        with _jwks_lock:
            _jwks_refresh_in_flight = False


@dataclass
class AdminUser:
    """Minimal representation of an authenticated admin caller."""

    id: str  # Supabase user UUID (the JWT ``sub``)
    email: Optional[str]
    roles: List[str]
    session_id: Optional[str] = None


def _validated_jwks(document: object) -> dict:
    if (
        not isinstance(document, dict)
        or not isinstance(document.get("keys"), list)
        or len(document["keys"]) > _JWKS_MAX_KEYS
        or any(not isinstance(key, dict) for key in document["keys"])
    ):
        raise ValueError("Invalid JWKS key set")
    return document


def _find_signing_key(jwks: dict, kid: str) -> Optional[dict]:
    jwks = _validated_jwks(jwks)
    return next(
        (
            key
            for key in jwks["keys"]
            if isinstance(key, dict) and key.get("kid") == kid
        ),
        None,
    )


def _decode_supabase_jwt(token: str) -> dict:
    """Verify the Supabase JWT and return its claims, or raise 401."""
    if not isinstance(token, str) or len(token) > 16_384:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    try:
        unverified_header = jwt.get_unverified_header(token)
    except (PyJWTError, ValueError, TypeError, OverflowError, RecursionError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token header: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not isinstance(unverified_header, dict):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token header")
    alg = unverified_header.get("alg")
    kid = unverified_header.get("kid")
    if not isinstance(alg, str) or alg not in ("HS256", "ES256", "RS256"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unsupported token algorithm",
            headers={"WWW-Authenticate": "Bearer"},
        )

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
        except (PyJWTError, ValueError, TypeError, OverflowError, RecursionError) as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid or expired token: {e}",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Asymmetric path (ES256 / RS256). Look up the signing key by
    # ``kid`` in the JWKS, with a one-shot refresh if the cache
    # doesn't know about it yet — covers the case of a key rotation
    # happening during the cache lifetime.
    try:
        if not isinstance(kid, str) or not kid or len(kid) > 256:
            raise PyJWTError("Asymmetric tokens require a signing key ID")
        key = _find_signing_key(_fetch_jwks(), kid)
        if key is None:
            key = _find_signing_key(_fetch_jwks(force_refresh=True), kid)
        if key is None:
            raise PyJWTError("No matching signing key")

        # Select the verification algorithm from the trusted key's type, never
        # widen the policy from the token header or allow an oct key via JWKS.
        if key.get("kty") == "RSA":
            key_algorithm = "RS256"
        elif key.get("kty") == "EC" and key.get("crv") == "P-256":
            key_algorithm = "ES256"
        else:
            raise PyJWTError("Unsupported signing key type")
        if alg != key_algorithm or key.get("alg") not in (None, key_algorithm):
            raise PyJWTError("Token and signing key algorithms differ")
        if key.get("use") not in (None, "sig"):
            raise PyJWTError("Key is not intended for signatures")
        operations = key.get("key_ops")
        if operations is not None and (
            not isinstance(operations, list)
            or not all(isinstance(operation, str) for operation in operations)
            or "verify" not in operations
        ):
            raise PyJWTError("Key does not permit verification")
        # JWKS publishes verification keys only. Reject private parameters before
        # conversion so neither key type can enter a signing-only API path.
        if any(field in key for field in ("d", "p", "q", "dp", "dq", "qi", "oth")):
            raise PyJWTError("Signing key must contain public material only")
        public_key = jwt.PyJWK.from_dict(key, algorithm=key_algorithm).key
        return jwt.decode(
            token,
            public_key,
            algorithms=[key_algorithm],
            # Supabase issues tokens with ``aud=authenticated``;
            # verifying the audience guards against a token from a
            # different Supabase project being accepted.
            audience="authenticated",
        )
    except (PyJWTError, ValueError, TypeError, OverflowError, RecursionError) as e:
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
    if not isinstance(row, dict):
        return None, []
    try:
        if UUID(row.get("id")) != UUID(user_id):
            return None, []
    except (ValueError, TypeError, AttributeError):
        return None, []
    roles = row.get("roles")
    if not isinstance(roles, list) or any(
        not isinstance(role, str) or not role.strip() for role in roles
    ):
        return None, []
    email = row.get("email")
    return email if isinstance(email, str) else None, roles.copy()


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
    session_id = claims.get("session_id")
    return AdminUser(
        id=user_id,
        email=email or claims.get("email"),
        roles=roles,
        session_id=session_id if isinstance(session_id, str) else None,
    )


def require_admin(current_user: AdminUser = Depends(get_current_user)) -> AdminUser:
    """FastAPI dependency that 403s anyone without ``admin`` in roles."""
    if (
        not isinstance(current_user.roles, list)
        or any(
            not isinstance(role, str) or not role.strip() for role in current_user.roles
        )
        or "admin" not in current_user.roles
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return current_user


# Sentinel stored in users.password_hash for rows created from Supabase
# identities. Never a valid bcrypt hash, so legacy password verification
# can never succeed against it.
_SUPABASE_MANAGED_PASSWORD = "!supabase-managed"


def get_current_db_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the calling Supabase user to the local ``users`` row.

    Verifies the Bearer token against Supabase's JWKS (same path as
    ``get_current_user``), then finds — or JIT-creates — the matching
    ``users`` row by email so features keyed on the integer ``users.id``
    (watchlist, alerts) work for Supabase identities.

    Replaces the legacy HS256 dependency from the deleted ``auth.py``,
    which decoded tokens with a local SECRET_KEY and expected an email
    in ``sub``. Supabase signs with asymmetric keys and puts the user
    UUID in ``sub``, so every real token failed — watchlist auth was
    effectively broken — while the hardcoded fallback secret left the
    endpoints forgeable if SECRET_KEY was ever unset.
    """
    claims = _decode_supabase_jwt(credentials.credentials)
    email = claims.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has no email claim",
        )

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        metadata = claims.get("user_metadata") or {}
        user = User(
            email=email,
            password_hash=_SUPABASE_MANAGED_PASSWORD,
            display_name=metadata.get("full_name") or metadata.get("name"),
            roles=[],
            email_verified=True,  # Supabase verified this email at sign-in
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            # Concurrent first-request race on the unique email index —
            # another worker created the row; use theirs.
            db.rollback()
            user = db.query(User).filter(User.email == email).first()
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to resolve user record",
                )
        else:
            db.refresh(user)

    if user.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )
    return user
