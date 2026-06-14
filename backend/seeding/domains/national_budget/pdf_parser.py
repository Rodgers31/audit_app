"""Parser for the COB National Government BIRR PDF (Tables 2.5 + 2.6).

Why this exists
---------------
The national_budget domain originally piped the discovered NG-BIRR
PDF through ``CoBQuarterlyReportParser``, which is anchored on a
47-county invariant. That works for the *Consolidated County* BIRR
but not for the National Government BIRR — different document with
no per-county breakdown — so the parser raised
``TableNotFoundError`` and the domain silently fell back to fixture.

This parser targets two consolidated tables that DO exist in the
NG-BIRR:

* **Table 2.5** ("Sectoral Development Estimates and Exchequer
  Issues") — sub-table 0: 10 sectors × {Net Estimates, Exchequer
  Issues, %} for the current period and the comparative prior period.
* **Table 2.6** ("Sectoral Recurrent Estimates and Exchequer
  Issues") — sub-table at index 1: same shape, recurrent side.

Both have a clean 7-column layout:

    | Sector | NetEst | ExchIss | % | NetEst (prior) | ExchIss (prior) | % |

Sectors are coded by short tags (ARUD, EIICT, GECA, GJLO, PAIR,
EPWNR, SPCR + literal "Health" / "Education" / "National Security"),
with a "Total" row at the bottom.

Caveats
-------
* The NG-BIRR publishes **Exchequer Issues** at the sector level,
  not actual Expenditure. Exchequer Issues is the cash released by
  Treasury — the closest sector-level proxy for spending we have.
  We map it to ``actual_spent`` and call out the proxy in record
  notes. (Per-Vote actual Expenditure lives in the section-4
  sectoral analysis tables; harvesting that requires walking ~10
  per-sector tables and aggregating — a follow-up.)
* Values in the bulletin are KShs Billion; we scale to whole KShs
  to match the fixture's amount-in-shillings convention.
* Period detection reads the cover page descriptor
  ("FIRST SIX MONTHS", "FIRST QUARTER", etc.) and the FY label
  ("FY 2025/2026"). Annual reports are detected when neither a
  half/quarter/nine-months descriptor appears.
"""

from __future__ import annotations

import calendar
import logging
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pdfplumber

logger = logging.getLogger(__name__)


# COB's 10 canonical sectors. Short codes match the row labels in
# Tables 2.5/2.6; long names are what we emit as the BudgetLine
# ``category`` (the writer matches on this string, so we want a
# stable, human-readable canonical form).
_SECTORS: Tuple[Tuple[str, str], ...] = (
    ("ARUD", "Agriculture, Rural and Urban Development"),
    ("EIICT", "Energy, Infrastructure and ICT"),
    ("GECA", "General Economic and Commercial Affairs"),
    ("Health", "Health"),
    ("Education", "Education"),
    ("GJLO", "Governance, Justice, Law and Order"),
    ("PAIR", "Public Administration and International Relations"),
    ("National Security", "National Security"),
    ("SPCR", "Social Protection, Culture and Recreation"),
    ("EPWNR", "Environment Protection, Water, and Natural Resources"),
)
_SECTOR_CODES = {code.lower() for code, _ in _SECTORS}
_CODE_TO_NAME = {code.lower(): name for code, name in _SECTORS}

# Period descriptors on the cover page → (subperiod_label, end_month).
# Order matters: longer phrases first so "FIRST NINE MONTHS" doesn't
# greedy-match "FIRST".
_PERIOD_DESCRIPTORS: Tuple[Tuple[str, str, int], ...] = (
    ("FIRST NINE MONTHS", "9M", 3),    # Jul–Mar
    ("FIRST SIX MONTHS",  "H1", 12),   # Jul–Dec
    ("FIRST HALF",        "H1", 12),   # alt phrasing
    ("FIRST QUARTER",     "Q1", 9),    # Jul–Sep
    ("HALF YEAR",         "H1", 12),   # alt phrasing
)


@dataclass(frozen=True)
class PeriodInfo:
    """Resolved fiscal period for the report."""
    label: str          # e.g. "FY 2025/26 H1"
    start_date: date    # always Jul 1 of the FY's first calendar year
    end_date: date      # period-dependent


def _parse_kes_billion(cell: str) -> Optional[Decimal]:
    """Parse a "1,234.56" cell as KShs Billions → whole KShs Decimal.

    Handles a pdfplumber quirk where the decimal point in some bulletin
    cells is read back as a comma — e.g. "95,23" actually means
    "95.23" (PAIR Recurrent in FY 2025/26 H1). Heuristic: if the
    cell has no period AND the trailing fragment after the last comma
    is exactly two digits, that comma was a misread decimal point.
    Three-or-more-digit trailing fragments are real thousands
    separators and get stripped normally.

    Returns ``None`` for empty / unparseable cells so the caller can
    skip the row instead of writing a garbage Decimal.
    """
    if cell is None:
        return None
    cleaned = cell.strip()
    if not cleaned or cleaned.lower() in ("-", "n/a", "na"):
        return None
    if "," in cleaned and "." not in cleaned:
        last_comma = cleaned.rfind(",")
        after = cleaned[last_comma + 1:]
        if len(after) == 2 and after.isdigit():
            # Misread decimal: "95,23" → "95.23"; preserve any earlier
            # commas as thousands separators ("1,234,56" → "1234.56").
            cleaned = cleaned[:last_comma].replace(",", "") + "." + after
        else:
            cleaned = cleaned.replace(",", "")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        return (Decimal(cleaned) * Decimal("1000000000")).quantize(Decimal("1"))
    except Exception:
        return None


def _detect_period(pdf: pdfplumber.PDF) -> Optional[PeriodInfo]:
    """Read the first few pages for the period descriptor + FY label."""
    text = ""
    for page in pdf.pages[:3]:
        text += "\n" + (page.extract_text() or "")
    text_upper = text.upper()

    fy_match = re.search(r"FY\s*(\d{4})\s*[/\-]\s*(\d{2,4})", text_upper)
    if not fy_match:
        return None
    fy_start_year = int(fy_match.group(1))
    # FY 2025/2026 → start year 2025. Period start is always Jul 1 of
    # that year (Kenya FY runs Jul–Jun).
    fy_label = f"FY {fy_start_year}/{str(fy_start_year + 1)[-2:]}"

    sub_label = None
    end_month = 6  # default = annual end
    for descriptor, sub, end_m in _PERIOD_DESCRIPTORS:
        if descriptor in text_upper:
            sub_label = sub
            end_month = end_m
            break

    end_year = fy_start_year if end_month >= 7 else fy_start_year + 1
    # Use the actual last day of the month — March has 31 days, not
    # 30 (caught by Copilot review on PR #81). The ``calendar`` module
    # handles leap years correctly for the few cases where it might
    # matter.
    end_day = calendar.monthrange(end_year, end_month)[1]
    end_date = date(end_year, end_month, end_day)
    label = f"{fy_label} {sub_label}" if sub_label else fy_label
    return PeriodInfo(
        label=label,
        start_date=date(fy_start_year, 7, 1),
        end_date=end_date,
    )


def _row_matches_sector(row: List[Optional[str]]) -> Optional[str]:
    """Return the canonical sector name if row[0] matches one of
    COB's 10 sector codes; else None.

    Matching is case-insensitive on the FIRST whitespace-separated
    token plus the literal multi-word codes ("National Security").
    """
    if not row or not row[0]:
        return None
    cell = " ".join(row[0].split()).lower()
    if cell in _CODE_TO_NAME:
        return _CODE_TO_NAME[cell]
    # Multi-word codes — strict equality on the first N words.
    for code, canonical in _SECTORS:
        if " " in code and cell.startswith(code.lower()):
            return canonical
    # Single-word codes that might have trailing punctuation/text.
    first_token = cell.split()[0]
    if first_token in _SECTOR_CODES:
        return _CODE_TO_NAME[first_token]
    return None


def _sector_table_score(table: List[List[Optional[str]]]) -> int:
    """How many sector rows the table's first column contains.

    Used to pick the right sub-table when ``extract_tables()`` returns
    several from the same page (e.g. Table 2.6's page also has a
    truncated sub-total fragment that pdfplumber returns as its own
    "table").
    """
    if not table:
        return 0
    return sum(1 for row in table if _row_matches_sector(row) is not None)


def _extract_sector_rows(
    table: List[List[Optional[str]]],
) -> List[Tuple[str, Decimal, Decimal]]:
    """From a 7-column sector table, pull (sector_name, net_estimates,
    exchequer_issues) for the CURRENT period only — the "prior period"
    columns are reference data and not persisted.

    Skips rows where required cells fail to parse.
    """
    out: List[Tuple[str, Decimal, Decimal]] = []
    for row in table:
        sector = _row_matches_sector(row)
        if not sector:
            continue
        if len(row) < 3:
            continue
        net = _parse_kes_billion(row[1] or "")
        exch = _parse_kes_billion(row[2] or "")
        if net is None or exch is None:
            logger.debug(
                "Skipping sector row %s: unparseable values net=%r exch=%r",
                sector, row[1], row[2],
            )
            continue
        out.append((sector, net, exch))
    return out


@dataclass
class NgBirrPdfRecord:
    """One sector × {Recurrent, Development} record extracted from the
    NG-BIRR. Caller (``national_budget/parser.py``) translates this
    into the writer's ``NationalBudgetRecord``.
    """
    sector: str           # canonical long sector name
    subcategory: str      # "Recurrent" | "Development"
    net_estimates: Decimal
    exchequer_issues: Decimal


class NgBirrSectoralParser:
    """Extract per-sector {Net Estimates, Exchequer Issues} for both
    Recurrent and Development from a COB National Government BIRR.

    Usage::

        parser = NgBirrSectoralParser(Path("ng_birr_h1_2025_26.pdf"))
        period, records = parser.parse()
        # period: PeriodInfo
        # records: List[NgBirrPdfRecord] — 10 sectors × 2 subcategories
    """

    def __init__(self, pdf_path: Path) -> None:
        self.pdf_path = pdf_path

    def parse(self) -> Tuple[PeriodInfo, List[NgBirrPdfRecord]]:
        with pdfplumber.open(self.pdf_path) as pdf:
            period = _detect_period(pdf)
            if period is None:
                raise ValueError(
                    f"Could not detect fiscal period in {self.pdf_path.name}"
                )
            dev_table = self._find_best_sector_table(pdf, "development")
            rec_table = self._find_best_sector_table(pdf, "recurrent")

        if dev_table is None and rec_table is None:
            raise ValueError(
                f"No sectoral aggregate tables found in {self.pdf_path.name} "
                "(expected Table 2.5 development + Table 2.6 recurrent)"
            )

        records: List[NgBirrPdfRecord] = []
        for sector, net, exch in _extract_sector_rows(dev_table or []):
            records.append(
                NgBirrPdfRecord(
                    sector=sector,
                    subcategory="Development",
                    net_estimates=net,
                    exchequer_issues=exch,
                )
            )
        for sector, net, exch in _extract_sector_rows(rec_table or []):
            records.append(
                NgBirrPdfRecord(
                    sector=sector,
                    subcategory="Recurrent",
                    net_estimates=net,
                    exchequer_issues=exch,
                )
            )

        if not records:
            raise ValueError(
                f"Detected sector tables in {self.pdf_path.name} but parsed "
                "zero rows — check the column layout / cell values"
            )

        logger.info(
            "NG-BIRR parser extracted %d records (period %s) from %s",
            len(records), period.label, self.pdf_path.name,
        )
        return period, records

    def _find_best_sector_table(
        self, pdf: pdfplumber.PDF, kind: str,
    ) -> Optional[List[List[Optional[str]]]]:
        """Walk pages, find the table whose section title contains
        ``kind`` (e.g. "development" or "recurrent") and whose first
        column has the most sector rows.

        We anchor on the section title because pdfplumber returns
        multiple sub-tables on a typical page; the title disambiguates
        which is the dev vs. recurrent aggregate. Sector-row count is
        the secondary score so a degraded extraction doesn't pick a
        truncated sub-fragment.
        """
        title_re = re.compile(
            rf"Table\s+2\.\d+:\s*Sectoral\s+{kind}\s+Estimates",
            re.IGNORECASE,
        )
        best: Optional[List[List[Optional[str]]]] = None
        best_score = 0
        for page in pdf.pages[:80]:  # Section 2 is well within the front 80 pages
            text = page.extract_text() or ""
            if not title_re.search(text):
                continue
            for table in page.extract_tables() or []:
                score = _sector_table_score(table)
                if score > best_score:
                    best, best_score = table, score
            if best_score >= 8:
                # 8+ of 10 sectors found; further pages won't have a
                # better hit for this kind.
                break
        return best


__all__ = ["NgBirrSectoralParser", "NgBirrPdfRecord", "PeriodInfo"]
