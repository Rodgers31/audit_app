"""The Controller of Budget's county BIRR: which editions exist, and one copy.

Two domains read the same ~50MB *County Governments Budget Implementation
Review Report*: ``counties_budget`` (budget execution tables) and
``stalled_projects`` (the per-county stalled-projects tables). The PDF comes
off cob.go.ke at 43 KB/s on a bad night, so it must be fetched once and
shared. Both domains therefore call :func:`download_cbirr` with the same URL,
which probes the server's fingerprint once per process and passes it to the
shared, cross-run PDF cache — the second caller is a cache hit.

:func:`list_cbirr_editions` reads COB's listing page, newest first, so the
freshness gate can compare what the listing offers with what was ingested.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import SeedingSettings
from .http_client import SeedingHttpClient

logger = logging.getLogger("seeding.cob_cbirr")

LISTING_URL = (
    "https://cob.go.ke/publications/"
    "consolidated-county-budget-implementation-review-reports/"
)

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
PDF_HEADERS = {"User-Agent": _BROWSER_UA, "Accept": "application/pdf,*/*;q=0.8"}
HTML_HEADERS = {
    "User-Agent": _BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

#: The county BIRR's WPDM slugs all read
#: "county-governments-budget-implementation-review-report-…" (one older one
#: is prefixed "annual-"). Anything else on the page — a single-county
#: report, a circular — is not an edition.
#:
#: The link lives in an onclick handler, not the href (which is "#"):
#: ``href='#' onclick="location.href='https://cob.go.ke/download/…?wpdmdl=16482'``.
_EDITION_RE = re.compile(
    r"""(?:location\.href=|href=)['"](?P<url>https://cob\.go\.ke/download/(?P<slug>[a-z0-9-]*county-governments-budget-implementation-review-report[a-z0-9-]*)/\?wpdmdl=(?P<id>\d+)[^'"\s]*)['"]""",
    re.I,
)


@dataclass(frozen=True)
class CbirrEdition:
    url: str
    wpdmdl: int
    slug: str

    @property
    def label(self) -> str:
        return self.slug.replace("-", " ")


@dataclass(frozen=True)
class CbirrPdf:
    url: str
    path: Path
    sha256: Optional[str]
    fingerprint: Optional[str]


def parse_listing(html: str) -> List[CbirrEdition]:
    """Every county BIRR edition linked from the listing, newest first.

    Newest = highest ``wpdmdl``: WordPress Download Manager numbers uploads
    monotonically (see ``seeding/cob_discovery.py``).
    """
    seen: Dict[int, CbirrEdition] = {}
    for m in _EDITION_RE.finditer(html or ""):
        wid = int(m.group("id"))
        seen.setdefault(wid, CbirrEdition(url=m.group("url"), wpdmdl=wid, slug=m.group("slug")))
    return sorted(seen.values(), key=lambda e: e.wpdmdl, reverse=True)


def list_cbirr_editions(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Tuple[str, List[CbirrEdition]]:
    """``(listing_url, editions newest first)``. Raises if unreachable."""
    url = getattr(settings, "counties_budget_cob_reports_url", None) or LISTING_URL
    response = client.get(url, raise_for_status=True, headers=HTML_HEADERS, timeout=60.0)
    return url, parse_listing(response.text)


#: One probe per URL per process. Two domains share one cache entry only if
#: they pass the same fingerprint; probing twice could straddle a re-issue
#: and have each evict the other's 50MB download.
_FINGERPRINTS: Dict[str, Optional[str]] = {}


def server_fingerprint(client: SeedingHttpClient, url: str) -> Optional[str]:
    """What cob.go.ke says it serves at ``url`` — probed once per process."""
    from . import pdf_download

    if url not in _FINGERPRINTS:
        _FINGERPRINTS[url] = pdf_download.probe_fingerprint(client, url, headers=PDF_HEADERS)
    return _FINGERPRINTS[url]


def download_cbirr(
    client: SeedingHttpClient, url: str, settings: SeedingSettings
) -> CbirrPdf:
    """Return the CBIRR at ``url`` from the shared cache, downloading on a miss.

    Raises ``PdfDownloadError`` (including ``PdfDownloadIncomplete``, whose
    progress is kept for the next run) exactly as ``get_or_download_pdf``.
    """
    # Imported at call time so tests that patch
    # ``seeding.pdf_download.get_or_download_pdf`` see their patch here.
    from . import pdf_download

    fingerprint = server_fingerprint(client, url)
    cache_dir = Path(settings.cache_path) / "pdfs"
    path = pdf_download.get_or_download_pdf(
        client,
        url,
        cache_dir=cache_dir,
        ttl_seconds=settings.pdf_cache_ttl_seconds,
        max_seconds=settings.pdf_download_timeout_seconds,
        max_bytes=settings.pdf_download_max_bytes,
        headers=PDF_HEADERS,
        fingerprint=fingerprint,
    )
    meta = pdf_download.cached_pdf_meta(cache_dir, url)
    sha = meta.get("sha256") if isinstance(meta, dict) else None
    return CbirrPdf(url=url, path=Path(path), sha256=sha if isinstance(sha, str) else None, fingerprint=fingerprint)


__all__ = [
    "CbirrEdition",
    "CbirrPdf",
    "LISTING_URL",
    "download_cbirr",
    "list_cbirr_editions",
    "parse_listing",
    "server_fingerprint",
]
