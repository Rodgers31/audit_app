"""Extract the OVERALL (headline) approved budget from a COB NG-BIRR report.

The sectoral parser (``pdf_parser.NgBirrSectoralParser``) reliably reads
Tables 2.5/2.6, but those sum to the MDA voted estimates only — they exclude
Consolidated Fund Services (debt service, pensions, constitutional salaries),
so they don't give the headline total budget the dashboard shows.

This module pulls that headline figure from the report's summary prose/text
(executive summary / overall-performance section). It is BEST-EFFORT and
conservative: it returns ``None`` unless a budget-anchored money figure is
found, and the caller (``fiscal_summary`` overlay) re-validates the result
against the plausibility gate AND a reconciliation tolerance before it may
replace the last-known value — so a wrong grab can never ship.

Pure-text extraction (``..._from_text``) is fully unit-tested; the PDF wrapper
is a thin shim over pdfplumber. Anchors follow the documented NG-BIRR phrasing
and should be confirmed against a live report on first run.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Optional

logger = logging.getLogger("seeding.national_budget.headline")

# ── Anchors, confirmed against a live report ─────────────────────────
# The previous anchors ("approved budget", "gross estimates", "total
# budget", ...) were written from *documented* NG-BIRR phrasing and the
# docstring noted they "should be confirmed against a live report on first
# run". That confirmation never happened, because the download timed out on
# every run and the domain fell back to a fixture before reaching the
# parser. Confirmed on 2026-08-29 against the FY2025/26 nine-month report:
#
#   "The National Government's original gross budget for FY 2025/26 amounts
#    to Kshs. 4.69 trillion, compared to Kshs.4.37 trillion in the FY
#    2024/25 after Supplementary III Estimates."
#   "... 72 per cent of the original net estimates of Kshs.4.43 trillion"
#
# NONE of the old anchors appear in that text, so the extractor could not
# have matched even with a working download.
#
# Each basis is captured SEPARATELY. Gross (4.69T), net (4.43T) and the
# Budget Policy Statement figure the fixture carries (4.19T) are three
# different, legitimate measures of "the budget"; collapsing them into one
# field is the "two systems for the same fact" defect this codebase already
# suffers from elsewhere (AUDIT_FINDINGS P3).
# Most specific first: the scanner returns the first anchor that yields a
# figure, so "original gross budget" must win over the looser "gross budget".
# The trailing group is the previously-documented phrasing — kept because a
# differently-worded edition may still use it, and dropping it would narrow
# the parser to exactly one report's wording.
_GROSS_BUDGET_ANCHORS: tuple[str, ...] = (
    "original gross budget",
    "gross national budget",
    "gross budget",
    "total approved budget",
    "approved budget",
    "gross estimates",
    "total budget",
    "overall budget",
    "annual budget",
)
_NET_BUDGET_ANCHORS: tuple[str, ...] = (
    "original net estimates",
    "net estimates",
)

# "Kshs 4,292.0 billion" / "KSh 4.29 trillion" / "Kshs.4.43 trillion"
_MONEY_RE = re.compile(
    r"(?:kshs?|ksh|kes)\.?\s*([\d,]+(?:\.\d+)?)\s*(trillion|billion|tn|bn)\b",
    re.IGNORECASE,
)

# How far after an anchor a figure may sit and still belong to it.
_ANCHOR_WINDOW_CHARS = 160

# Upper bound on pages scanned for the summary. The report is 418 pages;
# the summary has always been well inside the front matter.
_MAX_SUMMARY_PAGES = 40


def _money_to_billion(num_str: str, unit: str) -> Optional[Decimal]:
    try:
        val = Decimal(num_str.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None
    u = unit.lower()
    if u in ("trillion", "tn"):
        return val * Decimal(1000)
    return val  # already billions


def unwrap(text: str) -> str:
    """Join PDF-wrapped lines so an anchor and its figure share a string.

    The second reason extraction produced nothing: the report wraps prose
    mid-sentence, and the old scanner iterated ``splitlines()``. In the live
    report the word "receipts" sits on the line ABOVE its money figure, so
    no single line ever contained both anchor and number. De-hyphenates
    across the break ("allo-\ncation" -> "allocation") before joining.
    """
    if not text:
        return ""
    dehyphenated = re.sub(r"-\s*\n\s*", "", text)
    return re.sub(r"\s*\n\s*", " ", dehyphenated)


def _first_figure_after_anchor(
    text: str, anchors: tuple[str, ...]
) -> Optional[Decimal]:
    """First money figure following an anchor, in unwrapped text.

    FIRST, not largest: the report routinely continues "..., compared to
    Kshs.4.37 trillion in the FY 2024/25", so taking a maximum over the
    window can return the PRIOR YEAR's figure. Reading the first figure
    after the anchor matches how the sentence actually reads.
    """
    if not text:
        return None
    haystack = unwrap(text)
    low = haystack.lower()
    for anchor in anchors:
        pos = low.find(anchor)
        while pos != -1:
            window = haystack[pos : pos + _ANCHOR_WINDOW_CHARS]
            match = _MONEY_RE.search(window)
            if match:
                value = _money_to_billion(match.group(1), match.group(2))
                if value is not None and value > 0:
                    return value
            pos = low.find(anchor, pos + 1)
    return None


def extract_budget_bases_from_text(text: str) -> dict:
    """``{"gross": Decimal|None, "net": Decimal|None}`` in KSh billion.

    Returned separately and labelled so a caller can never promote one
    basis onto a field defined as another without saying so.
    """
    return {
        "gross": _first_figure_after_anchor(text, _GROSS_BUDGET_ANCHORS),
        "net": _first_figure_after_anchor(text, _NET_BUDGET_ANCHORS),
    }


def extract_overall_budget_billion_from_text(text: str) -> Optional[Decimal]:
    """OVERALL (gross) approved budget in KSh billion, or None.

    Gross is returned because it is the report's own headline measure. It is
    NOT interchangeable with the net estimates or with the Budget Policy
    Statement figure — see ``extract_budget_bases_from_text``.
    """
    return extract_budget_bases_from_text(text)["gross"]


_REVENUE_ANCHORS: tuple[str, ...] = (
    "total revenue",
    "ordinary revenue",
    "revenue collected",
    "actual revenue",
    "revenue performance",
    "total receipts",
)


def extract_total_revenue_billion_from_text(text: str) -> Optional[Decimal]:
    """TOTAL revenue in KSh billion, or None. Revenue-specific anchors keep a
    budget/expenditure figure from ever being mistaken for revenue.

    NOTE: extracting is not the same as publishing. A quarterly NG-BIRR
    reports CUMULATIVE period actuals, while
    ``fiscal_summaries.total_revenue`` is ANNUAL — so the overlay refuses to
    promote this figure for a quarterly report (see
    ``_overlay_live_revenue_headline``). The separation is deliberate: this
    stays a general, testable text utility, and the period judgement lives
    with the code that knows which document it read.
    """
    return _first_figure_after_anchor(text, _REVENUE_ANCHORS)


def extract_cob_headlines(pdf_path) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """Open a COB NG-BIRR PDF once and extract ``(overall_budget, total_revenue)``
    in KSh billion. Reads only the first pages (the summary lives up front). Any
    failure degrades to ``(None, None)`` (keep last-known); never raises.
    """
    try:
        import pdfplumber

        # Scan until the summary is found, not a fixed slice. The previous
        # ``pages[:8]`` never reached it: in the FY2025/26 report the
        # Executive Summary is on page 23, behind the cover, contents,
        # foreword and abbreviations. That alone guaranteed (None, None)
        # regardless of anchors — the third of three independent causes.
        text_parts: list[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:_MAX_SUMMARY_PAGES]:
                text_parts.append(page.extract_text() or "")
                joined = "\n".join(text_parts)
                if extract_budget_bases_from_text(joined)["gross"] is not None:
                    break  # found it; do not read a 418-page report
        text = "\n".join(text_parts)
        return (
            extract_overall_budget_billion_from_text(text),
            extract_total_revenue_billion_from_text(text),
        )
    except Exception as exc:  # pragma: no cover - defensive shim
        logger.warning("COB headline extraction failed: %s", exc)
        return None, None
