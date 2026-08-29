"""Find the CURRENT release of a periodically-republished document.

WHY THIS EXISTS
---------------
Several overlays were wired to a hardcoded deep link::

    treasury_brop_url = ".../2025-Budget-Review-and-Outlook-Paper-1.pdf"
    cbk_statistical_bulletin_url = None   # "auto-discovery is a planned follow-up"
    kra_revenue_url = None                # same

A hardcoded path is a time bomb: it works until the publisher issues the
next edition, then silently serves last year's document (or 404s into a
fixture fallback) with nothing to indicate the data stopped advancing.
That is the same failure shape as the frozen COB domains, just on a yearly
fuse instead of a nightly one. Two of the three were already unset, so
those overlays had simply never run.

This module discovers the newest edition from the publisher's own listing
page each run, so a new release is picked up automatically and an
unexpectedly OLD "newest" is visible rather than silent.

Ranking is by a date parsed from the link, not by page order: these listing
pages are not reliably sorted (CBK interleaves 2003 and 2025 editions).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Optional
from urllib.parse import urljoin

logger = logging.getLogger("seeding.discovery")

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

# A 4-digit year that is NOT part of a longer digit run. The lookarounds
# matter: CBK prefixes every filename with an upload hash
# ("1031256347_December 2003.pdf"), and a naive \d{4} happily matches
# "1031" inside it and dates the document to the 11th century.
_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_MONTH_YEAR_RE = re.compile(
    r"(?<![a-z])(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")"
    r"[\s\-_,]*(?:20|19)?(\d{2,4})(?!\d)",
    re.IGNORECASE,
)
_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+\.pdf)["']""", re.IGNORECASE)


@dataclass(frozen=True)
class DiscoveredDocument:
    url: str
    label: str
    published: Optional[date]
    strategy: str

    def __str__(self) -> str:
        return f"{self.label} ({self.published or 'undated'}) -> {self.url}"


def parse_document_date(text: str) -> tuple[Optional[date], str]:
    """Best-effort publication date from a filename or link text.

    Returns ``(date, strategy)``; ``(None, "none")`` when nothing parses.
    A month+year beats a bare year so "December 2025" sorts above "2025".
    """
    if not text:
        return None, "none"
    cleaned = text.replace("%20", " ")

    m = _MONTH_YEAR_RE.search(cleaned)
    if m:
        month = _MONTHS[m.group(1).lower()]
        raw_year = m.group(2)
        if len(raw_year) == 4:
            year = int(raw_year)
        else:
            # A 2-digit year: assume the current century for <= 50.
            year = 2000 + int(raw_year) if int(raw_year) <= 50 else 1900 + int(raw_year)
        if 1990 <= year <= 2100:
            return date(year, month, 1), "month_year"

    years = [int(y) for y in _YEAR_RE.findall(cleaned)]
    if years:
        # The LARGEST plausible year: Treasury names files
        # "2025-Budget-Review-and-Outlook-Paper-1.pdf" but some paths also
        # carry an older directory year.
        return date(max(years), 1, 1), "year"
    return None, "none"


def find_pdf_links(html: str, base_url: str) -> List[tuple[str, str]]:
    """Every ``.pdf`` href on the page as ``(absolute_url, raw_href)``."""
    out: List[tuple[str, str]] = []
    seen = set()
    for href in _HREF_RE.findall(html or ""):
        absolute = urljoin(base_url, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append((absolute, href))
    return out


def discover_latest_pdf(
    html: str,
    base_url: str,
    *,
    must_match: Iterable[str] = (),
    must_not_match: Iterable[str] = (),
    not_before: Optional[date] = None,
) -> Optional[DiscoveredDocument]:
    """Newest PDF on ``html`` whose URL contains all of ``must_match``.

    ``must_match`` is compared case-insensitively against the FULL URL, so a
    path segment (``/uploads/statistical_bulletin/``) is a reliable series
    filter even when individual filenames are inconsistent — CBK's older
    bulletins are named "June 2004.pdf" with no "bulletin" in them at all.

    ``not_before`` rejects candidates older than a floor, so a listing that
    has lost its recent entries fails loudly instead of quietly seeding a
    decade-old document.
    """
    must = [m.lower() for m in must_match]
    must_not = [m.lower() for m in must_not_match]

    candidates: List[DiscoveredDocument] = []
    for absolute, href in find_pdf_links(html, base_url):
        low = absolute.lower()
        if any(m not in low for m in must):
            continue
        if any(m in low for m in must_not):
            continue
        label = href.rsplit("/", 1)[-1]
        published, strategy = parse_document_date(label)
        if published is None:
            # Try the full path — some publishers date the directory.
            published, strategy = parse_document_date(absolute)
        candidates.append(
            DiscoveredDocument(absolute, label, published, strategy)
        )

    dated = [c for c in candidates if c.published is not None]
    if not dated:
        logger.warning(
            "Discovery found %d PDF(s) matching %s but none carried a "
            "parseable date; refusing to guess which is current",
            len(candidates),
            list(must_match),
        )
        return None

    dated.sort(key=lambda c: (c.published, c.url), reverse=True)
    best = dated[0]

    if not_before is not None and best.published < not_before:
        logger.warning(
            "Newest matching document is %s (published %s), older than the "
            "floor %s — treating discovery as FAILED rather than seeding a "
            "stale edition: %s",
            best.label,
            best.published,
            not_before,
            best.url,
        )
        return None

    logger.info(
        "Discovered latest document: %s (dated %s via %s, from %d candidates)",
        best.label,
        best.published,
        best.strategy,
        len(dated),
    )
    return best


__all__ = [
    "DiscoveredDocument",
    "discover_latest_pdf",
    "find_pdf_links",
    "parse_document_date",
]
