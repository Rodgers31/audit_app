"""A national-debt source document names the publisher of its URL (issue #274).

The writer created every document as ``record.publisher or "National Treasury
of Kenya"``, and ``real_data/national_debt.json`` declares no publisher for its
CBK Statistical Bulletin URL, so the production clone held

  1840 | National Treasury of Kenya | https://www.centralbank.go.ke/public-debt/  | CBK Public Debt Statistical Bulletin — April 2025
  2430 | National Treasury of Kenya | https://www.centralbank.go.ke/uploads/statistical_bulletin/…December 2025.pdf | Instrument register — CBK …

The writer finds a document by title and returned it untouched, so a fixed
fixture alone would not have repaired 2430. And an existing loan kept the
document it was created under, so the four CBK domestic rows (loans 381, 383,
384, 439) went on citing 1840, a title no payload names any more, while their
figures came from the current register. The data-freshness panel reads loans
through ``SourceDocument.publisher``, so on the clone the CBK row matched no
loans at all and the National Treasury row "covered" CBK's July 2025 figures.

Same pattern as #271 (revenue_by_source): the payload declares its publisher,
the writer files the declared value, corrects an existing document only when a
declaration disagrees, and keeps the old default for undeclared rows.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from models import (
    DebtCategory,
    DocumentType,
    Entity,
    EntityType,
    Loan,
    SourceDocument,
)
from sqlalchemy import select

from seeding.domains.national_debt.parser import parse_debt_payload
from seeding.domains.national_debt.writer import write_debt_records

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "seeding"
    / "real_data"
    / "national_debt.json"
)
CBK = "Central Bank of Kenya"
TREASURY_DEFAULT = "National Treasury of Kenya"
APRIL_2025_URL = "https://www.centralbank.go.ke/public-debt/"
APRIL_2025_TITLE = "CBK Public Debt Statistical Bulletin — April 2025"

# The CBK domestic rows that cite 1840 on the production clone, by lender.
DOMESTIC_LENDERS = {
    "Domestic Treasury Bonds": DebtCategory.DOMESTIC_BONDS,
    "Domestic Treasury Bills (91-day, 182-day, 364-day)": DebtCategory.DOMESTIC_BILLS,
    "CBK Overdraft Facility": DebtCategory.DOMESTIC_OVERDRAFT,
}


def _payload() -> dict:
    return json.loads(FIXTURE.read_text())


@pytest.fixture()
def national(db_session, seed_country) -> Entity:
    entity = Entity(
        country_id=seed_country.id,
        type=EntityType.NATIONAL,
        canonical_name="National Government",
        slug="national-government",
    )
    db_session.add(entity)
    db_session.flush()
    return entity


def _doc(session, title: str) -> SourceDocument:
    return session.execute(
        select(SourceDocument).where(SourceDocument.title == title)
    ).scalar_one()


def _add_doc(session, country_id, doc_id, publisher, url, title) -> SourceDocument:
    doc = SourceDocument(
        id=doc_id,
        country_id=country_id,
        publisher=publisher,
        title=title,
        url=url,
        fetch_date=datetime(2026, 2, 21, tzinfo=timezone.utc),
        doc_type=DocumentType.LOAN,
    )
    session.add(doc)
    session.flush()
    return doc


def test_the_fixture_declares_the_cbk_for_its_cbk_url():
    payload = _payload()
    assert payload["source_url"].startswith("https://www.centralbank.go.ke/")
    assert payload["publisher"] == CBK
    for record in parse_debt_payload(payload):
        assert record.publisher == CBK, record.lender


def test_the_register_is_filed_under_the_cbk(db_session, national):
    payload = _payload()
    write_debt_records(
        db_session, parse_debt_payload(payload), dataset_id="t", job_id=None
    )
    doc = _doc(db_session, payload["source_title"])
    assert doc.url == payload["source_url"]
    assert doc.publisher == CBK


def test_the_production_documents_are_corrected_in_place(
    db_session, seed_country, national
):
    """2430 is relabelled, not duplicated, and the domestic rows on 1840 move
    to the document their figures now come from."""
    payload = _payload()
    april = _add_doc(
        db_session, seed_country.id, 1840, TREASURY_DEFAULT,
        APRIL_2025_URL, APRIL_2025_TITLE,
    )
    register = _add_doc(
        db_session, seed_country.id, 2430, TREASURY_DEFAULT,
        payload["source_url"], payload["source_title"],
    )
    records = parse_debt_payload(payload)
    by_lender = {r.lender: r for r in records}
    for lender, category in DOMESTIC_LENDERS.items():
        # The figures already match the run's, as they do on a night the
        # bulletin has not moved: only the citation is wrong.
        record = by_lender[lender]
        db_session.add(
            Loan(
                entity_id=national.id,
                lender=lender,
                debt_category=category,
                principal=record.principal,
                outstanding=record.outstanding,
                issue_date=record.issue_date,
                maturity_date=record.maturity_date,
                currency="KES",
                source_document_id=april.id,
                provenance=[],
            )
        )
    db_session.flush()

    write_debt_records(db_session, records, dataset_id="t", job_id=None)

    same_title = db_session.execute(
        select(SourceDocument).where(
            SourceDocument.title == payload["source_title"]
        )
    ).scalars().all()
    assert [d.id for d in same_title] == [2430]
    assert register.publisher == CBK

    cited = {
        loan.lender: loan.source_document_id
        for loan in db_session.execute(
            select(Loan).where(Loan.lender.in_(DOMESTIC_LENDERS))
        ).scalars()
    }
    assert cited == {lender: 2430 for lender in DOMESTIC_LENDERS}


def test_a_second_identical_run_changes_nothing(db_session, national):
    """Repointing is a one-off correction, not churn on every run."""
    records = parse_debt_payload(_payload())
    write_debt_records(db_session, records, dataset_id="t", job_id=None)
    db_session.flush()  # the domain commits between runs
    created, updated = write_debt_records(
        db_session, parse_debt_payload(_payload()), dataset_id="t", job_id=None
    )
    assert (created, updated) == (0, 0)


def test_undeclared_row_never_overwrites_a_declared_publisher(
    db_session, national
):
    payload = _payload()
    write_debt_records(
        db_session, parse_debt_payload(payload), dataset_id="t", job_id=None
    )
    undeclared = {k: v for k, v in payload.items() if k != "publisher"}
    records = parse_debt_payload(undeclared)
    assert all(r.publisher is None for r in records)
    write_debt_records(db_session, records, dataset_id="t", job_id=None)

    assert _doc(db_session, payload["source_title"]).publisher == CBK


def test_a_row_with_its_own_source_does_not_inherit_the_payloads_publisher():
    """The payload's declaration is about the payload's URL. A row citing a
    different URL either declares its own publisher or declares none."""
    payload = _payload()
    ids_row = {
        **payload["loans"][0],
        "lender": "Bilateral (Japan)",
        "source_url": "https://api.worldbank.org/v2/sources/6/country/KEN",
        "source_title": "World Bank International Debt Statistics 2024",
        "publisher": "World Bank",
    }
    foreign_undeclared = {
        **payload["loans"][0],
        "lender": "Somebody else's row",
        "source_url": "https://example.org/other",
    }
    payload["loans"] = [ids_row, foreign_undeclared]
    ids, foreign = parse_debt_payload(payload)
    assert ids.publisher == "World Bank"
    assert foreign.publisher is None
