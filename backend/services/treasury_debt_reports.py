"""The National Treasury's Annual Public Debt Reports, discovered from its listing.

The budget page used to carry four literal links. On 2026-09-26 all four
returned 404 (issue #235): Treasury moved from WordPress to Drupal, so every
``/wp-content/uploads/...`` path died at once, and the fourth link ended in a
literal ``...pdf``. Literals also stop wherever their author stopped — the list
ended at FY2025/26 — while Treasury keeps publishing.

So the links are read off Treasury's own listing page every time the cache
expires. When the listing cannot be read, the answer is "unavailable" plus the
listing's address — never a stale list, which is how four dead links looked
authoritative for a year.
"""

from __future__ import annotations

import html as _html
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

LISTING_URL = "https://www.treasury.go.ke/annual-debt-management-reports-0"

#: "Annual Public Debt Report 2024-2025", "... 2022/2023", "... 2010-2011".
_TITLE_RE = re.compile(
    r"annual\s+public\s+debt(?:\s+management)?\s+report\D*?(\d{4})\s*[-/–]\s*(\d{2,4})",
    re.I,
)
_LINK_RE = re.compile(
    r'<a\b[^>]*\bhref="([^"]+\.pdf)"[^>]*>(.*?)</a>', re.I | re.S
)


class ListingError(RuntimeError):
    """The listing page did not contain what a listing page contains."""


def _fiscal_label(start: str, end: str) -> Optional[str]:
    y1 = int(start)
    y2 = int(end) if len(end) == 4 else int(str(y1)[:2] + end)
    if y2 != y1 + 1:
        return None
    return f"FY {y1}/{str(y2)[-2:]}"


def parse_listing(page_html: str, base_url: str = LISTING_URL) -> List[Dict[str, Any]]:
    """Every Annual Public Debt Report the page links, newest fiscal year first.

    Only anchors whose OWN text names an Annual Public Debt Report and a fiscal
    year are taken — the page also links forms and circulars. Where one fiscal
    year is linked twice, the first link on the page wins; the page lists
    newest first, as Treasury arranges it.
    """
    reports: Dict[str, Dict[str, Any]] = {}
    for href, inner in _LINK_RE.findall(page_html):
        text = " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", inner)).split())
        m = _TITLE_RE.search(text)
        if not m:
            continue
        fy = _fiscal_label(m.group(1), m.group(2))
        if fy is None or fy in reports:
            continue
        reports[fy] = {
            "fiscal_year": fy,
            "title": text,
            "url": urljoin(base_url, _html.unescape(href)),
        }
    if not reports:
        raise ListingError(
            f"{base_url} links no Annual Public Debt Report; the page has "
            "moved or changed shape"
        )
    return sorted(reports.values(), key=lambda r: r["fiscal_year"], reverse=True)


#: Success is kept for 12 hours; a failure for 10 minutes, so one blip at
#: Treasury does not hide the links for half a day. (The API's ``@cached``
#: cannot tell the two apart, which is why this has its own.)
SUCCESS_TTL_S = 12 * 3600
FAILURE_TTL_S = 600
_cache: Dict[str, Any] = {"at": 0.0, "ttl": 0, "value": None}


async def fetch_annual_debt_reports(timeout: float = 20.0) -> Dict[str, Any]:
    """The discovered list, or an explicit unavailable answer with the listing URL."""
    import time

    now = time.monotonic()
    if _cache["value"] is not None and now - _cache["at"] < _cache["ttl"]:
        return _cache["value"]
    value = await _fetch_uncached(timeout)
    _cache.update(
        at=now,
        ttl=SUCCESS_TTL_S if value["status"] == "success" else FAILURE_TTL_S,
        value=value,
    )
    return value


async def _fetch_uncached(timeout: float) -> Dict[str, Any]:
    import httpx

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (AuditGava; +https://auditgava.com)"},
        ) as client:
            resp = await client.get(LISTING_URL)
            resp.raise_for_status()
            reports = parse_listing(resp.text, str(resp.url))
    except (httpx.HTTPError, ListingError) as exc:
        return {
            "status": "unavailable",
            "reason": f"{type(exc).__name__}: {exc}"[:300],
            "listing_url": LISTING_URL,
            "reports": [],
        }
    return {
        "status": "success",
        "publisher": "The National Treasury",
        "listing_url": LISTING_URL,
        "reports": reports,
    }
