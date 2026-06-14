"""Fetch Kenya domestic debt from the CBK Statistical Bulletin.

Why CBK Statistical Bulletin?
-----------------------------
World Bank IDS (see ``wb_ids.py``) covers external debt only —
domestic debt (T-bills, T-bonds held by Kenyan banks/funds) is not
in IDS. CBK publishes Table 4.1.4 ("Composition of Government Gross
Domestic Debt by Instrument") in its biannual Statistical Bulletin,
broken down by month and instrument type. This is the cleanest
machine-extractable source for the domestic side.

Caveats
-------
* Biannual cadence (June & December bulletins). Latest figures lag
  by ~3 months.
* Values are reported in KES millions; we scale to whole KES to
  match the fixture's per-loan units.
* pdfplumber's ``extract_tables()`` is broken on this layout — every
  data cell gets concatenated with newlines. We use
  ``extract_text()`` and parse line-by-line, which produces clean
  per-month rows.
* The bulletin URL pattern at CBK changes each release. When the
  configured URL 404s or the parser can't find Table 4.1.4 (CBK
  occasionally renumbers tables between issues), we degrade silently
  to fixture and log a warning.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pdfplumber

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient

logger = logging.getLogger("seeding.national_debt.cbk_bulletin")

# The page text begins:
#   "Table 4.1.4: Composition of Government Gross Domestic Debt"
# We anchor on the substring after the table number so a future
# renumbering (4.1.4 → 4.1.5) doesn't break detection.
_TABLE_TITLE_ANCHOR = "Composition of Government Gross Domestic Debt"

# Fiscal year section headers look like "2024/2025" on their own line.
_FY_HEADER_RE = re.compile(r"^(\d{4})/(\d{4})$")

# Month rows look like:
#   "January 723,139.8 3,304,897.0 0.0 75,150.5 6,301.6 631.5 4,110,120.5"
# 7 numeric columns (TBills / TBonds / GovStocks / Overdraft / Advances
# / Other / Total). Numbers carry comma separators and decimals.
_MONTH_NAMES: Tuple[str, ...] = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_NUM_RE = r"-?[\d,]+\.\d+|-?[\d,]+"
_MONTH_ROW_RE = re.compile(
    r"^(?P<month>" + "|".join(_MONTH_NAMES) + r")\s+"
    + r"\s+".join(f"(?P<c{i}>{_NUM_RE})" for i in range(7))
    + r"\s*$"
)

# Map (column index after the month, fixture lender, debt_category).
# Column 2 (Government Stocks) is always 0 in modern bulletins → omit.
# Column 6 (Total Domestic Debt) is a sum line, not its own loan → omit.
# Bills/Bonds/Overdraft match existing fixture lenders so the overlay
# REPLACES rather than appends. Advances + Other become NEW rows
# alongside the fixture set (the writer dedupes by entity+lender+date).
_COLUMN_MAPPINGS: Tuple[Tuple[int, str, str], ...] = (
    (0, "Domestic Treasury Bills (91-day, 182-day, 364-day)", "domestic_bills"),
    (1, "Domestic Treasury Bonds", "domestic_bonds"),
    (3, "CBK Overdraft Facility", "domestic_overdraft"),
    (4, "Advances from Commercial Banks", "domestic_overdraft"),
    (5, "Other Domestic Debt", "other"),
)

# CBK reports values in shillings million; scale to whole KES to
# match the fixture convention.
_KES_MILLIONS_SCALE = Decimal("1000000")


def fetch_domestic_debt_from_cbk_bulletin(
    client: SeedingHttpClient, settings: SeedingSettings
) -> List[Dict[str, Any]]:
    """Download the CBK Statistical Bulletin, locate Table 4.1.4, and
    return loan dicts in fixture format.

    Returns ``[]`` on any failure — fetch, missing table, or unparseable
    rows. Caller (``fetcher._overlay_loans``) treats an empty result as
    "no overlay applied" and the fixture stays.
    """
    url = settings.cbk_statistical_bulletin_url
    if not url:
        logger.info("CBK Statistical Bulletin URL not configured; skipping.")
        return []

    try:
        pdf_bytes = _download_pdf(client, url)
    except Exception as exc:
        logger.warning("CBK bulletin download failed (%s): %s", url, exc)
        return []

    try:
        page_text = _extract_domestic_debt_page_text(pdf_bytes)
    except Exception as exc:
        logger.warning("CBK bulletin PDF parse failed: %s", exc)
        return []
    if page_text is None:
        logger.info(
            "CBK bulletin had no Table 4.1.4 page; skipping."
        )
        return []

    latest = _parse_latest_month_row(page_text)
    if latest is None:
        logger.info(
            "CBK bulletin yielded no parseable month rows; skipping."
        )
        return []

    measurement_date, fiscal_year_start, values = latest
    loans = _build_loan_records(
        measurement_date=measurement_date,
        fiscal_year_start=fiscal_year_start,
        values=values,
        source_url=url,
    )
    logger.info(
        "CBK bulletin parsed %d domestic-debt rows (latest: %s)",
        len(loans), measurement_date.isoformat(),
    )
    return loans


def _download_pdf(client: SeedingHttpClient, url: str) -> bytes:
    """Fetch PDF bytes. ``file://`` URLs are read from disk so tests
    and offline runs don't need a live HTTP path."""
    if url.startswith("file://"):
        return Path(url[len("file://"):]).read_bytes()
    response = client.get(url, raise_for_status=True)
    return response.content


def _extract_domestic_debt_page_text(pdf_bytes: bytes) -> Optional[str]:
    """Walk pages, return the first one whose text contains the
    Table 4.1.4 anchor. Returns ``None`` if no page matches."""
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if _TABLE_TITLE_ANCHOR in text:
                return text
    return None


def _parse_latest_month_row(
    page_text: str,
) -> Optional[Tuple[date, int, List[Decimal]]]:
    """Walk lines, tracking the active fiscal-year section header and
    matching month rows. Return (measurement_date, fy_start, values)
    for the LAST matching row, or ``None`` if nothing matched.

    Kenya FY runs Jul–Jun. Within FY YYYY/(YYYY+1):
    Jul–Dec rows fall in calendar year YYYY; Jan–Jun rows fall in
    calendar year YYYY+1.
    """
    fy_start: Optional[int] = None
    last: Optional[Tuple[date, int, List[Decimal]]] = None
    for raw in page_text.splitlines():
        line = raw.strip()
        m_fy = _FY_HEADER_RE.match(line)
        if m_fy:
            fy_start = int(m_fy.group(1))
            continue
        m_row = _MONTH_ROW_RE.match(line)
        if m_row and fy_start is not None:
            month_name = m_row.group("month")
            month_idx = _MONTH_NAMES.index(month_name) + 1
            cal_year = fy_start if month_idx >= 7 else fy_start + 1
            values = [
                Decimal(m_row.group(f"c{i}").replace(",", ""))
                for i in range(7)
            ]
            last = (date(cal_year, month_idx, 1), fy_start, values)
    return last


def _build_loan_records(
    *,
    measurement_date: date,
    fiscal_year_start: int,
    values: List[Decimal],
    source_url: str,
) -> List[Dict[str, Any]]:
    """Map the 7-column row to a list of loan dicts in fixture shape.

    Uses ``issue_date = f"{fy_start}-07-01"`` so repeated bulletin
    pulls within a fiscal year UPDATE the same row (writer dedupes by
    entity+lender+issue_date), while a new fiscal year produces a new
    row — same convention as ``wb_ids.py``. The actual measurement
    month lives in ``notes`` for human traceability.
    """
    issue_date_iso = f"{fiscal_year_start}-07-01"
    loans: List[Dict[str, Any]] = []
    for col_idx, lender, category in _COLUMN_MAPPINGS:
        kes_value = values[col_idx] * _KES_MILLIONS_SCALE
        if kes_value <= 0:
            continue
        loans.append(
            {
                "entity_name": "National Government",
                "entity_type": "national",
                "lender": lender,
                "debt_category": category,
                "principal": _format_decimal(kes_value),
                "outstanding": _format_decimal(kes_value),
                "interest_rate": None,
                "issue_date": issue_date_iso,
                "maturity_date": None,
                "currency": "KES",
                "notes": (
                    f"CBK Statistical Bulletin Table 4.1.4 "
                    f"(month-end {measurement_date.isoformat()}); "
                    f"KES millions scaled to whole KES."
                ),
            }
        )
    return loans


def _format_decimal(value: Decimal) -> str:
    """Render KES amounts as integer-string to match the fixture's
    ``"820000000000.00"`` shape."""
    return f"{value.quantize(Decimal('1'))}.00"


__all__ = ["fetch_domestic_debt_from_cbk_bulletin"]
