"""#381: persisted source metadata cannot be erased or coerced by a correction."""
from copy import deepcopy

import pytest

from models import BudgetLine, Entity, EntityType, FiscalPeriod, SourceDocument
from seeding.config import SeedingSettings
from seeding.domains.counties_budget import parser, writer
from seeding.types import DomainRunContext


BAD_METADATA = [False, 0, 1, "", "official", [], [1], [["data_quality", "official"]],
                [{"data_quality": "official"}], [["broken"]]]


def row(**changes):
    return {
        "entity_slug": "nairobi-county", "entity": "Nairobi County",
        "period_label": "2024/25", "start_date": "2024-07-01",
        "end_date": "2025-06-30", "category": "Total",
        "allocated_amount": 2000, "actual_amount": 1000,
        "source_url": "https://example.test/county-budget.pdf",
        "publisher": "Declared publisher", "source_label": "Original edition",
        "data_quality": "official", "dataset_id": "county-original",
        "artifact_sha256": "a" * 64, "page_ref": "p.42", **changes,
    }


def write(db, tmp_path, rows):
    return writer.persist_budget_records(
        db, parser.parse_budget_payload(rows), SeedingSettings(cache_path=tmp_path),
        DomainRunContext(since=None, dry_run=False),
    )


@pytest.fixture
def existing(db_session, seed_country, tmp_path):
    db_session.add(Entity(country_id=seed_country.id, type=EntityType.COUNTY,
                          slug="nairobi-county", canonical_name="Nairobi County"))
    db_session.flush()
    assert write(db_session, tmp_path, [row()]).created == 1
    db_session.flush()
    return db_session.query(SourceDocument).one()


def snapshot(db):
    source = db.query(SourceDocument).one()
    line = db.query(BudgetLine).one()
    return deepcopy((source.meta, source.title, source.publisher, source.status,
                     source.last_seen_at, line.actual_spent, line.source_hash,
                     line.provenance, line.page_ref, line.source_document_id))


@pytest.mark.parametrize("meta", BAD_METADATA)
@pytest.mark.parametrize("bad_first", [False, True])
def test_malformed_metadata_refuses_entire_batch_before_any_write(
    db_session, tmp_path, existing, meta, bad_first,
):
    existing.meta = meta
    db_session.flush()
    before = snapshot(db_session)
    new = row(source_url="https://example.test/new.pdf", category="Development")
    correction = row(actual_amount=1001, publisher="Correction publisher",
                     source_label="Reissued edition", artifact_sha256="b" * 64)
    rows = [correction, new] if bad_first else [new, correction]
    with db_session.begin_nested() as correction_transaction:
        refused = write(db_session, tmp_path, rows)
        assert refused.errors and "metadata" in refused.errors[0].lower()
        assert "object or null" in refused.errors[0].lower()
        assert (refused.processed, refused.skipped, refused.created,
                refused.updated, refused.superseded) == (2, 2, 0, 0, 0)
        # Flush even a refusal: it must leave no latent partial changes to commit.
        db_session.flush()
        db_session.expire_all()
        assert snapshot(db_session) == before
        correction_transaction.rollback()
    db_session.expire_all()
    assert snapshot(db_session) == before
    assert db_session.query(FiscalPeriod).count() == 1


@pytest.mark.parametrize("meta", BAD_METADATA)
def test_single_source_refresh_refuses_shape_without_mutating(
    db_session, seed_country, tmp_path, existing, meta,
):
    existing.meta = meta
    db_session.flush()
    before = snapshot(db_session)
    with pytest.raises(ValueError, match="metadata.*object or null"):
        writer._ensure_source_document(
            db_session, seed_country.id, SeedingSettings(cache_path=tmp_path),
            parser.parse_budget_payload([row(actual_amount=1001)])[0],
        )
    db_session.flush()
    db_session.expire_all()
    assert snapshot(db_session) == before


@pytest.mark.parametrize("meta", [None, {}, {"dataset_id": "county-original",
    "nested_evidence": {"edition": "original", "pages": [42]}, "sha256": "a" * 64}])
@pytest.mark.parametrize("digest", [None, "b" * 64])
def test_normal_official_correction_preserves_object_evidence_and_hash_semantics(
    db_session, tmp_path, existing, meta, digest,
):
    existing.meta = deepcopy(meta)
    db_session.flush()
    old_provenance = deepcopy(db_session.query(BudgetLine).one().provenance)
    result = write(db_session, tmp_path, [row(actual_amount=0,
        artifact_sha256=digest, source_label="Reissued edition",
        publisher="Correction publisher", dataset_id="county-correction")])
    db_session.flush()
    db_session.expire_all()
    source = db_session.query(SourceDocument).one()
    line = db_session.query(BudgetLine).one()
    assert result.errors == []
    assert line.actual_spent == 0
    assert line.provenance[:-1] == old_provenance
    assert source.meta["data_quality"] == "official"
    assert source.title == "Reissued edition"
    assert source.publisher == "Correction publisher"
    assert source.meta.get("sha256") == digest
    assert line.provenance[-1].get("artifact_sha256") == digest
    for key, value in (meta or {}).items():
        if key != "sha256":
            assert source.meta[key] == value
