"""Review regressions: source units, period and active publication authority."""
from copy import deepcopy

import pytest
from models import Extraction, Loan, SourceDocument
from seeding.domains.pending_bills import aging
from services.pending_bills_aging import aging_observations
from test_pending_bills_aging_persistence import (
    payables_entries,
    populate_counties,
    source_input,
    synthetic_tables,
    write,
)


@pytest.mark.parametrize("currency", ["USD", "EUR", ""])
def test_aging_millions_require_the_explicit_kes_currency(currency):
    tables = synthetic_tables()
    for _, table in tables:
        table[0][
            1
        ] = f"County Executives Ageing analysis (Amount in {currency} Millions)"
        table[0][5] = f"Total ({currency} Millions)"
    with pytest.raises(ValueError, match="unit"):
        aging.parse_aging_tables(tables, payables_entries())


@pytest.mark.parametrize("currency", ["KES", "Ksh", "Kshs."])
def test_supported_kes_headers_preserve_source_amounts(currency):
    tables = synthetic_tables()
    for _, table in tables:
        table[0][
            1
        ] = f"County Executives Ageing analysis (Amount in {currency} Millions)"
        table[0][5] = f"Total ({currency} Millions)"
    assert (
        aging.parse_aging_tables(tables, payables_entries())["summary"]["amounts"][4]
        == "460000000"
    )


def test_aging_cohort_cannot_claim_another_fiscal_year():
    cohort = aging.parse_aging_tables(synthetic_tables(), payables_entries())
    cohort["fiscal_year"] = "FY2024/25"
    with pytest.raises(ValueError, match="source|fiscal"):
        aging.validate_cohort(cohort)


@pytest.mark.parametrize("dry_run", [False, True])
def test_aging_rejects_wrong_record_fiscal_year_atomically(
    db_session, seed_country, tmp_path, monkeypatch, dry_run
):
    populate_counties(db_session, seed_country.id)
    records, cohort = source_input(tmp_path, monkeypatch)
    for record in records:
        record.fiscal_year = "FY2024/25"
    with pytest.raises(ValueError, match="fiscal"):
        write(db_session, records, cohort, dry_run=dry_run)
    assert db_session.query(SourceDocument).count() == 0
    assert db_session.query(Loan).count() == 0


@pytest.mark.parametrize("publication", ["cob_cbirr_year_end", "unsupported"])
def test_aging_rejects_payload_when_no_county_stock_survives_filtering(
    db_session, tmp_path, monkeypatch, publication
):
    records, cohort = source_input(tmp_path, monkeypatch)
    for record in records:
        record.entity_type, record.category = "national", "mda"
    with pytest.raises(ValueError, match="county|County"):
        write(db_session, records, cohort, publication=publication)
    assert db_session.query(SourceDocument).count() == 0


def test_new_unaged_title_cannot_republish_old_cohort(
    db_session, seed_country, tmp_path, monkeypatch
):
    populate_counties(db_session, seed_country.id)
    records, cohort = source_input(tmp_path, monkeypatch)
    write(db_session, records, cohort)
    old_doc = db_session.query(SourceDocument).one()
    assert (
        aging_observations(db_session, as_at=aging.AS_AT)["county_executive"]["status"]
        == "qualified"
    )
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    new_records, _ = source_input(replacement, monkeypatch)
    write(
        db_session,
        new_records,
        None,
        source_title="B84 replacement title without aging",
    )
    assert db_session.query(SourceDocument).count() == 2
    assert (
        old_doc.meta["pending_bills_aging_v1"] is not None
    )  # Retained history, not active authority.
    assert (
        db_session.query(Extraction)
        .filter(Extraction.extractor == "pending-bills-aging-v1")
        .count()
        == 1
    )
    assert (
        aging_observations(db_session, as_at=aging.AS_AT)["county_executive"]["status"]
        == "unavailable"
    )


def test_mixed_current_stock_batch_cannot_certify_aging(
    db_session, seed_country, tmp_path, monkeypatch
):
    populate_counties(db_session, seed_country.id)
    records, cohort = source_input(tmp_path, monkeypatch)
    write(db_session, records, cohort)
    row = db_session.query(Loan).first()
    row.provenance = {**row.provenance, "publication_batch": "b" * 64}
    db_session.flush()
    assert (
        aging_observations(db_session, as_at=aging.AS_AT)["county_executive"]["status"]
        == "unavailable"
    )


def test_reader_rechecks_persisted_extraction_after_session_cached_it(
    db_session, seed_country, tmp_path, monkeypatch
):
    from sqlalchemy import update

    populate_counties(db_session, seed_country.id)
    records, cohort = source_input(tmp_path, monkeypatch)
    write(db_session, records, cohort)
    cached = (
        db_session.query(Extraction)
        .filter(Extraction.extractor == "pending-bills-aging-v1")
        .one()
    )
    assert (
        aging_observations(db_session, as_at=aging.AS_AT)["county_executive"]["status"]
        == "qualified"
    )
    changed = deepcopy(cached.extracted_json)
    changed["fiscal_year"] = "FY2024/25"
    db_session.execute(
        update(Extraction)
        .where(Extraction.id == cached.id)
        .values(extracted_json=changed)
        .execution_options(synchronize_session=False)
    )
    assert cached.extracted_json["fiscal_year"] == "FY2025/26"
    assert (
        aging_observations(db_session, as_at=aging.AS_AT)["county_executive"]["status"]
        == "unavailable"
    )


def test_nightly_workflow_forwards_aging_opt_in_with_a_false_default():
    from pathlib import Path
    import yaml

    workflow = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / ".github/workflows/seed.yml").read_text()
    )
    assert (
        workflow["env"].get("SEED_PENDING_BILLS_AGING_ENABLED")
        == "${{ vars.SEED_PENDING_BILLS_AGING_ENABLED || 'false' }}"
    )
    assert (
        workflow["env"].get("SEED_PENDING_BILLS_ASSEMBLY_AGING_ENABLED")
        == "${{ vars.SEED_PENDING_BILLS_ASSEMBLY_AGING_ENABLED || 'false' }}"
    )


def test_summary_refuses_aging_from_a_publication_replaced_after_stock_read(
    db_session, seed_country, tmp_path, monkeypatch
):
    import main
    from services import pending_bills_aging

    populate_counties(db_session, seed_country.id)
    records, cohort = source_input(tmp_path, monkeypatch)
    write(db_session, records, cohort)
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    new_records, new_cohort = source_input(replacement, monkeypatch)
    actual = pending_bills_aging.aging_observations

    def replace_before_read(db, **kwargs):
        write(db, new_records, new_cohort, source_title="B84 newly aged report title")
        return actual(db, **kwargs)

    monkeypatch.setattr(pending_bills_aging, "aging_observations", replace_before_read)
    result = main._pending_bills_summary_from_loans(db_session)
    assert result["aging_observations"]["county_executive"]["status"] == "unavailable"
