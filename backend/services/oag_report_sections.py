"""Canonical names for the Auditor-General's report sections.

The OAG's reports are structured in three standing sub-reports, and every
finding sits under one of them:

  1. Report on the Financial Statements
  2. Report on Lawfulness and Effectiveness in the Use of Public Resources
  3. Report on Effectiveness of Internal Controls, Risk Management and
     Governance

The blue-book extractor writes whatever heading text it captured into
``audits.query_type``, and that text arrives truncated at different points and
cased differently from page to page. Production currently holds twelve
variants of those three sections — differing only by case, a trailing comma or
full stop, "in the Use of" versus "in Use of", and where the line happened to
be cut — plus one raw enum, ``financial_audit``, that leaked from an earlier
loader.

Rendered as a filter facet, that is twelve near-identical options a reader
cannot choose between, and a bar chart with twelve bars where there are three
categories (credibility audit F39).

This maps the variants onto the canonical section names for display and
filtering. It does NOT rewrite stored data: ``audits.query_type`` keeps
whatever the extractor captured, so the mapping can be corrected without a
migration, and a variant nobody anticipated falls through to its own name
rather than being silently folded into the wrong section.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional

FINANCIAL_STATEMENTS = "Report on the Financial Statements"
LAWFULNESS = "Report on Lawfulness and Effectiveness in the Use of Public Resources"
INTERNAL_CONTROLS = (
    "Report on Effectiveness of Internal Controls, Risk Management and Governance"
)

CANONICAL_SECTIONS = (FINANCIAL_STATEMENTS, LAWFULNESS, INTERNAL_CONTROLS)


def _normalise(raw: str) -> str:
    """Lowercase, collapse punctuation and whitespace — the shape we match on."""
    return re.sub(r"[^a-z ]+", " ", (raw or "").lower()).strip()


def canonical_section(raw: Optional[str]) -> Optional[str]:
    """The canonical OAG section name for a stored ``query_type``.

    Returns ``None`` for a null/blank value, and returns the input unchanged
    when it matches no known section — an unrecognised heading must stay
    visible rather than be absorbed into a section it may not belong to.
    """
    if raw is None:
        return None
    text = _normalise(raw)
    if not text:
        return None

    # The raw enum that leaked from an earlier loader. It carries no section
    # information beyond "this is a financial audit".
    if text == "financial audit":
        return FINANCIAL_STATEMENTS

    # Order matters: "internal controls" is the most specific marker, and the
    # lawfulness heading sometimes continues "... and Report on Effectiveness
    # of Internal Controls", so test the distinguishing phrase of each section
    # against the START of the heading, not anywhere in it.
    if text.startswith("report on effectiveness of internal controls") or text.startswith(
        "report on the effectiveness of internal controls"
    ):
        return INTERNAL_CONTROLS
    if text.startswith("report on lawfulness"):
        return LAWFULNESS
    if text.startswith("report on the financial statements") or text.startswith(
        "report on financial statements"
    ):
        return FINANCIAL_STATEMENTS
    return raw


def group_counts(counts: Dict[str, int]) -> Dict[str, int]:
    """Fold a ``{raw_query_type: count}`` facet onto canonical sections."""
    grouped: Dict[str, int] = {}
    for raw, count in counts.items():
        key = canonical_section(raw) or raw
        grouped[key] = grouped.get(key, 0) + count
    return grouped


def raw_variants_for(section: str, known: Iterable[str]) -> List[str]:
    """Every stored ``query_type`` that belongs to ``section``.

    Used to turn a canonical filter value back into the set of raw values a
    SQL ``IN`` clause needs. An exact raw value passed straight through still
    matches itself, so existing links keep working.
    """
    matches = [raw for raw in known if canonical_section(raw) == section]
    if not matches and section in known:
        return [section]
    return matches
