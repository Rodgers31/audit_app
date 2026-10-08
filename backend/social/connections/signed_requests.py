"""Offline Meta signed-request verification; no callback or freshness authority."""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import re


# Application ceilings for this prerequisite, not advertised provider limits.
MAX_SIGNED_REQUEST_BYTES = 8192
MAX_PAYLOAD_BYTES = 4096
MAX_TIMESTAMP = 253402300799
_IDENTITY = re.compile(r"[1-9][0-9]{0,63}\Z", re.ASCII)
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+={0,2}\Z", re.ASCII)
_FIELDS = frozenset({"algorithm", "user_id", "app_id", "issued_at", "expires"})


class SignedRequestError(ValueError):
    """One sanitized failure; never retain input or a decoder exception."""

    def __init__(self):
        super().__init__("Meta signed request could not be verified.")
        self.code = "SIGNED_REQUEST_INVALID"


@dataclass(frozen=True)
class VerifiedSignedRequest:
    """Ephemeral MAC result. This is not a public receipt or ownership proof."""

    app_id: str = field(repr=False)
    app_scoped_user_id: str = field(repr=False)
    payload_fingerprint: str = field(repr=False)
    issued_at: int | None = field(default=None, repr=False)
    expires_at: int | None = field(default=None, repr=False)


def _identity(value) -> bool:
    return type(value) is str and _IDENTITY.fullmatch(value) is not None


def _timestamp(value) -> bool:
    return type(value) is int and 0 < value <= MAX_TIMESTAMP


def _decode(value: str) -> bytes:
    if not _BASE64URL.fullmatch(value) or len(value.rstrip("=")) % 4 == 1:
        raise ValueError()
    if "=" in value and len(value) % 4:
        raise ValueError()
    decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    canonical = base64.urlsafe_b64encode(decoded).decode("ascii")
    if value not in (canonical, canonical.rstrip("=")):
        raise ValueError()
    return decoded


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def _reject_constant(_):
    raise ValueError()


def verify_signed_request(value: str, *, app_secret: str, expected_app_id: str) -> VerifiedSignedRequest:
    """Verify the exact encoded payload with an explicitly supplied app secret.

    Optional timestamps are structural metadata only. Old requests may verify;
    callers still need durable replay, ownership and retention decisions. No
    environment, filesystem, database or provider is consulted.
    """
    try:
        if (type(value) is not str or not 1 <= len(value) <= MAX_SIGNED_REQUEST_BYTES
                or not value.isascii() or value.count(".") != 1 or not _identity(expected_app_id)
                or type(app_secret) is not str or not 1 <= len(app_secret) <= 256
                or any(not 33 <= ord(character) <= 126 for character in app_secret)):
            raise ValueError()
        encoded_signature, encoded_payload = value.split(".")
        signature = _decode(encoded_signature)
        if len(signature) != hashlib.sha256().digest_size:
            raise ValueError()
        # Authenticity is checked before JSON interpretation; hash the original
        # encoded segment, including any canonical padding, never reserialized JSON.
        expected = hmac.digest(app_secret.encode("ascii"), encoded_payload.encode("ascii"), "sha256")
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        payload_bytes = _decode(encoded_payload)
        if not 1 <= len(payload_bytes) <= MAX_PAYLOAD_BYTES:
            raise ValueError()
        payload = json.loads(payload_bytes.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=_reject_constant)
        if (type(payload) is not dict or not {"algorithm", "user_id"} <= payload.keys()
                or not payload.keys() <= _FIELDS or payload["algorithm"] != "HMAC-SHA256"
                or not _identity(payload["user_id"])):
            raise ValueError()
        if "app_id" in payload and (not _identity(payload["app_id"]) or payload["app_id"] != expected_app_id):
            raise ValueError()
        for name in ("issued_at", "expires"):
            if name in payload and not _timestamp(payload[name]):
                raise ValueError()
        issued_at, expires_at = payload.get("issued_at"), payload.get("expires")
        if issued_at is not None and expires_at is not None and expires_at < issued_at:
            raise ValueError()
        fingerprint = hashlib.sha256(b"meta-signed-request-v1\0" + expected_app_id.encode("ascii")
            + b"\0" + encoded_payload.encode("ascii")).hexdigest()
        return VerifiedSignedRequest(expected_app_id, payload["user_id"], fingerprint, issued_at, expires_at)
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        pass
    # Raise outside the except block so even __context__ cannot expose JSON,
    # Unicode input, signature data or the original request.
    raise SignedRequestError()
