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


def find_table_by_row_anchors(
    tables: List[ExtractedTable],
    anchors: List[str],
    *,
    min_matches: int = 30,
    column: int = 0,
    header_synonyms: Optional[List[List[str]]] = None,
) -> Optional[ExtractedTable]:
    """Find the table whose ``column`` matches the most ``anchors``.

    Robust alternative to ``find_table_by_header`` for cases where the
    table you want has a stable invariant in its row labels (e.g., a
    consolidated county table is the only table in the report whose
    first column lists 47 Kenyan counties — the column header text
    can drift forever and this still works).

    A real report typically has SEVERAL tables that all list every
    county (revenue, arrears, budget execution, expenditure, …). To
    pick the right one, callers can pass ``header_synonyms`` — the
    same shape as for ``find_column_index`` — and tables whose
    flattened header text doesn't satisfy at least one synonym group
    are demoted in the ranking. Anchor count is still primary; header
    match is the tiebreaker.

    Returns the highest-ranked table, or None if no candidate reaches
    ``min_matches`` anchors. Matching is case-insensitive substring;
    apostrophes are stripped so "Murang'a" lines up with the
    canonical "Muranga".
    """
    # Normalise on both sides: COB sometimes prints hyphenated forms
    # ("Taita-Taveta", "Trans-Nzoia") that wouldn't substring-match a
    # space-separated canonical anchor. Also collapse all unicode
    # apostrophes and dashes, then squish whitespace.
    def _normalise(s: str) -> str:
        s = s.lower().replace("'", "").replace("\u2019", "")
        # Map every dash variant (ASCII + unicode \u2010-\u2015) to a space.
        for ch in ("-", "\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015"):
            s = s.replace(ch, " ")
        return re.sub(r"\s+", " ", s).strip()

    normalised_anchors = [_normalise(a) for a in anchors]

    def _strip(s: str) -> str:
        return _normalise(s)

    candidates: List[Tuple[int, int, ExtractedTable]] = []  # (anchor_score, header_score, table)
    for table in tables:
        if not table.rows:
            continue
        col_values = [
            _strip(row[column]) if len(row) > column else ""
            for row in table.rows
        ]
        anchor_score = sum(
            1 for a in normalised_anchors if any(a in v for v in col_values)
        )
        if anchor_score < min_matches:
            continue
        header_score = 0
        if header_synonyms is not None:
            # Combine the original header row + the first data row so
            # two-row "group / sub-label" headers are scored as one.
            haystack = " ".join(table.headers).lower()
            if table.rows:
                haystack += " " + " ".join(table.rows[0]).lower()
            header_score = sum(
                1
                for group in header_synonyms
                if all(kw.lower() in haystack for kw in group)
            )
        candidates.append((anchor_score, header_score, table))

    if not candidates:
        return None
    # Rank: anchor_score primary (the whole point of "invariant-anchored"),
    # header_score as the tiebreaker for the common case where MANY tables
    # in one report happen to list all 47 counties (revenue, arrears,
    # expenditure …). Stable sort means PDF-order is the final tiebreaker.
    candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return candidates[0][2]


def rank_tables_by_row_anchors(
    tables: List[ExtractedTable],
    anchors: List[str],
    *,
    min_matches: int = 30,
    column: int = 0,
    header_synonyms: Optional[List[List[str]]] = None,
) -> List[ExtractedTable]:
    """Like ``find_table_by_row_anchors`` but returns ALL qualifying
    candidates ranked best-first, instead of only the top hit.

    Why this exists: in real reports, ranking-by-anchor-count can be
    fooled. A 700-page CoB BIRR has multiple tables that list all 47
    counties (Arrears, Expenditure, Pending Bills, …). The single-pick
    version commits to the top-scoring candidate even if that candidate
    turns out to be unparseable for the caller's use-case (e.g. Arrears
    has no "allocated" column). With the ranked list the caller can
    walk it, validating each table — if column resolution fails on
    candidate #1, fall through to candidate #2, etc. That makes the
    pipeline robust to noisy pdfplumber output and to PDFs where the
    "right" table isn't the highest-scoring one.

    Same scoring/normalisation as the single-pick version. Stable sort
    so PDF order breaks ties beyond anchor + header score.
    """
    def _normalise(s: str) -> str:
        s = s.lower().replace("'", "").replace("\u2019", "")
        for ch in ("-", "\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015"):
            s = s.replace(ch, " ")
        return re.sub(r"\s+", " ", s).strip()

    normalised_anchors = [_normalise(a) for a in anchors]
    candidates: List[Tuple[int, int, ExtractedTable]] = []
    for table in tables:
        if not table.rows:
            continue
        col_values = [
            _normalise(row[column]) if len(row) > column else ""
            for row in table.rows
        ]
        anchor_score = sum(
            1 for a in normalised_anchors if any(a in v for v in col_values)
        )
        if anchor_score < min_matches:
            continue
        header_score = 0
        if header_synonyms is not None:
            haystack = " ".join(table.headers).lower()
            if table.rows:
                haystack += " " + " ".join(table.rows[0]).lower()
            header_score = sum(
                1
                for group in header_synonyms
                if all(kw.lower() in haystack for kw in group)
            )
        candidates.append((anchor_score, header_score, table))
    candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [t for _, _, t in candidates]


def flatten_grouped_headers(table: ExtractedTable) -> ExtractedTable:
    """Fold a two-row "group label / sub-label" header into single labels.

    Many financial PDFs render headers like::

        | County | Budget Estimates       | Actual Expenditure     | Absorption |
        |        | Rec | Dev | Total      | Rec | Dev | Total      | Rec | ...  |

    pdfplumber treats the first row as the header and the second as
    data, which destroys positional column lookups. This helper
    detects that pattern (the second row has no numeric content but
    repeated short labels like Rec/Dev/Total/Q1/etc.) and produces a
    new ExtractedTable whose headers carry the combined label
    ("Budget Estimates Total"). Group labels forward-fill across
    empty cells.

    Returns the input unchanged when no grouping is detected.
    """
    if not table.rows:
        return table
    sub_row = [c.strip() for c in table.rows[0]]
    if not sub_row or all(not c for c in sub_row):
        return table
    # Heuristic: every non-empty cell must be SHORT and NON-NUMERIC for
    # the row to count as a sub-header (rules out actual data rows
    # whose first cell happens to be a county name).
    non_empty = [c for c in sub_row if c]
    looks_like_subheader = all(
        len(c) <= 25 and not _re_compiled_numeric.search(c) for c in non_empty
    )
    if not looks_like_subheader:
        return table
    # Forward-fill group labels across empties so each column inherits
    # the most recent group label.
    filled_groups: List[str] = []
    last_group = ""
    for cell in table.headers:
        cell = (cell or "").strip()
        if cell:
            last_group = cell
        filled_groups.append(last_group)
    # zip_longest, not zip — pdfplumber occasionally returns ragged
    # tables where the sub-row is shorter than the group-row. Truncating
    # would silently drop trailing columns and break find_column_index
    # downstream. Fillvalue "" so missing sub-labels just leave the
    # group label intact.
    from itertools import zip_longest
    combined = [
        " ".join(filter(None, [grp, sub])).strip()
        for grp, sub in zip_longest(filled_groups, sub_row, fillvalue="")
    ]
    return ExtractedTable(
        page_number=table.page_number,
        table_index=table.table_index,
        headers=combined,
        rows=table.rows[1:],
        bbox=table.bbox,
    )


def find_column_index(
    headers: List[str], synonym_groups: List[List[str]]
) -> Optional[int]:
    """Pick the first column whose header satisfies any synonym group.

    Each synonym group is a list of keywords ALL of which must appear
    (case-insensitive substring) in the header cell. The first group
    that matches any column wins. Useful when terminology has drifted
    across report vintages — pass multiple synonym groups in priority
    order and the matcher tries each in turn.

    Example::

        find_column_index(
            headers,
            [
                ["budget", "estimates", "total"],   # H1 FY2025/26 wording
                ["approved", "budget", "total"],    # alt phrasing
                ["allocated", "total"],             # legacy
                ["allocated"],                      # bare-bones legacy
            ],
        )
    """
    lowered = [(h or "").lower() for h in headers]
    for group in synonym_groups:
        for col_idx, header in enumerate(lowered):
            if all(kw.lower() in header for kw in group):
                return col_idx
    return None


# Module-level compiled regex used by flatten_grouped_headers. A digit
# appearing anywhere in a "sub-header" cell is a strong signal that
# we're looking at actual data, not headers.
_re_compiled_numeric = re.compile(r"\d")


# ──────────────────────────────────────────────────────────────────
# Canonical entity lists used as row-anchors for invariant-based
# table identification. Keep these in sync with the entities table.
# ──────────────────────────────────────────────────────────────────
KENYAN_COUNTIES: Tuple[str, ...] = (
    "Baringo", "Bomet", "Bungoma", "Busia", "Elgeyo Marakwet", "Embu",
    "Garissa", "Homa Bay", "Isiolo", "Kajiado", "Kakamega", "Kericho",
    "Kiambu", "Kilifi", "Kirinyaga", "Kisii", "Kisumu", "Kitui", "Kwale",
    "Laikipia", "Lamu", "Machakos", "Makueni", "Mandera", "Marsabit",
    "Meru", "Migori", "Mombasa", "Murang'a", "Nairobi", "Nakuru", "Nandi",
    "Narok", "Nyamira", "Nyandarua", "Nyeri", "Samburu", "Siaya",
    "Taita Taveta", "Tana River", "Tharaka Nithi", "Trans Nzoia",
    "Turkana", "Uasin Gishu", "Vihiga", "Wajir", "West Pokot",
)
assert len(KENYAN_COUNTIES) == 47, "Kenya has 47 counties"


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

        The Consolidated County BIRR PDFs publish at least four tables
        relevant to the Budget page:

        * Aggregate: ``County | Allocated | Absorbed | Absorption Rate``
          → emitted as ``category="Total"``.
        * Recurrent: ``County | Allocated | Absorbed | ...`` with the
          word "recurrent" in the header → ``category="Recurrent"``.
        * Development: same layout with "development" in the header →
          ``category="Development"``.
        * Personnel Emoluments: ``County | PE | Absorbed | ...`` with
          the header literal "Personnel Emoluments" → persisted as a
          sub-category under Recurrent so the /budget/overview
          Personnel Emoluments trust-guard check passes.

        Tables are looked up best-effort; missing ones emit a warning
        but don't raise, so older PDFs that only publish the aggregate
        still produce useful output.

        Returns:
            List of budget execution records with structure::

                {
                    "county": "Nairobi",
                    "category": "Total" | "Recurrent" | "Development"
                               | "Personnel Emoluments",
                    "subcategory": Optional[str],
                    "allocated": Decimal("1500000000"),
                    "absorbed": Decimal("1200000000"),
                    "absorption_rate": 80.0,
                    "quarter": "Q2",
                    "fiscal_year": "2023/24",
                    "currency": "KES"
                }

        Raises:
            TableNotFoundError: If the aggregate county budget table
                cannot be located — other categories are optional.
        """
        self.tables = extract_all_tables(self.pdf_path)

        # ── Primary path: invariant-anchored, validator-driven ─────
        # COB reword the table headers every couple of vintages
        # ("Allocated"/"Absorbed" → "Budget Estimates"/"Actual
        # Expenditure" in FY2025/26), but the row labels stay constant
        # — there are always 47 Kenyan counties down the left column.
        #
        # A 700-page BIRR typically has SEVERAL tables that list all
        # 47 counties (Arrears, Pending Bills, Recurrent/Development
        # Expenditure, the consolidated Budget Execution table, …).
        # Anchor-count ranking alone picks the wrong one in real PDFs:
        # the Arrears table on page 52 had 45 county hits and beat the
        # actual budget table on page 55 (39 hits) in CI run
        # 24934906752. The header-synonym tiebreaker is too easy to
        # spoof when pdfplumber returns degraded headers.
        #
        # Robust answer: get the RANKED candidate list and walk it,
        # validating each one against the parser's actual needs (can
        # we resolve a "Total allocated" column?). First validating
        # candidate wins; reject others with a debug log so future
        # mis-picks are visible.
        primary_total_synonyms: List[List[str]] = [
            ["budget", "estimates", "total"],
            ["approved", "budget", "total"],
            ["allocated", "total"],
            ["allocated"],
        ]
        ranked = rank_tables_by_row_anchors(
            self.tables,
            list(KENYAN_COUNTIES),
            min_matches=30,
            header_synonyms=[
                ["budget", "expenditure"],
                ["budget", "estimates", "actual"],
                ["approved", "actual"],
                ["allocated", "absorbed"],
                ["budget", "absorption"],
            ],
        )

        budget_table: Optional[ExtractedTable] = None
        for candidate in ranked:
            flat = flatten_grouped_headers(candidate)
            if find_column_index(flat.headers, primary_total_synonyms) is not None:
                budget_table = flat
                break
            logger.info(
                "Anchored candidate at page %d rejected — no Total allocated column",
                candidate.page_number,
                extra={"page": candidate.page_number, "headers": flat.headers},
            )

        # ── Legacy fallback: original 3-keyword header probe ───────
        # Kept so the existing test fixtures and any older PDFs that
        # still use the literal "allocated"/"absorbed" wording still
        # work. The anchor pass above handles every vintage we've
        # seen since 2024.
        if budget_table is None:
            legacy = find_table_by_header(
                self.tables, ["county", "allocated", "absorbed"]
            )
            if legacy is not None:
                budget_table = flatten_grouped_headers(legacy)

        if budget_table is None:
            raise TableNotFoundError(
                "Could not find county budget execution table in report"
            )

        records: List[Dict[str, Any]] = []

        # ── Extract Total / Recurrent / Development from the same
        # consolidated table by picking different sub-columns ──────
        for category, allocated_synonyms, absorbed_synonyms, rate_synonyms in [
            (
                "Total",
                [
                    ["budget", "estimates", "total"],
                    ["approved", "budget", "total"],
                    ["allocated", "total"],
                    ["allocated"],  # legacy single-column tables
                ],
                [
                    ["actual", "expenditure", "total"],
                    ["expenditure", "total"],
                    ["absorbed", "total"],
                    ["absorbed"],
                ],
                [
                    ["absorption", "rate", "total"],
                    ["absorption", "total"],
                    ["absorption", "rate"],
                    ["absorption"],
                    ["rate"],  # legacy fixture / older PDFs
                ],
            ),
            (
                "Recurrent",
                [
                    ["budget", "estimates", "rec"],
                    ["approved", "budget", "rec"],
                    ["recurrent", "allocated"],
                    ["recurrent", "budget"],
                ],
                [
                    ["actual", "expenditure", "rec"],
                    ["recurrent", "expenditure"],
                    ["recurrent", "absorbed"],
                ],
                [
                    ["absorption", "rate", "rec"],
                    ["recurrent", "absorption"],
                ],
            ),
            (
                "Development",
                [
                    ["budget", "estimates", "dev"],
                    ["approved", "budget", "dev"],
                    ["development", "allocated"],
                    ["development", "budget"],
                ],
                [
                    ["actual", "expenditure", "dev"],
                    ["development", "expenditure"],
                    ["development", "absorbed"],
                ],
                [
                    ["absorption", "rate", "dev"],
                    ["development", "absorption"],
                ],
            ),
        ]:
            allocated_col = find_column_index(budget_table.headers, allocated_synonyms)
            absorbed_col = find_column_index(budget_table.headers, absorbed_synonyms)
            rate_col = find_column_index(budget_table.headers, rate_synonyms)
            # We only require the allocated and absorbed columns;
            # absorption rate is derivable when missing.
            if allocated_col is None or absorbed_col is None:
                # Log at INFO not WARNING — categories CAN legitimately be
                # missing (e.g. older PDFs only carry the Total column;
                # the Recurrent / Development synonyms then won't match).
                # But silent-skip-without-signal makes partial-parse
                # failures invisible in nightly runs, so emit the
                # available headers so an operator can confirm.
                logger.info(
                    "Skipping consolidated category — required columns not resolved",
                    extra={
                        "source": str(self.pdf_path),
                        "category": category,
                        "available_headers": budget_table.headers,
                        "allocated_col": allocated_col,
                        "absorbed_col": absorbed_col,
                    },
                )
                continue
            records.extend(
                self._rows_from_columns(
                    budget_table,
                    category=category,
                    allocated_col=allocated_col,
                    absorbed_col=absorbed_col,
                    rate_col=rate_col,
                )
            )

        # ── Backward-compat fallbacks for older PDF formats ────────
        # Pre-FY2024 reports published Recurrent / Development as
        # SEPARATE tables rather than as sub-columns of a consolidated
        # one. The new parser path above prefers the consolidated table,
        # but if a category came up empty we try the legacy separate-
        # table path before giving up — so old fixtures and any older
        # vintage that resurfaces still produce useful output.
        extracted_categories = {r["category"] for r in records}
        for category, header_keywords in (
            ("Recurrent", ["recurrent"]),
            ("Development", ["development"]),
        ):
            if category in extracted_categories:
                continue
            fallback = self._extract_category(category, header_keywords)
            if fallback:
                logger.info(
                    "%s category extracted via legacy separate-table fallback "
                    "(consolidated table didn't carry it)",
                    category,
                )
                records.extend(fallback)

        # Personnel Emoluments still lives in its own table when
        # present — the consolidated table doesn't break PE out.
        records.extend(
            self._extract_category(
                "Personnel Emoluments",
                ["personnel", "emolument"],
                subcategory="PE",
            )
        )

        logger.info(
            f"Parsed {len(records)} budget execution records from CoB report",
            extra={
                "source": str(self.pdf_path),
                "record_count": len(records),
                "categories": sorted({r.get("category") for r in records}),
            },
        )

        return records

    def _extract_category(
        self,
        category: str,
        header_keywords: List[str],
        subcategory: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Locate a sub-aggregate table by header keywords and
        convert it to the category-tagged record shape."""
        # The sub-aggregate tables share the "county | allocated |
        # absorbed" columns; the extra keyword disambiguates them.
        probe = list(header_keywords) + ["county"]
        table = find_table_by_header(self.tables, probe)
        if not table:
            # Some PDFs put category labels in a caption rather than
            # the header row — fall back to scanning for an "allocated"
            # + keyword combo without strict ordering.
            table = find_table_by_header(self.tables, header_keywords + ["allocated"])
        if not table:
            logger.info(
                "CoB PDF has no '%s' breakdown table (keywords=%s)",
                category,
                header_keywords,
            )
            return []
        return self._rows_to_records(table, category=category, subcategory=subcategory)

    def _rows_from_columns(
        self,
        table: ExtractedTable,
        *,
        category: str,
        allocated_col: int,
        absorbed_col: int,
        rate_col: Optional[int],
        subcategory: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Like ``_rows_to_records`` but picks values by EXPLICIT column
        index instead of fixed positions 1/2/3. Required for multi-column
        consolidated tables where the same row contains Rec / Dev / Total
        sub-columns for both budget-estimates AND actual-expenditure
        sides — fixed positions can't address them all."""
        out: List[Dict[str, Any]] = []
        for row in table.rows:
            try:
                county_name = (row[0] or "").strip()
                if not county_name:
                    continue
                low = county_name.lower()
                if any(
                    kw in low
                    for kw in ("total", "average", "summary", "grand total")
                ):
                    continue
                # Defensive: skip if the row is shorter than the
                # column we want to read.
                if len(row) <= max(allocated_col, absorbed_col):
                    continue

                allocated, currency = parse_currency(row[allocated_col])
                absorbed, _ = parse_currency(row[absorbed_col])
                absorption_rate: Optional[float] = None
                if rate_col is not None and len(row) > rate_col:
                    absorption_rate = parse_percentage(row[rate_col])
                # Derive when missing or unparseable. Some vintages drop
                # the absorption-rate sub-column entirely; downstream
                # consumers (the /budget/overview probe in particular)
                # expect this field, so compute it ourselves rather than
                # leaving a None that propagates as a UI gap.
                if (
                    absorption_rate is None
                    and allocated
                    and absorbed is not None
                    and allocated != Decimal("0")
                ):
                    absorption_rate = float(absorbed / allocated * Decimal("100"))

                out.append(
                    {
                        "county": county_name,
                        "category": category,
                        "subcategory": subcategory,
                        "allocated": allocated,
                        "absorbed": absorbed,
                        "absorption_rate": absorption_rate,
                        "currency": currency,
                        "quarter": self._extract_quarter(),
                        "fiscal_year": self._extract_fiscal_year(),
                    }
                )
            except (IndexError, ValueError) as e:
                logger.warning("Failed to parse row %s: %s", row, e)
                continue
        return out

    def _rows_to_records(
        self,
        table: ExtractedTable,
        category: str,
        subcategory: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Shared row-parsing loop for any county×amount table."""
        out: List[Dict[str, Any]] = []
        for row in table.rows:
            try:
                county_name = (row[0] or "").strip()
                if not county_name:
                    continue
                if any(
                    kw in county_name.lower()
                    for kw in ("total", "average", "summary", "grand total")
                ):
                    continue

                allocated, currency = parse_currency(row[1])
                absorbed, _ = parse_currency(row[2])
                absorption_rate = (
                    parse_percentage(row[3]) if len(row) > 3 else None
                )

                record: Dict[str, Any] = {
                    "county": county_name,
                    "category": category,
                    "subcategory": subcategory,
                    "allocated": allocated,
                    "absorbed": absorbed,
                    "absorption_rate": absorption_rate,
                    "currency": currency,
                    "quarter": self._extract_quarter(),
                    "fiscal_year": self._extract_fiscal_year(),
                }
                out.append(record)
            except (IndexError, ValueError) as e:
                logger.warning("Failed to parse row %s: %s", row, e)
                continue
        return out

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
