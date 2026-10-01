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
import math
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


def _incompatible_pending_context(context: str, fiscal_year: str) -> bool:
    """Reject explicitly incompatible currencies, periods and accounting bases."""
    currencies = {m.upper() for m in re.findall(r"\b(KES|USD|EUR|GBP)\b", context, re.I)}
    periods = {
        (int(start), int(end) if len(end) == 4 else int(start[:2] + end))
        for start, end in re.findall(r"\b(?:FY\s*)?((?:19|20)\d{2})[/-](\d{4}|\d{2})\b", context, re.I)
    }
    expected = re.search(r"((?:19|20)\d{2})/(\d{4}|\d{2})", fiscal_year)
    expected_period = (int(expected[1]), int(expected[1]) + 1) if expected else None
    lower = context.lower()
    return (
        bool(currencies - {"KES"})
        or any(period != expected_period for period in periods)
        or any(word in lower for word in ("projected", "modelled", "estimated"))
        or ("cash" in lower and "accrual" in lower)
    )


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

        logger.info("Extracted %s pending bills entries; grand_total=%s absent_reason=%s",
                    len(results["pending_bills"]), results["summary"].get("grand_total"),
                    results["summary"].get("grand_total_absent_reason"))
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
        if not isinstance(table, (list, tuple)) or len(table) < 2 or not isinstance(table[0], (list, tuple)):
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
            if len(table) > 2 and isinstance(table[1], (list, tuple)):
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
            if not isinstance(row, (list, tuple)) or len(row) <= entity_col:
                logger.warning("Skipping malformed pending-bill row %s", row_idx)
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

            context = " ".join(header_text)
            years = set(re.findall(r"\b(?:19|20)\d{2}\b", context))
            fy_match = re.search(r"((?:19|20)\d{2})/(\d{2}|\d{4})", fiscal_year)
            expected_years = {fy_match[1], str(int(fy_match[1]) + 1)} if fy_match else set()
            amount_headers = [header_text[i] for i in (total_col, eligible_col, ineligible_col) if i is not None]
            # Raw component values cannot be added across different printed
            # scales or observation years, even within one fiscal-year range.
            year_contexts = {tuple(sorted(re.findall(r"\b(?:19|20)\d{2}\b", h))) for h in amount_headers}
            unit_contexts = {tuple(re.findall(r"\b(?:trillion|billion|million|thousand)\b", h)) for h in amount_headers}
            year_contexts.discard(())
            unit_contexts.discard(())
            incompatible = (
                _incompatible_pending_context(context, fiscal_year)
                or bool(years - expected_years)
                or len(year_contexts) > 1
                or len(unit_contexts) > 1
            )
            reason = None
            if incompatible:
                total_val = None
                reason = "incompatible_component_context"
            elif total_val is None:
                if eligible_val is not None and ineligible_val is not None:
                    total_val = eligible_val + ineligible_val
                    if not math.isfinite(total_val):
                        total_val = None
                        reason = "invalid_component_total"
                else:
                    reason = "incomplete_components"
            elif eligible_val is not None and ineligible_val is not None:
                if not math.isclose(total_val, eligible_val + ineligible_val, rel_tol=1e-9, abs_tol=0.01):
                    total_val = None
                    reason = "conflicting_components"

            rows.append(
                {
                    "entity_name": entity,
                    "entity_type": "national",
                    "category": "mda",
                    "fiscal_year": fiscal_year,
                    "total_pending": total_val,
                    "total_pending_absent_reason": reason,
                    "printed_zero": total_val == 0,
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

        # Require explicit institution and unit; a county-only sentence cannot
        # stand in for a national observation, nor can nearby units scale it.
        def component(scope):
            pattern = (
                scope + r"\s+pending\s+bills?\s+(?:amounted?\s+to|stood\s+at|of|totall?(?:ed|ing)?)"
                r"\s*(?:KES|Ksh\.?|Kshs?\.?)?\s*([\d,\.]+)\s*(trillion|billion|million)\b"
            )
            values = set()
            for match in re.finditer(pattern, full_text, re.I):
                amount = self._parse_amount(match[1])
                if amount is None:
                    return None, "not_reported_or_invalid"
                value = amount * {"trillion": 1e12, "billion": 1e9, "million": 1e6}[match[2].lower()]
                if not math.isfinite(value):
                    return None, "not_reported_or_invalid"
                values.add(value)
            if len(values) > 1:
                return None, "conflicting_component_observations"
            return (next(iter(values)), None) if values else (None, "not_reported_or_invalid")

        incompatible = _incompatible_pending_context(full_text, fiscal_year)
        for key, scope in (("total_national", r"national\s+government"), ("total_county", r"county(?:\s+government)?")):
            value, absent_reason = component(scope)
            if incompatible:
                value, absent_reason = None, "incompatible_component_context"
            summary[key] = value
            summary[key + "_absent_reason"] = absent_reason
        summary["currency"] = None if incompatible else "KES"
        date_matches = re.findall(
            r"as\s+at\s+(\w+\s+\d{1,2}[,]?\s+\d{4}|\d{1,2}\s+\w+\s+\d{4})",
            full_text, re.I,
        )
        dates = set()
        invalid_date = False
        for raw in date_matches:
            parsed = False
            for fmt in ("%d %B %Y", "%B %d, %Y", "%B %d %Y"):
                try:
                    dates.add(datetime.strptime(raw, fmt).date().isoformat())
                    parsed = True
                    break
                except ValueError:
                    continue
            invalid_date |= not parsed
        summary["as_at_date"] = next(iter(dates)) if len(dates) == 1 else None
        national, county = summary["total_national"], summary["total_county"]
        reason = "incomplete_components"
        if national is not None and county is not None:
            if len(dates) != 1 or not date_matches or invalid_date:
                reason = "incompatible_or_missing_reporting_dates"
            else:
                total = national + county
                if math.isfinite(total):
                    summary["grand_total"] = total
                    reason = None
                else:
                    reason = "invalid_component_total"
        summary["grand_total_absent_reason"] = reason

        return summary

    @staticmethod
    def _parse_amount(value: Any) -> Optional[float]:
        """Finite nonnegative amounts; commas/spaces must be thousands groups."""
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value) if math.isfinite(value) and value >= 0 else None
        s = str(value).strip()
        s = re.sub(r"^(?:KES|Ksh\.?|Kshs?\.?)\s*", "", s, flags=re.I)
        if not re.fullmatch(r"(?:\d+|\d{1,3}(?:[, ]\d{3})+)(?:\.\d+)?", s):
            return None
        amount = float(s.replace(",", "").replace(" ", ""))
        return amount if math.isfinite(amount) and amount >= 0 else None


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
