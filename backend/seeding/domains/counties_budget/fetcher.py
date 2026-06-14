"""Budget domain fetcher with live COB PDF integration.

Strategy (in order):
1. If counties_budget_prefer_live_source AND live_pdf_fetch_enabled,
   try to discover the latest COB County Budget Implementation Review
   Report (C-BIRR) PDF and parse it.
2. Fall back to the static fixture / configured URL.

County budget data primarily comes from the Controller of Budget (COB)
quarterly reports. Unlike national-level data, there is no free API —
the data is published in PDF reports at
https://cob.go.ke/publications/consolidated-county-budget-implementation-review-reports/
"""

from __future__ import annotations

import logging
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...cob_discovery import discover_latest_cob_pdf_url
from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from ...utils import load_json_resource, slugify_entity

logger = logging.getLogger("seeding.counties_budget.fetcher")

# COB migrated from /reports/ to /publications/ paths (2025). Order is
# significant — the consolidated page publishes the single "all counties"
# BIRR PDF that covers sectoral + aggregate breakdowns in one artefact,
# so we try that first. /county-reports/ hosts per-county PDFs (harder
# to aggregate), and the legacy /reports/ path only survives as a redirect
# for old search hits.
_COB_COUNTY_BIRR_URLS = [
    "https://cob.go.ke/publications/consolidated-county-budget-implementation-review-reports/",
    "https://cob.go.ke/publications/county-reports/",
    "https://cob.go.ke/reports/county-governments-budget-implementation-review-reports/",  # legacy
]

# April-2026: the COB landing pages sit behind a CDN that rejects the
# seeder's default `Accept: */*` with HTTP 415 and frequently reports
# 000 at the CI edge even though the origin is up. Sending a browser-
# shaped Accept header + UA makes the probe behave the same way as the
# WP REST API (which is also exposed on the same host and returns 200
# reliably). We only override per-request because the default seeder UA
# is the preferred identity for everything else.
_BROWSER_UA = (
    "Mozilla/5.0 (compatible; KenyaAuditAppSeeder/1.0; "
    "+https://github.com/Rodgers31/audit_app-)"
)
_COB_HTML_HEADERS = {
    "User-Agent": _BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
_COB_JSON_HEADERS = {
    "User-Agent": _BROWSER_UA,
    "Accept": "application/json",
}

# County/BIRR-related keywords used to filter the WP REST media feed
# (and, as a fallback, HTML anchor hrefs). Keep lowercase.
_COUNTY_PDF_KEYWORDS = (
    "county",
    "c-birr",
    "cbirr",
    "county-government",
    "county_government",
    "county-budget",
    "consolidated-county",
)


def _derive_fiscal_year_dates(fy: str) -> Tuple[Optional[str], Optional[str]]:
    """Return ISO start_date/end_date for a Kenyan fiscal-year label.

    Kenya runs FY July 1 → June 30. Accepts "2024/2025", "2024/25",
    "FY2024/25", "FY 2024-25" and similar. Returns ("2024-07-01",
    "2025-06-30") or (None, None) if the label cannot be parsed.
    """
    if not fy:
        return None, None
    m = re.search(r"(\d{4})[/\-](\d{2,4})", fy)
    if not m:
        return None, None
    start_year = int(m.group(1))
    tail = m.group(2)
    # "25" → 2025; "2025" → 2025 (idempotent).
    end_year = int(tail) if len(tail) == 4 else 2000 + int(tail)
    # Sanity: end must be start+1.
    if end_year - start_year != 1:
        return None, None
    return f"{start_year}-07-01", f"{end_year}-06-30"


def fetch_budget_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Any:
    """Retrieve the budgets dataset, trying live COB PDF first.

    Strategy:
    1. Try live PDF fetch from COB county BIRR reports page.
    2. Fall back to configured fixture/API URL.
    """
    # Strategy 1: Live PDF fetch — gated by two toggles so operators
    # can disable independently:
    #   * live_pdf_fetch_enabled — global kill-switch for all PDF
    #     scraping (CBK, Treasury, COB). Useful for offline dev.
    #   * counties_budget_prefer_live_source — domain-specific toggle
    #     added April-2026 to let us freeze the fixture output for
    #     snapshot tests even when global PDF fetching is on.
    prefer_live = getattr(settings, "counties_budget_prefer_live_source", True)
    if settings.live_pdf_fetch_enabled and prefer_live:
        try:
            payload = _fetch_from_cob_county_pdf(client, settings)
            if payload and len(payload) > 0:
                logger.info(
                    "Successfully fetched county budgets from COB PDF (%d records)",
                    len(payload) if isinstance(payload, list) else 0,
                )
                return payload
            else:
                logger.warning(
                    "COB county PDF fetch returned no budget data, "
                    "falling back to fixture"
                )
        except Exception as exc:
            logger.warning(
                "COB county PDF fetch failed, falling back to fixture: %s", exc
            )
    elif not prefer_live:
        logger.info(
            "counties_budget_prefer_live_source=False — skipping COB PDF fetch"
        )

    # Strategy 2: Fixture fallback
    logger.info("Using fixture/configured URL for county budget data")
    return load_json_resource(
        url=settings.budgets_dataset_url,
        client=client,
        logger=logger,
        label="budgets",
    )


def _fetch_from_cob_county_pdf(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Optional[List[Dict[str, Any]]]:
    """Discover and parse the latest COB county BIRR PDF.

    Discovery strategy (April-2026):
      1. **WP REST API** (preferred) — `/wp-json/wp/v2/media` returns
         structured {title, date, source_url, mime_type} records sorted
         by upload date. Single 200 request, no HTML parsing, no WAF
         Accept-header issues.
      2. **HTML landing pages** (fallback) — try each known COB BIRR
         URL with a browser-shaped Accept header so the CDN does not
         reject us with 415. Useful when the WP API is temporarily
         disabled or the PDF we want lives under a different page.

    If both fail, the caller falls back to the fixture.
    """
    # Strategy 1: WP REST API — more reliable than HTML scraping.
    pdf_url: Optional[str] = None
    try:
        pdf_url = _discover_latest_county_birr_via_wp_api(client, settings)
    except Exception as exc:
        logger.warning("COB WP REST API discovery failed: %s", exc)

    # Strategy 2: HTML landing pages with browser-shaped headers.
    if not pdf_url:
        pdf_url = _discover_latest_county_birr_via_html(client, settings)

    if not pdf_url:
        # Both strategies empty — caller falls through to fixture.
        return None

    logger.info("Downloading COB county BIRR PDF: %s", pdf_url)
    return _download_and_parse_county_pdf(client, pdf_url)


def _discover_latest_county_birr_via_wp_api(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Optional[str]:
    """Query the COB WordPress REST API for the latest county BIRR PDF.

    We can't blindly trust the API's `orderby=date&order=desc` or the
    first "county" keyword match: empirically (CI run 24901989493) it
    surfaced a 2015 single-county file as the "latest", which also
    returned 404 because the CDN no longer hosts it. So:

      1. Pull up to 100 PDFs (the API default cap).
      2. Score each candidate by specificity — the *consolidated*
         county BIRR is what we actually want, not ad-hoc single-
         county files from years ago. Stronger keywords win.
      3. Sort ourselves by (score desc, parsed date desc) to avoid
         WordPress-plugin ordering quirks.
      4. HEAD-probe each candidate in order; return the first 200.
         Skipping 404s / 4xx / 5xx means a stale link in the API
         feed no longer poisons the whole seeding run.
    """
    api_url = getattr(
        settings,
        "counties_budget_cob_wp_api_url",
        "https://cob.go.ke/wp-json/wp/v2/media"
        "?per_page=100&mime_type=application/pdf&orderby=date&order=desc",
    )
    if not api_url:
        return None

    logger.info("Querying COB WP REST API for county BIRR PDFs: %s", api_url)
    response = client.get(
        api_url, raise_for_status=True, headers=_COB_JSON_HEADERS
    )
    try:
        items = response.json()
    except Exception as exc:
        logger.warning("COB WP REST API returned non-JSON payload: %s", exc)
        return None

    if not isinstance(items, list) or not items:
        logger.warning(
            "COB WP REST API returned %d media items (expected >0)",
            len(items) if isinstance(items, list) else -1,
        )
        return None

    # Score reflects how specifically the filename/title screams "the
    # consolidated, most-recent-BIRR-for-all-counties PDF". The same
    # signal set as before is still used, but weighted — plain "county"
    # alone is a weak hint; "consolidated" + "BIRR" + a FY marker win.
    def _score(item: Dict[str, Any]) -> int:
        title = (item.get("title") or {}).get("rendered", "") or ""
        slug = item.get("slug") or ""
        source = item.get("source_url") or ""
        haystack = f"{title} {slug} {source}".lower()
        if not any(kw in haystack for kw in _COUNTY_PDF_KEYWORDS):
            return 0
        score = 1  # baseline for any county match
        if "consolidated" in haystack:
            score += 5
        if "c-birr" in haystack or "cbirr" in haystack:
            score += 3
        if "budget-implementation-review" in haystack or "birr" in haystack:
            score += 2
        # FY markers — prefer recent years strongly.
        # Matches "2024-25", "2024/25", "fy-2024-25", "fy2024-25", etc.
        fy_match = re.search(r"(20\d{2})[-/](\d{2,4})", haystack)
        if fy_match:
            score += 1
            year = int(fy_match.group(1))
            # Give very recent fiscal years an extra nudge.
            score += max(0, year - 2020)
        return score

    def _parsed_date(item: Dict[str, Any]) -> str:
        # Fall back to empty string so sort is stable for items missing
        # the field (they'll rank last).
        return item.get("date") or ""

    scored = [
        (s, _parsed_date(i), i)
        for i in items
        if isinstance(i, dict) and (s := _score(i)) > 0
    ]
    if not scored:
        logger.warning(
            "COB WP REST API returned %d PDFs but none matched county keywords",
            len(items),
        )
        return None
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)

    # Liveness probe candidates in order, skipping 404s / 4xx / 5xx.
    # Keeps the failure mode of a stale feed entry (common with the
    # COB WP-Download-Manager plugin's orphaned links) local: one bad
    # URL just moves us on to the next candidate instead of poisoning
    # the whole domain run.
    head_headers = {
        "User-Agent": _BROWSER_UA,
        "Accept": "application/pdf,*/*;q=0.8",
    }
    for score, date, item in scored[:10]:
        source_url = item.get("source_url")
        if not isinstance(source_url, str) or not source_url.lower().endswith(".pdf"):
            continue
        try:
            head = client.head(
                source_url,
                raise_for_status=False,
                headers=head_headers,
                timeout=20.0,
            )
        except Exception as exc:
            logger.info(
                "Candidate %s HEAD failed (%s); trying next",
                source_url,
                exc,
            )
            continue
        if head.status_code >= 400:
            logger.info(
                "Candidate %s returned HTTP %d; trying next",
                source_url,
                head.status_code,
            )
            continue
        title = (item.get("title") or {}).get("rendered", "")
        logger.info(
            "COB WP REST API selected BIRR PDF: %s (date=%s, score=%d, title=%r)",
            source_url,
            date,
            score,
            title,
        )
        return source_url

    # All scored candidates failed HEAD probes — this is the
    # expected state since COB migrated BIRR distribution to the
    # WordPress Download Manager plugin (~Q4 2025), which doesn't
    # surface in /wp/v2/media. The endpoint now returns ~4 unrelated
    # stale image PDFs that score above the threshold but 404 on
    # fetch. The HTML fallback handles this correctly, so demote to
    # INFO — operators only need a real warning if both strategies
    # fail (the orchestrator logs that case at the caller level).
    logger.info(
        "COB WP REST API: %d scored candidates but none passed HEAD "
        "probe (expected post-WPDM-migration; HTML fallback in use)",
        len(scored),
    )
    return None


def _discover_latest_county_birr_via_html(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Optional[str]:
    """Fallback: scrape the COB HTML landing pages for a BIRR PDF link.

    Uses browser-shaped Accept / User-Agent headers so the CDN does not
    reject us with HTTP 415 the way the default `Accept: */*` triggers.
    """
    candidate_urls: List[str] = []
    configured = getattr(settings, "counties_budget_cob_reports_url", None)
    if configured:
        candidate_urls.append(configured)
    for url in _COB_COUNTY_BIRR_URLS:
        if url not in candidate_urls:
            candidate_urls.append(url)

    html: Optional[str] = None
    page_url = candidate_urls[0] if candidate_urls else ""
    for url in candidate_urls:
        try:
            logger.info("Fetching COB county BIRR reports page: %s", url)
            # The COB CDN regularly takes ~25s to serve this page —
            # the default seeder 30s is on the edge and flaps in CI.
            response = client.get(
                url,
                raise_for_status=True,
                headers=_COB_HTML_HEADERS,
                timeout=60.0,
            )
            html = response.text
            page_url = url
            break
        except Exception as exc:
            logger.warning("COB county page unavailable at %s: %s", url, exc)

    if not html:
        logger.warning("Could not reach COB county reports at any known URL")
        return None

    pdf_url = _discover_latest_county_birr_pdf(html, page_url)
    if not pdf_url:
        logger.warning("No county BIRR PDF link found on COB reports page")
        return None
    return pdf_url


_COUNTY_BIRR_KEYWORDS = (
    "county", "c-birr", "cbirr", "county-government",
    "county_government", "county-budget", "counties",
    "consolidated-county",
)


def _discover_latest_county_birr_pdf(
    html: str, base_url: str
) -> Optional[str]:
    """Extract the most recent county BIRR PDF URL from the COB page.

    Delegates to the shared COB WPDM discovery helper. See
    ``seeding.cob_discovery`` for the WPDM anchor + legacy ``.pdf``
    fallback strategy.
    """
    return discover_latest_cob_pdf_url(
        html, base_url, keywords=_COUNTY_BIRR_KEYWORDS
    )


def _download_and_parse_county_pdf(
    client: SeedingHttpClient, pdf_url: str
) -> Optional[List[Dict[str, Any]]]:
    """Download a COB county BIRR PDF, parse it, return budget records."""
    tmp_path: Optional[Path] = None
    try:
        from ...pdf_parsers import CoBQuarterlyReportParser

        # Use a browser-shaped UA for the PDF download — the same CDN
        # rule that rejects the HTML landing with 415 can block `*/*`
        # downloads too. `Accept: application/pdf` is what real browsers
        # send on direct-PDF clicks.
        #
        # Timeout: COB BIRR PDFs are ~30-50MB and the CDN is slow —
        # measured ~45s end-to-end in production. The default seeder
        # timeout (30s) times out here, so extend to 180s for this
        # single request only.
        pdf_headers = {
            "User-Agent": _BROWSER_UA,
            "Accept": "application/pdf,*/*;q=0.8",
        }
        # Explicit phase logging — this domain stalled in CI without any
        # signal between fetch-start and job timeout, so we couldn't tell
        # whether the CDN was slow or the parser hung. The download and
        # parse lines below bracket each phase and time them so future
        # stalls point at the real culprit.
        logger.info("Starting COB county BIRR PDF download: %s", pdf_url)
        download_start = time.monotonic()
        response = client.get(
            pdf_url,
            raise_for_status=True,
            headers=pdf_headers,
            timeout=180.0,
        )
        download_elapsed = time.monotonic() - download_start

        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False, prefix="cob_county_birr_"
        ) as tmp:
            tmp.write(response.content)
            tmp_path = Path(tmp.name)

        logger.info(
            "Downloaded COB county BIRR PDF (%d bytes, %.1fs) to %s",
            len(response.content),
            download_elapsed,
            tmp_path,
        )

        logger.info("Parsing COB county BIRR PDF: %s", tmp_path)
        parse_start = time.monotonic()
        parser = CoBQuarterlyReportParser(tmp_path)
        parsed_records = parser.parse()
        parse_elapsed = time.monotonic() - parse_start
        logger.info(
            "Parsed COB county BIRR PDF (%d records, %.1fs)",
            len(parsed_records) if parsed_records else 0,
            parse_elapsed,
        )

        if not parsed_records:
            logger.warning("CoBQuarterlyReportParser returned no records")
            return None

        # Convert to the budget parser's expected schema. Three pipeline
        # invariants enforced here (silently-wrong before April-2026):
        #   * key "actual_amount" — parser.py reads that; "actual_spent"
        #     was silently dropped.
        #   * start_date / end_date — parser.py requires ISO dates and
        #     drops the record otherwise (Kenya FY = Jul 1 → Jun 30).
        #   * period_label — parser falls back to fiscal_year but we
        #     set it explicitly so the normalized label is canonical.
        budget_records: List[Dict[str, Any]] = []
        dropped_no_fy = 0
        for record in parsed_records:
            county = record.get("county", "Unknown")
            entity_slug = slugify_entity(county)
            fy = record.get("fiscal_year", "")

            start_iso, end_iso = _derive_fiscal_year_dates(fy)
            if not start_iso or not end_iso:
                dropped_no_fy += 1
                continue

            allocated = record.get("allocated", 0)
            absorbed = record.get("absorbed", 0)
            if isinstance(allocated, str):
                try:
                    allocated = float(allocated.replace(",", ""))
                except ValueError:
                    allocated = 0
            if isinstance(absorbed, str):
                try:
                    absorbed = float(absorbed.replace(",", ""))
                except ValueError:
                    absorbed = 0

            budget_records.append({
                "entity_slug": entity_slug,
                "entity": f"{county} County",
                "fiscal_year": fy,
                "period_label": fy,
                "start_date": start_iso,
                "end_date": end_iso,
                "category": record.get("category", "Total"),
                "subcategory": record.get("subcategory"),
                "allocated_amount": float(allocated),
                # IMPORTANT: parser reads "actual_amount" or "actual";
                # the old "actual_spent" key was silently dropped.
                "actual_amount": float(absorbed),
                "committed_amount": None,
                "currency": "KES",
                "source_label": (
                    f"Controller of Budget County BIRR {fy}"
                    if fy
                    else "Controller of Budget County BIRR"
                ),
                "source_url": pdf_url,
                "data_quality": "official",
                "notes": record.get("notes"),
            })

        if dropped_no_fy:
            logger.warning(
                "Dropped %d COB records with un-parseable fiscal_year label",
                dropped_no_fy,
            )

        return budget_records if budget_records else None

    except ImportError:
        logger.warning(
            "CoBQuarterlyReportParser not available — "
            "install pdfplumber for live PDF parsing"
        )
        return None
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


__all__ = ["fetch_budget_payload"]
