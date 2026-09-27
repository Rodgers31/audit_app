from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
from models import Audit, Extraction, PovertyIndex
from seeding.extractors import oag_blue_book as bb
from seeding.extractors.reconciliation import (
    IncompleteExtraction,
    ReconciliationRequired,
    extract_and_load,
)
from tests.test_blue_book_national_walk import national_doc, _published, _legacy_rows
from tests.test_extraction_preservation import snapshot, review_for


def apply(db, doc, rows, review=None):
    return bb.replace_extractions(
        db, doc, bb.EXTRACTOR_ID, rows, bb.blue_book_row_key, review=review
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("amounts", [3]),
        ("entity_name", "Wrong entity"),
        ("fiscal_year", "2023/2024"),
        ("opinion", "Unqualified"),
        ("severity", "CRITICAL"),
        ("finding_text", "Changed text"),
        ("confidence", 0.1),
    ],
)
def test_page_movement_does_not_cover_semantic_changes(
    db_session, national_doc, field, value
):
    _published(db_session, national_doc)
    before = snapshot(db_session, national_doc)
    rows = _legacy_rows(national_doc)
    rows[0].page_number += 10
    rows[0].extracted_json["pdf_page"] += 10
    if field == "confidence":
        rows[0].confidence = value
    else:
        rows[0].extracted_json[field] = value
    with pytest.raises(ReconciliationRequired):
        apply(db_session, national_doc, rows)
    assert snapshot(db_session, national_doc) == before


@pytest.mark.parametrize(
    "state",
    ["candidate", "source_url", "source_missing", "replayed_after_other_revision"],
)
def test_review_is_bound_after_intervening_change(db_session, national_doc, state):
    _published(db_session, national_doc)
    rows = _legacy_rows(national_doc)
    rows[0].extracted_json["finding_text"] = "Reviewed text"
    review = review_for(db_session, national_doc, rows)
    if state == "candidate":
        rows[0].extracted_json["finding_text"] = "Unreviewed text"
    elif state == "source_url":
        national_doc.url = "https://example.org/different.pdf"
    elif state == "source_missing":
        Path(national_doc.file_path).unlink()
    else:
        apply(db_session, national_doc, rows, review)
        other = _legacy_rows(national_doc)
        other[0].extracted_json["finding_text"] = "Second reviewed change"
        review2 = review_for(db_session, national_doc, other)
        apply(db_session, national_doc, other, review2)
    before = snapshot(db_session, national_doc)
    with pytest.raises((ReconciliationRequired, IncompleteExtraction)):
        apply(db_session, national_doc, rows, review)
    assert snapshot(db_session, national_doc) == before


@pytest.mark.parametrize(
    "failure",
    [
        "parser_exception",
        "loader_exception",
        "loader_none",
        "loader_no_errors",
        "loader_errors",
    ],
)
def test_wrapper_failure_rolls_back_review_and_published_rows(
    db_session, national_doc, failure
):
    _published(db_session, national_doc)
    db_session.commit()
    before = snapshot(db_session, national_doc)
    rows = _legacy_rows(national_doc)[:1]
    review = review_for(db_session, national_doc, rows)

    def parser(db, doc, settings):
        stats = apply(db, doc, rows, review)
        if failure == "parser_exception":
            raise RuntimeError("parser failure after reconciliation")
        return stats

    def loader(*args, **kwargs):
        if failure == "loader_exception":
            raise RuntimeError("loader failure")
        if failure == "loader_none":
            return None
        if failure == "loader_no_errors":
            return SimpleNamespace()
        return SimpleNamespace(errors=["cannot load"])

    with pytest.raises((RuntimeError, AttributeError, IncompleteExtraction)):
        extract_and_load(db_session, national_doc, None, None, parser, loader)
    db_session.commit()
    db_session.expire_all()
    assert snapshot(db_session, national_doc) == before
    assert db_session.query(Audit).count() == 3
    assert "last_reconciliation_review" not in national_doc.meta
    assert (
        national_doc.meta.get("last_extraction_attempt", {}).get("status") != "complete"
    )


@pytest.mark.parametrize("change", ["confidence", "payload", "page"])
def test_reference_added_after_review_blocks_mutation(db_session, national_doc, change):
    _published(db_session, national_doc)
    rows = _legacy_rows(national_doc)
    first = db_session.query(Extraction).order_by(Extraction.id).first()
    if change == "confidence":
        rows[0].confidence = 0.1
    elif change == "payload":
        rows[0].extracted_json["finding_text"] = "Changed meaning"
    else:
        rows[0].page_number += 1
        rows[0].extracted_json["pdf_page"] += 1
    review = review_for(db_session, national_doc, rows) if change != "page" else None
    db_session.add(PovertyIndex(year=2025, publishable=False, extraction_id=first.id))
    db_session.flush()
    with pytest.raises(bb.ExtractionStillReferenced):
        apply(db_session, national_doc, rows, review)


def test_partial_county_run_recovers_with_full_reference_data(
    db_session, national_doc, monkeypatch
):
    from functools import partial
    from models import Entity, EntityType
    from seeding.extractors import oag_county_volume as cv
    from seeding.domains.audits.loader import load_blue_book_extractions
    from seeding.config import SeedingSettings
    from seeding.types import DomainRunContext
    from tests.test_oag_county_volume import _volume, BODY, _FILLER

    national_doc.url = "https://oag.example/COUNTY-EXECUTIVES-2024-2025.pdf"
    national_doc.meta = {
        "oag_discovery": {"fiscal_year": "2024/2025", "kind": "executives"}
    }
    names = ["Mombasa"] + _FILLER
    pages = _volume(
        [
            (
                i + 1,
                f"County Executive of {n}",
                f"COUNTY EXECUTIVE OF {n.upper()} - NO.{i + 1}",
                BODY.format(a=2 * i + 1, b=2 * i + 2),
            )
            for i, n in enumerate(names)
        ]
    )
    monkeypatch.setattr(cv, "read_pages", lambda *a, **k: pages)
    known = {n.lower(): n for n in names[:2]}
    for n in names:
        db_session.add(
            Entity(
                country_id=national_doc.country_id,
                canonical_name=n,
                slug=n.lower() + "-county",
                type=EntityType.COUNTY,
            )
        )
    db_session.flush()
    parser = partial(cv.extract_county_volume, known_counties=known)
    context = DomainRunContext(since=None, dry_run=False)
    stats, loaded = extract_and_load(
        db_session,
        national_doc,
        SeedingSettings(),
        context,
        parser,
        load_blue_book_extractions,
    )
    assert stats["partial"] is True and loaded.created == 4
    before = snapshot(db_session, national_doc)
    known.update({n.lower(): n for n in names})
    stats, loaded = extract_and_load(
        db_session,
        national_doc,
        SeedingSettings(),
        context,
        parser,
        load_blue_book_extractions,
    )
    assert stats["partial"] is False
    assert national_doc.meta["last_extraction_attempt"]["status"] == "complete"
    assert national_doc.meta["extracted_md5"] == national_doc.md5
    assert db_session.query(Audit).count() == 22
    assert snapshot(db_session, national_doc)[:4] == before
