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

Two voices, never mixed:

* **COB rows** — the county treasury's figures as reported to the
  Controller of Budget (``reported_by`` on every row).
* **OAG findings** — the Auditor-General's own words, with report,
  paragraph and page. Attached to a COB row only when the finding's heading
  shares distinctive name terms with it (``match.shared_terms`` says which);
  otherwise listed on their own. A match says "the Auditor-General's report
  discusses a project with a matching name", nothing stronger.
"""

from __future__ import annotations

import re
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


def _is_amount(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _sum_known(rows: Iterable[dict], key: str) -> Tuple[Optional[float], int]:
    """Sum ``key`` over rows that report it; ``None`` if no row does.

    A row whose figure is missing ("-" in COB's table) is left out of the sum
    rather than counted as 0 — and the row count beside the total says how
    many rows it covers, so a partial total never reads as a whole one.
    """
    known = [r.get(key) for r in rows if _is_amount(r.get(key))]
    return (float(sum(known)) if known else None), len(known)


# --------------------------------------------------------------------------
# OAG corroboration
# --------------------------------------------------------------------------

#: Heading language the Auditor-General uses for a project that did not
#: finish. Checked against the paragraph HEADING where there is one.
_STALLED_RE = re.compile(
    r"\b(stalled|abandon\w*|incomplete|uncompleted|unfinished|non-?completion|"
    r"delay(?:ed|s)?\s+in\s+(?:the\s+)?completion|delayed\s+completion|"
    r"delayed\s+(?:construction|implementation|project)|not\s+completed)\b",
    re.I,
)
_PROJECT_RE = re.compile(r"\b(project|construction|works|contract|building|rehabilitation|upgrading)\b", re.I)

#: Words every project name shares; matching on them would link anything.
_STOP = frozenset(
    """a an and at by for from in into of on or the to with within proposed
    construction constructing construct completion complete completed
    stalled project projects phase lot county government works work supply
    delivery installation equipping upgrading upgrade rehabilitation renovation
    building proposed new ward sub office offices block no i ii iii iv
    """.split()
)


#: Facility words: real content, but shared by half the projects in a
#: county. Two of them together linked Uasin Gishu's "Special Needs
#: Assessment, Training and Rehabilitation Centre, Chebolol" (COB FY2025/26)
#: to the Auditor-General's "Stalled Construction of Chebororwa Agricultural
#: Training Centre" (OAG FY2024/25 para 30) — different projects. A link now
#: needs at least one shared term that is not on this list: a place, a name.
_GENERIC = frozenset(
    """centre center training health hospital water business market school
    schools office dispensary road roads level facility facilities stadium
    unit house houses ward wards town township hall complex storey multi
    classroom classrooms ecde ecd latrine latrines borehole dam referral
    teaching vocational agricultural modern public general
    """.split()
)


def _terms(text: str) -> set:
    words = re.findall(r"[a-z][a-z'’]+", (text or "").lower().replace("- ", ""))
    return {w.strip("'’") for w in words if len(w) > 2 and w not in _STOP}


def stalled_oag_findings(audits: Iterable[Any], extracted: Dict[int, dict]) -> List[Dict[str, Any]]:
    """Published OAG findings about projects that did not finish.

    ``audits`` must already be publishable (``publishable_audit_criterion``)
    and display-grade; ``extracted`` maps ``extraction_id`` to
    ``extracted_json`` for the paragraph number and heading.
    """
    out: List[Dict[str, Any]] = []
    for a in audits:
        ext = extracted.get(getattr(a, "extraction_id", None) or -1) or {}
        prov = a.provenance[0] if isinstance(a.provenance, list) and a.provenance else {}
        prov = prov if isinstance(prov, dict) else {}
        title = ext.get("title") or prov.get("title")
        text = a.finding_text or ""
        haystack = title or text[:400]
        if not _STALLED_RE.search(haystack) or not _PROJECT_RE.search(title or text):
            continue
        doc = getattr(a, "source_document", None)
        url = getattr(doc, "url", None)
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        out.append(
            {
                "speaker": "Auditor-General",
                "report": getattr(doc, "title", None),
                "source_url": url,
                "page": a.page_ref,
                "paragraph": ext.get("paragraph_no") or prov.get("reference"),
                "fiscal_period": getattr(getattr(a, "period", None), "label", None),
                "audit_year": a.audit_year,
                "heading": title,
                "text": text,
                "audit_id": a.id,
            }
        )
    return out


def _link(rows: List[dict], findings: List[dict]) -> Tuple[Dict[int, List[dict]], List[dict]]:
    """Attach each finding to the COB row whose name it shares terms with.

    Two or more shared terms, at least one of them distinctive (not in
    ``_GENERIC``), covering at least 40% of the smaller name's terms. COB's
    "Construction and equipping of the theatre at Ainamoi Health Centre"
    (Kericho) and OAG's "Stalled Construction and Equipping of Theater at
    Ainamoi Health Centre" match on ainamoi/health/centre; two water projects
    in different villages share only "water" and do not.
    """
    linked: Dict[int, List[dict]] = {}
    unlinked: List[dict] = []
    row_terms = [_terms(r.get("project_name") or "") for r in rows]
    for f in findings:
        # The heading when there is one; otherwise the finding's opening
        # words, which is where OAG puts it (title and body are joined).
        f_terms = _terms(f.get("heading") or f.get("text", "")[:160])
        best: Optional[Tuple[float, int, List[str]]] = None
        for i, terms in enumerate(row_terms):
            shared = terms & f_terms
            if len(shared) < 2 or not terms or not (shared - _GENERIC):
                continue
            score = len(shared) / min(len(terms), len(f_terms) or 1)
            if score >= 0.4 and (best is None or score > best[0]):
                best = (score, i, sorted(shared))
        if best is None:
            unlinked.append(f)
        else:
            linked.setdefault(best[1], []).append(
                dict(f, match={"shared_terms": best[2], "score": round(best[0], 2)})
            )
    return linked, unlinked


# --------------------------------------------------------------------------
# The block
# --------------------------------------------------------------------------


def build_stalled_projects_block(
    stored: Any, oag_findings: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Return the ``stalled_projects`` block for one county."""
    rows, edition = _stored_rows(stored)
    published: List[dict] = []
    withheld: Dict[str, int] = {}
    for row in rows:
        gap = _evidence_gap(row)
        if gap is None:
            published.append(dict(row))
        else:
            withheld[gap] = withheld.get(gap, 0) + 1

    linked, oag_only = _link(published, list(oag_findings or []))
    for i, row in enumerate(published):
        row["oag_corroboration"] = linked.get(i, [])

    cob_words = {
        k: edition.get(k)
        for k in ("summary", "statement", "table_2_6")
        if edition.get(k)
    }
    base = {
        "source": edition.get("source"),
        "cob_statements": cob_words or None,
        "reconciliation": edition.get("reconciliation"),
        "withheld_fields": edition.get("withheld_fields") or [],
        "oag_findings": oag_only,
        "withheld": {"count": sum(withheld.values()), "by_reason": withheld},
    }

    if not published:
        if edition.get("tables"):
            reason = "table_unreadable"
        elif cob_words:
            reason = "no_table_in_edition"
        else:
            reason = "no_evidence_backed_source"
        return {
            "count": None,
            "total_contracted_value": None,
            "total_contracted_value_rows": 0,
            "total_amount_paid": None,
            "total_amount_paid_rows": 0,
            "projects": [],
            "reason": reason,
            **base,
        }

    value, value_rows = _sum_known(published, "estimated_value_kes")
    paid, paid_rows = _sum_known(published, "amount_paid_kes")
    return {
        "count": len(published),
        "total_contracted_value": value,
        "total_contracted_value_rows": value_rows,
        "total_amount_paid": paid,
        "total_amount_paid_rows": paid_rows,
        "projects": published,
        "reason": None,
        **base,
    }


__all__ = [
    "REQUIRED_EVIDENCE",
    "build_stalled_projects_block",
    "stalled_oag_findings",
]
