"""National pending bills: one publication, and it adds up to what it printed (#265).

Production served ``national_total = 931.3B``. The Treasury's Budget Review and
Outlook Paper 2025 prints 525.9B (para 18: 404.3B State Corporations + 121.6B
MDAs). The other 405.4B was eleven per-ministry and state-corporation rows
written from ``seeding/fixtures/pending_bills.json`` on a night the BROP fetch
failed — round invented figures citing a COB URL that resolves to an action-plan
template. The BROP's two lines already cover every MDA and every state
corporation, so the fixture's Ministry of Health or KeNHA is not additional to
them; summing both counted the same bills twice.

These tests write the BROP payload the fetcher builds from the para-18 text AND
the git fixture (the failed-fetch night), in both orders, and read back what the
endpoints call national.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from models import DebtCategory, Entity, EntityType, Loan

BROP_URL = (
    "https://www.treasury.go.ke/sites/default/files/"
    "2025-Budget-Review-and-Outlook-Paper-1.pdf"
)
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "seeding" / "fixtures" / "pending_bills.json"

#: BROP 2025, PDF page 18, para 18, as pdfplumber extracts it.
PARA_18 = """\
18. The total outstanding National Government pending bills as at 30th June 2025 amounted
to KSh 525.9 billion. These comprise of KSh 404.3 billion (76.9 percent) and KSh 121.6 billion
(23.1 percent) for the State Corporations and MDAs, respectively.
"""
PRINTED_NATIONAL_TOTAL = 525_900_000_000
NAIROBI_BROP = 86_769_200_000  # BROP 2025 Table 10, Nairobi — not read (#238)
#: Counties come from the CoB's year-end report since #238: Nairobi City at
#: 30 June 2025 (FY 2024/25 Table 2.9) and at 30 June 2026 (FY 2025/26 Table 2.10).
NAIROBI_COB_2025 = 86_769_200_000
NAIROBI_COB_2026 = 86_899_380_000

B = 1_000_000_000


def _get(client, path):
    from main import clear_all_caches

    clear_all_caches()
    response = client.get(path)
    assert response.status_code == 200, (path, response.text[:300])
    return response.json()


@pytest.fixture()
def entities(db_session, seed_country, seed_source_doc):
    national = Entity(
        id=900, country_id=seed_country.id, type=EntityType.NATIONAL,
        canonical_name="National Government", slug="national-government",
    )
    nairobi = Entity(
        id=3, country_id=seed_country.id, type=EntityType.COUNTY,
        canonical_name="Nairobi County", slug="nairobi-county",
    )
    db_session.add_all([national, nairobi])
    db_session.commit()
    national.doc_id = nairobi.doc_id = seed_source_doc.id
    return national, nairobi


def _brop_national():
    """What the parser reads from para 18."""
    from seeding.domains.pending_bills import brop_parser

    page = MagicMock()
    page.extract_text.return_value = PARA_18
    pdf = MagicMock()
    pdf.pages = [page]
    national = brop_parser._detect_national_paragraph(pdf, "FY 2024/25")
    assert national is not None
    return national


def _write_brop(db_session, *, with_counties=True):
    """The payload the fetcher builds from a BROP, through parser and writer."""
    from types import SimpleNamespace

    from seeding.domains.pending_bills.fetcher import _brop_result_to_payload
    from seeding.domains.pending_bills.parser import parse_pending_bills_payload
    from seeding.domains.pending_bills.writer import write_pending_bills

    counties = []
    if with_counties:
        counties = [SimpleNamespace(
            county="Nairobi", executive_subtotal=None, assembly_subtotal=None,
            fy_budget=None, total=Decimal(NAIROBI_BROP),
        )]
    result = SimpleNamespace(
        fiscal_year_label="FY 2024/25", national=_brop_national(), counties=counties,
    )
    payload = _brop_result_to_payload(result, BROP_URL)
    write_pending_bills(
        db_session, parse_pending_bills_payload(payload),
        source_url=payload["source_url"], source_title=payload["source_title"],
        publication=payload["publication"], publisher=payload["publisher"],
    )
    db_session.commit()


def _write_cob(db_session, amount, as_at):
    """Complete synthetic coverage through the real parser and writer.

    Nairobi pins the source value; the other 46 test-only zero amounts make
    this a complete population control, not a claim about those counties.
    """
    from seeding.domains.pending_bills.fetcher import county_payables_payload
    from seeding.domains.pending_bills.parser import parse_pending_bills_payload
    from seeding.domains.pending_bills.writer import write_pending_bills
    from seeding.pdf_parsers import KENYAN_COUNTIES

    year = int(as_at[:4])
    entry = {
        "county": "Nairobi", "status": "reported", "withheld_reason": None,
        "total_millions": str(Decimal(amount) / Decimal(1_000_000)),
        "assembly_printed": True, "cob_marked_inconsistent": False,
        "chapter_total_millions": None, "chapter_table": None, "chapter_page": None,
        "as_at": as_at, "fiscal_year": f"FY {year - 1}/{str(year)[2:]}",
        "table": "Table 2.10", "page": 52,
    }
    entries = [entry]
    country_id = db_session.query(Entity).first().country_id
    for name in KENYAN_COUNTIES:
        if name == "Nairobi":
            continue
        db_session.add(Entity(country_id=country_id, type=EntityType.COUNTY,
                              canonical_name=f"{name} County", slug=f"test-{name.lower()}"))
        entries.append({**entry, "county": name, "total_millions": "0"})
    db_session.flush()
    payload = county_payables_payload(entries, "https://cob.go.ke/download/cbirr/?wpdmdl=1")
    write_pending_bills(
        db_session, parse_pending_bills_payload(payload),
        source_url=payload["source_url"], source_title=payload["source_title"],
        publication=payload["publication"], publisher=payload["publisher"],
    )
    db_session.commit()


def _write_fixture(db_session):
    """The night the BROP is unreachable: the fetcher's Strategy 2."""
    from seeding.domains.pending_bills.parser import parse_pending_bills_payload
    from seeding.domains.pending_bills.writer import write_pending_bills

    payload = json.loads(FIXTURE_PATH.read_text())
    records = parse_pending_bills_payload(payload)
    assert any(r.entity_type == "national" for r in records), "fixture shape changed"
    write_pending_bills(
        db_session, records,
        source_url=payload["source_url"], source_title=payload["source_title"],
    )
    db_session.commit()


def _national_rows(body):
    return [r for r in body["pending_bills"] if r["entity_type"] != "county"]


@pytest.mark.parametrize("wrong_side", ["county", "national"])
def test_public_totals_reject_declarations_for_the_wrong_entity(
    client, db_session, entities, wrong_side
):
    national, county = entities
    _write_brop(db_session)
    _write_cob(db_session, NAIROBI_COB_2025, "2025-06-30")
    before = _get(client, "/api/v1/pending-bills")["summary"]
    entity, provenance = (
        (county, {**STAMPED, "category": "mda"}) if wrong_side == "county"
        else (national, COB_STAMPED)
    )
    db_session.add(_loan(entity, "Wrong-side declaration", 7_000_000_000, provenance))
    db_session.commit()
    body = _get(client, "/api/v1/pending-bills")
    assert body["summary"]["county_total"] == before["county_total"]
    assert body["summary"]["national_total"] == before["national_total"]
    assert body["summary"]["total_pending"] == before["total_pending"]


def test_brop_without_a_stated_date_preserves_published_rows(
    client, db_session, entities, monkeypatch
):
    from dataclasses import replace
    from types import SimpleNamespace
    from seeding import freshness
    from seeding.config import SeedingSettings
    from seeding.domains.pending_bills import fetcher
    from seeding.domains.pending_bills.parser import parse_pending_bills_payload
    from seeding.domains.pending_bills.writer import write_pending_bills

    _write_brop(db_session)
    before = [(r.id, r.outstanding, r.provenance) for r in db_session.query(Loan).all()]
    undated = replace(_brop_national(), as_at_stated=False)
    parsed = SimpleNamespace(national=undated, counties=[], fiscal_year_label="FY 2024/25")
    monkeypatch.setattr(fetcher, "_fetch_from_treasury_brop",
                        lambda *args: fetcher._brop_result_to_payload(parsed, BROP_URL))
    settings = SeedingSettings(live_pdf_fetch_enabled=True, treasury_brop_url=BROP_URL,
                               pending_bills_dataset_url=FIXTURE_PATH.as_uri())
    freshness.reset("pending_bills")
    http = MagicMock()
    http.get.return_value.text = "<html></html>"
    payload = fetcher.fetch_pending_bills_payload(http, settings)
    write_pending_bills(db_session, parse_pending_bills_payload(payload),
                       source_url=payload.get("source_url", BROP_URL),
                       source_title=payload.get("source_title", "Test"),
                       publication=payload.get("publication"), publisher=payload.get("publisher"))
    db_session.flush()
    after = [(r.id, r.outstanding, r.provenance) for r in db_session.query(Loan).all()]
    assert after == before
    assert freshness.get("pending_bills")["mode"] != "live"


# --------------------------------------------------------------------------
# the national rows add up to the BROP's printed para-18 total
# --------------------------------------------------------------------------


@pytest.mark.parametrize("order", ["brop_then_fixture", "fixture_then_brop"])
def test_the_national_rows_sum_to_the_brops_printed_total(client, db_session, entities, order):
    """RED before #265: 525.9 + 405.4 = 931.3."""
    if order == "brop_then_fixture":
        _write_brop(db_session)
        _write_fixture(db_session)
    else:
        _write_fixture(db_session)
        _write_brop(db_session)

    national = _brop_national()
    assert national.total == PRINTED_NATIONAL_TOTAL
    assert national.state_corporations + national.mdas == national.total

    body = _get(client, "/api/v1/pending-bills")
    rows = _national_rows(body)
    assert sum(r["total_pending"] for r in rows) == PRINTED_NATIONAL_TOTAL
    assert body["summary"]["national_total"] == PRINTED_NATIONAL_TOTAL
    assert sorted(r["total_pending"] for r in rows) == [121_600_000_000, 404_300_000_000]


def test_the_totals_are_the_sources_and_nothing_else(client, db_session, entities):
    """National from the BROP at 30 June 2025, counties from the CoB at the
    same date: one stock, so one total."""
    _write_brop(db_session)
    _write_cob(db_session, NAIROBI_COB_2025, "2025-06-30")
    _write_fixture(db_session)

    pb = _get(client, "/api/v1/pending-bills")["summary"]
    summary = _get(client, "/api/v1/pending-bills/summary")

    assert pb["county_total"] == NAIROBI_COB_2025
    assert pb["total_pending"] == PRINTED_NATIONAL_TOTAL + NAIROBI_COB_2025
    assert pb["as_at"] == "2025-06-30"
    assert summary["total_pending_amount"] == PRINTED_NATIONAL_TOTAL + NAIROBI_COB_2025
    # The fixture's 308.1B / 97.3B split was the only eligibility figure there
    # was. Neither source prints one, so there is none — absent, not zero.
    assert summary["eligible_total"] is None
    assert summary["ineligible_total"] is None
    assert sum(t["total_amount"] for t in summary["trend"]) == PRINTED_NATIONAL_TOTAL + NAIROBI_COB_2025


def test_no_total_and_no_trend_across_two_dates(client, db_session, entities):
    """The state after #238 deploys and before the national half is read from
    the 2026 BROP: national at 30 June 2025, counties at 30 June 2026. Their
    sum is two days, not a stock, and a fiscal-year trend drew it as a fall
    from 525.9B to 86.9B."""
    _write_brop(db_session)
    _write_cob(db_session, NAIROBI_COB_2026, "2026-06-30")

    pb = _get(client, "/api/v1/pending-bills")["summary"]
    summary = _get(client, "/api/v1/pending-bills/summary")

    assert pb["national_total"] == PRINTED_NATIONAL_TOTAL
    assert pb["county_total"] == NAIROBI_COB_2026
    assert pb["total_pending"] is None
    assert (pb["national_as_at"], pb["county_as_at"], pb["as_at"]) == (
        "2025-06-30", "2026-06-30", None
    )
    assert summary["total_pending_amount"] is None
    assert summary["trend"] == []
    assert summary["trend_absent_reason"] == "national_and_county_stated_at_different_dates"


def test_a_fixture_payload_writes_no_national_row(db_session, entities):
    _write_fixture(db_session)
    assert db_session.query(Loan).count() == 0


# --------------------------------------------------------------------------
# production as it stands: the fixture rows are already in the table
# --------------------------------------------------------------------------


def _loan(entity, lender, amount, provenance):
    return Loan(
        entity_id=entity.id, lender=lender, debt_category=DebtCategory.PENDING_BILLS,
        principal=amount, outstanding=amount, currency="KES", source_document_id=entity.doc_id,
        issue_date=datetime(2025, 6, 30, tzinfo=timezone.utc), provenance=provenance,
    )


STAMPED = {"source": "cob_pending_bills_etl", "publication": "treasury_brop",
           "fiscal_year": "FY 2024/25", "as_at": "2025-06-30"}
COB_STAMPED = {"source": "cob_pending_bills_etl", "publication": "cob_cbirr_year_end",
               "fiscal_year": "FY 2024/25", "as_at": "2025-06-30", "category": "county"}
FIXTURE_PROV = {"source": "cob_pending_bills_etl", "publication": None, "fiscal_year": "FY2024/25",
                "eligible_pending": 62_500_000_000.0, "ineligible_pending": 27_200_000_000.0}


def test_rows_already_written_from_the_fixture_are_not_counted(client, db_session, entities):
    """Loans 385-395 in production: no declaration, so not published."""
    national, _nairobi = entities
    _write_brop(db_session)
    _write_cob(db_session, NAIROBI_COB_2025, "2025-06-30")
    db_session.add(_loan(
        national, "Pending Bills — MDAs (Ministry of Health)", 89_700_000_000, FIXTURE_PROV
    ))
    db_session.commit()

    body = _get(client, "/api/v1/pending-bills")
    assert body["summary"]["national_total"] == PRINTED_NATIONAL_TOTAL
    assert "Pending Bills — MDAs (Ministry of Health)" not in {r["lender"] for r in body["pending_bills"]}
    assert body["source"] != "Controller of Budget Reports"

    summary = _get(client, "/api/v1/pending-bills/summary")
    assert summary["total_pending_amount"] == PRINTED_NATIONAL_TOTAL + NAIROBI_COB_2025
    assert summary["eligible_total"] is None


# --------------------------------------------------------------------------
# no partial sum presented as the total
# --------------------------------------------------------------------------


def test_no_total_without_a_published_national_figure(client, db_session, entities):
    """The window after deploy, before the nightly re-stamps the BROP rows:
    counties are published, national is not. 172.5B is not "the total"."""
    national, nairobi = entities
    db_session.add_all([
        _loan(national, "Pending Bills — MDAs (National Government — MDAs)",
              121_600_000_000, {"source": "cob_pending_bills_etl", "fiscal_year": "FY 2024/25"}),
        _loan(nairobi, "Pending Bills — County Governments (Nairobi County)",
              NAIROBI_COB_2025, COB_STAMPED),
    ])
    db_session.commit()

    pb = _get(client, "/api/v1/pending-bills")["summary"]
    assert pb["national_total"] is None
    assert pb["county_total"] is None
    assert pb["reported_county_sum"] == NAIROBI_COB_2025
    assert pb["total_pending"] is None
    assert _get(client, "/api/v1/pending-bills/summary")["total_pending_amount"] is None


def test_no_total_across_two_dates_even_within_one_fiscal_year_label(client, db_session, entities):
    national, nairobi = entities
    db_session.add_all([
        _loan(national, "Pending Bills — MDAs (National Government — MDAs)",
              121_600_000_000, {**STAMPED, "category": "mda", "as_at": "2024-06-30"}),
        _loan(nairobi, "Pending Bills — County Governments (Nairobi County)",
              NAIROBI_COB_2025, COB_STAMPED),
    ])
    db_session.commit()

    pb = _get(client, "/api/v1/pending-bills")["summary"]
    assert pb["national_total"] is None  # Only one national component.
    assert pb["county_total"] is None  # Only one county.
    assert pb["reported_county_sum"] == NAIROBI_COB_2025
    assert pb["total_pending"] is None


def test_no_total_when_a_row_states_no_date(client, db_session, entities):
    """Production's BROP rows were written before rows carried ``as_at``. Until
    the nightly re-stamps them there is no telling which day they are for."""
    national, nairobi = entities
    undated = {k: v for k, v in STAMPED.items() if k != "as_at"}
    db_session.add_all([
        _loan(national, "Pending Bills — MDAs (National Government — MDAs)",
              121_600_000_000, {**undated, "category": "mda"}),
        _loan(nairobi, "Pending Bills — County Governments (Nairobi County)",
              NAIROBI_COB_2025, COB_STAMPED),
    ])
    db_session.commit()

    pb = _get(client, "/api/v1/pending-bills")["summary"]
    assert pb["national_total"] is None
    assert pb["county_total"] is None
    assert pb["reported_county_sum"] == NAIROBI_COB_2025
    assert pb["total_pending"] is None


def test_nothing_published_is_no_data_not_zero(client, db_session, entities):
    national, _ = entities
    db_session.add(_loan(national, "Pending Bills — MDAs (Ministry of Health)", 89_700_000_000, FIXTURE_PROV))
    db_session.commit()

    pb = _get(client, "/api/v1/pending-bills")
    assert pb["status"] == "no_data"
    assert pb["summary"]["national_total"] is None
    summary = _get(client, "/api/v1/pending-bills/summary")
    assert summary["total_pending_amount"] is None


def test_the_live_scrape_serves_no_national_figure(client, db_session, seed_country, monkeypatch):
    """With no rows at all, /pending-bills used to scrape COB on the request
    path and serve its national rows — a second publication, ungated."""
    import etl.pending_bills_extractor as extractor_mod

    class Live:
        async def extract_all(self):
            return {
                "pending_bills": [
                    {"entity_name": "Ministry of Health", "entity_type": "national",
                     "total_pending": 89_700_000_000},
                ],
                "summary": {"total_national": 89_700_000_000},
            }

    monkeypatch.setattr(extractor_mod, "PendingBillsExtractor", Live)
    body = _get(client, "/api/v1/pending-bills")
    assert body["pending_bills"] == []
    assert body["summary"]["national_total"] is None
    assert body["summary"]["total_pending"] is None


def test_the_live_cob_extraction_cannot_declare_itself_the_brop(tmp_path, monkeypatch):
    """Strategy 3 returned the extractor's dict as-is; only Strategy 2 stripped
    a self-declared publication."""
    from seeding.config import SeedingSettings
    from seeding.domains.pending_bills import fetcher
    from seeding.http_client import create_http_client

    monkeypatch.setattr(fetcher, "_run_live_extraction", lambda: {
        "pending_bills": [], "summary": {}, "publication": "treasury_brop",
        "publisher": "National Treasury",
    })
    settings = SeedingSettings(
        storage_path=tmp_path / "s", cache_path=tmp_path / "c",
        log_path=tmp_path / "l" / "x.log", live_pdf_fetch_enabled=False,
        enrich_with_worldbank=False, pending_bills_dataset_url=None,
    )
    settings.ensure_directories()
    with create_http_client(settings) as client:
        payload = fetcher.fetch_pending_bills_payload(client, settings)
    assert payload.get("publication") is None


def test_a_failed_read_is_not_no_data(client, db_session, seed_country, monkeypatch):
    """Every exception used to fall through to the no-data answer, so a dead
    database and an empty table looked the same."""
    from sqlalchemy.exc import OperationalError

    import main

    def broken(_db):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(main, "_published_pending_bills", broken)
    main.clear_all_caches()
    assert client.get("/api/v1/pending-bills").status_code == 503
