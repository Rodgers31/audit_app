"""A gated IDS creditor pull must REPLACE external debt, not append to it.

`_replace_external_loans` rebuilds the in-memory payload only. The writer
upserts on `(entity_id, lender)` and removes duplicates of the SAME lender, so
lenders that disappear from the payload were left in the database — and the
IDS rows, which carry different names for the same debt, were inserted beside
them. External debt then appears twice in the headline and in the lender
treemap, which is what the treemap was withdrawn over in the first place.

This is a database-level test, as the review asked: it writes the fixture rows,
then writes the IDS rows, and asserts the old ones are gone.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from models import Entity, Loan
from seeding.domains.national_debt.parser import DebtRecord
from seeding.domains.national_debt.writer import write_debt_records

NATIONAL = "Republic of Kenya"


def _record(lender, category, outstanding):
    return DebtRecord(
        entity_name=NATIONAL,
        entity_type="national",
        lender=lender,
        principal=outstanding,
        outstanding=outstanding,
        issue_date=datetime(2020, 1, 1),
        maturity_date=None,
        currency="KES",
        debt_category=category,
        source_title="test",
        source_url="https://example.invalid/doc",
    )


FIXTURE_ROWS = [
    _record("Eurobonds (2014, 2018, 2019, 2021, 2024 issues)", "external_commercial", 2_276_000_000_000),
    _record("Multilateral (World Bank / IDA / IBRD)", "external_multilateral", 2_100_000_000_000),
    _record("Domestic Treasury Bonds", "domestic_bonds", 4_564_000_000_000),
]

IDS_ROWS = [
    _record("International Development Association", "external_multilateral", 1_400_000_000_000),
    _record("Eastern & Southern African Trade & Development Bank", "external_commercial", 185_000_000_000),
    _record("Domestic Treasury Bonds", "domestic_bonds", 4_564_000_000_000),
]


@pytest.fixture()
def written_fixture(db_session, seed_country):
    from models import EntityType

    # The national entity comes from bootstrap in production.
    db_session.add(
        Entity(
            country_id=seed_country.id,
            type=EntityType.NATIONAL,
            canonical_name=NATIONAL,
            slug="republic-of-kenya",
        )
    )
    db_session.commit()

    write_debt_records(db_session, FIXTURE_ROWS, dataset_id="t", job_id=None)
    db_session.commit()
    return db_session


def _external_lenders(db):
    entity = db.query(Entity).filter(Entity.canonical_name == NATIONAL).one()
    return {
        loan.lender
        for loan in db.query(Loan).filter(Loan.entity_id == entity.id).all()
        if str(getattr(loan.debt_category, "value", loan.debt_category)).startswith("external_")
    }


def test_the_replacement_removes_the_rows_it_replaces(written_fixture):
    db = written_fixture
    assert "Eurobonds (2014, 2018, 2019, 2021, 2024 issues)" in _external_lenders(db)

    write_debt_records(db, IDS_ROWS, dataset_id="t", job_id=None)
    db.commit()

    remaining = _external_lenders(db)
    assert remaining == {
        "International Development Association",
        "Eastern & Southern African Trade & Development Bank",
    }, (
        "the fixture's external rows survived beside the IDS rows, so external "
        f"debt is counted twice: {sorted(remaining)}"
    )


def test_domestic_rows_are_untouched(written_fixture):
    db = written_fixture
    write_debt_records(db, IDS_ROWS, dataset_id="t", job_id=None)
    db.commit()

    entity = db.query(Entity).filter(Entity.canonical_name == NATIONAL).one()
    domestic = [
        loan.lender
        for loan in db.query(Loan).filter(Loan.entity_id == entity.id).all()
        if not str(getattr(loan.debt_category, "value", loan.debt_category)).startswith("external_")
    ]
    assert domestic == ["Domestic Treasury Bonds"]


def test_a_run_with_no_external_rows_deletes_nothing(written_fixture):
    """A failed or ungated creditor pull must not wipe the external book."""
    db = written_fixture
    before = _external_lenders(db)

    domestic_only = [r for r in IDS_ROWS if r.debt_category == "domestic_bonds"]
    write_debt_records(db, domestic_only, dataset_id="t", job_id=None)
    db.commit()

    assert _external_lenders(db) == before, (
        "a run carrying no external rows deleted the existing external book"
    )


# ── IDS rows must be attributed to the World Bank, not to CBK ──────────────

def test_ids_creditor_rows_persist_with_world_bank_provenance(db_session, seed_country):
    """The parser reads source at PAYLOAD level, and the national-debt payload
    is a CBK/National Treasury bulletin. Without per-row provenance every IDS
    creditor was persisted as though CBK had reported it — free text in `notes`
    is not provenance a reader can follow.
    """
    from models import EntityType, SourceDocument
    from seeding.domains.national_debt.parser import parse_debt_payload
    from seeding.domains.national_debt.wb_ids_creditors import Creditor, to_loan_rows

    db_session.add(
        Entity(
            country_id=seed_country.id, type=EntityType.NATIONAL,
            canonical_name="National Government", slug="national-government",
        )
    )
    db_session.commit()

    creditors = [
        Creditor(
            name="International Development Association",
            counterpart_id="IDA",
            series="DT.DOD.MLAT.CD",
            debt_category="external_multilateral",
            usd=1_000_000_000.0,
        )
    ]
    payload = {
        # Payload-level source: the CBK bulletin the rows are merged into.
        "source_url": "https://www.centralbank.go.ke/public-debt/",
        "source_title": "CBK Public Debt Bulletin",
        "loans": to_loan_rows(creditors, 2024),
    }

    records = parse_debt_payload(payload)
    assert len(records) == 1
    write_debt_records(db_session, records, dataset_id="t", job_id=None)
    db_session.commit()

    loan = db_session.query(Loan).one()
    doc = db_session.query(SourceDocument).get(loan.source_document_id)

    assert doc.publisher == "World Bank", (
        f"IDS creditor row attributed to {doc.publisher!r}"
    )
    assert "International Debt Statistics" in doc.title, doc.title
    assert "worldbank.org" in (doc.url or ""), doc.url
