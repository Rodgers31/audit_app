"""Read-only OAG county × year × institution coverage receipts.

A finding count proves presence, never that a whole report was extracted.
Execution gaps and missing/invalid metadata therefore remain separate from
stored evidence. No network calls or writes are performed by this module.
"""
from __future__ import annotations

import re
from collections import Counter

from .oag_discovery import FIRST_INGESTED_FISCAL_YEAR

ROLES = ("executives", "assemblies")
COUNTY_COUNT = 47


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _years(value):
    if not isinstance(value, list) or not value:
        return None
    if any(not isinstance(v, str) or not re.fullmatch(r"20\d{2}/20\d{2}", v)
           or int(v[5:]) != int(v[:4]) + 1 for v in value):
        return None
    return sorted(set(value))


def _run_gaps(job):
    """Validate before iterating; malformed collections cannot certify success."""
    if job is None:
        return ["no non-dry audits run recorded"]
    meta = _mapping(job.meta)
    if not isinstance(job.meta, dict):
        return ["newest audits run has malformed metadata"]
    gaps = []
    discovery = meta.get("oag_county_discovery")
    if not isinstance(discovery, dict) or _years(discovery.get("listing_fiscal_years")) is None:
        gaps.append("newest audits run has no valid county listing")
    else:
        errors = discovery.get("errors", [])
        if not isinstance(errors, list) or any(not isinstance(e, str) for e in errors):
            gaps.append("malformed discovery errors")
        elif errors:
            gaps.extend(f"discovery: {e}" for e in errors)
    report = meta.get("county_volumes")
    if not isinstance(report, dict):
        gaps.append("newest audits run has no valid volume outcome report")
    else:
        outcome_count = 0
        labels = []
        for key in ("processed", "already_current", "deferred", "failed", "partial"):
            values = report.get(key, [] if key == "partial" else None)
            if isinstance(values, list) and all(isinstance(v, str) and v for v in values):
                outcome_count += len(values)
                for value in values:
                    match = re.match(r"^(20\d{2}/20\d{2}) (executives|assemblies)(?::|$)", value)
                    if not match or _years([match[1]]) is None:
                        gaps.append(f"invalid {key} volume label")
                    else:
                        labels.append((match[1], match[2]))
            else:
                gaps.append(f"malformed or absent {key} volume outcomes")
        discovered = report.get("discovered")
        if type(discovered) is not int or discovered <= 0 or discovered != outcome_count:
            gaps.append("volume outcomes do not account for every discovered volume")
        if len(labels) != len(set(labels)):
            gaps.append("duplicate volume outcomes")
        for key in ("deferred", "failed", "partial"):
            values = report.get(key, [])
            if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
                gaps.append(f"malformed {key} volume outcomes")
            else:
                gaps.extend(f"{key} {v}" for v in values)
    documents = meta.get("documents", [])
    if not isinstance(documents, list) or any(not isinstance(d, dict) for d in documents):
        gaps.append("malformed document outcomes")
    else:
        for doc in documents:
            if "extractions" in doc and not isinstance(doc["extractions"], dict):
                gaps.append(f"document {doc.get('doc_id')}: malformed extraction outcome")
            elif _mapping(doc.get("extractions")).get("partial"):
                gaps.append(f"document {doc.get('doc_id')}: partial extraction")
            elif "partial" in _mapping(doc.get("extractions")) and type(doc["extractions"]["partial"]) is not bool:
                gaps.append(f"document {doc.get('doc_id')}: malformed partial outcome")
    status = getattr(job.status, "value", job.status)
    if status != "completed":
        gaps.append(f"newest audits run status is {status}")
    if meta.get("source_mode") in ("refused", "partial", "fixture", "unknown"):
        gaps.append(f"newest audits run source mode is {meta['source_mode']}")
    return gaps


def county_audit_coverage_receipt(session):
    from models import Audit, Entity, EntityType, Extraction, IngestionJob, SourceDocument
    from services.audit_citations import audited_institution, extraction_payload, page_number
    from services.publication_gate import publishable_audit_criterion
    from .extractors.oag_county_audit import _known_counties
    from .extractors.oag_county_volume import canonical_county, county_from_auditee

    jobs = (session.query(IngestionJob)
            .filter(IngestionJob.domain == "audits", IngestionJob.dry_run.is_(False))
            .order_by(IngestionJob.started_at.desc(), IngestionJob.id.desc()).limit(60).all())
    listing_job, listing = None, []
    for job in jobs:
        years = _years(_mapping(_mapping(job.meta).get("oag_county_discovery")).get("listing_fiscal_years"))
        if years:
            listing_job, listing = job, years
            break
    listed = [fy for fy in listing if fy >= FIRST_INGESTED_FISCAL_YEAR]
    counties = session.query(Entity).filter(Entity.type == EntityType.COUNTY).order_by(Entity.id).all()
    counts, documents = Counter(), {}
    known_counties = _known_counties(session)
    incomplete_documents = set()
    unidentified = 0
    geographic = {}
    rows = (session.query(Audit, Entity, Extraction, SourceDocument)
            .join(Entity, Entity.id == Audit.entity_id)
            .outerjoin(Extraction, Extraction.id == Audit.extraction_id)
            .join(SourceDocument, SourceDocument.id == Audit.source_document_id)
            .filter(Entity.type == EntityType.COUNTY, Audit.publishable.is_(True),
                    publishable_audit_criterion()).all())
    seen = set()
    for audit, county, ext, doc in rows:
        if audit.audit_year is not None:
            geographic.setdefault(audit.audit_year, set()).add(county.id)
        payload = extraction_payload(ext.extracted_json) if ext else {}
        institution = audited_institution(payload, county_name=county.canonical_name, document_meta=doc.meta)
        role = next((kind for name, kind in (("assembly", "assemblies"), ("executive", "executives"))
                     if institution and re.search(rf"\bcounty\s+{name}\b", institution, re.I)), None)
        fy = payload.get("fiscal_year")
        if (role is None or ext is None or ext.source_document_id != doc.id
                or _years([fy]) is None or audit.audit_year != int(fy[5:])
                or page_number(audit.page_ref) is None
                or page_number(payload.get("pdf_page")) != page_number(audit.page_ref)
                or page_number(ext.page_number) != page_number(audit.page_ref)):
            unidentified += 1
            continue
        source_names = [payload.get(k) for k in ("entity_name", "auditee") if payload.get(k) is not None]
        expected_county = re.sub(r"\s+County$", "", county.canonical_name, flags=re.I)
        if not source_names or any(
            not isinstance(name, str) or not county_from_auditee(name)
            or canonical_county(county_from_auditee(name), known_counties) != expected_county
            for name in source_names
        ):
            unidentified += 1
            continue
        if _mapping(_mapping(doc.meta).get("extraction_stats")).get("partial"):
            incomplete_documents.add(doc.id)
        # Duplicate rows referencing one extraction do not inflate coverage.
        if ext.id in seen:
            continue
        seen.add(ext.id)
        key = (county.id, fy, role)
        counts[key] += 1
        documents.setdefault(key, set()).add(doc.id)
    cells = [dict(county_id=c.id, county=c.canonical_name, fiscal_year=fy,
                  institution=role, findings=counts[(c.id, fy, role)],
                  source_document_ids=sorted(documents.get((c.id, fy, role), ())))
             for fy in listed for c in counties for role in ROLES]
    return {
        "listing_years": listing, "required_years": listed,
        "listing_read_at": listing_job.started_at.isoformat() if listing_job and listing_job.started_at else None,
        "listing_job_id": listing_job.id if listing_job else None,
        "county_count": len(counties), "expected_county_count": COUNTY_COUNT,
        "cells": cells, "unattributed_findings": unidentified,
        "counties_by_year": {year: len(ids) for year, ids in geographic.items()},
        "run_gaps": _run_gaps(jobs[0] if jobs else None) + [
            f"document {doc_id}: stored partial extraction" for doc_id in sorted(incomplete_documents)
        ],
    }


def coverage_verdict(receipt):
    """Return a single severity/message pair; missing evidence never reads OK."""
    if receipt["listing_job_id"] is None:
        return "WARN", "no audits run has recorded OAG's county listing. Unrecorded is not the same as covered."
    listed = receipt["required_years"]
    when = (receipt["listing_read_at"] or "unknown date")[:10]
    if not listed:
        return "WARN", f"OAG's county listing (read {when}) named no fiscal year from {FIRST_INGESTED_FISCAL_YEAR} on"
    counts = receipt["counties_by_year"]
    missing = [fy for fy in listed if not counts.get(int(fy[5:]), 0)]
    messages, level = [], "OK"
    if missing:
        newest = max(counts, default=None)
        newest_label = f"FY{newest - 1}/{newest}" if newest else "none"
        messages.append(f"OAG's county listing (read {when}) publishes {', '.join(missing)}, "
                        f"and no county finding is published for them; newest county year published is {newest_label}")
        level = "FAIL"
    partial = [f"{fy} ({counts[int(fy[5:])]}/{COUNTY_COUNT} counties)" for fy in listed
               if 0 < counts.get(int(fy[5:]), 0) < COUNTY_COUNT]
    if partial:
        messages.append("some counties have no published finding for " + ", ".join(partial))
    role_gaps = []
    for fy in listed:
        for role in ROLES:
            n = sum(c["findings"] > 0 for c in receipt["cells"]
                    if c["fiscal_year"] == fy and c["institution"] == role)
            if n != COUNTY_COUNT:
                role_gaps.append(f"{fy} {role} ({n}/{COUNTY_COUNT} counties)")
    if role_gaps:
        messages.append("institutional coverage incomplete: " + "; ".join(role_gaps))
    if receipt["county_count"] != COUNTY_COUNT:
        messages.append(f"county reference set has {receipt['county_count']}/{COUNTY_COUNT} counties")
    if receipt["run_gaps"]:
        messages.append("newest audits run: " + "; ".join(receipt["run_gaps"]))
    if messages:
        return ("WARN" if level == "OK" else level), ". ".join(messages)
    return "OK", (f"every fiscal year OAG lists from {FIRST_INGESTED_FISCAL_YEAR} has "
                  f"published, attributed findings for all {COUNTY_COUNT} executives and "
                  f"{COUNTY_COUNT} assemblies (listing read {when}); this measures finding presence, not extraction completeness")
