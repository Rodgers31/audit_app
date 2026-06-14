"""Shared discovery helpers for Controller of Budget (COB) PDFs.

The COB website at https://cob.go.ke distributes its Budget
Implementation Review Reports (BIRR) through the WordPress Download
Manager (WPDM) plugin. Anchors on the publications pages no longer
end in ``.pdf`` — they look like

    <a ... href="https://cob.go.ke/download/<slug>/?wpdmdl=16349">

Hitting the ``?wpdmdl=NNN`` URL streams the actual file
(``Content-Type: application/pdf``). Higher ``wpdmdl`` IDs are newer
uploads (WPDM's monotonic counter), so sorting by ID descending
gives the latest report.

Three seeding domains scrape the same family of pages:

* ``counties_budget`` — Consolidated County BIRR
* ``national_budget`` — National Government BIRR
* ``pending_bills`` — same NG-BIRR page, different keyword filter

Before this helper landed each fetcher inlined a ``[^"']*\\.pdf``
regex — which matched zero links after COB migrated to WPDM — and
silently fell back to fixture. This module centralises the
WPDM-aware pattern with the legacy ``.pdf`` fallback so all three
domains stay in sync the next time the page layout shifts.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, Optional
from urllib.parse import urljoin

logger = logging.getLogger("seeding.cob_discovery")


# Match COB WPDM anchors. The href can use either "href=" or
# "location.href=" (the legacy onclick handler form). Captures the
# full URL plus the numeric ``wpdmdl`` ID for sort-by-recency.
_WPDM_RE = re.compile(
    r"""(?:location\.href=|href=)['"]"""
    r"""(?P<url>https?://[^'"\s]+\?(?:[^'"\s]*&)?wpdmdl=(?P<id>\d+)[^'"\s]*)""",
    re.IGNORECASE,
)

# Legacy direct ``.pdf`` href — kept as a fallback for older test
# fixtures and any page that ever reverts to direct links.
_PDF_RE = re.compile(r'href=["\']([^"\']*\.pdf)["\']', re.IGNORECASE)


def discover_latest_cob_pdf_url(
    html: str,
    base_url: str,
    *,
    keywords: Iterable[str],
) -> Optional[str]:
    """Return the most recent COB PDF URL on a publications page.

    Strategy
    --------
    1. Find every WPDM ``?wpdmdl=NNN`` anchor in the HTML.
       Filter by the caller's keywords (matched case-insensitively
       against the URL string — the slug encodes the FY/period so
       keyword filtering on the URL is reliable). Sort by ID
       descending (highest = newest WPDM upload). Return the top.
    2. If no WPDM anchors are present (legacy page or test fixture),
       fall back to a direct ``[^"']*\\.pdf`` regex with the same
       keyword filter and pick the first match — preserves the
       original fetcher behaviour for offline tests.

    Returns ``None`` only when neither strategy yields a candidate;
    callers treat that as "live discovery failed, fall back to
    fixture".

    Parameters
    ----------
    html
        Raw HTML body of the COB publications page.
    base_url
        URL of the page (used to absolutise relative hrefs in the
        legacy fallback path; WPDM URLs are always absolute).
    keywords
        Substrings to match (case-insensitively) against the
        candidate URLs. Domain-specific so each fetcher keeps its own
        editorial control over which reports it picks up.
    """
    keywords_lower = [k.lower() for k in keywords]

    # ── Strategy 1: WPDM anchors ──────────────────────────────────
    wpdm_matches = [
        (int(m.group("id")), m.group("url"))
        for m in _WPDM_RE.finditer(html)
    ]
    if wpdm_matches:
        filtered = [
            (wid, url)
            for wid, url in wpdm_matches
            if any(kw in url.lower() for kw in keywords_lower)
        ]
        # Filtered list preferred; fall back to all WPDM hits if no
        # keyword survived (cheap insurance against slug-text drift).
        pool = filtered if filtered else wpdm_matches
        pool.sort(key=lambda t: t[0], reverse=True)
        chosen = pool[0][1]
        if not chosen.startswith(("http://", "https://")):
            chosen = urljoin(base_url, chosen)
        logger.debug(
            "COB WPDM discovery picked %s (from %d WPDM anchors, "
            "%d after keyword filter)",
            chosen, len(wpdm_matches), len(filtered),
        )
        return chosen

    # ── Strategy 2: legacy direct .pdf hrefs ──────────────────────
    all_pdfs = _PDF_RE.findall(html)
    if not all_pdfs:
        return None
    filtered_pdfs = [
        url for url in all_pdfs
        if any(kw in url.lower() for kw in keywords_lower)
    ]
    candidates = filtered_pdfs if filtered_pdfs else all_pdfs
    if not candidates:
        return None
    chosen = candidates[0]
    if not chosen.startswith(("http://", "https://")):
        chosen = urljoin(base_url, chosen)
    return chosen


__all__ = ["discover_latest_cob_pdf_url"]
