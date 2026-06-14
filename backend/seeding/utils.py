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
                Path("backend") / path,  # CWD is repo root
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


import re as _re

# Optional trailing sub-period marker preserves quarter / half-year /
# nine-months distinctions in the canonical label. The COB BIRR
# domains emit labels like "FY 2025/26 H1" or "FY 2024/25 Q1" — these
# need to be kept distinct from the annual "FY 2025/26" so the writer
# doesn't collide records on the same FiscalPeriod natural key.
_FY_PATTERN = _re.compile(
    r"^(?:FY\s*)?(\d{4})[/\-](\d{2,4})(?:\s+(H[12]|Q[1-4]|\d+M))?$",
    _re.IGNORECASE,
)


_SLUG_STRIP_RE = _re.compile(r"[^a-z0-9]+")
# Apostrophes (ASCII + Unicode right-single-quote) are *stripped*
# rather than replaced with a hyphen so "Murang'a" → "muranga"
# matches the canonical DB slug. Everything else non-alphanumeric
# collapses to a hyphen.
_APOSTROPHE_RE = _re.compile(r"['\u2019]")


def canonicalize_slug(slug: str) -> str:
    """Normalise an already-formed slug to canonical kebab-case.

    Use on slugs coming in from JSON fixtures or partner exports before
    you do an Entity-by-slug lookup. This is the SAFE re-canoncalisation:
    strip apostrophes, collapse non-alphanumeric runs, trim edges. It
    does NOT add or remove the ``-county`` suffix because national vs
    county entities differ and we don't want ``national-government`` to
    accidentally become ``national-government-county``.

    Idempotent — applying twice yields the same result.
    """
    if not slug:
        return ""
    deaposted = _APOSTROPHE_RE.sub("", slug.strip().lower())
    return _SLUG_STRIP_RE.sub("-", deaposted).strip("-")


def slugify_entity(name: str, *, county_suffix: bool = True) -> str:
    """Canonicalise an entity name into the slug format used in the DB.

    The ``entities`` table's ``slug`` column is kept in kebab-case with
    no punctuation — e.g. ``muranga-county``, not ``murang'a-county``.
    Callers historically did a naive ``name.lower().replace(" ", "-")``
    which produced ``murang'a-county`` for Murang'a and then failed the
    lookup, generating the "Unknown entity slug" warnings we saw every
    run.

    Rules:
      * ASCII-lowercase.
      * Apostrophes are stripped (so Murang'a → muranga, O'Brien → obrien).
      * Every other non-alphanumeric run collapses to a single hyphen
        (commas, dots, em-dashes, multi-spaces all normalise).
      * Leading / trailing hyphens trimmed.
      * Whitespace-only input returns "" (no stray ``-county`` leaks).
      * Optionally appends ``-county`` — set to False when the caller
        passes an already-fully-qualified entity name like
        "National Government".
    """
    if not name:
        return ""
    lowered = name.strip().lower()
    # Strip apostrophes BEFORE the non-alphanumeric collapse so they
    # don't leave hyphens behind.
    deaposted = _APOSTROPHE_RE.sub("", lowered)
    collapsed = _SLUG_STRIP_RE.sub("-", deaposted).strip("-")
    if not collapsed:
        return ""
    if county_suffix and not collapsed.endswith("-county"):
        collapsed = f"{collapsed}-county"
    return collapsed


def normalize_fiscal_label(raw: str) -> str:
    """Normalise any fiscal-year string to the canonical ``FY{YYYY}/{YY}`` form.

    Accepted inputs and their canonical output::

        "FY2023/24"          -> "FY2023/24"
        "FY 2024/25"         -> "FY2024/25"
        "2023/2024"          -> "FY2023/24"
        "2022/2023"          -> "FY2022/23"
        "FY2025/26"          -> "FY2025/26"

    Sub-period markers (case-insensitive) are preserved with a single
    space separator so the FiscalPeriod natural key stays distinct
    from the same FY's annual record::

        "FY 2025/26 H1"      -> "FY2025/26 H1"
        "FY2025/26 Q1"       -> "FY2025/26 Q1"
        "FY 2024/25 9M"      -> "FY2024/25 9M"

    Raises ``ValueError`` for strings that cannot be parsed.
    """
    m = _FY_PATTERN.match(raw.strip())
    if not m:
        raise ValueError(f"Cannot normalise fiscal label: {raw!r}")
    start_year = int(m.group(1))
    end_raw = m.group(2)
    end_short = int(end_raw) % 100
    base = f"FY{start_year}/{end_short:02d}"
    sub_period = m.group(3)
    if sub_period:
        return f"{base} {sub_period.upper()}"
    return base


__all__ = [
    "parse_rate_limit",
    "load_json_resource",
    "compute_hash",
    "normalize_fiscal_label",
    "slugify_entity",
    "canonicalize_slug",
]
