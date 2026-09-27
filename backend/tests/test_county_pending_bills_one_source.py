"""County pending bills: one publication, one reader, the same number everywhere (#238).

County pending bills are read from ONE publication: the Controller of Budget's
full-year County Governments Budget Implementation Review Report, table of
trade payables at 30 June (Table 2.10 in FY 2025/26, KSh 172,526.69m, Nairobi
City 86,899.38m). Production held 46 county rows from the Treasury's Budget
Review and Outlook Paper (source document 2383, KSh 176.905B); the BROP's
county table is a reprint of the CoB's, and those rows are no longer served.
Two things let a different number reach a page:

* The pending-bills FIXTURE carries seven invented county figures (Nairobi
  98.7B, Mombasa 12.3B, ...) under the same lender key the county rows use.
  The fetcher falls back to it whenever the BROP is unreachable, and the
  writer upserted on (entity, lender) — so one failed night overwrote the
  published figure, and every reader served the invention as sourced.
* Each endpoint had its own rule. ``GET /counties`` summed any budget line
  whose category mentioned "pending" ahead of the loans; ``/pending-bills``
  and the debt page summed every row with no source test at all; the
  summary's ``top_counties_by_amount`` ranked national entities as counties.

These tests seed a county with the CoB row AND a fixture row, and read every
endpoint that shows county pending bills.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from models import DebtCategory, Entity, EntityType, Loan

NAIROBI_COB = 86_899_380_000  # CoB CBIRR FY 2025/26 Table 2.10, Nairobi City
NAIROBI_BROP = 86_769_200_000  # Treasury BROP 2025 Table 10 — no longer served
FIXTURE_NAIROBI = 98_700_000_000  # seeding/fixtures/pending_bills.json
CBIRR_URL = (
    "https://cob.go.ke/download/county-governments-budget-implementation-"
    "review-report-for-the-financial-year-2025-26/?wpdmdl=16482"
)


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


COB = {
    "source": "cob_pending_bills_etl",
    "publication": "cob_cbirr_year_end",
    "fiscal_year": "FY 2025/26",
    "category": "county",
    "as_at": "2026-06-30",
    "table": "Table 2.10",
    "source_url": CBIRR_URL,
}
#: A county row as #238 first wrote it, from the BROP's reprint.
BROP_COUNTY = {
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
        # Nairobi: the CoB figure, and a stale fixture row beside it.
        _pending(nairobi, seed_source_doc, NAIROBI_COB, COB),
        Loan(
            entity_id=nairobi.id, lender="Pending Bills — County Governments (Nairobi)",
            debt_category=DebtCategory.PENDING_BILLS, principal=FIXTURE_NAIROBI,
            outstanding=FIXTURE_NAIROBI, currency="KES",
            issue_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            source_document_id=seed_source_doc.id, provenance=FIXTURE,
        ),
        # Mombasa: a fixture row, and a BROP county row from before the
        # source moved — nothing published.
        _pending(mombasa, seed_source_doc, 12_300_000_000, FIXTURE),
        Loan(
            entity_id=mombasa.id, lender="Pending Bills — County Governments (Mombasa)",
            debt_category=DebtCategory.PENDING_BILLS, principal=3_867_700_000,
            outstanding=3_867_700_000, currency="KES",
            issue_date=datetime(2025, 6, 30, tzinfo=timezone.utc),
            source_document_id=seed_source_doc.id, provenance=BROP_COUNTY,
        ),
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


def test_every_county_endpoint_serves_the_cob_figure(client, counties):
    listed = {c["name"]: c for c in _get(client, "/api/v1/counties")}
    detail = _get(client, "/api/v1/counties/nairobi-county/comprehensive")
    single = _get(client, "/api/v1/counties/nairobi-county")
    card = _get(client, "/api/v1/pending-bills/counties/nairobi-county")

    assert listed["Nairobi"]["pending_bills"] == NAIROBI_COB
    assert single["pending_bills"] == NAIROBI_COB
    assert detail["debt"]["pending_bills"] == NAIROBI_COB
    assert card["total_pending"] == NAIROBI_COB


def test_a_county_with_only_a_fixture_row_is_absent_everywhere(client, counties):
    """RED before #238: Mombasa answered 12.3B, a figure nobody published.

    And since the source moved, its BROP row (3.87B) is not served either:
    the BROP is not where county pending bills are read from."""
    listed = {c["name"]: c for c in _get(client, "/api/v1/counties")}
    detail = _get(client, "/api/v1/counties/mombasa-county/comprehensive")
    card = _get(client, "/api/v1/pending-bills/counties/mombasa-county")

    assert listed["Mombasa"]["pending_bills"] is None
    assert detail["debt"]["pending_bills"] is None
    assert detail["financial_summary"]["pending_bills_ratio"] is None
    # Absent, not zero: the card's total is the same None, not 0.
    assert card["total_pending"] is None


def test_the_debt_page_ranks_counties_only_and_by_the_cob_figure(client, counties):
    """``top_counties_by_amount`` on /pending-bills/summary (the debt page)."""
    body = _get(client, "/api/v1/pending-bills/summary")
    top = body["top_counties_by_amount"]

    assert [(row["county"], row["amount"]) for row in top] == [
        ("Nairobi County", NAIROBI_COB)
    ]


def test_the_counties_split_is_the_cob_sum(client, counties):
    body = _get(client, "/api/v1/pending-bills")
    assert body["summary"]["county_total"] == NAIROBI_COB
    assert body["summary"]["county_as_at"] == "2026-06-30"


def test_the_detail_page_names_the_publication_it_printed(client, counties):
    """It said "Modelled — … not traced to a … National Treasury publication"."""
    nairobi = _get(client, "/api/v1/counties/nairobi-county/comprehensive")
    mombasa = _get(client, "/api/v1/counties/mombasa-county/comprehensive")

    assert "Modelled" not in nairobi["data_sources"]["debt"]
    assert (
        "Controller of Budget — County Governments Budget Implementation Review "
        "Report (FY 2025/26), Table 2.10, trade payables as at 2026-06-30"
    ) in nairobi["data_sources"]["debt"]
    assert "Budget Review and Outlook Paper" not in nairobi["data_sources"]["debt"]
    assert "no Controller of Budget year-end figure" in mombasa["data_sources"]["debt"]


def test_the_detail_page_carries_the_date_the_figure_is_stated_at(client, counties):
    """The page printed a figure with no date; the CoB states it at 30 June."""
    nairobi = _get(client, "/api/v1/counties/nairobi-county/comprehensive")["debt"]
    mombasa = _get(client, "/api/v1/counties/mombasa-county/comprehensive")["debt"]

    assert nairobi["pending_bills_as_at"] == "2026-06-30"
    assert nairobi["pending_bills_source"]["table"] == "Table 2.10"
    assert nairobi["pending_bills_source"]["url"] == CBIRR_URL
    assert nairobi["pending_bills_notes"] == []
    # No figure, so no date: the BROP row's FY 2024/25 is not borrowed.
    assert mombasa["pending_bills_as_at"] is None
    assert mombasa["pending_bills_source"] is None


def test_a_flagged_county_is_published_with_what_the_report_says(client, db_session, counties):
    """Owner's call (#238): publish the CoB's flagged counties, with a note."""
    uasin = Entity(
        id=44, country_id=db_session.query(Entity).first().country_id,
        type=EntityType.COUNTY, canonical_name="Uasin Gishu County", slug="uasin-gishu-county",
    )
    db_session.add(uasin)
    db_session.flush()
    notes = [
        {"code": "assembly_not_printed", "table": "Table 2.10"},
        {"code": "chapter_table_differs", "table": "Table 2.10",
         "chapter_table": "Table 3.678", "chapter_page": 877,
         "chapter_total": "1481440000.00"},
    ]
    db_session.add(_pending(
        uasin, db_session.query(Loan).first().source_document, 1_153_720_000,
        {**COB, "reader_notes": notes + [{"code": "not_a_known_code"}]},
    ))
    db_session.commit()

    debt = _get(client, "/api/v1/counties/uasin-gishu-county/comprehensive")["debt"]
    assert debt["pending_bills"] == 1_153_720_000
    # Known codes only: a note the page cannot word is not passed on.
    assert debt["pending_bills_notes"] == notes


# --------------------------------------------------------------------------
# the writer: a fixture night cannot replace the BROP
# --------------------------------------------------------------------------


def _record(total, name="Nairobi County", fiscal_year="FY 2025/26"):
    from seeding.domains.pending_bills.parser import PendingBillRecord

    return PendingBillRecord(
        entity_name=name,
        entity_type="county",
        category="county",
        fiscal_year=fiscal_year,
        total_pending=total,
        as_at="2026-06-30",
        source_table="Table 2.10",
        source_page=52,
    )


COB_WRITE = dict(
    source_url=CBIRR_URL,
    source_title="Controller of Budget — County Governments Budget Implementation Review Report, FY 2025/26",
    publication="cob_cbirr_year_end",
    publisher="Office of the Controller of Budget (OCOB)",
)


def test_a_fixture_run_after_a_cob_run_leaves_the_cob_figure(db_session, counties):
    from seeding.domains.pending_bills.writer import write_pending_bills
    from services.publication_gate import county_pending_bills

    db_session.query(Loan).delete()
    db_session.commit()

    write_pending_bills(db_session, [_record(NAIROBI_COB)], **COB_WRITE)
    # The night the sources are unreachable: the fixture payload, undeclared.
    write_pending_bills(
        db_session, [_record(FIXTURE_NAIROBI)],
        source_url="https://cob.go.ke/reports/pending-bills/",
        source_title="Controller of Budget — National Government Budget Implementation Review Report FY 2024/25",
    )
    db_session.commit()

    loans = db_session.query(Loan).filter(Loan.entity_id == 3).all()
    assert [float(l.outstanding) for l in loans] == [NAIROBI_COB]
    assert county_pending_bills(loans) == NAIROBI_COB
    assert loans[0].source_document.publisher == "Office of the Controller of Budget (OCOB)"
    # Written from what the parser read, not inferred later.
    assert loans[0].provenance["as_at"] == "2026-06-30"
    assert loans[0].provenance["table"] == "Table 2.10"
    assert loans[0].provenance["page"] == 52


def test_the_brop_writes_no_county_and_the_cob_no_national_row(db_session, counties):
    """Each payload is the source for one side only. A BROP county record —
    the reprint — must not overwrite the CoB's figure, and a CoB payload
    carries no national line to write."""
    from seeding.domains.pending_bills.parser import PendingBillRecord
    from seeding.domains.pending_bills.writer import write_pending_bills
    from services.publication_gate import county_pending_bills

    db_session.query(Loan).delete()
    db_session.commit()
    write_pending_bills(db_session, [_record(NAIROBI_COB)], **COB_WRITE)
    national = PendingBillRecord(
        entity_name="National Government — MDAs", entity_type="national",
        category="mda", fiscal_year="FY 2025/26", total_pending=121_600_000_000,
    )
    write_pending_bills(
        db_session, [_record(NAIROBI_BROP, fiscal_year="FY 2024/25")],
        source_url="https://t/brop.pdf", source_title="Treasury BROP FY 2024/25",
        publication="treasury_brop", publisher="National Treasury",
    )
    write_pending_bills(db_session, [national], **COB_WRITE)
    db_session.commit()

    nairobi = db_session.query(Loan).filter(Loan.entity_id == 3).all()
    assert county_pending_bills(nairobi) == NAIROBI_COB
    assert db_session.query(Loan).filter(Loan.entity_id == 900).count() == 0


def test_the_brop_payload_declares_itself():
    """The declaration is made where the source is known: the fetcher."""
    from types import SimpleNamespace

    from seeding.domains.pending_bills.fetcher import _brop_result_to_payload

    result = SimpleNamespace(
        fiscal_year_label="FY 2024/25", national=None,
        counties=[SimpleNamespace(county="Nairobi", total=NAIROBI_BROP)],
    )
    payload = _brop_result_to_payload(result, "https://example.test/brop.pdf")

    assert payload["publication"] == "treasury_brop"
    assert payload["publisher"] == "National Treasury"
    # The BROP's county table is not read: it reprints the CoB's.
    assert payload["pending_bills"] == []
    assert "total_county" not in payload["summary"]


# --------------------------------------------------------------------------
# found by an adversarial pass: published and should not have been
# --------------------------------------------------------------------------


def _row(amount, principal=None):
    from types import SimpleNamespace

    return SimpleNamespace(
        debt_category=SimpleNamespace(value="pending_bills"),
        outstanding=amount,
        principal=amount if principal is None else principal,
        provenance=dict(COB),
    )


@pytest.mark.parametrize("amount", [float("nan"), float("inf"), -5e9, True])
def test_the_gate_publishes_only_a_real_amount(amount):
    """NaN reached /counties as a float that JSON cannot encode — HTTP 500 for
    all 47 counties."""
    from services.publication_gate import county_pending_bills

    assert county_pending_bills([_row(amount)]) is None


def test_a_newer_report_retires_a_county_it_does_not_state(db_session, counties):
    """Nandi reported at 30 June 2025 and not at 30 June 2026. Its older figure
    would sit beside everyone's newer one, summed into the county total,
    indefinitely."""
    from seeding.domains.pending_bills.parser import PendingBillRecord
    from seeding.domains.pending_bills.writer import write_pending_bills
    from services.publication_gate import county_pending_bills

    db_session.query(Loan).delete()
    db_session.commit()

    def rec(name, fy, total):
        return PendingBillRecord(
            entity_name=name, entity_type="county", category="county",
            fiscal_year=fy, total_pending=total,
            as_at=f"20{fy[-2:]}-06-30",
        )

    kwargs = dict(publication="cob_cbirr_year_end", publisher="OCOB")
    write_pending_bills(
        db_session, [rec("Nairobi County", "FY 2024/25", 86_769_200_000), rec("Mombasa County", "FY 2024/25", 3e9)],
        source_url="https://c/cbirr2425.pdf", source_title="CBIRR FY 2024/25", **kwargs,
    )
    write_pending_bills(
        db_session, [rec("Nairobi County", "FY 2025/26", NAIROBI_COB)],
        source_url="https://c/cbirr2526.pdf", source_title="CBIRR FY 2025/26", **kwargs,
    )
    db_session.commit()

    mombasa = db_session.query(Loan).filter(Loan.entity_id == 47).all()
    nairobi = db_session.query(Loan).filter(Loan.entity_id == 3).all()
    assert county_pending_bills(nairobi) == NAIROBI_COB
    assert county_pending_bills(mombasa) is None


def test_a_reread_of_the_same_report_retires_a_county_it_now_withholds(db_session, counties):
    """Retiring by edition alone missed this: the same report read again with
    Mombasa's row withheld kept Mombasa's figure, stamped as current."""
    from seeding.domains.pending_bills.writer import write_pending_bills
    from services.publication_gate import county_pending_bills

    db_session.query(Loan).delete()
    db_session.commit()
    write_pending_bills(
        db_session, [_record(NAIROBI_COB), _record(3_844_590_000, name="Mombasa County")],
        **COB_WRITE,
    )
    write_pending_bills(db_session, [_record(NAIROBI_COB)], **COB_WRITE)
    db_session.commit()

    mombasa = db_session.query(Loan).filter(Loan.entity_id == 47).all()
    assert county_pending_bills(mombasa) is None
    assert county_pending_bills(db_session.query(Loan).filter(Loan.entity_id == 3).all()) == NAIROBI_COB


@pytest.mark.parametrize("category", ["County", " county", None])
def test_a_fixture_county_record_is_not_written_whatever_its_category_spelling(
    db_session, counties, category
):
    from seeding.domains.pending_bills.parser import PendingBillRecord
    from seeding.domains.pending_bills.writer import write_pending_bills

    db_session.query(Loan).delete()
    db_session.commit()
    write_pending_bills(
        db_session,
        [PendingBillRecord(
            entity_name="Nairobi County", entity_type="county",
            category=category, fiscal_year="FY2024/25", total_pending=FIXTURE_NAIROBI,
        )],
        source_url="https://cob.go.ke/reports/pending-bills/", source_title="fixture",
    )
    db_session.commit()
    assert db_session.query(Loan).filter(Loan.entity_id == 3).count() == 0


def test_a_dataset_cannot_declare_itself_the_brop(tmp_path):
    """The fixture path returned the dataset's JSON as-is, so a file carrying
    "publication": "treasury_brop" would publish its invented figures."""
    import json

    from seeding.config import SeedingSettings
    from seeding.domains.pending_bills import fetcher

    data = tmp_path / "pb.json"
    data.write_text(json.dumps({
        "pending_bills": [], "summary": {}, "source_url": "x", "source_title": "y",
        "publication": "treasury_brop", "publisher": "National Treasury",
    }))
    settings = SeedingSettings(
        storage_path=tmp_path / "s", cache_path=tmp_path / "c",
        log_path=tmp_path / "l" / "x.log", live_pdf_fetch_enabled=False,
        enrich_with_worldbank=False, pending_bills_dataset_url=f"file://{data}",
    )
    settings.ensure_directories()
    from seeding.http_client import create_http_client

    with create_http_client(settings) as client:
        payload = fetcher.fetch_pending_bills_payload(client, settings)
    assert payload.get("publication") is None


def test_no_pending_bills_at_all_is_null_not_zero_for_counties(client, db_session, seed_country, monkeypatch):
    import etl.pending_bills_extractor as extractor_mod

    class NoData:
        async def extract_all(self):
            return {"pending_bills": [], "summary": {}}

    monkeypatch.setattr(extractor_mod, "PendingBillsExtractor", NoData)
    assert _get(client, "/api/v1/pending-bills")["summary"]["county_total"] is None


def test_the_live_extraction_fallback_does_not_serve_county_figures(client, db_session, seed_country, monkeypatch):
    """With no rows in the database, /pending-bills served the live COB
    extractor's county rows ungated — Nairobi 98.7B while /counties said null."""
    import etl.pending_bills_extractor as extractor_mod

    class Live:
        async def extract_all(self):
            return {
                "pending_bills": [
                    {"entity_name": "Nairobi County", "entity_type": "county", "total_pending": 98_700_000_000},
                    {"entity_name": "Ministry of Health", "entity_type": "national", "total_pending": 89_700_000_000},
                ],
                "summary": {"grand_total": 188_400_000_000, "total_county": 98_700_000_000,
                            "total_national": 89_700_000_000},
            }

    monkeypatch.setattr(extractor_mod, "PendingBillsExtractor", Live)
    body = _get(client, "/api/v1/pending-bills")
    assert all(r.get("entity_type") != "county" for r in body["pending_bills"])
    assert body["summary"]["county_total"] is None


def test_a_published_zero_stays_zero_on_the_pending_bills_endpoints(client, db_session, counties):
    kisumu = Entity(
        id=42, country_id=db_session.query(Entity).first().country_id,
        type=EntityType.COUNTY, canonical_name="Kisumu County", slug="kisumu-county",
    )
    db_session.add(kisumu)
    db_session.flush()
    loan = _pending(kisumu, db_session.query(Loan).first().source_document, 0, COB)
    loan.principal = 5_000_000_000
    db_session.add(loan)
    db_session.commit()

    top = {r["county"]: r["amount"] for r in _get(client, "/api/v1/pending-bills/summary")["top_counties_by_amount"]}
    assert top.get("Kisumu County", 0) == 0
    assert _get(client, "/api/v1/pending-bills")["summary"]["county_total"] == NAIROBI_COB


def test_a_county_the_report_says_did_not_report_is_told_so(client, db_session, counties):
    """Nandi at 30 June 2026: the CoB prints "-" across its row and says it
    did not report. The page says that, rather than a bare dash — and says
    nothing for a county the report does not mention."""
    from seeding.domains.pending_bills.writer import write_pending_bills

    db_session.query(Loan).delete()
    db_session.commit()
    write_pending_bills(
        db_session, [_record(NAIROBI_COB)], **COB_WRITE,
        county_table={
            "as_at": "2026-06-30", "table": "Table 2.10",
            "not_reported": ["Mombasa"], "withheld": {},
        },
    )
    db_session.commit()

    mombasa = _get(client, "/api/v1/counties/mombasa-county/comprehensive")["debt"]
    nairobi = _get(client, "/api/v1/counties/nairobi-county/comprehensive")["debt"]
    assert mombasa["pending_bills"] is None
    assert mombasa["pending_bills_absence"] == {
        "reason": "not_reported", "as_at": "2026-06-30", "table": "Table 2.10",
    }
    # Never beside a figure.
    assert nairobi["pending_bills_absence"] is None


def test_no_reason_is_given_for_a_county_the_report_does_not_mention(client, db_session, counties):
    from seeding.domains.pending_bills.writer import write_pending_bills

    db_session.query(Loan).delete()
    db_session.commit()
    write_pending_bills(
        db_session, [_record(NAIROBI_COB)], **COB_WRITE,
        county_table={"as_at": "2026-06-30", "table": "Table 2.10",
                      "not_reported": ["Nandi"], "withheld": {}},
    )
    db_session.commit()
    mombasa = _get(client, "/api/v1/counties/mombasa-county/comprehensive")["debt"]
    assert mombasa["pending_bills"] is None
    assert mombasa["pending_bills_absence"] is None
