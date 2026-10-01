"""Declared pending amounts cannot become partial or invalid stored claims."""
from copy import deepcopy
from decimal import Decimal

import pytest

from models import Entity, EntityType, Loan, SourceDocument
from seeding.domains.pending_bills.parser import (
    PendingBillRecord,
    parse_pending_bills_payload,
)
from seeding.domains.pending_bills.writer import write_pending_bills
from services.publication_gate import NATIONAL_PENDING_BILLS_PUBLICATION as BROP

BAD = [-1, "NaN", "Infinity", "-Infinity", True, False, [], {}, "", "broken"]


def record(**changes):
    values = dict(
        entity_name="National Government — All MDAs",
        entity_type="national",
        category="mda",
        fiscal_year="FY2025/26",
        total_pending=Decimal(12),
        as_at="2026-06-30",
    )
    values.update(changes)
    return PendingBillRecord(**values)


def write(db, records, **changes):
    args = dict(
        source_url="https://example.invalid/session1.pdf",
        source_title="Synthetic Treasury BROP",
        publisher="Synthetic Treasury",
        publication=BROP,
    )
    args.update(changes)
    return write_pending_bills(db, records, **args)


def state(db):
    return dict(
        loans=[
            (
                r.id,
                str(r.principal),
                str(r.outstanding),
                r.source_document_id,
                deepcopy(r.provenance),
                r.updated_at,
                r.issue_date,
                r.currency,
            )
            for r in db.query(Loan).order_by(Loan.id)
        ],
        sources=[
            (r.id, r.title, r.url, r.publisher, r.fetch_date, deepcopy(r.meta))
            for r in db.query(SourceDocument).order_by(SourceDocument.id)
        ],
    )


@pytest.fixture
def national(db_session, seed_country):
    db_session.add(
        Entity(
            country_id=seed_country.id,
            type=EntityType.NATIONAL,
            canonical_name="National Government",
            slug="national",
        )
    )
    db_session.flush()


@pytest.mark.parametrize("key", ["total_national", "total_county", "grand_total"])
@pytest.mark.parametrize("amount", BAD)
def test_invalid_declared_summary_is_refused(key, amount):
    with pytest.raises(ValueError):
        parse_pending_bills_payload({"pending_bills": [], "summary": {key: amount}})


@pytest.mark.parametrize("key", ["total_national", "total_county"])
def test_summary_missing_and_printed_zero_remain_distinct(key):
    assert parse_pending_bills_payload({"summary": {key: None}}) == []
    assert parse_pending_bills_payload({"summary": {key: 0}}) == []
    parsed = parse_pending_bills_payload(
        {"summary": {key: 0, "printed_zero": True, "as_at_date": "2026-06-30"}}
    )
    assert len(parsed) == 1 and parsed[0].total_pending == 0
    assert parsed[0].as_at == "2026-06-30"


@pytest.mark.parametrize(
    "shape",
    [
        None,
        [],
        "bad",
        {"summary": []},
        {"pending_bills": {}},
        {"pending_bills": [None]},
    ],
)
def test_malformed_payload_container_is_not_empty_success(shape):
    with pytest.raises(ValueError):
        parse_pending_bills_payload(shape)


@pytest.mark.parametrize("amount", BAD)
def test_declared_item_cannot_be_salvaged_by_summary(amount):
    with pytest.raises(ValueError):
        parse_pending_bills_payload(
            {
                "pending_bills": [
                    {"entity_name": "National Government", "total_pending": amount}
                ],
                "summary": {"total_national": 100},
            }
        )


@pytest.mark.parametrize(
    "field", ["total_pending", "eligible_pending", "ineligible_pending"]
)
@pytest.mark.parametrize("amount", BAD)
def test_direct_writer_rejects_late_bad_amount_without_mutation(
    db_session, national, field, amount
):
    write(db_session, [record()])
    before = state(db_session)
    with pytest.raises(ValueError):
        write(
            db_session,
            [
                record(total_pending=Decimal(25)),
                record(category="state_corporation", **{field: amount}),
            ],
            source_url="https://example.invalid/correction.pdf",
            publisher="Changed publisher",
        )
    assert state(db_session) == before


def test_direct_writer_missing_required_total_is_refused(db_session, national):
    with pytest.raises(ValueError):
        write(db_session, [record(total_pending=None)])
    assert (
        not db_session.query(Loan).count()
        and not db_session.query(SourceDocument).count()
    )


def test_optional_missing_breakdown_and_reported_zero_survive(db_session, national):
    assert write(
        db_session,
        [
            record(
                total_pending=Decimal(0),
                eligible_pending=None,
                ineligible_pending=Decimal(0),
            )
        ],
    ) == (1, 0)
    row = db_session.query(Loan).one()
    assert row.outstanding == 0
    assert (
        "eligible_pending" not in row.provenance
        and row.provenance["ineligible_pending"] == 0
    )


@pytest.mark.parametrize("shape", [None, {}, "bad", [None], [dict(total_pending=12)]])
def test_direct_writer_malformed_records_are_refused(db_session, national, shape):
    with pytest.raises(ValueError):
        write(db_session, shape)
    assert not db_session.query(SourceDocument).count()


def test_unlabelled_fixture_still_cannot_write(db_session, national):
    assert write(db_session, [record(total_pending=Decimal(-1))], publication=None) == (
        0,
        0,
    )
    assert not db_session.query(Loan).count()


@pytest.mark.parametrize(
    "field,amount",
    [
        ("total_pending", "1,2"),
        ("eligible_pending", "1_2"),
        ("total_pending", Decimal("1e1000")),
        ("ineligible_pending", Decimal("1e1000")),
    ],
)
def test_grouping_and_storage_or_provenance_overflow_are_refused(
    db_session, national, field, amount
):
    with pytest.raises(ValueError):
        write(db_session, [record(**{field: amount})])
    assert not db_session.query(SourceDocument).count()


@pytest.mark.parametrize(
    "changes",
    [
        {"entity_type": None},
        {"category": False},
        {"fiscal_year": {}},
        {"source_url": []},
        {"source_title": {}},
        {"as_at": True},
        {"as_at": "20260630"},
        {"source_page": True},
        {"reader_notes": {}},
        {"reader_notes": [None]},
        {"source_url": "https://example.invalid/another.pdf"},
    ],
)
def test_consumed_identity_and_metadata_are_refused_before_mutation(
    db_session, national, changes
):
    write(db_session, [record()])
    before = state(db_session)
    with pytest.raises(ValueError):
        write(
            db_session,
            [
                record(total_pending=Decimal(20)),
                record(category="state_corporation", **changes),
            ]
            if "category" not in changes
            else [record(**changes)],
        )
    assert state(db_session) == before


@pytest.mark.parametrize("currency", ["USD", True, [], ""])
@pytest.mark.parametrize("container", ["payload", "summary", "item"])
def test_explicit_currency_conflict_cannot_be_written_as_kes(currency, container):
    payload = {
        "pending_bills": [{"entity_name": "National Government", "total_pending": 12}],
        "summary": {},
    }
    target = (
        payload
        if container == "payload"
        else payload["summary"]
        if container == "summary"
        else payload["pending_bills"][0]
    )
    target["currency"] = currency
    with pytest.raises(ValueError):
        parse_pending_bills_payload(payload)


def test_withheld_detail_does_not_become_summary_aggregate():
    assert (
        parse_pending_bills_payload(
            {
                "pending_bills": [
                    {"entity_name": "National Government", "total_pending": None}
                ],
                "summary": {"total_national": 100},
            }
        )
        == []
    )
