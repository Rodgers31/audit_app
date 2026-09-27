"""A county budget source document names the publisher of its URL (issue #276).

The counties_budget writer created every SourceDocument as ``publisher=
"Controller of Budget"``, whatever the record's ``source_url``, and the refresh
of an existing document rewrote its title and meta but never its publisher.

``real_data/budgets.json`` carries 470 rows at the National Treasury's Budget
Policy Statement page. On the production clone that URL is document 2380,
labelled "Government of Kenya" (created by other code first; this writer
reuses a document by URL), with 470 ``budget_lines`` behind it. On a database
where this writer ran first it would have been "Controller of Budget".

Same pattern as #271 (revenue_by_source): rows declare their publisher, the
writer files the declared value, corrects an existing document only when a
declaration disagrees, and keeps the old default for undeclared rows.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from models import DocumentType, Entity, EntityType, SourceDocument
from sqlalchemy import select

from seeding.config import SeedingSettings
from seeding.domains.counties_budget.parser import parse_budget_payload
from seeding.domains.counties_budget.writer import persist_budget_records
from seeding.types import DomainRunContext

FIXTURE = (
    Path(__file__).resolve().parents[1] / "seeding" / "real_data" / "budgets.json"
)
BPS_URL = "https://www.treasury.go.ke/budget-policy-statements/"
COB_URL = (
    "https://cob.go.ke/reports/consolidated-county-budget-implementation-review-reports/"
)


def _nairobi_rows() -> list[dict]:
    rows = [r for r in json.loads(FIXTURE.read_text()) if r["entity_slug"] == "nairobi-county"]
    assert {r["source_url"] for r in rows} == {BPS_URL, COB_URL}
    return rows


@pytest.fixture()
def nairobi(db_session, seed_country) -> Entity:
    entity = Entity(
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Nairobi City County",
        slug="nairobi-county",
        alt_names=["Nairobi"],
        meta={},
    )
    db_session.add(entity)
    db_session.flush()
    return entity


def _settings(tmp_path) -> SeedingSettings:
    settings = SeedingSettings(
        storage_path=tmp_path / "storage",
        cache_path=tmp_path / "cache",
        log_path=tmp_path / "logs" / "seed.log",
        live_pdf_fetch_enabled=False,
    )
    settings.ensure_directories()
    return settings


def _persist(session, rows, tmp_path):
    stats = persist_budget_records(
        session,
        parse_budget_payload(rows),
        _settings(tmp_path),
        DomainRunContext(since=None, dry_run=False),
    )
    assert stats.errors == []
    return stats


def _doc(session, url) -> SourceDocument:
    return session.execute(
        select(SourceDocument).where(SourceDocument.url == url)
    ).scalar_one()


def test_the_fixture_declares_the_treasury_for_its_treasury_rows():
    rows = json.loads(FIXTURE.read_text())
    bps = [r for r in rows if r["source_url"] == BPS_URL]
    assert len(bps) == 470
    assert {r.get("publisher") for r in bps} == {"National Treasury"}
    # The CoB rows declare nothing and keep the default.
    assert not any("publisher" in r for r in rows if r["source_url"] != BPS_URL)


def test_budget_policy_statement_rows_are_filed_under_the_treasury(
    db_session, nairobi, tmp_path
):
    _persist(db_session, _nairobi_rows(), tmp_path)
    assert _doc(db_session, BPS_URL).publisher == "National Treasury"
    assert _doc(db_session, COB_URL).publisher == "Controller of Budget"


def test_the_production_document_is_corrected_in_place(
    db_session, seed_country, nairobi, tmp_path
):
    """2380 is relabelled, not duplicated."""
    db_session.add(
        SourceDocument(
            id=2380,
            country_id=seed_country.id,
            publisher="Government of Kenya",
            title="2025 Budget Policy Statement — County Equitable Share Projection",
            url=BPS_URL,
            fetch_date=datetime(2026, 4, 19, tzinfo=timezone.utc),
            doc_type=DocumentType.BUDGET,
            meta={},
        )
    )
    db_session.flush()

    _persist(db_session, _nairobi_rows(), tmp_path)

    doc = _doc(db_session, BPS_URL)
    assert doc.id == 2380
    assert doc.publisher == "National Treasury"


def test_undeclared_row_never_overwrites_a_declared_publisher(
    db_session, nairobi, tmp_path
):
    rows = _nairobi_rows()
    _persist(db_session, rows, tmp_path)
    undeclared = [
        {k: v for k, v in r.items() if k != "publisher"}
        for r in rows
        if r["source_url"] == BPS_URL
    ]
    _persist(db_session, undeclared, tmp_path)
    assert _doc(db_session, BPS_URL).publisher == "National Treasury"


def test_the_declaration_is_not_row_provenance(db_session, nairobi, tmp_path):
    """The label belongs to the document. BudgetLine provenance is served by
    the API, and a new key there would count every row as changed."""
    from models import BudgetLine

    _persist(db_session, _nairobi_rows(), tmp_path)
    for line in db_session.execute(select(BudgetLine)).scalars():
        for entry in line.provenance or []:
            assert "publisher" not in entry
