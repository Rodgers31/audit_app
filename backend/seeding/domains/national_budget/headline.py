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

# Lines that introduce the overall budget. Sub-totals ("development budget",
# "recurrent budget") are deliberately NOT anchors — we want the grand total.
_BUDGET_ANCHORS: tuple[str, ...] = (
    "approved budget",
    "gross estimates",
    "total budget",
    "overall budget",
    "total approved budget",
    "annual budget",
    "total expenditure",
)

# Lines that introduce the total revenue figure. Deliberately revenue-specific
# so we never pick up a budget/expenditure number by mistake.
_REVENUE_ANCHORS: tuple[str, ...] = (
    "total revenue",
    "ordinary revenue",
    "revenue collected",
    "actual revenue",
    "revenue performance",
    "total receipts",
)

# "Kshs 4,292.0 billion" / "KSh 4.29 trillion" / "KES 4,291.9 bn"
_MONEY_RE = re.compile(
    r"(?:kshs?|ksh|kes)\.?\s*([\d,]+(?:\.\d+)?)\s*(trillion|billion|tn|bn)\b",
    re.IGNORECASE,
)


def _money_to_billion(num_str: str, unit: str) -> Optional[Decimal]:
    try:
        val = Decimal(num_str.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None
    u = unit.lower()
    if u in ("trillion", "tn"):
        return val * Decimal(1000)
    return val  # already billions


def _extract_anchored_max_billion(text: str, anchors: tuple[str, ...]) -> Optional[Decimal]:
    """Scan only lines carrying one of ``anchors``, collect the money figures on
    them, and return the LARGEST (the grand total dominates any anchored
    sub-figure). ``None`` when nothing matches — callers MUST treat ``None`` as
    "keep the last-known value", never as zero."""
    if not text:
        return None
    candidates: list[Decimal] = []
    for line in text.splitlines():
        low = line.lower()
        if not any(anchor in low for anchor in anchors):
            continue
        for m in _MONEY_RE.finditer(line):
            b = _money_to_billion(m.group(1), m.group(2))
            if b is not None and b > 0:
                candidates.append(b)
    return max(candidates) if candidates else None


def extract_overall_budget_billion_from_text(text: str) -> Optional[Decimal]:
    """Best-effort OVERALL approved budget (KSh billion) from report text."""
    return _extract_anchored_max_billion(text, _BUDGET_ANCHORS)


def extract_total_revenue_billion_from_text(text: str) -> Optional[Decimal]:
    """Best-effort TOTAL revenue (KSh billion) from report text. Revenue-specific
    anchors ensure a budget/expenditure figure is never mistaken for revenue."""
    return _extract_anchored_max_billion(text, _REVENUE_ANCHORS)


def extract_cob_headlines(pdf_path) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """Open a COB NG-BIRR PDF once and extract ``(overall_budget, total_revenue)``
    in KSh billion. Reads only the first pages (the summary lives up front). Any
    failure degrades to ``(None, None)`` (keep last-known); never raises.
    """
    try:
        import pdfplumber

        text_parts: list[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:8]:
                text_parts.append(page.extract_text() or "")
        text = "\n".join(text_parts)
        return (
            extract_overall_budget_billion_from_text(text),
            extract_total_revenue_billion_from_text(text),
        )
    except Exception as exc:  # pragma: no cover - defensive shim
        logger.warning("COB headline extraction failed: %s", exc)
        return None, None
