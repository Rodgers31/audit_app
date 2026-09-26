"""Fetch the newest COB county BIRR and parse its stalled-projects tables.

Source: the Controller of Budget's *County Governments Budget Implementation
Review Report* (CBIRR), listed at
https://cob.go.ke/publications/consolidated-county-budget-implementation-review-reports/.
The same PDF counties_budget reads; both go through
``seeding.cob_cbirr.download_cbirr`` so the ~50MB file is fetched once.

The records this domain replayed until issue #230 were invented. There is no
fixture fallback any more: when the newest edition cannot be read, the domain
refuses, writes nothing, and says why.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...freshness import mark_live, mark_refused

logger = logging.getLogger("seeding.stalled_projects")

DOMAIN = "stalled_projects"


@dataclass
class FetchResult:
    """What one run learned. ``records`` is empty unless ``ok``."""

    ok: bool
    edition: Dict[str, Any] = field(default_factory=dict)
    counties: List[Dict[str, Any]] = field(default_factory=list)
    listing_newest: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    detail: Optional[str] = None


def _refuse(reason: str, detail: str, **kw: Any) -> FetchResult:
    mark_refused(DOMAIN, reason=reason, detail=detail)
    return FetchResult(ok=False, reason=reason, detail=detail, **kw)


def _pdf_stack_versions() -> str:
    from importlib.metadata import PackageNotFoundError, version

    parts = []
    for name in ("pdfplumber", "pdfminer.six", "pypdfium2"):
        try:
            parts.append(f"{name}={version(name)}")
        except PackageNotFoundError:
            parts.append(f"{name}=unknown")
    return ";".join(parts)


def parse_edition(pdf_path: Path, settings: Any) -> List[Dict[str, Any]]:
    """Parse, reusing a cached result keyed on the PDF's bytes and this parser."""
    from ...parse_cache import parse_with_cache
    from .cob_parser import CbirrStalledProjectsParser

    parser = CbirrStalledProjectsParser(pdf_path)
    return parse_with_cache(
        pdf_path,
        cache_dir=Path(settings.cache_path) / "pdfs",
        kind="cob_cbirr_stalled_projects",
        parse_fn=parser.parse,
        enabled=getattr(settings, "parse_cache_enabled", True),
        key_extra=_pdf_stack_versions(),
    )


def _is_count(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _malformed(edition: Dict[str, Any], counties: List[Dict[str, Any]]) -> Optional[str]:
    """Why the parse output cannot be trusted, or None."""
    if not _is_count(edition.get("captions_found")):
        return f"captions_found={edition.get('captions_found')!r}"
    for c in counties:
        rec = c.get("reconciliation")
        if not isinstance(c.get("county"), str) or not isinstance(rec, dict) or not _is_count(rec.get("rows")):
            return f"county record {c.get('county')!r} has no usable reconciliation"
        for t in c.get("tables") or []:
            if t.get("as_of") is not None and not isinstance(t.get("as_of"), str):
                return f"{c['county']}: as_of={t.get('as_of')!r}"
    return None


def fetch(settings: Any, client: Any = None) -> FetchResult:
    from ... import cob_cbirr
    from ...http_client import PdfDownloadError, PdfDownloadIncomplete

    if not getattr(settings, "live_pdf_fetch_enabled", True):
        return _refuse(
            "live_pdf_fetch_disabled",
            "live_pdf_fetch_enabled is off; stalled projects have no other source",
        )

    try:
        listing_url, editions = cob_cbirr.list_cbirr_editions(client, settings)
    except Exception as exc:
        return _refuse("listing_unreachable", f"{type(exc).__name__}: {exc}"[:300])
    if not editions:
        return _refuse(
            "listing_has_no_editions",
            f"no county BIRR download link matched on {listing_url}",
        )
    newest = editions[0]
    # The fingerprint goes on the record BEFORE the download, so a re-issue
    # under the same link that fails to download is still visible to the
    # gate: same wpdmdl, different file.
    listing_newest = {
        "wpdmdl": newest.wpdmdl,
        "url": newest.url,
        "slug": newest.slug,
        "server_fingerprint": cob_cbirr.server_fingerprint(client, newest.url),
    }

    try:
        pdf = cob_cbirr.download_cbirr(client, newest.url, settings)
    except PdfDownloadIncomplete as exc:
        return _refuse(
            "download_incomplete",
            f"{exc.bytes_downloaded} bytes of {newest.url} on disk; resumes next run",
            listing_newest=listing_newest,
        )
    except PdfDownloadError as exc:
        return _refuse("download_failed", str(exc)[:300], listing_newest=listing_newest)
    except Exception as exc:
        # Disk full, a transport error outside the downloader's own handling:
        # still a refusal with a reason, never an escape that leaves the
        # run's provenance "unknown".
        return _refuse(
            "download_failed", f"{type(exc).__name__}: {exc}"[:300], listing_newest=listing_newest
        )

    try:
        records = parse_edition(pdf.path, settings)
    except Exception as exc:
        logger.exception("stalled_projects: parse of %s failed", pdf.path)
        return _refuse(
            "parse_failed", f"{type(exc).__name__}: {exc}"[:300], listing_newest=listing_newest
        )

    edition = next((r for r in records if isinstance(r, dict) and r.get("kind") == "edition"), None)
    counties = [r for r in records if isinstance(r, dict) and r.get("kind") == "county"]
    if edition is None:
        return _refuse("parse_failed", "parser returned no edition record", listing_newest=listing_newest)
    problem = _malformed(edition, counties)
    if problem:
        # The parse cache can serve an entry written by an older parser, and
        # a malformed record used to raise out of fetch() here, leaving the
        # run's provenance "unknown". Refuse with the reason instead.
        return _refuse("parse_output_invalid", problem, listing_newest=listing_newest)
    edition = dict(
        edition,
        url=newest.url,
        wpdmdl=newest.wpdmdl,
        slug=newest.slug,
        listing_url=listing_url,
        sha256=pdf.sha256,
        server_fingerprint=pdf.fingerprint,
    )
    rows = sum(c["reconciliation"]["rows"] for c in counties)
    captions = int(edition.get("captions_found") or 0)
    if captions and not rows:
        # The failure the freshness gate exists for: an edition that HAS
        # stalled-projects tables and a parser that read none of them.
        return _refuse(
            "captions_without_rows",
            f"{captions} stalled-projects caption(s) in {newest.slug}, 0 rows parsed",
            listing_newest=listing_newest,
            edition=edition,
        )
    if not captions:
        return _refuse(
            "edition_has_no_stalled_tables",
            f"no 'County Stalled Projects as of' caption in {newest.slug}",
            listing_newest=listing_newest,
            edition=edition,
        )

    statuses: Dict[str, int] = {}
    for c in counties:
        if c["reconciliation"]["rows"]:
            s = c["reconciliation"]["status"]
            statuses[s] = statuses.get(s, 0) + 1
    as_of = sorted({t["as_of"] for c in counties for t in c.get("tables", []) if t.get("as_of")})
    edition["as_of"] = as_of[-1] if as_of else None
    mark_live(
        DOMAIN,
        detail=(
            f"COB CBIRR {edition.get('fiscal_year')} {edition.get('period')} "
            f"(wpdmdl={newest.wpdmdl}, as of {edition['as_of']}): {rows} row(s) "
            f"in {sum(1 for c in counties if c['reconciliation']['rows'])} "
            f"count(y/ies) from {captions} caption(s); reconciliation "
            + ", ".join(f"{k}={v}" for k, v in sorted(statuses.items()))
        ),
    )
    return FetchResult(ok=True, edition=edition, counties=counties, listing_newest=listing_newest)
