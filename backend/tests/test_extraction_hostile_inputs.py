from copy import deepcopy
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest

from models import Audit, Extraction, Entity, EntityType, PovertyIndex
from seeding.config import SeedingSettings
from seeding.types import DomainRunContext
from seeding.extractors import oag_blue_book as bb
from seeding.extractors import oag_county_volume as cv
from seeding.extractors.reconciliation import (
    IncompleteExtraction,
    ReconciliationRequired,
    extract_and_load,
)
from seeding.domains.audits.loader import load_blue_book_extractions
from tests.test_blue_book_national_walk import national_doc, _published, _legacy_rows
from tests.test_extraction_preservation import snapshot, review_for
from tests.test_oag_county_volume import TestExtractionRows as CountyFixtures


@pytest.mark.parametrize(
    "field,value",
    [
        ("page", True),
        ("page", 0),
        ("page", -1),
        ("page", None),
        ("confidence", float("nan")),
        ("confidence", float("inf")),
        ("confidence", float("-inf")),
        ("confidence", True),
        ("payload", None),
        ("payload", []),
        ("schema", "other/v1"),
        ("title", ""),
        ("paragraph_no", True),
        ("amounts", [float("nan")]),
    ],
)
def test_hostile_rows_fail_without_changing_evidence(
    db_session, national_doc, field, value
):
    _published(db_session, national_doc)
    before = snapshot(db_session, national_doc)
    rows = _legacy_rows(national_doc)
    if field == "page":
        rows[0].page_number = value
    elif field == "confidence":
        rows[0].confidence = value
    elif field == "payload":
        rows[0].extracted_json = value
    else:
        rows[0].extracted_json[field] = value
    with pytest.raises((ValueError, RuntimeError, TypeError)):
        bb.replace_extractions(
            db_session, national_doc, bb.EXTRACTOR_ID, rows, bb.blue_book_row_key
        )
    assert snapshot(db_session, national_doc) == before
    assert db_session.query(Audit).count() == 3


def test_first_partial_volume_does_not_claim_complete_or_skip_retry(
    db_session, national_doc, monkeypatch
):
    national_doc.url = "https://oag.example/COUNTY-EXECUTIVES-2024-2025.pdf"
    national_doc.meta = {
        "oag_discovery": {"fiscal_year": "2024/2025", "kind": "executives"}
    }
    for name in ("Mombasa", "Taita Taveta"):
        db_session.add(
            Entity(
                country_id=national_doc.country_id,
                canonical_name=name,
                slug=name.lower().replace(" ", "-") + "-county",
                type=EntityType.COUNTY,
            )
        )
    db_session.flush()
    monkeypatch.setattr(cv, "read_pages", lambda *a, **k: CountyFixtures.PAGES)
    parser = partial(cv.extract_county_volume, known_counties=CountyFixtures.KNOWN)
    stats, loaded = extract_and_load(
        db_session,
        national_doc,
        SeedingSettings(),
        DomainRunContext(since=None, dry_run=False),
        parser,
        load_blue_book_extractions,
    )
    with pytest.raises(IncompleteExtraction):
        parser(db_session, national_doc, None)
    assert stats["refused"]
    assert national_doc.meta.get("extracted_md5") != national_doc.md5
    assert national_doc.meta["last_extraction_attempt"]["status"] != "complete"
    assert db_session.query(Audit).count() == 4


def test_cross_extractor_schema_cannot_publish(db_session, national_doc):
    rows = _legacy_rows(national_doc)
    for row in rows:
        row.extracted_json["schema"] = "oag_county_volume/v1"

    def parser(session, doc, settings):
        return bb.replace_extractions(
            session, doc, bb.EXTRACTOR_ID, rows, bb.blue_book_row_key
        )

    try:
        result = extract_and_load(
            db_session,
            national_doc,
            SeedingSettings(),
            DomainRunContext(since=None, dry_run=False),
            parser,
            load_blue_book_extractions,
        )
    except IncompleteExtraction:
        assert db_session.query(Audit).count() == 0
        return
    print(
        "MALFORMED_PUBLISHED",
        result[0],
        [
            (a.external_reference, a.page_ref, a.publishable)
            for a in db_session.query(Audit)
        ],
    )
    pytest.fail("cross-extractor candidate schema was published as a complete run")


def test_reviewed_revision_of_non_audit_cited_row_refused(db_session, national_doc):
    _published(db_session, national_doc)
    first = db_session.query(Extraction).order_by(Extraction.id).first()
    db_session.add(PovertyIndex(year=2025, publishable=False, extraction_id=first.id))
    db_session.flush()
    before = snapshot(db_session, national_doc)
    rows = _legacy_rows(national_doc)
    rows[0].extracted_json[
        "finding_text"
    ] = "Changed meaning, still cited by another domain"
    # Even an operator review cannot revise another domain's evidence.
    review = {"source_complete": True, "reason": "reviewed"}
    with pytest.raises(bb.ExtractionStillReferenced):
        bb.replace_extractions(
            db_session,
            national_doc,
            bb.EXTRACTOR_ID,
            rows,
            bb.blue_book_row_key,
            review=review,
        )
    assert snapshot(db_session, national_doc) == before


def test_review_bound_to_current_audit_ids(db_session, national_doc):
    _published(db_session, national_doc)
    rows = _legacy_rows(national_doc)[:1]
    review = review_for(db_session, national_doc, rows)
    db_session.delete(db_session.query(Audit).first())
    db_session.flush()
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
