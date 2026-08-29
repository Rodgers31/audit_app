"""Where did this domain's data actually come from — live source, or fixture?

WHY THIS EXISTS
---------------
Every nightly run reported ``[OK]`` for months while three domains persisted
nothing. Traced 2026-08-29, the mechanism was:

    live fetch fails (slow CDN / parser drop)
        -> silent fall back to a git-tracked JSON fixture
        -> fixture is byte-identical to what is already in the table
        -> 0 created, 0 updated
        -> status "completed"
        -> "[OK] national_budget: created=0 updated=0 processed=20"

Nothing in that chain is a lie, and nothing in it is the truth either: a
domain serving a frozen file from the repo is indistinguishable from one
that checked the publisher and found nothing new. The fallback was logged,
but a log line is not a fact anything can gate on.

This module makes the source mode a RECORDED value, carried on the
``IngestionJob`` row, so the run summary and the nightly validation can both
see it. `no-silent-fallbacks`: the fallback stays (it is the right
behaviour), but it can no longer be silent.

Usage — fetchers call exactly one of these per run::

    from ...freshness import mark_live, mark_fixture
    mark_live("national_budget", detail="COB NG-BIRR FY2025/26 9M")
    mark_fixture("national_budget", reason="pdf_download_timeout")

The value is per-domain and per-process, reset at the start of each domain
run by the CLI.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Dict, Optional

logger = logging.getLogger("seeding.freshness")

# mode ∈ {"live", "fixture", "unknown"}
_SOURCE_MODE: ContextVar[Dict[str, dict]] = ContextVar("seeding_source_mode")

LIVE = "live"
FIXTURE = "fixture"
UNKNOWN = "unknown"


def _store() -> Dict[str, dict]:
    try:
        return _SOURCE_MODE.get()
    except LookupError:
        store: Dict[str, dict] = {}
        _SOURCE_MODE.set(store)
        return store


def reset(domain: str) -> None:
    """Clear any recorded mode for ``domain`` (called before each run)."""
    _store().pop(domain, None)


def mark_live(domain: str, *, detail: Optional[str] = None) -> None:
    """Record that this run's data came from the authoritative publisher."""
    _store()[domain] = {"mode": LIVE, "detail": detail}
    logger.info("%s: data source = LIVE (%s)", domain, detail or "-")


def mark_fixture(domain: str, *, reason: str, detail: Optional[str] = None) -> None:
    """Record that this run fell back to a static fixture, and why.

    ``reason`` is a short machine-readable slug (``pdf_download_timeout``,
    ``parser_returned_nothing``, ``source_unreachable``, ``no_live_source``)
    so downstream gates can branch on it rather than parsing prose.
    """
    _store()[domain] = {"mode": FIXTURE, "reason": reason, "detail": detail}
    logger.warning(
        "%s: data source = FIXTURE (reason=%s). This run published NOTHING "
        "new from the publisher; any unchanged row counts below reflect a "
        "static file, not a confirmed no-op upstream. %s",
        domain,
        reason,
        detail or "",
    )


def get(domain: str) -> dict:
    """Recorded provenance for ``domain``; ``mode='unknown'`` if never set."""
    return _store().get(domain, {"mode": UNKNOWN})


def is_stale(domain: str) -> bool:
    """True when the run did not reach the authoritative publisher."""
    return get(domain).get("mode") != LIVE


__all__ = [
    "FIXTURE",
    "LIVE",
    "UNKNOWN",
    "get",
    "is_stale",
    "mark_fixture",
    "mark_live",
    "reset",
]
