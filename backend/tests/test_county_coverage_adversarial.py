"""Independent hostile-input probes for the county ingestion coverage verdict."""
from copy import deepcopy
from datetime import datetime

import pytest
from test_county_audit_coverage_gate import (_audits_run, _counties, _findings,
                                             db)

from seeding.staleness import OK, check_county_audit_coverage


@pytest.fixture()
def covered(db):
    _findings(db, 2025, _counties(db))
    _audits_run(
        db,
        ["2024/2025"],
        volumes={
            "discovered": 2,
            "processed": [
                "2024/2025 executives: 47 finding(s)",
                "2024/2025 assemblies: 47 finding(s)",
            ],
            "already_current": [],
            "deferred": [],
            "failed": [],
            "partial": [],
        },
    )
    assert check_county_audit_coverage(db)[0].level == OK
    return db


@pytest.mark.parametrize(
    "key,bad",
    [
        ("discovered", None),
        ("discovered", True),
        ("discovered", 0),
        ("discovered", -1),
        ("discovered", float("nan")),
        ("discovered", float("inf")),
        ("discovered", 3),
        ("processed", None),
        ("processed", {}),
        ("processed", "volume"),
        ("processed", [True]),
        ("processed", [None]),
        ("processed", [""]),
        ("already_current", True),
        ("deferred", ""),
        ("failed", None),
        ("partial", {"error": "nope"}),
    ],
)
def test_malformed_volume_reports_fail_closed(covered, key, bad):
    from models import IngestionJob

    job = covered.query(IngestionJob).one()
    meta = deepcopy(job.meta)
    meta["county_volumes"][key] = bad
    job.meta = meta
    covered.flush()
    assert check_county_audit_coverage(covered)[0].level != OK


@pytest.mark.parametrize(
    "field,bad",
    [
        ("documents", None),
        ("documents", {}),
        ("documents", [None]),
        ("documents", [{"extractions": None}]),
        ("documents", [{"extractions": []}]),
        ("documents", [{"extractions": {"partial": True}}]),
        ("documents", [{"extractions": {"partial": []}}]),
        ("documents", [{"extractions": {"partial": None}}]),
        ("documents", [{"extractions": {"partial": 0}}]),
    ],
)
def test_document_outcome_metadata_fail_closed(covered, field, bad):
    from models import IngestionJob

    job = covered.query(IngestionJob).one()
    job.meta = {**job.meta, field: bad}
    covered.flush()
    assert check_county_audit_coverage(covered)[0].level != OK


def test_duplicate_outcome_cannot_account_for_missing_volume(covered):
    from models import IngestionJob

    job = covered.query(IngestionJob).one()
    meta = deepcopy(job.meta)
    meta["county_volumes"] = {
        "discovered": 2,
        "processed": ["2024/2025 executives: 1 finding(s)"] * 2,
        "already_current": [],
        "deferred": [],
        "failed": [],
        "partial": [],
    }
    job.meta = meta
    covered.flush()
    assert check_county_audit_coverage(covered)[0].level != OK


@pytest.mark.parametrize(
    "bad", [None, False, True, 0, -1, float("nan"), float("inf"), [], {}, "bogus"]
)
def test_invalid_extraction_page_fails_closed(covered, bad):
    from models import Extraction

    ext = covered.query(Extraction).first()
    ext.extracted_json = {**ext.extracted_json, "pdf_page": bad}
    covered.flush()
    assert check_county_audit_coverage(covered)[0].level != OK


def test_three_invalid_pages_do_not_equal_valid_citation(covered):
    from models import Audit, Extraction

    audit = covered.query(Audit).first()
    ext = covered.query(Extraction).filter_by(id=audit.extraction_id).one()
    audit.page_ref = "bogus"
    ext.page_number = None
    ext.extracted_json = {**ext.extracted_json, "pdf_page": None}
    covered.flush()
    assert check_county_audit_coverage(covered)[0].level != OK


def test_geographic_county_cannot_be_inferred_from_wrong_unqualified_name(covered):
    from models import Extraction

    ext = covered.query(Extraction).first()
    ext.extracted_json = {
        **ext.extracted_json,
        "entity_name": "Elsewhere County",
        "auditee": "Elsewhere County",
    }
    covered.flush()
    assert check_county_audit_coverage(covered)[0].level != OK


def test_latest_refused_run_does_not_borrow_old_success(covered):
    from models import IngestionJob, IngestionStatus

    _audits_run(covered, ["2024/2025"], when=datetime(2026, 9, 27))
    job = covered.query(IngestionJob).order_by(IngestionJob.id.desc()).first()
    job.status = IngestionStatus.FAILED
    covered.flush()
    assert check_county_audit_coverage(covered)[0].level != OK


from test_audits_domain_county_ingest import _run as run_domain
from test_audits_domain_county_ingest import harness


def test_domain_volume_positive_control(harness):
    result = run_domain(harness["session"], 10_000)
    report = result.metadata["county_volumes"]
    assert len(report["processed"]) == 4
    assert not report["failed"] and not report["partial"]
    assert not result.errors


@pytest.mark.parametrize("outcome", ["partial", "refused", "crashed", "skipped"])
def test_domain_failure_outcomes_never_appear_processed(harness, monkeypatch, outcome):
    from seeding.domains.audits.writer import PersistenceStats
    from seeding.extractors import get_parser
    from seeding.extractors.oag_county_audit import CountyAuditError

    original = get_parser("oag_county_audit")

    def parser(session, doc, settings):
        if outcome == "refused":
            raise CountyAuditError("no_county", "no audited institution")
        if outcome == "crashed":
            raise RuntimeError("worker interrupted")
        result = original(session, doc, settings)
        if outcome == "partial":
            result["partial"] = True
        return result

    monkeypatch.setattr(
        "seeding.extractors.get_parser",
        lambda pid: parser if pid == "oag_county_audit" else None,
    )
    if outcome == "skipped":
        monkeypatch.setattr(
            "seeding.domains.audits.loader.load_blue_book_extractions",
            lambda *a, **kw: PersistenceStats(skipped=1),
        )
    result = run_domain(harness["session"], 10_000)
    report = result.metadata["county_volumes"]
    assert not report["processed"] and not report["already_current"]
    assert (
        len(report["partial"] if outcome in ("partial", "skipped") else report["failed"])
        == 4
    )


def test_invalid_parser_result_is_not_live_ingestion(harness, monkeypatch):
    from seeding import freshness

    monkeypatch.setattr("seeding.extractors.get_parser",
        lambda pid: (lambda *a: {"created": 0}) if pid == "oag_county_audit" else None)
    run_domain(harness["session"], 10_000)
    assert freshness.get("audits")["mode"] != "live"


@pytest.mark.parametrize(
    "stats",
    [
        {},
        {"created": 0},
        {"created": False},
        {"created": float("nan")},
        {"partial": []},
    ],
)
def test_domain_empty_or_malformed_statistics_do_not_certify_processed(
    harness, monkeypatch, stats
):
    monkeypatch.setattr(
        "seeding.extractors.get_parser",
        lambda pid: (lambda *a: deepcopy(stats)) if pid == "oag_county_audit" else None,
    )
    result = run_domain(harness["session"], 10_000)
    report = result.metadata["county_volumes"]
    assert not report["processed"] and not report["already_current"]


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_county",
        "wrong_year",
        "wrong_page",
        "missing_extraction",
        "wrong_document",
    ],
)
def test_wrong_attribution_does_not_count(covered, mutation):
    from models import Audit, Extraction, SourceDocument

    audit = covered.query(Audit).first()
    ext = covered.query(Extraction).filter_by(id=audit.extraction_id).one()
    if mutation == "wrong_county":
        ext.extracted_json = {
            **ext.extracted_json,
            "entity_name": "County Executive of Elsewhere",
            "auditee": "County Executive of Elsewhere",
        }
    elif mutation == "wrong_year":
        ext.extracted_json = {**ext.extracted_json, "fiscal_year": "2023/2024"}
    elif mutation == "wrong_page":
        ext.extracted_json = {**ext.extracted_json, "pdf_page": 2}
    elif mutation == "missing_extraction":
        audit.extraction_id = None
    else:
        doc = covered.query(SourceDocument).one()
        other = SourceDocument(
            country_id=doc.country_id,
            publisher=doc.publisher,
            title="other.pdf",
            url="https://www.oagkenya.go.ke/other.pdf",
            doc_type=doc.doc_type,
            status=doc.status,
            fetch_date=doc.fetch_date,
        )
        covered.add(other)
        covered.flush()
        ext.source_document_id = other.id
    covered.flush()
    assert check_county_audit_coverage(covered)[0].level != OK
