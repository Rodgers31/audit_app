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
from decimal import Decimal, InvalidOperation
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


def _discover_bulletin_url(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Optional[str]:
    """Locate the current Statistical Bulletin PDF on CBK's listing page.

    The listing interleaves editions back to 2003 and is not sorted, so the
    newest is chosen by the date parsed from each filename, not page order.
    A ``not_before`` floor means a listing that has lost its recent entries
    fails loudly instead of silently seeding a decade-old bulletin.
    """
    from datetime import date, timedelta

    from ...discovery import discover_latest_pdf

    page_url = settings.cbk_statistical_bulletin_page_url
    try:
        response = client.get(page_url, raise_for_status=True)
    except Exception as exc:
        logger.warning("CBK bulletin listing unreachable (%s): %s", page_url, exc)
        return None

    # CBK publishes twice a year; anything older than ~2 years means the
    # listing changed shape and we should not trust what we picked.
    floor = date.today() - timedelta(days=730)
    found = discover_latest_pdf(
        response.text,
        page_url,
        must_match=("/uploads/statistical_bulletin/",),
        not_before=floor,
    )
    if found is None:
        return None
    logger.info("Discovered CBK Statistical Bulletin: %s", found)
    return found.url


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
        # Discover the current edition rather than skipping. The direct path
        # embeds a per-release upload hash, so it can never be hardcoded
        # durably — which is why this overlay had never run in production.
        url = _discover_bulletin_url(client, settings)
    if not url:
        logger.warning(
            "No CBK Statistical Bulletin could be resolved (neither "
            "SEED_CBK_STATISTICAL_BULLETIN_URL nor discovery from %s); "
            "domestic debt stays on fixture values.",
            settings.cbk_statistical_bulletin_page_url,
        )
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


# ── Table 4.1.3: Deficit Financing and Public Debt ────────────────────
# The authoritative live source for the debt_timeline series (external /
# domestic / total). Previously those three columns came from a fixture
# whose 2025 total (12.5T) overstated the published figure (12.30T).
#
# Row shape, values in SHILLINGS MILLION:
#   <Month> <fin1> <fin2> <fin3> <fin4> <domestic> <external> <total>
# grouped under a fiscal-year header line ("2025/2026"). Kenya's FY runs
# July->June, so July-December belong to the FIRST calendar year of the
# label and January-June to the second.
_TABLE_413_ANCHOR = "4.1.3"
_FY413_HEADER_RE = re.compile(r"^(20\d{2})\s*/\s*(20\d{2})")
_MONTH413_ROW_RE = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(.+)$",
    re.IGNORECASE,
)
_MONTH_NUMBER = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}
# Shillings million -> raw KES. The debt_timeline table stores raw KES
# (stage1 3a); passing millions through would understate by 1e6.
_MILLION = Decimal("1000000")


def _find_public_debt_page_text(pdf_bytes: bytes) -> Optional[str]:
    """First page that actually YIELDS Table 4.1.3 rows.

    Keyword matching alone selected the table of CONTENTS, which lists
    "4.1.3 ... Deficit Financing and Public Debt" and contains every anchor
    word while holding no data. The page is therefore validated by parsing
    it: a page counts only if it produces at least one row that satisfies
    the domestic+external==total identity. That is self-checking and
    survives pagination changes between editions.
    """
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "4.1.3" not in text:
                continue
            if parse_public_debt_table(text):
                return text
    return None


def parse_public_debt_table(page_text: str) -> Dict[int, Dict[str, Decimal]]:
    """``{calendar_year: {external, domestic, total}}`` in raw KES.

    For each calendar year the LATEST available month is kept, so a year
    is represented by its most recent published stock rather than an
    arbitrary row. Rows failing the ``domestic + external == total``
    identity (±0.5%) are DROPPED: that identity is independent of our own
    arithmetic, so a mismatch means the row was mis-parsed and must not
    become a published figure.
    """
    out: Dict[int, Dict[str, Decimal]] = {}
    best_month: Dict[int, int] = {}
    fy_start: Optional[int] = None

    for raw_line in (page_text or "").split("\n"):
        line = raw_line.strip()
        fy = _FY413_HEADER_RE.match(line)
        if fy:
            fy_start = int(fy.group(1))
            continue
        m = _MONTH413_ROW_RE.match(line)
        if not m or fy_start is None:
            continue
        month_name = m.group(1).lower()
        numbers = re.findall(r"-?[\d,]+\.?\d*", m.group(2))
        if len(numbers) < 3:
            continue
        try:
            domestic, external, total = (
                Decimal(n.replace(",", "")) for n in numbers[-3:]
            )
        except (InvalidOperation, ValueError):
            continue
        if total <= 0:
            continue
        # Independent cross-check (see docstring).
        if abs((domestic + external) - total) > (total * Decimal("0.005")):
            logger.warning(
                "CBK 4.1.3 row '%s' fails domestic+external==total "
                "(%s + %s != %s); dropping rather than publishing it",
                month_name,
                domestic,
                external,
                total,
            )
            continue

        month = _MONTH_NUMBER[month_name]
        # FY label "2025/2026": Jul-Dec -> 2025, Jan-Jun -> 2026.
        year = fy_start if month >= 7 else fy_start + 1
        if year in best_month and best_month[year] >= month:
            continue
        best_month[year] = month
        out[year] = {
            "external": external * _MILLION,
            "domestic": domestic * _MILLION,
            "total": total * _MILLION,
            "as_of_month": Decimal(month),
        }
    return out


def fetch_public_debt_timeline_from_cbk_bulletin(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Dict[int, Dict[str, Decimal]]:
    """Live external/domestic/total public debt by calendar year, raw KES.

    Returns ``{}`` on any failure so the caller keeps fixture values.
    """
    url = settings.cbk_statistical_bulletin_url or _discover_bulletin_url(
        client, settings
    )
    if not url:
        logger.warning(
            "No CBK Statistical Bulletin resolved; debt timeline stays on "
            "fixture values."
        )
        return {}
    try:
        pdf_bytes = _download_pdf(client, url)
        page_text = _find_public_debt_page_text(pdf_bytes)
    except Exception as exc:
        logger.warning("CBK bulletin fetch/parse failed for 4.1.3: %s", exc)
        return {}
    if page_text is None:
        logger.warning("CBK bulletin had no Table 4.1.3 page.")
        return {}

    parsed = parse_public_debt_table(page_text)
    if parsed:
        newest = max(parsed)
        logger.info(
            "CBK 4.1.3 parsed %d year(s); newest %d total=KES %.2fT",
            len(parsed),
            newest,
            float(parsed[newest]["total"]) / 1e12,
        )
    return parsed
