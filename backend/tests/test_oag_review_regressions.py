"""Review regressions: malformed provenance cannot certify OAG coverage."""

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from models import (
    Audit, DocumentStatus, Extraction, IngestionJob, IngestionStatus, SourceDocument,
)
from seeding.staleness import (
    OK, check_county_audit_coverage, check_ingestion_freshness,
)
from seeding.county_audit_coverage import county_audit_coverage_receipt, coverage_verdict
from services.audit_citations import audited_institution
from test_county_audit_coverage_gate import db  # noqa: F401 - fixture for imported covered
from test_county_coverage_adversarial import covered
from test_audits_domain_county_ingest import harness, _run as run_domain


def test_missing_partial_bucket_cannot_certify_all_volumes(covered):
    job = covered.query(IngestionJob).one()
    meta = deepcopy(job.meta)
    del meta["county_volumes"]["partial"]
    job.meta = meta
    covered.flush()
    assert check_county_audit_coverage(covered)[0].level != OK


@pytest.mark.parametrize("source_mode", [["live"], {}, "", " "])
def test_malformed_county_source_mode_cannot_certify_coverage(covered, source_mode):
    job = covered.query(IngestionJob).one()
    job.meta = {**job.meta, "source_mode": source_mode}
    covered.flush()
    assert check_county_audit_coverage(covered)[0].level != OK


@pytest.mark.parametrize(
    "stats", [None, [], {"partial": 0}, {"partial": []}, {"partial": None}]
)
def test_malformed_stored_extraction_stats_cannot_count_as_coverage(covered, stats):
    document = covered.query(SourceDocument).one()
    document.meta = {"extraction_stats": stats}
    covered.flush()
    finding = check_county_audit_coverage(covered)[0]
    assert finding.level != OK
    assert "document" in finding.message


def test_discovered_volumes_must_have_outcomes_for_the_same_year_and_role(covered):
    job = covered.query(IngestionJob).one()
    meta = deepcopy(job.meta)
    meta["oag_county_discovery"]["volumes_by_fiscal_year"] = {
        "2024/2025": [
            "https://www.oagkenya.go.ke/county-executives-2024-2025.pdf",
            "https://www.oagkenya.go.ke/county-assemblies-2024-2025.pdf",
        ]
    }
    meta["county_volumes"]["processed"] = [
        "2023/2024 executives: 47 finding(s)",
        "2023/2024 assemblies: 47 finding(s)",
    ]
    job.meta = meta
    covered.flush()
    assert check_county_audit_coverage(covered)[0].level != OK


@pytest.mark.parametrize("filenames", [
    ("example-executives.txt", "example-assemblies.txt"),
    ("example.pdf?x=executives", "example.pdf?x=assemblies"),
    ("county-executives-2021-2022.pdf", "county-assemblies-2021-2022.pdf"),
    ("county-executives-2024-2025-2021-2022.pdf",
     "county-assemblies-2024-2025-2021-2022.pdf"),
])
def test_discovered_volume_urls_must_be_current_pdf_roles(covered, filenames):
    job = covered.query(IngestionJob).one()
    meta = deepcopy(job.meta)
    meta["oag_county_discovery"]["volumes_by_fiscal_year"] = {
        "2024/2025": [f"https://www.oagkenya.go.ke/{name}" for name in filenames]
    }
    job.meta = meta
    covered.flush()
    assert check_county_audit_coverage(covered)[0].level != OK


def test_json_saved_coverage_receipt_keeps_its_valid_verdict(covered):
    receipt = json.loads(json.dumps(county_audit_coverage_receipt(covered)))
    assert coverage_verdict(receipt)[0] == "OK"


def test_unlisted_volume_outcome_cannot_certify_inventory(covered):
    job = covered.query(IngestionJob).one()
    meta = deepcopy(job.meta)
    meta["county_volumes"]["processed"].append("2023/2024 executives: 1 finding(s)")
    meta["county_volumes"]["discovered"] = 3
    job.meta = meta
    covered.flush()
    assert check_county_audit_coverage(covered)[0].level != OK


def test_stale_extraction_hash_cannot_certify_current_source(covered):
    document = covered.query(SourceDocument).one()
    document.md5 = "a" * 32
    document.meta = {"extracted_md5": "b" * 32,
                     "extraction_stats": {"partial": False}}
    covered.flush()
    assert check_county_audit_coverage(covered)[0].level != OK


def test_failed_source_document_cannot_certify_coverage(covered):
    document = covered.query(SourceDocument).one()
    document.status = DocumentStatus.FAILED
    covered.flush()
    assert check_county_audit_coverage(covered)[0].level != OK


def test_latest_partial_extraction_attempt_remains_visible(covered):
    document = covered.query(SourceDocument).one()
    document.meta = {"extraction_stats": {"partial": False},
                     "last_extraction_attempt": {"status": "partial", "error": "unreadable"}}
    covered.flush()
    assert check_county_audit_coverage(covered)[0].level != OK


def test_malformed_extra_document_is_not_hidden_by_complete_valid_cells(covered):
    good = covered.query(Audit).first()
    source = covered.query(SourceDocument).one()
    extra = SourceDocument(country_id=source.country_id, publisher=source.publisher,
                           title="broken.pdf", url="https://www.oagkenya.go.ke/broken.pdf",
                           fetch_date=source.fetch_date, doc_type=source.doc_type,
                           status=DocumentStatus.AVAILABLE,
                           meta={"extraction_stats": []})
    covered.add(extra)
    covered.flush()
    extraction = Extraction(source_document_id=extra.id, page_number=1,
                            extractor="oag_county_volume", confidence=0.9,
                            extracted_json={"fiscal_year": "2024/2025", "pdf_page": 99,
                                            "auditee": "County Executive of Elsewhere"})
    covered.add(extraction)
    covered.flush()
    covered.add(Audit(entity_id=good.entity_id, period_id=good.period_id,
                      finding_text="unattributable", severity=good.severity,
                      source_document_id=extra.id, extraction_id=extraction.id,
                      audit_year=2025, page_ref="p.1", publishable=True))
    covered.flush()
    assert check_county_audit_coverage(covered)[0].level != OK


@pytest.mark.parametrize("source_mode", ["", " ", "bogus", None, "unknown"])
def test_latest_untrusted_mode_cannot_borrow_older_live_run(db_session, source_mode):
    now = datetime(2026, 9, 27, tzinfo=timezone.utc)
    jobs = [
        IngestionJob(domain="national_budget", status=IngestionStatus.COMPLETED,
                     dry_run=False, started_at=(now - timedelta(days=2)).replace(tzinfo=None),
                     meta={"source_mode": "live"}),
        IngestionJob(domain="national_budget", status=IngestionStatus.COMPLETED,
                     dry_run=False, started_at=(now - timedelta(days=1)).replace(tzinfo=None),
                     meta={} if source_mode is None else {"source_mode": source_mode}),
    ]
    db_session.add_all(jobs)
    db_session.flush()
    finding = check_ingestion_freshness(db_session, now=now, domains=["national_budget"])[0]
    assert finding.level != OK


def test_tied_refusal_outranks_missing_mode_and_older_live_run(db_session):
    now = datetime(2026, 9, 27, tzinfo=timezone.utc)
    older = (now - timedelta(days=2)).replace(tzinfo=None)
    latest = (now - timedelta(days=1)).replace(tzinfo=None)
    db_session.add_all([
        IngestionJob(domain="national_budget", status=IngestionStatus.COMPLETED,
                     dry_run=False, started_at=older, meta={"source_mode": "live"}),
        IngestionJob(domain="national_budget", status=IngestionStatus.COMPLETED,
                     dry_run=False, started_at=latest, meta={"source_mode": "refused"}),
        IngestionJob(domain="national_budget", status=IngestionStatus.COMPLETED,
                     dry_run=False, started_at=latest, meta={}),
    ])
    db_session.flush()
    finding = check_ingestion_freshness(db_session, now=now, domains=["national_budget"])[0]
    assert finding.level == "FAIL"


@pytest.mark.parametrize("identity_key", ["auditee", "entity_name"])
def test_single_foreign_county_role_cannot_name_stored_county(identity_key):
    assert audited_institution(
        {identity_key: "County Executive of Kilifi"}, county_name="Nairobi County"
    ) is None


def test_nonrole_foreign_entity_cannot_be_relabelled_as_stored_county():
    assert audited_institution(
        {"entity_name": "Office of Kilifi County", "volume_kind": "executives"},
        county_name="Nairobi County",
    ) is None


def test_malformed_parser_statistics_are_refused_before_domain_uses_them(harness, monkeypatch):
    """Review-overview lead: a list cannot reach the later domain .get()."""
    monkeypatch.setattr(
        "seeding.extractors.get_parser",
        lambda parser_id: (lambda *args: [1]) if parser_id == "oag_county_audit" else None,
    )
    result = run_domain(harness["session"], 10_000)
    report = result.metadata["county_volumes"]
    assert len(report["failed"]) == 4
    assert not report["processed"] and not report["already_current"]
    assert result.errors
