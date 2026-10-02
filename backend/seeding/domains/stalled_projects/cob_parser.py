"""Read the county "Stalled Projects" tables out of COB's CBIRR.

The Controller of Budget's *County Governments Budget Implementation Review
Report* (CBIRR) carries, inside each county's chapter, a table captioned::

    Table 3.11: Baringo County Stalled Projects as of 30 June 2026

and, just above it, a sentence in the county's own terms::

    The County reported 23 stalled development projects as of 30 June 2026,
    with an estimated value of Kshs.163.32 million, of which an expenditure of
    Kshs.83.69 million had already been paid.

The annual edition also has a national Table 2.6 (count, value and amount
paid per county, in Kshs. million). This module reads all three and puts them
side by side; it never picks a winner. When they disagree, which they do
(FY2025/26: Kakamega's sentence says 26 projects and Kshs.848.95 million, its
table lists 10 rows totalling Kshs.241,277,062), the disagreement is part of
the output.

WHAT THIS MODULE REFUSES TO DO
------------------------------
* Turn a blank or "-" into 0. Missing is ``None`` with the printed text kept
  beside it. "Nil" and "no amount has been paid" are COB saying zero, and
  are read as 0.
* Guess a unit. The unit comes from the column header ("(Kshs.)",
  "(Kshs.Mn)", "(Kshs. Million)"). A column whose header names none has its
  figures withheld. Trans Nzoia FY2025/26 prints "874" under "(Kshs.)"
  against a Table 2.6 value of 874.00 million; the table is published as
  printed and the mismatch is flagged, not silently rescaled.
* Map columns by position. Layouts vary inside one edition: Kericho has no
  "No." column, Nandi prints a contract-sum layout with no amount-paid column,
  Baringo carries an extra accrued/balance pair. Columns are found by header
  text; a row whose percentage cell holds prose is flagged, not coerced.

Self-contained on purpose: ``parse_cache.parser_digest`` hashes this file, so
every helper the parse depends on must live here for a fix to invalidate
cached output.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger("seeding.stalled_projects.cob_parser")

#: Who is speaking in every row this module emits. COB compiles the tables
#: from county submissions ("Source: Baringo County Treasury" under each), so
#: the figures are the county's, published by COB — not COB's own audit.
REPORTED_BY = "County treasury, as reported to the Controller of Budget (CBIRR)"
REPORTED_BY_ASSEMBLY = (
    "County assembly, as reported to the Controller of Budget (CBIRR)"
)

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
assert len(KENYAN_COUNTIES) == 47

_MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january"), ("feb", "february"), ("mar", "march"),
            ("apr", "april"), ("may",), ("jun", "june"), ("jul", "july"),
            ("aug", "august"), ("sep", "sept", "september"),
            ("oct", "october"), ("nov", "november"), ("dec", "december"),
        ],
        start=1,
    )
    for m in names
}

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20,
}


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------

#: PDF text layers carry U+FFFE / U+00AD where the typesetter hyphenated
#: ("mil￾lion", "Pro￾jects"). Both mean "join these".
_SOFT_HYPHENS = re.compile("[\\ufffe\\u00ad]")


def clean(text: Optional[str]) -> str:
    """Single-line, soft-hyphen-free, whitespace-collapsed text."""
    if not text:
        return ""
    text = _SOFT_HYPHENS.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _dehyphenate(text: str) -> str:
    """Rejoin words the typesetter broke across lines ("Comple- tion")."""
    return re.sub(r"(\w)- (\w)", r"\1\2", text)


def parse_as_of(text: str) -> Optional[str]:
    """"30th June 2026" / "30 Jun 2026" / "30 June,2026" -> "2026-06-30"."""
    m = re.search(
        r"(\d{1,2})\s*(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\s*,?\s*(\d{4})", text or ""
    )
    if not m:
        m2 = re.search(r"([A-Za-z]{3,9})\s+(\d{1,2})\s*,\s*(\d{4})", text or "")
        if not m2:
            return None
        month, day, year = m2.group(1), m2.group(2), m2.group(3)
    else:
        day, month, year = m.group(1), m.group(2), m.group(3)
    mon = _MONTHS.get(month.lower())
    if not mon:
        return None
    try:
        return date(int(year), mon, int(day)).isoformat()
    except ValueError:
        return None


def _county_key(name: str) -> str:
    key = clean(name).lower().replace("’", "'")
    key = re.sub(r"\b(city|county|government|of|the)\b", " ", key)
    return re.sub(r"[^a-z]", "", key)


_COUNTY_KEYS = {_county_key(c): c for c in KENYAN_COUNTIES}


def normalise_county(printed: str) -> Optional[str]:
    """Map a county name as COB printed it to one of the 47, or ``None``.

    Exact match on letters first ("Nairobi City", "Tharaka-Nithi",
    "Murang’a"), then a unique prefix ("Elgeyo"), then a close spelling
    ("Kakemega", "Elegyo-Marakwet"). Anything looser is refused: a caption
    filed under the wrong county is worse than one not filed at all. The
    printed form is always kept by the caller, so a corrected typo stays
    visible.
    """
    key = _county_key(printed)
    if not key:
        return None
    if key in _COUNTY_KEYS:
        return _COUNTY_KEYS[key]
    prefixed = [c for k, c in _COUNTY_KEYS.items() if k.startswith(key) and len(key) >= 4]
    if len(prefixed) == 1:
        return prefixed[0]
    # 0.85 and the same first two letters: "Kakemega" and "Elegyo-Marakwet"
    # (both printed by COB) pass; "East Pokot" (a Baringo sub-county) and
    # "Nyandira" do not become West Pokot and Nyamira.
    close = [
        k
        for k in difflib.get_close_matches(key, list(_COUNTY_KEYS), n=2, cutoff=0.85)
        if k[:2] == key[:2]
    ]
    if len(close) == 1 or (
        len(close) == 2
        and difflib.SequenceMatcher(None, key, close[0]).ratio()
        - difflib.SequenceMatcher(None, key, close[1]).ratio()
        > 0.1
    ):
        return _COUNTY_KEYS[close[0]]
    return None


def county_slug(county: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", county.lower().replace("'", "")).strip("-")
    return f"{slug}-county"


# --------------------------------------------------------------------------
# Numbers and units
# --------------------------------------------------------------------------

_MISSING = {"", "-", "–", "—", "_", "__", "n/a", "na", "not provided",
            "not given", "not available", "nan", "none"}
#: Words COB prints meaning "nothing was paid". A statement of zero, so 0.
_ZERO_WORDS = {"nil", "not paid", "no payment", "none paid"}


def unit_from_header(header: str) -> Optional[float]:
    """KES multiplier a column header declares, or ``None`` if it declares none."""
    h = clean(header).lower()
    if re.search(r"'000|’000|\b000s\b|thousand", h):
        return 1e3
    if re.search(r"billion|\bbn\b", h):
        return 1e9
    if re.search(r"million|\bmn\b|\bmns\b|kshs?\.?\s*m\b|\(m\)", h):
        return 1e6
    if re.search(r"\bk\s*shs?\b|\bkes\b|\bksh\b", h):
        return 1.0
    return None


def parse_amount(cell: Optional[str], unit: Optional[float]) -> Tuple[Optional[float], Optional[str]]:
    """``(value_in_kes, flag)`` for a money cell.

    ``flag`` is ``None`` for a clean read, otherwise one of ``missing``,
    ``unit_not_stated``, ``unparseable``. A missing figure is never 0.
    """
    text = clean(cell).lower()
    if text in _MISSING:
        return None, "missing"
    if text in _ZERO_WORDS:
        return 0.0, None
    text = re.sub(r"^k\s*shs?\.?\s*", "", text)
    # A space right after a thousands comma is typesetting ("1, 053,976.40",
    # Laikipia Q1); any other space separates two figures, and two figures
    # are not one amount.
    text = re.sub(r",\s+", ",", text)
    # 1,234,567 or 1,234,567.89 or 1234567.8 — and nothing else. "3,490.800.00"
    # (Uasin Gishu FY2025/26) is refused rather than guessed at.
    if not re.fullmatch(r"\d{1,3}(,\d{3})*(\.\d+)?|\d+(\.\d+)?", text):
        return None, "unparseable"
    if unit is None:
        return None, "unit_not_stated"
    return float(text.replace(",", "")) * unit, None


def parse_percent(cell: Optional[str]) -> Tuple[Optional[float], Optional[str]]:
    text = clean(cell).lower()
    if text in _MISSING:
        return None, "missing"
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*%?(?:\s*complete)?", text)
    if not m:
        return None, "not_a_percentage"
    value = float(m.group(1))
    if value > 100:
        return None, "percentage_over_100"
    return value, None


def _is_number(cell: Optional[str]) -> bool:
    return bool(re.fullmatch(r"[\d,.\s%]+", clean(cell))) and any(
        ch.isdigit() for ch in clean(cell)
    )


# --------------------------------------------------------------------------
# Column mapping
# --------------------------------------------------------------------------

#: (field, pattern) in priority order. A header cell takes the FIRST field
#: whose pattern it matches, and each field is taken once. Order matters:
#: "Expected Completion Date" must become ``expected_completion`` before the
#: percentage rule sees "completion"; "Outstanding Unpaid Balance" must not
#: become ``amount_paid``.
_COLUMN_RULES: Tuple[Tuple[str, str], ...] = (
    ("row_no", r"^(s/?\s*no\.?|s/n|no\.?|#|sn)$"),
    ("expected_completion", r"expected"),
    ("commencement", r"commence|start\s*date"),
    ("estimated_value", r"estimated\s*value|contract\s*sum|value\s*of\s*(the\s*)?project|project\s*(cost|value)"),
    ("amount_paid", r"^(?!.*\b(?:balance|not|yet|to be|percent\w*|outstanding)\b).*(?<!un)paid"),
    ("accrued_expenditure", r"accrued"),
    ("cumulative_expenditure", r"cumulative"),
    ("fy_funding", r"total\s*funding"),
    ("fy_expenditure", r"^expenditure"),
    ("outstanding_balance", r"outstanding|balance"),
    ("completion_pct", r"^(?!.*\bpaid\b).*(?:percent|completion|%)"),
    ("reason", r"reason|cause"),
    ("action", r"action|recovery"),
    ("sector", r"sector|department"),
    ("project_name", r"project\s*name|^project$|name\s*of\s*(the\s*)?project|description"),
    ("location", r"location|ward"),
)

MONEY_FIELDS = (
    "estimated_value", "amount_paid", "accrued_expenditure",
    "cumulative_expenditure", "outstanding_balance",
)


def header_key(cells: Sequence[Optional[str]]) -> Tuple[str, ...]:
    return tuple(_dehyphenate(clean(c)).lower() for c in cells)


def map_columns(header: Sequence[Optional[str]]) -> Dict[str, Any]:
    """Column index and declared unit per field, found by header text."""
    columns: Dict[str, int] = {}
    units: Dict[str, Optional[float]] = {}
    unmapped: List[str] = []
    for idx, raw in enumerate(header):
        text = _dehyphenate(clean(raw)).lower()
        if not text:
            continue
        for field, pattern in _COLUMN_RULES:
            if field in columns:
                continue
            if re.search(pattern, text):
                columns[field] = idx
                if field in MONEY_FIELDS:
                    units[field] = unit_from_header(text)
                break
        else:
            unmapped.append(_dehyphenate(clean(raw)))
    # A money column whose header names no unit takes its siblings' unit when
    # every sibling that does name one agrees (Kericho FY2025/26: "Estimated
    # Value of the Project (Kshs.)" beside a bare "Amount Paid on the stalled
    # project"). Flagged per row, and checked against COB's own totals by
    # reconcile() — which is what turns this from a guess into a test.
    declared = {u for u in units.values() if u is not None}
    inherited: List[str] = []
    if len(declared) == 1:
        (only,) = declared
        for field, unit in list(units.items()):
            if unit is None:
                units[field] = only
                inherited.append(field)
    return {"columns": columns, "units": units, "unmapped": unmapped, "inherited_units": inherited}


def looks_like_stalled_header(header: Sequence[Optional[str]]) -> bool:
    mapped = map_columns(header)["columns"]
    return "project_name" in mapped and (
        "estimated_value" in mapped or "amount_paid" in mapped
    )


# --------------------------------------------------------------------------
# Table rows
# --------------------------------------------------------------------------


def _is_total_row(cells: Sequence[str], cols: Dict[str, int]) -> bool:
    if any(re.fullmatch(r"(sub[- ]?)?totals?:?", c.lower()) for c in cells if c):
        return True
    # Samburu FY2025/26: the totals row has no label at all — only figures
    # under the money columns, with the number and name cells empty.
    name = cells[cols["project_name"]] if "project_name" in cols else ""
    no = cells[cols["row_no"]] if "row_no" in cols else ""
    money_idx = [cols[f] for f in MONEY_FIELDS if f in cols]
    return (
        not name
        and not no
        and any(_is_number(cells[i]) for i in money_idx if i < len(cells))
    )


def parse_table(
    header: Sequence[Optional[str]],
    rows: Iterable[Tuple[int, Sequence[Optional[str]]]],
) -> Dict[str, Any]:
    """Parse one caption's rows. ``rows`` is ``(pdf_page, cells)`` pairs.

    Returns ``{"rows", "total", "layout", "skipped"}``. Every row keeps its
    cells exactly as printed under ``cells`` (header text -> cell text), so
    whatever the field mapping concluded can be checked against the page.
    """
    mapping = map_columns(header)
    cols: Dict[str, int] = mapping["columns"]
    units: Dict[str, Optional[float]] = mapping["units"]
    head_key = header_key(header)
    header_labels = [_dehyphenate(clean(h)) or f"column {i + 1}" for i, h in enumerate(header)]

    out_rows: List[Dict[str, Any]] = []
    total: Optional[Dict[str, Any]] = None
    skipped: List[Dict[str, Any]] = []
    misaligned: List[Dict[str, Any]] = []
    group: Optional[str] = None

    for page, raw_cells in rows:
        cells = [clean(c) for c in raw_cells]
        if len(cells) < len(header):
            cells = cells + [""] * (len(header) - len(cells))
        if header_key(raw_cells) == head_key:
            continue  # header repeated on a continuation page
        filled = [c for c in cells if c]
        if not filled:
            continue
        if len(filled) == 1 and not _is_number(filled[0]) and (
            "project_name" not in cols
            or cells[cols["project_name"]] != filled[0]
            or re.search(r"\b(funded|financed|donor|projects|programmes?)\b", filled[0], re.I)
        ):
            # "County Funded Projects", "Donor Funded Projects". A lone name in
            # the project column that reads like a project (Kericho has no
            # "No." column) is a row with no figures, not a heading.
            group = filled[0]
            continue

        printed = {header_labels[i]: cells[i] for i in range(len(header_labels))}
        if _is_total_row(cells, cols):
            if total is not None:
                # A second "total" means rows without a name or number carry
                # figures — the header and data are out of step (Turkana
                # FY2024/25 prints every row one cell to the right and drops
                # the value column). Nothing in the table can be trusted to
                # its header; keep every line as printed and publish none.
                misaligned.append(total)
                misaligned.append({"source_page": page, "cells": printed})
                total = None
                continue
            if misaligned:
                misaligned.append({"source_page": page, "cells": printed})
                continue
            total = {"source_page": page, "cells": printed}
            for field in MONEY_FIELDS:
                if field in cols:
                    value, _flag = parse_amount(cells[cols[field]], units.get(field))
                    total[f"{field}_kes"] = value
            continue

        name = cells[cols["project_name"]] if "project_name" in cols else ""
        row_no = cells[cols["row_no"]] if "row_no" in cols else ""
        numbered = bool(re.fullmatch(r"\d+\.?", row_no))
        if not name and not numbered:
            skipped.append({"source_page": page, "cells": printed, "why": "no_project_name"})
            continue

        row: Dict[str, Any] = {
            "row_no": row_no.rstrip(".") or None,
            # Nairobi FY2025/26 row 41 has a number, a value and a cause, and
            # no project name. It is a row COB printed; it stays, unnamed.
            "project_name": name or None,
            "source_page": page,
            "group": group,
            "cells": printed,
            "flags": [] if name else ["project_name_blank"],
        }
        if len([c for c in raw_cells]) != len(header):
            row["flags"].append("row_width_differs_from_header")
        if "row_no" in cols and not numbered:
            # Baringo Q1 FY2025/26 lists five unnumbered components under
            # "9. Construction of Kabarnet Stadium"; COB counts 16, not 21.
            row["flags"].append("unnumbered_row")
        for field in ("sector", "location", "commencement", "expected_completion", "reason", "action"):
            if field in cols:
                row[field] = cells[cols[field]] or None
        for field in MONEY_FIELDS:
            if field not in cols:
                continue
            value, flag = parse_amount(cells[cols[field]], units.get(field))
            row[f"{field}_kes"] = value
            if flag and flag != "missing":
                row["flags"].append(f"{field}:{flag}")
            elif value is not None and field in mapping["inherited_units"]:
                row["flags"].append(f"{field}:unit_from_sibling_column")
        if "completion_pct" in cols:
            pct, flag = parse_percent(cells[cols["completion_pct"]])
            row["completion_pct"] = pct
            if flag and flag != "missing":
                row["flags"].append(f"completion_pct:{flag}")
        out_rows.append(row)

    if misaligned:
        for row in out_rows:
            misaligned.append({"source_page": row["source_page"], "cells": row["cells"]})
        skipped.extend(dict(m, why="header_and_data_misaligned") for m in misaligned)
        out_rows, total = [], None
    layout = {
        "misaligned": bool(misaligned),
        "columns": sorted(cols),
        "units": {f: units.get(f) for f in MONEY_FIELDS if f in cols},
        "unmapped_headers": mapping["unmapped"],
        "units_inherited": mapping["inherited_units"],
        "header": header_labels,
    }
    return {"rows": out_rows, "total": total, "layout": layout, "skipped": skipped}


# --------------------------------------------------------------------------
# Captions, chapters and COB's own sentences
# --------------------------------------------------------------------------

CAPTION_RE = re.compile(
    # "Baringo County Stalled Projects", "Baringo County List of Stalled
    # Projects" (FY2024/25), "Kitui County, List of ..." and "Kisii County
    # Assembly Stalled Projects" (Q1 FY2025/26) all occur.
    r"Table\s+(?P<table>3\.\d+)\s*:?\s*(?P<county>[A-Za-z’'\- ]{0,40}?)\s*,?\s*"
    r"County\s*,?\s*(?P<assembly>Assembly\s+)?(?:List\s+of\s+)?"
    r"Stalled\s+(?:Development\s+)?Projects?\s+as\s+(?:of|at)\s+"
    r"(?P<asof>\d{1,2}\s*(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s*,?\s*\d{4})",
    re.I,
)

CHAPTER_RE = re.compile(
    r"\b3\.(?P<n>\d{1,2})\.?\s+(?:The\s+)?(?:County\s+Government\s+of\s+)?"
    r"(?P<name>[A-Z][A-Za-z’'\- ]{2,30}?)(?:\s+City)?(?:\s+County)?\s+3\.(?P=n)\.?\s*1\b"
)

SUMMARY_RE = re.compile(
    r"(?P<who>The\s+County(?:\s+Assembly)?)\s+reported\s+(?P<n>\d+|[A-Za-z]+)\s+"
    # "as of 30 June 2026," / "as of 30 June, 2025," (Kitui FY2024/25) /
    # "as of September 30, 2025,".
    r"stalled\s+(?:development\s+)?projects?\s+(?:as\s+(?:of|at)\s+"
    r"(?P<date>\d{1,2}\s*(?:st|nd|rd|th)?\s+[A-Za-z]{3,9},?\s*\d{4}|[A-Za-z]{3,9}\s+\d{1,2},\s*\d{4}),?\s*)?"
    r"with\s+an\s+estimated\s+value\s+of\s+(?P<tail>.{0,260})",
    re.I,
)

#: Sentences in which COB records that a county gave it nothing. Quoted
#: verbatim; never converted into a count.
STATEMENT_RE = re.compile(
    r"[^.]{0,120}?\b(?:did\s+not\s+(?:report|disclose|provide|declare)|"
    r"reported\s+no\s+stalled|has\s+not\s+reported|not\s+reported\s+any|"
    r"was\s+not\s+submitted|were\s+not\s+submitted)"
    r"[^.]{0,160}?\.",
    re.I,
)

_AMOUNT_RE = re.compile(
    r"Kshs?\.?\s*(?P<v>\d[\d,]*(?:\.\d+)?)\s*(?P<u>billion|million|bn|mn)?", re.I
)


class Document:
    """All page texts joined, with a map from character offset to PDF page.

    Attribution is by offset, not by page: a county's chapter starts part-way
    down a page whose top half is the previous county's key issues. By page,
    Isiolo's "The County has 7 stalled development projects worth
    Kshs.1.77 billion" (FY2025/26 p.217) was filed under Kajiado.
    """

    def __init__(self, pages: Sequence[str]):
        self.pages = [clean(p) for p in pages]
        self.starts: List[int] = []
        parts: List[str] = []
        pos = 0
        for text in self.pages:
            self.starts.append(pos)
            parts.append(text)
            pos += len(text) + 1
        self.text = " ".join(parts)

    def page_of(self, offset: int) -> int:
        import bisect

        return bisect.bisect_right(self.starts, offset)


def find_captions(doc: "Document") -> List[Dict[str, Any]]:
    """Every body caption, skipping table-of-contents entries."""
    found: List[Dict[str, Any]] = []
    for m in CAPTION_RE.finditer(doc.text):
        after = doc.text[m.end(): m.end() + 12]
        if re.match(r"\s*\.{3,}", after) or re.match(r"\s*\.\s*\.", after):
            continue  # TOC line: caption followed by dot leaders
        printed = clean(m.group("county"))
        found.append(
            {
                "page": doc.page_of(m.start()),
                "offset": m.start(),
                "table_no": m.group("table"),
                "caption": clean(m.group(0)),
                "county_printed": printed,
                "county": normalise_county(printed) if printed else None,
                "as_of_printed": clean(m.group("asof")),
                "as_of": parse_as_of(m.group("asof")),
                "reported_by": REPORTED_BY_ASSEMBLY if m.group("assembly") else None,
            }
        )
    return found


def body_captions(captions: List[Dict[str, Any]], chapters: Dict[str, Tuple[int, int]]) -> List[Dict[str, Any]]:
    """Drop list-of-tables entries; keep one caption per table number.

    The FY2025/26 annual's list of tables uses dot leaders, which
    ``find_captions`` already skips. The FY2025/26 Q1 and FY2024/25 annual
    lists do not, so every caption appeared twice and the TOC copy pulled
    whatever table sat below it on a front-matter page. Anything before the
    first county chapter is front matter.
    """
    first = min((a for a, _ in chapters.values()), default=0)
    by_table: Dict[str, Dict[str, Any]] = {}
    for cap in captions:
        if cap["offset"] < first:
            continue
        by_table[cap["table_no"]] = cap
    return sorted(by_table.values(), key=lambda c: c["offset"])


#: Chapter 4 ("KEY OBSERVATIONS AND RECOMMENDATIONS") closes the last
#: county's chapter; without it West Pokot owned the national conclusions.
CHAPTER_4_RE = re.compile(r"\b4\.?\s+(?:KEY|CONCLUSION|GENERAL|RECOMMEND|CHALLENGES)[A-Z ,&]{3,60}")


def find_chapters(doc: "Document") -> Dict[str, Tuple[int, int]]:
    """``county -> (start_offset, end_offset)`` of each county's chapter 3.N."""
    by_n: Dict[int, Tuple[int, str]] = {}
    for m in CHAPTER_RE.finditer(doc.text):
        county = normalise_county(m.group("name"))
        if county:
            # Last occurrence wins: the body heading, not the TOC entry.
            by_n[int(m.group("n"))] = (m.start(), county)
    ordered = sorted(by_n.values())
    if not ordered:
        return {}
    end_all = len(doc.text)
    for m in CHAPTER_4_RE.finditer(doc.text, ordered[-1][0]):
        end_all = m.start()
        break
    chapters: Dict[str, Tuple[int, int]] = {}
    for i, (start, county) in enumerate(ordered):
        end = ordered[i + 1][0] if i + 1 < len(ordered) else end_all
        chapters.setdefault(county, (start, end))
    return chapters


def _word_or_int(token: str) -> Optional[int]:
    if token.isdigit():
        return int(token)
    return _NUMBER_WORDS.get(token.lower())


def parse_summary_sentence(text: str) -> Optional[Dict[str, Any]]:
    """COB's per-county sentence -> ``{count, value_kes, paid_kes, ...}``.

    A paid figure printed without a unit ("Kshs.218.98 has already been
    paid") inherits the value's unit and is flagged; "no amount has been
    paid" is a stated zero; a sentence with no paid clause leaves it ``None``.
    """
    m = SUMMARY_RE.search(clean(text))
    if not m:
        return None
    tail = m.group("tail")
    stop = re.search(r"(?<!Kshs)(?<!Ksh)\.(?=\s+[A-Z]|\s*$)", tail)
    tail = tail[: stop.start() + 1] if stop else tail
    sentence = clean(m.group(0)[: m.start("tail") - m.start()] + tail)
    amounts = list(_AMOUNT_RE.finditer(tail))
    flags: List[str] = []

    def _kes(am: re.Match, inherit: Optional[str]) -> Optional[float]:
        unit = (am.group("u") or inherit or "").lower()
        mult = {"billion": 1e9, "bn": 1e9, "million": 1e6, "mn": 1e6}.get(unit)
        if mult is None:
            return None
        return float(am.group("v").replace(",", "")) * mult

    def _tol(am: Optional[re.Match], unit_word: Optional[str]) -> Optional[float]:
        if am is None:
            return None
        mult = {"billion": 1e9, "bn": 1e9, "million": 1e6, "mn": 1e6}.get(
            (am.group("u") or unit_word or "").lower()
        )
        if mult is None:
            return None
        frac = re.search(r"\.(\d+)$", am.group("v"))
        digit = (10 ** -(len(frac.group(1)) if frac else 0)) * mult
        value = float(am.group("v").replace(",", "")) * mult
        # One unit of the last printed digit, capped at 1% of the figure:
        # "Kshs.1 billion" would otherwise accept anything from 0 to 2bn.
        return min(digit, max(0.01 * value, 10_000.0)) + 1.0

    value = _kes(amounts[0], None) if amounts else None
    value_unit = amounts[0].group("u") if amounts else None
    paid: Optional[float] = None
    not_paid = re.search(
        r"\b(?:not\s+(?:yet\s+)?been\s+paid|yet\s+to\s+be\s+paid|unpaid|outstanding|owed)\b", tail, re.I
    )
    if len(amounts) >= 2 and not_paid:
        # "of which Kshs.83.69 million has not been paid" is a balance, not a
        # payment. Kept in the sentence; not compared with the paid column.
        flags.append("second_amount_is_unpaid_balance")
    elif len(amounts) >= 2:
        if not amounts[1].group("u"):
            flags.append("paid_unit_not_printed_inherited_from_value")
        paid = _kes(amounts[1], value_unit)
        if not re.search(r"\bpaid\b", tail, re.I):
            # Kitui FY2024/25: "of which Kshs.476.92 million has been SPENT
            # towards the projects". Compared with the paid column, but the
            # word is COB's and the sentence is published beside it.
            if re.search(r"\bspent\b", tail, re.I):
                flags.append("second_amount_described_as_spent")
            else:
                # Machakos FY2024/25: "of which Kshs.314.26 million has been
                # allocated in the budget". Not a payment; not compared as one.
                flags.append("second_amount_described_as_other")
                paid = None
    elif re.search(r"no\s+amount\s+has\s+been\s+paid", tail, re.I):
        paid = 0.0
    who = m.group("who").lower()
    return {
        "sentence": sentence,
        # One unit of the last digit printed: "Kshs.281 million" is +/- 1M,
        # "Kshs.95.3 million" is +/- 0.1M.
        "value_tolerance_kes": _tol(amounts[0] if amounts else None, None),
        "paid_tolerance_kes": _tol(amounts[1] if len(amounts) >= 2 else None, value_unit),
        "count": _word_or_int(m.group("n")),
        "value_kes": value,
        "paid_kes": paid,
        "as_of": parse_as_of(m.group("date") or ""),
        "reported_by": REPORTED_BY_ASSEMBLY if "assembly" in who else REPORTED_BY,
        "flags": flags,
    }


# --------------------------------------------------------------------------
# Table 2.6 and the national sentence
# --------------------------------------------------------------------------

T26_CAPTION_RE = re.compile(
    r"Table\s+(?P<table>2\.\d+)\s*:?\s*County\s+Governments?\s+number\s+and\s+value\s+of\s+stalled",
    re.I,
)
NATIONAL_RE = re.compile(
    r"County\s+Governments\s+reported\s+(?P<n>\d+)\s+stalled\s+projects\s+valued\s+at\s+"
    r"Kshs\.?\s*(?P<v>[\d,.]+)\s*(?P<vu>billion|million),\s*of\s+which\s+"
    r"Kshs\.?\s*(?P<p>[\d,.]+)\s*(?P<pu>billion|million)",
    re.I,
)


def parse_table_2_6(rows: Iterable[Tuple[int, Sequence[Optional[str]]]]) -> Dict[str, Any]:
    """COB's national per-county table (Kshs. million), keyed by county.

    ``-`` is missing, not 0: in FY2025/26 it is printed for every county that
    reported nothing, and Trans Nzoia's count cell is simply blank while its
    value and paid cells are filled.
    """
    counties: Dict[str, Dict[str, Any]] = {}
    total: Optional[Dict[str, Any]] = None
    unit = 1e6
    for page, raw in rows:
        cells = [clean(c) for c in raw]
        if not cells or not cells[0]:
            continue
        label = cells[0]
        if re.search(r"no\s+of\s+stalled|value\s+of\s+projects", " ".join(cells), re.I):
            declared = unit_from_header(" ".join(cells[1:]))
            unit = declared or unit
            continue
        vals = (cells + ["", "", ""])[1:4]
        count_text, value_text, paid_text = vals
        count = int(count_text) if re.fullmatch(r"\d+", count_text) else None
        value, _ = parse_amount(value_text, unit)
        paid, _ = parse_amount(paid_text, unit)
        entry = {
            "printed": {"label": label, "count": count_text, "value": value_text, "paid": paid_text},
            "count": count,
            "value_kes": value,
            "paid_kes": paid,
            "source_page": page,
        }
        if label.lower().startswith("total"):
            total = entry
            continue
        county = normalise_county(label)
        if county:
            counties[county] = entry
    return {"counties": counties, "total": total, "unit_kes": unit}


# --------------------------------------------------------------------------
# Reconciliation
# --------------------------------------------------------------------------


def _tolerance(printed: Optional[str], unit: float) -> float:
    """One unit of the last printed digit, in KES.

    One, not a half: COB truncates as well as rounds. Kericho FY2025/26 sums
    to Kshs.280,325,251.32 and is printed "280.32 million" in both the
    sentence and Table 2.6.
    """
    m = re.search(r"\.(\d+)", printed or "")
    decimals = len(m.group(1)) if m else 0
    return (10 ** -decimals) * unit + 1.0


def _sentence_tolerance(value: Optional[float]) -> float:
    """The sentence prints two decimals of a million or of a billion."""
    return 0.01e9 if (value or 0) >= 1e9 else 0.01e6 + 1.0


def _sum_known(rows: List[Dict[str, Any]], key: str) -> Tuple[Optional[float], int]:
    vals = [
        r.get(key)
        for r in rows
        if isinstance(r.get(key), (int, float))
        and not isinstance(r.get(key), bool)
        and r.get(key) == r.get(key)  # NaN
    ]
    return (float(sum(vals)) if vals else None), len(vals)


def reconcile(
    rows: List[Dict[str, Any]],
    table_total: Optional[Dict[str, Any]],
    summary: Optional[Dict[str, Any]],
    t26: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compare the table's rows with COB's three statements about them.

    Every comparison that can be made is reported, agreeing or not. Status is
    ``agrees`` only if at least one comparison was possible and none failed.
    """
    checks: List[Dict[str, Any]] = []
    # Count what COB counts: numbered rows, when the table numbers them.
    numbered = [r for r in rows if "unnumbered_row" not in r.get("flags", [])]
    counted = len(numbered)
    value_sum, value_rows = _sum_known(rows, "estimated_value_kes")
    paid_sum, paid_rows = _sum_known(rows, "amount_paid_kes")

    def add(what: str, ours: Any, theirs: Any, source: str, tol: float = 0.0) -> None:
        if ours is None or theirs is None:
            checks.append({"check": what, "rows": ours, "cob": theirs, "cob_source": source, "agrees": None})
            return
        agrees = abs(float(ours) - float(theirs)) <= tol
        checks.append({"check": what, "rows": ours, "cob": theirs, "cob_source": source, "agrees": agrees})

    if summary:
        add("count", counted, summary.get("count"), "county summary sentence")
        add("estimated_value_kes", value_sum, summary.get("value_kes"), "county summary sentence",
            tol=summary["value_tolerance_kes"] if summary.get("value_tolerance_kes") is not None
            else _sentence_tolerance(summary.get("value_kes")))
        add("amount_paid_kes", paid_sum, summary.get("paid_kes"), "county summary sentence",
            tol=summary["paid_tolerance_kes"] if summary.get("paid_tolerance_kes") is not None
            else _sentence_tolerance(summary.get("paid_kes")))
    if table_total:
        add("estimated_value_kes", value_sum, table_total.get("estimated_value_kes"), "table total row", tol=1.0)
        add("amount_paid_kes", paid_sum, table_total.get("amount_paid_kes"), "table total row", tol=1.0)
    if t26:
        add("count", counted, t26.get("count"), "Table 2.6")
        add("estimated_value_kes", value_sum, t26.get("value_kes"), "Table 2.6",
            tol=_tolerance((t26.get("printed") or {}).get("value"), 1e6))
        add("amount_paid_kes", paid_sum, t26.get("paid_kes"), "Table 2.6",
            tol=_tolerance((t26.get("printed") or {}).get("paid"), 1e6))

    # A thousand- or million-fold gap is not a disagreement about the
    # figures, it is a disagreement about the unit (Trans Nzoia FY2025/26:
    # "874" under "(Kshs.)", 874.00 in Table 2.6's Kshs. million). Those
    # fields are named so the writer can withhold them rather than publish
    # a Kshs.874 business centre.
    unit_conflicts = sorted(
        {
            c["check"]
            for c in checks
            if c["agrees"] is False
            and c["check"] != "count"
            and c["rows"]
            and c["cob"]
            and any(
                abs(float(c["cob"]) / float(c["rows"]) / f - 1) < 0.02
                for f in (1e3, 1e6)
            )
        }
    )
    # A column shift: the rows' figure for one field matches what COB states
    # for ANOTHER field, and not what it states for its own (Garissa Q1
    # FY2025/26: every value is printed under "Amount Paid", so the paid
    # column sums to the sentence's Kshs.283.54 million value).
    column_shift = []
    stated: List[Tuple[str, str, float, float]] = []  # (source, field, KES, tolerance)
    if summary:
        for field, key in (("estimated_value_kes", "value"), ("amount_paid_kes", "paid")):
            amount = summary.get(f"{key}_kes")
            if amount:
                tol = summary.get(f"{key}_tolerance_kes") or _sentence_tolerance(amount)
                stated.append(("county summary sentence", field, amount, tol))
    if t26:
        for field, key in (("estimated_value_kes", "value"), ("amount_paid_kes", "paid")):
            amount = t26.get(f"{key}_kes")
            if amount:
                stated.append(("Table 2.6", field, amount, _tolerance((t26.get("printed") or {}).get(key), 1e6)))
    sums = {"estimated_value_kes": value_sum, "amount_paid_kes": paid_sum}
    for field, total_rows in sums.items():
        if not total_rows:
            continue
        own = [a for s_, f, a, t in stated if f == field and abs(total_rows - a) <= t]
        other = [(s_, f) for s_, f, a, t in stated if f != field and abs(total_rows - a) <= t]
        if other and not own:
            column_shift.append({"field": field, "matches": other})

    decided = [c["agrees"] for c in checks if c["agrees"] is not None]
    # A gap is any row missing a figure COB states a total for — whether or
    # not the rows that do carry one happened to agree.
    gaps = (value_rows < len(rows) and any(c["check"] == "estimated_value_kes" and c["cob"] is not None for c in checks)) or (
        paid_rows < len(rows) and any(c["check"] == "amount_paid_kes" and c["cob"] is not None for c in checks)
    )
    if not decided:
        status = "unverifiable"
    elif not all(decided):
        status = "disagrees"
    else:
        # Agreement reached while some rows had no readable figure: the rows
        # that DO carry one sum to COB's number, which is a narrower claim.
        status = "agrees_with_gaps" if gaps else "agrees"
    return {
        "status": status,
        "rows": len(rows),
        "estimated_value_kes_sum": value_sum,
        "estimated_value_rows": value_rows,
        "amount_paid_kes_sum": paid_sum,
        "amount_paid_rows": paid_rows,
        "rows_numbered": counted,
        "unit_conflicts": unit_conflicts,
        "column_shift": column_shift,
        "checks": checks,
    }


# --------------------------------------------------------------------------
# The PDF
# --------------------------------------------------------------------------


def page_texts(pdf_path: Path) -> List[str]:
    """Plain text per page via pdfium: ~3s for 935 pages, against minutes
    for pdfplumber, which is then only opened on the ~60 pages that hold a
    caption or its continuation."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        return [doc[i].get_textpage().get_text_range() for i in range(len(doc))]
    finally:
        doc.close()


def _caption_top(page: Any, table_no: str) -> Optional[float]:
    hits = page.search(rf"Table\s*{re.escape(table_no)}\b", regex=True)
    if hits:
        return hits[0]["top"]
    hits = page.search(r"Stalled\s+Projects?\s+as", regex=True)
    return hits[0]["top"] if hits else None


def _next_caption_top(page: Any, after: float) -> Optional[float]:
    tops = [h["top"] for h in page.search(r"Table\s*\d+\.\d+\s*:", regex=True) if h["top"] > after + 1]
    return min(tops) if tops else None


def _extract_caption_rows(pdf: Any, cap: Dict[str, Any]) -> Tuple[Optional[List[str]], List[Tuple[int, List[Optional[str]]]], List[str]]:
    """Header and ``(page, cells)`` rows for one caption, across page breaks."""
    notes: List[str] = []
    page_no = cap["page"]
    page = pdf.pages[page_no - 1]
    top = _caption_top(page, cap["table_no"]) or 0.0
    below = [t for t in page.find_tables() if t.bbox[1] >= top - 2]
    below.sort(key=lambda t: t.bbox[1])
    if below:
        first = below[0]
        more_on_page = len(below) > 1
    else:
        # Caption at the foot of the page; its table starts overleaf.
        page_no += 1
        if page_no > len(pdf.pages):
            return None, [], ["caption_without_table"]
        nxt = sorted(pdf.pages[page_no - 1].find_tables(), key=lambda t: t.bbox[1])
        if not nxt:
            return None, [], ["caption_without_table"]
        first, more_on_page = nxt[0], len(nxt) > 1
    table = first.extract()
    if not table or not looks_like_stalled_header(table[0]):
        return (table[0] if table else None), [], ["first_table_is_not_a_stalled_projects_table"]
    header = table[0]
    rows: List[Tuple[int, List[Optional[str]]]] = [(page_no, r) for r in table[1:]]
    head_key = header_key(header)

    # Follow the table overleaf while it is the page's first table, nothing
    # captioned sits above it, and it carries the same header (or the same
    # width, for a continuation printed without one).
    while not more_on_page and page_no < len(pdf.pages):
        nxt_page = pdf.pages[page_no]
        tables = sorted(nxt_page.find_tables(), key=lambda t: t.bbox[1])
        if not tables:
            break
        cand = tables[0]
        cap_top = _next_caption_top(nxt_page, -10)
        if cap_top is not None and cap_top < cand.bbox[1]:
            break
        extracted = cand.extract()
        if not extracted:
            break
        same_header = header_key(extracted[0]) == head_key
        same_width = len(extracted[0]) == len(header) and _is_number(extracted[0][0] or "")
        if not (same_header or same_width):
            break
        page_no += 1
        rows.extend((page_no, r) for r in (extracted[1:] if same_header else extracted))
        more_on_page = len(tables) > 1
        notes.append(f"continued_on_page_{page_no}")
    return header, rows, notes


def _table_2_6_rows(pdf: Any, pages: Sequence[str]) -> Tuple[Optional[Dict[str, Any]], List[Tuple[int, List[Optional[str]]]]]:
    for idx, raw in enumerate(pages):
        text = clean(raw)
        m = T26_CAPTION_RE.search(text)
        if not m or re.match(r"[^\n]{0,120}\.{4,}", text[m.end():m.end() + 140]):
            continue
        rows: List[Tuple[int, List[Optional[str]]]] = []
        for page_no in (idx + 1, idx + 2):
            if page_no > len(pdf.pages):
                break
            for t in pdf.pages[page_no - 1].find_tables():
                data = t.extract()
                if data and re.search(r"stalled|value\s+of\s+projects", " ".join(clean(c) for c in data[0]), re.I):
                    rows.extend((page_no, r) for r in data)
        if rows:
            return {"page": idx + 1, "table_no": m.group("table")}, rows
    return None, []


def _text_table_2_6(pages: Sequence[str], start: int) -> List[Tuple[int, List[str]]]:
    """Fallback when Table 2.6 is not ruled: read "<County> n v p" lines."""
    rows: List[Tuple[int, List[str]]] = []
    for page_no in (start, start + 1):
        if page_no > len(pages):
            break
        for line in pages[page_no - 1].splitlines():
            line = clean(line)
            m = re.fullmatch(r"([A-Za-z’'\- ]+?)\s+(\d+|-)?\s*([\d,.]+|-)\s+([\d,.]+|-)", line)
            if m and (normalise_county(m.group(1)) or m.group(1).lower().startswith("total")):
                rows.append((page_no, [m.group(1), m.group(2) or "", m.group(3), m.group(4)]))
    return rows


# Only these retained annual passages have a local ingestion decision.
# Keep helpers and binding evidence here: parser_digest hashes this entire file.
NARRATIVE_SOURCE = {
    "url": "https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/?wpdmdl=16482",
    "sha256": "5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3",
    "pages": 935,
    "fiscal_year": "2025/2026",
    "publisher": "Office of the Controller of Budget",
    "scope": "annual",
}
NARRATIVE_EVIDENCE = {
    "nyamira-summary": {
        "source_ref": "cob_annual",
        "pdf_page": 686,
        "printed_page": 652,
        "paragraph": None,
        "anchor": "county stalled-development summary",
        "excerpt": "The County reported one stalled development project as of 30 June 2026, with an estimated value of\nKshs.34.38 million, of which Kshs.26.62 million has already been paid.",
    },
    "nyamira-named": {
        "source_ref": "cob_annual",
        "pdf_page": 686,
        "printed_page": 652,
        "paragraph": None,
        "anchor": "named Speaker’s Residence narrative",
        "excerpt": "The stalled project was the County Assembly Speaker’s Residence in Bonyamatuta Ward, which was start-\ned in February 2023. It was estimated at Kshs.34.38 million, with Kshs.26.65 million paid as of 30 June\n2026, and reported at 77 per cent completion. There was no budget allocation to complete the Speaker’s\nresidence, and the County Assembly needs to allocate funds to complete the project.",
    },
    "siaya-named": {
        "source_ref": "cob_annual",
        "pdf_page": 758,
        "printed_page": 724,
        "paragraph": None,
        "anchor": "named Nyamonye narrative",
        "excerpt": "The County reported 1 stalled development project as of 30 June 2026, with an estimated value of\nKshs.1.88 million, of which Kshs.3.72 million has already been paid. The stalled project is the completion\nof Nyamonye Juakali, located in Yimbo East, which is currently under investigation.",
    },
}


def _source_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _narrative_text(text: str) -> str:
    # Only PDF typography/whitespace is normalized, never wording or numbers.
    return re.sub(r"([A-Za-z])- ([A-Za-z])", r"\1\2", clean(text))


def _narrative_date(value: str, precision: str = "day") -> dict:
    pattern = r"\d{4}-\d{2}-\d{2}" if precision == "day" else r"\d{4}-\d{2}"
    if (
        precision not in {"day", "month"}
        or not isinstance(value, str)
        or not re.fullmatch(pattern, value)
    ):
        raise ValueError("invalid_narrative_date")
    date.fromisoformat(value if precision == "day" else value + "-01")
    return {"value": value, "precision": precision, "reason": None}


def _narrative_statement(
    literal: str, source_unit: str, evidence_ref: str, scope: str, as_of: dict
) -> dict:
    if not isinstance(literal, str) or not re.fullmatch(
        r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", literal
    ):
        raise ValueError("invalid_source_decimal")
    if source_unit not in {"KES", "KES_million", "percent"}:
        raise ValueError("invalid_source_unit")
    n = Decimal(literal.replace(",", "")) * (1000000 if source_unit == "KES_million" else 1)
    if source_unit == "percent":
        if n > 100:
            raise ValueError("invalid_progress")
        value = int(n) if n == n.to_integral_value() else float(n)
    else:
        if n != n.to_integral_value():
            raise ValueError("fractional_KES_not_supported")
        value = int(n)
    return {
        "value": value,
        "unit": "percent" if source_unit == "percent" else "KES",
        "source_value": literal,
        "source_unit": source_unit,
        "evidence_ref": evidence_ref,
        "scope": scope,
        "as_of": as_of,
    }


def _narrative_corpus(county: str, excerpts: dict) -> dict:
    """Derive the observation from an already bound bounded passage, not a row template."""
    nyamira = county == "Nyamira"
    if county not in {"Nyamira", "Siaya"}:
        raise ValueError("unapproved_narrative_county")
    named = "nyamira-named" if nyamira else "siaya-named"
    text = _narrative_text(excerpts[named])
    evidence = {k: dict(NARRATIVE_EVIDENCE[k], excerpt=v) for k, v in excerpts.items()}
    at = _narrative_date(parse_as_of(re.search(r"as of (30 June\s+2026)", text).group(1)))
    money = re.findall(r"Kshs\.([\d,.]+) million", text)

    def stated(value):
        return {"state": "stated", "value": value, "reason": None}

    def missing(state, reason):
        return {"state": state, "value": None, "reason": reason}

    measures = {
        k: {
            "state": "absent",
            "reason": "Not stated in the bounded annual passage.",
            "statements": [],
        }
        for k in ("estimated_value", "contract_sum", "paid", "payable", "completion_pct")
    }

    def statement(literal, unit="KES_million", ref=named, scope="named_project"):
        return _narrative_statement(literal, unit, ref, scope, at)

    def slot(statements, conflict=False):
        return {
            "state": "conflicting" if conflict else "stated",
            "reason": "Named payment differs from the same-date singleton county summary; no winner selected."
            if conflict
            else None,
            "statements": statements,
        }

    measures["estimated_value"] = slot([statement(money[0])])
    paid = [statement(money[1])]
    milestones = []
    if nyamira:
        summary = _narrative_text(excerpts["nyamira-summary"])
        paid.append(
            statement(
                re.findall(r"Kshs\.([\d,.]+) million", summary)[1],
                ref="nyamira-summary",
                scope="county_summary_one_project",
            )
        )
        measures["completion_pct"] = slot(
            [statement(re.search(r"(\d+) per cent completion", text).group(1), "percent")]
        )
        commencement = re.search(r"started in ([A-Za-z]+) (\d{4})", text)
        commencement_month = f"{commencement.group(2)}-{_MONTHS[commencement.group(1).lower()]:02d}"
        milestones = [
            {
                "kind": "commencement",
                "date": _narrative_date(commencement_month, "month"),
                "evidence_ref": named,
            }
        ]
        name = re.search(r"project was the (.*?) in Bonyamatuta Ward", text).group(1)
        location = re.search(r"Residence in (.*?), which", text).group(1)
        institution = stated("Nyamira County Assembly")
    else:
        # Keep the exact line break in the printed name, independent of scalar parsing.
        name = re.search(r"project is the (.*?), located", excerpts[named], re.S).group(1).strip()
        location = re.search(r"located in (.*?), which", text).group(1)
        institution = missing(
            "unknown", "The bounded narrative does not identify the implementing institution."
        )
    measures["paid"] = slot(paid, conflict=nyamira)
    observation = {
        "observation_id": county.lower() + "-cob-annual",
        "county": {"official_code": "046" if nyamira else "041", "name": county},
        "name_as_printed": name,
        "location": stated(location),
        "reporting_body": stated(county + " County"),
        "implementing_institution": institution,
        "tender_reference": missing(
            "absent", "No shared tender or contract identifier is stated in the bounded narrative."
        ),
        "source_ref": "cob_annual",
        "fiscal_year": "2025/2026",
        "scope": "annual",
        "named_evidence_ref": named,
        "measures": measures,
        "milestones": milestones,
        "status": {
            "classification": "reported_stalled" if nyamira else "under_investigation",
            "evidence_ref": named,
            "as_of": at,
        },
    }
    return {
        "schema_version": 1,
        "decision": "accepted_for_local_implementation",
        "sources": {"cob_annual": dict(NARRATIVE_SOURCE)},
        "evidence": evidence,
        "observations": [observation],
        "relationships": [],
    }


def narrative_refusal(reason: str) -> dict:
    return {"schema_version": 1, "status": "refused", "reason": reason, "corpus": None}


def parse_bounded_narratives(pages: Sequence[str], edition: dict, sha256: str) -> dict:
    """Two exact anchors only. Refusal is optional evidence, never a table refusal."""
    result = {}
    doc = Document(pages)
    chapters = find_chapters(doc)
    edition_ok = (
        sha256 == NARRATIVE_SOURCE["sha256"]
        and edition.get("fiscal_year") == "FY2025/26"
        and edition.get("period") == "annual"
        and edition.get("pages") == NARRATIVE_SOURCE["pages"]
    )
    for county, keys, page, section in (
        ("Nyamira", ("nyamira-summary", "nyamira-named"), 686, "3.34.16"),
        ("Siaya", ("siaya-named",), 758, "3.38.16"),
    ):
        reason = None
        if not edition_ok:
            reason = "unapproved_source_hash_or_edition"
        elif len(pages) < page or county not in chapters:
            reason = "missing_page_or_county_chapter"
        else:
            raw = pages[page - 1]
            start, end = chapters[county]
            offset = doc.starts[page - 1] + doc.pages[page - 1].find("The County reported")
            if (
                not start <= offset < end
                or "Source: " + county + " County Treasury" not in raw
                or section not in raw
            ):
                reason = "county_page_context_mismatch"
            else:
                excerpts = {}
                for i, key in enumerate(keys):
                    # The first line has extraction-specific spacing; use its opening sentence.
                    opening = (
                        "The stalled project was"
                        if key == "nyamira-named"
                        else "The County reported"
                    )
                    a = raw.find(opening)
                    closing = "The stalled project was" if i + 1 < len(keys) else section
                    b = raw.find(closing, a + len(opening)) if a >= 0 else -1
                    if a < 0 or b < 0:
                        reason = "missing_bounded_passage"
                        break
                    excerpt = raw[a:b].strip()
                    if _narrative_text(excerpt) != _narrative_text(
                        NARRATIVE_EVIDENCE[key]["excerpt"]
                    ):
                        reason = "changed_bounded_passage"
                        break
                    excerpts[key] = excerpt
                if reason is None:
                    result[county] = {
                        "schema_version": 1,
                        "status": "accepted",
                        "reason": None,
                        "corpus": _narrative_corpus(county, excerpts),
                    }
        if reason is not None:
            logger.warning("stalled_projects narratives: %s refused: %s", county, reason)
            result[county] = narrative_refusal(reason)
    return result


def validate_bound_narratives(value: Any, edition: Any, county: Optional[str] = None) -> dict:
    """Strict read/write boundary: a shaped object is not source authority.

    Re-derive this bounded corpus from its retained evidence and require exact,
    typed JSON equality. Refuse changed names, measures, states, refs or unknown
    keys. Old schema-2 blocks without this optional collection remain readable.
    """
    try:
        if (
            type(value) is not dict
            or set(value) != {"schema_version", "status", "reason", "corpus"}
            or type(value["schema_version"]) is not int
            or value["schema_version"] != 1
        ):
            raise ValueError("invalid_narrative_envelope")
        if value["status"] == "refused":
            if (
                value["corpus"] is not None
                or not isinstance(value["reason"], str)
                or not value["reason"].strip()
            ):
                raise ValueError("invalid_narrative_refusal")
            return dict(value)
        if value["status"] != "accepted" or value["reason"] is not None:
            raise ValueError("invalid_narrative_status")
        if type(edition) is not dict or any(
            edition.get(k) != v
            for k, v in {
                "sha256": NARRATIVE_SOURCE["sha256"],
                "url": NARRATIVE_SOURCE["url"],
                "fiscal_year": "FY2025/26",
                "period": "annual",
            }.items()
        ):
            raise ValueError("narrative_source_edition_mismatch")
        corpus = value["corpus"]
        # JSON serialization rejects hostile nonfinite values; canonical equality
        # also distinguishes bool/int, absent/zero and unknown/stated.
        encoded = json.dumps(corpus, sort_keys=True, ensure_ascii=False, allow_nan=False)
        observation = corpus["observations"][0]
        name = observation["county"]["name"]
        if county is not None and county != name:
            raise ValueError("narrative_county_mismatch")
        keys = {"nyamira-summary", "nyamira-named"} if name == "Nyamira" else {"siaya-named"}
        if type(corpus["evidence"]) is not dict or set(corpus["evidence"]) != keys:
            raise ValueError("invalid_narrative_evidence")
        excerpts = {}
        for k in keys:
            e = corpus["evidence"][k]
            if (
                type(e) is not dict
                or type(e.get("excerpt")) is not str
                or _narrative_text(e["excerpt"])
                != _narrative_text(NARRATIVE_EVIDENCE[k]["excerpt"])
            ):
                raise ValueError("narrative_passage_binding_mismatch")
            excerpts[k] = e["excerpt"]
        expected = _narrative_corpus(name, excerpts)
        if encoded != json.dumps(expected, sort_keys=True, ensure_ascii=False, allow_nan=False):
            raise ValueError("narrative_shape_or_source_binding_mismatch")
        # Return a freshly derived copy, never a mutable reference into JSONB.
        return {"schema_version": 1, "status": "accepted", "reason": None, "corpus": expected}
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        OverflowError,
        RecursionError,
    ) as exc:
        logger.warning("stalled_projects narratives refused: %s", exc)
        return narrative_refusal(str(exc))


class CbirrStalledProjectsParser:
    """``CbirrStalledProjectsParser(path).parse()`` -> list of records.

    One ``{"kind": "edition"}`` record, then one ``{"kind": "county"}``
    record per county COB wrote anything about: a table, a sentence, a Table
    2.6 line, or a statement that the county reported nothing.
    """

    def __init__(self, pdf_path: Path):
        self.pdf_path = Path(pdf_path)

    def parse(self) -> List[Dict[str, Any]]:
        import pdfplumber

        pages = page_texts(self.pdf_path)
        doc = Document(pages)
        chapters = find_chapters(doc)
        captions = body_captions(find_captions(doc), chapters)
        edition = _edition_header(pages)
        edition["captions_found"] = len(captions)
        edition["chapters_found"] = len(chapters)
        national = None
        m = NATIONAL_RE.search(doc.text)
        if m:
            mult = {"billion": 1e9, "million": 1e6}
            national = {
                "sentence": clean(m.group(0)),
                "source_page": doc.page_of(m.start()),
                "count": int(m.group("n")),
                "value_kes": float(m.group("v").replace(",", "")) * mult[m.group("vu").lower()],
                "paid_kes": float(m.group("p").replace(",", "")) * mult[m.group("pu").lower()],
            }
        edition["national_summary"] = national

        counties: Dict[str, Dict[str, Any]] = {}
        unplaced: List[Dict[str, Any]] = []

        with pdfplumber.open(str(self.pdf_path)) as pdf:
            t26_meta, t26_rows = _table_2_6_rows(pdf, pages)
            if t26_meta and not t26_rows:
                t26_rows = _text_table_2_6(pages, t26_meta["page"])
            t26 = parse_table_2_6(t26_rows) if t26_rows else None
            if t26 is not None and t26_meta:
                t26.update(t26_meta)
            edition["table_2_6"] = (
                {k: v for k, v in t26.items() if k != "counties"} if t26 else None
            )

            for cap in captions:
                county = cap["county"]
                if county is None:
                    # A caption with its county name missing or unreadable:
                    # file it under the chapter it sits in, and say so.
                    county = next(
                        (c for c, (a, b) in chapters.items() if a <= cap["offset"] < b),
                        None,
                    )
                    cap["county_from"] = "chapter" if county else None
                if county is None:
                    unplaced.append(cap)
                    continue
                header, raw_rows, notes = _extract_caption_rows(pdf, cap)
                parsed = parse_table(header, raw_rows) if header and raw_rows else {
                    "rows": [], "total": None, "layout": {"header": header}, "skipped": []
                }
                rec = counties.setdefault(county, {"county": county})
                rec.setdefault("tables", []).append(
                    {
                        "caption": cap["caption"],
                        "caption_page": cap["page"],
                        "table_no": cap["table_no"],
                        "county_as_printed": cap["county_printed"],
                        "county_from": cap.get("county_from", "caption"),
                        "as_of": cap["as_of"],
                        "as_of_printed": cap["as_of_printed"],
                        "reported_by": cap.get("reported_by"),
                        "notes": notes,
                        **parsed,
                    }
                )

        for county, (start, end) in chapters.items():
            rec = counties.get(county)
            caps = [c for c in captions if start <= c["offset"] < end]
            # The county's sentence precedes its table; stop at the caption so
            # a key-issues recap later in the chapter is not read instead.
            stop = caps[0]["offset"] if caps else end
            m = SUMMARY_RE.search(doc.text, start, stop) or SUMMARY_RE.search(doc.text, start, end)
            if m:
                summary = parse_summary_sentence(doc.text[m.start(): m.start() + 600])
                if summary:
                    summary["source_page"] = doc.page_of(m.start())
                    counties.setdefault(county, {"county": county})["summary"] = summary
                    continue
            for sm in STATEMENT_RE.finditer(doc.text, start, end):
                if "stalled" in sm.group(0).lower():
                    counties.setdefault(county, {"county": county})["statement"] = {
                        "text": clean(sm.group(0)),
                        "source_page": doc.page_of(sm.start()),
                    }
                    break

        if t26:
            for county, entry in t26["counties"].items():
                counties.setdefault(county, {"county": county})["table_2_6"] = entry

        narratives = parse_bounded_narratives(pages, edition, _source_sha256(self.pdf_path))
        for county, collection in narratives.items():
            if county in counties:
                counties[county]["narratives"] = collection

        records: List[Dict[str, Any]] = [dict(edition, kind="edition", unplaced_captions=unplaced)]
        for county in sorted(counties):
            rec = counties[county]
            tables = rec.get("tables", [])
            rows = [r for t in tables for r in t["rows"]]
            total = next((t["total"] for t in tables if t.get("total")), None)
            rec["kind"] = "county"
            rec["slug"] = county_slug(county)
            rec["reconciliation"] = reconcile(rows, total, rec.get("summary"), rec.get("table_2_6"))
            records.append(rec)
        return records


def _edition_header(pages: Sequence[str]) -> Dict[str, Any]:
    """Title, fiscal year, period and publication month from the cover."""
    cover = clean(" ".join(pages[:3]))
    fy = re.search(r"(?:FY|FINANCIAL\s+YEAR)\s*(20\d{2})\s*/\s*(\d{2,4})", cover, re.I)
    period = "annual"
    low = cover.lower()
    if re.search(r"first\s+quarter", low):
        period = "first_quarter"
    elif re.search(r"first\s+half|half\s+year", low):
        period = "first_half"
    elif re.search(r"nine\s+months", low):
        period = "first_nine_months"
    published = re.search(
        r"\b(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER),?\s+(20\d{2})\b",
        cover,
    )
    return {
        "title": "County Governments Budget Implementation Review Report",
        "fiscal_year": f"FY{fy.group(1)}/{fy.group(2)[-2:]}" if fy else None,
        "period": period,
        "published": f"{published.group(1).title()} {published.group(2)}" if published else None,
        "pages": len(pages),
    }


__all__ = [
    "CbirrStalledProjectsParser",
    "REPORTED_BY",
    "REPORTED_BY_ASSEMBLY",
    "find_captions",
    "normalise_county",
    "parse_amount",
    "parse_percent",
    "parse_summary_sentence",
    "parse_table",
    "parse_table_2_6",
    "reconcile",
]
