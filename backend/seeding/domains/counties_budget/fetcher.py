"""Budget domain fetcher with live COB PDF integration.

Strategy (in order):
1. If live_pdf_fetch_enabled, try to discover the latest COB County
   Budget Implementation Review Report (C-BIRR) PDF, parse it.
2. Fall back to the static fixture / configured URL.

County budget data primarily comes from the Controller of Budget (COB)
quarterly reports. Unlike national-level data, there is no free API —
the data is published in PDF reports.
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

logger = logging.getLogger("seeding.counties_budget.fetcher")

# COB migrated from /reports/ to /publications/ paths (2025)
_COB_COUNTY_BIRR_URLS = [
    "https://cob.go.ke/publications/county-reports/",
    "https://cob.go.ke/publications/consolidated-county-budget-implementation-review-reports/",
    "https://cob.go.ke/reports/county-governments-budget-implementation-review-reports/",  # legacy
]


def fetch_budget_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Any:
    """Retrieve the budgets dataset, trying live COB PDF first.

    Strategy:
    1. Try live PDF fetch from COB county BIRR reports page.
    2. Fall back to configured fixture/API URL.
    """
    # Strategy 1: Live PDF fetch
    if settings.live_pdf_fetch_enabled:
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
    """Discover and parse the latest COB county BIRR PDF."""
    # Try multiple URLs since COB restructures their site periodically
    html = None
    page_url = _COB_COUNTY_BIRR_URLS[0]
    for url in _COB_COUNTY_BIRR_URLS:
        try:
            logger.info("Fetching COB county BIRR reports page: %s", url)
            response = client.get(url, raise_for_status=True)
            html = response.text
            page_url = url
            break
        except Exception as exc:
            logger.warning("COB county page unavailable at %s: %s", url, exc)

    if not html:
        raise RuntimeError("Could not reach COB county reports at any known URL")

    pdf_url = _discover_latest_county_birr_pdf(html, page_url)
    if not pdf_url:
        logger.warning("No county BIRR PDF link found on COB reports page")
        return None

    logger.info("Downloading COB county BIRR PDF: %s", pdf_url)
    return _download_and_parse_county_pdf(client, pdf_url)


def _discover_latest_county_birr_pdf(
    html: str, base_url: str
) -> Optional[str]:
    """Extract the most recent county BIRR PDF URL from the COB page."""
    pdf_pattern = re.compile(
        r'href=["\']([^"\']*\.pdf)["\']',
        re.IGNORECASE,
    )
    all_pdfs = pdf_pattern.findall(html)
    if not all_pdfs:
        return None

    # Filter for county budget-related PDFs
    county_keywords = [
        "county", "c-birr", "cbirr", "county-government",
        "county_government", "county-budget",
    ]
    county_pdfs = [
        url for url in all_pdfs
        if any(kw in url.lower() for kw in county_keywords)
    ]

    candidates = county_pdfs if county_pdfs else all_pdfs
    if not candidates:
        return None

    chosen = candidates[0]
    if not chosen.startswith(("http://", "https://")):
        chosen = urljoin(base_url, chosen)

    return chosen


def _download_and_parse_county_pdf(
    client: SeedingHttpClient, pdf_url: str
) -> Optional[List[Dict[str, Any]]]:
    """Download a COB county BIRR PDF, parse it, return budget records."""
    tmp_path: Optional[Path] = None
    try:
        from ...pdf_parsers import CoBQuarterlyReportParser

        response = client.get(pdf_url, raise_for_status=True)

        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False, prefix="cob_county_birr_"
        ) as tmp:
            tmp.write(response.content)
            tmp_path = Path(tmp.name)

        logger.info(
            "Downloaded COB county BIRR PDF (%d bytes) to %s",
            len(response.content),
            tmp_path,
        )

        parser = CoBQuarterlyReportParser(tmp_path)
        parsed_records = parser.parse()

        if not parsed_records:
            logger.warning("CoBQuarterlyReportParser returned no records")
            return None

        # Convert to budget format
        budget_records: List[Dict[str, Any]] = []
        for record in parsed_records:
            county = record.get("county", "Unknown")
            entity_slug = county.lower().replace(" ", "-") + "-county"
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
                "entity": f"{county} County",
                "fiscal_year": fy,
                "category": record.get("category", "Total"),
                "allocated_amount": float(allocated),
                "actual_spent": float(absorbed),
                "committed_amount": None,
                "source": f"Controller of Budget C-BIRR Report",
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


__all__ = ["fetch_budget_payload"]
