"""Best-effort extraction of KRA per-tax-head revenue from report/press text.

KRA publishes the FY revenue performance (PAYE, VAT, Corporation, Excise,
Customs) as press releases / PDFs whose exact URL and layout change each
release. This module pulls the per-head figures from that text so the
revenue_by_source breakdown can move off the fixture.

It is BEST-EFFORT and conservative: it returns only the heads it confidently
finds, and the caller (revenue_by_source fetcher) re-validates the result
against ``trust_guards.check_revenue_breakdown`` (per-head bands + sum
reconciliation to the fixture total) before any value may replace the fixture
— so a garbled/partial parse can never ship. Pure-text extraction is fully
unit-tested; the live discovery/fetch is opt-in via ``settings.kra_revenue_url``.

Canonical ``revenue_type`` strings match the fixture so the overlay can map
parsed heads onto existing rows.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Dict

# Canonical revenue_type (matches the fixture) → anchor patterns (regex,
# matched against lowercased line text). Order matters: the first head whose
# anchor matches a money-bearing line claims that figure.
_TAX_HEADS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("PAYE", (r"\bpaye\b", r"pay[\s-]?as[\s-]?you[\s-]?earn")),
    ("Corporation Tax", (r"corporat(?:e|ion)\s+tax",)),
    ("VAT", (r"\bvat\b", r"value[\s-]?added\s+tax")),
    ("Excise Duty", (r"\bexcise\b",)),
    ("Customs & Import Duty", (r"customs", r"import\s+duty", r"border\s+control")),
)

_MONEY_RE = re.compile(
    r"(?:kshs?|ksh|kes)\.?\s*([\d,]+(?:\.\d+)?)\s*(trillion|billion|tn|bn)\b",
    re.IGNORECASE,
)

# "FY 2024/25", "FY2024/2025", "2024/25 financial year"
_FY_RE = re.compile(r"(?:FY\s*)?(20\d{2})\s*[/-]\s*(20\d{2}|\d{2})", re.IGNORECASE)


def extract_kra_fiscal_year(text: str) -> str | None:
    """Return the report's fiscal year in canonical ``FY YYYY/YY`` form, or
    ``None`` if not found. Used to overlay KRA actuals onto the right year."""
    if not text:
        return None
    m = _FY_RE.search(text)
    if not m:
        return None
    start, end = m.group(1), m.group(2)
    return f"FY {start}/{end[-2:]}"


def _money_to_billion(num_str: str, unit: str) -> Decimal | None:
    try:
        val = Decimal(num_str.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None
    return val * Decimal(1000) if unit.lower() in ("trillion", "tn") else val


def extract_kra_revenue_by_type_from_text(text: str) -> Dict[str, Decimal]:
    """Return ``{canonical_revenue_type: amount_billion_kes}`` for the heads
    confidently found in ``text``. Best-effort: scans each line for a tax-head
    anchor plus a money figure; the first money figure on the first matching
    line wins per head. Returns ``{}`` when nothing matches — callers MUST
    treat ``{}`` / a missing head as "keep the fixture", never as zero.
    """
    out: Dict[str, Decimal] = {}
    if not text:
        return out
    for line in text.splitlines():
        m = _MONEY_RE.search(line)
        if not m:
            continue
        amount = _money_to_billion(m.group(1), m.group(2))
        if amount is None or amount <= 0:
            continue
        low = line.lower()
        for canonical, patterns in _TAX_HEADS:
            if canonical in out:
                continue
            if any(re.search(p, low) for p in patterns):
                out[canonical] = amount
                break
    return out
