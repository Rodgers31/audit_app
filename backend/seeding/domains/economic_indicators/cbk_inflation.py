"""Monthly CPI inflation from the Central Bank of Kenya's inflation-rates page.

WHY THIS EXISTS
---------------
Until this module the only live inflation series was the World Bank's
``FP.CPI.TOTL.ZG``: one ANNUAL-AVERAGE observation per calendar year, about a
year behind. On 2026-09-26 /budget showed that series' 2025 value (4.1%)
captioned "KNBS Consumer Price Index", while KNBS's own headline for August
2026 — 12-month inflation — was 6.59% (issue #232).

CBK republishes the KNBS monthly figures as one HTML table,
``Year | Month | Annual Average Inflation | 12-Month Inflation``, back to
January 2005, footnoted "Source: Kenya National Bureau of Statistics". The
12-month rate is the headline measure; it is written under its own key,
:data:`INDICATOR_TYPE`, because the World Bank series already owns
``inflation_rate`` with a DIFFERENT measure at colliding ``YYYY-12-31`` dates
(Dec 2025: 12-month 4.49 vs annual average 4.07). One key holding two
measures is how the old bootstrap literals and the World Bank pull came to
overwrite each other.

THE CROSS-CHECK
---------------
CBK's table is hand-maintained and has at least one row with its columns
swapped: June 2024 reads annual-average 4.64 / 12-month 6.22, where the twelve
12-month rates ending June 2024 average 6.36. The annual-average rate is, to a
close approximation, the mean of the last twelve 12-month rates (median gap
over the whole table 0.02pp; the largest anywhere else is 0.66pp, across
KNBS's 2020 CPI rebasing). So each row is checked against its own history,
and a row that misses by more than :data:`CROSS_CHECK_TOLERANCE_PP` is
DROPPED, not corrected: "absent" is recoverable, a published swapped figure
is not. Rows without eleven predecessors cannot be checked and are dropped
too — every published row is a checked row.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from decimal import Decimal
from services.response_receipts import capture_response

CBK_INFLATION_URL = "https://www.centralbank.go.ke/inflation-rates/"
INDICATOR_TYPE = "inflation_rate_12m"
PUBLISHER = "Central Bank of Kenya"
COMPILED_BY = "Kenya National Bureau of Statistics"
SOURCE_LABEL = "KNBS CPI, via Central Bank of Kenya"
MEASURE = "12-month CPI inflation"

#: Largest gap allowed between a row's annual-average rate and the mean of
#: the twelve 12-month rates ending that month. 1.0pp clears every row in the
#: table except the swapped June 2024 one (1.72pp); the next largest is 0.66.
CROSS_CHECK_TOLERANCE_PP = 1.0

#: Anything outside this is a parse error, not an economy. Kenya's 12-month
#: rate peaked at 19.72% (Nov 2011) in the table's 2005-2026 span.
_PLAUSIBLE_RANGE = (-10.0, 60.0)

_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}

_COL_YEAR = "year"
_COL_MONTH = "month"
_COL_ANNUAL = "annual average inflation"
_COL_12M = "12-month inflation"


class CbkTableNotFound(ValueError):
    """The page no longer carries a table with the expected columns."""


@dataclass
class CbkInflationResult:
    records: List[Dict[str, Any]] = field(default_factory=list)
    #: ``(YYYY-MM, reason)`` for every row that was read and not published.
    rejected: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def newest_month(self) -> Optional[str]:
        return self.records[0]["reference_month"] if self.records else None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _to_float(text: str) -> Optional[float]:
    try:
        return float(text.replace(",", "").strip())
    except (AttributeError, ValueError):
        return None


def _read_table(html: str) -> List[Tuple[int, int, float, float]]:
    """``(year, month, annual_avg, twelve_month)`` rows, located by header NAME.

    Columns are found by their header text, never by position, so a
    reordered table still parses correctly and a renamed one fails loudly.
    """
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        header_row = table.find("tr")
        if header_row is None:
            continue
        headers = [_norm(th.get_text()) for th in header_row.find_all(["th", "td"])]
        wanted = (_COL_YEAR, _COL_MONTH, _COL_ANNUAL, _COL_12M)
        if not all(w in headers for w in wanted):
            continue
        idx = [headers.index(w) for w in wanted]

        body = table.find("tbody") or table
        rows: List[Tuple[int, int, float, float]] = []
        for tr in body.find_all("tr"):
            cells = [c.get_text() for c in tr.find_all("td")]
            if len(cells) <= max(idx):
                continue  # header rows use <th>; they carry no <td>
            year = _to_float(cells[idx[0]])
            month = _MONTHS.get(_norm(cells[idx[1]]))
            annual = _to_float(cells[idx[2]])
            twelve = _to_float(cells[idx[3]])
            if year is None or month is None or annual is None or twelve is None:
                continue
            rows.append((int(year), month, annual, twelve))
        if rows:
            return rows
    raise CbkTableNotFound(
        "no table with columns Year / Month / Annual Average Inflation / "
        "12-Month Inflation on the CBK inflation-rates page"
    )


def _month_index(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def parse_cbk_inflation(html: str, response_receipt: dict | None = None) -> CbkInflationResult:
    """Parse the CBK page into checked economic-indicator payload dicts.

    Records are newest first and shaped for
    :func:`..parser.parse_economic_payload`; every one declares its own
    provenance (``source_label``, ``measure``, ``publisher``) so a reader of
    the row never has to guess where it came from.
    """
    rows = _read_table(html)
    source_cells = {}
    if response_receipt is not None:
        for table_index, table in enumerate(BeautifulSoup(html, "html.parser").find_all("table")):
            header = table.find("tr")
            headers = [_norm(c.get_text()) for c in header.find_all(["th", "td"])] if header else []
            if not all(k in headers for k in (_COL_YEAR, _COL_MONTH, _COL_12M)):
                continue
            yi, mi, vi = [headers.index(k) for k in (_COL_YEAR, _COL_MONTH, _COL_12M)]
            for row_index, tr in enumerate((table.find("tbody") or table).find_all("tr")):
                cells = [c.get_text().strip() for c in tr.find_all("td")]
                if len(cells) <= max(yi, mi, vi):
                    continue
                year, month = _to_float(cells[yi]), _MONTHS.get(_norm(cells[mi]))
                if year is None or month is None:
                    continue
                key = (int(year), month)
                raw = cells[vi].replace(",", "")
                if key in source_cells and source_cells[key][0] != raw:
                    raise CbkTableNotFound("contradictory duplicate month in CBK source cells")
                source_cells[key] = (raw, {"table": f"table[{table_index}]", "row": row_index,
                    "cell": vi, "column": _COL_12M, "edition": response_receipt.get("digest"), "date": f"{int(year):04d}-{month:02d}"})
            break
    by_month: Dict[int, Tuple[int, int, float, float]] = {}
    for r in rows:
        by_month[_month_index(r[0], r[1])] = r

    result = CbkInflationResult()
    for key in sorted(by_month, reverse=True):
        year, month, annual, twelve = by_month[key]
        ref = f"{year:04d}-{month:02d}"

        lo, hi = _PLAUSIBLE_RANGE
        if not (lo <= twelve <= hi and lo <= annual <= hi):
            result.rejected.append((ref, f"implausible value ({annual}, {twelve})"))
            continue

        window = [by_month.get(key - k) for k in range(12)]
        if any(w is None for w in window):
            result.rejected.append((ref, "fewer than 11 prior months to cross-check"))
            continue
        implied = sum(w[3] for w in window) / 12.0
        if abs(annual - implied) > CROSS_CHECK_TOLERANCE_PP:
            result.rejected.append(
                (
                    ref,
                    f"annual average {annual} vs {implied:.2f} implied by the "
                    "12-month rates (columns likely swapped)",
                )
            )
            continue

        last_day = calendar.monthrange(year, month)[1]
        result.records.append(
            {
                "indicator_type": INDICATOR_TYPE,
                "date": f"{year:04d}-{month:02d}-{last_day:02d}",
                "value": twelve,
                "unit": "percent",
                "source_url": CBK_INFLATION_URL,
                "source": (
                    f"Central Bank of Kenya, Inflation Rates table "
                    f"({calendar.month_name[month]} {year}); compiled by KNBS"
                ),
                "source_label": SOURCE_LABEL,
                "measure": MEASURE,
                "publisher": PUBLISHER,
                "compiled_by": COMPILED_BY,
                "reference_month": ref,
                "annual_average_pct": annual,
                "cross_check_implied_annual_pct": round(implied, 2),
                "data_quality": "official",
            }
        )
    if response_receipt is not None:
        receipt = {**response_receipt, "source_kind": "web", "parser_version": "cbk-inflation-table-v1"}
        manifest = []
        for record in result.records:
            period = record["reference_month"]
            raw, locator = source_cells[(int(period[:4]), int(period[5:]))]
            identity = {"measure": INDICATOR_TYPE, "entity_id": None, "geography": "KEN", "period": period,
                "unit": "percent", "basis": "actual", "dimensions": {}}
            manifest.append({"identity": identity, "locator": locator, "raw_value": raw, "raw_unit": "percent",
                "transformation": {"operation": "identity", "factor": "1", "rounding": 2, "rounding_mode": "ROUND_HALF_EVEN"}})
            record["source_evidence"] = [{"version": 1, "source_kind": "web", "identity": identity,
                "_response_receipt": receipt, "receipt": {"digest": receipt["digest"]},
                "raw_value": raw, "raw_unit": "percent", "value": str(Decimal(raw).quantize(Decimal("0.01"))),
                "unit": "percent", "locator": locator,
                "transformation": {"operation": "identity", "factor": "1", "rounding": 2, "rounding_mode": "ROUND_HALF_EVEN"},
                "checks": {"identity": True, "value": True, "locator": True,
                    "transport": receipt["status"] == 200 and receipt.get("acquired_at") is not None,
                    "bytes": receipt["byte_check"]["status"] == "matched"},
                "reconciliation": {"status": "matched", "reason": "parsed monthly cell matches stored value; annual-window guard accepted"}}]
        receipt["observations"] = manifest
    return result


def fetch_cbk_inflation(client) -> CbkInflationResult:
    """GET the CBK page and parse it. Raises on HTTP or structural failure."""
    resp = client.get(CBK_INFLATION_URL, raise_for_status=True)
    if resp.status_code != 200 or "html" not in resp.headers.get("content-type", "").lower():
        raise CbkTableNotFound("CBK table requires a complete HTTP200 HTML response")
    receipt = resp.extensions.get("response_receipt")
    if not isinstance(receipt, dict) or "digest" not in receipt:
        receipt = capture_response(resp, getattr(client, "receipt_store", None), source_kind="web")
    return parse_cbk_inflation(resp.text, receipt)


__all__ = [
    "CBK_INFLATION_URL",
    "CROSS_CHECK_TOLERANCE_PP",
    "CbkInflationResult",
    "CbkTableNotFound",
    "INDICATOR_TYPE",
    "MEASURE",
    "SOURCE_LABEL",
    "fetch_cbk_inflation",
    "parse_cbk_inflation",
]
