"""PDF parsing utilities for extracting structured data from government reports.

This module provides parsers for:
1. Controller of Budget (CoB) quarterly budget execution reports
2. Office of Auditor General (OAG) annual audit reports
3. National Treasury debt bulletins

Each parser handles specific document formats and table structures.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pdfplumber
from pdfplumber.page import Page

logger = logging.getLogger(__name__)


@dataclass
class ExtractedTable:
    """Represents a table extracted from a PDF with metadata."""

    page_number: int
    table_index: int  # Index on the page (0, 1, 2...)
    headers: List[str]
    rows: List[List[str]]
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1)

    @property
    def row_count(self) -> int:
        """Return number of data rows (excluding header)."""
        return len(self.rows)

    def to_dicts(self) -> List[Dict[str, str]]:
        """Convert table rows to list of dictionaries using headers as keys."""
        return [dict(zip(self.headers, row)) for row in self.rows]


class PDFParserError(Exception):
    """Base exception for PDF parsing errors."""

    pass


class PDFNotFoundError(PDFParserError):
    """Raised when PDF file is not found."""

    pass


class PDFCorruptedError(PDFParserError):
    """Raised when PDF file cannot be opened or is corrupted."""

    pass


class TableNotFoundError(PDFParserError):
    """Raised when expected table is not found in PDF."""

    pass


def extract_all_tables(pdf_path: Path) -> List[ExtractedTable]:
    """
    Extract all tables from a PDF document.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        List of ExtractedTable objects, one for each table found

    Raises:
        PDFNotFoundError: If PDF file does not exist
        PDFCorruptedError: If PDF cannot be opened
    """
    if not pdf_path.exists():
        raise PDFNotFoundError(f"PDF file not found: {pdf_path}")

    extracted_tables: List[ExtractedTable] = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                page_tables = page.extract_tables()

                for table_idx, table_data in enumerate(page_tables):
                    if not table_data or len(table_data) < 2:
                        # Skip empty tables or tables with only header
                        continue

                    # First row is typically headers
                    headers = [
                        str(cell).strip() if cell else "" for cell in table_data[0]
                    ]
                    rows = [
                        [str(cell).strip() if cell else "" for cell in row]
                        for row in table_data[1:]
                    ]

                    # Get table bounding box if available
                    bbox = page.bbox if hasattr(page, "bbox") else (0, 0, 0, 0)

                    extracted_tables.append(
                        ExtractedTable(
                            page_number=page_num,
                            table_index=table_idx,
                            headers=headers,
                            rows=rows,
                            bbox=bbox,
                        )
                    )

    except Exception as e:
        raise PDFCorruptedError(f"Failed to parse PDF {pdf_path}: {e}") from e

    logger.info(
        f"Extracted {len(extracted_tables)} tables from {pdf_path.name}",
        extra={"pdf": str(pdf_path), "table_count": len(extracted_tables)},
    )

    return extracted_tables


def extract_text_from_pdf(pdf_path: Path, pages: Optional[List[int]] = None) -> str:
    """
    Extract plain text from PDF pages.

    Args:
        pdf_path: Path to the PDF file
        pages: Optional list of page numbers to extract (1-indexed). If None, extract all pages.

    Returns:
        Concatenated text from specified pages

    Raises:
        PDFNotFoundError: If PDF file does not exist
        PDFCorruptedError: If PDF cannot be opened
    """
    if not pdf_path.exists():
        raise PDFNotFoundError(f"PDF file not found: {pdf_path}")

    text_parts: List[str] = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_indices = [p - 1 for p in pages] if pages else range(len(pdf.pages))

            for page_idx in page_indices:
                if 0 <= page_idx < len(pdf.pages):
                    page = pdf.pages[page_idx]
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)

    except Exception as e:
        raise PDFCorruptedError(f"Failed to extract text from {pdf_path}: {e}") from e

    return "\n\n".join(text_parts)


def parse_currency(value: str, default_currency: str = "KES") -> Tuple[Decimal, str]:
    """
    Parse a currency string to Decimal amount and currency code.

    Examples:
        "KES 1,234,567.89" -> (Decimal('1234567.89'), 'KES')
        "1,234,567" -> (Decimal('1234567'), 'KES')
        "$1,234.56" -> (Decimal('1234.56'), 'USD')

    Args:
        value: Currency string to parse
        default_currency: Currency code to use if not found in string

    Returns:
        Tuple of (amount, currency_code)
    """
    # Remove common formatting
    cleaned = value.strip().replace(",", "").replace(" ", "")

    # Try to find currency code
    currency_match = re.search(r"[A-Z]{3}", cleaned)
    currency = currency_match.group(0) if currency_match else default_currency

    # Extract numeric value
    number_match = re.search(r"-?\d+\.?\d*", cleaned)
    if not number_match:
        logger.warning(f"Could not parse currency value: {value}")
        return Decimal("0"), currency

    amount = Decimal(number_match.group(0))
    return amount, currency


def parse_percentage(value: str) -> Optional[float]:
    """
    Parse a percentage string to float.

    Examples:
        "85.5%" -> 85.5
        "85.5" -> 85.5
        "N/A" -> None

    Args:
        value: Percentage string to parse

    Returns:
        Float percentage value or None if parsing fails
    """
    cleaned = value.strip().replace("%", "").replace(",", "")

    if cleaned.upper() in ["N/A", "NA", "-", ""]:
        return None

    try:
        return float(cleaned)
    except ValueError:
        logger.warning(f"Could not parse percentage: {value}")
        return None


def find_table_by_header(
    tables: List[ExtractedTable], header_keywords: List[str]
) -> Optional[ExtractedTable]:
    """
    Find the first table whose headers contain all specified keywords.

    Args:
        tables: List of extracted tables to search
        header_keywords: Keywords that should appear in table headers (case-insensitive)

    Returns:
        First matching table or None if not found
    """
    for table in tables:
        header_text = " ".join(table.headers).lower()
        if all(keyword.lower() in header_text for keyword in header_keywords):
            return table

    return None


class CoBQuarterlyReportParser:
    """Parser for Controller of Budget quarterly budget execution reports."""

    def __init__(self, pdf_path: Path):
        """
        Initialize parser with PDF path.

        Args:
            pdf_path: Path to CoB quarterly report PDF
        """
        self.pdf_path = pdf_path
        self.tables: List[ExtractedTable] = []

    def parse(self) -> List[Dict[str, Any]]:
        """
        Parse CoB report and extract budget execution data.

        Returns:
            List of budget execution records with structure:
            {
                "county": "Nairobi",
                "allocated": Decimal("1500000000"),
                "absorbed": Decimal("1200000000"),
                "absorption_rate": 80.0,
                "quarter": "Q2",
                "fiscal_year": "2023/24",
                "currency": "KES"
            }

        Raises:
            TableNotFoundError: If county budget table not found
        """
        self.tables = extract_all_tables(self.pdf_path)

        # Look for county budget execution table
        budget_table = find_table_by_header(
            self.tables, ["county", "allocated", "absorbed"]
        )

        if not budget_table:
            raise TableNotFoundError(
                "Could not find county budget execution table in report"
            )

        records = []
        for row in budget_table.rows:
            try:
                # Assuming table structure: County | Allocated | Absorbed | Rate
                county_name = row[0].strip()

                # Skip summary/total rows
                if any(
                    keyword in county_name.lower()
                    for keyword in ["total", "average", "summary"]
                ):
                    continue

                allocated, currency = parse_currency(row[1])
                absorbed, _ = parse_currency(row[2])
                absorption_rate = parse_percentage(row[3])

                record = {
                    "county": county_name,
                    "allocated": allocated,
                    "absorbed": absorbed,
                    "absorption_rate": absorption_rate,
                    "currency": currency,
                    # Extract quarter and FY from filename or text
                    "quarter": self._extract_quarter(),
                    "fiscal_year": self._extract_fiscal_year(),
                }

                records.append(record)

            except (IndexError, ValueError) as e:
                logger.warning(f"Failed to parse row {row}: {e}")
                continue

        logger.info(
            f"Parsed {len(records)} budget execution records from CoB report",
            extra={"source": str(self.pdf_path), "record_count": len(records)},
        )

        return records

    def _extract_quarter(self) -> str:
        """Extract quarter from PDF filename or content."""
        # Try filename pattern: "Q2-2023-24.pdf"
        quarter_match = re.search(r"Q([1-4])", self.pdf_path.name, re.IGNORECASE)
        if quarter_match:
            return f"Q{quarter_match.group(1)}"

        # Default to Q1 if not found
        return "Q1"

    def _extract_fiscal_year(self) -> str:
        """Extract fiscal year from PDF filename or content."""
        # Try pattern: "2023-24" or "2023/24"
        fy_match = re.search(r"(\d{4})[-/](\d{2,4})", self.pdf_path.name)
        if fy_match:
            year1, year2 = fy_match.groups()
            # Normalize to YYYY/YY format
            return f"{year1}/{year2[-2:]}"

        # Default to current FY
        return "2024/25"


class OAGAuditReportParser:
    """Parser for Office of Auditor General audit reports."""

    def __init__(self, pdf_path: Path):
        """
        Initialize parser with PDF path.

        Args:
            pdf_path: Path to OAG audit report PDF
        """
        self.pdf_path = pdf_path
        self.full_text: str = ""

    def parse(self) -> Dict[str, Any]:
        """
        Parse OAG audit report and extract key information.

        Returns:
            Dictionary with audit report data:
            {
                "county": "Nairobi",
                "fiscal_year": "2022/23",
                "opinion": "Unqualified",
                "findings": ["Finding 1 text...", "Finding 2 text..."],
                "recommendations": ["Rec 1...", "Rec 2..."]
            }
        """
        self.full_text = extract_text_from_pdf(self.pdf_path)

        return {
            "county": self._extract_county(),
            "fiscal_year": self._extract_fiscal_year(),
            "opinion": self._extract_opinion(),
            "findings": self._extract_findings(),
            "recommendations": self._extract_recommendations(),
        }

    def _extract_county(self) -> str:
        """Extract county name from report."""
        # Look for pattern: "County Government of [County Name]"
        match = re.search(
            r"County Government of ([A-Za-z\s]+?)(?:\s+for|\s+FOR)",
            self.full_text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip().title()
        return "Unknown"

    def _extract_fiscal_year(self) -> str:
        """Extract fiscal year from report."""
        match = re.search(r"(\d{4})/(\d{2,4})", self.full_text)
        if match:
            year1, year2 = match.groups()
            return f"{year1}/{year2[-2:]}"
        return "Unknown"

    def _extract_opinion(self) -> str:
        """Extract audit opinion from report."""
        opinion_keywords = [
            "Unqualified",
            "Qualified",
            "Adverse",
            "Disclaimer of Opinion",
        ]

        # Look for opinion section
        opinion_section = re.search(
            r"Opinion(.{200})", self.full_text, re.IGNORECASE | re.DOTALL
        )

        if opinion_section:
            text = opinion_section.group(1)
            for keyword in opinion_keywords:
                if keyword.lower() in text.lower():
                    return keyword

        return "Unknown"

    def _extract_findings(self) -> List[str]:
        """Extract audit findings from report."""
        # This is a simplified extraction - real implementation would need
        # more sophisticated NLP or pattern matching
        findings = []

        # Look for numbered findings
        finding_matches = re.finditer(
            r"(?:Finding|Issue)\s+\d+[:\.](.{100,500})", self.full_text, re.DOTALL
        )

        for match in finding_matches:
            findings.append(match.group(1).strip())

        return findings[:10]  # Limit to first 10 findings

    def _extract_recommendations(self) -> List[str]:
        """Extract recommendations from report."""
        recommendations = []

        # Look for recommendation sections
        rec_matches = re.finditer(
            r"(?:Recommendation|The Auditor recommends)(.{100,300})",
            self.full_text,
            re.DOTALL,
        )

        for match in rec_matches:
            recommendations.append(match.group(1).strip())

        return recommendations[:10]  # Limit to first 10


class TreasuryDebtBulletinParser:
    """Parser for National Treasury public debt bulletins."""

    def __init__(self, pdf_path: Path):
        """
        Initialize parser with PDF path.

        Args:
            pdf_path: Path to Treasury debt bulletin PDF
        """
        self.pdf_path = pdf_path
        self.tables: List[ExtractedTable] = []

    def parse(self) -> List[Dict[str, Any]]:
        """
        Parse debt bulletin and extract loan data.

        Returns:
            List of loan records with structure:
            {
                "lender": "World Bank",
                "principal": Decimal("50000000000"),
                "outstanding": Decimal("45000000000"),
                "currency": "KES",
                "loan_type": "Bilateral/Multilateral/Commercial"
            }
        """
        self.tables = extract_all_tables(self.pdf_path)

        # Look for debt schedule table
        debt_table = find_table_by_header(
            self.tables, ["lender", "principal", "outstanding"]
        )

        if not debt_table:
            logger.warning("Could not find debt schedule table")
            return []

        records = []
        for row in debt_table.rows:
            try:
                lender = row[0].strip()

                # Skip summary rows
                if any(
                    keyword in lender.lower()
                    for keyword in ["total", "sub-total", "grand"]
                ):
                    continue

                principal, currency = parse_currency(row[1])
                outstanding, _ = parse_currency(row[2])

                record = {
                    "lender": lender,
                    "principal": principal,
                    "outstanding": outstanding,
                    "currency": currency,
                    "loan_type": self._classify_loan_type(lender),
                }

                records.append(record)

            except (IndexError, ValueError) as e:
                logger.warning(f"Failed to parse debt row {row}: {e}")
                continue

        logger.info(
            f"Parsed {len(records)} loan records from debt bulletin",
            extra={"source": str(self.pdf_path), "record_count": len(records)},
        )

        return records

    def _classify_loan_type(self, lender: str) -> str:
        """Classify loan type based on lender name."""
        lender_lower = lender.lower()

        if any(
            org in lender_lower
            for org in ["world bank", "imf", "african development", "adb"]
        ):
            return "Multilateral"

        if any(
            country in lender_lower
            for country in ["china", "france", "japan", "uk", "usa"]
        ):
            return "Bilateral"

        if any(word in lender_lower for word in ["bond", "eurobond", "commercial"]):
            return "Commercial"

        return "Other"
