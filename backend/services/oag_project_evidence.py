"""Bounded historical observations from supplied, ingested OAG county records.

The accepted passage hashes are over the real visible-text extractor's normalized
finding text (heading included), not PDF identity or a canonical JSON hash.
They are refusal guards, never records to inject when ingestion is absent.
"""
from __future__ import annotations

import hashlib
import json
import re

from seeding.pdf_artifact import (
    BINDING_KEY,
    artifact_for_document,
    artifact_matches_document,
    valid_binding,
)
from seeding.extractors.oag_blue_book import source_hash_of
from services.county_identity import official_county_code

SOURCE_SHA256 = "683fa522bf11eaa2b0bc2a9eef51eadc3d664d9a512d3af63cb6e9479820f8a2"
SOURCE_URL = "https://www.oagkenya.go.ke/wp-content/uploads/2025/02/GREEN-BOOK-ASSEMBLIES-2024-FINAL-01-April-2025-KLB.pdf"
# Full actual finding texts, including paragraph533's continuation on PDF206.
PASSAGES = {
    537: (
        207,
        193,
        "Delayed Completion of Speaker’s Residence",
        "f6ea6e3bbfd7f30b60a5460d8f37c8ce8a7c147f564ca9e25e0820540f755db5",
    ),
    533: (
        205,
        191,
        "Pending Account Payables",
        "2882514b3419c7ef361a2a172f97c93d506401560e08c64a6ae4a79b709c94f3",
    ),
}


def bound_context(audit, extraction, doc, county_name):
    """Return exact context or a visible refusal; never infer legacy binding."""
    try:
        return _bound_context(audit, extraction, doc, county_name)
    except (
        TypeError,
        ValueError,
        AttributeError,
        KeyError,
        RecursionError,
        OverflowError,
    ):
        return None, "malformed_oag_evidence"


def _bound_context(a, ext, doc, county_name):
    if ext is None or doc is None:
        return None, "missing_extraction_or_document"
    p = ext.extracted_json
    if not isinstance(p, dict):
        return None, "malformed_oag_extraction"
    binding = p.get(BINDING_KEY)
    if binding is None:
        return None, "extraction_artifact_binding_absent"
    if not valid_binding(binding):
        return None, "invalid_extraction_artifact_binding"
    artifact = binding["artifact"]
    if (
        not artifact_matches_document(artifact, doc)
        or artifact_for_document(doc) != artifact
        or getattr(doc.status, "name", doc.status) != "AVAILABLE"
        or getattr(doc.doc_type, "name", doc.doc_type) != "AUDIT"
    ):
        return None, "document_artifact_mismatch"
    if (
        ext.extractor != "oag_county_volume"
        or p.get("schema") != "oag_county_volume/v1"
        or a.extraction_id != ext.id
        or a.source_document_id != doc.id
        or ext.source_document_id != doc.id
        or a.publishable is not True
    ):
        return None, "audit_extraction_source_mismatch"
    json.dumps(p, allow_nan=False)  # canonical hash must not bless non-JSON numbers.
    if a.source_hash != source_hash_of(p):
        return None, "extraction_json_hash_mismatch"
    code = official_county_code(county_name) if county_name is not None else None
    if (
        code is None
        or official_county_code(p.get("county_name")) != code
        or official_county_code(a.entity.canonical_name) != code
        or a.entity.country_id != doc.country_id
        or getattr(a.entity.type, "name", a.entity.type) != "COUNTY"
    ):
        return None, "oag_county_mismatch"
    role = {"assemblies": "Assembly", "executives": "Executive"}.get(
        p.get("volume_kind")
    )
    county = p.get("county_name")
    if (
        role is None
        or p.get("entity_name") != f"County {role} of {county}"
        or p.get("auditee") != f"County {role} of {county}"
    ):
        return None, "oag_institution_mismatch"
    fy = p.get("fiscal_year")
    if (
        not isinstance(fy, str)
        or not re.fullmatch(r"\d{4}/\d{4}", fy)
        or int(fy[-4:]) != int(fy[:4]) + 1
        or a.audit_year != int(fy[-4:])
        or a.period.label != f"FY{fy[:4]}/{fy[-2:]}"
    ):
        return None, "oag_period_mismatch"
    if (
        any(
            type(p.get(k)) is not int or p[k] <= 0
            for k in ("pdf_page", "printed_page", "paragraph_no", "chapter_no")
        )
        or p["pdf_page"] > binding["pdf_pages"]
        or ext.page_number != p["pdf_page"]
        or a.page_ref != f"p.{p['pdf_page']}"
        or a.finding_text != p.get("finding_text")
        or p.get("extraction_method") not in ("pdfplumber", "ocr")
    ):
        return None, "oag_locator_or_text_mismatch"
    prov = a.provenance
    if not isinstance(prov, list) or len(prov) != 1 or not isinstance(prov[0], dict):
        return None, "oag_provenance_mismatch"
    entry = prov[0]
    if (
        entry.get(BINDING_KEY) != binding
        or entry.get("source_md5") != artifact["md5"]
        or entry.get("source_url") != artifact["source_url"]
        or entry.get("extraction_id") != ext.id
        or entry.get("pdf_page") != p["pdf_page"]
        or entry.get("printed_page") != p["printed_page"]
        or entry.get("title") != p.get("title")
        or entry.get("auditee") != p.get("auditee")
        or entry.get("volume_kind") != p.get("volume_kind")
        or any(
            entry.get(k) != p.get(k)
            for k in (
                "chapter_no",
                "subreport",
                "opinion",
                "heading",
                "sub_section",
                "extraction_method",
                "fiscal_year_sources",
            )
        )
    ):
        return None, "oag_provenance_mismatch"
    return {
        "artifact": artifact,
        "report": artifact["report_title"],
        "source_url": artifact["source_url"],
        "fiscal_year": fy,
        "scope": "audit_year",
        "institution": f"{county} County {role}",
        "county": county,
        "pdf_page": p["pdf_page"],
        "printed_page": p["printed_page"],
        "paragraph": str(p["paragraph_no"]),
        "chapter": p["chapter_no"],
        "auditee": p["auditee"],
        "chapter_heading": p.get("chapter_heading"),
        "heading": p.get("title"),
        "text": p["finding_text"],
        "subreport": p.get("subreport"),
        "opinion": p.get("opinion"),
        "report_section": p.get("heading"),
        "extraction_method": p.get("extraction_method"),
        "fiscal_year_sources": p.get("fiscal_year_sources"),
        "extraction_id": ext.id,
        "audit_id": a.id,
        "extraction_json_sha256": a.source_hash,
        "text_visibility": binding["text_visibility"],
        "pdf_pages": binding["pdf_pages"],
    }, None


def historical_projection(audits, extractions, documents, county_name):
    """Only the accepted Nyamira edition/passages have a historical contract."""
    out = {
        "schema_version": 1,
        "status": "unavailable",
        "reason": "not_ingested",
        "observations": [],
        "sources": {},
        "evidence": {},
        "refusals": [],
    }
    if official_county_code(county_name) != "046":
        out["reason"] = "no_approved_historical_candidate_for_county"
        return out
    found = {}
    for a in audits:
        ext = extractions.get(a.extraction_id)
        # Other findings are not evidence for this narrow accepted contract.
        p = getattr(ext, "extracted_json", None)
        if (
            not isinstance(p, dict)
            or type(p.get("paragraph_no")) is not int
            or p["paragraph_no"] not in PASSAGES
        ):
            continue
        context, reason = bound_context(
            a, ext, documents.get(a.source_document_id), county_name
        )
        if reason is None:
            page, printed, heading, text_hash = PASSAGES[p["paragraph_no"]]
            if (
                context["artifact"]["sha256"] != SOURCE_SHA256
                or context["source_url"] != SOURCE_URL
                or context["pdf_pages"] != 217
                or context["artifact"]["publisher"] != "Office of the Auditor-General"
                or context["fiscal_year"] != "2023/2024"
                or context["institution"] != "Nyamira County Assembly"
                or context["chapter"] != 46
                or context["chapter_heading"] != "COUNTY ASSEMBLY OF NYAMIRA – NO.46"
                or context["pdf_page"] != page
                or context["printed_page"] != printed
                or context["heading"] != heading
                or hashlib.sha256(context["text"].encode()).hexdigest() != text_hash
            ):
                reason = "unapproved_historical_source_or_context"
        if reason:
            out["refusals"].append({"audit_id": a.id, "reason": reason})
        else:
            found.setdefault(p["paragraph_no"], []).append(context)
    if len(found.get(537, [])) != 1:
        out["reason"] = "historical_residence_evidence_unavailable_or_ambiguous"
        return out
    primary = found[537][0]
    payable = found.get(533, [])
    # Optional payable must name the exact same document/artifact edition.
    payable = (
        payable[0]
        if len(payable) == 1 and payable[0]["artifact"] == primary["artifact"]
        else None
    )
    evidence = {"nyamira-oag537": _evidence(primary)}
    if payable:
        evidence["nyamira-oag533"] = _evidence(payable)
    observation = _observation(primary, payable)
    out.update(
        status="accepted",
        reason=None,
        observations=[observation],
        evidence=evidence,
        sources={
            "oag_assembly_2024": {
                "url": primary["source_url"],
                "sha256": primary["artifact"]["sha256"],
                "pages": primary["pdf_pages"],
                "fiscal_year": primary["fiscal_year"],
                "publisher": primary["artifact"]["publisher"],
                "scope": "audit_year",
                "report": primary["report"],
                "artifact": primary["artifact"],
            }
        },
    )
    return out


def _evidence(context):
    return {
        "source_ref": "oag_assembly_2024",
        "pdf_page": context["pdf_page"],
        "printed_page": context["printed_page"],
        "paragraph": context["paragraph"],
        "anchor": context["heading"],
        "excerpt": context["text"],
        "chapter": context["chapter"],
        "auditee": context["auditee"],
        "extraction_id": context["extraction_id"],
        "audit_id": context["audit_id"],
        "extraction_json_sha256": context["extraction_json_sha256"],
    }


def _observation(primary, payable):
    from seeding.domains.stalled_projects.cob_parser import (
        _narrative_date,
        _narrative_statement,
    )

    def absent(reason):
        return {"state": "absent", "reason": reason, "statements": []}

    def stated(value):
        return {"state": "stated", "value": value, "reason": None}

    unknown = {
        "value": None,
        "precision": "unknown",
        "reason": "Exact observation date is not stated in the bound passage.",
    }
    text = primary["text"]
    # Date precision comes from the actual bound text. Source/download dates
    # never fill an unstated observation date.
    from datetime import datetime

    def passage_day(pattern):
        literal = re.search(pattern, text).group(1)
        return _narrative_date(
            datetime.strptime(literal, "%d %B, %Y").date().isoformat()
        )

    at = passage_day(r"report issued on (\d+ \w+, \d{4})")
    commenced = passage_day(r"contract commenced on (\d+ \w+, \d{4})")
    expected = passage_day(r"expected completion date of (\d+ \w+, \d{4})")
    measures = {
        "estimated_value": absent("No estimated value stated in the bound OAG passage.")
    }
    literals = {
        "contract_sum": re.search(
            r"contract price amount of Kshs\.([\d,]+)", text
        ).group(1),
        "paid": re.search(r"payments totalling Kshs\.([\d,]+)", text).group(1),
        "completion_pct": re.search(r"construction was (\d+)% complete", text).group(1),
    }
    for key, literal in literals.items():
        statement = _narrative_statement(
            literal,
            "percent" if key == "completion_pct" else "KES",
            "nyamira-oag537",
            "named_project",
            unknown if key == "contract_sum" else at,
        )
        measures[key] = {"state": "stated", "reason": None, "statements": [statement]}
    measures["payable"] = absent(
        "No uniquely bound paragraph533 supplied for this artifact; payable is unavailable."
    )
    if payable:
        literal = re.search(
            r"Kshs\.([\d,]+) in respect of construction the Speaker’s residence",
            payable["text"],
        ).group(1)
        measures["payable"] = {
            "state": "stated",
            "reason": None,
            "statements": [
                _narrative_statement(
                    literal, "KES", "nyamira-oag533", "named_project", unknown
                )
            ],
        }
    inspection_literal = re.search(
        r"inspection undertaken in (\w+, \d{4})", text
    ).group(1)
    inspection = _narrative_date(
        datetime.strptime(inspection_literal, "%B, %Y").strftime("%Y-%m"), "month"
    )
    return {
        "observation_id": "nyamira-oag-historical",
        "county": {"official_code": "046", "name": "Nyamira"},
        "name_as_printed": re.search(
            r"construct the (Speaker’s residence)", text
        ).group(1),
        "location": {
            "state": "absent",
            "value": None,
            "reason": "Ward is not stated in paragraph537.",
        },
        "reporting_body": stated(primary["artifact"]["publisher"]),
        "implementing_institution": stated(primary["institution"]),
        "tender_reference": {
            "state": "absent",
            "value": None,
            "reason": "No shared tender identifier in the bound passage.",
        },
        "source_ref": "oag_assembly_2024",
        "fiscal_year": primary["fiscal_year"],
        "scope": "audit_year",
        "named_evidence_ref": "nyamira-oag537",
        "measures": measures,
        "scalar_measures": {
            k: v["statements"][0]["value"] if v["state"] == "stated" else None
            for k, v in measures.items()
        },
        "milestones": [
            {
                "kind": "commencement",
                "date": commenced,
                "evidence_ref": "nyamira-oag537",
            },
            {
                "kind": "expected_completion",
                "date": expected,
                "evidence_ref": "nyamira-oag537",
            },
            {
                "kind": "inspection",
                "date": inspection,
                "evidence_ref": "nyamira-oag537",
            },
        ],
        "status": {
            "classification": "historical_value_for_money_concern",
            "evidence_ref": "nyamira-oag537",
            "as_of": inspection,
        },
    }


def attach_historical(narratives, historical):
    """A candidate compares accepted observations; it cannot alter their measures."""
    narratives.update(
        historical_observations=historical["observations"],
        historical_sources=historical["sources"],
        historical_evidence=historical["evidence"],
        historical_evidence_status=historical["status"],
        historical_refusals=historical["refusals"],
        historical_candidate_reason=historical["reason"],
    )
    if narratives["status"] != "accepted":
        narratives["historical_candidate_reason"] = "annual_narrative_unavailable"
        return narratives
    if historical["status"] != "accepted":
        return narratives
    annual = narratives["observations"][0]
    older = historical["observations"][0]
    if (
        annual["observation_id"] != "nyamira-cob-annual"
        or annual["implementing_institution"] != older["implementing_institution"]
    ):
        narratives["historical_candidate_reason"] = "observation_identity_not_supported"
        return narratives
    narratives["historical_identity_candidates"] = [
        {
            "from_observation": annual["observation_id"],
            "to_observation": older["observation_id"],
            "type": "historical_identity_candidate",
            "basis": [
                "institution",
                "name",
                "commencement_month",
                "rounded_contract",
                "completion_pct",
            ],
            "missing": ["shared_tender_reference", "ward_in_oag"],
            "decision": "candidate_only_no_automatic_join",
            "qualification": "Older source observation only; no current audit verification, financial reconciliation or proven loss. Paid and payable stay separate and do not resolve the annual paid conflict.",
        }
    ]
    return narratives
