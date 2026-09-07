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

    from ...freshness import mark_live, mark_fixture, mark_refused
    mark_live("national_budget", detail="COB NG-BIRR FY2025/26 9M")
    mark_fixture("national_budget", reason="pdf_download_timeout")
    mark_refused("national_debt", reason="external_register_incomplete")

A domain that REFUSES to publish must say so before it raises. Raising first
and recording nothing leaves the mode at ``unknown``, which the nightly then
renders as a fixture that was never served — see :data:`REFUSED`.

The value is per-domain and per-process, reset at the start of each domain
run by the CLI.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Dict, Optional

logger = logging.getLogger("seeding.freshness")

# mode ∈ {"live", "fixture", "partial", "refused", "unknown"}
# Every constant below must appear here. This comment spent the whole life of
# `partial` claiming three modes, which is most of why the fifth one nearly
# went missing too; test_staleness_gates.py pins it against the constants.
_SOURCE_MODE: ContextVar[Dict[str, dict]] = ContextVar("seeding_source_mode")

LIVE = "live"
FIXTURE = "fixture"
# Reached the publisher for a SECONDARY series while the figure this domain
# actually publishes stayed on the fixture. Added after review on PR #136:
# revenue_by_source recorded LIVE when only the World Bank headline totals
# refreshed, while the PAYE/VAT/Corporation/Excise/Customs breakdown — the
# thing the domain exists to publish — was still the git-tracked file. The
# staleness gate keys on the mode and never reads the detail, so that run
# reported OK and would have gone on reporting OK indefinitely.
PARTIAL = "partial"
# The domain reached a verdict of "do not publish" and wrote NOTHING. The
# reader sees the PREVIOUS seed's rows; no fixture was served, and no fixture
# will be. Added after #178 gave national_debt a refuse-rather-than-publish
# path: when the IDS creditor pull is quarantined the fetcher raises rather
# than serve the fixture's external rows, which would put a 13.34T headline
# on the page against the register's 12.22T.
#
# It has to be distinct from both of its neighbours:
#
# * not ``FIXTURE`` — nothing was served from a file, so the fixture prose
#   ("served from a FIXTURE in all N recent run(s)") is simply untrue. Reusing
#   ``mark_fixture(reason=...)`` to make the gate's message read better would
#   write a false statement into the provenance record, on a project whose
#   whole thesis is that the provenance record is true.
# * not ``UNKNOWN`` — the run knows exactly what happened and why. "We don't
#   know" is the one thing this is not.
#
# Not national_debt-specific. Any domain that grows a refuse path records it
# here rather than inventing a local convention.
REFUSED = "refused"
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


def mark_partial(
    domain: str, *, reason: str, detail: Optional[str] = None
) -> None:
    """Record that the publisher was reached, but NOT for the headline figure.

    Use this wherever a run refreshes a supporting series while the domain's
    published figure stays on a fixture. It is deliberately NOT ``mark_live``:
    ``is_stale`` returns True and the nightly reports WARN, so a permanently
    unavailable primary source cannot hide behind a working secondary one.
    """
    _store()[domain] = {"mode": PARTIAL, "reason": reason, "detail": detail}
    logger.warning(
        "%s: data source = PARTIAL (reason=%s). A secondary series refreshed "
        "from the publisher, but the figure this domain publishes is still a "
        "fixture. %s",
        domain,
        reason,
        detail or "",
    )


def mark_refused(
    domain: str, *, reason: str, detail: Optional[str] = None
) -> None:
    """Record that this run REFUSED to publish, and why.

    Call this immediately before raising, not after. A domain that raises
    first records no mode at all, so ``get()`` answers ``unknown`` and the
    nightly's all-fixture branch describes a fixture that was never served
    while reporting the reason as "unrecorded" — even though the reason is
    sitting in ``job.errors``.

    ``reason`` is a short machine-readable slug naming the gate that refused
    (``external_register_incomplete``); ``detail`` carries the specific cause
    an operator has to go and fix (``IDS creditor replacement did not apply
    (returned_no_creditors)``). Both reach the job row via ``cli.py`` and the
    gate prints them.

    ``is_stale`` is True, as for every non-LIVE mode: nothing new was
    published, so the reader is looking at older data either way.
    """
    _store()[domain] = {"mode": REFUSED, "reason": reason, "detail": detail}
    logger.error(
        "%s: data source = REFUSED (reason=%s). This run published NOTHING "
        "and wrote NOTHING — not a fixture, not a partial register. The "
        "PREVIOUS seed's rows still stand and are what a reader sees. %s",
        domain,
        reason,
        detail or "",
    )


def get(domain: str) -> dict:
    """Recorded provenance for ``domain``; ``mode='unknown'`` if never set."""
    return _store().get(domain, {"mode": UNKNOWN})


def is_stale(domain: str) -> bool:
    """True unless the run refreshed the figure this domain publishes.

    PARTIAL counts as stale on purpose: reaching the publisher for something
    else is not the same as publishing fresh data. So does REFUSED, for the
    plainer reason that a refused run wrote nothing at all.
    """
    return get(domain).get("mode") != LIVE


__all__ = [
    "FIXTURE",
    "LIVE",
    "PARTIAL",
    "REFUSED",
    "UNKNOWN",
    "get",
    "is_stale",
    "mark_fixture",
    "mark_live",
    "mark_partial",
    "mark_refused",
    "reset",
]
