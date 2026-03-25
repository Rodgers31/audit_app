"""Fetcher for pending bills data from COB reports.

Strategy (in order):
1. If live_pdf_fetch_enabled, try to discover the latest COB National
   Government BIRR PDF, download it, and parse with CoBQuarterlyReportParser.
2. If pending_bills_dataset_url is configured, load from that source.
3. Otherwise, run the live ETL extractor against COB website.
"""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient

logger = logging.getLogger("seeding.pending_bills.fetcher")


def fetch_pending_bills_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> dict[str, Any]:
    """
    Fetch pending bills data.

    Strategy:
      1. Try live PDF fetch from COB reports page (if enabled).
      2. If pending_bills_dataset_url is configured, load from fixture/API.
      3. Otherwise, run the live ETL extractor against COB website.
    """
    # Strategy 1: Live PDF fetch
    if settings.live_pdf_fetch_enabled:
        try:
            payload = _fetch_from_cob_pdf(client, settings)
            if payload and payload.get("pending_bills"):
                logger.info(
                    "Successfully fetched pending bills from COB PDF (%d records)",
                    len(payload["pending_bills"]),
                )
                return payload
            else:
                logger.warning(
                    "COB PDF fetch returned no pending bills, trying fixture"
                )
        except Exception as exc:
            logger.warning(
                "COB PDF fetch failed, trying fixture: %s", exc
            )

    # Strategy 2: Configured fixture / API URL
    dataset_url = getattr(settings, "pending_bills_dataset_url", None)
    if dataset_url:
        logger.info("Fetching pending bills from configured URL: %s", dataset_url)
        from ...utils import load_json_resource

        return load_json_resource(
            url=dataset_url,
            client=client,
            logger=logger,
            label="pending_bills",
        )

    # Strategy 3: Live ETL extraction
    logger.info(
        "No pending_bills_dataset_url configured. Running live COB extraction..."
    )
    return _run_live_extraction()


def _fetch_from_cob_pdf(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Optional[Dict[str, Any]]:
    """Discover and parse the latest COB BIRR PDF."""
    page_url = settings.cob_birr_page_url
    logger.info("Fetching COB BIRR reports page: %s", page_url)

    response = client.get(page_url, raise_for_status=True)
    html = response.text

    pdf_url = _discover_latest_birr_pdf(html, page_url)
    if not pdf_url:
        logger.warning("No BIRR PDF link found on COB reports page")
        return None

    logger.info("Downloading COB BIRR PDF: %s", pdf_url)
    return _download_and_parse_cob_pdf(client, pdf_url)


def _discover_latest_birr_pdf(html: str, base_url: str) -> Optional[str]:
    """Extract the most recent BIRR PDF URL from the COB reports page.

    Looks for links matching common COB BIRR naming patterns like:
    - BIRR-*.pdf
    - Budget-Implementation-Review-*.pdf
    - NG-BIRR-*.pdf
    - national-government-budget-implementation*.pdf
    """
    pdf_pattern = re.compile(
        r'href=["\']([^"\']*\.pdf)["\']',
        re.IGNORECASE,
    )
    all_pdfs = pdf_pattern.findall(html)

    if not all_pdfs:
        return None

    # Filter for BIRR-related PDFs
    birr_keywords = [
        "birr", "budget-implementation", "budget_implementation",
        "implementation-review", "implementation_review",
        "pending-bill", "pending_bill",
    ]
    birr_pdfs = [
        url for url in all_pdfs
        if any(kw in url.lower() for kw in birr_keywords)
    ]

    candidates = birr_pdfs if birr_pdfs else all_pdfs

    if not candidates:
        return None

    # Pick the first match (usually the most recent)
    chosen = candidates[0]

    if not chosen.startswith(("http://", "https://")):
        chosen = urljoin(base_url, chosen)

    return chosen


def _download_and_parse_cob_pdf(
    client: SeedingHttpClient, pdf_url: str
) -> Optional[Dict[str, Any]]:
    """Download a COB PDF to a temp file, parse it, and return pending bills payload."""
    from ...pdf_parsers import CoBQuarterlyReportParser

    tmp_path: Optional[Path] = None
    try:
        response = client.get(pdf_url, raise_for_status=True)

        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False, prefix="cob_birr_"
        ) as tmp:
            tmp.write(response.content)
            tmp_path = Path(tmp.name)

        logger.info(
            "Downloaded COB PDF (%d bytes) to %s",
            len(response.content),
            tmp_path,
        )

        # Parse with CoBQuarterlyReportParser
        parser = CoBQuarterlyReportParser(tmp_path)
        parsed_records = parser.parse()

        if not parsed_records:
            logger.warning("CoBQuarterlyReportParser returned no records")
            return None

        # Convert parsed budget execution records into pending bills format.
        # The COB parser extracts county budget execution data (allocated vs absorbed).
        # We derive "pending bills" as the gap between allocated and absorbed —
        # unspent allocations often correspond to pending obligations.
        pending_bills: List[Dict[str, Any]] = []
        for record in parsed_records:
            allocated = record.get("allocated", 0)
            absorbed = record.get("absorbed", 0)
            if isinstance(allocated, str):
                try:
                    from decimal import Decimal
                    allocated = float(Decimal(allocated))
                except Exception:
                    allocated = 0
            if isinstance(absorbed, str):
                try:
                    from decimal import Decimal
                    absorbed = float(Decimal(absorbed))
                except Exception:
                    absorbed = 0

            # Pending ≈ allocated - absorbed (unspent = potential pending bills)
            pending = max(float(allocated) - float(absorbed), 0)
            if pending <= 0:
                continue

            county = record.get("county", "Unknown")
            fy = record.get("fiscal_year", "")
            quarter = record.get("quarter", "")

            pending_bills.append({
                "entity_name": f"County Government of {county}",
                "entity_type": "county",
                "category": "county",
                "fiscal_year": fy,
                "total_pending": pending,
                "eligible_pending": None,
                "ineligible_pending": None,
                "notes": (
                    f"Derived from COB BIRR {quarter} {fy}: "
                    f"allocated {allocated:,.0f} - absorbed {absorbed:,.0f} = "
                    f"{pending:,.0f} unspent (proxy for pending obligations)"
                ),
            })

        if not pending_bills:
            logger.warning("No pending bills derived from COB budget data")
            return None

        return {
            "pending_bills": pending_bills,
            "summary": {
                "fiscal_year": parsed_records[0].get("fiscal_year", ""),
                "total_county": sum(
                    pb["total_pending"] for pb in pending_bills
                ),
            },
            "source_url": pdf_url,
            "source_title": f"COB BIRR Report (live fetch)",
        }

    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
                logger.debug("Cleaned up temp PDF: %s", tmp_path)
            except OSError:
                pass


def _run_live_extraction() -> dict[str, Any]:
    """Run the pending bills ETL extractor against the COB website."""
    try:
        from etl.pending_bills_extractor import PendingBillsExtractor

        extractor = PendingBillsExtractor()
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(extractor.extract_all())
        finally:
            loop.close()

        if not result.get("pending_bills") and not result.get("summary", {}).get(
            "grand_total"
        ):
            logger.warning(
                "Live extraction returned no pending bills data. "
                "The COB reports may require Playwright for PDF download. "
                "Consider setting PLAYWRIGHT_ENABLED=1 and "
                "SEED_PENDING_BILLS_DATASET_URL to a fixture file."
            )
        return result

    except ImportError as exc:
        logger.error(
            "Cannot run live extraction: %s. "
            "Install required packages: pip install pdfplumber httpx beautifulsoup4",
            exc,
        )
        return {
            "pending_bills": [],
            "summary": {},
            "source_url": "https://cob.go.ke/publications/",
            "source_title": "Controller of Budget Reports",
            "extraction_error": str(exc),
        }
    except Exception as exc:
        logger.exception("Live extraction failed: %s", exc)
        return {
            "pending_bills": [],
            "summary": {},
            "source_url": "https://cob.go.ke/publications/",
            "source_title": "Controller of Budget Reports",
            "extraction_error": str(exc),
        }
