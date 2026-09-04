"""Read the APPROVED revenue estimate for a fiscal year from Treasury's
Budget Summary.

WHY THIS EXISTS
---------------
The domain already ingests revenue: ``_fetch_cob_headlines`` discovers COB's
NG-BIRR and ``_overlay_live_revenue_headline`` promotes the total onto a row.
That path structurally cannot produce a revenue figure for a NEW fiscal year,
for the same two reasons ``budget_estimates`` documents for the budget:

1. COB has not published for the year yet, and will not for months. It
   publishes at quarter-end + 45 days, so FY2026/27 Q1 is not due until
   ~15 Nov 2026.
2. ``_overlay_live_revenue_headline`` only ever MUTATES a row it finds. An
   overlay cannot create a fiscal year, and it additionally refuses any value
   more than 15% from the fixture's last-known total — which a year with no
   fixture row does not have.

So on 2026-09-04 the site had an enacted FY2026/27 budget (2,315.9B of debt
service inside it) and no revenue to divide it by, and the debt-service chart
plotted "share of revenue" as 0% for the year that share is largest.

The missing figure lives in a document class this pipeline did not ingest at
all: the National Treasury's **Budget Summary**, published alongside the
budget books. This module reads the medium-term fiscal framework table out of
it, so the figure is re-derived from the source on every run rather than typed
into a fixture once and left to rot.

WHICH REVENUE
-------------
"Ordinary Revenue" — tax + non-tax, EXCLUDING Appropriations-in-Aid and
grants. That is the measure the rest of this file's revenue series is on, and
the denominator of Treasury's own headline debt-service-to-revenue ratio.
Total revenue including A-i-A is carried too, because it is what the table's
own identity check needs, but it is NOT what gets published as
``total_revenue``.

THE COLUMN PROBLEM
------------------
Table 2 prints TWO columns for the budget year. In the FY2026/27 book they are
"Approved Budget" and "2026 BPS", and their header order is not recoverable
from the PDF text layer — the header words do not align to the data columns
closely enough to tell them apart, and picking the wrong one publishes a
revenue figure that is out by ~84 billion.

They are separated by cross-document identity instead, which is the same
technique ``budget_estimates`` uses for its strongest gate: the Budget Policy
Statement independently publishes its own ordinary-revenue projection, so
whichever column equals the BPS figure IS the BPS column, and the other is the
approved budget. A parse that grabbed the wrong column cannot satisfy that by
accident.

THE GATES
---------
Every identity must hold before a figure may be published; any failure raises
``RevenueEstimatesError`` and the caller quarantines rather than publishing:

1. ``ordinary + ministerial AiA == total revenues`` in the chosen column.
2. The OTHER column for the same year matches the BPS's published ordinary
   revenue, which is what identifies the chosen column as the approved one.
3. The book's PRIOR-year column matches what we already hold for that year,
   so a parse that slipped a column is caught by a figure we can check.
4. The result sits inside a plausible band for Kenyan ordinary revenue.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("seeding.fiscal_summary.revenue_estimates")

#: Ordinary revenue the Budget Policy Statement publishes for a fiscal year,
#: with the receipt it was read from. Used ONLY to tell the two budget-year
#: columns apart (gate 2) — never published as the figure itself, because the
#: BPS number is a policy projection and the approved budget supersedes it.
BPS_PUBLISHED_ORDINARY_REVENUE_BILLION: Dict[str, Tuple[float, str]] = {
    "FY 2026/27": (
        2901.9,
        "2026 Budget Policy Statement (The National Treasury), para 340 p.89 "
        "and Annex Table 2 p.121; also 'ORDINARY REVENUE (EXCLUDING AIA) "
        "2,901,875' (thousand) on p.91",
    ),
}

#: How far the two may drift and still be called the same figure.
BPS_CROSS_CHECK_TOLERANCE_PCT = 0.5

#: Prior-year drift allowed on gate 3. Wider than gate 2 because the book and
#: our own row can legitimately be different vintages of the same year
#: (supplementary estimates revise it mid-year).
PRIOR_YEAR_TOLERANCE_PCT = 3.0

#: Kenyan ordinary revenue, KSh billion. A parse landing outside this is a
#: column slip or a units error, not a real collapse or windfall.
_PLAUSIBLE_ORDINARY_REVENUE_BILLION = (1500.0, 6000.0)

_TABLE_MARKER = "medium-term fiscal framework"

# Row labels as they appear once whitespace is collapsed. The PDF renders
# these letter-spaced ("O rd in a ry R e ve n u e"), so callers must strip
# spaces before matching — see ``_squash``.
_ROW_TOTAL_REVENUES = "2.0totalrevenues"
_ROW_ORDINARY = "2.1ordinaryrevenue"
_ROW_AIA = "2.2ministerialaia"


class RevenueEstimatesError(Exception):
    """A parse that must be QUARANTINED, never published.

    Carries a short machine-readable ``reason`` so the caller can record why
    the figure was not published instead of logging prose nobody gates on.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class RevenueEstimates:
    """The approved revenue estimate for one fiscal year, with its receipts."""

    fiscal_year: str  # "FY 2026/27"
    #: Tax + non-tax, EXCLUDING A-i-A and grants. This is what gets published.
    ordinary_revenue_billion: Decimal
    #: Ordinary + ministerial A-i-A. Carried for the identity check and so the
    #: UI can name the broader measure without re-deriving it.
    total_revenue_incl_aia_billion: Decimal
    ministerial_aia_billion: Decimal
    #: The column that was NOT chosen, and the BPS figure it matched.
    bps_column_billion: Optional[Decimal] = None
    prior_fiscal_year: Optional[str] = None
    prior_ordinary_revenue_billion: Optional[Decimal] = None
    source_url: Optional[str] = None
    page_refs: Dict[str, int] = field(default_factory=dict)
    checks: List[str] = field(default_factory=list)


def _squash(text: str) -> str:
    """Collapse the letter-spacing Treasury's table renderer emits."""
    return re.sub(r"\s+", "", text).lower()


def _to_decimal(token: str) -> Optional[Decimal]:
    """``'2,985.7'`` -> Decimal, ``'(1,126.9)'`` -> negative, ``'-'`` -> None."""
    t = token.strip()
    if t in {"-", "–", "—", ""}:
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()").replace(",", "")
    try:
        value = Decimal(t)
    except Exception:
        return None
    return -value if neg else value


@dataclass(frozen=True)
class FiscalFrameworkTable:
    """Table 2, reduced to the rows this module needs.

    Each row maps a fiscal year to the columns printed under it, left to
    right. A budget year has TWO columns; settled years have one.
    """

    ordinary_revenue: Dict[str, List[Decimal]]
    total_revenues: Dict[str, List[Decimal]]
    ministerial_aia: Dict[str, List[Decimal]]
    page: Optional[int] = None

    def years(self) -> List[str]:
        return sorted(self.ordinary_revenue)


def parse_fiscal_framework(words: List[dict], *, page: Optional[int] = None) -> FiscalFrameworkTable:
    """Read Table 2's revenue rows out of one page's positioned words.

    Takes pdfplumber ``extract_words()`` output rather than text, because the
    columns can only be assigned by x-position: the table prints the same rows
    twice (KSh Billion, then as a share of GDP), and a text-order read cannot
    tell the halves apart or tell which of a budget year's two columns is
    which.
    """
    lines: Dict[int, List[dict]] = {}
    for w in words:
        lines.setdefault(round(w["top"] / 2) * 2, []).append(w)

    def merged(ws: List[dict]) -> List[Tuple[str, float]]:
        """Rejoin letter-spaced glyph runs into tokens, keeping each x0."""
        ws = sorted(ws, key=lambda w: w["x0"])
        out: List[Tuple[str, float]] = []
        cur, x0, last = ws[0]["text"], ws[0]["x0"], ws[0]
        for w in ws[1:]:
            if w["x0"] - last["x1"] < 1.6:
                cur += w["text"]
            else:
                out.append((cur, x0))
                cur, x0 = w["text"], w["x0"]
            last = w
        out.append((cur, x0))
        return out

    # ── Year header. The row lists every year TWICE: once for the KSh Billion
    # half and again for the "as a share of GDP" half. The x of the first
    # repeat is the boundary between them, so the money half needs no guess.
    year_cols: List[Tuple[str, float]] = []
    money_right_edge = float("inf")
    for y in sorted(lines):
        fys = [
            (t, x) for t, x in merged(lines[y]) if re.fullmatch(r"FY\d{4}/\d{2}", t)
        ]
        if len(fys) >= 4:
            seen: Dict[str, float] = {}
            for label, x in fys:
                if label in seen:
                    money_right_edge = min(money_right_edge, x)
                else:
                    seen[label] = x
            year_cols = sorted(seen.items(), key=lambda kv: kv[1])
            break
    if not year_cols:
        raise RevenueEstimatesError("no_year_header", "no FY column header found on the page")

    def money_numbers(toks: List[Tuple[str, float]]) -> List[Tuple[float, Decimal]]:
        out: List[Tuple[float, Decimal]] = []
        for tok, x in toks:
            if x >= money_right_edge:
                break
            if not re.search(r"\d", tok):
                continue
            value = _to_decimal(tok)
            if value is not None:
                out.append((x, value))
        return out

    # ── Column grid. The table is a uniform grid: the year labels do NOT sit
    # centred over their group, they sit over the group's FIRST column, and a
    # budget year's two columns are spaced exactly like every other pair. So
    # the grid is taken from the widest data row and the years are mapped onto
    # it by index — assigning each number to its "nearest year label" instead
    # puts a budget year's second column under the FOLLOWING year, which is
    # how FY2026/27's approved column first went missing.
    rows_raw: Dict[str, List[Tuple[float, Decimal]]] = {}
    for y in sorted(lines):
        toks = merged(lines[y])
        label = _squash("".join(t for t, _ in toks[:4]))
        for key, marker in (
            ("total_revenues", _ROW_TOTAL_REVENUES),
            ("ordinary", _ROW_ORDINARY),
            ("aia", _ROW_AIA),
        ):
            if label.startswith(marker) and key not in rows_raw:
                rows_raw[key] = money_numbers(toks)

    missing = [k for k in ("total_revenues", "ordinary", "aia") if k not in rows_raw]
    if missing:
        raise RevenueEstimatesError(
            "rows_not_found", f"Table 2 exposed no {', '.join(missing)} row"
        )

    grid = [x for x, _ in max(rows_raw.values(), key=len)]
    if len(grid) < len(year_cols):
        raise RevenueEstimatesError(
            "grid_narrower_than_header",
            f"{len(grid)} money columns for {len(year_cols)} year labels",
        )

    # Each year label -> the index of the column it sits over.
    starts: List[Tuple[str, int]] = []
    for label, hx in year_cols:
        idx = min(range(len(grid)), key=lambda i: abs(grid[i] - hx))
        starts.append((label, idx))
    if len({i for _, i in starts}) != len(starts):
        raise RevenueEstimatesError(
            "year_labels_share_a_column",
            f"year labels mapped to {sorted(i for _, i in starts)}",
        )

    # A year owns every column from its own up to the next year's.
    spans: Dict[str, Tuple[int, int]] = {}
    for n, (label, idx) in enumerate(starts):
        end_idx = starts[n + 1][1] if n + 1 < len(starts) else len(grid)
        spans[label] = (idx, end_idx)

    def by_year(cells: List[Tuple[float, Decimal]]) -> Dict[str, List[Decimal]]:
        ordered = [v for _, v in sorted(cells, key=lambda p: p[0])]
        out: Dict[str, List[Decimal]] = {}
        for label, (lo, hi) in spans.items():
            picked = ordered[lo:hi]
            if picked:
                out[label] = picked
        return out

    return FiscalFrameworkTable(
        ordinary_revenue=by_year(rows_raw["ordinary"]),
        total_revenues=by_year(rows_raw["total_revenues"]),
        ministerial_aia=by_year(rows_raw["aia"]),
        page=page,
    )


def _normalise_fy(label: str) -> str:
    """``'FY2026/27'`` -> ``'FY 2026/27'`` to match the rest of the domain."""
    m = re.fullmatch(r"FY\s*(\d{4})/(\d{2})", label.strip())
    return f"FY {m.group(1)}/{m.group(2)}" if m else label.strip()


def _previous_fiscal_year(label: str) -> Optional[str]:
    m = re.search(r"(\d{4})/(\d{2})", label or "")
    if not m:
        return None
    start = int(m.group(1)) - 1
    return f"FY {start}/{str(start + 1)[-2:]}"


def build_revenue_estimates(
    *,
    fiscal_year: str,
    table: FiscalFrameworkTable,
    known_prior_ordinary_billion: Optional[float] = None,
    source_url: Optional[str] = None,
) -> RevenueEstimates:
    """Apply every gate and return the publishable figure, or raise.

    Pure: takes what the page parser found and decides. Kept separate from the
    PDF walk so each gate has a test that makes it FIRE.
    """
    key = next(
        (k for k in table.ordinary_revenue if _normalise_fy(k) == fiscal_year), None
    )
    if key is None:
        raise RevenueEstimatesError(
            "fiscal_year_not_in_table",
            f"{fiscal_year} has no column; found "
            f"{[_normalise_fy(k) for k in table.years()] or 'nothing'}",
        )

    ordinary_cols = table.ordinary_revenue.get(key) or []
    if len(ordinary_cols) < 2:
        raise RevenueEstimatesError(
            "budget_year_not_two_columns",
            f"{fiscal_year} printed {len(ordinary_cols)} ordinary-revenue "
            f"column(s); the approved column cannot be identified from one",
        )

    # ── Gate 2 (run first: it decides WHICH column the others check) ───────
    expected = BPS_PUBLISHED_ORDINARY_REVENUE_BILLION.get(fiscal_year)
    if expected is None:
        raise RevenueEstimatesError(
            "no_bps_figure_on_file",
            f"{fiscal_year} prints two columns but no BPS ordinary-revenue "
            f"figure is recorded to tell them apart",
        )
    bps_value, receipt = expected
    matches = [
        c
        for c in ordinary_cols
        if abs(float(c) - bps_value) / bps_value * 100.0 <= BPS_CROSS_CHECK_TOLERANCE_PCT
    ]
    if len(matches) != 1:
        raise RevenueEstimatesError(
            "bps_column_not_identified",
            f"{len(matches)} of {len(ordinary_cols)} columns "
            f"({[float(c) for c in ordinary_cols]}) match the BPS figure "
            f"{bps_value}. Source: {receipt}",
        )
    bps_col = matches[0]
    approved_cols = [c for c in ordinary_cols if c is not bps_col]
    if len(approved_cols) != 1:
        raise RevenueEstimatesError(
            "approved_column_ambiguous",
            f"{len(approved_cols)} columns remain after removing the BPS one",
        )
    ordinary = approved_cols[0]
    index = ordinary_cols.index(ordinary)

    checks = [
        f"BPS column {float(bps_col)} matches published {bps_value} "
        f"(identifies the other column as approved). Source: {receipt}"
    ]

    # ── Gate 1: the chosen column's own components must add up ────────────
    def column(row: Dict[str, List[Decimal]]) -> Optional[Decimal]:
        cols = row.get(key) or []
        return cols[index] if index < len(cols) else None

    total = column(table.total_revenues)
    aia = column(table.ministerial_aia)
    if total is None or aia is None:
        raise RevenueEstimatesError(
            "column_incomplete",
            f"the approved column has "
            f"{'no total revenues' if total is None else 'no ministerial AiA'}",
        )
    if abs((ordinary + aia) - total) > total * Decimal("0.001"):
        raise RevenueEstimatesError(
            "revenue_does_not_reconcile",
            f"ordinary ({ordinary}) + ministerial AiA ({aia}) != "
            f"total revenues ({total})",
        )
    checks.append(f"ordinary+AiA==total revenues ({total})")

    # ── Gate 3: prior year must match the figure we already hold ──────────
    prior = _previous_fiscal_year(fiscal_year)
    prior_key = next(
        (k for k in table.ordinary_revenue if _normalise_fy(k) == prior), None
    )
    prior_cols = table.ordinary_revenue.get(prior_key or "") or []
    prior_value = prior_cols[-1] if prior_cols else None
    if prior_value is not None and known_prior_ordinary_billion:
        drift = (
            abs(float(prior_value) - known_prior_ordinary_billion)
            / known_prior_ordinary_billion
            * 100.0
        )
        if drift > PRIOR_YEAR_TOLERANCE_PCT:
            raise RevenueEstimatesError(
                "prior_year_revenue_mismatch",
                f"{prior} ordinary revenue reads {float(prior_value)}B in this "
                f"book but we hold {known_prior_ordinary_billion}B "
                f"({drift:.1f}% apart)",
            )
        checks.append(
            f"{prior} ordinary revenue {float(prior_value)}B matches the "
            f"{known_prior_ordinary_billion}B on file ({drift:.2f}% apart)"
        )
    else:
        # Say so; do not let a skipped check read as a passed one.
        checks.append(
            f"prior-year cross-check SKIPPED — "
            f"{'no prior column in the book' if prior_value is None else 'nothing on file'}"
            f" for {prior}"
        )

    # ── Gate 4: plausibility ──────────────────────────────────────────────
    lo, hi = _PLAUSIBLE_ORDINARY_REVENUE_BILLION
    if not (lo <= float(ordinary) <= hi):
        raise RevenueEstimatesError(
            "revenue_outside_plausible_band",
            f"{float(ordinary)}B is outside the [{lo}B, {hi}B] band",
        )

    return RevenueEstimates(
        fiscal_year=fiscal_year,
        ordinary_revenue_billion=ordinary,
        total_revenue_incl_aia_billion=total,
        ministerial_aia_billion=aia,
        bps_column_billion=bps_col,
        prior_fiscal_year=prior,
        prior_ordinary_revenue_billion=prior_value,
        source_url=source_url,
        page_refs={"fiscal_framework": table.page} if table.page else {},
        checks=checks,
    )


def extract_revenue_estimates(
    pdf_path, fiscal_year: str, *, known_prior_ordinary_billion: Optional[float] = None,
    source_url: Optional[str] = None,
) -> RevenueEstimates:
    """Walk the Budget Summary for Table 2 and return the gated figure.

    Raises ``RevenueEstimatesError`` on anything it cannot prove.
    """
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            # Both sides squashed: the table renderer letter-spaces its title
            # ("M e d iu m -T e rm"), so only a whitespace-free compare finds it.
            if _squash(_TABLE_MARKER) not in _squash(text):
                continue
            table = parse_fiscal_framework(page.extract_words(), page=i + 1)
            return build_revenue_estimates(
                fiscal_year=fiscal_year,
                table=table,
                known_prior_ordinary_billion=known_prior_ordinary_billion,
                source_url=source_url,
            )

    raise RevenueEstimatesError(
        "fiscal_framework_table_not_found",
        f"no page matching '{_TABLE_MARKER}' in {pdf_path}",
    )
