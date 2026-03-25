"""Fetcher for National Treasury debt bulletin data.

Strategy (in order):
1. If live_pdf_fetch_enabled, try to discover the latest PDF from the CBK
   public debt page, download it, and parse with TreasuryDebtBulletinParser.
2. Fall back to the static fixture / configured URL.
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

logger = logging.getLogger("seeding.national_debt.fetcher")


def fetch_debt_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> dict[str, Any]:
    """
    Fetch debt data from CBK PDF bulletin or fixture.

    Tries live PDF fetch first (if enabled), then falls back to fixture.
    """
    if settings.live_pdf_fetch_enabled:
        try:
            payload = _fetch_from_cbk_pdf(client, settings)
            if payload and payload.get("loans"):
                logger.info(
                    "Successfully fetched national debt from CBK PDF (%d loans)",
                    len(payload["loans"]),
                )
                return payload
            else:
                logger.warning(
                    "CBK PDF fetch returned no loans, falling back to fixture"
                )
        except Exception as exc:
            logger.warning(
                "CBK PDF fetch failed, falling back to fixture: %s", exc
            )

    logger.info("Using fixture fallback for national debt data")
    return load_json_resource(
        url=settings.national_debt_dataset_url,
        client=client,
        logger=logger,
        label="national_debt",
    )


def _fetch_from_cbk_pdf(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Optional[Dict[str, Any]]:
    """Discover and parse the latest CBK debt bulletin PDF."""
    page_url = settings.cbk_public_debt_page_url
    logger.info("Fetching CBK public debt page: %s", page_url)

    response = client.get(page_url, raise_for_status=True)
    html = response.text

    # Find PDF links on the page
    pdf_url = _discover_latest_pdf_url(html, page_url)
    if not pdf_url:
        logger.warning("No PDF link found on CBK public debt page")
        return None

    logger.info("Downloading CBK debt bulletin PDF: %s", pdf_url)
    return _download_and_parse_pdf(client, pdf_url)


def _discover_latest_pdf_url(html: str, base_url: str) -> Optional[str]:
    """Extract the most recent debt bulletin PDF URL from the CBK page HTML.

    Looks for links matching common CBK bulletin naming patterns like:
    - Public-Debt-Statistical-Bulletin-*.pdf
    - Public_Debt_*.pdf
    - debt-bulletin-*.pdf
    """
    # Find all PDF links
    pdf_pattern = re.compile(
        r'href=["\']([^"\']*\.pdf)["\']',
        re.IGNORECASE,
    )
    all_pdfs = pdf_pattern.findall(html)

    if not all_pdfs:
        return None

    # Exclude PDFs that are clearly NOT debt bulletins
    exclude_keywords = [
        "auction", "guidelines", "tender", "vacancy", "career",
        "press-release", "speech", "circular", "calendar",
        "monetary-policy", "cbk-annual",
    ]

    # Filter for debt-related PDFs
    debt_keywords = [
        "debt", "bulletin", "public-debt", "public_debt",
        "statistical-bulletin", "borrowing",
    ]
    debt_pdfs = [
        url for url in all_pdfs
        if any(kw in url.lower() for kw in debt_keywords)
        and not any(ex in url.lower() for ex in exclude_keywords)
    ]

    # If no debt-specific PDFs, try statistical bulletins
    if not debt_pdfs:
        stat_pdfs = [
            url for url in all_pdfs
            if "statistical" in url.lower() or "bulletin" in url.lower()
            and not any(ex in url.lower() for ex in exclude_keywords)
        ]
        debt_pdfs = stat_pdfs

    if not debt_pdfs:
        logger.warning(
            "No debt-related PDFs found among %d PDFs on page", len(all_pdfs)
        )
        return None

    # Pick the first match (usually the most recent on CBK page)
    chosen = debt_pdfs[0]

    # Make absolute URL
    if not chosen.startswith(("http://", "https://")):
        chosen = urljoin(base_url, chosen)

    return chosen


def _download_and_parse_pdf(
    client: SeedingHttpClient, pdf_url: str
) -> Optional[Dict[str, Any]]:
    """Download a PDF to a temp file, parse it, and return the payload."""
    from ...pdf_parsers import TreasuryDebtBulletinParser

    tmp_path: Optional[Path] = None
    try:
        # Download PDF to temp file
        response = client.get(pdf_url, raise_for_status=True)
        content_type = response.headers.get("content-type", "").lower()

        if "pdf" not in content_type and not pdf_url.lower().endswith(".pdf"):
            logger.warning(
                "Response does not appear to be a PDF (content-type: %s)",
                content_type,
            )

        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False, prefix="cbk_debt_"
        ) as tmp:
            tmp.write(response.content)
            tmp_path = Path(tmp.name)

        logger.info(
            "Downloaded CBK PDF (%d bytes) to %s",
            len(response.content),
            tmp_path,
        )

        # Parse with TreasuryDebtBulletinParser
        parser = TreasuryDebtBulletinParser(tmp_path)
        parsed_loans = parser.parse()

        if not parsed_loans:
            logger.warning("TreasuryDebtBulletinParser returned no loans")
            return None

        # Convert parsed Decimal-based records to the JSON format expected
        # by national_debt/parser.py
        loans_json: List[Dict[str, Any]] = []
        for loan in parsed_loans:
            loans_json.append({
                "entity_name": "National Government",
                "entity_type": "national",
                "lender": loan["lender"],
                "debt_category": _classify_debt_category(loan.get("loan_type", "")),
                "principal": str(loan["principal"]),
                "outstanding": str(loan["outstanding"]),
                "interest_rate": None,
                "issue_date": "2020-01-01",  # placeholder — PDF rarely has exact dates
                "maturity_date": None,
                "currency": loan.get("currency", "KES"),
                "notes": f"Parsed from CBK bulletin: {pdf_url}",
            })

        return {
            "metadata": {
                "source": "Central Bank of Kenya Public Debt Statistics",
                "description": "Parsed from live CBK debt bulletin PDF",
                "units": "kes",
                "last_updated": None,  # could extract from PDF
            },
            "source_url": pdf_url,
            "source_title": "CBK Public Debt Statistical Bulletin (live fetch)",
            "loans": loans_json,
        }

    finally:
        # Clean up temp file
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
                logger.debug("Cleaned up temp PDF: %s", tmp_path)
            except OSError:
                pass


def _classify_debt_category(loan_type: str) -> str:
    """Map TreasuryDebtBulletinParser loan_type to our debt_category enum."""
    lt = loan_type.lower()
    if lt == "multilateral":
        return "external_multilateral"
    elif lt == "bilateral":
        return "external_bilateral"
    elif lt == "commercial":
        return "external_commercial"
    else:
        return "external_other"
