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
    # ``p\.?a\.?y\.?e`` covers both "PAYE" and the dotted "P.A.Y.E" KRA uses.
    ("PAYE", (r"\bpaye\b", r"p\.?a\.?y\.?e", r"pay[\s-]?as[\s-]?you[\s-]?earn")),
    ("Corporation Tax", (r"corporat(?:e|ion)\s+tax",)),
    ("VAT", (r"\bvat\b", r"value[\s-]?added\s+tax")),
    ("Excise Duty", (r"\bexcise\b",)),
    ("Customs & Import Duty", (r"customs", r"import\s+duty", r"border\s+control")),
)

# Sentence boundary: ". " / "! " / "? " before a capital, or a newline. Tuned
# NOT to fire on "Kshs. 560" (". 5" → digit) or "P.A.Y.E" (no following space),
# so confining a head's money search to its own sentence keeps the previous
# head's figure (or a "target of Kshs X" aside) from bleeding in.
_SENTENCE_BOUNDARY = re.compile(r"[.!?]\s+(?=[A-Z])|\n+")

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
    confidently found in ``text``.

    For each head, find its name anchor anywhere in the text, then take the
    money figure NEAREST that anchor within a window — so it works whether the
    figure precedes the name ("Kshs X Billion from P.A.Y.E") or follows it
    ("Domestic VAT ... Kshs X Billion"), and regardless of line breaks (KRA's
    HTML/PDF collapses sentences). Best-effort: returns ``{}`` / omits a head
    when nothing matches — callers MUST treat that as "keep the fixture", never
    as zero. The fetcher re-validates the result (bands + reconciliation) before
    any value may replace the fixture.
    """
    out: Dict[str, Decimal] = {}
    if not text:
        return out
    low = text.lower()
    for canonical, patterns in _TAX_HEADS:
        best_amount: Decimal | None = None
        best_dist: int | None = None
        for pattern in patterns:
            for anchor in re.finditer(pattern, low):
                a = anchor.start()
                lo, hi = _sentence_bounds(text, a)
                for money in _MONEY_RE.finditer(text[lo:hi]):
                    amount = _money_to_billion(money.group(1), money.group(2))
                    if amount is None or amount <= 0:
                        continue
                    dist = abs((lo + money.start()) - a)
                    if best_dist is None or dist < best_dist:
                        best_dist, best_amount = dist, amount
        if best_amount is not None:
            out[canonical] = best_amount
    return out


def _sentence_bounds(text: str, pos: int) -> tuple[int, int]:
    """Return ``(start, end)`` of the sentence containing ``pos`` so a head's
    money search can't cross into an adjacent sentence (the previous head's
    figure or a 'target of Kshs X' aside)."""
    # Scan the FULL text (not endpos=pos): the boundary's trailing lookahead
    # can't see the capital letter when it sits exactly at endpos, which would
    # miss the boundary immediately before the anchor.
    start = 0
    for m in _SENTENCE_BOUNDARY.finditer(text):
        if m.end() <= pos:
            start = m.end()
        else:
            break
    after = _SENTENCE_BOUNDARY.search(text, pos)
    end = after.start() if after else len(text)
    return start, end
