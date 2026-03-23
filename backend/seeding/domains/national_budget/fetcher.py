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
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from ...utils import load_json_resource

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
                # Filter metadata entries
                return [r for r in payload if "_metadata" not in r]
            else:
                logger.warning(
                    "COB NG-BIRR PDF fetch returned no data, "
                    "falling back to fixture"
                )
        except Exception as exc:
            logger.warning(
                "COB NG-BIRR PDF fetch failed, falling back to fixture: %s", exc
            )

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
    return _download_and_parse_ng_pdf(client, pdf_url)


def _discover_latest_ng_birr_pdf(
    html: str, base_url: str
) -> Optional[str]:
    """Extract the most recent NG-BIRR PDF URL from the COB page."""
    pdf_pattern = re.compile(
        r'href=["\']([^"\']*\.pdf)["\']',
        re.IGNORECASE,
    )
    all_pdfs = pdf_pattern.findall(html)
    if not all_pdfs:
        return None

    birr_keywords = [
        "ng-birr", "national-government-budget",
        "national_government_budget", "birr",
        "budget-implementation", "budget_implementation",
    ]
    birr_pdfs = [
        url for url in all_pdfs
        if any(kw in url.lower() for kw in birr_keywords)
    ]

    candidates = birr_pdfs if birr_pdfs else all_pdfs
    if not candidates:
        return None

    chosen = candidates[0]
    if not chosen.startswith(("http://", "https://")):
        chosen = urljoin(base_url, chosen)

    return chosen


def _download_and_parse_ng_pdf(
    client: SeedingHttpClient, pdf_url: str
) -> Optional[List[Dict[str, Any]]]:
    """Download a COB NG-BIRR PDF, parse it, return budget execution records."""
    tmp_path: Optional[Path] = None
    try:
        from ...pdf_parsers import CoBQuarterlyReportParser

        response = client.get(pdf_url, raise_for_status=True)

        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False, prefix="cob_ng_birr_"
        ) as tmp:
            tmp.write(response.content)
            tmp_path = Path(tmp.name)

        logger.info(
            "Downloaded COB NG-BIRR PDF (%d bytes) to %s",
            len(response.content),
            tmp_path,
        )

        parser = CoBQuarterlyReportParser(tmp_path)
        parsed_records = parser.parse()

        if not parsed_records:
            logger.warning("CoBQuarterlyReportParser returned no records")
            return None

        # Convert to national budget execution format
        budget_records: List[Dict[str, Any]] = []
        for record in parsed_records:
            entity = record.get("entity", record.get("ministry", "Unknown"))
            entity_slug = entity.lower().replace(" ", "-").replace(",", "")
            fy = record.get("fiscal_year", "")

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
                "entity": entity,
                "fiscal_year": fy,
                "category": record.get("category", record.get("sector", "General")),
                "allocated_amount": float(allocated),
                "actual_spent": float(absorbed),
                "committed_amount": None,
                "source": "Controller of Budget NG-BIRR Report",
                "source_url": pdf_url,
                "data_quality": "official",
            })

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
