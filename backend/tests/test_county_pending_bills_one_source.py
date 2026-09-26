"""County pending bills: one publication, one reader, the same number everywhere (#238).

Production holds 46 county pending-bills rows from the Treasury's Budget Review
and Outlook Paper (source document 2383, KSh 176.905B in total). Two things let
a different number reach a page:

* The pending-bills FIXTURE carries seven invented county figures (Nairobi
  98.7B, Mombasa 12.3B, ...) under the same lender key the BROP uses. The
  fetcher falls back to it whenever the BROP is unreachable, and the writer
  upserted on (entity, lender) — so one failed night overwrote the published
  figure, and every reader served the invention as sourced.
* Each endpoint had its own rule. ``GET /counties`` summed any budget line
  whose category mentioned "pending" ahead of the loans; ``/pending-bills``
  and the debt page summed every row with no source test at all; the
  summary's ``top_counties_by_amount`` ranked national entities as counties.

These tests seed a county with the BROP row AND a fixture row, and read every
endpoint that shows county pending bills.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from models import DebtCategory, Entity, EntityType, Loan

NAIROBI_BROP = 86_769_200_000  # Treasury BROP 2025, Nairobi County row
FIXTURE_NAIROBI = 98_700_000_000  # seeding/fixtures/pending_bills.json


def _pending(entity, doc, amount, provenance):
    return Loan(
        entity_id=entity.id,
        lender=f"Pending Bills — County Governments ({entity.canonical_name})",
        debt_category=DebtCategory.PENDING_BILLS,
        principal=amount,
        outstanding=amount,
        issue_date=datetime(2025, 6, 30, tzinfo=timezone.utc),
        currency="KES",
        source_document_id=doc.id,
        provenance=provenance,
    )


BROP = {
    "source": "cob_pending_bills_etl",
    "publication": "treasury_brop",
    "fiscal_year": "FY 2024/25",
    "category": "county",
}
FIXTURE = {
    "source": "cob_pending_bills_etl",
    "fiscal_year": "FY2024/25",
    "category": "county",
    "source_url": "https://cob.go.ke/reports/pending-bills/",
}


@pytest.fixture()
def counties(db_session, seed_country, seed_source_doc):
    nairobi = Entity(
        id=3, country_id=seed_country.id, type=EntityType.COUNTY,
        canonical_name="Nairobi County", slug="nairobi-county",
    )
    mombasa = Entity(
        id=47, country_id=seed_country.id, type=EntityType.COUNTY,
        canonical_name="Mombasa County", slug="mombasa-county",
    )
    national = Entity(
        id=900, country_id=seed_country.id, type=EntityType.NATIONAL,
        canonical_name="National Government", slug="national-government",
    )
    db_session.add_all([nairobi, mombasa, national])
    db_session.flush()
    db_session.add_all([
        # Nairobi: the BROP figure, and a stale fixture row beside it.
        _pending(nairobi, seed_source_doc, NAIROBI_BROP, BROP),
        Loan(
            entity_id=nairobi.id, lender="Pending Bills — County Governments (Nairobi)",
            debt_category=DebtCategory.PENDING_BILLS, principal=FIXTURE_NAIROBI,
            outstanding=FIXTURE_NAIROBI, currency="KES",
            issue_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            source_document_id=seed_source_doc.id, provenance=FIXTURE,
        ),
        # Mombasa: ONLY a fixture row — nothing published.
        _pending(mombasa, seed_source_doc, 12_300_000_000, FIXTURE),
        # A national aggregate, which is not a county.
        Loan(
            entity_id=national.id, lender="Pending Bills — MDAs (National Government — MDAs)",
            debt_category=DebtCategory.PENDING_BILLS, principal=121_600_000_000,
            outstanding=121_600_000_000, currency="KES",
            issue_date=datetime(2025, 6, 30, tzinfo=timezone.utc),
            source_document_id=seed_source_doc.id,
            provenance={"publication": "treasury_brop", "category": "mda"},
        ),
    ])
    db_session.commit()


def _get(client, path):
    from main import clear_all_caches

    clear_all_caches()
    response = client.get(path)
    assert response.status_code == 200, (path, response.text[:300])
    return response.json()


def test_every_county_endpoint_serves_the_brop_figure(client, counties):
    listed = {c["name"]: c for c in _get(client, "/api/v1/counties")}
    detail = _get(client, "/api/v1/counties/nairobi-county/comprehensive")
    single = _get(client, "/api/v1/counties/nairobi-county")
    card = _get(client, "/api/v1/pending-bills/counties/nairobi-county")

    assert listed["Nairobi"]["pending_bills"] == NAIROBI_BROP
    assert single["pending_bills"] == NAIROBI_BROP
    assert detail["debt"]["pending_bills"] == NAIROBI_BROP
    assert card["total_pending"] == NAIROBI_BROP


def test_a_county_with_only_a_fixture_row_is_absent_everywhere(client, counties):
    """RED before #238: Mombasa answered 12.3B, a figure nobody published."""
    listed = {c["name"]: c for c in _get(client, "/api/v1/counties")}
    detail = _get(client, "/api/v1/counties/mombasa-county/comprehensive")
    card = _get(client, "/api/v1/pending-bills/counties/mombasa-county")

    assert listed["Mombasa"]["pending_bills"] is None
    assert detail["debt"]["pending_bills"] is None
    assert detail["financial_summary"]["pending_bills_ratio"] is None
    # Absent, not zero: the card's total is the same None, not 0.
    assert card["total_pending"] is None


def test_the_debt_page_ranks_counties_only_and_by_the_brop_figure(client, counties):
    """``top_counties_by_amount`` on /pending-bills/summary (the debt page)."""
    body = _get(client, "/api/v1/pending-bills/summary")
    top = body["top_counties_by_amount"]

    assert [(row["county"], row["amount"]) for row in top] == [
        ("Nairobi County", NAIROBI_BROP)
    ]


def test_the_counties_split_is_the_brop_sum(client, counties):
    body = _get(client, "/api/v1/pending-bills")
    assert body["summary"]["county_total"] == NAIROBI_BROP


def test_the_detail_page_names_the_publication_it_printed(client, counties):
    """It said "Modelled — … not traced to a … National Treasury publication"."""
    nairobi = _get(client, "/api/v1/counties/nairobi-county/comprehensive")
    mombasa = _get(client, "/api/v1/counties/mombasa-county/comprehensive")

    assert "Modelled" not in nairobi["data_sources"]["debt"]
    assert "National Treasury — Budget Review and Outlook Paper (FY 2024/25)" in (
        nairobi["data_sources"]["debt"]
    )
    assert "not reported for this county" in mombasa["data_sources"]["debt"]


# --------------------------------------------------------------------------
# the writer: a fixture night cannot replace the BROP
# --------------------------------------------------------------------------


def _record(total):
    from seeding.domains.pending_bills.parser import PendingBillRecord

    return PendingBillRecord(
        entity_name="Nairobi County",
        entity_type="county",
        category="county",
        fiscal_year="FY 2024/25",
        total_pending=total,
    )


def test_a_fixture_run_after_a_brop_run_leaves_the_brop_figure(db_session, counties):
    from seeding.domains.pending_bills.writer import write_pending_bills
    from services.publication_gate import county_pending_bills

    db_session.query(Loan).delete()
    db_session.commit()

    write_pending_bills(
        db_session, [_record(NAIROBI_BROP)],
        source_url="https://www.treasury.go.ke/sites/default/files/2025-Budget-Review-and-Outlook-Paper-1.pdf",
        source_title="Treasury BROP FY 2024/25",
        publication="treasury_brop", publisher="National Treasury",
    )
    # The night the BROP is unreachable: the fixture payload, undeclared.
    write_pending_bills(
        db_session, [_record(FIXTURE_NAIROBI)],
        source_url="https://cob.go.ke/reports/pending-bills/",
        source_title="Controller of Budget — National Government Budget Implementation Review Report FY 2024/25",
    )
    db_session.commit()

    loans = db_session.query(Loan).filter(Loan.entity_id == 3).all()
    assert [float(l.outstanding) for l in loans] == [NAIROBI_BROP]
    assert county_pending_bills(loans) == NAIROBI_BROP
    assert loans[0].source_document.publisher == "National Treasury"


def test_the_brop_payload_declares_itself():
    """The declaration is made where the source is known: the fetcher."""
    from types import SimpleNamespace

    from seeding.domains.pending_bills.fetcher import _brop_result_to_payload

    result = SimpleNamespace(fiscal_year_label="FY 2024/25", national=None, counties=[])
    payload = _brop_result_to_payload(result, "https://example.test/brop.pdf")

    assert payload["publication"] == "treasury_brop"
    assert payload["publisher"] == "National Treasury"
