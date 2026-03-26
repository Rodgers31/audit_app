"""Shared helper utilities for the seeding package."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Tuple
from urllib.parse import unquote, urlparse

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .http_client import SeedingHttpClient


def parse_rate_limit(value: str) -> Tuple[int, float]:
    """Parse a rate limit string like '60/min' into tokens per period in seconds."""

    if not value or "/" not in value:
        raise ValueError("Rate limit must be in the form '<count>/<unit>'.")

    raw_count, raw_unit = value.split("/", maxsplit=1)
    tokens = int(raw_count.strip())
    unit = raw_unit.strip().lower()

    if unit in {"sec", "second", "seconds", "s"}:
        period_seconds = 1.0
    elif unit in {"min", "minute", "minutes", "m"}:
        period_seconds = 60.0
    elif unit in {"hour", "hours", "hr", "h"}:
        period_seconds = 3600.0
    else:
        raise ValueError(f"Unsupported rate limit unit '{raw_unit}'.")

    if tokens <= 0:
        raise ValueError("Rate limit count must be greater than zero.")

    return tokens, period_seconds


def _resolve_local_path(url: str) -> Path:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        netloc = parsed.netloc
        path = parsed.path
        if os.name == "nt":
            if netloc:
                path = f"//{netloc}{path}"
            elif path.startswith("/") and len(path) > 3 and path[2] == ":":
                path = path.lstrip("/")
        else:
            if netloc:
                # file://relative/path gets misinterpreted as netloc="relative",
                # path="/path".  Reconstruct the intended relative path instead
                # of producing an invalid "//netloc/path" UNC path on Unix.
                path = f"{netloc}{path}"
        return Path(unquote(path)).expanduser()

    return Path(unquote(url)).expanduser()


def load_json_resource(
    *,
    url: str,
    client: "SeedingHttpClient",
    logger: logging.Logger,
    label: str,
) -> Any:
    """Load JSON from an HTTP endpoint or local file path.

    Supports regular HTTP(S) URLs as well as local files via ``file://`` or direct paths.
    """

    parsed = urlparse(url)
    if parsed.scheme in {"", "file"}:
        path = _resolve_local_path(url)
        if not path.exists():
            # The path may include a "backend/" prefix while CWD is already
            # backend/, or vice-versa. Try common alternatives before failing.
            alternatives = [
                Path("backend") / path,        # CWD is repo root
                Path(str(path).removeprefix("backend/")),  # CWD is backend/
                Path(__file__).resolve().parent.parent / path,  # relative to backend/
            ]
            resolved = None
            for alt in alternatives:
                if alt.exists():
                    resolved = alt
                    break
            if resolved is None:
                raise FileNotFoundError(f"{label} fixture not found at {path!s}")
            path = resolved
        raw_bytes = path.read_bytes()
        try:
            payload = json.loads(raw_bytes.decode("utf-8"))
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(f"{label} fixture at {path!s} is not valid JSON") from exc

        logger.debug(
            "Loaded %s fixture",
            label,
            extra={"path": str(path), "bytes": len(raw_bytes)},
        )
        return payload

    response = client.get(url, raise_for_status=True)
    content_type = response.headers.get("content-type", "").lower()
    if "json" not in content_type:
        logger.warning(
            "%s payload returned non-JSON content-type",
            label.capitalize(),
            extra={"content_type": content_type, "url": url},
        )
    try:
        payload = response.json()
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f"{label} payload is not valid JSON") from exc

    logger.debug(
        "Fetched %s payload",
        label,
        extra={"url": url, "bytes": len(response.content)},
    )
    return payload


def compute_hash(payload: Any) -> str:
    """Return a deterministic SHA-256 hash for serialisable payloads."""

    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(normalized).hexdigest()


__all__ = ["parse_rate_limit", "load_json_resource", "compute_hash"]
