from datetime import datetime
from decimal import Decimal
from copy import deepcopy

import pytest
from models import Entity, EntityType, Loan, DebtCategory, SourceDocument
from seeding.domains.pending_bills.parser import PendingBillRecord
from seeding.domains.pending_bills.writer import (
    write_pending_bills,
    _get_or_create_entity,
)
from services.publication_gate import COUNTY_PENDING_BILLS_PUBLICATION


def _record(name, date, amount=100):
    return PendingBillRecord(
        entity_name=name,
        entity_type="county",
        category="county",
        fiscal_year="FY2025/26",
        total_pending=Decimal(amount),
        as_at=date,
        source_page=42,
        source_table="Table 2.10",
    )


@pytest.fixture
def counties(db_session, seed_country):
    result = []
    for name in ["Mombasa County", "Nairobi County"]:
        e = Entity(
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name=name,
            slug=name.lower().replace(" ", "-"),
        )
        db_session.add(e)
        result.append(e)
    db_session.flush()
    return result


def _write(session, records, day):
    return write_pending_bills(
        session,
        records,
        source_url=f"https://cob.go.ke/{day}.pdf",
        source_title=f"County CBIRR {day}",
        publication=COUNTY_PENDING_BILLS_PUBLICATION,
        county_table={"as_at": day, "table": "Table 2.10"},
    )


@pytest.mark.parametrize("incoming", ["2025-06-30", None, "broken"])
def test_stale_or_undated_edition_cannot_overwrite_or_retire_current_rows(
    db_session, counties, incoming
):
    _write(
        db_session,
        [_record(e.canonical_name, "2026-06-30") for e in counties],
        "2026-06-30",
    )
    before = [
        (l.id, l.outstanding, deepcopy(l.provenance), l.source_document_id)
        for l in db_session.query(Loan).all()
    ]
    docs = db_session.query(SourceDocument).count()
    with pytest.raises(ValueError):
        _write(
            db_session, [_record(counties[0].canonical_name, incoming, 50)], incoming
        )
    assert before == [
        (l.id, l.outstanding, l.provenance, l.source_document_id)
        for l in db_session.query(Loan).all()
    ]
    assert db_session.query(SourceDocument).count() == docs


def test_mixed_dates_are_rejected_before_any_write(db_session, counties):
    with pytest.raises(ValueError):
        _write(
            db_session,
            [
                _record(counties[0].canonical_name, "2026-06-30"),
                _record(counties[1].canonical_name, "2025-06-30"),
            ],
            "2026-06-30",
        )
    assert (
        db_session.query(Loan).count() == db_session.query(SourceDocument).count() == 0
    )


def test_newer_and_corrected_same_date_editions_remain_supported(db_session, counties):
    _write(
        db_session,
        [_record(e.canonical_name, "2025-06-30") for e in counties],
        "2025-06-30",
    )
    _write(
        db_session,
        [_record(counties[0].canonical_name, "2026-06-30", 75)],
        "2026-06-30",
    )
    _write(
        db_session, [_record(counties[0].canonical_name, "2026-06-30", 0)], "2026-06-30"
    )
    rows = db_session.query(Loan).order_by(Loan.entity_id).all()
    assert rows[0].outstanding == 0
    assert rows[0].provenance["publication"] == COUNTY_PENDING_BILLS_PUBLICATION
    assert rows[1].provenance["publication"] is None


def test_county_fallback_never_attaches_to_a_noncounty(db_session, seed_country):
    agency = Entity(
        country_id=seed_country.id,
        canonical_name="Mombasa County Assembly",
        type=EntityType.AGENCY,
        slug="mombasa-assembly",
    )
    db_session.add(agency)
    db_session.flush()
    assert _get_or_create_entity(db_session, "Mombasa", "county") is None


def test_county_fallback_preserves_exact_county_positive_control(db_session, counties):
    assert _get_or_create_entity(db_session, "Mombasa", "county").id == counties[0].id


def test_older_reupload_is_not_the_newest_edition():
    from seeding.domains.pending_bills.fetcher import year_end_cbirr_links

    urls = [
        f"https://cob.go.ke/download/county-governments-budget-implementation-review-report-fy-{year}/?wpdmdl={upload}"
        for year, upload in [("2025-26", 16482), ("2024-25", 99999)]
    ]
    listing = "\n".join(
        f"<a onclick=\"location.href='{url}'\">Download</a>" for url in urls
    )
    assert year_end_cbirr_links(listing)[0] == urls[0]
