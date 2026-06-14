"""Round-trip tests for the counties_budget seeding domain.

Added during the April-2026 credibility audit. These tests exercise
the full fixture → parser → writer → DB path for county budget records
and lock in the following contracts:

* The ``data_quality`` field is preserved from fixture to DB — a
  fixture self-labelled ``"estimated"`` must land as
  ``BudgetLine.provenance[].data_quality == "estimated"`` so the
  /budget/overview endpoint's trust probe can read it back.
* The writer promotes ``data_quality`` to ``"official"`` when a
  re-seed arrives with real COB data — older rows must not get
  frozen at their original estimated label.
* ``source_label`` propagates to ``SourceDocument.title`` so the UI
  can display human-readable attribution ("Controller of Budget
  County BIRR FY2024/25 Annual" vs. the generic fixture title).
* ``notes`` propagates to ``BudgetLine.notes`` so per-row caveats
  survive re-seed.
* The parser accepts both ``actual_spent`` (fixture/DB-column name)
  and ``actual_amount`` (canonical) — this was a silent drop before
  April-2026 so we lock it in.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from models import (
    Base,
    BudgetLine,
    Country,
    Entity,
    EntityType,
    FiscalPeriod,
    SourceDocument,
)
from seeding.config import SeedingSettings
from seeding.domains.counties_budget import parser as budget_parser
from seeding.domains.counties_budget import writer as budget_writer
from seeding.types import DomainRunContext
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover
    return "TEXT"


@pytest.fixture()
def sqlite_session(tmp_path) -> Iterator[Session]:
    engine = create_engine(f"sqlite:///{tmp_path/'counties_budget.db'}")
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def bootstrap(sqlite_session) -> None:
    country = Country(
        iso_code="KEN",
        name="Kenya",
        currency="KES",
        timezone="Africa/Nairobi",
        default_locale="en-KE",
    )
    sqlite_session.add(country)
    sqlite_session.flush()
    sqlite_session.add(
        Entity(
            country_id=country.id,
            type=EntityType.COUNTY,
            canonical_name="Nairobi City County",
            slug="nairobi-county",
            alt_names=["Nairobi"],
            meta={},
        )
    )
    sqlite_session.commit()


def _make_settings(tmp_path) -> SeedingSettings:
    settings = SeedingSettings(
        storage_path=tmp_path / "storage",
        cache_path=tmp_path / "cache",
        log_path=tmp_path / "logs" / "seed.log",
        retry_backoff=0.01,
        max_retries=1,
        live_pdf_fetch_enabled=False,
        enrich_with_worldbank=False,
    )
    settings.ensure_directories()
    return settings


def _estimated_payload() -> list[dict]:
    """CRA-formula-style fixture record (self-labelled estimated)."""
    return [
        {
            "entity_slug": "nairobi-county",
            "entity": "Nairobi",
            "fiscal_year": "2023/2024",
            "start_date": "2023-07-01",
            "end_date": "2024-06-30",
            "category": "Health Services",
            "allocated_amount": 5_441_872_939.72,
            # Fixture uses the DB-column name "actual_spent" — parser
            # must accept it as an alias of "actual_amount".
            "actual_spent": 4_625_591_998.76,
            "source": "Estimated based on CRA Equitable Share FY 2023/24",
            "source_url": "https://www.crakenya.org/county-allocations/",
            "data_quality": "estimated",
            "notes": "Allocation estimated using CRA formula.",
        }
    ]


def _official_payload() -> list[dict]:
    """COB C-BIRR-style payload that a later seed run would emit."""
    return [
        {
            "entity_slug": "nairobi-county",
            "entity": "Nairobi",
            "fiscal_year": "2023/2024",
            "period_label": "2023/2024",
            "start_date": "2023-07-01",
            "end_date": "2024-06-30",
            "category": "Health Services",
            "allocated_amount": 5_600_000_000.00,
            "actual_amount": 4_800_000_000.00,
            "currency": "KES",
            "source_label": "Controller of Budget County BIRR FY2023/24 Annual",
            "source_url": "https://cob.go.ke/county-birr-fy2023-24.pdf",
            "data_quality": "official",
            "notes": "Annual report, reconciled figures.",
        }
    ]


class TestParserRoundtrip:
    """The parser must preserve credibility fields and accept the
    three-alias set for actual amounts."""

    def test_estimated_fields_preserved(self):
        records = budget_parser.parse_budget_payload(_estimated_payload())
        assert len(records) == 1
        r = records[0]
        assert r.data_quality == "estimated"
        assert r.source_label == "Estimated based on CRA Equitable Share FY 2023/24"
        assert r.notes == "Allocation estimated using CRA formula."
        # Verify actual_spent alias is honoured (was silently dropped).
        assert r.actual_amount is not None
        assert float(r.actual_amount) == pytest.approx(4_625_591_998.76)

    def test_official_fields_preserved(self):
        records = budget_parser.parse_budget_payload(_official_payload())
        assert len(records) == 1
        r = records[0]
        assert r.data_quality == "official"
        assert "Controller of Budget" in (r.source_label or "")

    def test_unknown_default_when_field_absent(self):
        payload = _estimated_payload()
        payload[0].pop("data_quality")
        records = budget_parser.parse_budget_payload(payload)
        assert records[0].data_quality == "unknown"


class TestWriterPersistence:
    """The writer must surface data_quality into both SourceDocument
    meta and BudgetLine provenance, and must upgrade stale fixture
    records when a real-source seed overwrites them."""

    def test_estimated_record_persists_to_provenance(
        self, sqlite_session, bootstrap, tmp_path
    ):
        settings = _make_settings(tmp_path)
        context = DomainRunContext(since=None, dry_run=False, job_id=42)

        records = budget_parser.parse_budget_payload(_estimated_payload())
        stats = budget_writer.persist_budget_records(
            sqlite_session, records, settings, context
        )
        sqlite_session.commit()

        assert stats.created == 1
        assert stats.errors == []

        line = sqlite_session.execute(select(BudgetLine)).scalar_one()
        # Provenance JSONB carries data_quality so /budget/overview
        # can probe it without a separate join.
        assert line.provenance, "provenance should never be empty after seed"
        entry = line.provenance[0]
        assert entry["data_quality"] == "estimated"
        assert entry["ingestion_job_id"] == 42
        assert "ingested_at" in entry
        # notes round-trip.
        assert line.notes == "Allocation estimated using CRA formula."

        src = sqlite_session.execute(select(SourceDocument)).scalar_one()
        assert src.meta.get("data_quality") == "estimated"

    def test_reseed_upgrades_estimated_to_official(
        self, sqlite_session, bootstrap, tmp_path
    ):
        """A later seed run carrying real COB data must flip the
        badge — the /budget/overview probe reads source.meta and
        the freshest provenance entry."""
        settings = _make_settings(tmp_path)
        context = DomainRunContext(since=None, dry_run=False, job_id=1)

        # First pass: CRA-formula estimate.
        records = budget_parser.parse_budget_payload(_estimated_payload())
        budget_writer.persist_budget_records(
            sqlite_session, records, settings, context
        )
        sqlite_session.commit()

        # Second pass: real COB data for the same period/entity. The
        # unique constraint (entity, period, category, subcategory)
        # means this updates-in-place rather than inserting.
        context2 = DomainRunContext(since=None, dry_run=False, job_id=2)
        records2 = budget_parser.parse_budget_payload(_official_payload())
        budget_writer.persist_budget_records(
            sqlite_session, records2, settings, context2
        )
        sqlite_session.commit()

        # Still exactly one BudgetLine (upsert semantics).
        lines = sqlite_session.execute(select(BudgetLine)).scalars().all()
        assert len(lines) == 1
        line = lines[0]

        # The SourceDocument meta reflects the latest seed — this is
        # the key read path for /budget/overview's data_quality badge.
        #
        # The CRA fixture and the COB payload use different source_urls,
        # so they get separate SourceDocument rows. The newest row
        # (the COB one) must carry data_quality="official".
        srcs = sqlite_session.execute(select(SourceDocument)).scalars().all()
        cob_src = next(
            (s for s in srcs if "cob.go.ke" in (s.url or "")),
            None,
        )
        assert cob_src is not None, "expected a SourceDocument for the COB URL"
        assert cob_src.meta.get("data_quality") == "official"
        assert "Controller of Budget" in (cob_src.title or "")
        # BudgetLine is now linked to the COB source, not the stale one.
        assert line.source_document_id == cob_src.id

        # Provenance array accumulates both entries so we keep the
        # audit trail of how the row evolved.
        quals = [
            e.get("data_quality") for e in (line.provenance or []) if isinstance(e, dict)
        ]
        assert "official" in quals
        assert "estimated" in quals

    def test_fiscal_period_derived_from_dates(
        self, sqlite_session, bootstrap, tmp_path
    ):
        """Sanity check: parser + writer correctly land a FiscalPeriod
        even when the fixture label is non-canonical ('2023/2024')."""
        settings = _make_settings(tmp_path)
        context = DomainRunContext(since=None, dry_run=False)

        records = budget_parser.parse_budget_payload(_estimated_payload())
        budget_writer.persist_budget_records(
            sqlite_session, records, settings, context
        )
        sqlite_session.commit()

        fp = sqlite_session.execute(select(FiscalPeriod)).scalar_one()
        # The canonical label is FY2023/24 (two-digit tail). See
        # seeding.utils.normalize_fiscal_label.
        assert fp.label in {"FY2023/24", "2023/2024"}
        assert fp.start_date.year == 2023
        assert fp.end_date.year == 2024
