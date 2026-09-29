"""A source-backed county figure survives stale editions and fixture fallback."""

import pytest

from models import BudgetLine, Entity, EntityType, FiscalPeriod, SourceDocument
from seeding.config import SeedingSettings
from seeding.domains.counties_budget import parser, writer
from seeding.types import DomainRunContext


COB_URL = "https://cob.go.ke/download/county-report/?wpdmdl=16482"


def _row(*, period="2025/26", actual=1000, url=COB_URL, quality="official"):
    year = int(period[:4])
    return {
        "entity_slug": "nairobi-county", "entity": "Nairobi County",
        "period_label": period, "start_date": f"{year}-07-01",
        "end_date": f"{year + 1}-06-30", "category": "Revenue Receipts",
        "subcategory": "Total", "allocated_amount": 2000,
        "actual_amount": actual, "currency": "KES", "source_url": url,
        "source_label": f"CoB FY{period}", "data_quality": quality,
        "artifact_sha256": "a" * 64 if quality == "official" else None,
        "page_ref": "PDF pp. 100" if quality == "official" else None,
    }


def _write(session, tmp_path, row):
    return writer.persist_budget_records(
        session, parser.parse_budget_payload([row]),
        SeedingSettings(cache_path=tmp_path),
        DomainRunContext(since=None, dry_run=False),
    )


def test_reuploaded_older_report_cannot_retire_newer_same_url_edition(
    db_session, seed_country, tmp_path,
):
    db_session.add(Entity(country_id=seed_country.id, type=EntityType.COUNTY,
                          slug="nairobi-county", canonical_name="Nairobi County"))
    db_session.flush()
    assert _write(db_session, tmp_path, _row()).errors == []
    db_session.flush()
    before = db_session.query(BudgetLine).one()
    original_id, original_source = before.id, before.source_document_id

    stale = _write(db_session, tmp_path, _row(period="2024/25", actual=777))
    db_session.flush()
    db_session.expire_all()

    assert stale.errors and "older" in stale.errors[0].lower()
    rows = db_session.query(BudgetLine).all()
    assert len(rows) == 1
    assert rows[0].id == original_id
    assert rows[0].actual_spent == 1000
    assert rows[0].source_document_id == original_source
    assert db_session.query(FiscalPeriod).count() == 1


def test_fixture_fallback_cannot_replace_official_county_amount(
    db_session, seed_country, tmp_path,
):
    db_session.add(Entity(country_id=seed_country.id, type=EntityType.COUNTY,
                          slug="nairobi-county", canonical_name="Nairobi County"))
    db_session.flush()
    assert _write(db_session, tmp_path, _row()).errors == []
    db_session.flush()
    original = db_session.query(BudgetLine).one()
    original_id, original_source = original.id, original.source_document_id
    original_provenance = list(original.provenance)

    fixture = _write(db_session, tmp_path, _row(
        actual=9_999_999, url="file://seeding/real_data/budgets.json",
        quality="modelled",
    ))
    db_session.flush()
    db_session.expire_all()

    assert fixture.errors and "source-backed" in fixture.errors[0].lower()
    row = db_session.query(BudgetLine).one()
    assert (row.id, row.actual_spent, row.source_document_id) == (
        original_id, 1000, original_source,
    )
    assert row.provenance == original_provenance
    assert db_session.query(SourceDocument).count() == 1


def test_same_period_official_correction_still_updates(
    db_session, seed_country, tmp_path,
):
    db_session.add(Entity(country_id=seed_country.id, type=EntityType.COUNTY,
                          slug="nairobi-county", canonical_name="Nairobi County"))
    db_session.flush()
    assert _write(db_session, tmp_path, _row()).errors == []
    revised = _write(db_session, tmp_path, _row(actual=1001))
    db_session.flush()
    assert revised.errors == []
    assert db_session.query(BudgetLine).one().actual_spent == 1001


def test_fixture_new_category_cannot_downgrade_same_url_official_document(
    db_session, seed_country, tmp_path,
):
    db_session.add(Entity(country_id=seed_country.id, type=EntityType.COUNTY,
                          slug="nairobi-county", canonical_name="Nairobi County"))
    db_session.flush()
    assert _write(db_session, tmp_path, _row()).errors == []
    db_session.flush()
    source = db_session.query(SourceDocument).one()
    original_meta = dict(source.meta)

    modelled = _row(actual=99, quality="modelled")
    modelled["category"] = "Health Services"
    modelled["subcategory"] = None
    refused = _write(db_session, tmp_path, modelled)
    db_session.flush()
    db_session.expire_all()

    assert refused.errors and "source-backed" in refused.errors[0].lower()
    assert db_session.query(BudgetLine).count() == 1
    assert db_session.query(SourceDocument).one().meta == original_meta


def test_false_annual_end_date_cannot_replace_newer_official_edition(
    db_session, seed_country, tmp_path,
):
    db_session.add(Entity(country_id=seed_country.id, type=EntityType.COUNTY,
                          slug="nairobi-county", canonical_name="Nairobi County"))
    db_session.flush()
    assert _write(db_session, tmp_path, _row()).errors == []
    stale = _row(period="2024/25", actual=777)
    stale["end_date"] = "2026-06-30"
    refused = _write(db_session, tmp_path, stale)
    assert refused.errors
    assert db_session.query(BudgetLine).one().actual_spent == 1000


def test_newer_other_county_cannot_mask_stale_county_in_same_document_batch(
    db_session, seed_country, tmp_path,
):
    for slug, name in [("nairobi-county", "Nairobi County"),
                       ("mombasa-county", "Mombasa County")]:
        db_session.add(Entity(country_id=seed_country.id, type=EntityType.COUNTY,
                              slug=slug, canonical_name=name))
    db_session.flush()
    assert _write(db_session, tmp_path, _row()).errors == []
    mombasa = _row()
    mombasa["entity_slug"] = "mombasa-county"
    mombasa["entity"] = "Mombasa County"
    refused = writer.persist_budget_records(
        db_session, parser.parse_budget_payload([
            _row(period="2024/25", actual=777), mombasa,
        ]),
        SeedingSettings(cache_path=tmp_path),
        DomainRunContext(since=None, dry_run=False),
    )
    assert refused.errors
    lines = db_session.query(BudgetLine).all()
    assert len(lines) == 1 and lines[0].actual_spent == 1000


@pytest.mark.parametrize("qualities", [("official", "modelled"), ("modelled", "official")])
def test_mixed_quality_same_document_batch_is_atomic(
    db_session, seed_country, tmp_path, qualities,
):
    db_session.add(Entity(country_id=seed_country.id, type=EntityType.COUNTY,
                          slug="nairobi-county", canonical_name="Nairobi County"))
    db_session.flush()
    rows = [_row(actual=1000 if q == "official" else 999999, quality=q)
            for q in qualities]
    refused = writer.persist_budget_records(
        db_session, parser.parse_budget_payload(rows),
        SeedingSettings(cache_path=tmp_path),
        DomainRunContext(since=None, dry_run=False),
    )
    assert refused.errors
    assert db_session.query(BudgetLine).count() == 0
    assert db_session.query(SourceDocument).count() == 0


def test_older_official_interim_cannot_replace_annual_same_key(
    db_session, seed_country, tmp_path,
):
    db_session.add(Entity(country_id=seed_country.id, type=EntityType.COUNTY,
                          slug="nairobi-county", canonical_name="Nairobi County"))
    db_session.flush()
    assert _write(db_session, tmp_path, _row()).errors == []
    interim = _row(actual=900, url=COB_URL + "&quarter=3")
    interim["end_date"] = "2026-03-31"
    refused = _write(db_session, tmp_path, interim)
    assert refused.errors
    assert db_session.query(BudgetLine).one().actual_spent == 1000


def test_historical_official_provenance_survives_bad_source_metadata(
    db_session, seed_country, tmp_path,
):
    db_session.add(Entity(country_id=seed_country.id, type=EntityType.COUNTY,
                          slug="nairobi-county", canonical_name="Nairobi County"))
    db_session.flush()
    assert _write(db_session, tmp_path, _row()).errors == []
    line = db_session.query(BudgetLine).one()
    source = db_session.query(SourceDocument).one()
    source.meta = {"data_quality": "modelled"}
    line.provenance = [{"data_quality": "official"}, {"data_quality": "modelled"}]
    db_session.flush()
    fixture = _row(actual=999999, url="file://seeding/real_data/budgets.json", quality="modelled")
    refused = _write(db_session, tmp_path, fixture)
    assert refused.errors
    assert db_session.query(BudgetLine).one().actual_spent == 1000
