"""Read the ENACTED gross budget for a fiscal year from Treasury's Budget Estimates.

WHY THIS EXISTS
---------------
On 2026-08-29 the site still showed FY 2025/26. That was not the frozen-COB
bug fixed in 897a00d: the COB path was working and current. COB's newest
National Government BIRR *is* the FY2025/26 nine-month report, because COB
publishes at quarter-end + 45 days and FY2026/27 Q1 is not due until
~15 Nov 2026. Nothing in the COB pipeline could ever produce an FY2026/27
row, for two independent reasons:

1. COB has not published one, and will not for months.
2. ``_overlay_live_budget_headline`` only ever MUTATES ``max(fiscal_years)``.
   An overlay cannot create a fiscal year.

The enacted FY2026/27 budget lives in a document class this pipeline did not
ingest at all: the National Treasury Budget Estimates ("budget books"),
approved by Parliament and published under ``/budget-books``. This module
reads the headline gross budget out of the Programme Based Budget book.

WHAT "GROSS BUDGET" MEANS HERE
------------------------------
The user chose COB's "original gross budget" as the canonical basis, so this
parser reproduces COB's OWN composition rather than inventing one. COB states
it explicitly (NG-BIRR First Nine Months FY2025/26, Executive Summary, p.xxii,
PDF page 23)::

    "The National Government's original gross budget for FY 2025/26 amounts
     to Kshs. 4.69 trillion ... This comprises Kshs.744.84 billion for
     ministerial development expenditure ... Recurrent vote allocation
     amounts to Kshs.3.95 trillion, comprising the ministerial recurrent
     allocation of Kshs.1.80 trillion ... and Consolidated Fund Services
     (CFS) at Kshs. 2.14 trillion"

i.e. **gross budget = gross voted (ministerial) expenditure + CFS**, and it
EXCLUDES the county equitable share (COB reports that separately: Kshs.418.26
billion of exchequer issues to counties in FY2024/25).

Both halves are printed in the Programme Based Budget book:

* "TOTAL VOTED EXPENDITURE ... KShs." — gross current + gross capital + gross
  total, on the "Summary of Expenditure by Vote and Category" page.
* "GRAND TOTAL Kshs" on the Consolidated Fund Services summary page, one
  column per fiscal year.

THE GATE
--------
Three independent identities must hold before a figure may be published; any
failure quarantines rather than publishes (see ``BudgetEstimatesError``):

1. ``gross current + gross capital == gross total`` on the voted page.
2. ``interest&redemption + pensions/salaries/misc == CFS grand total`` in the
   target column.
3. The book's PRIOR-year CFS column must match what COB independently
   published for that year. This is the strongest check available because it
   crosses publishers: the FY2026/27 book prints FY2025/26 CFS as
   Kshs.2,141,025,101,165 and COB's FY2025/26 report states CFS of
   "Kshs. 2.14 trillion". A parse that grabbed the wrong column or the wrong
   row cannot satisfy that by accident.

Anchors were confirmed against the real FY2026/27 Approved Programme Based
Budget Book on 2026-08-29 (29,637,635 bytes, 1,206 pages), not from
documentation — three parser bugs this month came from anchors that the real
PDF does not use.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("seeding.fiscal_summary.budget_estimates")

# ── Anchors, confirmed against the real FY2026/27 Approved PBB ────────
# Page (v) — "GLOBAL BUDGET - CAPITAL & CURRENT / Summary of Expenditure by
# Vote and Category 2026/2027 (KShs)" ends with:
#     TOTAL VOTED EXPENDITURE ... KShs.
#     2,078,271,468,734 844,435,444,450 2,922,706,913,184
_VOTED_TOTAL_ANCHOR = "total voted expenditure"

# The CFS appendix's "SUMMARY 1" page carries the per-year GRAND TOTAL.
_CFS_PAGE_ANCHOR = "consolidated fund services"
_CFS_GRAND_TOTAL_ANCHOR = "grand total"
_CFS_INTEREST_REDEMPTION_ANCHOR = "interest & redemption"
# Matched after collapsing spaces around the dash, so both "Sub - Total" and
# "Sub-Total" (the page uses both) hit it.
_CFS_SUBTOTAL_ANCHOR = "sub-total"

# The column header line is a run of "YYYY/YYYY" labels, one per column.
_FY_HEADER_LINE_RE = re.compile(r"^\s*(?:(?:19|20)\d{2}\s*/\s*(?:19|20)\d{2}\s*)+$")
_FY_LABEL_RE = re.compile(r"((?:19|20)\d{2})\s*/\s*((?:19|20)\d{2})")
# Sits directly above the year line: "ESTIMATES SUPP I ESTIMATES ESTIMATES ..."
_QUALIFIER_RE = re.compile(r"SUPP\s*I+V?|REVISED|ESTIMATES", re.IGNORECASE)

# How many pages to read from each end of the book. The voted summary is
# front matter (page (v) = PDF page 11 of 1,206); the CFS appendix is the
# last section (PDF page 1,193 of 1,206). Bounded so a 1,200-page book is
# not fully rendered, and a miss is REPORTED, never silently absorbed.
FRONT_PAGES = 40
BACK_PAGES = 60

# Kenya's national gross budget, in raw KES. Wide enough for a decade of
# growth, tight enough that a units slip (millions read as shillings, or a
# per-vote line read as the total) cannot pass.
_PLAUSIBLE_GROSS_KES = (2_000e9, 12_000e9)

# COB's independently published CFS by fiscal year, in raw KES, used as the
# cross-publisher check in rule 3. Each entry carries its receipt.
COB_PUBLISHED_CFS_KES: Dict[str, Tuple[float, str]] = {
    "FY 2025/26": (
        2.14e12,
        "COB NG-BIRR First Nine Months FY2025/26 (May 2026), Executive "
        "Summary p.xxii (PDF p.23): 'Consolidated Fund Services (CFS) at "
        "Kshs. 2.14 trillion'",
    ),
    "FY 2024/25": (
        1.99e12,
        "COB NG-BIRR FY2024/25 (Aug 2025), Executive Summary p.xxviii "
        "(PDF p.29): 'Consolidated Fund Services (CFS) at Kshs.1.99 "
        "trillion' (revised budget)",
    ),
    "FY 2023/24": (
        1.96e12,
        "COB NG-BIRR FY2023/24 (Aug 2024), s.3.2 p.17 (PDF p.39): "
        "'Kshs.1.96 trillion for CFS' (original estimates)",
    ),
}
# COB rounds CFS to 3 significant figures ("2.14 trillion"), so the
# cross-check tolerance must absorb that rounding and nothing more.
CFS_CROSS_CHECK_TOLERANCE_PCT = 1.0


class BudgetEstimatesError(Exception):
    """A parse that must be QUARANTINED, never published.

    Carries a short machine-readable ``reason`` so the caller can record why
    the fiscal year was not created instead of logging prose nobody gates on.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class BudgetEstimates:
    """The enacted gross budget for one fiscal year, with its receipts."""

    fiscal_year: str  # "FY 2026/27"
    voted_gross_kes: Decimal
    voted_current_kes: Decimal
    voted_capital_kes: Decimal
    cfs_kes: Decimal
    #: How much of ``cfs_kes`` is redemption of maturing debt rather than new
    #: spending. ``None`` when the book's own sub-totals did not reconcile, so
    #: an unproven split is never published. This is the single largest reason
    #: the gross figure differs from the enacted headline.
    debt_redemption_kes: Optional[Decimal] = None
    prior_fiscal_year: Optional[str] = None
    prior_cfs_kes: Optional[Decimal] = None
    source_url: Optional[str] = None
    page_refs: Dict[str, int] = field(default_factory=dict)
    checks: List[str] = field(default_factory=list)

    @property
    def gross_budget_kes(self) -> Decimal:
        return self.voted_gross_kes + self.cfs_kes

    @property
    def gross_budget_billion(self) -> float:
        return float(self.gross_budget_kes) / 1e9


# ── Number extraction ────────────────────────────────────────────────
# pdfplumber renders this book's right-aligned money columns with a stray
# space after the leading digit(s): "2 ,562,973,919,672", "9 86,725,816,391",
# "7 2,480,000". Naively stripping every space inside a digit run would fuse
# two ADJACENT columns ("71,000,000 71,000,000" -> "71,000,00071,000,000"),
# so fragments are merged only when the left piece is a bare 1-2 digit token
# AND the merge yields a legal 1-3 digit leading group.
_TOKEN_RE = re.compile(r"^[\d,]+$")
_WELL_FORMED_RE = re.compile(r"^\d{1,3}(?:,\d{3})*$")


def numbers_in_line(line: str) -> List[Decimal]:
    """Every money figure on ``line``, repairing pdfplumber's split digits."""
    tokens = (line or "").split()
    out: List[Decimal] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if not _TOKEN_RE.match(tok):
            i += 1
            continue
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if (
            tok.isdigit()
            and len(tok) <= 2
            and _TOKEN_RE.match(nxt or "")
            and (nxt.startswith(",") or _WELL_FORMED_RE.match(nxt))
            and len(tok + nxt.split(",")[0]) <= 3
        ):
            merged = tok + nxt
            if _WELL_FORMED_RE.match(merged):
                out.append(_to_decimal(merged))
                i += 2
                continue
        if _WELL_FORMED_RE.match(tok):
            out.append(_to_decimal(tok))
        i += 1
    return [v for v in out if v is not None]


def _to_decimal(text: str) -> Optional[Decimal]:
    try:
        return Decimal(text.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


# ── Page-level parsers (pure; unit-tested against real page text) ─────
def extract_voted_gross_from_text(
    text: str,
) -> Optional[Tuple[Decimal, Decimal, Decimal]]:
    """``(gross_current, gross_capital, gross_total)`` in raw KES, or None.

    The anchor and its figures sit on SEPARATE lines in the real book, so the
    anchor line and the two following lines are searched — the same wrapping
    problem that made the COB headline extractor return nothing until
    ``unwrap`` was added there.
    """
    lines = (text or "").splitlines()
    for idx, line in enumerate(lines):
        if _VOTED_TOTAL_ANCHOR not in line.lower():
            continue
        for candidate in (line, *lines[idx + 1 : idx + 3]):
            nums = numbers_in_line(candidate)
            # Take the LAST three: the anchor line may carry a page label.
            if len(nums) >= 3:
                current, capital, total = nums[-3], nums[-2], nums[-1]
                if current > 0 and capital >= 0 and total > 0:
                    return current, capital, total
    return None


def parse_fy_columns(text: str) -> List[Tuple[str, bool]]:
    """Column order of a CFS summary page as ``[(fy_label, is_supplementary)]``.

    The FY2026/27 book prints seven columns, the first two BOTH FY2025/26 —
    printed estimates and Supplementary I. Picking a year by name alone would
    be a coin flip between an original and a revised budget, which is exactly
    the basis conflation this codebase keeps tripping over, so the qualifier
    line directly above ("ESTIMATES SUPP I ESTIMATES ...") is parsed too.
    """
    lines = (text or "").splitlines()
    for idx, line in enumerate(lines):
        if not _FY_HEADER_LINE_RE.match(line):
            continue
        labels = [
            f"FY {m.group(1)}/{m.group(2)[-2:]}"
            for m in _FY_LABEL_RE.finditer(line)
        ]
        if not labels:
            continue
        qualifiers: List[str] = []
        for prev in reversed(lines[max(0, idx - 3) : idx]):
            found = _QUALIFIER_RE.findall(prev)
            if len(found) == len(labels):
                qualifiers = [q.upper().replace(" ", "") for q in found]
                break
        if len(qualifiers) != len(labels):
            # No usable qualifier row: treat the FIRST occurrence of each
            # year as its printed estimates and say so, rather than guessing
            # silently.
            seen: set[str] = set()
            out: List[Tuple[str, bool]] = []
            for lab in labels:
                out.append((lab, lab in seen))
                seen.add(lab)
            return out
        return [
            (lab, not q.startswith("ESTIMATES"))
            for lab, q in zip(labels, qualifiers)
        ]
    return []


@dataclass
class CfsSummary:
    """Consolidated Fund Services totals from one summary page.

    ``redemption`` is populated only when the page's interest and redemption
    sub-totals reconcile to their own combined line (identity 4). It is what
    lets the site say how much of the gross budget is rolling over maturing
    debt rather than funding new spending — the single largest reason the
    gross figure and the enacted headline differ.

    Behaves like the plain ``{fiscal_year: total}`` mapping this used to
    return, so existing callers read unchanged.
    """

    totals: Dict[str, Decimal] = field(default_factory=dict)
    redemption: Dict[str, Decimal] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.totals)

    def __len__(self) -> int:
        return len(self.totals)

    def __iter__(self):
        return iter(self.totals)

    def __contains__(self, key) -> bool:
        return key in self.totals

    def __getitem__(self, key):
        return self.totals[key]

    def get(self, key, default=None):
        return self.totals.get(key, default)

    def items(self):
        return self.totals.items()

    def keys(self):
        # With __getitem__, this completes the mapping protocol, so dict(x)
        # and {**x} keep working for callers that treat it as the plain
        # {fiscal_year: total} mapping it replaced.
        return self.totals.keys()

    def values(self):
        return self.totals.values()

    def __eq__(self, other) -> bool:
        if isinstance(other, CfsSummary):
            return (self.totals, self.redemption) == (other.totals, other.redemption)
        # Compared against a plain mapping, only the totals are in scope.
        return self.totals == other


def parse_cfs_summary_from_text(text: str) -> CfsSummary:
    """CFS totals (and, where provable, the redemption split) from a page.

    Only ORIGINAL (printed) estimate columns are returned; supplementary
    columns are dropped so a revised figure can never be served as an
    original one. Raises :class:`BudgetEstimatesError` when the page's own
    arithmetic does not reconcile.
    """
    low = (text or "").lower()
    if _CFS_PAGE_ANCHOR not in low or _CFS_GRAND_TOTAL_ANCHOR not in low:
        return CfsSummary()

    columns = parse_fy_columns(text)
    if not columns:
        return CfsSummary()

    grand: List[Decimal] = []
    interest: List[Decimal] = []
    subtotal: List[Decimal] = []
    # Sub-totals printed BEFORE the "Total: INTEREST & REDEMPTION" line. The
    # last two are the interest block and the redemption block; identity 4
    # below proves it, so a mis-selected row quarantines rather than
    # publishing a wrong redemption figure.
    pre_anchor_subtotals: List[List[Decimal]] = []
    seen_interest = False
    for line in text.splitlines():
        # "Sub - Total Kshs" and "Sub-Total Kshs" both occur on this page;
        # normalise so the anchor does not depend on pdfplumber's spacing.
        lowered = re.sub(r"\s*-\s*", "-", line.lower().lstrip())
        if lowered.startswith(_CFS_GRAND_TOTAL_ANCHOR):
            grand = numbers_in_line(line)
        elif _CFS_INTEREST_REDEMPTION_ANCHOR in lowered:
            interest = numbers_in_line(line)
            seen_interest = True
        elif not seen_interest and lowered.startswith(_CFS_SUBTOTAL_ANCHOR):
            pre_anchor_subtotals.append(numbers_in_line(line))
        elif seen_interest and lowered.startswith(_CFS_SUBTOTAL_ANCHOR):
            # THREE "Sub-Total" rows exist: interest, redemption, and the
            # pensions/salaries/miscellaneous block. Only the third completes
            # the identity, and it is the only one printed AFTER the
            # "Total: INTEREST & REDEMPTION" line — so position, not row
            # order luck, selects it.
            subtotal = numbers_in_line(line)

    if len(grand) != len(columns):
        raise BudgetEstimatesError(
            "cfs_column_count_mismatch",
            f"{len(grand)} GRAND TOTAL figure(s) for {len(columns)} column(s)",
        )

    # Identity 2: interest&redemption + pensions/salaries/misc == grand total.
    if len(interest) == len(grand) and len(subtotal) == len(grand):
        for idx, (label, _supp) in enumerate(columns):
            expected = interest[idx] + subtotal[idx]
            if abs(expected - grand[idx]) > grand[idx] * Decimal("0.001"):
                raise BudgetEstimatesError(
                    "cfs_does_not_reconcile",
                    f"{label}: interest+redemption ({interest[idx]}) + "
                    f"other ({subtotal[idx]}) != grand total ({grand[idx]})",
                )
    else:
        raise BudgetEstimatesError(
            "cfs_components_not_found",
            "the CFS page's component rows could not be read, so its grand "
            "total cannot be cross-checked against its own parts",
        )

    # Identity 4: interest + redemption == the combined interest&redemption
    # line. Splitting them is what lets the site say how much of the gross
    # budget is rolling over maturing debt rather than new spending — and the
    # identity is what makes the split trustworthy rather than positional luck.
    redemption: List[Decimal] = []
    if len(pre_anchor_subtotals) >= 2:
        cand_interest, cand_redemption = pre_anchor_subtotals[-2:]
        if (
            len(cand_interest) == len(interest)
            and len(cand_redemption) == len(interest)
            and all(
                abs((cand_interest[i] + cand_redemption[i]) - interest[i])
                <= interest[i] * Decimal("0.001")
                for i in range(len(interest))
            )
        ):
            redemption = cand_redemption
        else:
            logger.info(
                "CFS interest/redemption sub-totals did not reconcile to their "
                "own combined line; publishing the combined figure only"
            )

    out: CfsSummary = CfsSummary()
    for idx, (label, is_supp) in enumerate(columns):
        if is_supp or label in out.totals:
            continue
        out.totals[label] = grand[idx]
        if redemption:
            out.redemption[label] = redemption[idx]
    return out


def _previous_fiscal_year(label: str) -> Optional[str]:
    m = re.match(r"FY (\d{4})/(\d{2})$", label or "")
    if not m:
        return None
    start = int(m.group(1)) - 1
    return f"FY {start}/{str(start + 1)[-2:]}"


def build_estimates(
    *,
    fiscal_year: str,
    voted: Tuple[Decimal, Decimal, Decimal],
    cfs_by_year: Dict[str, Decimal],
    page_refs: Optional[Dict[str, int]] = None,
) -> BudgetEstimates:
    """Apply every gate and return the publishable figure, or raise.

    Pure: takes what the two page parsers found and decides. Kept separate
    from the PDF walk so each gate has a test that makes it FIRE.
    """
    current, capital, total = voted

    # Identity 1: the voted page's own columns must add up.
    if abs((current + capital) - total) > total * Decimal("0.001"):
        raise BudgetEstimatesError(
            "voted_does_not_reconcile",
            f"gross current ({current}) + gross capital ({capital}) != "
            f"gross total ({total})",
        )

    cfs = cfs_by_year.get(fiscal_year)
    if cfs is None:
        raise BudgetEstimatesError(
            "cfs_year_not_found",
            f"{fiscal_year} has no original-estimates column; found "
            f"{sorted(cfs_by_year) or 'nothing'}",
        )

    checks = [
        f"voted current+capital==total ({total})",
        f"CFS components reconcile to grand total ({cfs})",
    ]

    # Identity 3: cross-publisher check on the prior year's CFS column.
    prior = _previous_fiscal_year(fiscal_year)
    prior_cfs = cfs_by_year.get(prior) if prior else None
    expected = COB_PUBLISHED_CFS_KES.get(prior or "")
    if prior_cfs is not None and expected is not None:
        cob_value, receipt = expected
        drift = abs(float(prior_cfs) - cob_value) / cob_value * 100.0
        if drift > CFS_CROSS_CHECK_TOLERANCE_PCT:
            raise BudgetEstimatesError(
                "prior_year_cfs_mismatch",
                f"{prior} CFS reads {float(prior_cfs) / 1e12:.3f}T in this "
                f"book but COB publishes {cob_value / 1e12:.2f}T "
                f"({drift:.1f}% apart). Source: {receipt}",
            )
        checks.append(
            f"{prior} CFS {float(prior_cfs) / 1e12:.3f}T matches COB's "
            f"{cob_value / 1e12:.2f}T ({drift:.2f}% apart)"
        )
    elif prior in COB_PUBLISHED_CFS_KES:
        raise BudgetEstimatesError(
            "prior_year_cfs_missing",
            f"{prior} has a COB-published CFS to check against but this "
            f"book exposed no {prior} original-estimates column",
        )
    else:
        # No COB figure on file for the prior year. Say so; do not pretend
        # the strongest of the three checks ran.
        checks.append(
            f"prior-year CFS cross-check SKIPPED — no COB-published CFS "
            f"recorded for {prior}"
        )

    gross = total + cfs
    lo, hi = _PLAUSIBLE_GROSS_KES
    if not (lo <= float(gross) <= hi):
        raise BudgetEstimatesError(
            "gross_outside_plausible_band",
            f"{float(gross) / 1e12:.2f}T is outside the "
            f"[{lo / 1e12:.0f}T, {hi / 1e12:.0f}T] band",
        )

    return BudgetEstimates(
        fiscal_year=fiscal_year,
        voted_gross_kes=total,
        voted_current_kes=current,
        voted_capital_kes=capital,
        cfs_kes=cfs,
        debt_redemption_kes=(
            getattr(cfs_by_year, "redemption", {}) or {}
        ).get(fiscal_year),
        prior_fiscal_year=prior,
        prior_cfs_kes=prior_cfs,
        page_refs=dict(page_refs or {}),
        checks=checks,
    )


# ── PDF walk (thin shim over pdfplumber) ─────────────────────────────
def extract_budget_estimates(pdf_path, fiscal_year: str) -> BudgetEstimates:
    """Read ``fiscal_year``'s enacted gross budget from a PBB book.

    ``fiscal_year`` comes from the DISCOVERY url (which edition we chose to
    download), and the voted-summary page must agree with it — a book whose
    own header names a different year is a failed download, not a new budget.
    Raises :class:`BudgetEstimatesError` on every failure; never returns a
    figure it could not check.
    """
    import pdfplumber

    voted: Optional[Tuple[Decimal, Decimal, Decimal]] = None
    cfs_by_year: Dict[str, Decimal] = {}
    page_refs: Dict[str, int] = {}

    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages
        total_pages = len(pages)

        for index in range(min(FRONT_PAGES, total_pages)):
            text = pages[index].extract_text() or ""
            if _VOTED_TOTAL_ANCHOR not in text.lower():
                continue
            _assert_book_is_for(text, fiscal_year, page=index + 1)
            found = extract_voted_gross_from_text(text)
            if found:
                voted = found
                page_refs["voted_total"] = index + 1
                break

        start = max(0, total_pages - BACK_PAGES)
        for index in range(total_pages - 1, start - 1, -1):
            text = pages[index].extract_text() or ""
            parsed = parse_cfs_summary_from_text(text)
            if parsed:
                cfs_by_year = parsed
                page_refs["cfs_summary"] = index + 1
                break

    if voted is None:
        raise BudgetEstimatesError(
            "voted_total_not_found",
            f"no '{_VOTED_TOTAL_ANCHOR}' row in the first {FRONT_PAGES} pages",
        )
    if not cfs_by_year:
        raise BudgetEstimatesError(
            "cfs_summary_not_found",
            f"no Consolidated Fund Services summary in the last {BACK_PAGES} "
            f"pages",
        )

    return build_estimates(
        fiscal_year=fiscal_year,
        voted=voted,
        cfs_by_year=cfs_by_year,
        page_refs=page_refs,
    )


def _assert_book_is_for(text: str, fiscal_year: str, *, page: int) -> None:
    """The voted-summary header names its own fiscal year; it must match.

    Catches the failure mode that a stale cache, a redirect, or a discovery
    regression serves LAST year's book — which would otherwise publish last
    year's budget under this year's label.
    """
    labels = {
        f"FY {m.group(1)}/{m.group(2)[-2:]}" for m in _FY_LABEL_RE.finditer(text)
    }
    if not labels:
        # Not fatal — the figures still have to pass three identities — but a
        # summary page that names no fiscal year means the layout moved, and a
        # skipped check must never be silent.
        logger.warning(
            "Budget book page %d carries the '%s' row but names no fiscal "
            "year; the book-identity check did NOT run for %s",
            page,
            _VOTED_TOTAL_ANCHOR,
            fiscal_year,
        )
        return
    if fiscal_year not in labels:
        raise BudgetEstimatesError(
            "book_fiscal_year_mismatch",
            f"page {page} of the downloaded book names {sorted(labels)}, "
            f"but discovery said {fiscal_year}",
        )


__all__ = [
    "BudgetEstimates",
    "BudgetEstimatesError",
    "COB_PUBLISHED_CFS_KES",
    "build_estimates",
    "extract_budget_estimates",
    "extract_voted_gross_from_text",
    "numbers_in_line",
    "CfsSummary",
    "parse_cfs_summary_from_text",
    "parse_fy_columns",
]
