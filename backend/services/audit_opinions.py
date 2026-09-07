"""Canonical audit opinions, and the gate on publishing an opinion facet.

THE TWO DEFECTS THIS MODULE EXISTS FOR
--------------------------------------
Production ``/api/v1/audit/summary`` published, across 2,312 findings::

    "findings_by_opinion": {"Unmodified Opinion": 182, "Unqualified Opinion": 9}

**1. Those are the same opinion counted twice.** ISA 700 (revised) renamed the
clean opinion from *Unqualified* to *Unmodified*; Kenya's OAG uses the new name
in the 2024/25 national report and the superseded one in the 2020/21 county
volumes. Rendered as a facet they became two chart bars and two filter options
for one category.

**2. Not one Qualified, Adverse or Disclaimer opinion appears in the whole
set** — and that is not what the source documents say. Measured against the
production database on 2026-09-06, the *same extraction rows* that produced
those 191 opinions carry a ``heading`` field reading:

    Basis for Qualified Opinion        408 findings
    Basis for Adverse Opinion          104 findings
    Basis for Disclaimer of Opinion     33 findings

545 findings sit under an explicit modified-opinion heading, and every one of
them reached ``audits.audit_opinion`` as NULL. The extractor recorded the
modification in ``heading`` and dropped it from ``opinion``
(``seeding/extractors/oag_blue_book.py``: ``_OPINION_RE`` only fires on a line
that is *exactly* "<Word> Opinion", and ``_HEADING_RE`` consumes the
"Basis for ..." line without setting the opinion it names).

So the facet is not merely sparse — 191 of 2,312 findings, 8.3% — it is
**biased in one direction**: every opinion it can publish is a clean one, while
the evidence for 545 modified ones sits unpublished in the same pipeline. A
reader seeing 100% clean opinions on Kenyan county audits would draw a
conclusion the Auditor-General's own reports contradict.

WHAT THIS MODULE DOES ABOUT IT
------------------------------
:func:`canonical_opinion` folds the superseded label onto the current one, so
one opinion is one category.

:func:`opinion_facet` then **withholds the whole facet** unless at least one
modified opinion survives. That is a fail-closed gate, not a filter: seed a
Qualified opinion and the facet publishes normally. It goes green the moment
the extractor stops dropping them — which is the repair, and it belongs in
``seeding/extractors/oag_blue_book.py``, not here.
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

#: The clean opinion, under its current ISA 700 (revised) name.
UNMODIFIED = "Unmodified Opinion"

#: The three modified opinions of ISA 705. Their absence is what the gate
#: below tests for: an opinion facet containing none of these has not been
#: shown to be complete.
QUALIFIED = "Qualified Opinion"
ADVERSE = "Adverse Opinion"
DISCLAIMER = "Disclaimer of Opinion"

MODIFIED_OPINIONS = (QUALIFIED, ADVERSE, DISCLAIMER)

#: Why the facet is not published. Stated once so the summary endpoint and the
#: trends endpoint cannot drift into describing the same hole differently.
INCOMPLETE_FACET_REASON = (
    "not published: the opinion facet contains no Qualified, Adverse or "
    "Disclaimer opinion. The extraction records a modified opinion in the "
    "finding's heading (Basis for Qualified/Adverse/Disclaimer of Opinion) but "
    "does not carry it into the opinion field, so a facet built from that "
    "field cannot be shown to be complete and is systematically flattering to "
    "the audited entities. An opinion mix is published again once modified "
    "opinions are extracted."
)


def _normalise(raw: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace — the shape we match."""
    return " ".join(re.sub(r"[^a-z ]+", " ", (raw or "").lower()).split())


def canonical_opinion(raw: Optional[str]) -> Optional[str]:
    """The canonical name for a stored ``audit_opinion``.

    Returns ``None`` for a null/blank value, and returns the input **unchanged**
    when it matches no known opinion — an unrecognised label must stay visible
    rather than be folded into an opinion it may not be.

    Matching is on the leading word of the normalised text, never a substring:
    ``"unqualified"`` contains ``"qualified"``, and an ``in`` test would fold
    the clean opinion onto the modified one — inverting the very bias this
    module exists to stop.
    """
    if raw is None:
        return None
    text = _normalise(raw)
    if not text:
        return None

    head = text.split(" ", 1)[0]
    if head in ("unmodified", "unqualified"):
        return UNMODIFIED
    if head == "qualified":
        return QUALIFIED
    if head == "adverse":
        return ADVERSE
    if head == "disclaimer":
        return DISCLAIMER
    return raw


def group_opinion_counts(counts: Dict[str, int]) -> Dict[str, int]:
    """Fold a ``{raw_opinion: count}`` facet onto canonical opinion names."""
    grouped: Dict[str, int] = {}
    for raw, count in counts.items():
        key = canonical_opinion(raw) or raw
        grouped[key] = grouped.get(key, 0) + count
    return grouped


def has_modified_opinion(counts: Dict[str, int]) -> bool:
    """Does this facet contain a Qualified, Adverse or Disclaimer opinion?

    A key present with a count of 0 counts as present: that is a real measured
    zero, and it is the difference between "the Auditor-General modified no
    opinion" and "nobody looked".
    """
    return any(name in counts for name in MODIFIED_OPINIONS)


def opinion_facet(
    raw_counts: Dict[str, int]
) -> Tuple[Optional[Dict[str, int]], Optional[str]]:
    """``(counts, reason)`` — the publishable opinion facet, or absence and why.

    ``counts is None`` means **not published**, and the caller must render it as
    absence rather than as an empty object. An empty ``{}`` would read as "no
    findings carried an opinion", which is a different claim from "the opinions
    we hold cannot be shown to be complete".

    An empty input is passed through as an empty facet rather than withheld:
    a dataset with no opinions at all has nothing to be flattering about, and
    withholding there would make the gate un-observable on an empty database.
    """
    if not raw_counts:
        return {}, None
    grouped = group_opinion_counts(raw_counts)
    if not has_modified_opinion(grouped):
        return None, INCOMPLETE_FACET_REASON
    return grouped, None


def opinion_facet_by_year(
    per_year: Dict[str, Dict[str, int]]
) -> Tuple[Optional[Dict[str, Dict[str, int]]], Optional[str]]:
    """The same gate as :func:`opinion_facet`, applied to a year-sliced facet.

    Judged on the **whole** facet, not year by year. A per-year test would
    publish whichever single year happened to contain one modified opinion and
    withhold the rest, which reads as "2023 was the bad year" — an artefact of
    the extraction, presented as a finding about the world.
    """
    if not per_year:
        return {}, None
    combined: Dict[str, int] = {}
    for counts in per_year.values():
        for raw, count in counts.items():
            combined[raw] = combined.get(raw, 0) + count
    _, reason = opinion_facet(combined)
    if reason is not None:
        return None, reason
    return {
        year: group_opinion_counts(counts) for year, counts in per_year.items()
    }, None
