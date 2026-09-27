"""Execute the writer/reader boundary against incomplete publication editions.

The complete control traverses the same payload converters, parser and writer
as the bad batches. Synthetic amounts exercise accounting, not source claims.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models import Entity, EntityType, Loan
from seeding.domains.pending_bills import brop_parser
from seeding.domains.pending_bills.fetcher import (
    _brop_result_to_payload,
    check_county_payables_entries,
    county_payables_payload,
)
from seeding.domains.pending_bills.parser import parse_pending_bills_payload
from seeding.domains.pending_bills.writer import write_pending_bills
from seeding.pdf_parsers import KENYAN_COUNTIES

DAY = "2026-06-30"
BROP_A = "https://www.treasury.go.ke/brop-2026.pdf"
BROP_B = "https://www.treasury.go.ke/brop-2026-corrected.pdf"
COB = "https://cob.go.ke/download/county-fy-2025-26/?wpdmdl=1"


@pytest.fixture
def publication_entities(db_session, seed_country):
    for name, kind in [("National Government", EntityType.NATIONAL)] + [
        (f"{name} County", EntityType.COUNTY) for name in KENYAN_COUNTIES
    ]:
        db_session.add(Entity(
            country_id=seed_country.id, canonical_name=name, type=kind,
            slug=name.lower().replace(" ", "-"),
        ))
    db_session.flush()


def _national_payload(sc=100, mda=200, url=BROP_A):
    page = MagicMock()
    page.extract_text.return_value = (
        f"18. The total outstanding National Government pending bills as at "
        f"30th June 2026 amounted to KSh {sc + mda} billion. These comprise "
        f"of KSh {sc} billion and KSh {mda} billion for the State Corporations "
        "and MDAs, respectively."
    )
    national = brop_parser._detect_national_paragraph(
        SimpleNamespace(pages=[page]), "FY 2025/26"
    )
    assert national is not None
    return _brop_result_to_payload(
        SimpleNamespace(national=national, counties=[], fiscal_year_label="FY 2025/26"),
        url,
    )


def _county_payload(withheld=False):
    entries = [dict(
        county=name, status="reported", withheld_reason=None,
        total_millions="0" if index == 0 else "1", assembly_printed=True,
        cob_marked_inconsistent=False, chapter_total_millions=None,
        chapter_table=None, chapter_page=None, as_at=DAY,
        fiscal_year="FY 2025/26", table="Table 2.10", page=42,
    ) for index, name in enumerate(KENYAN_COUNTIES)]
    if withheld:
        entries[-1].update(status="withheld", withheld_reason="unreconciled")
    # This is the real live-fetch entry gate, before payload conversion.
    check_county_payables_entries(entries, COB)
    return county_payables_payload(entries, COB)


def _write(db, payload):
    records = parse_pending_bills_payload(payload)
    result = write_pending_bills(
        db, records, source_url=payload["source_url"],
        source_title=payload["source_title"], publication=payload["publication"],
        publisher=payload["publisher"], county_table=payload.get("county_table"),
    )
    db.flush()
    return records, result


def _published(db):
    from main import _published_pending_bills
    return _published_pending_bills(db)


def test_complete_same_day_editions_publish_and_preserve_a_county_zero(
    db_session, publication_entities,
):
    _write(db_session, _national_payload())
    records, result = _write(db_session, _county_payload())
    rows, totals = _published(db_session)
    assert result == (47, 0)
    assert len(records) == 47 and len(rows) == 49
    assert sum(amount == 0 for _loan, _name, _kind, amount in rows) == 1
    assert totals["national"] == 300_000_000_000
    assert totals["county"] == 46_000_000
    assert totals["total"] == 300_046_000_000


def test_one_national_half_cannot_certify_a_combined_total(
    db_session, publication_entities,
):
    payload = _national_payload()
    payload["pending_bills"] = payload["pending_bills"][:1]
    _write(db_session, payload)
    _write(db_session, _county_payload())
    _rows, totals = _published(db_session)
    assert totals["total"] is None


def test_county_withheld_by_live_entry_gate_cannot_certify_a_combined_total(
    db_session, publication_entities,
):
    _write(db_session, _national_payload())
    records, result = _write(db_session, _county_payload(withheld=True))
    assert result == (46, 0) and len(records) == 46
    rows, totals = _published(db_session)
    assert len(rows) == 48  # Valid individual rows remain available.
    assert totals["total"] is None


def test_partial_same_day_national_correction_cannot_mix_artifacts(
    db_session, publication_entities,
):
    _write(db_session, _national_payload())
    _write(db_session, _county_payload())
    corrected = _national_payload(sc=150, mda=250, url=BROP_B)
    corrected["pending_bills"] = corrected["pending_bills"][:1]
    _write(db_session, corrected)
    rows, totals = _published(db_session)
    assert len({loan.provenance["source_url"] for loan, _n, kind, _a in rows if kind == "national"}) == 2
    assert totals["total"] is None


def test_publisher_zero_national_half_replaces_previous_figure(
    db_session, publication_entities,
):
    _write(db_session, _national_payload())
    _write(db_session, _county_payload())
    # No mutilated payload: actual BROP paragraph -> converter -> parser ->
    # writer. A valid printed zero must replace the previous 100B half.
    corrected = _national_payload(sc=0, mda=300, url=BROP_B)
    assert len(corrected["pending_bills"]) == 2
    _write(db_session, corrected)
    _rows, totals = _published(db_session)
    assert totals["national"] == 300_000_000_000
    assert totals["total"] == 300_046_000_000
    assert db_session.query(Loan).filter(Loan.outstanding == 0).count() == 2


def _complete(db):
    _write(db, _national_payload())
    _write(db, _county_payload())
    rows, totals = _published(db)
    assert totals["total"] == 300_046_000_000
    return rows


def test_partial_same_url_correction_has_a_different_batch_and_no_total(
    db_session, publication_entities,
):
    _complete(db_session)
    corrected = _national_payload(sc=150, mda=250, url=BROP_A)
    corrected["pending_bills"] = corrected["pending_bills"][:1]
    _write(db_session, corrected)
    rows, totals = _published(db_session)
    national = [loan for loan, _n, kind, _a in rows if kind == "national"]
    assert len({loan.source_document_id for loan in national}) == 1
    assert len({loan.provenance["source_url"] for loan in national}) == 1
    assert len({loan.provenance["publication_batch"] for loan in national}) == 2
    assert totals["national"] is None
    assert totals["total"] is None


@pytest.mark.parametrize("field,value", [
    ("publication_batch", "f" * 64),
    ("source_url", "https://cob.go.ke/another-edition.pdf"),
    ("as_at", "2025-06-30"),
])
def test_mixed_county_editions_never_form_a_county_or_combined_total(
    db_session, publication_entities, field, value,
):
    rows = _complete(db_session)
    county = next(loan for loan, _n, kind, _a in rows if kind == "county")
    county.provenance = {**county.provenance, field: value}
    db_session.flush()
    kept, totals = _published(db_session)
    assert len(kept) == 49
    assert totals["national"] == 300_000_000_000
    assert totals["county"] is None
    assert totals["total"] is None


def test_47_rows_with_duplicate_county_identity_are_incomplete(
    db_session, publication_entities,
):
    rows = _complete(db_session)
    counties = [loan for loan, _n, kind, _a in rows if kind == "county"]
    counties[-1].entity_id = counties[0].entity_id
    db_session.flush()
    kept, totals = _published(db_session)
    assert len(kept) == 49  # Mere row count is unchanged.
    assert totals["coverage"]["county_complete"] is False
    assert totals["county"] is None
    assert totals["total"] is None


@pytest.mark.parametrize("value", [None, "", " ", True, 1, [], {}, "not-a-sha256", "a" * 63, "g" * 64])
def test_malformed_batch_metadata_withholds_totals_without_crashing(
    db_session, publication_entities, value,
):
    rows = _complete(db_session)
    for loan, _n, kind, _a in rows:
        if kind == "national":
            loan.provenance = {**loan.provenance, "publication_batch": value}
    db_session.flush()
    kept, totals = _published(db_session)
    assert len(kept) == 49
    assert totals["national"] is None
    assert totals["total"] is None


def test_absent_batch_metadata_does_not_certify_a_legacy_total(
    db_session, publication_entities,
):
    rows = _complete(db_session)
    for loan, _n, _kind, _a in rows:
        loan.provenance = {
            key: value for key, value in loan.provenance.items()
            if key != "publication_batch"
        }
    db_session.flush()
    kept, totals = _published(db_session)
    assert len(kept) == 49
    assert totals["national"] is None
    assert totals["county"] is None
    assert totals["total"] is None


def _complete_splits(db):
    from main import _pending_bills_summary_from_loans
    rows = _complete(db)
    for loan, _n, _kind, amount in rows:
        loan.provenance = {
            **loan.provenance,
            "eligible_pending": amount / 2,
            "ineligible_pending": amount / 2,
        }
    db.flush()
    summary = _pending_bills_summary_from_loans(db)
    assert summary["eligible_total"] == summary["ineligible_total"] == 150_023_000_000
    return rows


@pytest.mark.parametrize("key", ["eligible_pending", "ineligible_pending"])
@pytest.mark.parametrize("missing", [None, True, -1, "NaN", "Infinity", [], {}])
def test_partial_or_malformed_split_is_not_a_complete_population_total(
    db_session, publication_entities, key, missing,
):
    from main import _pending_bills_summary_from_loans
    rows = _complete_splits(db_session)
    loan = rows[-1][0]
    loan.provenance = {**loan.provenance, key: missing}
    db_session.flush()
    summary = _pending_bills_summary_from_loans(db_session)
    assert summary["total_pending_amount"] == 300_046_000_000
    assert summary["eligible_total" if key == "eligible_pending" else "ineligible_total"] is None
