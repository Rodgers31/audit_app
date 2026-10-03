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
from dataclasses import dataclass, field
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


def extract_all_tables(pdf_path: Path, *, pages: Optional[List[int]] = None) -> List[ExtractedTable]:
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
                if pages is not None and page_num not in pages:
                    continue
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
_KES_GROUPED_CELL_RE = re.compile(
    r"(?:-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|\(\d{1,3}(?:,\d{3})+(?:\.\d+)?\))"
)


def _kes_cell(cell: Optional[str]) -> Optional[Decimal]:
    """A whole-shilling cell: "7, 956, 564, 058" -> 7956564058; "-" -> 0.

    None when the cell holds something that is not a number, so a caller can
    tell a misread cell from a printed nil. Kisii PDF 331 prints underscores
    as its nil marks; a lone underscore is nil, never an observed numeric zero.
    """
    s = (cell or "").strip()
    # A leading comma means pdfplumber clipped a digit from the cell (Kilifi
    # FY2025/26: printed 1,150,000,000 became ",150,000,000"). Dropping the
    # comma would silently publish an amount smaller by a billion.
    if "," in s and not _KES_GROUPED_CELL_RE.fullmatch(s.replace(" ", "")):
        return None
    s = s.replace(",", "").replace(" ", "")
    if s in ("", "-", "–", ".", "_"):
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


def _is_cash_revenue_header(header: str) -> bool:
    """Recognize the cash column, never the adjacent accrual/receivables one.

    County treasuries call it either ``Actual Receipts`` (most chapters) or
    ``Actual Revenue(s)`` (Bungoma and Busia in FY2025/26). The latter is
    cash: the table separately labels the D column ``Total Revenues (on an
    accrual basis)`` and defines D=B+C, with B as the actual-revenue column.
    """
    return bool(
        re.search(r"\bactual\s+(?:receipts?|revenues?)\b", header)
        and not re.search(r"\b(?:accrual|receivables?|arrears?)\b", header)
    )


def _corroborated_misgrouped_cash(
    row: List[str], headers: List[str], actual_col: int,
) -> Optional[Decimal]:
    """Recover a misgrouped cash item only when the same row proves B=D-C.

    Machakos PDF 440 prints B as ``16,04,988,360``; C is a dash and D
    independently prints ``1,604,988,360``. The enclosing FIF subtotal is
    checked later. An uncorroborated malformed cell remains unreadable.
    """
    raw = (row[actual_col] or "").strip()
    if not re.fullmatch(r"\d[\d,]+(?:\.\d+)?", raw) or "," not in raw:
        return None
    receivable_cols = [i for i, h in enumerate(headers) if "receivab" in h]
    accrual_cols = [i for i, h in enumerate(headers) if "accrual" in h]
    if len(receivable_cols) != 1 or len(accrual_cols) != 1:
        return None
    receivable_col, accrual_col = receivable_cols[0], accrual_cols[0]
    if max(receivable_col, accrual_col) >= len(row):
        return None
    if (row[receivable_col] or "").strip() not in {"-", "–", "0", "0.00"}:
        return None
    candidate = _KES_CELL_RE.fullmatch(raw.replace(",", ""))
    accrual = _kes_cell(row[accrual_col])
    if candidate is None or accrual is None:
        return None
    value = Decimal(candidate.group("digits"))
    return value if value == accrual else None


def _is_revenue_table(table: ExtractedTable) -> bool:
    headers = [_cell_text(c) for c in table.headers]
    # "Revenue Stream" is sometimes split across the first two header cells
    # ("No Reve" | "nue Stream"), so match it on the two joined.
    joined = _cell_text("".join(table.headers[:2]))
    return "revenue stream" in joined and any(_is_cash_revenue_header(h) for h in headers)


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
    receipts_observed: bool = False
    blank_items: bool = False
    blank_subtotal: bool = False
    nil_heading: bool = False
    # (printed subtotal, sum of item cells read up to that subtotal). Some
    # county tables print nested subtotals; retain each checkpoint so we can
    # prove whether the later subtotal is cumulative or an additional part.
    actual_checkpoints: List[Tuple[Optional[Decimal], Decimal]] = field(default_factory=list)
    target_checkpoints: List[Tuple[Optional[Decimal], Decimal]] = field(default_factory=list)
    nested_grant_headings_after_subtotal: int = 0

    @property
    def target(self) -> Decimal:
        return self.target_sub if self.target_sub is not None else self.target_items

    @property
    def actual(self) -> Decimal:
        return self.actual_sub if self.actual_sub is not None else self.actual_items


def _revenue_rows(tables: List[ExtractedTable]):
    """``(kind, lettered, label, target, actual, observed, blank)`` per row.

    kind is ``header`` (a section or sub-section title), ``item``, ``sub`` or
    ``grand``. Columns are found per table from its own header, because the
    47 county treasuries lay the table out differently: Kiambu has no "No"
    column, Homa Bay no receivables column, and a table may be split across
    pages with the header repeated inside the body.
    """
    for table in tables:
        headers = [_cell_text(c) for c in table.headers]
        actual_cols = [i for i, h in enumerate(headers) if _is_cash_revenue_header(h)]
        # Two "actual receipts" columns (a quarter and a cumulative, say) is
        # a layout this cannot tell apart; take neither.
        actual_col = actual_cols[0] if len(actual_cols) == 1 else None
        target_col = next(
            (i for i, h in enumerate(headers) if "annual" in h or "target" in h), None
        )
        if target_col is None and actual_col is not None and actual_col >= 2:
            # On Kilifi PDF 314 and Kisumu PDF 351 the header's first
            # letters leak into "Revenue Stream", leaving "geted Revenue"
            # or "argeted Revenue" in the target cell. Its position just
            # before the independently named cash column identifies it.
            before = headers[actual_col - 1]
            if "revenue stream" in _cell_text("".join(table.headers[:2])) and re.match(
                r"(?:geted|argeted)\s+revenue\b", before
            ):
                target_col = actual_col - 1
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
                yield (
                    "header",
                    lettered and target_col >= 2,
                    label,
                    None,
                    None,
                    False,
                    False,
                )
                continue
            if re.fullmatch(
                r"[A-Za-z]?", (row[target_col] or "").strip()
            ) and re.fullmatch(r"[A-Za-z]", (row[actual_col] or "").strip()):
                # The column legend under the header ("A | B | C | D=B+C"),
                # sometimes shifted a cell by the extraction.
                continue
            target = (
                _kes_cell(row[target_col]) if (row[target_col] or "").strip() else None
            )
            # Kisumu PDF 351 clips the leading target digit into the total
            # label: ``Total 1 | ... | 6,973,318,712``. Only a grouped target
            # with room in its first group can substantiate that boundary.
            clipped_total = re.fullmatch(r"((?:grand\s*)?total)\s+(\d{1,2})", label)
            if clipped_total:
                label, prefix = clipped_total.groups()
                raw_target = (row[target_col] or "").strip().replace(" ", "")
                target = None
                if re.fullmatch(r"\d{1,2}(?:,\d{3})+(?:\.\d+)?", raw_target):
                    if len(prefix + raw_target.split(",")[0]) <= 3:
                        target = _kes_cell(prefix + raw_target)
            actual = _kes_cell(row[actual_col])
            if actual is None:
                actual = _corroborated_misgrouped_cash(row, headers, actual_col)
            observed = actual is not None and bool(
                (row[actual_col] or "").strip().strip("-–._")
            )
            blank = (row[actual_col] or "").strip() in ("", ".")
            if label == "-":
                # Kitui PDF 368 leaves its closing grants label as a dash.
                # D independently repeats B and C explicitly prints nil.
                arrears = [
                    i
                    for i, h in enumerate(headers)
                    if "arrears" in h or "receivab" in h
                ]
                accrual = [i for i, h in enumerate(headers) if "accrual" in h]
                corroborated = (
                    actual is not None
                    and len(arrears) == len(accrual) == 1
                    and max(arrears[0], accrual[0]) < len(row)
                    and (row[arrears[0]] or "").strip() in {"-", "–", "_", "0", "0.00"}
                    and _kes_cell(row[accrual[0]]) == actual
                )
                yield (
                    "unlabelled_sub" if corroborated else "unlabelled_sub_unproven",
                    False,
                    label,
                    target,
                    actual,
                    observed,
                    blank,
                )
                continue
            if re.search(r"sub[- ]?to[- ]?tal", label):
                yield ("sub", False, label, target, actual, observed, blank)
                continue
            if re.fullmatch(r"(grand\s*)?total", label):
                # Blank, dot and dash are unobserved totals, never reported zero.
                yield (
                    "grand",
                    False,
                    label,
                    target,
                    actual if observed else None,
                    observed,
                    blank,
                )
                continue
            has_numbers = any((c or "").strip() for c in row[target_col:])
            lettered = bool(_SECTION_LETTER_RE.match((row[0] or "").strip())) and (
                target_col >= 2
            )
            # County treasuries also letter individual grant items A/B/C.
            # Those have amount cells; section titles span the empty columns.
            # Treating a monetary item as a new section counts it again beside
            # the enclosing grant subtotal (e.g. Nairobi Table 3.457).
            has_amount_cells = any(
                (row[i] or "").strip() for i in (target_col, actual_col)
            )
            aggregate_heading = lettered and _revenue_stream(label) in {
                "Balance Brought Forward",
                "Equitable Share",
                "Own Source Revenue",
                "Facility Improvement Financing",
                "Appropriations in Aid",
                "Other Revenue",
            }
            # A monetary aggregate grants row is distinct from a named grant
            # item whose label merely contains "grant" (e.g. DANIDA Grant).
            stream_label = re.sub(r"^[a-h]\.?(?:\s*)", "", label)
            aggregate_heading = aggregate_heading or (
                lettered
                and bool(
                    re.match(
                        r"(?:additional|conditional|unconditional)(?: additional)? allocations\b",
                        stream_label,
                    )
                )
            )
            if aggregate_heading and has_amount_cells and actual is None:
                yield ("item", False, label, target, None, False, blank)
                continue
            if not has_numbers or (
                lettered and (not has_amount_cells or aggregate_heading)
            ):
                yield (
                    "header",
                    lettered,
                    label,
                    target if has_numbers else None,
                    actual if has_numbers else None,
                    observed,
                    blank if has_numbers else False,
                )
            else:
                yield ("item", False, label, target, actual, observed, blank)


def _recover_revenue_layout_rows(rows):
    """Resolve two printed subtotal layouts using their local row evidence.

    Samburu PDF 729 labels its sole numbered equitable-share item Sub-Total,
    then repeats the same target and cash in the unnumbered closing subtotal.
    Kitui PDF 368 prints only a dash as the grants subtotal's label.
    Cash must match both its accrual cell (with nil arrears) and the preceding
    items within their printed precision. Complete targets must also add up;
    incomplete targets only bound the independently printed aggregate from
    below. The next row must open a different named stream. A grand total
    elsewhere is never evidence for either recovery.
    """
    recovered = list(rows)
    section_start = 0
    for index, row in enumerate(rows):
        kind, _lettered, label, target, actual, observed, blank = row
        previous = rows[index - 1] if index else None
        following = rows[index + 1] if index + 1 < len(rows) else None
        if (
            kind == "sub"
            and re.fullmatch(r"1\s*sub[- ]?total", label)
            and previous is not None
            and previous[0] == "header"
            and _revenue_stream(previous[2]) == "Equitable Share"
            and previous[3:5] == (None, None)
            and following is not None
            and following[0] == "sub"
            and following[2] in {"sub-total", "sub total", "subtotal"}
            and target is not None
            and actual is not None
            and observed
            and not blank
            and following[3:5] == (target, actual)
            and following[5]
            and not following[6]
        ):
            recovered[index] = ("item", *row[1:])

        if kind == "header" and _revenue_stream(label) != "Additional Allocations":
            section_start = index
        elif kind == "header" and _revenue_stream(label) == "Additional Allocations":
            if (
                rows[section_start][0] != "header"
                or _revenue_stream(rows[section_start][2]) != "Additional Allocations"
            ):
                section_start = index
        if kind not in {"unlabelled_sub", "unlabelled_sub_unproven"}:
            continue
        section = rows[section_start:index]
        if not section or _revenue_stream(section[0][2]) != "Additional Allocations":
            return None, "unlabelled_subtotal_not_corroborated"
        items = [r for r in section if r[0] == "item"]
        # A numbered monetary item with every amount erased is classified
        # as a heading upstream. It must not vanish from the proof merely
        # because its label includes "grant". Only named allocation-group
        # headings may divide the items used to prove this subtotal.
        erased_item = any(
            r[0] == "header"
            and re.match(r"^\d", r[2])
            and not re.match(
                r"^\d+\s*(?:unconditional|conditional)(?: additional)? allocations\b",
                r[2],
            )
            for r in section[1:]
        )
        if (
            kind != "unlabelled_sub"
            or not items
            or any(r[0] == "sub" for r in section)
            or following is None
            or following[0] != "header"
            or _revenue_stream(following[2]) in {None, "Additional Allocations"}
            or target is None
            or actual is None
            or not observed
            or blank
            or erased_item
            or any(r[4] is None or r[6] for r in items)
        ):
            return None, "unlabelled_subtotal_not_corroborated"
        for column in (3, 4):
            amounts = [r[column] for r in items if r[column] is not None]
            printed = row[column]
            # Half a unit in each cell's last printed decimal place. Nil
            # items contribute no rounding allowance. Never use the wider
            # grand-total tolerance to certify this previously unnamed row.
            bound = sum(
                (
                    Decimal("0.5") * Decimal(10) ** value.as_tuple().exponent
                    for value in [*amounts, printed]
                    if value != 0
                ),
                Decimal(0),
            )
            difference = sum(amounts, Decimal(0)) - printed
            incomplete_target = column == 3 and any(r[3] is None for r in items)
            if (
                any(value < 0 for value in amounts)
                or printed < 0
                or (
                    difference > bound if incomplete_target else abs(difference) > bound
                )
            ):
                return None, "unlabelled_subtotal_not_corroborated"
        recovered[index] = ("sub", *row[1:])
    return recovered, ""


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
    rows, layout_reason = _recover_revenue_layout_rows(list(_revenue_rows(tables)))
    if rows is None:
        return None, layout_reason
    grand = [r for r in rows if r[0] == "grand" and r[4] is not None]
    if not grand:
        return None, "no_grand_total"
    if len(grand) > 1:
        # Two counties' tables grouped as one — a caption was not found.
        return None, "more_than_one_grand_total"
    grand_target, grand_actual = grand[-1][3], grand[-1][4]
    if not grand_actual.is_finite() or grand_actual < 0:
        return None, "grand_total_is_negative_or_nonfinite"
    if any(r[0] in ("item", "sub") and r[4] is None for r in rows):
        # A cell in the receipts column that is not a number ("n/a", "NaN",
        # a merged cell): the streams cannot be proven to add up.
        return None, "unreadable_receipts_cell"

    lettered = any(r[1] for r in rows if r[0] == "header")
    sections: List[_RevenueSection] = []
    current: Optional[_RevenueSection] = None
    for kind, is_lettered, label, target, actual, observed, blank in rows:
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
            if (
                not top
                and current is not None
                and current.actual_sub is not None
                and current.stream == stream == "Additional Allocations"
            ):
                current.nested_grant_headings_after_subtotal += 1
            if top:
                current = _RevenueSection(stream=stream, label=label)
                sections.append(current)
                if actual is not None:
                    current.actual_items += actual
                    current.target_items += target or Decimal(0)
                    current.target_unreadable = target is None
                    current.receipts_observed = observed
                    current.blank_items = blank
                    current.nil_heading = actual == 0 and not observed and not blank
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
            current.receipts_observed = observed
            current.blank_subtotal = blank
            current.actual_checkpoints.append((actual, current.actual_items))
            current.target_checkpoints.append((target, current.target_items))
        elif kind == "item" and actual is not None:
            current.actual_items += actual
            current.receipts_observed = current.receipts_observed or observed
            current.blank_items = current.blank_items or blank
            if target is None:
                current.target_unreadable = True
            else:
                current.target_items += target

    if not sections:
        return None, "no_sections"
    for section in sections:
        if section.subtotals <= 1:
            continue
        if (
            section.subtotals != 2
            or section.stream != "Additional Allocations"
            or section.nested_grant_headings_after_subtotal != 1
        ):
            return None, "a_section_has_two_subtotals"

        def subtotal_mode(checkpoints):
            if any(value is None for value, _items in checkpoints):
                return None
            cumulative = all(
                abs(value - items) <= _REVENUE_TOLERANCE_KES
                for value, items in checkpoints
            )
            if cumulative:
                return checkpoints[-1][0]
            previous_items = Decimal(0)
            additive = True
            for value, items in checkpoints:
                if abs(value - (items - previous_items)) > _REVENUE_TOLERANCE_KES:
                    additive = False
                    break
                previous_items = items
            if additive:
                return sum((value for value, _items in checkpoints), Decimal(0))
            return None

        actual_sub = subtotal_mode(section.actual_checkpoints)
        if actual_sub is None:
            # Without item-by-item support, two subtotals may belong to
            # different streams; a matching grand total alone is insufficient.
            return None, "a_section_has_two_subtotals"
        section.actual_sub = actual_sub
        target_sub = subtotal_mode(section.target_checkpoints)
        if target_sub is None:
            section.target_unreadable = True
        else:
            section.target_sub = target_sub
    if any(
        (s.blank_subtotal and not (s.nil_heading and s.actual_items == 0))
        or (s.actual_sub is None and s.blank_items and not s.nil_heading)
        for s in sections
    ):
        # A section subtotal can substantiate blank constituent item cells.
        # Without that printed subtotal, a positive Grand Total elsewhere
        # cannot turn a missing stream receipt into zero. A printed dash on
        # the section heading is independent evidence of a nil stream even
        # when its subtotal cell is blank (Vihiga PDF p.864).
        return None, "unobserved_receipts_cell"
    if sum(1 for s in sections if s.stream == "Equitable Share") != 1:
        return None, "equitable_share_not_exactly_one_section"
    if any(s.actual < 0 for s in sections):
        return None, "negative_receipts_section"
    if grand_actual == 0 and any(not s.receipts_observed for s in sections):
        return None, "zero_total_has_unobserved_sections"
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
        self.revenue_coverage: Dict[str, Dict[str, Any]] = {}
        self._row_sources = None

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
        self._row_sources = None

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
        # Keep refusals in cached parses and ingestion receipts, including
        # counties for which no supported chapter table was extracted.
        for record in records:
            if record.get("category") == "Total":
                record["revenue_coverage"] = self.revenue_coverage.get(record["county"])

        logger.info(
            f"Parsed {len(records)} budget execution records from CoB report",
            extra={
                "source": str(self.pdf_path),
                "record_count": len(records),
                "categories": sorted({r.get("category") for r in records}),
            },
        )

        return records

    @staticmethod
    def _cash_total_cells(tables, target, actual):
        """Only direct Grand Total cells; stream sums need operand evidence.

        Cash B is selected by its own header. An accrual D column or the
        chapter summary cannot stand in for the receipts cell.
        """
        found = []
        for table in tables:
            headers = [_cell_text(c) for c in table.headers]
            cash_columns = [i for i, header in enumerate(headers) if _is_cash_revenue_header(header)]
            targets = [i for i, header in enumerate(headers) if "annual" in header or "target" in header]
            if len(cash_columns) != 1 or len(targets) != 1:
                continue
            cash, allocation = cash_columns[0], targets[0]
            for number, row in enumerate(table.rows, 1):
                if len(row) <= max(cash, allocation) or "grand total" not in _cell_text("".join(row[:allocation])):
                    continue
                if _kes_cell(row[cash]) != actual or (target is not None and _kes_cell(row[allocation]) != target):
                    continue
                found.append({measure: {"raw_value": str(value), "raw_token": row[column], "raw_unit": "KES",
                    "unit_checked": "ksh" in headers[column] or "kes" in headers[column],
                    "locator": {"page": table.page_number, "table": f"pdfplumber table {table.table_index + 1}",
                                "cell": f"Grand Total / row {number} / column {column + 1}: {table.headers[column]}"}}
                    for measure, column, value in (("allocated_amount", allocation, target), ("actual_spent", cash, actual)) if value is not None})
        return found[0] if len(found) == 1 else {}

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
        self.revenue_coverage = {
            county: {"status": "withheld", "reason": "no_supported_revenue_table", "pages": []}
            for county in KENYAN_COUNTIES
        }
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
            for item in self.revenue_coverage.values():
                item["reason"] = "revenue_captions_unreadable"
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
            source_pages = sorted({t.page_number for t in tables})
            self.revenue_coverage[county] = {
                "status": "reconciled" if streams is not None else "withheld",
                "reason": why or None,
                "pages": source_pages,
                "basis": "cash_receipts_including_opening_balance",
            }
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
                        "page_ref": "PDF pp. " + ", ".join(map(str, source_pages)),
                        "_pdf_cells": self._cash_total_cells(tables, target, actual) if stream == REVENUE_TOTAL else {},
                    }
                )
        reconciled = len(grouped) - len(refused)
        logger.info(
            "CoB revenue receipts: %d of %d counties reconcile to their own "
            "Grand Total",
            reconciled,
            len(KENYAN_COUNTIES),
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
                        "_pdf_cells": self._source_cells(row, {"allocated_amount": allocated_col, "actual_spent": absorbed_col}),
                    }
                )
            except (IndexError, ValueError) as e:
                logger.warning("Failed to parse row %s: %s", row, e)
                continue
        return out

    def _source_cells(self, row, columns):
        """Locate the original row even when the selected table was stitched.

        Ambiguous or reconstructed rows get no locator; the first page of a
        stitched table is never used as a substitute for the actual cell page.
        """
        if self._row_sources is None:
            self._row_sources = {}
            for original in self.tables:
                table = flatten_grouped_headers(original)
                for number, candidate in enumerate(table.rows, 1):
                    self._row_sources.setdefault(tuple(candidate), []).append((table, number, candidate))
        matches = self._row_sources.get(tuple(row), [])
        if len(matches) != 1:
            return {}
        table, number, candidate = matches[0]
        units = "million" in " ".join(table.headers).lower()
        return {measure: {"raw_value": str(parse_currency(candidate[column])[0]),
                          "raw_token": candidate[column], "raw_unit": "KES million",
                          "unit_checked": units,
                          "locator": {"page": table.page_number, "table": f"pdfplumber table {table.table_index + 1}",
                                      "cell": f"{candidate[0]} / row {number} / column {column + 1}: {table.headers[column]}"}}
                for measure, column in columns.items() if column < len(candidate)
                and parse_currency(candidate[column])[0] is not None}

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
                    "_pdf_cells": self._source_cells(row, {"allocated_amount": 1, "actual_spent": 2}),
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


# --------------------------------------------------------------------------
# county trade payables (pending bills) at the fiscal year end
# --------------------------------------------------------------------------
#
# The Controller of Budget's full-year County Governments Budget Implementation
# Review Report prints one table of every county's trade payables ("previously
# termed pending bills") at 30 June: Table 2.10 in the FY 2025/26 edition,
# Table 2.9 ("Pending Bills for the Counties") in FY 2024/25. The Treasury's
# Budget Review and Outlook Paper reprints it: BROP 2025 Table 10 is the
# FY 2024/25 table row for row, less Narok, and BROP 2026 Table 11 is the
# nine-month edition's verbatim (#238). This reads the original.
#
# Only a fiscal-year-end table is read. The quarterly editions print the same
# table at 30 September, 31 December and 31 March, but the stock is seasonal
# (183.0B, 177.5B, 156.8B, 172.5B through FY 2025/26), and they print "0.00"
# where the annual prints "-", so a county that sent nothing reads as a county
# that owes nothing.


class NotAYearEndTable(PDFParserError):
    """The report's county payables table is not stated at 30 June."""


_MONTHS = {
    m: i
    for i, m in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
        start=1,
    )
}

_DAY_MONTH_YEAR_RE = re.compile(
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?P<month>[A-Za-z]{3,9})\.?,?\s+(?P<year>20\d{2})"
)
_MONTH_DAY_YEAR_RE = re.compile(
    r"(?P<month>[A-Za-z]{3,9})\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<year>20\d{2})"
)


def parse_caption_date(text: str):
    """The date a table caption states: "30 June 2026", "30th June 2025",
    "30 Jun 2026", "30 June, 2026", "June 30, 2025". None when it names none."""
    from datetime import date

    for pattern in (_DAY_MONTH_YEAR_RE, _MONTH_DAY_YEAR_RE):
        m = pattern.search(text or "")
        if not m:
            continue
        month = _MONTHS.get(m.group("month")[:3].lower())
        if month is None:
            continue
        try:
            return date(int(m.group("year")), month, int(m.group("day")))
        except ValueError:
            continue
    return None


#: A List of Tables entry: "Table 2.10: Trade Payables for the Counties as of
#: 30 June 2026 .......17" (dot leaders in FY 2025/26, dashes in FY 2024/25).
_TOC_ENTRY_RE = re.compile(
    r"^\s*Table\s+(?P<num>\d+\.\d+)\s*:\s*(?P<title>.+?)\s*[.\-–— ]{3,}\s*(?P<page>\d{1,4})\s*$"
)
_COUNTIES_PAYABLES_TITLE_RE = re.compile(
    r"^(?:Trade\s+Payables|Pending\s+Bills)\s+for\s+the\s+Counties\s+as\s+(?:of|at)\s+(?P<date>.+)$",
    re.IGNORECASE,
)
#: "Baringo County Trade Payables as of 30 June 2026". "County Executive trade
#: payables Ageing Analysis" does not match: nothing may sit between "County"
#: and the table's name.
_COUNTY_PAYABLES_TITLE_RE = re.compile(
    r"^(?P<county>.+?)\s+County\s+(?:Trade\s+Payables|Pending\s+Bills)\s+as\s+(?:of|at)\s+(?P<date>.+)$",
    re.IGNORECASE,
)


def payables_toc_entries(text: str) -> Dict[str, Any]:
    """The payables tables a report's List of Tables names, with printed pages.

    Returns ``{"counties": (num, date, page) | None, "county": {name: (num,
    date, page)}}``. The List of Tables is read instead of the whole document
    because it is the cheap way to find ~50 pages among ~900: pdfplumber takes
    ~0.15s a page, and the nightly budget has no room for a full walk.
    """
    found: Dict[str, Any] = {"counties": None, "county": {}}
    for line in (text or "").splitlines():
        m = _TOC_ENTRY_RE.match(line)
        if not m:
            continue
        title, num, page = m.group("title"), m.group("num"), int(m.group("page"))
        whole = _COUNTIES_PAYABLES_TITLE_RE.match(title)
        if whole:
            # The latest-dated one: a report that also lists last year's
            # county table must not have it read as this year's.
            entry = (num, parse_caption_date(whole.group("date")), page)
            current = found["counties"]
            if current is None or (
                entry[1] is not None and (current[1] is None or entry[1] > current[1])
            ):
                found["counties"] = entry
            continue
        one = _COUNTY_PAYABLES_TITLE_RE.match(title)
        if one:
            county = canonical_county_label(one.group("county"))
            if _county_key(county) in {_county_key(c) for c in KENYAN_COUNTIES}:
                found["county"].setdefault(
                    county, (num, parse_caption_date(one.group("date")), page)
                )
    return found


#: Row sums are printed to the cent (FY 2025/26) or the tenth (FY 2024/25) of
#: a million; 0.5 absorbs the tenth-rounding and nothing a misread would make.
_PAYABLES_ROW_TOLERANCE_MILLIONS = Decimal("0.5")
#: More rows than this failing their own arithmetic is a misread table.
_PAYABLES_MAX_WITHHELD_ROWS = 3

_PAYABLES_COLUMNS = (
    "executive_recurrent", "executive_development", "executive",
    "assembly_recurrent", "assembly_development", "assembly",
    "total", "budget", "pct_of_budget",
)


def _millions_cell(cell: Optional[str]) -> Tuple[bool, Optional[Decimal]]:
    """``(printed, value)`` for a KSh-million cell.

    ``(False, None)`` for "-" or blank — nothing printed, which in this table
    is absence, never zero: Nandi's row is "-" in every column and "0" in the
    ratio column, and the report says Nandi did not report. ``(True, None)``
    for text that is not a number, so a misread cannot pass as a nil.
    """
    s = (cell or "").replace("\n", " ").strip()
    if s in ("", "-", "–", "—"):
        return False, None
    s = s.replace(",", "").replace(" ", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", s):
        return True, None
    return True, Decimal(s)


def _is_payables_summary_table(table: List[List[Optional[str]]]) -> bool:
    if not table or len(table[0]) not in (10, 11):
        return False
    header = " ".join((c or "") for c in table[0]).replace("\n", " ").lower()
    return "grand" in header and "county" in header and "assembly" in header


def county_payables_rows(
    tables: List[Tuple[int, List[List[Optional[str]]]]],
) -> Tuple[Dict[str, Dict[str, Any]], Optional[Dict[str, Optional[Decimal]]]]:
    """Read the county payables table from its pages' raw pdfplumber tables.

    ``tables`` is ``[(pdf_page, table), ...]`` in page order. Returns ``(rows,
    printed_total)``: one entry per county, and the table's own Total row. Only
    tables with this table's header are read, so the ageing analysis that
    follows it on the same page is not.
    """
    rows: Dict[str, Dict[str, Any]] = {}
    printed_total: Optional[Dict[str, Optional[Decimal]]] = None
    known = {_county_key(c): c for c in KENYAN_COUNTIES}
    for page, table in tables:
        if not _is_payables_summary_table(table):
            continue
        for raw in table:
            cells = [(c or "").replace("\n", " ").strip() for c in raw]
            if len(cells) == 11:
                # FY 2024/25 p.58: the budget column is split in two.
                cells = cells[:8] + [cells[8] or cells[9]] + [cells[10]]
            label = cells[0]
            marked = "*" in label
            key = _county_key(label.replace("*", ""))
            values = [_millions_cell(c) for c in cells[1:10]]
            if key == "total":
                printed_total = {
                    col: value for col, (_p, value) in zip(_PAYABLES_COLUMNS, values)
                }
                continue
            if key not in known:
                continue
            county = known[key]
            if county in rows:
                raise CountyTableIncomplete(
                    f"{county} appears twice in the county payables table"
                )
            rows[county] = {
                "county": county,
                "page": page,
                "cob_marked_inconsistent": marked,
                "cells": dict(zip(_PAYABLES_COLUMNS, values)),
                "unit_checked": "million" in "".join((c or "") for c in table[0]).lower().replace("-", "").replace("\n", ""),
            }
    return rows, printed_total


def classify_payables_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """What one county's row lets us publish.

    * ``reported`` — a Grand Total that is a number and equals its Executive
      plus Assembly sub-totals;
    * ``not_reported`` — nothing printed in the Grand Total (Nandi, FY 2025/26);
    * ``withheld`` — something printed that cannot be read, or that its own
      sub-totals contradict.
    """
    cells = row["cells"]
    total_printed, total = cells["total"]
    exec_printed, executive = cells["executive"]
    asm_printed, assembly = cells["assembly"]
    out = {
        "county": row["county"],
        "page": row["page"],
        "cob_marked_inconsistent": row["cob_marked_inconsistent"],
        "total_millions": None,
        "executive_millions": str(executive) if executive is not None else None,
        "assembly_millions": str(assembly) if assembly is not None else None,
        "executive_printed": exec_printed,
        "assembly_printed": asm_printed,
        "budget_millions": (
            str(cells["budget"][1]) if cells["budget"][1] is not None else None
        ),
        "status": "reported",
        "withheld_reason": None,
        "unit_checked": row.get("unit_checked", False),
    }
    if not total_printed:
        if exec_printed or asm_printed:
            out.update(status="withheld", withheld_reason="sub-totals printed with no total")
        else:
            out["status"] = "not_reported"
        return out
    if total is None:
        out.update(status="withheld", withheld_reason="total is not a number")
        return out
    if not exec_printed and not asm_printed:
        out.update(status="withheld", withheld_reason="a total with no sub-totals")
        return out
    if (exec_printed and executive is None) or (asm_printed and assembly is None):
        out.update(status="withheld", withheld_reason="a sub-total is not a number")
        return out
    parts = (executive or Decimal(0)) + (assembly or Decimal(0))
    if abs(parts - total) > _PAYABLES_ROW_TOLERANCE_MILLIONS:
        out.update(
            status="withheld",
            withheld_reason=f"Executive + Assembly = {parts} but the total is {total}",
        )
        return out
    out["total_millions"] = str(total)
    return out


def check_payables_against_printed_total(
    rows: Dict[str, Dict[str, Any]],
    printed_total: Optional[Dict[str, Optional[Decimal]]],
    source: str,
) -> None:
    """Refuse a county payables table that is not whole.

    All 47 counties, each once, and the Grand, Executive and Assembly columns
    summed to the table's own Total row. A county whose row was withheld still
    counts towards the sum — if its cells are numbers — so a withheld row
    cannot hide a misread column.
    """
    missing = [c for c in KENYAN_COUNTIES if c not in rows]
    if missing:
        raise CountyTableIncomplete(
            f"{len(missing)} of {len(KENYAN_COUNTIES)} counties missing from the "
            f"county payables table in {source}: {', '.join(missing)}"
        )
    if printed_total is None:
        raise CountyTableIncomplete(
            f"the county payables table in {source} has no Total row to check against"
        )
    # Rows that contradict their own sub-totals. One or two are the CoB's
    # typos and are withheld on their own; most of the table is a column
    # mapping misread — a phantom empty column shifts every row AND the Total
    # row alike, so the column sums below still agree (adversarial pass,
    # #238). Refuse it rather than publish nothing and call it a success.
    broken = [
        county for county, row in rows.items()
        if classify_payables_row(row)["status"] == "withheld"
    ]
    if len(broken) > _PAYABLES_MAX_WITHHELD_ROWS:
        raise CountyTableIncomplete(
            f"{len(broken)} county rows in {source} do not add up on their own "
            f"terms ({', '.join(sorted(broken)[:5])}...) — the columns are "
            "misread, not the report"
        )
    for col in ("total", "executive", "assembly"):
        printed = printed_total.get(col)
        if printed is None:
            raise CountyTableIncomplete(
                f"the county payables Total row in {source} prints no {col} figure"
            )
        parsed = sum(
            (r["cells"][col][1] or Decimal(0)) for r in rows.values()
        )
        if abs(parsed - printed) > _COUNTY_TOTAL_TOLERANCE_MILLIONS:
            raise CountyTableIncomplete(
                f"county payables {col} rows sum to {parsed:,} but the table "
                f"prints {printed:,} (out by {parsed - printed:+,}) in {source}"
            )


_SPACED_THOUSANDS_RE = re.compile(r"(\d),\s+(\d)")
_SHILLINGS_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
_SHILLINGS_OR_NIL_RE = re.compile(
    r"[-–]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)|(?<!\S)[-–](?!\S)"
)
#: The closing block's label: its formula, "e=a-c*b", which the report often
#: breaks across lines ("e=a-" / "c*b") so only its start is required — or, in
#: tables that print no formula (Nairobi, Kiambu, Turkana), a row label that
#: begins "Outstanding Trade Payables".
_CLOSING_FORMULA_RE = re.compile(
    r"(?<![A-Za-z])[eE]\s*=\s*a\s*-|^\s*Outstanding\s+trade", re.IGNORECASE
)
_STEP_HEADER_RE = re.compile(r"(?<![A-Za-z])a\s+b\s+c\s+d(?![A-Za-z])")


def chapter_closing_total(text: str) -> Optional[Decimal]:
    """The closing Total of one county's chapter payables table, in shillings.

    ``text`` runs from the table's caption to its "Source:" line. Only the
    FY 2025/26 layout is read: blocks lettered a to e down the page, the
    closing one labelled with its formula, "e=a-c*b", and its Total row the
    first after that label. The FY 2024/25 tables run the same steps ACROSS
    the page, and a "last Total row" rule read Nairobi's County Assembly
    (650.60m) as the county's closing balance. A layout this does not
    recognise returns None — no cross-check, never a guess.
    """
    # Printed in millions: the figure would be read as shillings.
    if re.search(r"million", text or "", re.IGNORECASE):
        return None
    lines = (text or "").splitlines()
    marker = next(
        (i for i, line in enumerate(lines) if _CLOSING_FORMULA_RE.search(line)), None
    )
    # "a b c d e=a-b-c+d" is a header row: the steps run across the page, the
    # layout this cannot read.
    if marker is None or _STEP_HEADER_RE.search(lines[marker]):
        return None
    # The row-wise layout has the opening balance, the amount paid and the
    # other blocks ABOVE the closing one. A marker with fewer than two Total
    # rows above it is a column header, and the first Total below it would be
    # one entity's figure, not the county's.
    if sum(1 for line in lines[:marker] if _is_total_row(line)) < 2:
        return None
    for line in lines[marker:]:
        if not _is_total_row(line):
            continue
        rest = _SPACED_THOUSANDS_RE.sub(r"\1,\2", line.split("Total", 1)[1])
        cells = _SHILLINGS_OR_NIL_RE.findall(rest)
        # Development, Recurrent, Total — three cells, or it is not this layout.
        if len(cells) != 3:
            return None
        closing = cells[-1]
        # A nil, or a negative balance, is not a closing stock to compare.
        if closing.startswith(("-", "–")):
            return None
        return Decimal(closing.replace(",", ""))
    return None


def _is_total_row(line: str) -> bool:
    """A "Total" row — not a "Sub-Total", and not a "Total (Kshs.)" header."""
    return bool(
        re.search(r"\bTotal\b", line)
        and not re.search(r"Total\s*\(", line)
        and not re.search(r"sub\s*-?\s*total", line, re.IGNORECASE)
    )


def fiscal_year_ending(as_at) -> str:
    """"FY 2025/26" for a year ending 30 June 2026."""
    return f"FY {as_at.year - 1}/{str(as_at.year)[2:]}"


def cbirr_year_end_trade_payables(pdf_path: Path) -> List[Dict[str, Any]]:
    """Every county's trade payables at 30 June, from a full-year CBIRR.

    Returns one dict per county (47), JSON-safe so the result can be cached by
    ``parse_cache``: amounts as decimal strings in KSh millions, the table's
    date as ISO. Raises :class:`NotAYearEndTable` when the table is dated
    anything but 30 June, and :class:`CountyTableIncomplete` when it is not
    whole.

    Each county also carries the closing Total of its own chapter table
    (Chapter 3, printed in shillings), so a reader can be told when the report
    disagrees with itself: Uasin Gishu's Table 2.10 row is KSh 1,153.72m and
    its chapter table KSh 1,481.44m. Table 2.10 is published, because it is
    the one that sums to the report's printed total.
    """
    from datetime import date as _date

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise PDFNotFoundError(f"PDF file not found: {pdf_path}")
    source = pdf_path.name
    with pdfplumber.open(pdf_path) as pdf:
        n_pages = len(pdf.pages)

        def page_text(pdf_page: int) -> str:
            if not 1 <= pdf_page <= n_pages:
                return ""
            page = pdf.pages[pdf_page - 1]
            try:
                return page.extract_text() or ""
            finally:
                page.flush_cache()

        toc_text = "\n".join(page_text(p) for p in range(1, min(40, n_pages) + 1))
        toc = payables_toc_entries(toc_text)
        if toc["counties"] is None:
            raise TableNotFoundError(
                f"no county trade payables table in the List of Tables of {source}"
            )
        num, as_at, printed_page = toc["counties"]
        if as_at is None or (as_at.month, as_at.day) != (6, 30):
            raise NotAYearEndTable(
                f"Table {num} in {source} is stated as at {as_at}, not 30 June"
            )

        # The List of Tables prints report page numbers; find the PDF page the
        # caption is actually on, and with it the offset for every other entry.
        caption = f"Table {num}:"
        summary_page = None
        for candidate in range(printed_page, min(printed_page + 80, n_pages) + 1):
            text = page_text(candidate)
            if caption in text and not _TOC_ENTRY_RE.search(
                next((ln for ln in text.splitlines() if caption in ln), "")
            ):
                summary_page = candidate
                break
        if summary_page is None:
            raise TableNotFoundError(f"{caption} not found in the body of {source}")
        offset = summary_page - printed_page

        tables: List[Tuple[int, List[List[Optional[str]]]]] = []
        for p in range(summary_page, min(summary_page + 3, n_pages + 1)):
            page = pdf.pages[p - 1]
            try:
                tables.extend((p, t) for t in page.extract_tables())
            finally:
                page.flush_cache()
        rows, printed_total = county_payables_rows(tables)
        check_payables_against_printed_total(rows, printed_total, source)

        results: Dict[str, Dict[str, Any]] = {
            county: classify_payables_row(row) for county, row in rows.items()
        }

        for county, (c_num, c_date, c_printed) in toc["county"].items():
            entry = results.get(county)
            if entry is None:
                continue
            entry["chapter_table"] = f"Table {c_num}"
            if c_date != as_at:
                continue
            c_caption = f"Table {c_num}:"
            expected = c_printed + offset
            for p in (expected, expected + 1, expected - 1, expected + 2, expected - 2):
                text = page_text(p)
                at = text.find(c_caption)
                if at < 0:
                    continue
                block = text[at:] + "\n" + page_text(p + 1)
                end = block.find("Source:")
                closing = chapter_closing_total(block[: end if end > 0 else None])
                if closing is not None:
                    entry["chapter_page"] = p
                    entry["chapter_total_millions"] = str(
                        (closing / Decimal(1_000_000)).quantize(Decimal("0.01"))
                    )
                break
            else:
                logger.info(
                    "county payables: %s's chapter table %s not found near PDF page %d",
                    county, c_num, expected,
                )

    fiscal_year = fiscal_year_ending(as_at)
    out: List[Dict[str, Any]] = []
    for county in KENYAN_COUNTIES:
        entry = results[county]
        entry.setdefault("chapter_table", None)
        entry.setdefault("chapter_page", None)
        entry.setdefault("chapter_total_millions", None)
        entry.update(
            as_at=as_at.isoformat() if isinstance(as_at, _date) else str(as_at),
            fiscal_year=fiscal_year,
            table=f"Table {num}",
            printed_total_millions=str(printed_total["total"]),
        )
        out.append(entry)
    logger.info(
        "county payables: %s Table %s as at %s — %d reported, %d not reported, "
        "%d withheld, %d marked inconsistent by the CoB",
        source, num, as_at,
        sum(1 for e in out if e["status"] == "reported"),
        sum(1 for e in out if e["status"] == "not_reported"),
        sum(1 for e in out if e["status"] == "withheld"),
        sum(1 for e in out if e["cob_marked_inconsistent"]),
    )
    return out


class CbirrYearEndPayablesParser:
    """:func:`cbirr_year_end_trade_payables` as a bound ``parse``.

    ``parse_cache`` keys an entry on the source file that defines the parse
    function. A lambda in the fetcher would be keyed on the FETCHER, so a fix
    here would go on serving the cached pre-fix parse; a method defined in
    this module is keyed on this module.
    """

    def __init__(self, pdf_path: Path):
        self.pdf_path = Path(pdf_path)

    def parse(self) -> List[Dict[str, Any]]:
        return cbirr_year_end_trade_payables(self.pdf_path)


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
