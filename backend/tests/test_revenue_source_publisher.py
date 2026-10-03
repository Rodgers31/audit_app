"""A revenue source document names the publisher of its URL (issue #267).

The revenue_by_source writer created every SourceDocument as
``publisher="Kenya Revenue Authority"``, ``title="KRA Annual Revenue
Performance Report"``, whatever the URL. The fetcher also emits World Bank
headline totals, so production held:

  1860 | Kenya Revenue Authority | https://data.worldbank.org/indicator/GC.REV.TOTL.CN?locations=KE
  1861 | Kenya Revenue Authority | https://data.worldbank.org/indicator/GC.TAX.TOTL.CN?locations=KE

and ``/api/v1/provenance/verify/revenue_by_source?year=2022`` answered
"Kenya Revenue Authority — KRA Annual Revenue Performance Report" for a
World Bank figure. Because the writer only ever created documents, a fixed
fetcher alone would not have repaired 1860/1861 either.

The same defect was fixed for economic_indicators in #232: the fetcher
declares who published each record, the writer files the declared value and
corrects an existing document that disagrees, and undeclared rows keep the
old default.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import httpx
from models import DocumentType, RevenueBySource, SourceDocument
from sqlalchemy import select

from seeding.config import SeedingSettings
from seeding.domains.revenue_by_source.fetcher import _fetch_wb_revenue
from seeding.domains.revenue_by_source.parser import parse_revenue_payload
from seeding.domains.revenue_by_source.writer import persist_revenue_records
from seeding.types import DomainRunContext

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "seeding"
    / "real_data"
    / "revenue_by_source.json"
)

WB_REV_URL = "https://data.worldbank.org/indicator/GC.REV.TOTL.CN?locations=KE"
WB_TAX_URL = "https://data.worldbank.org/indicator/GC.TAX.TOTL.CN?locations=KE"
KRA_DEFAULT_PUBLISHER = "Kenya Revenue Authority"
KRA_DEFAULT_TITLE = "KRA Annual Revenue Performance Report"

# One observation per indicator, in the World Bank API's response shape. The
# values are what production holds for these years (FY 2010/11 = 641.0B,
# FY 2022/23 = 2,114.2B).
_WB_OBSERVATIONS = {
    "GC.REV.TOTL.CN": [{"date": "2011", "value": 641.0e9}],
    "GC.TAX.TOTL.CN": [{"date": "2023", "value": 2114.2e9}],
    "GC.TAX.TOTL.GD.ZS": [{"date": "2023", "value": 14.1}],
}


class _WorldBankClient:
    """Answers indicator requests with source-shaped bytes and transport metadata."""
    def get(self, url, **_kwargs):
        code = url.rstrip("/").rsplit("/", 1)[-1]
        rows = [{**row, "indicator": {"id": code}, "countryiso3code": "KEN"} for row in _WB_OBSERVATIONS[code]]
        return httpx.Response(200, json=[{"page": 1, "pages": 1, "total": len(rows)}, rows],
            headers={"content-type": "application/json"}, request=httpx.Request("GET", url))


def _context():
    return DomainRunContext(since=None, dry_run=False)


def _world_bank_records():
    payload = _fetch_wb_revenue(_WorldBankClient(), SeedingSettings())
    assert {r["source_url"] for r in payload} == {WB_REV_URL, WB_TAX_URL}
    return parse_revenue_payload(payload)


def _doc(session, url):
    return session.execute(
        select(SourceDocument).where(SourceDocument.url == url)
    ).scalar_one()


def test_world_bank_rows_are_filed_under_the_world_bank(db_session, seed_country):
    stats = persist_revenue_records(
        db_session, _world_bank_records(), SeedingSettings(), _context()
    )
    assert stats.errors == []

    rev = _doc(db_session, WB_REV_URL)
    tax = _doc(db_session, WB_TAX_URL)
    for doc in (rev, tax):
        assert doc.publisher == "World Bank", (doc.url, doc.publisher)
        assert "KRA" not in doc.title, (doc.url, doc.title)
    # The World Bank's own series names, from api.worldbank.org/v2/indicator.
    assert "Total revenue (current LCU)" in rev.title
    assert "GC.REV.TOTL.CN" in rev.title
    assert "Tax revenue (current LCU)" in tax.title
    assert "GC.TAX.TOTL.CN" in tax.title


def test_misfiled_production_documents_are_corrected_in_place(
    db_session, seed_country
):
    """1860/1861 already exist; the next run must relabel, not duplicate."""
    for doc_id, url in ((1860, WB_REV_URL), (1861, WB_TAX_URL)):
        db_session.add(
            SourceDocument(
                id=doc_id,
                country_id=seed_country.id,
                publisher=KRA_DEFAULT_PUBLISHER,
                title=KRA_DEFAULT_TITLE,
                url=url,
                fetch_date=datetime(2026, 3, 25, tzinfo=timezone.utc),
                doc_type=DocumentType.REPORT,
                meta={},
            )
        )
    db_session.add(
        RevenueBySource(
            fiscal_year="FY 2022/23",
            revenue_type="Total Tax Revenue",
            category="tax",
            amount_billion_kes=2114.2,
            source_document_id=1861,
        )
    )
    db_session.flush()

    stats = persist_revenue_records(
        db_session, _world_bank_records(), SeedingSettings(), _context()
    )
    assert stats.errors == []

    docs = db_session.execute(
        select(SourceDocument).where(SourceDocument.url.in_([WB_REV_URL, WB_TAX_URL]))
    ).scalars().all()
    assert sorted(d.id for d in docs) == [1860, 1861]
    assert {d.publisher for d in docs} == {"World Bank"}
    assert not any("KRA" in d.title for d in docs), [d.title for d in docs]

    row = db_session.execute(
        select(RevenueBySource).where(
            RevenueBySource.fiscal_year == "FY 2022/23",
            RevenueBySource.revenue_type == "Total Tax Revenue",
        )
    ).scalar_one()
    assert row.source_document_id == 1861


def test_undeclared_fixture_rows_keep_the_kra_default(db_session, seed_country):
    """The fixture cites KRA press releases and declares no publisher."""
    payload = json.loads(FIXTURE.read_text())
    assert not any("publisher" in r for r in payload)
    urls = {r["source_url"] for r in payload}
    assert urls and all(u.startswith("https://www.kra.go.ke/") for u in urls)

    stats = persist_revenue_records(
        db_session, parse_revenue_payload(payload), SeedingSettings(), _context()
    )
    assert stats.errors == []
    for url in urls:
        doc = _doc(db_session, url)
        assert (doc.publisher, doc.title) == (KRA_DEFAULT_PUBLISHER, KRA_DEFAULT_TITLE)


def test_undeclared_row_never_overwrites_a_declared_publisher(
    db_session, seed_country
):
    """The default is for creating a document, not for correcting one.

    If an undeclared row could reset an existing document to the default, a
    run that mixed the fixture and the World Bank at one URL would relabel the
    document back and forth on every pass.
    """
    persist_revenue_records(
        db_session, _world_bank_records(), SeedingSettings(), _context()
    )
    undeclared = parse_revenue_payload(
        [
            {
                "fiscal_year": "FY 2022/23",
                "revenue_type": "Total Tax Revenue",
                "amount_billion_kes": 2114.2,
                "source_url": WB_TAX_URL,
            }
        ]
    )
    persist_revenue_records(db_session, undeclared, SeedingSettings(), _context())

    doc = _doc(db_session, WB_TAX_URL)
    assert doc.publisher == "World Bank"
    assert "Tax revenue (current LCU)" in doc.title


def test_declaration_stays_out_of_row_meta():
    """Row ``meta`` is served by /budget/enhanced; the document label is not
    row provenance, and putting it there would change every row's payload and
    count each as an update on the next run."""
    for record in _world_bank_records():
        assert record.publisher == "World Bank"
        assert record.source_title
        assert "publisher" not in record.metadata
        assert "source_title" not in record.metadata
