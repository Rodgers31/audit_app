"""Tests for the national_debt writer's dedupe + zombie cleanup.

The writer keys on ``(entity_id, lender)`` rather than the older
``(entity_id, lender, issue_date)`` triple. National-debt loans are
synthetic aggregate buckets — adding ``issue_date`` to the dedupe key
made every new live-overlay vintage insert a fresh row alongside the
prior one, leaving zombie rows in production. These tests pin the
new behaviour so a future refactor can't silently regress it.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Iterator

import pytest
from models import (
    Base,
    Country,
    DebtCategory,
    DocumentType,
    Entity,
    EntityType,
    Loan,
    SourceDocument,
)
from seeding.domains.national_debt.parser import DebtRecord
from seeding.domains.national_debt.writer import write_debt_records
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover - dialect shim
    return "TEXT"


@pytest.fixture()
def session(tmp_path) -> Iterator[Session]:
    engine = create_engine(f"sqlite:///{tmp_path/'debt.db'}")
    Base.metadata.create_all(engine)
    Maker = sessionmaker(bind=engine)
    s = Maker()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture()
def national_entity(session: Session) -> Entity:
    """Bootstrap a Country + National Government Entity, mirroring
    what bootstrap_data.py creates in production."""
    country = Country(
        iso_code="KEN",
        name="Kenya",
        currency="KES",
        timezone="Africa/Nairobi",
        default_locale="en-KE",
    )
    session.add(country)
    session.flush()
    entity = Entity(
        country_id=country.id,
        type=EntityType.NATIONAL,
        canonical_name="National Government",
        slug="national-government",
    )
    session.add(entity)
    session.flush()
    return entity


@pytest.fixture()
def source_doc(session: Session, national_entity: Entity) -> SourceDocument:
    """A SourceDocument the staged zombie loans can attach to. The
    writer creates its own SourceDocument for live-record loans, so
    this only exists to satisfy the NOT NULL FK on the seeded
    fixture-state rows."""
    doc = SourceDocument(
        country_id=national_entity.country_id,
        publisher="Test Publisher",
        title="test bulletin",
        doc_type=DocumentType.LOAN,
        fetch_date=datetime(2024, 1, 1),
    )
    session.add(doc)
    session.flush()
    return doc


def _make_record(
    *,
    lender: str,
    outstanding: str,
    issue_date_iso: str,
    debt_category: str = "external_multilateral",
) -> DebtRecord:
    return DebtRecord(
        entity_name="National Government",
        entity_type="national",
        lender=lender,
        principal=Decimal(outstanding),
        outstanding=Decimal(outstanding),
        issue_date=datetime.fromisoformat(issue_date_iso),
        maturity_date=None,
        currency="KES",
        source_url="file://test",
        source_title="test bulletin",
        debt_category=debt_category,
        interest_rate=None,
        notes=None,
    )


class TestZombieConsolidation:
    def test_consolidates_two_existing_rows_into_one(
        self, session, national_entity, source_doc
    ):
        """Pre-existing zombies (same entity+lender, different
        issue_dates from earlier runs that keyed on the triple) must
        be collapsed to a single row on the next write."""
        # Stage two stale rows for the same lender — represents what
        # production looks like after PR #75 ran a couple of times
        # against an older fixture.
        for issue_date, outstanding in [
            (datetime(2010, 7, 1), Decimal("500000000000")),
            (datetime(2024, 1, 1), Decimal("253000000000")),
        ]:
            session.add(
                Loan(
                    entity_id=national_entity.id,
                    lender="Multilateral (World Bank / IDA / IBRD)",
                    debt_category=DebtCategory.EXTERNAL_MULTILATERAL,
                    principal=outstanding,
                    outstanding=outstanding,
                    interest_rate=Decimal("0"),
                    issue_date=issue_date,
                    currency="KES",
                    source_document_id=source_doc.id,
                )
            )
        session.flush()
        assert session.query(Loan).count() == 2

        record = _make_record(
            lender="Multilateral (World Bank / IDA / IBRD)",
            outstanding="1797000000000",  # the correct WB IDS combined value
            issue_date_iso="2024-01-01",
        )
        created, updated = write_debt_records(
            session, [record], dataset_id="national-debt", job_id=42
        )
        session.flush()

        loans = session.query(Loan).all()
        # Both zombies collapsed into the keeper row.
        assert len(loans) == 1
        assert created == 0
        assert updated == 1
        # Keeper now reflects the live value, not the partial.
        assert loans[0].outstanding == Decimal("1797000000000")

    def test_create_when_no_existing_row(self, session, national_entity):
        """First-ever seed of a brand-new lender bucket should INSERT,
        not error from the empty existing-loans list."""
        record = _make_record(
            lender="Multilateral (Brand New Lender)",
            outstanding="1000000",
            issue_date_iso="2024-07-01",
        )
        created, updated = write_debt_records(
            session, [record], dataset_id="national-debt", job_id=1
        )
        session.flush()
        assert created == 1
        assert updated == 0
        assert session.query(Loan).count() == 1

    def test_update_in_place_when_one_existing_row(
        self, session, national_entity, source_doc
    ):
        """A single existing row with a different issue_date must be
        UPDATED in place — not joined by a sibling — so the WB IDS
        date-vintage drift across runs doesn't fork rows."""
        session.add(
            Loan(
                entity_id=national_entity.id,
                lender="Multilateral (IMF — Extended Credit & Resilience Trust)",
                debt_category=DebtCategory.EXTERNAL_MULTILATERAL,
                principal=Decimal("400000000000"),
                outstanding=Decimal("400000000000"),
                interest_rate=Decimal("0"),
                issue_date=datetime(2024, 1, 1),
                currency="KES",
                source_document_id=source_doc.id,
            )
        )
        session.flush()

        record = _make_record(
            lender="Multilateral (IMF — Extended Credit & Resilience Trust)",
            outstanding="644000000000",
            # Different issue_date than the existing row — older writer
            # would have inserted a sibling here.
            issue_date_iso="2025-01-01",
        )
        created, updated = write_debt_records(
            session, [record], dataset_id="national-debt", job_id=2
        )
        session.flush()

        loans = session.query(Loan).all()
        assert len(loans) == 1
        assert created == 0
        assert updated == 1
        assert loans[0].outstanding == Decimal("644000000000")
        assert loans[0].issue_date.date().isoformat() == "2025-01-01"

    def test_no_op_when_record_unchanged(
        self, session, national_entity, source_doc
    ):
        """An identical re-write (same outstanding, same date, same
        category) shouldn't be counted as an update — ``updated``
        tracks real churn, not row touches. Provenance is also not
        appended, to avoid bloating the JSON column on no-op runs."""
        session.add(
            Loan(
                entity_id=national_entity.id,
                lender="Multilateral (World Bank / IDA / IBRD)",
                debt_category=DebtCategory.EXTERNAL_MULTILATERAL,
                principal=Decimal("1000"),
                outstanding=Decimal("1000"),
                interest_rate=Decimal("0"),
                issue_date=datetime(2024, 1, 1),
                currency="KES",
                provenance=[{"existing": "entry"}],
                source_document_id=source_doc.id,
            )
        )
        session.flush()

        record = _make_record(
            lender="Multilateral (World Bank / IDA / IBRD)",
            outstanding="1000",
            issue_date_iso="2024-01-01",
        )
        created, updated = write_debt_records(
            session, [record], dataset_id="national-debt", job_id=3
        )
        session.flush()

        assert (created, updated) == (0, 0)
        loan = session.query(Loan).one()
        assert loan.provenance == [{"existing": "entry"}]
