"""A parse is a candidate, not permission to remove published evidence (#322)."""
from copy import deepcopy

import pytest

from models import Audit, Extraction
from seeding.extractors import oag_blue_book as bb
from tests.test_blue_book_national_walk import national_doc, _published, _legacy_rows
from tests.test_audits_domain_county_ingest import harness


def candidates(doc):
    return _legacy_rows(doc)


def snapshot(db, doc):
    return [
        (r.id, deepcopy(r.extracted_json))
        for r in db.query(Extraction)
        .filter_by(source_document_id=doc.id)
        .order_by(Extraction.id)
    ]


@pytest.mark.parametrize(
    "mode", ["empty", "fewer", "different", "malformed", "duplicate", "truncated"]
)
def test_candidate_cannot_silently_replace_published_evidence(
    db_session, national_doc, mode
):
    _published(db_session, national_doc)
    before = snapshot(db_session, national_doc)
    audit_ids = [a.id for a in db_session.query(Audit)]
    rows = candidates(national_doc)
    if mode == "empty":
        rows = []
    elif mode == "fewer":
        rows = rows[:1]
    elif mode == "different":
        rows[1].extracted_json["paragraph_no"] = 999
    elif mode == "malformed":
        rows[1].extracted_json = {}
    elif mode == "duplicate":
        rows[1].extracted_json = deepcopy(rows[0].extracted_json)
    else:
        rows[0].extracted_json["finding_text"] = "Truncated"
    refused = False
    try:
        bb.replace_extractions(
            db_session, national_doc, bb.EXTRACTOR_ID, rows, bb.blue_book_row_key
        )
    except (ValueError, RuntimeError):
        refused = True
    assert snapshot(db_session, national_doc) == before
    assert [a.id for a in db_session.query(Audit)] == audit_ids
    assert refused, "unsafe candidate reported success"


def test_unchanged_positive_control(db_session, national_doc):
    _published(db_session, national_doc)
    before = snapshot(db_session, national_doc)
    result = bb.replace_extractions(
        db_session,
        national_doc,
        bb.EXTRACTOR_ID,
        candidates(national_doc),
        bb.blue_book_row_key,
    )
    assert result["removed"] == result["updated"] == 0
    assert snapshot(db_session, national_doc) == before


def review_for(db, doc, rows):
    from seeding.extractors.reconciliation import ReconciliationRequired

    with pytest.raises(ReconciliationRequired) as exc:
        bb.replace_extractions(db, doc, bb.EXTRACTOR_ID, rows, bb.blue_book_row_key)
    return {
        "proposal": exc.value.proposal,
        "source_complete": True,
        "reason": "Fixture source checked: obsolete table row is absent in corrected report.",
    }


def test_deliberate_reconciliation_preserves_surviving_ids(db_session, national_doc):
    _published(db_session, national_doc)
    before = snapshot(db_session, national_doc)
    rows = candidates(national_doc)[:1]
    review = review_for(db_session, national_doc, rows)
    stats = bb.replace_extractions(
        db_session,
        national_doc,
        bb.EXTRACTOR_ID,
        rows,
        bb.blue_book_row_key,
        review=review,
    )
    assert stats["removed"] == stats["audits_removed"] == 2
    assert snapshot(db_session, national_doc) == before[:1]
    assert db_session.query(Audit).count() == 1


@pytest.mark.parametrize(
    "change", ["candidate", "source", "previous", "reason", "completeness"]
)
def test_stale_or_unchecked_review_cannot_authorize_changes(
    db_session, national_doc, change
):
    from seeding.extractors.reconciliation import ReconciliationRequired

    _published(db_session, national_doc)
    rows = candidates(national_doc)[:1]
    review = review_for(db_session, national_doc, rows)
    if change == "candidate":
        rows[0].extracted_json["finding_text"] = "Different candidate"
    elif change == "source":
        from pathlib import Path

        Path(national_doc.file_path).write_bytes(b"different report")
    elif change == "previous":
        old = db_session.query(Extraction).first()
        old.extracted_json = {
            **old.extracted_json,
            "finding_text": "Corrected in another run",
        }
        db_session.flush()
    elif change == "reason":
        review["reason"] = " "
    else:
        review["source_complete"] = False
    before = snapshot(db_session, national_doc)
    with pytest.raises(ReconciliationRequired):
        bb.replace_extractions(
            db_session,
            national_doc,
            bb.EXTRACTOR_ID,
            rows,
            bb.blue_book_row_key,
            review=review,
        )
    assert snapshot(db_session, national_doc) == before


def test_loader_failure_rolls_back_replacement_and_keeps_failed_attempt(
    db_session, national_doc
):
    from types import SimpleNamespace
    from seeding.extractors.reconciliation import (
        extract_and_load,
        record_failed_attempt,
        IncompleteExtraction,
    )

    _published(db_session, national_doc)
    db_session.commit()
    before = snapshot(db_session, national_doc)
    rows = candidates(national_doc)[:1]
    review = review_for(db_session, national_doc, rows)

    def parser(db, doc, settings):
        result = bb.replace_extractions(
            db, doc, bb.EXTRACTOR_ID, rows, bb.blue_book_row_key, review=review
        )
        doc.meta = {**doc.meta, "extractor_version": 999}
        return result

    with pytest.raises(IncompleteExtraction) as exc:
        extract_and_load(
            db_session,
            national_doc,
            None,
            None,
            parser,
            lambda *a, **kw: SimpleNamespace(errors=["injected loader failure"]),
        )
    record_failed_attempt(national_doc, exc.value)
    db_session.commit()
    db_session.expire_all()
    assert snapshot(db_session, national_doc) == before
    assert db_session.query(Audit).count() == 3
    assert national_doc.meta.get("extractor_version") != 999
    assert national_doc.meta["last_extraction_attempt"]["status"] == "partial"


def test_mid_replacement_failure_is_atomic(db_session, national_doc):
    from sqlalchemy import event

    _published(db_session, national_doc)
    db_session.commit()
    before = snapshot(db_session, national_doc)
    rows = candidates(national_doc)[:1]
    review = review_for(db_session, national_doc, rows)

    def refuse_delete(mapper, connection, target):
        raise RuntimeError("injected storage failure after audit deletion")

    event.listen(Extraction, "before_delete", refuse_delete)
    try:
        with pytest.raises(RuntimeError, match="injected storage failure"):
            bb.replace_extractions(
                db_session,
                national_doc,
                bb.EXTRACTOR_ID,
                rows,
                bb.blue_book_row_key,
                review=review,
            )
    finally:
        event.remove(Extraction, "before_delete", refuse_delete)
    db_session.commit()
    assert snapshot(db_session, national_doc) == before
    assert db_session.query(Audit).count() == 3


def test_additive_findings_preserve_published_ids(db_session, national_doc):
    _published(db_session, national_doc)
    before = snapshot(db_session, national_doc)
    rows = candidates(national_doc)
    extra = candidates(national_doc)[0]
    extra.extracted_json["paragraph_no"] = 999
    extra.extracted_json["title"] = "New finding"
    rows.append(extra)
    stats = bb.replace_extractions(
        db_session, national_doc, bb.EXTRACTOR_ID, rows, bb.blue_book_row_key
    )
    assert stats["inserted"] == 1
    assert stats["removed"] == 0
    assert snapshot(db_session, national_doc)[:3] == before
    assert db_session.query(Audit).count() == 3


def test_complete_reissue_with_page_moves_needs_no_content_review(
    db_session, national_doc
):
    _published(db_session, national_doc)
    ids = [r[0] for r in snapshot(db_session, national_doc)]
    rows = candidates(national_doc)
    national_doc.md5 = "b" * 32
    for row in rows:
        row.page_number += 2
        row.extracted_json["pdf_page"] += 2
        row.extracted_json["printed_page"] += 2
    stats = bb.replace_extractions(
        db_session, national_doc, bb.EXTRACTOR_ID, rows, bb.blue_book_row_key
    )
    assert stats["updated"] == 3
    assert stats["removed"] == 0
    assert [r[0] for r in snapshot(db_session, national_doc)] == ids
    replay = bb.replace_extractions(
        db_session,
        national_doc,
        bb.EXTRACTOR_ID,
        [
            Extraction(
                source_document_id=r.source_document_id,
                extractor=r.extractor,
                page_number=r.page_number,
                confidence=r.confidence,
                extracted_json=deepcopy(r.extracted_json),
            )
            for r in rows
        ],
        bb.blue_book_row_key,
    )
    assert replay["kept"] == 3 and replay["updated"] == 0


def test_reviewed_content_correction_loads_and_replays_without_duplicate_audits(
    db_session, national_doc
):
    from seeding.extractors.reconciliation import (
        extract_and_load,
        record_failed_attempt,
        ReconciliationRequired,
    )
    from seeding.domains.audits.loader import load_blue_book_extractions
    from seeding.config import SeedingSettings
    from seeding.types import DomainRunContext

    _published(db_session, national_doc)
    audit_ids = [a.id for a in db_session.query(Audit).order_by(Audit.id)]
    rows = candidates(national_doc)
    rows[0].extracted_json["finding_text"] = "Publisher corrected this finding."
    try:
        bb.replace_extractions(
            db_session, national_doc, bb.EXTRACTOR_ID, rows, bb.blue_book_row_key
        )
    except ReconciliationRequired as exc:
        record_failed_attempt(national_doc, exc)
    db_session.commit()
    proposal = national_doc.meta["last_extraction_attempt"]["proposal"]
    assert (
        proposal["revised_rows"][0]["after"]["payload"]["finding_text"]
        == "Publisher corrected this finding."
    )
    review = {
        "proposal": proposal,
        "source_complete": True,
        "reason": "Correction verified against fixture source.",
    }

    def parser(db, doc, settings):
        return bb.replace_extractions(
            db, doc, bb.EXTRACTOR_ID, rows, bb.blue_book_row_key, review=review
        )

    for _ in range(2):
        stats, loaded = extract_and_load(
            db_session,
            national_doc,
            SeedingSettings(),
            DomainRunContext(since=None, dry_run=False),
            parser,
            load_blue_book_extractions,
        )
    assert (
        db_session.query(Audit).order_by(Audit.id).first().finding_text
        == "Publisher corrected this finding."
    )
    assert [a.id for a in db_session.query(Audit).order_by(Audit.id)] == audit_ids
    assert stats["kept"] == 3
    assert national_doc.meta["last_extraction_attempt"]["status"] == "complete"


def test_domain_refusal_persists_failed_attempt_and_returns_errors(
    harness, monkeypatch
):
    from seeding.extractors.reconciliation import ReconciliationRequired
    from tests.test_audits_domain_county_ingest import _run
    from models import SourceDocument

    def refuse(session, doc, settings):
        raise ReconciliationRequired(
            {
                "document_id": doc.id,
                "retire_ids": [123],
                "update_ids": [],
                "candidate_sha256": "fixture-hash",
            }
        )

    monkeypatch.setattr("seeding.extractors.get_parser", lambda pid: refuse)
    result = _run(harness["session"], budget=150)
    harness["session"].commit()
    assert result.errors and "reconciliation review required" in result.errors[0]
    documents = result.metadata["documents"]
    assert any(
        d.get("extraction_attempt", {}).get("status") == "partial" for d in documents
    )
    held = (
        harness["session"]
        .query(SourceDocument)
        .filter(SourceDocument.file_path.isnot(None))
        .all()
    )
    assert held and all(
        d.meta["last_extraction_attempt"]["proposal"]["candidate_sha256"]
        == "fixture-hash"
        for d in held
    )


def test_reference_added_after_review_blocks_confidence_revision(
    db_session, national_doc
):
    from models import PovertyIndex

    _published(db_session, national_doc)
    rows = candidates(national_doc)
    rows[0].confidence = 0.1
    review = review_for(db_session, national_doc, rows)
    row = db_session.query(Extraction).order_by(Extraction.id).first()
    db_session.add(PovertyIndex(year=2025, publishable=False, extraction_id=row.id))
    db_session.flush()
    with pytest.raises(bb.ExtractionStillReferenced):
        bb.replace_extractions(
            db_session,
            national_doc,
            bb.EXTRACTOR_ID,
            rows,
            bb.blue_book_row_key,
            review=review,
        )
    assert float(row.confidence) == 0.9
