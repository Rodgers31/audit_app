"""Retired metadata and source-backed extracted findings use distinct paths."""

import pytest

from models import Audit, DocumentType, Extraction, Severity


LEGACY_CLAIM = "RETIRED_METADATA_CASE_WITH_PLAUSIBLE_CITATION"
REPORT_URL = "https://www.oagkenya.go.ke/wp-content/uploads/2026/05/county-report.pdf"
PATHS = [
    "/api/v1/accountability/missing-funds",
    "/api/v1/counties/1/comprehensive",
]


@pytest.fixture()
def candidate(db_session, seed_entity, seed_source_doc, seed_fiscal_period):
    seed_entity.canonical_name = "Nairobi County"
    seed_source_doc.title = "County Assembly of Nairobi audit report"
    seed_source_doc.publisher = "Office of the Auditor-General"
    seed_source_doc.url = REPORT_URL
    seed_source_doc.doc_type = DocumentType.AUDIT
    text = "Unaccounted expenditure The Assembly did not provide supporting records."
    extraction = Extraction(
        source_document_id=seed_source_doc.id,
        extractor="oag_county_volume",
        page_number=23,
        extracted_json={
            "title": "Unaccounted expenditure",
            "finding_text": text,
            "entity_name": "County Assembly of Nairobi",
            "volume_kind": "assemblies",
            "pdf_page": 23,
        },
    )
    db_session.add(extraction)
    db_session.flush()
    audit = Audit(
        entity_id=seed_entity.id,
        period_id=seed_fiscal_period.id,
        source_document_id=seed_source_doc.id,
        extraction_id=extraction.id,
        page_ref="p.23",
        finding_text=text,
        severity=Severity.WARNING,
        amount=999999,
    )
    db_session.add(audit)
    # A page-shaped string and existing document ID do not turn retired JSON
    # into an extracted finding or prove that its amount was actually reported.
    seed_entity.meta = {
        "county_code": "047",
        "missing_funds_cases": [{
            "case_id": "MF_001",
            "description": LEGACY_CLAIM,
            "amount": "KES 120M",
            "source_document_id": seed_source_doc.id,
            "page_ref": "p.23",
        }],
    }
    db_session.commit()
    return audit, seed_source_doc


def block(client, path):
    response = client.get(path)
    assert response.status_code == 200, response.text
    assert LEGACY_CLAIM not in response.text
    data = response.json()
    return data["missing_funds"] if path.endswith("comprehensive") else data


@pytest.mark.parametrize("path", PATHS)
def test_extracted_case_publishes_without_reopening_legacy_metadata(client, candidate, path):
    audit, document = candidate
    audit_id, document_id = audit.id, document.id
    data = block(client, path)
    assert len(data["cases"]) == 1
    case = data["cases"][0]
    assert case["finding_id"] == audit_id
    assert case["entity"] == "County Assembly of Nairobi"
    assert case["county_name"] == "Nairobi County"
    assert case["excerpt"] == "The Assembly did not provide supporting records."
    assert case["source"]["document_id"] == document_id
    assert case["source"]["page_url"] == REPORT_URL + "#page=23"
    # A balance in the paragraph is not a quantified loss; do not sum it.
    assert data["total_amount"] is None
    assert data["withheld"]["count"] == 0


@pytest.mark.parametrize("path", PATHS)
def test_plausibly_cited_legacy_metadata_alone_stays_retired(
    client, db_session, candidate, path
):
    audit, _ = candidate
    db_session.delete(audit)
    db_session.commit()
    data = block(client, path)
    assert data["cases"] == []
    assert data["total_amount"] is None


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("failure", ["missing_url", "missing_page", "unreadable_text"])
def test_extracted_candidate_failing_provenance_is_counted(
    client, db_session, candidate, path, failure
):
    audit, document = candidate
    if failure == "missing_url":
        document.url = None
    elif failure == "missing_page":
        audit.page_ref = None
    else:
        audit.finding_text += " (cid:100)"
    db_session.commit()
    data = block(client, path)
    assert data["cases"] == []
    assert data["total_amount"] is None
    assert data["withheld"]["count"] == 1
    assert sum(data["withheld"]["by_reason"].values()) == 1
