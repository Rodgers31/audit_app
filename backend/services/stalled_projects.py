"""What ``/counties/{id}/comprehensive`` may say about stalled projects.

The block used to be ``Entity.meta['stalled_projects']`` returned verbatim.
Until issue #230 that key held 25 invented records written nightly from
``seeding/real_data/stalled_projects.json``: no source document, a
``scraped_at`` older than the file itself, amounts paid that were exact
20/30/40/50/60% fractions of round contract sums, and ``OAG/NRB/2023/INF-012``
style references in a format the Auditor-General does not use.

So the rule here is evidence first. A row is published only if it names the
document it was read from, the page, the date the figures are "as of", and
who reported them. Anything else is withheld and counted, never shown and
never summed. When nothing survives the answer is ``count: None`` with a
reason, not ``count: 0``: zero stalled projects is a claim about a county,
and nobody has made it.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

#: Fields a row must carry to be published. Each one is something a reader
#: needs to go and check the figure: the document, the page in it, the date
#: the figures describe, and whose statement it is.
REQUIRED_EVIDENCE = ("source_url", "source_page", "as_of", "reported_by")


def _evidence_gap(row: Any) -> Optional[str]:
    """Why ``row`` may not be published, or ``None`` if it may."""
    if not isinstance(row, dict):
        return "not_a_record"
    url = row.get("source_url")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return "no_source_document"
    page = row.get("source_page")
    # bool is an int subclass; True is not page 1.
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        return "no_source_page"
    as_of = row.get("as_of")
    if not isinstance(as_of, str) or len(as_of) < 10:
        return "no_as_of_date"
    reported_by = row.get("reported_by")
    if not isinstance(reported_by, str) or not reported_by.strip():
        return "no_reporter"
    return None


def _stored_rows(stored: Any) -> Tuple[List[Any], Dict[str, Any]]:
    """Split the stored meta value into (rows, edition-level fields).

    Two shapes exist in the wild: the legacy bare list the fixture writer
    produced, and the dict the COB writer produces. Anything else is treated
    as no rows at all.
    """
    if isinstance(stored, list):
        return stored, {}
    if isinstance(stored, dict):
        rows = stored.get("rows")
        return (rows if isinstance(rows, list) else []), stored
    return [], {}


def _sum_known(rows: Iterable[dict], key: str) -> Optional[float]:
    """Sum ``key`` over rows that report it; ``None`` if no row does.

    A row whose figure is missing ("-" in COB's table) is left out of the sum
    rather than counted as 0 — and ``known`` in the response says how many
    rows the total covers, so a partial total never reads as a whole one.
    """
    values = [r.get(key) for r in rows]
    known = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return float(sum(known)) if known else None


def build_stalled_projects_block(stored: Any) -> Dict[str, Any]:
    """Return the ``stalled_projects`` block for one county."""
    rows, edition = _stored_rows(stored)
    published: List[dict] = []
    withheld: Dict[str, int] = {}
    for row in rows:
        gap = _evidence_gap(row)
        if gap is None:
            published.append(row)
        else:
            withheld[gap] = withheld.get(gap, 0) + 1

    if not published:
        return {
            "count": None,
            "total_contracted_value": None,
            "total_amount_paid": None,
            "projects": [],
            "reason": "no_evidence_backed_source",
            "withheld": {"count": sum(withheld.values()), "by_reason": withheld},
        }

    value_known = sum(
        1 for r in published if isinstance(r.get("estimated_value_kes"), (int, float))
    )
    paid_known = sum(
        1 for r in published if isinstance(r.get("amount_paid_kes"), (int, float))
    )
    return {
        "count": len(published),
        "total_contracted_value": _sum_known(published, "estimated_value_kes"),
        "total_contracted_value_rows": value_known,
        "total_amount_paid": _sum_known(published, "amount_paid_kes"),
        "total_amount_paid_rows": paid_known,
        "projects": published,
        "source": edition.get("source"),
        "reconciliation": edition.get("reconciliation"),
        "reason": None,
        "withheld": {"count": sum(withheld.values()), "by_reason": withheld},
    }


__all__ = ["REQUIRED_EVIDENCE", "build_stalled_projects_block"]
