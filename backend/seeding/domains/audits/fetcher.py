"""Audit domain fetcher with live OAG report integration.

Strategy (in order):
1. If live_pdf_fetch_enabled, try to discover the latest audit report
   PDFs from the OAG (Office of the Auditor General) website.
2. Fall back to the static fixture / configured URL.

Known limitation: OAG report PDFs are scanned images
-----------------------------------------------------
Most published OAG audit reports are scanned (raster) PDFs with no
embedded text, so pdfplumber's ``extract_text`` returns empty and
the live path produces zero findings. Probed 2026-04-26: the home
page links one matching "performance-audit" PDF (32 MB, scanned)
plus an Annual Corporate Report (text but doesn't match the audit
keyword filter); the per-category listings
(/national-government-audit-reports/, /county-governments-reports/,
/financial-audit-reports/) are JS-rendered and don't expose PDFs in
raw HTML.

Both solutions to that are now implemented here:

* OCR (pytesseract + pdf2image, page-capped via
  ``audits_ocr_max_pages``) behind ``SEED_AUDITS_OCR_ENABLED`` —
  the seed workflow apt-installs tesseract-ocr + poppler-utils and
  enables it; local runs default off.
* PDF discovery via the OAG WordPress REST API
  (/wp-json/wp/v2/media — plain JSON, no JS rendering needed),
  with the homepage href-scrape as fallback.

The fixture fallback is intentionally EMPTY: the previous
512-record fixture was template-generated ("Ghost workers detected
- KES …") while labelled official — fabricated findings must never
seed a transparency site. Until OCR extraction lands real
opinions, the audits domain seeding nothing is the honest state.
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus, urljoin

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from ...utils import load_json_resource, slugify_entity

logger = logging.getLogger("seeding.audits.fetcher")

# OAG migrated from /reports/ to root page with direct PDF links (2025)
_OAG_REPORTS_URLS = [
    "https://www.oagkenya.go.ke/",
    "https://www.oagkenya.go.ke/reports/",  # legacy fallback
]


def fetch_audit_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Any:
    """Fetch audit findings, trying live OAG reports first.

    Strategy:
    1. Try live PDF fetch from OAG reports page (if enabled).
    2. Fall back to configured fixture/API URL.
    """
    # Strategy 1: Live PDF fetch from OAG.
    # Empty results are EXPECTED on the live path while OAG continues
    # to publish scanned-image PDFs (see module docstring) — the
    # "fall back to fixture" log is INFO not WARNING so we don't
    # noise up every nightly run. Real exceptions still WARN because
    # they signal a NEW failure (e.g. OAG site reorganisation,
    # network outage, pdfplumber regression).
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
                logger.info(
                    "OAG live fetch produced no findings (expected: "
                    "OAG PDFs are scanned images); falling back to fixture"
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
    # Strategy 1a: the OAG site is WordPress and exposes the WP REST API
    # (probed 2026-07-07: /wp-json/wp/v2/media answers 200). Unlike the
    # JS-rendered per-category listing pages, the media API returns
    # attachment records — including PDFs — in plain JSON, so report
    # discovery doesn't depend on scraping rendered HTML.
    pdf_urls = _discover_audit_pdfs_via_wp_api(client)

    # Strategy 1b: fall back to regex-scraping the homepage / legacy
    # reports page for direct PDF hrefs.
    if not pdf_urls:
        html = None
        page_url = _OAG_REPORTS_URLS[0]
        for url in _OAG_REPORTS_URLS:
            try:
                logger.info("Fetching OAG reports page: %s", url)
                response = client.get(url, raise_for_status=True)
                html = response.text
                page_url = url
                break
            except Exception as exc:
                logger.warning("Could not reach OAG at %s: %s", url, exc)

        if not html:
            logger.warning("Could not reach OAG website at any known URL")
            return None

        pdf_urls = _discover_audit_pdfs(html, page_url)

    if not pdf_urls:
        logger.warning("No audit report PDFs found on OAG website")
        return None

    # Try to parse the most recent report(s)
    all_findings: List[Dict[str, Any]] = []
    for pdf_url in pdf_urls[:3]:  # try up to 3 reports
        try:
            findings = _download_and_parse_audit_pdf(client, pdf_url, settings)
            if findings:
                all_findings.extend(findings)
        except Exception as exc:
            logger.warning(
                "Failed to parse OAG PDF %s: %s", pdf_url, exc
            )

    if all_findings:
        return all_findings

    return None


# WP media search terms tried in order; each targets a naming pattern the
# OAG uses for uploaded report PDFs. Results are merged + de-duplicated.
_WP_MEDIA_SEARCHES = ("county", "audit report", "financial statements")


def _discover_audit_pdfs_via_wp_api(
    client: SeedingHttpClient,
) -> List[str]:
    """Discover audit-report PDF URLs via the OAG WordPress media API.

    Best-effort: any HTTP/JSON failure returns [] so the caller falls
    back to homepage scraping.
    """
    discovered: List[str] = []
    seen: set = set()
    for term in _WP_MEDIA_SEARCHES:
        api_url = (
            "https://www.oagkenya.go.ke/wp-json/wp/v2/media"
            f"?per_page=100&search={quote_plus(term)}"
        )
        try:
            response = client.get(api_url, raise_for_status=True)
            items = response.json()
        except Exception as exc:
            logger.info("OAG WP media API query failed (%s): %s", term, exc)
            continue
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("mime_type") != "application/pdf":
                continue
            url = item.get("source_url") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            discovered.append(url)
    if discovered:
        logger.info(
            "OAG WP media API discovered %d audit-candidate PDFs",
            len(discovered),
        )
        # Keep the audit-keyword filter consistent with the HTML path.
        filtered = [
            u
            for u in discovered
            if any(kw in u.lower() for kw in ("audit", "county", "financial"))
        ]
        return filtered or discovered
    return []


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
    client: SeedingHttpClient,
    pdf_url: str,
    settings: SeedingSettings,
) -> Optional[List[Dict[str, Any]]]:
    """Download and attempt to parse an OAG audit report PDF.

    Embedded-text extraction first (pdfplumber); when the PDF is a
    scanned image (OAG's norm) and ``audits_ocr_enabled`` is on, fall
    back to OCR via pdf2image + pytesseract.
    """
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
            if settings.audits_ocr_enabled:
                full_text = _ocr_pdf_text(
                    tmp_path, max_pages=settings.audits_ocr_max_pages
                )
            else:
                # OAG publishes scanned-image PDFs — enable
                # SEED_AUDITS_OCR_ENABLED (and install tesseract-ocr +
                # poppler-utils) to extract them. INFO not WARNING so
                # the log doesn't suggest a new fault on every run.
                logger.info(
                    "PDF appears to contain no extractable text "
                    "(scanned image; OCR disabled)"
                )
                return None

        if not full_text.strip():
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


def _ocr_pdf_text(pdf_path: Path, max_pages: int = 30) -> str:
    """OCR a scanned PDF into text (pdf2image + pytesseract).

    Returns "" when the OCR stack isn't installed or fails — callers
    treat that identically to a text-less PDF. Pages are rendered one
    at a time (not the whole document) so a 700-page report doesn't
    hold hundreds of rasterised pages in memory.
    """
    try:
        import pytesseract
        from pdf2image import convert_from_path, pdfinfo_from_path
    except ImportError:
        logger.warning(
            "OCR requested but pytesseract/pdf2image not installed — "
            "pip install pytesseract pdf2image (plus system "
            "tesseract-ocr and poppler-utils)"
        )
        return ""

    try:
        info = pdfinfo_from_path(pdf_path)
        total_pages = int(info.get("Pages", 0)) or 1
    except Exception as exc:
        logger.warning("OCR: could not read PDF info: %s", exc)
        return ""

    pages_to_read = min(total_pages, max_pages)
    logger.info(
        "OCR: extracting %d/%d pages from %s",
        pages_to_read,
        total_pages,
        pdf_path.name,
    )

    chunks: List[str] = []
    for page_no in range(1, pages_to_read + 1):
        try:
            images = convert_from_path(
                pdf_path, dpi=200, first_page=page_no, last_page=page_no
            )
            for image in images:
                text = pytesseract.image_to_string(image)
                if text.strip():
                    chunks.append(text)
        except Exception as exc:
            logger.warning("OCR failed on page %d: %s", page_no, exc)
            break

    text = "\n".join(chunks)
    logger.info("OCR: extracted %d characters", len(text))
    return text


# ── Fiscal-period derivation ──────────────────────────────────────────
# Kenya's fiscal year runs 1 July → 30 June. Every persisted audit
# finding MUST carry a period_label + start/end dates (the parser drops
# any finding missing them, and the writer keys a FiscalPeriod off them).
# The FY the accounts cover is reliably present in the OAG report
# filename ("...-Homa-Bay-2021-2022.pdf",
# "...-NATIONAL-GOVERNMENT-2024-2025.pdf") and, failing that, on the
# cover page ("...for the year ended 30 June 2022"). We derive it from
# the source URL first, then the report text.

# FY spans as they appear in filenames/URLs and inline text:
# 2021-2022, 2021_2022, 2021/2022, 2021-22, 2022/23, 2021–2022 (en-dash).
_FY_SPAN_RE = re.compile(r"(20\d{2})\s*[/_–-]\s*(20\d{2}|\d{2})")
# Cover-page phrasing: "for the year ended 30 June 2022".
_YEAR_ENDED_RE = re.compile(
    r"year\s+ended\s+\d{1,2}(?:st|nd|rd|th)?\s+june\s+(20\d{2})",
    re.IGNORECASE,
)


def _fy_from_span(
    y1: int, y2: int
) -> Optional[Tuple[str, str, str, int]]:
    """Build (period_label, start_date, end_date, audit_year) for a
    consecutive-year Kenyan FY (July y1 → June y2).

    Returns None when y1/y2 aren't a consecutive pair — this guards
    against multi-year ranges (e.g. a "2019-2023" strategic-plan span)
    being mistaken for a single fiscal year. audit_year is the END year
    (the "year ended 30 June {y2}" the report audits).
    """
    if y2 == y1 + 1:
        return (f"{y1}/{y2}", f"{y1}-07-01", f"{y2}-06-30", y2)
    return None


def _derive_fiscal_period(
    source: str, text: str
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[int]]:
    """Best-effort fiscal period for an OAG report.

    Order of preference: source URL/filename (most reliable) → an FY
    span in the first pages of text → a "year ended 30 June YYYY" cover
    line. Returns (period_label, start_date, end_date, audit_year); each
    element is None when the FY cannot be determined, in which case the
    finding is intentionally left unattributed (and dropped downstream)
    rather than stamped with a guessed period.
    """
    head = text[:4000] if text else ""
    for candidate in (source or "", head):
        # Scan ALL spans, not just the first: an OAG upload URL embeds a
        # publish date ("/wp-content/uploads/2023/11/") that matches the
        # span shape but isn't a fiscal year — the consecutive-year check
        # in _fy_from_span rejects it, so we keep looking for the real FY.
        for match in _FY_SPAN_RE.finditer(candidate):
            y1 = int(match.group(1))
            y2_raw = match.group(2)
            # "2021-22" → 2022; "2021-2022" → 2022.
            y2 = int(y2_raw) if len(y2_raw) == 4 else (y1 // 100) * 100 + int(y2_raw)
            fy = _fy_from_span(y1, y2)
            if fy:
                return fy
    if text:
        match = _YEAR_ENDED_RE.search(text)
        if match:
            y2 = int(match.group(1))
            fy = _fy_from_span(y2 - 1, y2)
            if fy:
                return fy
    return (None, None, None, None)


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

    # Fiscal period is document-level: derive it once from the source
    # filename / report text and stamp every finding with it. Without a
    # period_label + start/end dates the parser drops the finding.
    period_label, start_date, end_date, audit_year = _derive_fiscal_period(
        source_url, text
    )

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
            # slugify_entity collapses punctuation (incl. apostrophes) so
            # "Murang'a" normalises to "muranga" — matches the DB slug
            # format. Prior `.lower().replace(" ", "-")` left apostrophes
            # in place and triggered "Unknown entity slug" warnings.
            entity_slug = slugify_entity(entity, county_suffix=bool(current_county))

            # Truncate finding text to reasonable length
            finding_text = section.strip()[:500]

            findings.append({
                "entity_slug": entity_slug,
                "entity": f"{entity} County" if current_county else entity,
                "period_label": period_label or "",
                "start_date": start_date,
                "end_date": end_date,
                "finding_text": finding_text,
                "severity": severity,
                "recommended_action": "",
                "reference": f"OAG-{len(findings) + 1:04d}",
                "query_type": "financial_audit",
                "amount": amount,
                "status": "pending",
                "audit_year": audit_year,
                "source_url": source_url,
                "source": "Office of the Auditor General",
                "data_quality": "official",
            })

    logger.info("Extracted %d findings from OAG PDF text", len(findings))
    return findings


__all__ = ["fetch_audit_payload"]
