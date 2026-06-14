"""Parse pending bills from the National Treasury BROP.

Why BROP and not the COB NG-BIRR
--------------------------------
The pending_bills domain was originally piped through the COB
National Government BIRR (NG-BIRR), but that report has zero
pending-bills tables — confirmed by walking the FY 2025/26 H1 PDF's
TOC and full text. The four pages that mention the phrase use it
incidentally inside Annex II Article 223 emergency-exchequer
justifications, not as published data. So the prior fetch+parse
path was structurally wrong (and the "derive pending = allocated −
absorbed" formula it fell back on was a non-sequitur — that's
unspent budget, not unpaid obligations).

Treasury's annual **Budget Review and Outlook Paper** (BROP),
published every September/October, is the cleanest live source:

* **Paragraph 18** carries the national aggregate split — total
  National Government pending bills, broken into State Corporations
  and MDAs. Three numbers in narrative prose; we extract via regex.
* **Table 10** ("County Governments Pending Bills as at 30th June
  YYYY") carries 47 per-county rows with County Executive
  {Recurrent, Development, Sub-Total} + County Assembly
  {Recurrent, Development, Sub-Total} + Total. We extract via
  text-mode parsing because pdfplumber's ``extract_tables`` returns
  31 columns of misaligned soup on this layout.

Caveats
-------
* **Annual cadence** (October). Fresh county-side data is published
  more frequently in the COB Consolidated County BIRR; that's a
  follow-up overlay using the same WPDM discovery from PR #78.
* The narrative para-48 cites "cumulative pending bills" of KSh
  195.5 B (statutory + payroll deductions included) but Table 10
  reports KSh 176.9 B. Table 10 is the audited per-county breakdown
  and what we persist; the 18.6B delta lives in the narrative only.
* National-side detail is sparse — BROP only publishes the two-line
  MDA-vs-SOE split, not per-MDA. Per-MDA pending bills require OAG
  audit OCR and stay on fixture for now.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple

import pdfplumber

from ...pdf_parsers import KENYAN_COUNTIES

logger = logging.getLogger(__name__)


# Para 18 anchor + capture pattern. Real text:
#   "The total outstanding National Government pending bills as at
#    30th June 2025 amounted to KSh 525.9 billion. These comprise of
#    KSh 404.3 billion (76.9 percent) and KSh 121.6 billion (23.1
#    percent) for the State Corporations and MDAs, respectively."
# Three "X billion" numbers in order: total, SOEs, MDAs. We require
# the trailing "State Corporations and MDAs" anchor AFTER the third
# number to make sure we're in the right paragraph (not catching a
# random three-billion-figure narrative elsewhere).
_NATIONAL_PARA_RE = re.compile(
    r"total\s+outstanding\s+National\s+Government\s+pending\s+bills"
    r".{0,200}?"
    r"(?P<total>[\d,]+\.?\d*)\s*billion"
    r".{0,300}?"
    r"(?P<soes>[\d,]+\.?\d*)\s*billion"
    r".{0,200}?"
    r"(?P<mdas>[\d,]+\.?\d*)\s*billion"
    r".{0,200}?"
    r"State\s+Corporations\s+and\s+MDAs",
    re.IGNORECASE | re.DOTALL,
)

# "as at 30th June 2025" → date(2025, 6, 30) — gives the records a
# stable measurement date for the writer's natural key.
_AS_AT_RE = re.compile(
    r"as\s+at\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?P<month>"
    r"January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(?P<year>\d{4})",
    re.IGNORECASE,
)

# Months map for _AS_AT_RE.
_MONTHS = {
    name.lower(): i + 1 for i, name in enumerate([
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ])
}

# Table 10 row pattern — one numbered county row in extract_text()
# output. The county name can span 1-2 tokens (e.g. "Homa Bay",
# "Trans Nzoia") or break across lines via a hyphen ("Tharaka- /
# Nithi", "Elgeyo- / Marakwet"); we pre-process the text to dehyphenate
# before applying this regex. Numeric columns may be "-" for empty
# cells. We capture the last 3 numbers (Total, FY Budget, %) which
# are present on every row; the Executive/Assembly sub-columns are
# extracted in a second pass.
_NUM = r"(?:[\d,]+\.\d+|[\d,]+|-)"
_COUNTY_ROW_RE = re.compile(
    r"^\s*(?P<no>\d{1,2})\.\s+"
    r"(?P<county>[A-Za-z][A-Za-z\s\-']+?)"
    r"\s+(?P<rest>(?:" + _NUM + r"\s+){4,9}" + _NUM + r")\s*$"
)


@dataclass(frozen=True)
class NationalPendingBills:
    """Para-18 national aggregate split.

    All amounts are in whole KShs (BROP publishes billions; the
    parser scales to match the fixture/writer convention).
    """
    as_at_date: date
    total: Decimal
    state_corporations: Decimal
    mdas: Decimal


@dataclass(frozen=True)
class CountyPendingBill:
    """One row of Table 10 for a single county."""
    county: str             # canonical county name (per KENYAN_COUNTIES)
    executive_recurrent: Optional[Decimal]
    executive_development: Optional[Decimal]
    executive_subtotal: Optional[Decimal]
    assembly_recurrent: Optional[Decimal]
    assembly_development: Optional[Decimal]
    assembly_subtotal: Optional[Decimal]
    total: Decimal
    fy_budget: Optional[Decimal]
    pct_of_budget: Optional[Decimal]


@dataclass(frozen=True)
class BropParseResult:
    """Combined output of a BROP parse pass."""
    fiscal_year_label: str   # e.g. "FY 2024/25"
    national: Optional[NationalPendingBills]
    counties: List[CountyPendingBill]


def _parse_kes_billion(token: str) -> Optional[Decimal]:
    """Parse "525.9" or "1,234" as KSh billions → whole KSh Decimal."""
    if token is None:
        return None
    cleaned = token.strip().replace(",", "")
    if not cleaned or cleaned == "-":
        return None
    try:
        return (Decimal(cleaned) * Decimal("1000000000")).quantize(Decimal("1"))
    except Exception:
        return None


def _parse_kes_million(token: str) -> Optional[Decimal]:
    """Parse "1,588.1" as KSh millions → whole KSh Decimal.
    Returns ``None`` for "-" or unparseable cells so the caller can
    leave the column unset rather than write 0.
    """
    if token is None:
        return None
    cleaned = token.strip().replace(",", "")
    if not cleaned or cleaned == "-":
        return None
    try:
        return (Decimal(cleaned) * Decimal("1000000")).quantize(Decimal("1"))
    except Exception:
        return None


def _detect_brop_fiscal_year(pdf: pdfplumber.PDF) -> str:
    """Read the cover for the BROP year (e.g. "2025"), then format
    as a Kenya fiscal-year label ending in that calendar year (BROP
    is published in Sep/Oct of the FY's first calendar year, so
    "2025 BROP" reports on FY 2024/25)."""
    text = ""
    for page in pdf.pages[:3]:
        text += "\n" + (page.extract_text() or "")
    m = re.search(r"(20\d{2})\s+BUDGET\s+REVIEW", text, re.IGNORECASE)
    if m:
        year = int(m.group(1))
        return f"FY {year - 1}/{str(year)[-2:]}"
    return "FY ?"


def _detect_national_paragraph(
    pdf: pdfplumber.PDF, fy_label: str,
) -> Optional[NationalPendingBills]:
    """Walk pages for the para-18 anchor + extract the 3 amounts.

    The as-at date normally lives in the paragraph itself ("as at
    30th June YYYY"). When the regex misses it (e.g. a rephrasing in
    a future BROP), we infer June 30 of the FY's second calendar
    year — BROPs are constitutionally tied to the FY end, so this is
    a correct semantic default, not a sentinel. The previous
    placeholder ``date(2000, 6, 30)`` would have produced a wrong
    natural key in the writer.
    """
    for page in pdf.pages[:30]:
        text = page.extract_text() or ""
        m = _NATIONAL_PARA_RE.search(text)
        if not m:
            continue
        total = _parse_kes_billion(m.group("total"))
        soes = _parse_kes_billion(m.group("soes"))
        mdas = _parse_kes_billion(m.group("mdas"))
        if total is None or soes is None or mdas is None:
            continue
        date_match = _AS_AT_RE.search(text)
        if date_match:
            as_at = date(
                int(date_match.group("year")),
                _MONTHS[date_match.group("month").lower()],
                int(date_match.group("day")),
            )
        else:
            as_at = _infer_fy_end_date(fy_label)
        return NationalPendingBills(
            as_at_date=as_at,
            total=total,
            state_corporations=soes,
            mdas=mdas,
        )
    return None


def _infer_fy_end_date(fy_label: str) -> date:
    """Infer the Kenya FY-end date (Jun 30 of the FY's second calendar
    year) from labels like ``"FY 2024/25"`` or ``"FY 2024/2025"``.
    Falls back to a recent FY-end if the label is unparseable so we
    never emit ``date(2000, …)`` again."""
    m = re.search(r"(20\d{2})\s*/\s*(\d{2,4})", fy_label)
    if m:
        first = int(m.group(1))
        return date(first + 1, 6, 30)
    # Last-resort: today's most recent past June 30. Better than a
    # millennium-old sentinel; still flagged via the missing-date log
    # below so it's visible to operators.
    today = date.today()
    if (today.month, today.day) >= (6, 30):
        return date(today.year, 6, 30)
    return date(today.year - 1, 6, 30)


def _dehyphenate_text(text: str) -> str:
    """Stitch back county names that pdfplumber broke across lines:
    "Tharaka- / Nithi" → "Tharaka-Nithi". Also fixes "Elgeyo- /
    Marakwet". We only join when the hyphen is the LAST character of
    a line and the next line starts with an uppercase letter."""
    lines = text.split("\n")
    out: List[str] = []
    skip = False
    for i, line in enumerate(lines):
        if skip:
            skip = False
            continue
        stripped = line.rstrip()
        if (
            i + 1 < len(lines)
            and stripped.endswith("-")
            and lines[i + 1].strip()
            and lines[i + 1].strip()[0].isupper()
        ):
            # Join: "...Tharaka-" + " " + "Nithi" + " ..." (rest of next line)
            out.append(stripped + lines[i + 1].lstrip())
            skip = True
        else:
            out.append(line)
    return "\n".join(out)


def _normalise_county(name: str) -> Optional[str]:
    """Map an extracted county-name fragment to the canonical
    KENYAN_COUNTIES form. Returns None if no match — callers treat
    that as "this row isn't a county row, skip it".

    Both sides go through the same lowercasing + apostrophe-strip +
    hyphen→space normalisation so "Murang'a" → "Murang'a", and a
    pdfplumber-truncated "Tharaka-" prefix-matches "Tharaka Nithi"
    (a real BROP failure mode where pdfplumber drops the second line
    of a wrapped county name).
    """
    def _norm(s: str) -> str:
        return re.sub(
            r"\s+",
            " ",
            s.lower().replace("'", "").replace("’", "")
             .replace("-", " "),
        ).strip()

    norm = _norm(" ".join(name.split()).rstrip(",").rstrip("-"))
    for canonical in KENYAN_COUNTIES:
        canon_norm = _norm(canonical)
        if norm == canon_norm:
            return canonical
        # Prefix-match for the wrapped-name case: "Tharaka" matches
        # "Tharaka Nithi", "Elgeyo" matches "Elgeyo Marakwet".
        # Only counties where the prefix is unambiguous are eligible
        # (no other county starts with the same first word).
        if " " in canon_norm and norm == canon_norm.split(" ", 1)[0]:
            # Verify uniqueness — if two canonicals share the first
            # word, refuse to guess.
            siblings = [
                c for c in KENYAN_COUNTIES
                if _norm(c).startswith(norm + " ") and c != canonical
            ]
            if not siblings:
                return canonical
    return None


_COUNTY_TABLE_TITLE_RE = re.compile(
    r"Table\s+\d+:\s*County\s+Governments\s+Pending\s+Bills",
    re.IGNORECASE,
)
_END_OF_COUNTY_TABLE_RE = re.compile(
    # Row of "Total ... Source: Controller of Budget" / next section
    # heading marks end of the table.
    r"^(?:Total\s|N/B|Source\s*:|\d+\.\s+(?:To\s+address|[A-Z][a-z]+\s+(?:Status|Issues|Risks))|"
    r"E\.\s+|F\.\s+)",
    re.IGNORECASE,
)


def _parse_county_table(pdf: pdfplumber.PDF) -> List[CountyPendingBill]:
    """Extract Table 10 ("County Governments Pending Bills as at
    YYYY-mm-dd") by walking pages from the first one whose text
    contains the table title; stop at the Total/N.B./Source row.

    Anchoring on the title prevents picking up earlier numbered
    tables (the BROP has at least one other table with county-style
    rows on page 23 that would otherwise pollute the parse).

    pdfplumber's ``extract_tables`` produces 30+-column misaligned
    noise on this layout, so we use ``extract_text`` line-by-line.
    """
    out: List[CountyPendingBill] = []
    seen: set = set()
    in_table = False
    # Section D of BROP is well within the front 40 pages — the
    # table title gates entry, so the page-range cap is just a sanity
    # bound to avoid scanning the whole 75-page doc on a malformed
    # PDF.
    for page in pdf.pages[:50]:
        raw = page.extract_text() or ""
        text = _dehyphenate_text(raw)
        for line in text.split("\n"):
            if not in_table:
                if _COUNTY_TABLE_TITLE_RE.search(line):
                    in_table = True
                continue
            if _END_OF_COUNTY_TABLE_RE.match(line):
                # The table can be split across pages, but the actual
                # END marker (Total / N/B / Source) only appears once.
                # After we hit it, we're permanently done.
                return out
            m = _COUNTY_ROW_RE.match(line)
            if not m:
                continue
            county = _normalise_county(m.group("county"))
            if not county or county in seen:
                continue
            tokens = m.group("rest").split()
            row = _parse_county_row_numbers(tokens)
            if row is None:
                continue
            seen.add(county)
            out.append(
                CountyPendingBill(
                    county=county,
                    executive_recurrent=row.get("exec_rec"),
                    executive_development=row.get("exec_dev"),
                    executive_subtotal=row.get("exec_sub"),
                    assembly_recurrent=row.get("asm_rec"),
                    assembly_development=row.get("asm_dev"),
                    assembly_subtotal=row.get("asm_sub"),
                    total=row["total"],
                    fy_budget=row.get("fy_budget"),
                    pct_of_budget=row.get("pct"),
                )
            )
    return out


def _parse_county_row_numbers(tokens: List[str]) -> Optional[dict]:
    """Distribute the captured numeric tokens across the column
    layout.

    The full row layout has 9 cells:
    ``exec_rec, exec_dev, exec_sub, asm_rec, asm_dev, asm_sub,
    total, fy_budget, pct``.

    BROP renders empty cells as "-" inline; the row regex captures
    those as tokens too, so when pdfplumber preserves them we get a
    9-element ``nums`` array with ``None`` placeholders that keep
    the column layout aligned. We DO NOT compress dashes out of the
    list — doing so was a real bug: a missing assembly-development
    cell would shift the assembly_subtotal into ``asm_dev``,
    misattributing the value (Copilot review on PR #81).

    For shorter rows pdfplumber sometimes drops a dash entirely
    (no token at all), making the breakdown ambiguous: with 5
    breakdown tokens we can't tell whether ``asm_dev`` or ``asm_rec``
    was the omitted cell. In that case we leave the ambiguous columns
    as ``None`` rather than guess. The persisted ``total_pending``
    (always the third-from-last token) is unaffected, so the only
    user-visible loss is some breakdown detail in the ``notes`` field.
    """
    nums = [_parse_kes_million(t) for t in tokens]
    if len(nums) < 3:
        return None
    # Last three: total, FY budget, pct — always present, never
    # rendered as dashes. The "%" column flows through the same KSh-
    # millions scaler so we divide back out for cosmetic display.
    pct_raw = nums[-1]
    pct = (pct_raw / Decimal("1000000")) if pct_raw is not None else None
    fy_budget = nums[-2]
    total = nums[-3]
    if total is None:
        return None

    out: dict = {"total": total, "fy_budget": fy_budget, "pct": pct}
    breakdown = nums[:-3]

    # Only assign all six breakdown columns when the row gave us
    # exactly six tokens (i.e. every cell rendered, dashes preserved
    # as None). For shorter rows pdfplumber dropped a cell silently
    # and we can't tell which slot it belonged in — leave the
    # breakdown unset there. Executive's three columns are reliable
    # (every county has Executive expenditure) so we keep those when
    # available.
    if len(breakdown) == 6:
        keys = (
            "exec_rec", "exec_dev", "exec_sub",
            "asm_rec", "asm_dev", "asm_sub",
        )
        for key, value in zip(keys, breakdown):
            out[key] = value
    elif len(breakdown) >= 3:
        out["exec_rec"], out["exec_dev"], out["exec_sub"] = breakdown[:3]
    return out


def parse_brop_pdf(pdf_path: Path) -> BropParseResult:
    """Parse a BROP PDF and return the structured pending-bills data."""
    with pdfplumber.open(pdf_path) as pdf:
        fy_label = _detect_brop_fiscal_year(pdf)
        national = _detect_national_paragraph(pdf, fy_label)
        counties = _parse_county_table(pdf)
    if national is None and not counties:
        raise ValueError(
            f"No pending-bills data found in {pdf_path.name} — "
            "neither the para-18 anchor nor the county table matched"
        )
    logger.info(
        "BROP parser extracted national=%s + %d counties (FY %s) from %s",
        "yes" if national else "no", len(counties),
        fy_label, pdf_path.name,
    )
    return BropParseResult(
        fiscal_year_label=fy_label,
        national=national,
        counties=counties,
    )


__all__ = [
    "BropParseResult",
    "CountyPendingBill",
    "NationalPendingBills",
    "parse_brop_pdf",
]
