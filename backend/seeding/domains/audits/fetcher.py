"""Audit domain fetcher with live OAG report integration.

Strategy (in order):
1. If live_pdf_fetch_enabled, try to discover the latest audit report
   PDFs from the OAG (Office of the Auditor General) website.
2. Fall back to the static fixture / configured URL.

Note: OAG Kenya does not provide a structured API. Audit findings are
published as PDF reports at https://www.oagkenya.go.ke/reports/.
The live fetcher attempts to discover and parse the latest reports.
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

logger = logging.getLogger("seeding.audits.fetcher")

_OAG_REPORTS_URL = "https://www.oagkenya.go.ke/reports/"


def fetch_audit_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Any:
    """Fetch audit findings, trying live OAG reports first.

    Strategy:
    1. Try live PDF fetch from OAG reports page (if enabled).
    2. Fall back to configured fixture/API URL.
    """
    # Strategy 1: Live PDF fetch from OAG
    if settings.live_pdf_fetch_enabled:
        try:
            payload = _fetch_from_oag(client, settings)
            if payload and _count_findings(payload) > 0:
                logger.info(
                    "Successfully fetched audit data from OAG (%d findings)",
                    _count_findings(payload),
                )
                return payload
            else:
                logger.warning(
                    "OAG fetch returned no findings, falling back to fixture"
                )
        except Exception as exc:
            logger.warning(
                "OAG fetch failed, falling back to fixture: %s", exc
            )

    # Strategy 2: Fixture fallback
    logger.info("Using fixture/configured URL for audit data")
    return load_json_resource(
        url=settings.audits_dataset_url,
        client=client,
        logger=logger,
        label="audits",
    )


def _count_findings(payload: Any) -> int:
    """Count audit findings in a payload regardless of format."""
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        records = payload.get("records", payload.get("findings", []))
        if isinstance(records, list):
            return len(records)
    return 0


def _fetch_from_oag(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Optional[Any]:
    """Try to discover and parse audit reports from OAG website.

    The OAG website lists PDF reports. We look for county and national
    audit report PDFs, download, and attempt to extract findings.
    """
    page_url = _OAG_REPORTS_URL
    logger.info("Fetching OAG reports page: %s", page_url)

    try:
        response = client.get(page_url, raise_for_status=True)
    except Exception as exc:
        logger.warning("Could not reach OAG website: %s", exc)
        return None

    html = response.text

    # Find audit report PDF links
    pdf_urls = _discover_audit_pdfs(html, page_url)
    if not pdf_urls:
        logger.warning("No audit report PDFs found on OAG website")
        return None

    # Try to parse the most recent report(s)
    all_findings: List[Dict[str, Any]] = []
    for pdf_url in pdf_urls[:3]:  # try up to 3 reports
        try:
            findings = _download_and_parse_audit_pdf(client, pdf_url)
            if findings:
                all_findings.extend(findings)
        except Exception as exc:
            logger.warning(
                "Failed to parse OAG PDF %s: %s", pdf_url, exc
            )

    if all_findings:
        return all_findings

    return None


def _discover_audit_pdfs(html: str, base_url: str) -> List[str]:
    """Extract audit report PDF URLs from OAG reports page."""
    pdf_pattern = re.compile(
        r'href=["\']([^"\']*\.pdf)["\']',
        re.IGNORECASE,
    )
    all_pdfs = pdf_pattern.findall(html)

    if not all_pdfs:
        return []

    # Filter for audit-related PDFs
    audit_keywords = [
        "audit", "county", "national-government",
        "financial-statement", "special-audit",
        "performance-audit", "forensic",
    ]
    audit_pdfs = [
        url for url in all_pdfs
        if any(kw in url.lower() for kw in audit_keywords)
    ]

    candidates = audit_pdfs if audit_pdfs else all_pdfs[:5]

    # Make absolute URLs
    result = []
    for url in candidates:
        if not url.startswith(("http://", "https://")):
            url = urljoin(base_url, url)
        result.append(url)

    return result


def _download_and_parse_audit_pdf(
    client: SeedingHttpClient, pdf_url: str
) -> Optional[List[Dict[str, Any]]]:
    """Download and attempt to parse an OAG audit report PDF."""
    tmp_path: Optional[Path] = None
    try:
        # Try to use pdfplumber for text extraction
        import pdfplumber
    except ImportError:
        logger.warning(
            "pdfplumber not available — cannot parse OAG PDFs. "
            "Install: pip install pdfplumber"
        )
        return None

    try:
        response = client.get(pdf_url, raise_for_status=True)

        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False, prefix="oag_audit_"
        ) as tmp:
            tmp.write(response.content)
            tmp_path = Path(tmp.name)

        logger.info(
            "Downloaded OAG PDF (%d bytes) to %s",
            len(response.content),
            tmp_path,
        )

        findings: List[Dict[str, Any]] = []

        with pdfplumber.open(tmp_path) as pdf:
            full_text = ""
            for page in pdf.pages[:50]:  # limit to first 50 pages
                text = page.extract_text()
                if text:
                    full_text += text + "\n"

            if not full_text.strip():
                logger.warning("PDF appears to contain no extractable text")
                return None

            # Extract audit findings using pattern matching
            findings = _extract_findings_from_text(full_text, pdf_url)

        return findings if findings else None

    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _extract_findings_from_text(
    text: str, source_url: str
) -> List[Dict[str, Any]]:
    """Extract structured audit findings from OAG report text.

    OAG reports follow common patterns:
    - Numbered findings (e.g., "1.", "2.", "3.")
    - County headers followed by finding descriptions
    - Key phrases: "irregular", "unaccounted", "unsupported",
      "pending", "variance", "over-expenditure"
    """
    findings: List[Dict[str, Any]] = []

    # Try to find county-specific sections
    county_pattern = re.compile(
        r'(?:County Government of|County Assembly of)\s+([A-Za-z\s]+?)(?:\n|$)',
        re.IGNORECASE,
    )

    # Split by numbered findings
    finding_pattern = re.compile(
        r'(?:^|\n)\s*(\d+)\.\s*(.+?)(?=\n\s*\d+\.|$)',
        re.DOTALL,
    )

    # Extract severity keywords
    severity_keywords = {
        "critical": ["fraud", "loss", "missing", "theft", "embezzlement"],
        "high": ["irregular", "unaccounted", "unsupported", "unauthorized"],
        "medium": ["variance", "over-expenditure", "under-collection", "pending"],
        "low": ["delay", "non-compliance", "weakness", "recommendation"],
    }

    current_county = None
    sections = text.split("\n\n")

    for section in sections:
        # Check for county header
        county_match = county_pattern.search(section)
        if county_match:
            current_county = county_match.group(1).strip()

        # Look for finding-like content
        if len(section) > 100 and any(
            kw in section.lower()
            for kws in severity_keywords.values()
            for kw in kws
        ):
            # Determine severity
            severity = "INFO"
            section_lower = section.lower()
            for level, keywords in severity_keywords.items():
                if any(kw in section_lower for kw in keywords):
                    severity = level.upper()
                    break

            # Extract amount if mentioned
            amount_match = re.search(
                r'Ks?h\.?\s*([\d,]+(?:\.\d+)?)\s*(?:million|billion)?',
                section,
                re.IGNORECASE,
            )
            amount = None
            if amount_match:
                try:
                    raw = amount_match.group(1).replace(",", "")
                    amount = float(raw)
                    if "billion" in section[amount_match.start():amount_match.end() + 20].lower():
                        amount *= 1e9
                    elif "million" in section[amount_match.start():amount_match.end() + 20].lower():
                        amount *= 1e6
                except ValueError:
                    pass

            entity = current_county or "National Government"
            entity_slug = entity.lower().replace(" ", "-")
            if current_county:
                entity_slug += "-county"

            # Truncate finding text to reasonable length
            finding_text = section.strip()[:500]

            findings.append({
                "entity_slug": entity_slug,
                "entity": f"{entity} County" if current_county else entity,
                "period_label": "",  # Will be extracted from context
                "finding_text": finding_text,
                "severity": severity,
                "recommended_action": "",
                "reference": f"OAG-{len(findings) + 1:04d}",
                "query_type": "financial_audit",
                "amount": amount,
                "status": "pending",
                "audit_year": None,
                "source_url": source_url,
                "source": "Office of the Auditor General",
                "data_quality": "official",
            })

    logger.info("Extracted %d findings from OAG PDF text", len(findings))
    return findings


__all__ = ["fetch_audit_payload"]
