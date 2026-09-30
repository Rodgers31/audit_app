"""Evidence selection for the site's severity-derived county health signal.

No opinion is inferred from finding severity. Legacy status names remain only
as compatibility inputs to the unchanged site score's numeric mapping.
"""
import re
from collections import defaultdict
from datetime import date

from models import Audit, Extraction, FiscalPeriod, SourceDocument
from types import SimpleNamespace
from services.audit_citations import (
    audited_institution,
    extraction_json_type,
    string_extraction_payloads,
)
from services.publication_gate import publishable_audit_criterion


def fiscal_year(value):
    match = re.fullmatch(
        r"(?:FY\s*)?(\d{4})/(\d{2}|\d{4})", str(value or "").strip(), re.I
    )
    if not match:
        return None
    start = int(match[1])
    end = int(match[2]) if len(match[2]) == 4 else start // 100 * 100 + int(match[2])
    return (start, end) if end == start + 1 else None


def county_audit_signals(db, entity_ids, *, display_grade):
    """Batch metadata only; latest valid executive FY, worst severity in that FY.

    A latest-period scope/period conflict withholds that period, without
    falling back. Unknown periods are counted explicitly. Multiple documents
    of the same executive/FY contribute findings to the maximum severity;
    distinct citations are counted and sampled, so ties need no ingestion/ID priority.
    """
    if not entity_ids:
        return {}
    rows = (
        db.query(
            Audit.extraction_id,
            extraction_json_type(
                Extraction.extracted_json, db.get_bind().dialect.name
            ).label("extraction_payload_type"),
            Audit.entity_id,
            Audit.severity,
            Audit.provenance,
            Audit.source_document_id,
            Audit.page_ref,
            FiscalPeriod.label,
            FiscalPeriod.start_date,
            FiscalPeriod.end_date,
            SourceDocument.url,
            SourceDocument.meta,
            Extraction.extracted_json["entity_name"].as_string().label("entity_name"),
            Extraction.extracted_json["auditee"].as_string().label("auditee"),
            Extraction.extracted_json["volume_kind"].as_string().label("volume_kind"),
            Extraction.extracted_json["fiscal_year"].as_string().label("fiscal_year"),
        )
        .outerjoin(FiscalPeriod, Audit.period_id == FiscalPeriod.id)
        .join(SourceDocument, Audit.source_document_id == SourceDocument.id)
        .outerjoin(Extraction, Audit.extraction_id == Extraction.id)
        .filter(Audit.entity_id.in_(entity_ids), publishable_audit_criterion())
        .all()
    )
    serialized = string_extraction_payloads(db, rows)
    if serialized:
        rows = [
            SimpleNamespace(
                **{
                    **r._mapping,
                    **{
                        key: serialized[r.extraction_id].get(key)
                        for key in (
                            "entity_name",
                            "auditee",
                            "volume_kind",
                            "fiscal_year",
                        )
                    },
                }
            )
            if r.extraction_id in serialized
            else r
            for r in rows
        ]
    from models import Entity

    names = dict(
        db.query(Entity.id, Entity.canonical_name).filter(Entity.id.in_(entity_ids))
    )
    grouped = defaultdict(list)
    for row in rows:
        if display_grade(row):
            grouped[row.entity_id].append(row)
    return {eid: select_audit_signal(grouped[eid], names[eid]) for eid in entity_ids}


def select_audit_signal(rows, county_name):
    periods = defaultdict(list)
    excluded = defaultdict(int)
    for r in rows:
        payload = {
            k: getattr(r, k, None) for k in ("entity_name", "auditee", "volume_kind")
        }
        institution = audited_institution(
            payload, county_name=county_name, document_meta=r.meta
        )
        if institution and re.search(r"\bassembly\b", institution, re.I):
            excluded["county_assembly_excluded"] += 1
            continue
        fy = fiscal_year(r.label)
        if not fy:
            excluded["missing_or_ambiguous_audit_period"] += 1
            continue
        if (
            not r.start_date
            or not r.end_date
            or (
                r.start_date.date() != date(fy[0], 7, 1)
                or r.end_date.date() != date(fy[1], 6, 30)
            )
        ):
            periods[fy].append((r, "missing_or_ambiguous_audit_period", institution))
            continue
        entries = r.provenance if isinstance(r.provenance, list) else [r.provenance]
        meta = r.meta if isinstance(r.meta, dict) else {}
        stats = meta.get("extraction_stats")
        stats = stats if isinstance(stats, dict) else {}
        declared = [
            r.fiscal_year,
            stats.get("fiscal_year"),
            meta.get("fiscal_year"),
            meta.get("period_label"),
        ]
        declared += [
            e.get("fiscal_year") or e.get("period_label")
            for e in entries
            if isinstance(e, dict)
        ]
        conflict = any(v is not None and fiscal_year(v) != fy for v in declared)
        if conflict:
            periods[fy].append((r, "conflicting_audit_period", institution))
        elif not institution:
            periods[fy].append((r, "missing_or_conflicting_audit_institution", None))
        elif re.search(r"\bassembly\b", institution, re.I):
            excluded["county_assembly_excluded"] += 1
        else:
            periods[fy].append((r, None, institution))
    result = {
        "status": "pending",
        "severity": None,
        "source_period": None,
        "period_end": None,
        "source_url": None,
        "sources": [],
        "source_count": 0,
        "sources_truncated": False,
        "institution": None,
        "measurement_basis": "finding_severity",
        "official_opinion": False,
        "selection_policy": "latest_executive_fiscal_year_maximum_severity",
        "excluded": dict(sorted(excluded.items())),
        "absent_reason": "no_publishable_audit_signal",
    }
    if not periods:
        if excluded.get("missing_or_ambiguous_audit_period"):
            result["absent_reason"] = "missing_or_ambiguous_audit_period"
        return result
    fy = max(periods)
    chosen = periods[fy]
    result["source_period"] = f"FY{fy[0]}/{str(fy[1])[-2:]}"
    sources = {(r.source_document_id, r.url, r.page_ref) for r, _, _ in chosen}
    urls = {url for _, url, _ in sources}
    result.update(
        source_url=next(iter(urls)) if len(urls) == 1 else None,
        sources=[
            {"source_document_id": sid, "url": url, "page_ref": page}
            for sid, url, page in sorted(
                sources, key=lambda item: tuple(str(v or "") for v in item)
            )[:20]
        ],
        source_count=len(sources),
        sources_truncated=len(sources) > 20,
    )
    reasons = sorted({reason for _, reason, _ in chosen if reason})
    if reasons:
        result["absent_reason"] = reasons[0]
        return result
    ranks = {"info": 0, "warning": 1, "critical": 2}
    severities = {getattr(r.severity, "value", r.severity) for r, _, _ in chosen}
    if not severities or not severities <= ranks.keys():
        result["absent_reason"] = "unknown_audit_severity"
        return result
    severity = max(severities, key=ranks.get)
    result["period_end"] = date(fy[1], 6, 30).isoformat()
    result.update(
        status={"info": "clean", "warning": "qualified", "critical": "adverse"}[
            severity
        ],
        severity=severity,
        institution=f"County Executive of {county_name.removesuffix(' County')}",
        absent_reason=None,
    )
    return result
