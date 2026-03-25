"""Extract pending bills data from Controller of Budget (COB) reports.

Primary source: COB National Government Budget Implementation Review Reports
  - https://cob.go.ke/publications/national-government-budget-implementation-review-reports/
  - These PDF reports contain detailed pending bills tables broken down by MDA/vote

Secondary source: COB County Government Budget Implementation Review Reports
  - https://cob.go.ke/publications/county-government-budget-implementation-review-reports/

The extractor:
  1. Scrapes the COB reports listing page for the latest report PDF link
  2. Downloads the PDF (or uses headless browser for protected downloads)
  3. Extracts pending bills summary tables using pdfplumber
  4. Returns structured data with entity, amount, fiscal year, status
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("etl.pending_bills")

# ── COB source URLs ──────────────────────────────────────────────────────
COB_BASE = "https://cob.go.ke"
COB_NATIONAL_REPORTS = (
    "https://cob.go.ke/publications/"
    "national-government-budget-implementation-review-reports/"
)
COB_COUNTY_REPORTS = (
    "https://cob.go.ke/publications/"
    "county-government-budget-implementation-review-reports/"
)
COB_DOWNLOADS_BASE = "https://cob.go.ke/download/"
COB_PENDING_BILLS_PAGE = "https://cob.go.ke/publications/pending-bills/"

# Known report download pages by fiscal year (discovered via scraping)
KNOWN_REPORT_PAGES: dict[str, str] = {
    "FY2024/25": (
        "https://cob.go.ke/download/"
        "national-government-budget-implementation-review-report-fy-2024-2025/"
    ),
    "FY2023/24": (
        "https://cob.go.ke/download/"
        "national-government-budget-implementation-review-report-fy-2023-2024/"
    ),
}

CACHE_DIR = Path("data/pending_bills_cache")
USER_AGENT = (
    "KenyaAuditApp/1.0 (+https://github.com/Rodgers31/audit_app-) "
    "Transparency Research"
)

# Patterns to find pending bills tables in PDF text
PENDING_BILLS_PATTERNS = [
    re.compile(r"pending\s+bills?", re.IGNORECASE),
    re.compile(r"unpaid\s+(?:invoices?|obligations?)", re.IGNORECASE),
    re.compile(r"arrears", re.IGNORECASE),
    re.compile(r"outstanding\s+(?:payments?|bills?)", re.IGNORECASE),
]


class PendingBillsExtractor:
    """Extract pending bills data from COB reports."""

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def extract_all(self) -> dict[str, Any]:
        """Run the full extraction pipeline.

        Returns structured pending bills data:
        {
            "pending_bills": [
                {
                    "entity_name": "...",
                    "entity_type": "national" | "county",
                    "category": "mda" | "county" | "state_corporation",
                    "fiscal_year": "FY2024/25",
                    "total_pending": 123456789.0,
                    "eligible_pending": 100000000.0,
                    "ineligible_pending": 23456789.0,
                    "notes": "...",
                }
            ],
            "summary": {
                "total_national": ...,
                "total_county": ...,
                "grand_total": ...,
                "fiscal_year": "...",
                "as_at_date": "...",
            },
            "source_url": "...",
            "source_title": "...",
            "extracted_at": "...",
        }
        """
        logger.info("Starting pending bills extraction from COB reports")
        results: dict[str, Any] = {
            "pending_bills": [],
            "summary": {},
            "source_url": COB_NATIONAL_REPORTS,
            "source_title": "",
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        }

        # Step 1: Discover the latest report
        report_url, fiscal_year = await self._discover_latest_report()
        if not report_url:
            logger.warning(
                "Could not discover latest COB report. " "Trying known report pages..."
            )
            for fy, url in KNOWN_REPORT_PAGES.items():
                report_url = url
                fiscal_year = fy
                break

        if not report_url:
            logger.error("No COB report found for pending bills extraction")
            return results

        logger.info(f"Found report: {report_url} ({fiscal_year})")
        results["source_url"] = report_url
        results["source_title"] = (
            f"COB National Government Budget Implementation "
            f"Review Report {fiscal_year}"
        )

        # Step 2: Download the PDF
        pdf_path = await self._download_report_pdf(report_url)
        if not pdf_path:
            logger.error("Failed to download report PDF")
            return results

        # Step 3: Extract pending bills tables from PDF
        bills_data = self._extract_pending_bills_from_pdf(pdf_path, fiscal_year)
        results["pending_bills"] = bills_data.get("bills", [])
        results["summary"] = bills_data.get("summary", {})

        logger.info(
            f"Extracted {len(results['pending_bills'])} pending bills entries "
            f"totalling KES {results['summary'].get('grand_total', 0):,.0f}"
        )
        return results

    async def _discover_latest_report(
        self,
    ) -> tuple[Optional[str], Optional[str]]:
        """Scrape COB reports page to find the latest budget review report."""
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(
                    COB_NATIONAL_REPORTS,
                    headers={"User-Agent": USER_AGENT},
                )
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                # Look for links to budget implementation review reports
                report_links: list[tuple[str, str]] = []
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"]
                    text = a_tag.get_text(strip=True).lower()
                    if (
                        "budget-implementation" in href.lower()
                        or "budget implementation" in text
                    ) and ("national" in href.lower() or "national" in text):
                        # Extract fiscal year from text or URL
                        fy_match = re.search(
                            r"(?:fy\s*)?(\d{4})[/-](\d{2,4})", text + " " + href
                        )
                        fy = ""
                        if fy_match:
                            start = fy_match.group(1)
                            end = fy_match.group(2)
                            if len(end) == 2:
                                end = start[:2] + end
                            fy = f"FY{start}/{end[-2:]}"
                        full_url = urljoin(COB_BASE, href)
                        report_links.append((full_url, fy))

                if report_links:
                    # Sort by fiscal year descending, take latest
                    report_links.sort(key=lambda x: x[1], reverse=True)
                    return report_links[0]

        except Exception as exc:
            logger.warning(
                f"Failed to scrape COB reports page: {exc}. "
                f"Falling back to known URLs."
            )

        return None, None

    async def _download_report_pdf(self, report_page_url: str) -> Optional[Path]:
        """Download the report PDF from a COB download page.

        COB uses WordPress Download Manager, so we may need headless
        browser to resolve the actual download link.
        """
        # Check cache first
        url_hash = re.sub(r"[^\w]", "_", report_page_url)[-60:]
        cached_pdf = self.cache_dir / f"cob_report_{url_hash}.pdf"
        if cached_pdf.exists():
            age_hours = (datetime.now().timestamp() - cached_pdf.stat().st_mtime) / 3600
            if age_hours < 168:  # 1 week cache
                logger.info(f"Using cached PDF: {cached_pdf}")
                return cached_pdf

        # Try headless browser first (COB uses WPDM protected downloads)
        try:
            from .cob_headless import fetch_cob_download, headless_allowed

            if headless_allowed():
                logger.info(f"Attempting headless download from {report_page_url}")
                result = await fetch_cob_download(report_page_url)
                if result:
                    pdf_bytes, filename = result
                    if pdf_bytes and pdf_bytes.startswith(b"%PDF"):
                        cached_pdf.write_bytes(pdf_bytes)
                        logger.info(
                            f"Downloaded PDF via headless: " f"{len(pdf_bytes)} bytes"
                        )
                        return cached_pdf
        except Exception as exc:
            logger.warning(f"Headless download failed: {exc}")

        # Fallback: try direct HTTP with common WPDM patterns
        try:
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                # First, get the download page to find the actual PDF link
                resp = await client.get(
                    report_page_url,
                    headers={"User-Agent": USER_AGENT},
                )
                soup = BeautifulSoup(resp.text, "html.parser")

                # Look for direct PDF links
                pdf_links: list[str] = []
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"]
                    if href.lower().endswith(".pdf"):
                        pdf_links.append(urljoin(COB_BASE, href))

                # Also check for WPDM download links
                for a_tag in soup.find_all(
                    "a",
                    class_=re.compile(r"wpdm", re.IGNORECASE),
                ):
                    href = a_tag.get("href", "")
                    if href:
                        pdf_links.append(urljoin(COB_BASE, href))

                for pdf_url in pdf_links:
                    try:
                        pdf_resp = await client.get(
                            pdf_url,
                            headers={"User-Agent": USER_AGENT},
                        )
                        if (
                            pdf_resp.status_code == 200
                            and pdf_resp.content[:4] == b"%PDF"
                        ):
                            cached_pdf.write_bytes(pdf_resp.content)
                            logger.info(
                                f"Downloaded PDF: {len(pdf_resp.content)} bytes"
                            )
                            return cached_pdf
                    except Exception:
                        continue

        except Exception as exc:
            logger.warning(f"Direct PDF download failed: {exc}")

        return None

    def _extract_pending_bills_from_pdf(
        self, pdf_path: Path, fiscal_year: str
    ) -> dict[str, Any]:
        """Extract pending bills tables from a COB budget review PDF.

        Typical COB report structure for pending bills:
        - Chapter/section on "Pending Bills"
        - Summary table with columns: Vote, Ministry/MDA, Total Pending,
          Eligible, Ineligible
        - May include county-level breakdown in separate chapter
        """
        result: dict[str, Any] = {"bills": [], "summary": {}}

        try:
            import pdfplumber
        except ImportError:
            logger.error("pdfplumber not installed — cannot extract PDF tables")
            return result

        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                total_pages = len(pdf.pages)
                logger.info(f"Opened PDF: {total_pages} pages")

                # Phase 1: Find pages containing pending bills content
                pending_pages: list[int] = []
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    if any(p.search(text) for p in PENDING_BILLS_PATTERNS):
                        pending_pages.append(i)

                if not pending_pages:
                    logger.warning(
                        "No pending bills sections found in PDF. "
                        "Trying broader search..."
                    )
                    # Try extracting all tables and searching content
                    for i, page in enumerate(pdf.pages):
                        tables = page.extract_tables()
                        for table in tables:
                            flat = " ".join(
                                str(cell) for row in table for cell in row if cell
                            ).lower()
                            if "pending" in flat and (
                                "bill" in flat or "amount" in flat
                            ):
                                pending_pages.append(i)
                                break

                logger.info(
                    f"Found pending bills content on "
                    f"{len(pending_pages)} pages: {pending_pages[:10]}"
                )

                # Phase 2: Extract tables from pending bills pages
                all_rows: list[dict[str, Any]] = []
                for page_idx in pending_pages:
                    page = pdf.pages[page_idx]
                    tables = page.extract_tables()

                    for table in tables:
                        parsed = self._parse_pending_bills_table(table, fiscal_year)
                        all_rows.extend(parsed)

                # Phase 3: Also try text extraction for summary figures
                summary = self._extract_summary_from_text(
                    pdf, pending_pages, fiscal_year
                )

                result["bills"] = all_rows
                result["summary"] = summary

                # If tables didn't yield data but we found summary text
                if not all_rows and summary.get("grand_total"):
                    logger.info(
                        "Table extraction yielded no rows but "
                        "text extraction found summary figures"
                    )

        except Exception as exc:
            logger.exception(f"PDF extraction failed: {exc}")

        return result

    def _parse_pending_bills_table(
        self, table: list[list], fiscal_year: str
    ) -> list[dict[str, Any]]:
        """Parse a single table that may contain pending bills data.

        Expected column patterns:
        - Vote/No | Ministry/Entity | Total Pending | Eligible | Ineligible
        - Entity | Amount (KES) | Status | Verification
        """
        rows: list[dict[str, Any]] = []
        if not table or len(table) < 2:
            return rows

        # Try to identify header row
        header_row = table[0]
        header_text = [str(cell).lower().strip() if cell else "" for cell in header_row]

        # Find relevant column indices
        entity_col = None
        total_col = None
        eligible_col = None
        ineligible_col = None

        for idx, h in enumerate(header_text):
            if any(
                kw in h
                for kw in [
                    "ministry",
                    "mda",
                    "entity",
                    "vote",
                    "department",
                    "name",
                ]
            ):
                entity_col = idx
            elif "ineligible" in h:
                ineligible_col = idx
            elif "eligible" in h:
                eligible_col = idx
            elif any(kw in h for kw in ["total", "amount", "pending", "outstanding"]):
                total_col = idx

        if entity_col is None:
            # Try second row as header
            if len(table) > 2:
                header_row = table[1]
                header_text = [
                    str(cell).lower().strip() if cell else "" for cell in header_row
                ]
                for idx, h in enumerate(header_text):
                    if any(
                        kw in h for kw in ["ministry", "mda", "entity", "vote", "name"]
                    ):
                        entity_col = idx
                    elif "ineligible" in h:
                        ineligible_col = idx
                    elif "eligible" in h:
                        eligible_col = idx
                    elif any(kw in h for kw in ["total", "amount", "pending"]):
                        total_col = idx

        if entity_col is None:
            return rows

        # Parse data rows
        data_start = 1 if entity_col is not None else 2
        for row_idx in range(data_start, len(table)):
            row = table[row_idx]
            if not row or len(row) <= entity_col:
                continue

            entity = str(row[entity_col] or "").strip()
            if not entity or entity.lower() in (
                "total",
                "grand total",
                "sub-total",
                "",
            ):
                continue

            # Skip header-like rows
            if any(
                kw in entity.lower() for kw in ["ministry", "mda", "entity", "vote"]
            ):
                continue

            total_val = self._parse_amount(
                row[total_col]
                if total_col is not None and len(row) > total_col
                else None
            )
            eligible_val = self._parse_amount(
                row[eligible_col]
                if eligible_col is not None and len(row) > eligible_col
                else None
            )
            ineligible_val = self._parse_amount(
                row[ineligible_col]
                if ineligible_col is not None and len(row) > ineligible_col
                else None
            )

            if total_val is None and eligible_val is None:
                continue

            if total_val is None and eligible_val is not None:
                total_val = eligible_val + (ineligible_val or 0)

            rows.append(
                {
                    "entity_name": entity,
                    "entity_type": "national",
                    "category": "mda",
                    "fiscal_year": fiscal_year,
                    "total_pending": total_val or 0,
                    "eligible_pending": eligible_val,
                    "ineligible_pending": ineligible_val,
                }
            )

        return rows

    def _extract_summary_from_text(
        self, pdf: Any, pending_pages: list[int], fiscal_year: str
    ) -> dict[str, Any]:
        """Extract summary pending bills figures from PDF text.

        Looks for patterns like:
        - "total pending bills amounted to KES 397 billion"
        - "national government pending bills stood at KES X"
        - "county pending bills of KES Y"
        """
        summary: dict[str, Any] = {
            "fiscal_year": fiscal_year,
            "as_at_date": None,
            "total_national": None,
            "total_county": None,
            "grand_total": None,
        }

        # Collect text from relevant pages (and surrounding pages for context)
        pages_to_check = set(pending_pages)
        for p in list(pending_pages):
            pages_to_check.add(max(0, p - 1))
            pages_to_check.add(min(len(pdf.pages) - 1, p + 1))

        full_text = ""
        for page_idx in sorted(pages_to_check):
            text = pdf.pages[page_idx].extract_text() or ""
            full_text += text + "\n"

        # Amount extraction patterns (KES billions/millions)
        def _find_amount(pattern: str) -> Optional[float]:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(",", "").strip()
                try:
                    val = float(amount_str)
                    # Determine multiplier from context
                    context = full_text[
                        max(0, match.start() - 30) : match.end() + 30
                    ].lower()
                    if "trillion" in context:
                        return val * 1e12
                    elif "billion" in context:
                        return val * 1e9
                    elif "million" in context:
                        return val * 1e6
                    elif val < 100:
                        # Likely billions
                        return val * 1e9
                    elif val < 100_000:
                        # Likely millions
                        return val * 1e6
                    return val
                except ValueError:
                    pass
            return None

        # Look for national pending bills total
        for pattern in [
            r"(?:national\s+government\s+)?pending\s+bills?\s+(?:amounted?\s+to|stood\s+at|of|totall?(?:ed|ing)?)\s*(?:KES|Ksh\.?|Kshs?\.?)?\s*([\d,\.]+)",
            r"(?:total\s+)?pending\s+bills?\s*(?:of|at|:)?\s*(?:KES|Ksh\.?|Kshs?\.?)?\s*([\d,\.]+)\s*(?:billion|million|trillion)",
            r"(?:KES|Ksh\.?|Kshs?\.?)\s*([\d,\.]+)\s*(?:billion|million|trillion)?\s*(?:in\s+)?pending\s+bills?",
        ]:
            val = _find_amount(pattern)
            if val and val > 1e6:
                if summary["total_national"] is None:
                    summary["total_national"] = val
                    break

        # Look for county pending bills
        for pattern in [
            r"county\s+(?:government\s+)?pending\s+bills?\s+(?:amounted?\s+to|stood\s+at|of)\s*(?:KES|Ksh\.?|Kshs?\.?)?\s*([\d,\.]+)",
            r"county\s+.*?(?:KES|Ksh\.?|Kshs?\.?)\s*([\d,\.]+)\s*(?:billion|million|trillion)?\s*(?:in\s+)?pending",
        ]:
            val = _find_amount(pattern)
            if val and val > 1e6:
                if summary["total_county"] is None:
                    summary["total_county"] = val
                    break

        # Look for date "as at" reference
        date_match = re.search(
            r"as\s+at\s+(\w+\s+\d{1,2}[,]?\s+\d{4}|\d{1,2}\s+\w+\s+\d{4})",
            full_text,
            re.IGNORECASE,
        )
        if date_match:
            summary["as_at_date"] = date_match.group(1).strip()

        # Calculate grand total
        national = summary.get("total_national") or 0
        county = summary.get("total_county") or 0
        if national or county:
            summary["grand_total"] = national + county

        return summary

    @staticmethod
    def _parse_amount(value: Any) -> Optional[float]:
        """Parse a string/number into a float amount."""
        if value is None:
            return None
        s = str(value).strip().replace(",", "").replace(" ", "")
        # Remove currency prefixes
        s = re.sub(r"^(?:KES|Ksh\.?|Kshs?\.?)\s*", "", s, flags=re.IGNORECASE)
        if not s or s == "-" or s.lower() in ("nil", "n/a", "none"):
            return None
        try:
            return float(s)
        except ValueError:
            return None


# ── CLI entry point ──────────────────────────────────────────────────────


async def _main() -> None:
    """Run the extractor standalone for testing."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    extractor = PendingBillsExtractor()
    data = await extractor.extract_all()

    import json

    print(json.dumps(data, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(_main())
