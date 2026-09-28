"""Audit headline figures derived from extracted OAG findings (issue #233).

Everything here is computed from what the Blue Book extractor already stored —
``extractions.extracted_json`` joined to the publishable ``audits`` row it
produced — and every figure carries the page it came from. It replaces
``backend/data/reference/oag_national_audit_data.json``, a hand-written file
whose opinion summary cited only the OAG homepage and was withheld on every
request.

Three rules, each learnt the hard way:

1. **A section heading is evidence of an opinion; its absence is not.** The
   Auditor-General sets out every modified opinion under "Basis for Qualified
   Opinion", "Basis for Adverse Opinion" or "Basis for Disclaimer of Opinion".
   Those headings are matched exactly, never by ``"qualified" in text`` — that
   files "Unqualified Opinion" (the old name for a clean one) as modified.
   The extractor records NO heading at all past roughly pdf page 400 of the
   FY2024/25 report (121 of the 324 findings there carry none), so every count
   here is a floor, published beside the number of votes it could be read for.

2. **A vote is not one audit.** A State Department's vote groups its own
   accounts and several donor-funded projects, each audited and opined on
   separately, and the extraction does not name the sub-report's auditee. So a
   vote is reported as having "at least one" report under a given modified
   opinion, and no vote is ever called clean: an "Unmodified Opinion" line on
   one project says nothing about the next.

3. **Matched on the Auditor-General's words, not ours.** Recurring issues are
   findings the report itself titles "Unresolved Prior Year Matters"; the
   unaccounted-funds list is findings it titles "Unaccounted …" or
   "Loss of Funds". Nothing is inferred from ``query_type``, which holds the
   report section, not a class of irregularity.

4. **A table row is not a finding.** Each vote's "Unresolved Prior Year
   Matters" paragraph lists last year's issues in a numbered table
   ("1. Inaccuracies in Wages …", "2. Long Outstanding Retention Fees", …). The
   extractor reads each row as a numbered finding with no text under it: 304 of
   the 813 FY2024/25 rows on the 2026-09-26 production clone. They are excluded
   here by their shape — no body AND a number already passed by the report's
   running paragraph sequence (rows 1-6 printed between paragraphs 1692 and
   1693). A real finding whose body was lost keeps its place in the sequence
   and is kept (p.39, paragraph 52, the one such row).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import or_

from models import Audit, Entity, EntityType, Extraction, FiscalPeriod, SourceDocument
from services.publication_gate import publishable_audit_criterion
from services.audit_citations import (
    audited_institution,
    extraction_json_type,
    page_number as _page_number,
    report_page_url as page_url,
    string_extraction_payloads,
)

#: Most severe first — the order a reader should meet them in.
MODIFIED_OPINIONS = ("Adverse", "Disclaimer", "Qualified")

_MODIFIED_BASIS_RE = re.compile(
    r"^basis\s+for\s+(?:(qualified|adverse)\s+opinion|(disclaimer)\s+of\s+opinion)$",
    re.I,
)
_UNMODIFIED_LABEL_RE = re.compile(r"^(?:unmodified|unqualified)\s+opinion$", re.I)
_UNRESOLVED_PRIOR_RE = re.compile(
    r"^unresolved\s+prior\s+years?(?:['’]s?)?\s+(?:audit\s+)?(?:matters?|issues?)\b",
    re.I,
)
#: The Auditor-General's own words for money or assets not accounted for.
#: Deliberately narrow — "Unsupported" and "Irregular" describe documentation
#: and procedure, not money that cannot be found.
UNACCOUNTED_TITLE_RE = re.compile(r"^unaccounted\b|\bloss\s+of\s+funds\b", re.I)

_WS = re.compile(r"\s+")


def _norm(value: Any) -> str:
    return _WS.sub(" ", str(value or "")).strip()


def modified_opinion_from_heading(heading: Any) -> Optional[str]:
    """``"Basis for Qualified Opinion"`` → ``"Qualified"``; anything else → None."""
    m = _MODIFIED_BASIS_RE.match(_norm(heading))
    if not m:
        return None
    return (m.group(1) or m.group(2)).capitalize()


def is_unmodified_label(label: Any) -> bool:
    """True for the extractor's "Unmodified Opinion" / "Unqualified Opinion"."""
    return bool(_UNMODIFIED_LABEL_RE.match(_norm(label)))


def is_unresolved_prior_year(title: Any) -> bool:
    return bool(_UNRESOLVED_PRIOR_RE.match(_norm(title)))


def is_unaccounted_title(title: Any) -> bool:
    return bool(UNACCOUNTED_TITLE_RE.search(_norm(title)))



def _payload(extraction: Optional[Extraction]) -> Dict[str, Any]:
    raw = extraction.extracted_json if extraction is not None else None
    if isinstance(raw, str):  # SQLite stores JSONB as TEXT
        import json

        try:
            raw = json.loads(raw)
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


def table_row_extraction_ids(db, source_document_ids: Iterable[int]) -> set:
    """Extraction ids that are rows of a numbered table, not findings.

    See rule 4 in the module docstring. Judged per document over EVERY
    extraction of it (publishable or not), in page order, because the running
    paragraph sequence is a property of the whole report.
    """
    out: set = set()
    doc_ids = set(source_document_ids)
    if not doc_ids:
        return out
    payload_type = extraction_json_type(
        Extraction.extracted_json, db.get_bind().dialect.name
    )
    fields = (
        db.query(
            Extraction.id.label("extraction_id"),
            Extraction.source_document_id,
            Extraction.page_number,
            Extraction.extracted_json["pdf_page"].label("pdf_page"),
            Extraction.extracted_json["paragraph_no"].label("paragraph_no"),
            Extraction.extracted_json["finding_text"].label("finding_text"),
            Extraction.extracted_json["title"].label("title"),
            payload_type.label("extraction_payload_type"),
        )
        .filter(Extraction.source_document_id.in_(doc_ids))
        .all()
    )
    string_payloads = string_extraction_payloads(db, fields)
    rows_by_document = defaultdict(list)
    for ext in fields:
        j = string_payloads.get(ext.extraction_id)
        if j is None:
            j = {
                "pdf_page": ext.pdf_page,
                "paragraph_no": ext.paragraph_no,
                "finding_text": ext.finding_text,
                "title": ext.title,
            }
        try:
            page = int(j.get("pdf_page") or ext.page_number or 0)
        except (TypeError, ValueError):
            page = 0
        rows_by_document[ext.source_document_id].append((page, ext.extraction_id, j))

    for rows in rows_by_document.values():
        rows.sort(key=lambda r: (r[0], r[1]))
        running = 0
        for _page, ext_id, j in rows:
            try:
                number = int(j.get("paragraph_no"))
            except (TypeError, ValueError):
                number = None
            if _norm(j.get("finding_text")) != _norm(j.get("title")):
                if number is not None:
                    running = max(running, number)
                continue
            if number is not None and number < running:
                out.add(ext_id)
    return out


def _first(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """The row a reader should open first: the lowest page."""
    return min(rows, key=lambda r: (_page_number(r["page_ref"]) or 10**9, r["id"]))


def derive_federal_headline(
    db, *, source_document_id: int, entity_types: Iterable[EntityType]
) -> Optional[Dict[str, Any]]:
    """Opinion, recurring-issue and emphasis counts for ONE national report.

    Scoped to a single source document on purpose: an opinion belongs to a
    report, and counting FY2022/23 and FY2024/25 qualifications together
    would describe no report at all.

    Returns None when the document has no publishable, extraction-backed
    finding — there is nothing to derive from, and the caller must say so
    rather than render zeros.
    """
    doc = db.get(SourceDocument, source_document_id)
    rows = (
        db.query(Audit, Entity.canonical_name, Extraction)
        .join(Entity, Audit.entity_id == Entity.id)
        .join(Extraction, Audit.extraction_id == Extraction.id)
        .filter(publishable_audit_criterion())
        .filter(Audit.source_document_id == source_document_id)
        .filter(Entity.type.in_(list(entity_types)))
        .all()
    )
    if doc is None or not rows:
        return None

    table_rows = table_row_extraction_ids(db, [source_document_id])
    excluded = sum(1 for _a, _n, ext in rows if ext.id in table_rows)
    rows = [r for r in rows if r[2].id not in table_rows]
    if not rows:
        return None

    findings: List[Dict[str, Any]] = []
    for audit, entity_name, extraction in rows:
        j = _payload(extraction)
        findings.append(
            {
                "id": audit.id,
                "entity_id": audit.entity_id,
                "entity": entity_name,
                "page_ref": audit.page_ref,
                "title": _norm(j.get("title")),
                "heading": _norm(j.get("heading")),
                "opinion_label": _norm(j.get("opinion")),
            }
        )

    by_entity: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for f in findings:
        by_entity[f["entity_id"]].append(f)

    # --- opinions ---------------------------------------------------------
    entity_opinions: List[Dict[str, Any]] = []
    read = 0
    for entity_id, rows_e in by_entity.items():
        modified: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        unmodified_seen = False
        for f in rows_e:
            op = modified_opinion_from_heading(f["heading"])
            if op:
                modified[op].append(f)
            elif is_unmodified_label(f["opinion_label"]):
                unmodified_seen = True
        if modified or unmodified_seen:
            read += 1
        for op in MODIFIED_OPINIONS:
            if op not in modified:
                continue
            first = _first(modified[op])
            entity_opinions.append(
                {
                    "entity": first["entity"],
                    "opinion": op,
                    "findings": len(modified[op]),
                    "page_ref": first["page_ref"],
                    "source_url": page_url(doc.url, first["page_ref"]),
                }
            )

    rank = {op: i for i, op in enumerate(MODIFIED_OPINIONS)}
    entity_opinions.sort(
        key=lambda e: (rank[e["opinion"]], _page_number(e["page_ref"]) or 10**9)
    )
    modified_totals = []
    for op in MODIFIED_OPINIONS:
        hits = [e for e in entity_opinions if e["opinion"] == op]
        if hits:  # a category nobody found is absent, never a 0
            modified_totals.append(
                {
                    "opinion": op,
                    "entities": len(hits),
                    "findings": sum(e["findings"] for e in hits),
                }
            )

    # --- recurring: the report's own "Unresolved Prior Year Matters" ------
    unresolved = [f for f in findings if is_unresolved_prior_year(f["title"])]
    recurring = None
    if unresolved:
        first = _first(unresolved)
        recurring = {
            "entities": len({f["entity_id"] for f in unresolved}),
            "findings": len(unresolved),
            "page_ref": first["page_ref"],
            "source_url": page_url(doc.url, first["page_ref"]),
        }

    # --- emphasis of matter ----------------------------------------------
    emphasis_rows = [f for f in findings if f["heading"].lower() == "emphasis of matter"]
    emphasis = None
    if emphasis_rows:
        titles = Counter(f["title"] for f in emphasis_rows if f["title"])
        top_title, top_count = titles.most_common(1)[0] if titles else (None, 0)
        top_first = _first([f for f in emphasis_rows if f["title"] == top_title]) if top_title else None
        emphasis = {
            "entities": len({f["entity_id"] for f in emphasis_rows}),
            "findings": len(emphasis_rows),
            "most_common_title": top_title,
            "most_common_findings": top_count or None,
            "page_ref": top_first["page_ref"] if top_first else None,
            "source_url": page_url(doc.url, top_first["page_ref"]) if top_first else None,
        }

    return {
        "basis": "extracted_section_headings",
        "source_document": {"id": doc.id, "title": doc.title, "url": doc.url},
        "entities_with_findings": len(by_entity),
        # Rows of the unresolved-prior-year tables, not counted (rule 4).
        "excluded_table_rows": excluded,
        # The denominator every opinion count must be read against.
        "entities_opinion_read": read,
        "modified_opinions": modified_totals,
        "entities": entity_opinions,
        "recurring_prior_year": recurring,
        "emphasis_of_matter": emphasis,
    }


def derive_unaccounted_cases(
    db, *, entity_ids: Optional[Iterable[int]] = None
) -> Dict[str, Any]:
    """Findings the Auditor-General titled "Unaccounted …" or "Loss of Funds".

    Publishable rows only. Unpublishable rows that match are counted under
    ``withheld`` by the gate's own ``quarantine_reason``, never dropped
    silently. No money total is computed: the ``amount`` column holds the
    paragraph's only KES figure when there is exactly one, which is often the
    balance under discussion rather than the sum unaccounted for.
    """
    q = (
        db.query(
            Audit.id.label("audit_id"),
            Audit.finding_text,
            Audit.quarantine_reason,
            Audit.page_ref,
            Entity.id.label("entity_id"),
            Entity.canonical_name,
            Entity.slug,
            Entity.type.label("entity_type"),
            Extraction.id.label("extraction_id"),
            Extraction.extracted_json["title"].label("extracted_title"),
            Extraction.extracted_json["finding_text"].label("extracted_finding_text"),
            Extraction.extracted_json["heading"].label("extracted_heading"),
            Extraction.extracted_json["entity_name"].label("extracted_entity_name"),
            Extraction.extracted_json["auditee"].label("extracted_auditee"),
            Extraction.extracted_json["volume_kind"].label("extracted_volume_kind"),
            extraction_json_type(
                Extraction.extracted_json, db.get_bind().dialect.name
            ).label("extraction_payload_type"),
            SourceDocument.id.label("document_id"),
            SourceDocument.title.label("document_title"),
            SourceDocument.publisher.label("document_publisher"),
            SourceDocument.url.label("document_url"),
            SourceDocument.meta["extraction_stats"].label("extraction_stats"),
            FiscalPeriod.label.label("period_label"),
        )
        .join(Entity, Audit.entity_id == Entity.id)
        .join(Extraction, Audit.extraction_id == Extraction.id)
        .join(SourceDocument, Audit.source_document_id == SourceDocument.id)
        .outerjoin(FiscalPeriod, Audit.period_id == FiscalPeriod.id)
        # Cheap SQL prefilter; the title regex below is the real test.
        .filter(
            or_(
                Audit.finding_text.ilike("%unaccounted%"),
                Audit.finding_text.ilike("%loss of funds%"),
            )
        )
    )
    if entity_ids is not None:
        q = q.filter(Audit.entity_id.in_(list(entity_ids)))

    matched = []
    rows = q.all()
    string_payloads = string_extraction_payloads(db, rows)
    for row in rows:
        payload = string_payloads.get(row.extraction_id)
        if payload is None:
            payload = {
                "title": row.extracted_title,
                "finding_text": row.extracted_finding_text,
                "heading": row.extracted_heading,
                "entity_name": row.extracted_entity_name,
                "auditee": row.extracted_auditee,
                "volume_kind": row.extracted_volume_kind,
            }
        title = _norm(payload.get("title"))
        if is_unaccounted_title(title):
            matched.append((row, payload, title))

    # Only a finding with no text under its title can be a table row, so only
    # their documents are scanned — a county page must not walk a whole
    # 6,000-finding volume to rule out a case that has a body.
    bodyless = [
        m for m in matched
        if _norm(m[1].get("finding_text")) == m[2]
    ]
    table_rows = table_row_extraction_ids(db, {m[0].document_id for m in bodyless})
    table_row_matches = [m for m in matched if m[0].extraction_id in table_rows]
    matched = [m for m in matched if m[0].extraction_id not in table_rows]

    ok_ids = set()
    if matched:
        ok_ids = {
            aid
            for (aid,) in db.query(Audit.id)
            .filter(Audit.id.in_([m[0].audit_id for m in matched]))
            .filter(publishable_audit_criterion())
            .all()
        }

    cases: List[Dict[str, Any]] = []
    withheld: Dict[str, int] = {}
    for row, payload, title in matched:
        if row.audit_id not in ok_ids:
            reason = row.quarantine_reason or "withheld_by_publication_gate"
            withheld[reason] = withheld.get(reason, 0) + 1
            continue
        text = _norm(row.finding_text)
        # The finding text opens with its own title; the excerpt is what
        # follows it, in the report's words.
        excerpt = text[len(title):].strip() if title and text.startswith(title) else text
        county_name = row.canonical_name if row.entity_type == EntityType.COUNTY else None
        cases.append(
            {
                "finding_id": row.audit_id,
                "entity": audited_institution(
                    payload,
                    county_name=county_name,
                    document_meta={"extraction_stats": row.extraction_stats},
                ),
                "entity_id": row.entity_id,
                "county_name": county_name,
                "county_slug": row.slug if county_name else None,
                "entity_type": row.entity_type.value if row.entity_type else None,
                "title": title,
                "excerpt": excerpt[:600],
                "heading": _norm(payload.get("heading")) or None,
                "fiscal_year": row.period_label,
                "page_ref": row.page_ref,
                "source": {
                    "document_id": row.document_id,
                    "title": row.document_title,
                    "publisher": row.document_publisher,
                    "url": row.document_url,
                    "page_url": page_url(row.document_url, row.page_ref),
                },
            }
        )

    # Newest report first, then alphabetically within it.
    cases.sort(key=lambda c: c["entity"] or "")
    cases.sort(key=lambda c: c["fiscal_year"] or "", reverse=True)
    return {
        "cases": cases,
        "withheld": withheld,
        # e.g. "7. Unaccounted for Motor Vehicles" in a table of issues the
        # previous year's audit raised — not a finding of this report.
        "excluded_table_rows": len(table_row_matches),
    }
