"""Fetch national budget execution payload with live COB PDF integration.

Strategy (in order):
1. If live_pdf_fetch_enabled, try to discover the latest COB National
   Government BIRR PDF, download and parse it.
2. Fall back to the static fixture / configured URL.

National budget execution data comes from the Controller of Budget (COB)
quarterly NG-BIRR reports.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...cob_discovery import discover_latest_cob_pdf_url
from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from ...utils import load_json_resource
from ...freshness import mark_fixture, mark_live

logger = logging.getLogger("seeding.national_budget.fetcher")


def fetch_national_budget_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> list[dict[str, Any]]:
    """Fetch national budget execution, trying live COB PDF first.

    Strategy:
    1. Try live PDF fetch from COB NG-BIRR reports page.
    2. Fall back to configured fixture/API URL.
    """
    # Strategy 1: Live PDF fetch
    if settings.live_pdf_fetch_enabled:
        try:
            payload = _fetch_from_cob_ng_pdf(client, settings)
            if payload and len(payload) > 0:
                logger.info(
                    "Successfully fetched national budget from COB PDF (%d records)",
                    len(payload),
                )
                mark_live(
                    "national_budget",
                    detail=f"COB NG-BIRR PDF, {len(payload)} records",
                )
                # Filter metadata entries
                return [r for r in payload if "_metadata" not in r]
            else:
                logger.warning(
                    "COB NG-BIRR PDF fetch returned no data, "
                    "falling back to fixture"
                )
                mark_fixture(
                    "national_budget", reason="parser_returned_nothing"
                )
        except Exception as exc:
            logger.warning(
                "COB NG-BIRR PDF fetch failed, falling back to fixture: %s", exc
            )
            mark_fixture(
                "national_budget",
                reason="live_fetch_failed",
                detail=str(exc)[:200],
            )
    else:
        mark_fixture("national_budget", reason="live_pdf_fetch_disabled")

    # Strategy 2: Fixture fallback
    logger.info("Using fixture/configured URL for national budget data")
    payload = load_json_resource(
        url=settings.national_budget_execution_dataset_url,
        client=client,
        logger=logger,
        label="national_budget_execution",
    )

    if not isinstance(payload, list):
        raise ValueError("national_budget_execution payload must be a list")

    # Skip metadata entries (first element may have _metadata key)
    return [r for r in payload if "_metadata" not in r]


def _fetch_from_cob_ng_pdf(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Optional[List[Dict[str, Any]]]:
    """Discover and parse the latest COB national government BIRR PDF."""
    page_url = settings.cob_birr_page_url
    logger.info("Fetching COB NG-BIRR reports page: %s", page_url)

    response = client.get(page_url, raise_for_status=True)
    html = response.text

    pdf_url = _discover_latest_ng_birr_pdf(html, page_url)
    if not pdf_url:
        logger.warning("No NG-BIRR PDF link found on COB reports page")
        return None

    logger.info("Downloading COB NG-BIRR PDF: %s", pdf_url)
    return _download_and_parse_ng_pdf(client, pdf_url, settings)


_NG_BIRR_KEYWORDS = (
    "ng-birr", "national-government-budget",
    "national_government_budget", "birr",
    "budget-implementation", "budget_implementation",
)


def _discover_latest_ng_birr_pdf(
    html: str, base_url: str
) -> Optional[str]:
    """Extract the most recent NG-BIRR PDF URL from the COB page.

    Delegates to the shared COB WPDM discovery helper — see
    ``seeding.cob_discovery`` for why direct ``.pdf`` regex stopped
    matching after COB migrated to the WordPress Download Manager
    plugin.
    """
    return discover_latest_cob_pdf_url(
        html, base_url, keywords=_NG_BIRR_KEYWORDS
    )


def _download_and_parse_ng_pdf(
    client: SeedingHttpClient, pdf_url: str, settings: SeedingSettings
) -> Optional[List[Dict[str, Any]]]:
    """Download a COB NG-BIRR PDF, parse it, return budget execution records.

    Uses ``NgBirrSectoralParser`` which targets Tables 2.5 (Sectoral
    Development) and 2.6 (Sectoral Recurrent) — see
    ``pdf_parser.py`` for why these tables and not the older
    ``CoBQuarterlyReportParser`` (which is anchored on the 47-county
    invariant and only matches the *Consolidated County* BIRR).

    Output dicts feed ``parse_national_budget_payload``, which is why
    they include ``start_date``/``end_date`` (the writer keys
    ``BudgetLine`` on entity+period+category+subcategory).
    """
    try:
        from .pdf_parser import NgBirrSectoralParser
        from ...pdf_download import get_or_download_pdf

        # get_or_download_pdf enforces a TOTAL wall-clock cap on the transfer
        # (not httpx's per-chunk timeout, which a slow-but-steady body never
        # trips) and reuses a cached copy across runs. So a slow-CDN night
        # either reuses the last good download or bails to the fixture,
        # instead of eating the 600s domain budget and aborting mid-parse
        # (issue #119) — same guard the counties_budget domain uses.
        logger.info("Starting COB NG-BIRR PDF download: %s", pdf_url)
        download_start = time.monotonic()
        pdf_path = get_or_download_pdf(
            client,
            pdf_url,
            cache_dir=Path(settings.cache_path) / "pdfs",
            ttl_seconds=settings.pdf_cache_ttl_seconds,
            max_seconds=settings.pdf_download_timeout_seconds,
            max_bytes=settings.pdf_download_max_bytes,
        )
        download_elapsed = time.monotonic() - download_start

        logger.info(
            "COB NG-BIRR PDF ready (%d bytes, %.1fs) at %s",
            pdf_path.stat().st_size, download_elapsed, pdf_path,
        )

        parser = NgBirrSectoralParser(pdf_path)
        period, sectoral_records = parser.parse()

        if not sectoral_records:
            logger.warning("NgBirrSectoralParser returned no records")
            return None

        # Convert to the dict shape parse_national_budget_payload expects.
        # Sector aggregates: net_estimates → allocated, exchequer_issues
        # → actual_spent (proxy: NG-BIRR publishes Exchequer Issues at
        # the sector level, not Expenditure — see pdf_parser.py
        # docstring).
        budget_records: List[Dict[str, Any]] = []
        for r in sectoral_records:
            budget_records.append(
                {
                    "entity_slug": "national-government",
                    "entity": "National Government of Kenya",
                    "fiscal_year": period.label,
                    "start_date": period.start_date.isoformat(),
                    "end_date": period.end_date.isoformat(),
                    "category": r.sector,
                    "subcategory": r.subcategory,
                    "allocated_amount": str(r.net_estimates),
                    "actual_spent": str(r.exchequer_issues),
                    "committed_amount": None,
                    "source": f"CoB NG-BIRR {period.label}",
                    "source_url": pdf_url,
                    "data_quality": "official",
                    "notes": (
                        "Sectoral aggregate from CoB NG-BIRR Tables 2.5 "
                        "(Development) / 2.6 (Recurrent). actual_spent "
                        "is Exchequer Issues — the closest sector-level "
                        "spending proxy CoB publishes."
                    ),
                }
            )

        return budget_records or None

    except ImportError:
        logger.warning(
            "pdfplumber not available — install it for live NG-BIRR parsing"
        )
        return None
    # No temp-file cleanup: get_or_download_pdf() returns a path in the
    # persistent PDF cache (reused across runs), so it must NOT be unlinked.
