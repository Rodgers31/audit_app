"""Exact declared Meta subject binding, without provider or persistence authority."""
from __future__ import annotations

from dataclasses import dataclass, field
import hmac
import re
from typing import Literal
from uuid import UUID

from .signed_requests import VerifiedSignedRequest, _identity, _timestamp


@dataclass(frozen=True, slots=True)
class DeclaredCredentialOwnership:
    """Server-supplied inspection declaration; matching does not authenticate it."""

    app_id: str = field(repr=False)
    app_scoped_user_id: str = field(repr=False)
    credential_id: UUID = field(repr=False)
    credential_version: int = field(repr=False)


@dataclass(frozen=True, slots=True)
class DeclaredOwnershipBinding:
    status: Literal["declared_match", "unverified"]
    credential_id: UUID | None = field(default=None, repr=False)
    credential_version: int | None = None
    provider_verification_performed: Literal[False] = field(default=False, init=False)


def _credential(identifier, version) -> bool:
    return (type(identifier) is UUID and type(identifier.int) is int and 0 < identifier.int < 2**128
            and type(version) is int and 0 < version <= 2**63 - 1)


def _request_shape(request) -> bool:
    if (type(request) is not VerifiedSignedRequest or not _identity(request.app_id)
            or not _identity(request.app_scoped_user_id) or type(request.payload_fingerprint) is not str
            or re.fullmatch(r"[0-9a-f]{64}", request.payload_fingerprint) is None):
        return False
    if any(value is not None and not _timestamp(value) for value in (request.issued_at, request.expires_at)):
        return False
    return not (request.issued_at is not None and request.expires_at is not None and request.expires_at < request.issued_at)


def bind_declared_ownership(request: VerifiedSignedRequest, declaration: DeclaredCredentialOwnership | None,
        *, expected_app_id: str, expected_credential_id: UUID, expected_credential_version: int) -> DeclaredOwnershipBinding:
    """Compare exact supplied identities; missing/legacy/malformed inputs fail closed.

    This helper makes no token inspection, lookup, migration or callback call.
    It neither upgrades a legacy grant nor establishes that a declaration came
    from Meta. Its result is never permission to delete data or dispatch work.
    """
    try:
        if (not _request_shape(request) or type(declaration) is not DeclaredCredentialOwnership
                or not _identity(expected_app_id) or not _identity(declaration.app_id)
                or not _identity(declaration.app_scoped_user_id)
                or not _credential(expected_credential_id, expected_credential_version)
                or not _credential(declaration.credential_id, declaration.credential_version)):
            return DeclaredOwnershipBinding("unverified")
        if (not hmac.compare_digest(request.app_id, expected_app_id)
                or not hmac.compare_digest(declaration.app_id, expected_app_id)
                or not hmac.compare_digest(request.app_scoped_user_id, declaration.app_scoped_user_id)
                or declaration.credential_id != expected_credential_id
                or declaration.credential_version != expected_credential_version):
            return DeclaredOwnershipBinding("unverified")
    except (AttributeError, TypeError, ValueError):
        return DeclaredOwnershipBinding("unverified")
    return DeclaredOwnershipBinding("declared_match", expected_credential_id, expected_credential_version)
