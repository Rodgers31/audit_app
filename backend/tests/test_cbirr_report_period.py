"""The CBIRR is filed under the period its cover names, and moves with the publisher.

Issue #238 §2. ``CoBQuarterlyReportParser`` read the fiscal year out of the
PDF's FILENAME and fell back to a hardcoded ``"2024/25"``. The fetcher hands it
a file from the PDF cache, whose name is a sha256, so the fallback fired every
time: the Controller of Budget's report for the first nine months of FY2025/26
landed in production as FY2024/25 (188 rows, source document 2388), and every
later edition would have upserted onto the same rows because the upsert key
includes the period.

These tests pin three things:

* the period comes from the report's cover, sub-period included;
* the fetcher files a part-year report under ``FY2025/26 9M`` with a
  31 March end date, never under the bare year;
* re-parsing a document that was filed under the wrong period removes the stale
  copy — and nothing else.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator
from unittest.mock import patch

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
from seeding.domains.counties_budget import fetcher as cb_fetcher
from seeding.domains.counties_budget import parser as budget_parser
from seeding.domains.counties_budget import writer as budget_writer
from seeding.pdf_parsers import (
    CoBQuarterlyReportParser,
    ExtractedTable,
    detect_cob_report_period,
)
from seeding.types import DomainRunContext
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover
    return "TEXT"


#: The cover of the report production holds, as pdfplumber reads it (page 1).
NINE_MONTH_COVER = (
    "Office of the\nController of Budget\nBudget Oversight for Transparency\n"
    "COUNTY GOVERNMENTS\nBUDGET\nIMPLEMENTATION\nREVIEW REPORT\n"
    "FIRST NINE MONTHS OF FY 2025/26\nMAY, 2026"
)

#: The name the PDF cache gives that file — what the parser actually receives.
CACHED_NAME = "6ddc3527da566a4cad6b93d2feade2a1698072320d8dd1160ce19baf14e9b20f.pdf"

CBIRR_URL = (
    "https://cob.go.ke/download/county-governments-budget-implementation-"
    "review-report-for-the-first-nine-months-of-fy-2025-26/?wpdmdl=16378"
)


class TestCoverPeriod:
    @pytest.mark.parametrize(
        "cover, expected",
        [
            (NINE_MONTH_COVER, ("2025/26", "9M")),
            ("COUNTY GOVERNMENTS BUDGET IMPLEMENTATION REVIEW REPORT\n"
             "FIRST SIX MONTHS OF FY 2025/26", ("2025/26", "H1")),
            ("COUNTY BUDGET IMPLEMENTATION REVIEW REPORT\n"
             "FIRST QUARTER OF FY 2024/2025", ("2024/25", "Q1")),
            ("ANNUAL COUNTY GOVERNMENTS BUDGET IMPLEMENTATION REVIEW REPORT\n"
             "FY 2024/25", ("2024/25", None)),
        ],
    )
    def test_the_cover_names_the_period(self, cover, expected):
        assert detect_cob_report_period(cover) == expected

    @pytest.mark.parametrize("cover", ["", "BUDGET REPORT MAY 2026", "FY 2025/27"])
    def test_an_unreadable_cover_names_nothing(self, cover):
        assert detect_cob_report_period(cover) == (None, None)

    def test_the_full_year_cover_is_read_without_an_fy_token(self):
        """The FY2025/26 annual CBIRR's cover (August 2026) says "FOR THE
        FINANCIAL YEAR 2025/26" — no "FY". Found by adversarial pass: it was
        only ever read off the foreword on page 3."""
        cover = (
            "Office of the\nController of Budget\nCOUNTY GOVERNMENTS\nBUDGET\n"
            "IMPLEMENTATION\nREVIEW REPORT\nFOR THE FINANCIAL YEAR 2025/26\nAUGUST, 2026"
        )
        assert detect_cob_report_period(cover) == ("2025/26", None)

    def test_the_period_phrase_names_the_year_not_the_first_year_mentioned(self):
        text = (
            "Revenue rose compared to FY 2024/25. COUNTY BUDGET IMPLEMENTATION "
            "REVIEW REPORT FOR THE FIRST QUARTER OF FY 2025/26"
        )
        assert detect_cob_report_period(text) == ("2025/26", "Q1")

    @pytest.mark.parametrize(
        "cover",
        ["REVIEW REPORT THIRD QUARTER FY 2025/26", "SECOND QUARTER OF FY 2025/26",
         "FIRST EIGHT MONTHS OF FY 2025/26"],
    )
    def test_a_part_year_it_cannot_name_is_refused_not_read_as_a_full_year(self, cover):
        """Read as a full year, a quarterly report would be filed over — and
        overwrite — the annual one."""
        assert detect_cob_report_period(cover) == (None, None)


def _fake_pdf(cover_text: str):
    page = SimpleNamespace(extract_text=lambda: cover_text)
    pdf = SimpleNamespace(pages=[page], __enter__=None)

    class _Ctx:
        def __enter__(self):
            return pdf

        def __exit__(self, *exc):
            return False

    return lambda _path: _Ctx()


def _consolidated_table() -> ExtractedTable:
    return ExtractedTable(
        page_number=1,
        table_index=0,
        headers=["County", "Allocated", "Absorbed", "Rate"],
        rows=[["Nairobi", "44,620.89", "32,122.66", "72.0"]],
        bbox=(0, 0, 0, 0),
    )


class TestParserReadsPagesInOrder:
    def test_the_cover_wins_over_a_foreword_that_names_another_year(self):
        pages = [
            "COUNTY GOVERNMENTS BUDGET IMPLEMENTATION REVIEW REPORT\n"
            "FOR THE FINANCIAL YEAR 2025/26",
            "",
            "FOREWORD In FY 2024/25 counties collected ...",
        ]
        parser = CoBQuarterlyReportParser(Path(CACHED_NAME))
        with patch("seeding.pdf_parsers.pdfplumber.open", _fake_pages(pages)):
            assert parser._report_period() == ("2025/26", None)


def _fake_pages(texts):
    pdf = SimpleNamespace(pages=[SimpleNamespace(extract_text=(lambda t=t: t)) for t in texts])

    class _Ctx:
        def __enter__(self):
            return pdf

        def __exit__(self, *exc):
            return False

    return lambda _path: _Ctx()


class TestParserReadsTheCover:
    def test_a_cached_file_is_filed_under_its_cover_period(self):
        """The file the fetcher passes is named by its digest, not its period."""
        parser = CoBQuarterlyReportParser(Path(CACHED_NAME))
        with patch(
            "seeding.pdf_parsers.extract_all_tables",
            return_value=[_consolidated_table()],
        ), patch("seeding.pdf_parsers.pdfplumber.open", _fake_pdf(NINE_MONTH_COVER)):
            records = parser.parse()

        assert records, "the consolidated table should parse"
        assert {r["fiscal_year"] for r in records} == {"2025/26"}
        assert {r["quarter"] for r in records} == {"9M"}

    def test_no_readable_period_is_none_not_a_default_year(self):
        parser = CoBQuarterlyReportParser(Path(CACHED_NAME))
        with patch(
            "seeding.pdf_parsers.extract_all_tables",
            return_value=[_consolidated_table()],
        ), patch("seeding.pdf_parsers.pdfplumber.open", _fake_pdf("")):
            records = parser.parse()

        assert {r["fiscal_year"] for r in records} == {None}


def _settings(tmp_path) -> SeedingSettings:
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


def _parsed(category: str, allocated: str, absorbed: str, fy="2025/26", sub="9M"):
    return {
        "county": "Nairobi",
        "category": category,
        "subcategory": None,
        "allocated": Decimal(allocated),
        "absorbed": Decimal(absorbed),
        "absorption_rate": None,
        "currency": "KES",
        "quarter": sub,
        "fiscal_year": fy,
    }


def _fetch(tmp_path, parsed):
    settings = _settings(tmp_path)
    cached = tmp_path / CACHED_NAME
    cached.write_bytes(b"%PDF-1.4")
    with patch("seeding.pdf_download.get_or_download_pdf", return_value=cached), patch(
        "seeding.parse_cache.parse_with_cache", return_value=parsed
    ):
        return cb_fetcher._download_and_parse_county_pdf(None, CBIRR_URL, settings)


class TestFetcherFilesTheSubPeriod:
    def test_a_nine_month_report_is_filed_under_its_own_period(self, tmp_path):
        records = _fetch(tmp_path, [_parsed("Total", "44620.89", "32122.66")])

        assert [r["period_label"] for r in records] == ["2025/26 9M"]
        assert records[0]["start_date"] == "2025-07-01"
        assert records[0]["end_date"] == "2026-03-31"
        assert records[0]["source_label"] == (
            "Controller of Budget County BIRR FY2025/26 9M"
        )

    def test_a_full_year_report_keeps_the_bare_year(self, tmp_path):
        records = _fetch(tmp_path, [_parsed("Total", "1", "1", sub=None)])
        assert [r["period_label"] for r in records] == ["2025/26"]
        assert records[0]["end_date"] == "2026-06-30"

    def test_a_report_with_no_period_is_dropped(self, tmp_path):
        assert _fetch(tmp_path, [_parsed("Total", "1", "1", fy=None)]) is None


# --------------------------------------------------------------------------
# the writer: a re-filed document leaves no copy behind
# --------------------------------------------------------------------------


@pytest.fixture()
def session(tmp_path) -> Iterator[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'period.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    country = Country(
        iso_code="KEN", name="Kenya", currency="KES",
        timezone="Africa/Nairobi", default_locale="en-KE",
    )
    s.add(country)
    s.flush()
    s.add(Entity(
        country_id=country.id, type=EntityType.COUNTY,
        canonical_name="Nairobi City County", slug="nairobi-county",
        alt_names=["Nairobi"], meta={},
    ))
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _seed_mislabelled_production_state(s: Session) -> None:
    """What production holds: the CBIRR under FY2024/25, beside another doc."""
    kenya = s.query(Country).one()
    nairobi = s.query(Entity).one()
    fy2425 = FiscalPeriod(
        country_id=kenya.id, label="FY2024/25",
        start_date=datetime(2024, 7, 1, tzinfo=timezone.utc),
        end_date=datetime(2025, 6, 30, tzinfo=timezone.utc),
    )
    cbirr = SourceDocument(
        country_id=kenya.id, publisher="Controller of Budget",
        title="Controller of Budget County BIRR 2024/25", url=CBIRR_URL,
        fetch_date=datetime.now(timezone.utc), doc_type="BUDGET",
    )
    other = SourceDocument(
        country_id=kenya.id, publisher="Controller of Budget",
        title="CoB County Budget Implementation Review Report FY2024/25 H1",
        url="https://cob.go.ke/reports/consolidated-county-budget-implementation-review-reports/",
        fetch_date=datetime.now(timezone.utc), doc_type="BUDGET",
    )
    s.add_all([fy2425, cbirr, other])
    s.flush()
    for cat, alloc in (("Total", 44_620_890_000), ("Own Source Revenue", 21_178_050_000)):
        s.add(BudgetLine(
            entity_id=nairobi.id, period_id=fy2425.id, category=cat,
            allocated_amount=Decimal(alloc), actual_spent=Decimal(1),
            currency="KES", source_document_id=cbirr.id, provenance=[],
        ))
    s.add(BudgetLine(
        entity_id=nairobi.id, period_id=fy2425.id, category="Health Services",
        allocated_amount=Decimal(5_475_796_303), actual_spent=Decimal(1),
        currency="KES", source_document_id=other.id, provenance=[],
    ))
    s.commit()


def test_refiling_a_document_moves_its_rows_and_touches_nothing_else(session, tmp_path):
    _seed_mislabelled_production_state(session)
    records = budget_parser.parse_budget_payload(
        _fetch(tmp_path, [
            _parsed("Total", "44620.89", "32122.66"),
            _parsed("Own Source Revenue", "21178.05", "10789.42"),
        ])
    )

    stats = budget_writer.persist_budget_records(
        session, records, _settings(tmp_path), DomainRunContext(since=None, dry_run=False)
    )
    session.commit()

    by_period = {}
    for line in session.query(BudgetLine).all():
        label = session.get(FiscalPeriod, line.period_id).label
        by_period.setdefault(label, set()).add(line.category)

    assert by_period == {
        "FY2025/26 9M": {"Total", "Own Source Revenue"},
        # The other document's row in FY2024/25 is not this document's to move.
        "FY2024/25": {"Health Services"},
    }
    assert stats.superseded == 2


def test_a_run_that_writes_nothing_removes_nothing(session, tmp_path):
    _seed_mislabelled_production_state(session)
    stats = budget_writer.persist_budget_records(
        session, [], _settings(tmp_path), DomainRunContext(since=None, dry_run=False)
    )
    session.commit()
    assert stats.superseded == 0
    assert session.query(BudgetLine).count() == 3


def test_a_reparse_is_the_whole_revenue_story_for_its_document(session, tmp_path):
    """Revenue receipts a document no longer yields do not outlive the parse
    that stopped yielding them. A stricter parser (or a renamed stream) left
    the earlier run's rows in place, still published."""
    def receipts(*streams):
        return [
            _parsed("Revenue Receipts", str(a), str(a)) | {"subcategory": s, "amounts_in": "kes"}
            for s, a in streams
        ]

    settings = _settings(tmp_path)
    ctx = DomainRunContext(since=None, dry_run=False)
    first = budget_parser.parse_budget_payload(_fetch(tmp_path, [
        _parsed("Total", "44620.89", "32122.66"),
        *receipts(("Equitable Share", 100), ("Other Revenue", 20), ("Total", 120)),
    ]))
    budget_writer.persist_budget_records(session, first, settings, ctx)
    session.commit()

    second = budget_parser.parse_budget_payload(_fetch(tmp_path, [
        _parsed("Total", "44620.89", "32122.66"),
        *receipts(("Equitable Share", 100), ("Additional Allocations", 20), ("Total", 120)),
    ]))
    budget_writer.persist_budget_records(session, second, settings, ctx)
    session.commit()

    streams = {
        l.subcategory
        for l in session.query(BudgetLine).filter(BudgetLine.category == "Revenue Receipts")
    }
    assert streams == {"Equitable Share", "Additional Allocations", "Total"}

    third = budget_parser.parse_budget_payload(_fetch(tmp_path, [
        _parsed("Total", "44620.89", "32122.66"),
    ]))
    budget_writer.persist_budget_records(session, third, settings, ctx)
    session.commit()
    assert session.query(BudgetLine).filter(BudgetLine.category == "Revenue Receipts").count() == 0
    # The budget row the document still yields is untouched.
    assert session.query(BudgetLine).filter(BudgetLine.category == "Total").count() == 1
