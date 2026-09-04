"""Instrument-level Kenya debt data from CBK's own HTML data tables.

Why this module exists
----------------------
``fetcher.py`` records that the CBK PDF path was retired because "the published
format is now aggregated by instrument type, not by lender — so even a
successful discovery wouldn't have given us the per-loan rows the original
parser expected" (PR #75). That conclusion was right about the PDF and wrong
about CBK: the per-instrument data IS published, as WordPress data tables on
centralbank.go.ke rather than inside the Statistical Bulletin.

Two tables matter, and both were read off the live pages before a line of this
parser was written (house rule: confirm anchors against the real document):

1. ``/bills-bonds/treasury-bonds/`` — 333 rows, one per Treasury bond TRANCHE:
       Issue Date | Issue No | ISIN Number | Tenor | Face Value (Kshs Millions)
       | Maturity Date | Coupon Rate | Redemption Yield
   e.g. ``26/04/2010 | FXD1/2010/10 | KE1000001921 | 10 | 12052.6 |
        13/04/2020 | 8.79 | 8.633``

   This is the register the withdrawn maturity ladder needed. The site had 3
   instruments carrying a maturity date, five Eurobond issues collapsed onto a
   single 2034 date, and a flat 14.5% assumed coupon on the whole bond book
   (credibility audit F24/F42). This table carries real maturities from 2026 to
   2047 and a real coupon per security.

2. ``/public-debt/`` — 262 rows of MONTHLY domestic / external / total public
   debt, December 1999 through December 2021.

   This one matters more than it looks. The debt timeline's 2013–2021 rows are
   round hundreds of billions that no CBK table produces (F13), and CBK's own
   December figures show they are not merely imprecise — 2013 is published at
   KSh 2,111.6bn against the fixture's 3,100bn, **46.8% too high**, with the
   error shrinking steadily toward the present. That is the signature of a
   series extrapolated backwards from a recent number, and it made the
   headline "4.0x since 2013" out of a base that was never real.

Known limits, stated because they bound what may be published
--------------------------------------------------------------
* The bond register covers bonds SOLD AT AUCTION from 2007. Summing the
  tranches of every ISIN not yet matured gives ~KSh 4.12T against CBK's
  published Treasury-bond stock of 5.579T — about 74%. The remainder is
  pre-2007 paper, non-auction issuance and amortisation this table cannot show.
  So the register is authoritative on DATES and COUPONS and is NOT a stock
  measure: ``bond_register_coverage_ratio`` is returned with it, and callers
  must not sum it into a debt total. See ``BOND_COVERAGE_BAND``.
* The monthly tables stop in 2021/2022 — CBK has not refreshed them. They are
  the right source for history and the wrong one for the current year, which
  is why the Statistical Bulletin path in ``cbk_bulletin.py`` stays.
* ``serverSide`` is false on both tables, so every row is present in the HTML.
  ``_assert_table_complete`` re-checks that per fetch: if CBK ever switches the
  tables to server-side paging we would silently start parsing page one only,
  and a partial register is worse than none.
"""

from __future__ import annotations

import html as _html
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient

logger = logging.getLogger("seeding.national_debt.cbk_web_tables")

BONDS_URL = "https://www.centralbank.go.ke/bills-bonds/treasury-bonds/"
PUBLIC_DEBT_URL = "https://www.centralbank.go.ke/public-debt/"

# Column headers, verbatim from the live pages on 2026-09-03. Matching on the
# header text rather than a table id means a CBK re-render that renumbers
# `table_3` does not silently hand us a different table — which is exactly how
# three earlier parser bugs in this repo happened.
BOND_HEADERS = (
    "Issue Date",
    "Issue No",
    "ISIN Number",
    "Tenor",
    "Face Value",
    "Maturity Date",
    "Coupon Rate",
)
PUBLIC_DEBT_HEADERS = ("Year", "Month", "Domestic Debt", "External Debt", "Total")

# Acceptable coverage of CBK's published Treasury-bond stock. Below the floor
# the register is too partial to describe the maturity profile of the book;
# above the ceiling it is double-counting reopenings. Either way: quarantine,
# do not publish. Measured at 0.74 on 2026-09-03.
BOND_COVERAGE_BAND = (0.55, 1.05)

# CBK reports these tables in KSh millions.
_MILLIONS = 1_000_000

_MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}


class CbkTableError(RuntimeError):
    """The page did not contain the table we expect, in the shape we expect."""


# ---------------------------------------------------------------------------
# HTML table extraction
# ---------------------------------------------------------------------------

def _strip_tags(fragment: str) -> str:
    return _html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _assert_table_complete(page_html: str, url: str) -> None:
    """Refuse to parse a table CBK has switched to server-side paging.

    Both tables render every row into the HTML today (``"serverSide":false``).
    If that changes, `_iter_tables` would return only the first page and we
    would publish a register missing most of its instruments — silently, and
    looking exactly like a smaller bond book. Fail instead.
    """
    if re.search(r'"serverSide"\s*:\s*true', page_html):
        raise CbkTableError(
            f"{url} now uses server-side paging; the HTML holds only one page "
            "of rows. Parsing it would publish a partial register that looks "
            "like a complete one."
        )


def _iter_tables(page_html: str):
    for m in re.finditer(r"<table[^>]*>(.*?)</table>", page_html, re.S | re.I):
        yield m.group(1)


def _headers_of(table_html: str) -> List[str]:
    seen: List[str] = []
    for cell in re.findall(r"<th[^>]*>(.*?)</th>", table_html, re.S):
        text = _strip_tags(cell)
        if text and text not in seen:
            seen.append(text)
    return seen


def _rows_of(table_html: str) -> List[List[str]]:
    rows = []
    for row_html in re.findall(r'<tr[^>]*id="[^"]*"[^>]*>(.*?)</tr>', table_html, re.S):
        cells = [_strip_tags(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.S)]
        if cells:
            rows.append(cells)
    return rows


def _find_table(page_html: str, wanted: Tuple[str, ...], url: str) -> List[List[str]]:
    """The first table whose headers start with every string in ``wanted``."""
    candidates = []
    for table_html in _iter_tables(page_html):
        headers = _headers_of(table_html)
        candidates.append(headers)
        joined = " | ".join(headers)
        if all(w.lower() in joined.lower() for w in wanted):
            rows = _rows_of(table_html)
            if rows:
                return rows
    raise CbkTableError(
        f"No table on {url} carries the headers {wanted!r}. "
        f"Found instead: {candidates!r}"
    )


def _num(text: str) -> Optional[float]:
    text = (text or "").replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _dmy(text: str) -> Optional[date]:
    text = (text or "").strip()
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# 1. Treasury bond instrument register
# ---------------------------------------------------------------------------

@dataclass
class BondTranche:
    """One row of the CBK table: a sale (or reopening) of one security."""

    issue_date: date
    issue_no: str
    isin: str
    tenor_years: Optional[float]
    face_value_kes: float
    maturity_date: date
    coupon_rate: Optional[float]


@dataclass
class BondSecurity:
    """One ISIN: every tranche of it summed.

    Reopenings share an ISIN — ``FXD1/2010/10`` and ``FXD1/2010/10(R1)`` are
    both KE1000001921, same maturity, same coupon. Summing by ISIN is what
    turns a list of auctions into a register of securities.
    """

    isin: str
    issue_no: str
    maturity_date: date
    coupon_rate: Optional[float]
    tenor_years: Optional[float]
    face_value_kes: float
    tranches: int
    first_issued: date

    @property
    def instrument_type(self) -> str:
        code = self.issue_no.upper()
        if code.startswith("IFB"):
            return "infrastructure_bond"
        if code.startswith("SDB"):
            return "savings_development_bond"
        if code.startswith("FXD"):
            return "fixed_coupon_bond"
        return "other_bond"


def parse_bond_register(page_html: str, url: str = BONDS_URL) -> List[BondTranche]:
    """Every parseable tranche row. Rows missing a date are dropped, loudly."""
    _assert_table_complete(page_html, url)
    rows = _find_table(page_html, BOND_HEADERS, url)

    tranches: List[BondTranche] = []
    dropped = 0
    for cells in rows:
        if len(cells) < 7:
            dropped += 1
            continue
        issue_date, maturity = _dmy(cells[0]), _dmy(cells[5])
        face = _num(cells[4])
        if issue_date is None or maturity is None or face is None:
            # CBK leaves the issue date blank on a handful of rows. Without a
            # date the tranche cannot be placed on a ladder, and without a face
            # value it cannot be summed — so it is dropped rather than guessed.
            dropped += 1
            continue
        tranches.append(
            BondTranche(
                issue_date=issue_date,
                issue_no=cells[1].strip(),
                isin=cells[2].strip(),
                tenor_years=_num(cells[3]),
                face_value_kes=face * _MILLIONS,
                maturity_date=maturity,
                coupon_rate=_num(cells[6]),
            )
        )
    if dropped:
        logger.warning(
            "CBK bond table: dropped %d of %d rows for a missing issue date, "
            "maturity or face value", dropped, len(rows),
        )
    if not tranches:
        raise CbkTableError(f"{url}: table found but no row parsed")
    return tranches


def outstanding_securities(
    tranches: List[BondTranche], as_of: Optional[date] = None
) -> List[BondSecurity]:
    """Collapse tranches into securities, keeping only those not yet matured.

    Keyed on (ISIN, maturity date), NOT on ISIN alone. Reading the real table
    showed three reasons an ISIN carries more than one maturity, and grouping
    on ISIN handled none of them correctly:

    * **Amortising infrastructure bonds.** IFB1/2023/017 (KE8000005549) lists
      the same issue date and the same face value against both 2033-02-28 and
      2040-02-20 — CBK records the tranche against each redemption date. On an
      ISIN key the whole amount landed on one date, which is where 2027 jumped
      from 260Bn to 575Bn in testing.
    * **A reused ISIN.** KE4000003808 covers FXD2/2013/015 (matures 2028,
      coupon 12.0) *and* FXD2/2018/015 (2033, coupon 12.75) — two different
      securities under one identifier.
    * **What look like CBK typos**: one row of eleven carrying 2027-07-28 where
      the other ten say 2028-07-10, on a bond whose tenor is 5 years.

    Keying on (ISIN, maturity) is what the table actually asserts: this much
    face value redeems on this date. Reopenings of the same maturity still sum.
    Telling the three cases apart is left to ``partition_ambiguous``.
    """
    as_of = as_of or date.today()
    by_key: Dict[Tuple[str, date], Dict[str, Any]] = {}
    for t in tranches:
        if t.maturity_date <= as_of:
            continue
        key = (t.isin, t.maturity_date)
        agg = by_key.setdefault(
            key,
            {
                "issue_no": t.issue_no,
                "maturity_date": t.maturity_date,
                "coupon_rate": t.coupon_rate,
                "tenor_years": t.tenor_years,
                "face_value_kes": 0.0,
                "tranches": 0,
                "first_issued": t.issue_date,
            },
        )
        agg["face_value_kes"] += t.face_value_kes
        agg["tranches"] += 1
        agg["first_issued"] = min(agg["first_issued"], t.issue_date)
        if agg["coupon_rate"] is None:
            agg["coupon_rate"] = t.coupon_rate
    return sorted(
        (BondSecurity(isin=k[0], **v) for k, v in by_key.items()),
        key=lambda s: s.maturity_date,
    )


# Why an ISIN was held back, in the language of what we found in the table.
AMBIGUITY_REUSED_ISIN = "isin_covers_two_securities"
AMBIGUITY_AMORTISING = "amortising_schedule_not_resolvable"
AMBIGUITY_ODD_MATURITY = "conflicting_maturity_dates"


def partition_ambiguous(
    securities: List[BondSecurity],
) -> Tuple[List[BondSecurity], Dict[str, Dict[str, Any]]]:
    """Split the register into what may be published and what may not.

    An ISIN appearing under more than one maturity cannot be placed on a
    maturity ladder without a decision this table does not support. For an
    amortising bond, CBK lists the same tranche against each redemption date —
    so summing the rows double-counts it, and picking one date moves the money
    to a year it does not fall due in. Neither is a figure we can stand behind.

    Six of 62 outstanding ISINs are affected, holding about 15% of the
    register's face value. They are withheld from published amounts and
    returned with their reason, so the omission is visible rather than
    inferred from a total that looks slightly small.
    """
    by_isin: Dict[str, List[BondSecurity]] = {}
    for s in securities:
        by_isin.setdefault(s.isin, []).append(s)

    publishable: List[BondSecurity] = []
    withheld: Dict[str, Dict[str, Any]] = {}
    for isin, group in by_isin.items():
        if len(group) == 1:
            publishable.extend(group)
            continue
        coupons = {s.coupon_rate for s in group}
        base_issues = {
            re.sub(r"\(R\d+\)", "", s.issue_no).strip().upper() for s in group
        }
        if len(coupons) > 1 or len(base_issues) > 1:
            reason = AMBIGUITY_REUSED_ISIN
        elif any(s.tranches > 1 for s in group):
            reason = AMBIGUITY_AMORTISING
        else:
            reason = AMBIGUITY_ODD_MATURITY
        withheld[isin] = {
            "reason": reason,
            "issue_no": sorted(base_issues)[0],
            "maturities": [s.maturity_date.isoformat() for s in group],
            "face_value_kes": sum(s.face_value_kes for s in group),
        }
    publishable.sort(key=lambda s: s.maturity_date)
    return publishable, withheld


def check_bond_coverage(
    securities: List[BondSecurity], published_bond_stock_kes: Optional[float]
) -> Dict[str, Any]:
    """Compare the register against CBK's own published Treasury-bond stock.

    This is the gate that stops the register being mistaken for a stock
    measure. It returns the ratio and a verdict; it never adjusts a figure to
    make the two agree.
    """
    total = sum(s.face_value_kes for s in securities)
    if not published_bond_stock_kes:
        return {
            "register_total_kes": total,
            "published_stock_kes": None,
            "coverage_ratio": None,
            "status": "unchecked",
            "reason": "no published Treasury-bond stock to compare against",
        }
    ratio = total / published_bond_stock_kes
    low, high = BOND_COVERAGE_BAND
    ok = low <= ratio <= high
    return {
        "register_total_kes": total,
        "published_stock_kes": published_bond_stock_kes,
        "coverage_ratio": round(ratio, 4),
        "status": "within_band" if ok else "out_of_band",
        "band": [low, high],
        "reason": (
            None
            if ok
            else (
                f"register covers {ratio:.0%} of the published bond stock, "
                f"outside the {low:.0%}-{high:.0%} band: too partial to "
                "describe the maturity profile, or double-counting reopenings"
            )
        ),
    }


# ---------------------------------------------------------------------------
# 2. Monthly public debt series
# ---------------------------------------------------------------------------

@dataclass
class PublicDebtMonth:
    year: int
    month: int
    domestic_kes: float
    external_kes: float
    total_kes: float

    def identity_holds(self, tolerance: float = 0.005) -> bool:
        """CBK's own identity: domestic + external == total."""
        if not self.total_kes:
            return False
        return abs((self.domestic_kes + self.external_kes) - self.total_kes) <= (
            self.total_kes * tolerance
        )


def parse_public_debt_monthly(
    page_html: str, url: str = PUBLIC_DEBT_URL
) -> List[PublicDebtMonth]:
    """Monthly domestic/external/total, newest first on the page.

    Every row must satisfy CBK's own ``domestic + external = total``. A row
    that fails is dropped rather than published — the same rule
    ``parse_public_debt_table`` already applies to the PDF path, and the reason
    the 2026-08-29 correction could trust its own output.
    """
    _assert_table_complete(page_html, url)
    rows = _find_table(page_html, PUBLIC_DEBT_HEADERS, url)

    out: List[PublicDebtMonth] = []
    dropped_identity = 0
    for cells in rows:
        if len(cells) < 5:
            continue
        month = _MONTHS.get(cells[1].strip().lower())
        dom, ext, tot = (_num(cells[2]), _num(cells[3]), _num(cells[4]))
        if not cells[0].strip().isdigit() or month is None:
            continue
        if dom is None or ext is None or tot is None:
            continue
        rec = PublicDebtMonth(
            year=int(cells[0]),
            month=month,
            domestic_kes=dom * _MILLIONS,
            external_kes=ext * _MILLIONS,
            total_kes=tot * _MILLIONS,
        )
        if not rec.identity_holds():
            dropped_identity += 1
            continue
        out.append(rec)
    if dropped_identity:
        logger.warning(
            "CBK public-debt table: dropped %d row(s) failing "
            "domestic + external = total", dropped_identity,
        )
    if not out:
        raise CbkTableError(f"{url}: table found but no row survived parsing")
    return sorted(out, key=lambda r: (r.year, r.month))


def december_series(rows: List[PublicDebtMonth]) -> Dict[int, PublicDebtMonth]:
    """Year -> December reading, the convention the debt timeline uses."""
    return {r.year: r for r in rows if r.month == 12}


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def _get_html(client: SeedingHttpClient, url: str) -> str:
    resp = client.get(url, headers={"User-Agent": "Mozilla/5.0 (AuditGava seeding)"})
    resp.raise_for_status()
    return resp.text


def fetch_bond_register(
    client: SeedingHttpClient,
    settings: Optional[SeedingSettings] = None,
    as_of: Optional[date] = None,
) -> Dict[str, Any]:
    """The outstanding Treasury-bond register, with its provenance."""
    html_text = _get_html(client, BONDS_URL)
    tranches = parse_bond_register(html_text, BONDS_URL)
    securities = outstanding_securities(tranches, as_of=as_of)
    return {
        "source_url": BONDS_URL,
        "source_title": "CBK — Issues of Treasury Bonds",
        "retrieved_at": datetime.utcnow().isoformat() + "Z",
        "tranche_rows": len(tranches),
        "securities": securities,
        "as_of": (as_of or date.today()).isoformat(),
    }


def fetch_public_debt_monthly(
    client: SeedingHttpClient, settings: Optional[SeedingSettings] = None
) -> Dict[str, Any]:
    """The monthly public-debt series, with its provenance."""
    html_text = _get_html(client, PUBLIC_DEBT_URL)
    rows = parse_public_debt_monthly(html_text, PUBLIC_DEBT_URL)
    return {
        "source_url": PUBLIC_DEBT_URL,
        "source_title": "CBK — Public Debt (monthly)",
        "retrieved_at": datetime.utcnow().isoformat() + "Z",
        "rows": rows,
        "covers": [
            f"{rows[0].year}-{rows[0].month:02d}",
            f"{rows[-1].year}-{rows[-1].month:02d}",
        ],
    }
