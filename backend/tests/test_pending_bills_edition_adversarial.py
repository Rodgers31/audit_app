"""Independent hostile execution of county edition and identity guards."""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal

import pytest

from models import DebtCategory, Entity, EntityType, Loan, SourceDocument
from seeding.domains.pending_bills.fetcher import year_end_cbirr_links
from seeding.domains.pending_bills.parser import PendingBillRecord
from seeding.domains.pending_bills.writer import (
    _get_or_create_entity,
    _require_forward_county_edition,
    write_pending_bills,
)
from services.publication_gate import COUNTY_PENDING_BILLS_PUBLICATION


def _record(name="Mombasa County", as_at="2026-06-30", **changes):
    values = dict(
        entity_name=name,
        entity_type="county",
        category="county",
        fiscal_year="FY2025/26",
        total_pending=Decimal(100),
        as_at=as_at,
        source_page=42,
        source_table="Table 2.10",
    )
    values.update(changes)
    return PendingBillRecord(**values)


def _write(db, records, table=None):
    return write_pending_bills(
        db,
        records,
        source_url="https://cob.go.ke/test-edition.pdf",
        source_title="Test county edition",
        publication=COUNTY_PENDING_BILLS_PUBLICATION,
        county_table=table,
    )


@pytest.fixture
def county_rows(db_session, seed_country):
    result = []
    for name, kind in [
        ("Mombasa County", EntityType.COUNTY),
        ("Nairobi County", EntityType.COUNTY),
        ("National Government", EntityType.NATIONAL),
        ("Mombasa County Assembly", EntityType.AGENCY),
    ]:
        row = Entity(
            country_id=seed_country.id,
            canonical_name=name,
            type=kind,
            slug=name.lower().replace(" ", "-"),
        )
        db_session.add(row)
        result.append(row)
    db_session.flush()
    return result


def _state(db):
    return {
        "loans": [
            (
                loan.id,
                loan.entity_id,
                loan.outstanding,
                loan.source_document_id,
                deepcopy(loan.provenance),
            )
            for loan in db.query(Loan).order_by(Loan.id).all()
        ],
        "sources": [
            (doc.id, doc.url, deepcopy(doc.meta))
            for doc in db.query(SourceDocument).order_by(SourceDocument.id).all()
        ],
    }


@pytest.mark.parametrize(
    "as_at",
    [
        None,
        "",
        "broken",
        True,
        20260630,
        date(2026, 6, 30),
        "20260630",
        "2026-06-30T00:00:00Z",
        "2026-06-31",
        "2026-03-31",
        "2026-06-30 ",
        "2026-6-30",
    ],
)
def test_malformed_or_non_year_end_dates_fail_before_mutation(
    db_session, county_rows, as_at
):
    _write(db_session, [_record()])
    before = _state(db_session)
    with pytest.raises(ValueError):
        _write(db_session, [_record(as_at=as_at)])
    assert _state(db_session) == before


@pytest.mark.parametrize(
    "table", [{}, {"as_at": "2025-06-30"}, {"as_at": True}, [], "broken", 1]
)
def test_bad_table_schema_or_conflicting_date_fails_before_mutation(
    db_session, county_rows, table
):
    _write(db_session, [_record()])
    before = _state(db_session)
    with pytest.raises((ValueError, TypeError, AttributeError)):
        _write(db_session, [_record()], table)
    assert _state(db_session) == before


@pytest.mark.parametrize("list_shape", [False, True])
def test_newer_stored_edition_blocks_old_payload_in_both_provenance_shapes(
    db_session, county_rows, list_shape
):
    _write(db_session, [_record()])
    loan = db_session.query(Loan).one()
    if list_shape:
        loan.provenance = [loan.provenance]
        db_session.flush()
    before = _state(db_session)
    with pytest.raises(ValueError, match="Stale"):
        _require_forward_county_edition(db_session, [_record(as_at="2025-06-30")], None)
    assert _state(db_session) == before


@pytest.mark.parametrize("existing_date", [None, "wrong", "2026-03-31", True])
def test_malformed_date_in_declared_current_provenance_does_not_allow_overwrite(
    db_session, county_rows, existing_date
):
    _write(db_session, [_record()])
    loan = db_session.query(Loan).one()
    loan.provenance = {**loan.provenance, "as_at": existing_date}
    db_session.flush()
    before = _state(db_session)
    with pytest.raises(ValueError):
        _write(db_session, [_record(as_at="2025-06-30")])
    assert _state(db_session) == before


def test_same_date_correction_and_newer_edition_work_with_printed_zero(
    db_session, county_rows
):
    _write(db_session, [_record(as_at="2025-06-30")])
    _write(db_session, [_record(total_pending=Decimal(50))])
    _write(db_session, [_record(total_pending=Decimal(0))])
    row = db_session.query(Loan).one()
    assert row.outstanding == 0
    assert row.provenance["as_at"] == "2026-06-30"


@pytest.mark.parametrize(
    "name",
    ["Mombasa County Assembly", "International County Institute", "%", "Mombas%"],
)
def test_county_lookup_cannot_use_institutions_national_substrings_or_wildcards(
    db_session, county_rows, name
):
    assert _get_or_create_entity(db_session, name, "county") is None


@pytest.mark.parametrize("entity_type", ["county", "COUNTY", "County"])
def test_case_normalized_entity_type_keeps_county_fallback(
    db_session, county_rows, entity_type
):
    row = _get_or_create_entity(db_session, "Mombasa", entity_type)
    assert row is not None and row.id == county_rows[0].id


@pytest.mark.parametrize(
    "records",
    [
        [_record("National Government", entity_type="national")],
        [_record("Mombasa County Assembly", entity_type="agency")],
        [_record("Unknown County")],
    ],
)
def test_unresolved_or_wrong_type_county_input_cannot_retire_existing_counties(
    db_session, county_rows, records
):
    _write(db_session, [_record(), _record("Nairobi County")])
    before = _state(db_session)
    try:
        _write(db_session, records)
    except ValueError:
        pass
    assert _state(db_session) == before


def test_late_unknown_county_cannot_partially_update_then_retire_current_rows(
    db_session, county_rows
):
    _write(db_session, [_record(), _record("Nairobi County")])
    before = _state(db_session)
    try:
        _write(
            db_session, [_record(total_pending=Decimal(50)), _record("Unknown County")]
        )
    except ValueError:
        pass
    assert _state(db_session) == before


def test_late_malformed_record_schema_cannot_leave_partial_update(
    db_session, county_rows
):
    _write(db_session, [_record(), _record("Nairobi County")])
    before = _state(db_session)
    with pytest.raises((ValueError, TypeError)):
        _write(
            db_session,
            [
                _record(total_pending=Decimal(50)),
                _record("Nairobi County", reader_notes=[42]),
            ],
        )
    assert _state(db_session) == before


def _url(slug, upload):
    return f"https://cob.go.ke/download/county-governments-budget-implementation-review-report-{slug}/?wpdmdl={upload}"


def _listing(urls):
    return "\n".join(f'<a href="{url}">Download</a>' for url in urls)


@pytest.mark.parametrize(
    "new_slug", ["fy-2025-26", "financial-year-2025-26", "fy-2025-2026"]
)
def test_supported_fiscal_year_styles_beat_older_high_upload_ids(new_slug):
    new, old = _url(new_slug, 10), _url("fy-2024-25", 99999)
    assert year_end_cbirr_links(_listing([old, new])) == [new, old]


def test_discovery_year_order_is_case_insensitive():
    new, old = _url("FY-2025-26", 10), _url("fy-2024-25", 99999)
    assert year_end_cbirr_links(_listing([old, new])) == [new, old]


def test_quarterlies_are_excluded_duplicates_removed_and_upload_breaks_same_year_tie():
    first, second = _url("fy-2025-26", 10), _url("financial-year-2025-26", 20)
    quarterly = _url("first-quarter-fy-2026-27", 100000)
    assert year_end_cbirr_links(_listing([first, quarterly, second, first])) == [
        second,
        first,
    ]


def test_empty_guard_input_does_not_certify_an_edition(db_session):
    with pytest.raises(ValueError):
        _require_forward_county_edition(db_session, [], None)
