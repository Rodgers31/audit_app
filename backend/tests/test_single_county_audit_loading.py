"""Single-report county evidence must survive the parser-to-fact boundary."""

import copy
import hashlib
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from models import (
    Audit, Country, DocumentType, Entity, EntityType, Extraction, FiscalPeriod,
    SourceDocument,
)
from seeding.config import SeedingSettings
from seeding.domains.audits.loader import load_blue_book_extractions
from seeding.domains.audits.refresh_outcome import verify_outcome
from seeding.extractors import oag_county_audit as ca, oag_county_volume as cv
from seeding.extractors.reconciliation import IncompleteExtraction, extract_and_load
from seeding.pdf_artifact import ARTIFACT_KEY, BINDING_KEY, file_identity
from seeding.types import DomainRunContext
from test_oag_county_audit import BODY, HEAD
from test_oag_county_volume import _hand_made_pdf


@pytest.fixture
def source(db_session, monkeypatch, tmp_path):
    country = Country(
        name="Kenya", iso_code="KEN", currency="KES",
        timezone="Africa/Nairobi", default_locale="en-KE",
    )
    db_session.add(country)
    db_session.flush()
    county = Entity(
        country_id=country.id, type=EntityType.COUNTY,
        canonical_name="Homa Bay", slug="homa-bay-county",
    )
    db_session.add(county)
    path = tmp_path / "county.pdf"
    _hand_made_pdf(path)
    doc = SourceDocument(
        country_id=country.id, title="County Assembly of Homa Bay 2021-2022",
        publisher="Office of the Auditor-General",
        url="https://www.oagkenya.go.ke/homa-bay-2022.pdf",
        doc_type=DocumentType.AUDIT, fetch_date=datetime.now(timezone.utc),
        file_path=str(path), md5=hashlib.md5(path.read_bytes()).hexdigest(), meta={},
    )
    db_session.add(doc)
    db_session.flush()
    # The bytes are owned PDF bytes; the known report text isolates the parser
    # and persistence boundary from PDF font/renderer differences.
    monkeypatch.setattr(ca, "read_pages", lambda _path: [(1, HEAD), (2, BODY)])
    monkeypatch.setattr(cv, "read_head", lambda _path: [])
    return doc, county, path


def context(*, dry_run=False):
    return DomainRunContext(since=None, dry_run=dry_run)


def load(db, doc, *, dry_run=False):
    return load_blue_book_extractions(
        db, doc, SeedingSettings(), context(dry_run=dry_run)
    )


def extract(db, doc):
    return ca.extract_county_audit(db, doc, SeedingSettings())


def facts(db):
    return list(db.scalars(select(Audit).order_by(Audit.extraction_id)))


def payload_for_first_finding():
    result = ca.build_result(
        [(1, HEAD), (2, BODY)], known_counties={"homabay": "Homa Bay"}
    )
    return ca.finding_to_extracted_json(result.findings[0], result)


def add_extraction(db, doc, payload):
    db.add(Extraction(
        source_document_id=doc.id, page_number=2, extracted_json=payload,
        extractor=ca.EXTRACTOR_ID, confidence=.9,
    ))


def extract_and_load_atomically(db, doc):
    return extract_and_load(
        db, doc, SeedingSettings(), context(), ca.extract_county_audit,
        load_blue_book_extractions,
    )


def test_actual_four_findings_load_with_exact_amounts_and_replay(db_session, source):
    doc, county, _ = source
    first = extract(db_session, doc)
    db_session.flush()
    assert first["created"] == 4
    assert doc.meta.get("extracted_md5") == doc.md5
    verify_outcome(db_session, doc, first, ca.EXTRACTOR_ID)
    loaded = load(db_session, doc)
    assert (
        loaded.processed, loaded.created, loaded.updated, loaded.unchanged,
        loaded.skipped, loaded.errors,
    ) == (4, 4, 0, 0, 0, [])
    rows = facts(db_session)
    assert len(rows) == 4
    assert {r.entity_id for r in rows} == {county.id}
    period = db_session.get(FiscalPeriod, rows[0].period_id)
    assert period.label == "FY2021/22" and period.country_id == doc.country_id
    assert [None if r.amount is None else float(r.amount) for r in rows] == [
        None, 470385703.0, 1100678005.0, 4952549.0,
    ]
    assert rows[0].provenance[0]["amounts"] == [1122267322.0, 1177145243.0, 54877921.0]
    assert {r.provenance[0]["source"] for r in rows} == {ca.EXTRACTOR_ID}
    assert {r.provenance[0]["auditee"] for r in rows} == {"County Assembly Of Homa Bay"}
    assert all(BINDING_KEY not in r.provenance[0] for r in rows)
    assert all(r.external_reference.startswith("OAG-CA-") for r in rows)
    assert len({r.external_reference for r in rows}) == 4
    snapshot = [(r.id, r.source_hash, copy.deepcopy(r.provenance)) for r in rows]
    again = extract(db_session, doc)
    verify_outcome(db_session, doc, again, ca.EXTRACTOR_ID)
    replay = load(db_session, doc)
    assert (
        replay.processed, replay.created, replay.updated, replay.unchanged,
        replay.errors,
    ) == (4, 0, 0, 4, [])
    assert [(r.id, r.source_hash, r.provenance) for r in facts(db_session)] == snapshot
    dry = load(db_session, doc, dry_run=True)
    assert (dry.processed, dry.created, dry.updated, dry.unchanged) == (4, 0, 0, 4)


@pytest.mark.parametrize("stamp", [None, "0" * 32, "malformed", True])
def test_retained_rows_with_missing_or_stale_stamp_are_refused_atomically(
    db_session, source, monkeypatch, stamp
):
    doc, _, _ = source
    extract(db_session, doc)
    load(db_session, doc)
    db_session.flush()
    before = [
        (r.id, r.finding_text, r.source_hash, copy.deepcopy(r.provenance))
        for r in facts(db_session)
    ]
    doc.meta = {} if stamp is None else {"extracted_md5": stamp}
    db_session.flush()
    monkeypatch.setattr(
        ca, "read_pages",
        lambda _path: pytest.fail("retained evidence must not be replaced without review"),
    )
    with pytest.raises(IncompleteExtraction):
        extract_and_load_atomically(db_session, doc)
    assert doc.meta == ({} if stamp is None else {"extracted_md5": stamp})
    assert [(r.id, r.finding_text, r.source_hash, r.provenance) for r in facts(db_session)] == before
    assert db_session.query(Extraction).count() == 4


def test_changed_source_is_not_restamped_and_existing_facts_stay_intact(db_session, source):
    doc, _, _ = source
    extract(db_session, doc)
    load(db_session, doc)
    before = [(r.id, r.finding_text, r.source_hash) for r in facts(db_session)]
    old_stamp = doc.meta["extracted_md5"]
    doc.md5 = "a" * 32
    db_session.flush()
    with pytest.raises(IncompleteExtraction):
        extract_and_load_atomically(db_session, doc)
    assert doc.meta["extracted_md5"] == old_stamp
    assert [(r.id, r.finding_text, r.source_hash) for r in facts(db_session)] == before


@pytest.mark.parametrize("md5", [None, "bad", True])
def test_missing_or_malformed_digest_cannot_create_current_rows(db_session, source, md5):
    doc, _, _ = source
    doc.md5 = md5
    with pytest.raises(IncompleteExtraction):
        extract(db_session, doc)
    assert db_session.query(Extraction).count() == 0
    assert "extracted_md5" not in doc.meta


@pytest.mark.parametrize("head,body", [
    (HEAD.replace("HOMA BAY", "ATLANTIS"), BODY),
    (HEAD.replace("FOR THE YEAR ENDED 30 JUNE, 2022", "UNDATED"), BODY),
    (HEAD, "Basis for Qualified Opinion\nNo numbered findings."),
])
def test_unattributable_or_empty_reports_create_no_rows(
    db_session, source, monkeypatch, head, body
):
    doc, _, _ = source
    monkeypatch.setattr(ca, "read_pages", lambda _path: [(1, head), (2, body)])
    with pytest.raises(ca.CountyAuditError):
        extract(db_session, doc)
    assert db_session.query(Extraction).count() == 0
    assert "extracted_md5" not in doc.meta


def test_a_corrupt_page_cannot_stamp_a_partial_single_report_complete(db_session, source, monkeypatch):
    doc, _, _ = source
    monkeypatch.setattr(ca, "read_pages", lambda _path: [
        (1, HEAD), (2, BODY), (3, "(cid:3)(cid:11)(cid:82)" * 60),
    ])
    with pytest.raises(IncompleteExtraction):
        extract(db_session, doc)
    assert db_session.query(Extraction).count() == 0
    assert "extracted_md5" not in doc.meta


@pytest.mark.parametrize("change", [
    {"schema": "oag_blue_book/v1"},
    {"auditee": "National Treasury", "entity_name": "National Treasury"},
    {"county_name": "Atlantis"},
    {"county_name": "Nairobi"},
    {"auditee": "County Assembly of Nairobi"},
    {"fiscal_year": "2021/2023"},
    {"fiscal_year": ""},
])
def test_single_county_payload_never_falls_back_to_a_ministry_or_guesses_identity(
    db_session, source, change
):
    doc, county, _ = source
    payload = payload_for_first_finding()
    payload.update(change)
    add_extraction(db_session, doc, payload)
    db_session.flush()
    result = load(db_session, doc)
    assert result.processed == 1 and result.skipped == 1 and result.errors
    assert facts(db_session) == []
    assert [(e.id, e.type) for e in db_session.scalars(select(Entity))] == [
        (county.id, EntityType.COUNTY),
    ]


def test_same_name_county_from_another_country_is_refused(db_session, source):
    doc, county, _ = source
    other = Country(
        name="Other", iso_code="OTH", currency="OTH", timezone="UTC",
        default_locale="en",
    )
    db_session.add(other)
    db_session.flush()
    county.country_id = other.id
    db_session.flush()
    with pytest.raises(ca.CountyAuditError):
        extract(db_session, doc)
    assert db_session.query(Extraction).count() == 0
    # A persisted legacy payload must be refused by the loader independently.
    add_extraction(db_session, doc, payload_for_first_finding())
    db_session.flush()
    loaded = load(db_session, doc)
    assert loaded.processed == loaded.skipped == 1 and loaded.errors
    assert facts(db_session) == []


def artifact(doc, path):
    return {
        "schema_version": 1, **file_identity(path),
        "source_document_id": doc.id, "source_url": doc.url,
        "report_title": doc.title, "publisher": doc.publisher,
        "validation": "pdf_magic_and_final_eof", "verification_time": None,
        "verification_time_reason": "download_time_not_available",
    }


@pytest.mark.parametrize("timing", ["before", "during"])
def test_present_artifact_is_checked_before_and_after_read(db_session, source, monkeypatch, timing):
    doc, _, path = source
    doc.meta = {ARTIFACT_KEY: artifact(doc, path)}
    if timing == "before":
        path.write_bytes(path.read_bytes().replace(b"VISIBLE PAGE TEXT", b"CHANGED PAGE TEXT"))
    else:
        def read_and_change(_path):
            path.write_bytes(path.read_bytes().replace(b"VISIBLE PAGE TEXT", b"CHANGED PAGE TEXT"))
            return [(1, HEAD), (2, BODY)]
        monkeypatch.setattr(ca, "read_pages", read_and_change)
    with pytest.raises(IncompleteExtraction):
        extract(db_session, doc)
    assert db_session.query(Extraction).count() == 0
    assert "extracted_md5" not in doc.meta


def test_present_artifact_does_not_forge_the_volume_only_row_binding(db_session, source):
    doc, _, path = source
    identity = artifact(doc, path)
    doc.meta = {ARTIFACT_KEY: identity}
    extract(db_session, doc)
    assert doc.meta["extracted_md5"] == doc.md5
    assert doc.meta[ARTIFACT_KEY] == identity
    assert all(BINDING_KEY not in e.extracted_json for e in db_session.scalars(select(Extraction)))


def test_assembly_and_executive_restarted_sections_have_distinct_references(db_session, source):
    doc, county, _ = source
    parsed = ca.build_result(
        [(1, HEAD), (2, BODY)], known_counties={"homabay": "Homa Bay"}
    )
    for auditee in ("County Assembly Of Homa Bay", "County Executive Of Homa Bay"):
        for finding in parsed.findings:
            payload = ca.finding_to_extracted_json(finding, parsed)
            payload.update(auditee=auditee, entity_name=auditee)
            add_extraction(db_session, doc, payload)
    db_session.flush()
    loaded = load(db_session, doc)
    assert loaded.created == 8 and not loaded.errors
    rows = facts(db_session)
    assert len({r.external_reference for r in rows}) == 8
    assert {r.entity_id for r in rows} == {county.id}
