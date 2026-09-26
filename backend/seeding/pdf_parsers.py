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


class CountyTableIncomplete(PDFParserError):
    """The consolidated county table was found but not read whole.

    Raised rather than returned because a partial county table is the failure
    that hides: 39 rows look exactly like 47 unless something counts them, and
    the run that dropped eight counties reported success for every nightly it
    ran in.
    """


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


#: County labels the CBIRR prints differently from this project's names, once
#: reduced to letters. Kept explicit rather than inferred: "nairobicity" and
#: "nairobi" are the same county, but no general rule that collapses them
#: leaves "kisii" and "kisumu" distinct.
_COUNTY_LABEL_ALIASES = {
    "nairobicity": "nairobi",
}


def canonical_county_label(label: str) -> str:
    """The county this label names, spelled the way this project spells it.

    The report breaks names across lines ("Taita-Tav-\neta"), uses a curly
    apostrophe, and calls the capital "Nairobi City". Emitting the raw label
    pushed that onto the writer, which slugified it and looked for
    "nairobi-city-county" — a county that does not exist here, so Nairobi's
    own-source revenue was dropped with an error while three other counties
    were rescued by a "despaced" fallback. Resolving it once, here, means
    every consumer gets a name that resolves exactly.

    Unrecognised labels are returned unchanged, so a genuinely new row still
    reaches the caller rather than vanishing.
    """
    key = _county_key(label)
    for county in KENYAN_COUNTIES:
        if _county_key(county) == key:
            return county
    return (label or "").strip()


def _county_key(label: str) -> str:
    """A county label reduced to comparable letters.

    The CBIRR hyphenates across lines and uses a curly apostrophe, so the same
    county appears as "Elgeyo -\nMarakwet", "Taita-Tav-\neta" and "Murang\u2019a".
    Its own-source revenue table also names the capital "Nairobi City", which
    is why the alias map exists — without it Nairobi was the one county missing
    from that table, and the sum gate would have refused the whole parse.
    """
    key = re.sub(r"[^a-z]", "", (label or "").lower())
    return _COUNTY_LABEL_ALIASES.get(key, key)


def stitch_table_continuation(
    base: ExtractedTable,
    tables: List[ExtractedTable],
    anchors: List[str],
    *,
    max_page_gap: int = 2,
) -> ExtractedTable:
    """Append the rows of a table that continues ``base`` onto a later page.

    A 47-row county table does not fit on one page. In the FY2025/26 CBIRR the
    consolidated budget table runs across pages 61 and 62: page 61 carries 39
    counties, page 62 the remaining 8 and the Total row. Only page 61 is ever a
    candidate, because ranking requires 30+ county rows and the continuation
    has 8 — so the parse silently covered 39 of the 47 counties, with the Total
    row that would have exposed it sitting on the page nobody read.

    A table is treated as a continuation only when all of these hold, which is
    tight enough that an unrelated table of the same shape cannot qualify:

    * it is on a page within ``max_page_gap`` — either side, because which
      part of a split table is the "base" depends on which half has more
      rows. The budget table's continuation is the page AFTER it (39 counties
      on 61, 8 on 62); the own-source revenue table's is the page BEFORE
      (33 on 56, 13 on 55);
    * it repeats the base table's headers exactly. A continuation reprints
      them, and requiring equality rather than a matching column count is
      what stops two DIFFERENT county tables of the same width from being
      welded together — this report has several;
    * its first column holds county names, at least one of which the base
      table does not already have;
    * it contributes no county twice.
    """
    known = {_county_key(row[0]) for row in base.rows if row and row[0]}
    anchor_keys = {_county_key(a) for a in anchors}
    width = len(base.headers)
    added: List[List[str]] = []
    pages: List[int] = []

    for raw in sorted(tables, key=lambda t: (t.page_number, t.table_index)):
        if raw.page_number == base.page_number and raw.table_index == base.table_index:
            continue
        if abs(raw.page_number - base.page_number) > max_page_gap:
            continue
        candidate = flatten_grouped_headers(raw)
        if candidate.headers != base.headers:
            continue
        rows = [r for r in candidate.rows if r and r[0]]
        # The header may repeat, or the first row may be a sub-label row.
        county_rows = [r for r in rows if _county_key(r[0]) in anchor_keys]
        if not county_rows:
            continue
        fresh = [r for r in county_rows if _county_key(r[0]) not in known]
        if not fresh:
            continue
        for row in fresh:
            known.add(_county_key(row[0]))
            added.append(list(row) + [""] * (width - len(row)))
        pages.append(candidate.page_number)

    if not added:
        return base

    logger.info(
        "Stitched %d continuation row(s) onto the county table from page(s) %s",
        len(added),
        ", ".join(str(p) for p in pages),
        extra={"base_page": base.page_number, "added": len(added)},
    )
    return ExtractedTable(
        page_number=base.page_number,
        table_index=base.table_index,
        headers=list(base.headers),
        rows=list(base.rows) + added,
        bbox=base.bbox,
    )


#: Row totals are printed to one decimal of a million, so 47 of them can drift
#: by up to KSh 2.35m. The smallest county Total in the FY2025/26 CBIRR is
#: Lamu at KSh 4,988.65m, a thousand times the tolerance, so a dropped county
#: still fails.
_COUNTY_TOTAL_TOLERANCE_MILLIONS = Decimal("3")


def _printed_total_row(
    base: ExtractedTable, tables: List[ExtractedTable]
) -> Optional[List[str]]:
    """The table's own Total row, wherever it ended up.

    It sits at the foot of the LAST page of the table, which for the FY2025/26
    CBIRR is the continuation page — so it has to be looked for beyond the
    page the table was selected on.
    """
    width = len(base.headers)
    for candidate in [base] + sorted(
        (t for t in tables
         if base.page_number <= t.page_number <= base.page_number + 2
         and len(t.headers) == width),
        key=lambda t: (t.page_number, t.table_index),
    ):
        for row in candidate.rows:
            if row and row[0] and _county_key(row[0]) == "total":
                return list(row)
    return None


def _check_county_coverage(
    records: List[Dict[str, Any]],
    printed_total: Optional[List[str]],
    source: str,
    allocated_col: Optional[int] = None,
    category: str = "Total",
) -> None:
    """Refuse a consolidated county table that is not whole.

    Two checks the table answers itself:

    1. all 47 counties present — a missing one is a row the parse lost;
    2. the Total-category rows sum to the Total row the table prints.

    The second is what makes the first more than a headcount: a row read from
    the wrong column keeps the count right and breaks the sum.
    """
    totals = [r for r in records if r.get("category") == category]
    seen = {_county_key(str(r.get("county") or "")) for r in totals}
    missing = [c for c in KENYAN_COUNTIES if _county_key(c) not in seen]
    if missing:
        raise CountyTableIncomplete(
            f"{len(missing)} of {len(KENYAN_COUNTIES)} counties missing from the "
            f"consolidated table in {source}: {', '.join(missing)}"
        )
    logger.info("CBIRR check: all %d counties read", len(KENYAN_COUNTIES))

    if printed_total is None:
        logger.warning(
            "CBIRR: no Total row found, so the county rows could not be "
            "checked against one",
            extra={"source": source},
        )
        return

    parsed = sum((r.get("allocated") or Decimal("0")) for r in totals)

    # Read the SAME column the county rows were read from. Picking "the first
    # big-looking cell" instead compared the county budget total against the
    # row's Recurrent sub-total — 633,303.87 against 398,974.59 — and failed a
    # parse that was in fact exact.
    printed = None
    if allocated_col is not None and allocated_col < len(printed_total):
        value, _ = parse_currency(str(printed_total[allocated_col] or ""))
        printed = value or None
    if printed is None:
        logger.warning(
            "CBIRR: the Total row carried no comparable figure",
            extra={"source": source, "row": printed_total, "col": allocated_col},
        )
        return

    drift = abs(parsed - printed)
    if drift > _COUNTY_TOTAL_TOLERANCE_MILLIONS:
        raise CountyTableIncomplete(
            f"county rows sum to {parsed:,} but the table prints {printed:,} "
            f"(out by {parsed - printed:+,}, tolerance "
            f"{_COUNTY_TOTAL_TOLERANCE_MILLIONS:,}) in {source}"
        )
    logger.info(
        "CBIRR check: rows sum to the printed total within %s", drift
    )


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


#: Cover-page wording for a part-year implementation report, and the canonical
#: sub-period label ``seeding.utils.normalize_fiscal_label`` keeps. Longer
#: phrases first, so "FIRST NINE MONTHS" is not read as some shorter match.
_COB_SUB_PERIODS: Tuple[Tuple[str, str], ...] = (
    ("FIRST NINE MONTHS", "9M"),
    ("FIRST SIX MONTHS", "H1"),
    ("FIRST HALF", "H1"),
    ("HALF YEAR", "H1"),
    ("FIRST QUARTER", "Q1"),
)

_YEAR = r"(?:FY|FINANCIAL\s+YEAR)\s*(\d{4})\s*[/\-]\s*(\d{2,4})"
_COB_SUB_PERIOD_RE = re.compile(
    r"(" + "|".join(p for p, _ in _COB_SUB_PERIODS) + r")\s+(?:OF\s+)?(?:THE\s+)?" + _YEAR
)
_COB_FULL_YEAR_RE = re.compile(r"FOR\s+(?:THE\s+)?" + _YEAR)
_COB_ANY_YEAR_RE = re.compile(_YEAR)
#: Wording of a part-year report. Present without a phrase this module can
#: name ("THIRD QUARTER", "FIRST EIGHT MONTHS"), the period is refused — read
#: as a full year, that report would be filed over the annual one.
_COB_PART_YEAR_WORDS = re.compile(r"\b(QUARTER|MONTHS|HALF)\b")


def _fy_label(start: str, end: str) -> Optional[str]:
    start_year, end_short = int(start), int(end) % 100
    if (start_year + 1) % 100 != end_short:
        return None
    return f"{start_year}/{end_short:02d}"


def _cob_period_on_page(text: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """``(decided, fiscal_year, sub_period)`` from one page of a CoB report.

    ``decided`` False means the page says nothing about the period and the
    next page may be read. True with ``fiscal_year`` None is a refusal: the
    page names a period this cannot read, and no later page may overrule it.
    """
    upper = " ".join((text or "").upper().split())
    phrase = _COB_SUB_PERIOD_RE.search(upper)
    if phrase:
        sub = dict(_COB_SUB_PERIODS)[phrase.group(1)]
        fy = _fy_label(phrase.group(2), phrase.group(3))
        return True, fy, sub if fy else None
    if _COB_PART_YEAR_WORDS.search(upper) and _COB_ANY_YEAR_RE.search(upper):
        return True, None, None
    full = _COB_FULL_YEAR_RE.search(upper)
    if full:
        return True, _fy_label(full.group(1), full.group(2)), None
    years = {_fy_label(m.group(1), m.group(2)) for m in _COB_ANY_YEAR_RE.finditer(upper)}
    if len(years) == 1:
        return True, years.pop(), None
    # Several years and no phrase tying one to the report: undecidable here.
    return (len(years) > 1), None, None


def detect_cob_report_period(text: str) -> Tuple[Optional[str], Optional[str]]:
    """``("2025/26", "9M")`` from a CoB report's cover text, or ``(None, None)``.

    The cover says what the report covers — "FIRST NINE MONTHS OF FY 2025/26",
    "FOR THE FINANCIAL YEAR 2025/26". That, and not the file's name, is the
    report's period: the fetcher hands this parser a file out of the PDF cache,
    whose name is a sha256, so the old filename reading never matched and every
    CBIRR fell back to a hardcoded "2024/25".

    The year is the one the period phrase names, not the first year the text
    mentions (a foreword compares with the year before). A part-year wording
    this cannot name is refused rather than read as a full year.
    ``sub_period`` is None for a full-year report.
    """
    _decided, fy, sub = _cob_period_on_page(text)
    return (fy, sub) if fy else (None, None)


# --------------------------------------------------------------------------
# per-county revenue receipts (CBIRR Chapter 3, "Revenue Performance")
# --------------------------------------------------------------------------

#: The BudgetLine category every revenue-receipts row is written under. It is
#: money the county RECEIVED, stored in the budget table because it has the
#: same target/actual shape — so every budget aggregate must skip it
#: (``services.county_budget.NON_SECTOR_CATEGORIES``).
REVENUE_RECEIPTS_CATEGORY = "Revenue Receipts"

#: Subcategories, one per stream the CBIRR prints, plus the printed total.
REVENUE_TOTAL = "Total"
REVENUE_STREAMS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("Balance Brought Forward", ("unspent", "brought forward", "balance b/f")),
    ("Equitable Share", ("equitable share",)),
    ("Equalisation Fund", ("equalisation", "equalization")),
    ("Additional Allocations", ("additional allocation", "grant", "conditional")),
    ("Facility Improvement Financing", ("facility improvement", "fif")),
    ("Appropriations in Aid", ("appropriation", "a-i-a", "aia")),
    ("Own Source Revenue", ("own source", "osr")),
    ("Other Revenue", ("other revenue", "other income", "other sources")),
)
#: A section the table prints but these keywords do not name.
REVENUE_OTHER = "Other Revenue"

#: Rows are printed to the shilling; a section sum may differ from the printed
#: total by rounding in the treasury's own spreadsheet, never by more.
_REVENUE_TOLERANCE_KES = Decimal("1000")

_REVENUE_CAPTION_RE = re.compile(
    r"Table\s+3\.\d+:\s*(.+?)\s+County,?\s+Revenue\s+Performance", re.IGNORECASE
)
_SECTION_LETTER_RE = re.compile(r"^[A-H]\.?(\s|$)")


def _cell_text(cell: Optional[str]) -> str:
    """A cell with pdfplumber's line-break hyphenation undone, lowercased."""
    s = (cell or "").replace("’", "'")
    s = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", s)
    s = re.sub(r"(\w)- (\w)", r"\1\2", s)
    return " ".join(s.split()).lower()


_KES_CELL_RE = re.compile(
    r"(?:(?P<minus>-)|(?P<paren>\())?(?P<digits>\d+(?:\.\d+)?)(?(paren)\))"
)


def _kes_cell(cell: Optional[str]) -> Optional[Decimal]:
    """A whole-shilling cell: "7, 956, 564, 058" -> 7956564058; "-" -> 0.

    None when the cell holds something that is not a number, so a caller can
    tell a misread cell from a printed nil.
    """
    s = (cell or "").strip().replace(",", "").replace(" ", "")
    if s in ("", "-", "–", "."):
        return Decimal(0)
    # Digits, one optional decimal point, a leading minus or parentheses —
    # nothing else. Decimal() alone would take "1e6", "1_000_000", "NaN" and
    # "Infinity", and stripping "-" from both ends read "1,000,000-" as +1M.
    match = _KES_CELL_RE.fullmatch(s)
    if not match:
        return None
    value = Decimal(match.group("digits"))
    return -value if (match.group("minus") or match.group("paren")) else value


def _revenue_stream(label: str) -> Optional[str]:
    for stream, keywords in REVENUE_STREAMS:
        if any(k in label for k in keywords):
            return stream
    return None


def _is_revenue_table(table: ExtractedTable) -> bool:
    headers = [_cell_text(c) for c in table.headers]
    # "Revenue Stream" is sometimes split across the first two header cells
    # ("No Reve" | "nue Stream"), so match it on the two joined.
    joined = _cell_text("".join(table.headers[:2]))
    return "revenue stream" in joined and any(
        "actual" in h and "receipt" in h for h in headers
    )


@dataclass
class _RevenueSection:
    stream: Optional[str]
    label: str
    target_items: Decimal = Decimal(0)
    actual_items: Decimal = Decimal(0)
    target_sub: Optional[Decimal] = None
    actual_sub: Optional[Decimal] = None
    subtotals: int = 0
    target_unreadable: bool = False

    @property
    def target(self) -> Decimal:
        return self.target_sub if self.target_sub is not None else self.target_items

    @property
    def actual(self) -> Decimal:
        return self.actual_sub if self.actual_sub is not None else self.actual_items


def _revenue_rows(tables: List[ExtractedTable]):
    """``(kind, lettered, label, target, actual)`` for each meaningful row.

    kind is ``header`` (a section or sub-section title), ``item``, ``sub`` or
    ``grand``. Columns are found per table from its own header, because the
    47 county treasuries lay the table out differently: Kiambu has no "No"
    column, Homa Bay no receivables column, and a table may be split across
    pages with the header repeated inside the body.
    """
    for table in tables:
        headers = [_cell_text(c) for c in table.headers]
        target_col = next(
            (i for i, h in enumerate(headers) if "annual" in h or "target" in h), None
        )
        actual_cols = [
            i for i, h in enumerate(headers) if "actual" in h and "receipt" in h
        ]
        # Two "actual receipts" columns (a quarter and a cumulative, say) is
        # a layout this cannot tell apart; take neither.
        actual_col = actual_cols[0] if len(actual_cols) == 1 else None
        if target_col is None or actual_col is None or target_col < 1:
            continue
        for row in table.rows:
            if len(row) <= actual_col or not any((c or "").strip() for c in row):
                continue
            label = _cell_text("".join(row[:target_col]))
            if _cell_text(row[actual_col]).startswith("actual"):
                # The header printed again inside the body. Its first cell can
                # still carry a section letter ("B | Equitable Share | Annual…").
                lettered = bool(_SECTION_LETTER_RE.match((row[0] or "").strip()))
                yield ("header", lettered and target_col >= 2, label, None, None)
                continue
            if re.fullmatch(r"[A-Za-z]?", (row[target_col] or "").strip()) and re.fullmatch(
                r"[A-Za-z]", (row[actual_col] or "").strip()
            ):
                # The column legend under the header ("A | B | C | D=B+C"),
                # sometimes shifted a cell by the extraction.
                continue
            target = _kes_cell(row[target_col])
            actual = _kes_cell(row[actual_col])
            if re.search(r"sub[- ]?to[- ]?tal", label):
                yield ("sub", False, label, target, actual)
                continue
            if re.fullmatch(r"(grand )?total", label):
                # A Grand Total cell that printed nothing is not a printed
                # nil: read as 0 it reconciled 0 against 0 and published a
                # county that received nothing.
                printed = bool((row[actual_col] or "").strip().strip("-" + chr(0x2013)))
                yield ("grand", False, label, target, actual if printed else None)
                continue
            has_numbers = any((c or "").strip() for c in row[target_col:])
            lettered = bool(_SECTION_LETTER_RE.match((row[0] or "").strip())) and (
                target_col >= 2
            )
            if lettered or not has_numbers:
                yield (
                    "header",
                    lettered,
                    label,
                    target if has_numbers else None,
                    actual if has_numbers else None,
                )
            else:
                yield ("item", False, label, target, actual)


def county_revenue_receipts(
    tables: List[ExtractedTable],
) -> Tuple[Optional[Dict[str, Tuple[Decimal, Decimal]]], str]:
    """One county's revenue receipts from its "Revenue Performance" table.

    Returns ``({stream: (annual_target, actual_receipts)}, "")`` with a
    ``"Total"`` entry, or ``(None, why)`` when the table does not prove itself.

    It proves itself by adding up: the streams must sum to the table's own
    Grand Total of actual receipts. That is the whole reason the result can be
    published — each of the 47 tables is laid out by a different county
    treasury (sections lettered A-H, or "C.", or not at all; sub-totals printed
    for some sections and not others; the same heading split across two cells)
    and a parse that has misread any of it does not reconcile. Two further
    refusals catch a misread that happens to reconcile: a section carrying
    two sub-totals (Turkana numbers its grants section "3", so the grants
    sub-total lands on equitable share), and anything but exactly one
    equitable-share section.

    The actual-receipts column is read, never the accrual total beside it
    (receipts plus receivables), which is a different measure — several
    counties' own narratives quote the accrual figure.
    """
    rows = list(_revenue_rows(tables))
    grand = [r for r in rows if r[0] == "grand" and r[4] is not None]
    if not grand:
        return None, "no_grand_total"
    if len(grand) > 1:
        # Two counties' tables grouped as one — a caption was not found.
        return None, "more_than_one_grand_total"
    grand_target, grand_actual = grand[-1][3], grand[-1][4]
    if not grand_actual.is_finite() or grand_actual <= 0:
        return None, "grand_total_is_not_positive"
    if any(r[0] in ("item", "sub") and r[4] is None for r in rows):
        # A cell in the receipts column that is not a number ("n/a", "NaN",
        # a merged cell): the streams cannot be proven to add up.
        return None, "unreadable_receipts_cell"

    lettered = any(r[1] for r in rows if r[0] == "header")
    sections: List[_RevenueSection] = []
    current: Optional[_RevenueSection] = None
    for kind, is_lettered, label, target, actual in rows:
        if kind == "header":
            stream = _revenue_stream(label)
            closed = current is not None and current.actual_sub is not None
            if lettered:
                # A lettered table can still lose a letter into the label
                # ("cadditional allocations", "3conditional allocations…").
                # A heading for a DIFFERENT stream after the current section
                # has printed its sub-total is the next section all the same.
                # Also when the section above printed no Sub-Total: Bomet's
                # own-source section prints none, and with the FIF heading's
                # letter lost, FIF was summed into own-source and the table
                # still reconciled. A heading naming the SAME stream (a
                # "Conditional allocations" sub-heading under grants) does not.
                top = is_lettered or (
                    stream is not None
                    and current is not None
                    and stream != current.stream
                )
            else:
                top = stream is not None and (
                    current is None or stream != current.stream or closed
                )
            if top:
                current = _RevenueSection(stream=stream, label=label)
                sections.append(current)
                if actual is not None:
                    current.actual_items += actual
                    current.target_items += target or Decimal(0)
            continue
        if current is None:
            continue
        if kind == "sub":
            if current.actual_sub is not None and not actual:
                # A nil section whose heading did not survive extraction
                # ("Transfers from the Equalisation Fund … Sub-Total -"). It
                # adds nothing; anything non-zero here is refused below.
                continue
            current.subtotals += 1
            current.actual_sub = actual
            current.target_sub = target
            current.target_unreadable = target is None
        elif kind == "item" and actual is not None:
            current.actual_items += actual
            if target is None:
                current.target_unreadable = True
            else:
                current.target_items += target

    if not sections:
        return None, "no_sections"
    if any(s.subtotals > 1 for s in sections):
        return None, "a_section_has_two_subtotals"
    if sum(1 for s in sections if s.stream == "Equitable Share") != 1:
        return None, "equitable_share_not_exactly_one_section"
    if any(s.stream == "Equitable Share" and s.actual <= 0 for s in sections):
        return None, "equitable_share_is_not_positive"
    drift = abs(sum((s.actual for s in sections), Decimal(0)) - grand_actual)
    if drift > _REVENUE_TOLERANCE_KES:
        return None, f"streams_do_not_sum_to_grand_total (out by {drift:,})"

    out: Dict[str, Tuple[Optional[Decimal], Decimal]] = {}
    for section in sections:
        stream = section.stream or REVENUE_OTHER
        prev_target, prev_actual = out.get(stream, (Decimal(0), Decimal(0)))
        target = (
            None
            if prev_target is None or section.target_unreadable
            else prev_target + section.target
        )
        out[stream] = (target, prev_actual + section.actual)
    # An unreadable target is absent, not 0.
    out[REVENUE_TOTAL] = (grand_target, grand_actual)
    return out, ""


def group_revenue_tables_by_county(
    tables: List[ExtractedTable], captions: Dict[int, str]
) -> Dict[str, List[ExtractedTable]]:
    """Each county's revenue-table pages, keyed by county.

    ``captions`` maps page number -> the county a "Table 3.N: X County,
    Revenue Performance" caption on that page names. A table belongs to the
    nearest caption at or before its page: the caption can sit at the foot of
    the page before, and the table can run over two or three pages.
    """
    caption_pages = sorted(captions)
    grouped: Dict[str, List[ExtractedTable]] = {}
    for table in sorted(tables, key=lambda t: (t.page_number, t.table_index)):
        if not _is_revenue_table(table):
            continue
        owner = [p for p in caption_pages if p <= table.page_number]
        if not owner:
            continue
        county = canonical_county_label(captions[owner[-1]])
        grouped.setdefault(county, []).append(table)
    return grouped


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
        self._period: Optional[Tuple[Optional[str], Optional[str]]] = None

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

        # Whether this really is the 47-county consolidated table. The
        # completeness gate below applies only when it is, so the small tables
        # in the parser's own fixtures — which reach here via the legacy
        # header probe — are not held to a 47-county standard.
        _anchor_keys = {_county_key(c) for c in KENYAN_COUNTIES}
        anchored = (
            len([r for r in budget_table.rows
                 if r and r[0] and _county_key(r[0]) in _anchor_keys]) >= 30
        )

        # The table runs past the bottom of its page — see
        # stitch_table_continuation for what that cost.
        budget_table = stitch_table_continuation(
            budget_table, self.tables, list(KENYAN_COUNTIES)
        )
        printed_total = _printed_total_row(budget_table, self.tables)
        total_allocated_col = find_column_index(
            budget_table.headers, primary_total_synonyms
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
                    # FY2025/26 CBIRR wording. Its consolidated table splits a
                    # merged header into sub-columns, so the cell reads
                    # "Expenditure (Kshs.Million) Rec" — no "actual", and "Rec"
                    # rather than "Recurrent", which is why every synonym above
                    # missed it. The Total category already had the equivalent
                    # (["expenditure", "total"]); Recurrent and Development did
                    # not, so both fell through to the legacy separate-table
                    # path and the parse covered 25 of the 47 counties.
                    ["expenditure", "rec"],
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
                    ["expenditure", "dev"],  # see the Recurrent note above
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

        if anchored:
            _check_county_coverage(
                records, printed_total, str(self.pdf_path), total_allocated_col
            )

        # What each county RAISES ITSELF, which is a different figure from its
        # budget and was previously modelled as 0.85 x it.
        records.extend(self._extract_own_source_revenue())

        # What each county RECEIVED, stream by stream (equitable share,
        # additional allocations, ...) with the report's own total.
        records.extend(self._extract_county_revenue_receipts())

        logger.info(
            f"Parsed {len(records)} budget execution records from CoB report",
            extra={
                "source": str(self.pdf_path),
                "record_count": len(records),
                "categories": sorted({r.get("category") for r in records}),
            },
        )

        return records

    def _extract_own_source_revenue(self) -> List[Dict[str, Any]]:
        """Table 2.1 — "Own Source Revenue Collection", per county.

        This is what a county raises itself: rates, licences, park fees,
        hospital charges. It is NOT the county's budget, most of which is the
        equitable share from the national government, and the difference is
        large — 47 counties collected KSh 53.9B against budgets of KSh 633.3B
        in the first nine months of FY 2025/26.

        That matters because the figure this replaces was
        ``0.85 x budget_2025`` from a fixture, published under the label
        "Revenue Collected" — roughly ten times what counties actually collect.

        ``allocated`` carries the TARGET and ``absorbed`` the ACTUAL REALISED
        figure, which is the same shape the budget rows use, so the writer and
        the absorption-rate derivation need no special case.
        """
        target_synonyms: List[List[str]] = [
            ["target", "total osr"],
            ["target", "total", "osr"],
        ]
        actual_synonyms: List[List[str]] = [
            ["actual", "realised", "total osr"],
            ["actual", "realised", "total", "osr"],
            ["actual", "realized", "total", "osr"],
        ]
        rate_synonyms: List[List[str]] = [
            ["performance", "total osr"],
            ["performance", "total", "osr"],
        ]

        ranked = rank_tables_by_row_anchors(
            self.tables,
            list(KENYAN_COUNTIES),
            min_matches=30,
            header_synonyms=[["target", "actual"], ["osr"]],
        )
        for candidate in ranked:
            flat = flatten_grouped_headers(candidate)
            target_col = find_column_index(flat.headers, target_synonyms)
            actual_col = find_column_index(flat.headers, actual_synonyms)
            if target_col is None or actual_col is None:
                continue

            stitched = stitch_table_continuation(
                flat, self.tables, list(KENYAN_COUNTIES)
            )
            records = self._rows_from_columns(
                stitched,
                category="Own Source Revenue",
                allocated_col=target_col,
                absorbed_col=actual_col,
                rate_col=find_column_index(stitched.headers, rate_synonyms),
            )
            _check_county_coverage(
                records,
                _printed_total_row(stitched, self.tables),
                f"{self.pdf_path} (own source revenue)",
                target_col,
                category="Own Source Revenue",
            )
            return records

        logger.info(
            "CoB PDF has no per-county own-source revenue table",
            extra={"source": str(self.pdf_path)},
        )
        return []

    def _extract_county_revenue_receipts(self) -> List[Dict[str, Any]]:
        """Chapter 3's per-county "Revenue Performance" tables, reconciled.

        One record per revenue stream plus the table's Grand Total, under
        ``REVENUE_RECEIPTS_CATEGORY``, for every county whose streams add up to
        its own Grand Total (see ``county_revenue_receipts``). A county that
        does not reconcile gets no records at all — its revenue is absent, not
        partial — and is named in the log with the reason.

        Amounts are whole shillings, as printed; ``amounts_in: "kes"`` tells
        the fetcher not to apply the KSh-millions scaling the Chapter 2
        aggregates need.
        """
        candidates = [t for t in self.tables if _is_revenue_table(t)]
        if not candidates:
            logger.info(
                "CoB PDF has no per-county revenue performance tables",
                extra={"source": str(self.pdf_path)},
            )
            return []

        pages = sorted(
            {p for t in candidates for p in (t.page_number - 1, t.page_number) if p >= 1}
        )
        captions: Dict[int, str] = {}
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                for number in pages:
                    if number > len(pdf.pages):
                        continue
                    match = _REVENUE_CAPTION_RE.search(
                        pdf.pages[number - 1].extract_text() or ""
                    )
                    if match:
                        captions[number] = match.group(1)
        except Exception as exc:  # noqa: BLE001 - no captions means no owners
            logger.warning("CoB revenue captions unreadable: %s", exc)
            return []

        records: List[Dict[str, Any]] = []
        refused: Dict[str, str] = {}
        grouped = group_revenue_tables_by_county(candidates, captions)
        for county, tables in sorted(grouped.items()):
            try:
                streams, why = county_revenue_receipts(tables)
            except Exception as exc:  # noqa: BLE001 - one county, not the report
                # Revenue rows ride along with the budget parse; an exception
                # here must cost this county its revenue, never every county
                # its budget.
                streams, why = None, f"extraction_error ({type(exc).__name__}: {exc})"
            if streams is None:
                refused[county] = why
                continue
            for stream, (target, actual) in streams.items():
                records.append(
                    {
                        "county": county,
                        "category": REVENUE_RECEIPTS_CATEGORY,
                        "subcategory": stream,
                        "allocated": target,
                        "absorbed": actual,
                        "absorption_rate": None,
                        "currency": "KES",
                        "amounts_in": "kes",
                        "quarter": self._extract_quarter(),
                        "fiscal_year": self._extract_fiscal_year(),
                    }
                )
        reconciled = len(grouped) - len(refused)
        logger.info(
            "CoB revenue receipts: %d of %d counties reconcile to their own "
            "Grand Total",
            reconciled,
            len(grouped),
        )
        if refused:
            logger.warning(
                "CoB revenue receipts withheld for %d county(ies): %s",
                len(refused),
                "; ".join(f"{c} ({why})" for c, why in sorted(refused.items())),
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
                        "county": canonical_county_label(county_name),
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
                    "county": canonical_county_label(county_name),
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

    def _report_period(self) -> Tuple[Optional[str], Optional[str]]:
        """``(fiscal_year, sub_period)`` for this report, read once.

        The cover first; the filename only when there is no readable cover (a
        test double, or a download saved under its publisher's name). Neither
        is guessed: a report whose period cannot be read yields ``None`` and the
        fetcher drops its rows, because rows filed under the wrong year are
        worse than no rows — they look right.
        """
        if self._period is not None:
            return self._period
        # Page by page, cover first: the first page that decides the period
        # wins, and a refusal is final (a foreword must not overrule a cover
        # this could not read).
        fy, sub, decided = None, None, False
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                for page in pdf.pages[:3]:
                    decided, fy, sub = _cob_period_on_page(page.extract_text() or "")
                    if decided:
                        break
        except Exception:  # noqa: BLE001 - an unreadable cover is "no cover"
            fy, sub, decided = None, None, False
        if fy is None and not decided:
            name = self.pdf_path.name
            fy_match = re.search(r"(\d{4})[-/](\d{2,4})", name)
            if fy_match:
                fy = f"{fy_match.group(1)}/{fy_match.group(2)[-2:]}"
                quarter = re.search(r"Q([1-4])", name, re.IGNORECASE)
                sub = f"Q{quarter.group(1)}" if quarter else None
        if fy is None:
            logger.warning(
                "CoB report period unreadable from cover or filename: %s",
                self.pdf_path,
            )
        self._period = (fy, sub)
        return self._period

    def _extract_quarter(self) -> Optional[str]:
        """The report's sub-period ("9M", "H1", "Q2"), None for a full year."""
        return self._report_period()[1]

    def _extract_fiscal_year(self) -> Optional[str]:
        """The report's fiscal year ("2025/26"), None when it cannot be read."""
        return self._report_period()[0]


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
