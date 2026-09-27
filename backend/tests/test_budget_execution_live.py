"""The /budget execution panel publishes COB's actual expenditure by sector (#241).

Before: ``/api/v1/budget/enhanced`` kept only national BudgetLines with
``committed_amount`` set. Only the git fixture set it, so production served
``execution_by_sector: []`` once a live FY 2025/26 period was newest — and the
live rows would not have been fit to publish anyway: they held Exchequer
Issues (cash released) against Net Estimates, and only the recurrent half.

The parser tests run on page text captured from the REAL annual reports
(``tests/fixtures/cob/ngbirr_fy202*_annual_pages.json``: pdfplumber
``extract_text()`` of the pages the parse needs, with the PDF's md5 and URL),
because a parser tested on tidy hand-written tables is untested against the
things that break it — interleaved header cells, a summary spilling onto the
next page, "377.5 0" for 377.50, and two publisher errors in the FY 2025/26
report itself.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from seeding.domains.national_budget.sector_expenditure import (
    EXPENDITURE_MEASURE,
    SECTORS,
    parse_sector_expenditure,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "cob"


def _pages(name: str) -> dict[int, str]:
    data = json.loads((FIXTURES / name).read_text())
    return {int(k): v for k, v in data["pages"].items()}


@pytest.fixture(scope="module")
def fy2526():
    return parse_sector_expenditure(_pages("ngbirr_fy2025_26_annual_pages.json"))


@pytest.fixture(scope="module")
def fy2425():
    return parse_sector_expenditure(_pages("ngbirr_fy2024_25_annual_pages.json"))


# ── The parse, on the real FY 2025/26 report ────────────────────────────────

# Every sector's Sector Summary Total, as printed (KSh bn): (table, PDF page of
# the summary, revised gross, expenditure). Read off the report by hand.
FY2526_TOTALS = {
    "Agriculture, Rural and Urban Development": ("Table 4.1", 94, "117.41", "103.98"),
    "Education": ("Table 4.17", 112, "757.50", "745.44"),
    "Energy, Infrastructure and ICT": ("Table 4.32", 130, "608.17", "546.85"),
    "Environment Protection, Water, and Natural Resources": ("Table 4.63", 160, "115.35", "105.04"),
    "General Economic and Commercial Affairs": ("Table 4.82", 180, "74.94", "62.39"),
    "Governance, Justice, Law and Order": ("Table 4.106", 209, "328.21", "322.21"),
    "Health": ("Table 4.149", 243, "164.92", "157.20"),
    "National Security": ("Table 4.156", 255, "291.40", "289.73"),
    "Public Administration and International Relations": ("Table 4.160", 262, "377.50", "346.54"),
    "Social Protection, Culture and Recreation": ("Table 4.223", 324, "96.35", "91.57"),
}


def test_all_ten_sectors_are_verified_with_their_printed_totals(fy2526):
    got = {
        s.sector: (s.table, s.summary_page, str(s.total.gross), str(s.total.expenditure))
        for s in fy2526.accepted
    }
    assert got == FY2526_TOTALS


def test_the_ten_sectors_are_the_whole_ministerial_budget(fy2526):
    """Sum of sector Totals against Table 3.1's MDA recurrent + development
    expenditure (1,961.55 + 809.47). If a sector were dropped, or a unit
    misread, this is where it would show."""
    cov = fy2526.coverage()
    assert cov["sectors_reported"] == 10 and cov["sectors_missing"] == []
    assert cov["sector_expenditure_bn"] == "2770.95"
    assert cov["mda_expenditure_bn"] == "2771.02"
    assert cov["cfs_expenditure_bn"] == "1982.52"
    assert cov["reconciles"] is True


def test_national_security_split_is_withheld_but_its_total_stands(fy2526):
    """The report's National Security Recurrent row (248.84 / 241.01 / 189.23 /
    201.48) is the NINE-MONTH figure carried over by mistake: Dev + Rec does not
    make the Total. The Total agrees with the sector prose (289.73), so the
    total is published and the split is not."""
    ns = next(s for s in fy2526.sectors if s.sector == "National Security")
    assert ns.recurrent.expenditure == Decimal("201.48")
    assert ns.checks["development_plus_recurrent_equals_total"] is False
    assert ns.checks["prose_total_matches"] is True
    assert ns.accepted and not ns.split_published


def test_eiict_split_is_withheld_for_its_bad_development_row(fy2526):
    """EIICT Development prints expenditure 385.40 of 453.71 (84.9%) while its
    own % column says 92; Dev + Rec = 514.14 against a Total (and prose) of
    546.85."""
    e = next(s for s in fy2526.sectors if s.code == "EIICT")
    assert e.development.expenditure == Decimal("385.40")
    assert e.accepted and not e.split_published


def test_split_is_published_where_it_reproduces_the_total(fy2526):
    arud = next(s for s in fy2526.sectors if s.code == "ARUD")
    assert arud.split_published
    assert (arud.development.expenditure, arud.recurrent.expenditure) == (
        Decimal("68.04"),
        Decimal("35.94"),
    )


# ── …and on the real FY 2024/25 report, whose layout differs ────────────────


def test_fy2425_parses_all_ten_but_says_its_coverage_does_not_close(fy2425):
    """Its overall table is "Table 3.4", its Development row prints the
    percentages before the amounts, and National Security's prose sits AFTER
    the summary. Sectors sum to 2,212.41 against the MDA 2,215.18: a real
    2.77 bn gap, reported rather than tolerated away."""
    assert len(fy2425.accepted) == 10
    cov = fy2425.coverage()
    assert (cov["sector_expenditure_bn"], cov["mda_expenditure_bn"]) == ("2212.41", "2215.18")
    assert cov["reconciles"] is False
    ns = next(s for s in fy2425.sectors if s.sector == "National Security")
    assert ns.prose_expenditure_bn == Decimal("235.78") and ns.prose_page == 231


# ── A wrong figure is refused, and a refused sector is absent — not zero ────


def test_a_tampered_total_is_refused_and_reported_missing():
    pages = _pages("ngbirr_fy2025_26_annual_pages.json")
    assert "Total 117.41 87.41 86.28 103.98 99 89" in pages[94]
    pages[94] = pages[94].replace(
        "Total 117.41 87.41 86.28 103.98 99 89", "Total 117.41 87.41 86.28 113.98 99 89"
    )
    res = parse_sector_expenditure(pages)
    arud = next(s for s in res.sectors if s.code == "ARUD")
    assert not arud.accepted
    assert res.missing == ["Agriculture, Rural and Urban Development"]
    assert all(s.total.expenditure > 0 for s in res.accepted)


# ── Discovery: the newest ANNUAL report, by the FY it names ─────────────────


def test_discovery_picks_the_fy2025_26_annual_from_the_real_listing():
    from seeding.domains.national_budget.fetcher import discover_latest_annual_ng_birr

    html = (FIXTURES / "ng_birr_listing_2026-09-26.html").read_text()
    found = discover_latest_annual_ng_birr(html, "https://cob.go.ke/")
    assert found.fiscal_year == "FY 2025/26"
    assert found.url.endswith("review-report-fy-2025-2026/?wpdmdl=16454")


def test_discovery_ranks_by_fiscal_year_not_upload_id_and_skips_quarterlies():
    from seeding.domains.national_budget.fetcher import discover_latest_annual_ng_birr

    base = "https://cob.go.ke/download/national-government-budget-implementation-review-report"
    html = (
        f'<a href="{base}-fy-2023-24/?wpdmdl=99999">re-uploaded old annual</a>'
        f'<a href="{base}-fy-2024-2025/?wpdmdl=16252">annual</a>'
        f'<a href="{base}-first-quarter-fy-2025-26/?wpdmdl=16300">Q1</a>'
    )
    found = discover_latest_annual_ng_birr(html, "https://cob.go.ke/")
    assert found.fiscal_year == "FY 2024/25"


# ── The endpoint publishes declared expenditure, and only that ──────────────


def _seed_national(db_session, seed_country, seed_source_doc):
    from models import BudgetLine, Entity, EntityType, FiscalPeriod

    national = Entity(
        country_id=seed_country.id,
        type=EntityType.NATIONAL,
        canonical_name="National Government of Kenya",
        slug="national-government",
    )
    db_session.add(national)
    db_session.flush()

    def period(label, start, end):
        fp = FiscalPeriod(country_id=seed_country.id, label=label, start_date=start, end_date=end)
        db_session.add(fp)
        db_session.flush()
        return fp

    fy2324 = period("FY2023/24", datetime(2023, 7, 1), datetime(2024, 6, 30))
    fy2526 = period("FY2025/26", datetime(2025, 7, 1), datetime(2026, 6, 30))
    h1 = period("FY2025/26 H1", datetime(2025, 7, 1), datetime(2025, 12, 31))

    common = {"entity_id": national.id, "currency": "KES", "source_document_id": seed_source_doc.id}
    # The git fixture's shape: committed_amount set, no declared measure.
    db_session.add(
        BudgetLine(period_id=fy2324.id, category="Education", subcategory="Recurrent & Development",
                   allocated_amount=628.5e9, actual_spent=558.4e9, committed_amount=590.2e9, **common)
    )
    # A quarterly period's exchequer proxy — declared as such.
    db_session.add(
        BudgetLine(period_id=h1.id, category="Health", subcategory="Recurrent",
                   allocated_amount=74.78e9, actual_spent=40.90e9,
                   provenance=[{"measure": "exchequer_issues", "period": "FY 2025/26 H1"}], **common)
    )
    return national, fy2526, common


def _expenditure_line(fy, common, sector, gross, spent, page):
    from models import BudgetLine

    return BudgetLine(
        period_id=fy.id, category=sector, subcategory="Recurrent & Development",
        allocated_amount=gross, actual_spent=spent, committed_amount=None, page_ref=page,
        provenance=[{"measure": EXPENDITURE_MEASURE, "allocated_measure": "revised_gross_estimates",
                     "period": "annual", "table": "Table 4.1",
                     "coverage": {"sectors_expected": 10, "sectors_reported": 2,
                                  "cfs_expenditure_bn": "1982.52", "reconciles": None}}],
        **common,
    )


def test_enhanced_serves_the_live_expenditure_rows(client, db_session, seed_country, seed_source_doc):
    """RED on the pre-#241 handler: its ``committed_amount IS NOT NULL`` filter
    drops every live row, so this returned []."""
    _, fy2526, common = _seed_national(db_session, seed_country, seed_source_doc)
    db_session.add_all([
        _expenditure_line(fy2526, common, "Agriculture, Rural and Urban Development", 117.41e9, 103.98e9, "p.94"),
        _expenditure_line(fy2526, common, "Health", 164.92e9, 157.20e9, "p.243"),
    ])
    db_session.commit()

    body = client.get("/api/v1/budget/enhanced").json()
    rows = {r["sector"]: r for r in body["execution_by_sector"]}
    assert set(rows) == {"Agriculture, Rural and Urban Development", "Health"}
    assert rows["Health"]["allocated"] == pytest.approx(164.92e9)
    assert rows["Health"]["spent"] == pytest.approx(157.20e9)
    assert rows["Health"]["execution_rate"] == 95.3
    assert rows["Health"]["page_ref"] == "p.243"
    assert body["execution_fiscal_year"] == "FY2025/26"
    assert body["execution_measure"] == {"spent": "expenditure", "allocated": "revised_gross_estimates"}
    assert body["execution_excludes"]["expenditure_bn"] == "1982.52"


def test_enhanced_publishes_nothing_rather_than_an_undeclared_or_proxy_row(
    client, db_session, seed_country, seed_source_doc
):
    """With only the fixture-shaped row and a quarterly exchequer proxy, there
    is nothing that declares expenditure for a whole year: empty, with no FY,
    and no sector shown at 0."""
    _seed_national(db_session, seed_country, seed_source_doc)
    db_session.commit()
    body = client.get("/api/v1/budget/enhanced").json()
    assert body["execution_by_sector"] == []
    assert body["execution_fiscal_year"] is None
    assert body["execution_source"] is None


def test_a_sector_missing_its_spend_is_absent_not_zero(client, db_session, seed_country, seed_source_doc):
    _, fy2526, common = _seed_national(db_session, seed_country, seed_source_doc)
    db_session.add_all([
        _expenditure_line(fy2526, common, "Health", 164.92e9, 157.20e9, "p.243"),
        _expenditure_line(fy2526, common, "Education", 757.50e9, None, "p.112"),
    ])
    db_session.commit()
    rows = client.get("/api/v1/budget/enhanced").json()["execution_by_sector"]
    assert [r["sector"] for r in rows] == ["Health"]


# ── The writer retires the exchequer proxies its expenditure rows replace ──


def test_writer_retires_same_period_proxies_and_keeps_other_periods(db_session, seed_country, seed_source_doc):
    from models import BudgetLine
    from seeding.config import SeedingSettings
    from seeding.domains.national_budget.parser import parse_national_budget_payload
    from seeding.domains.national_budget.writer import current_measure, persist_national_budget_records
    from seeding.types import DomainRunContext

    national, fy2526, common = _seed_national(db_session, seed_country, seed_source_doc)
    # What production holds today: FY2025/26 annual rows written as exchequer.
    db_session.add(
        BudgetLine(period_id=fy2526.id, category="Health", subcategory="Recurrent",
                   allocated_amount=90.38e9, actual_spent=89.41e9, **common)
    )
    db_session.commit()

    records = parse_national_budget_payload([{
        "entity_slug": "national-government", "entity": "National Government of Kenya",
        "fiscal_year": "FY 2025/26", "start_date": "2025-07-01", "end_date": "2026-06-30",
        "category": "Health", "subcategory": "Recurrent & Development",
        "allocated_amount": "164920000000", "actual_spent": "157200000000", "committed_amount": None,
        "source": "CoB NG-BIRR FY 2025/26 (annual)", "source_url": "https://cob.go.ke/x?wpdmdl=16454",
        "data_quality": "official", "notes": "n", "page_ref": "p.243",
        "provenance_extra": {"measure": "expenditure", "period": "annual"},
    }])
    stats = persist_national_budget_records(
        db_session, records, SeedingSettings(), DomainRunContext(since=None, dry_run=False)
    )
    db_session.commit()

    fy_lines = db_session.query(BudgetLine).filter(BudgetLine.period_id == fy2526.id).all()
    assert [(l.subcategory, current_measure(l)) for l in fy_lines] == [
        ("Recurrent & Development", "expenditure")
    ]
    assert stats.superseded == 1
    # The quarterly proxy and the fixture year are other periods: untouched.
    assert db_session.query(BudgetLine).filter(BudgetLine.entity_id == national.id).count() == 3


# ── The fetcher: annual expenditure is what makes the run LIVE ──────────────


def test_fetcher_promotes_the_annual_report_and_records_the_edition(tmp_path):
    from seeding import freshness
    from seeding.config import SeedingSettings
    from seeding.domains.national_budget import fetcher
    from seeding.http_client import SeedingHttpClient

    settings = SeedingSettings(
        storage_path=tmp_path / "s", cache_path=tmp_path / "c", log_path=tmp_path / "l" / "x.log",
        http_cache_enabled=False, live_pdf_fetch_enabled=True, rate_limit="1000/sec",
    )
    settings.ensure_directories()
    listing = (FIXTURES / "ng_birr_listing_2026-09-26.html").read_text()
    pages = _pages("ngbirr_fy2025_26_annual_pages.json")
    fake_pdf = tmp_path / "ng.pdf"
    fake_pdf.write_bytes(b"%PDF-1.7\n")

    def handler(request):
        return httpx.Response(200, text=listing, request=request)

    inner = httpx.Client(transport=httpx.MockTransport(handler))
    freshness.reset("national_budget")
    with SeedingHttpClient(settings, cache=None, client=inner) as client, patch(
        "seeding.pdf_download.get_or_download_pdf", return_value=fake_pdf
    ), patch.object(
        fetcher, "_extract_page_texts", return_value=[{"page": k, "text": v} for k, v in pages.items()]
    ), patch.object(fetcher, "_download_and_parse_ng_pdf") as exchequer:
        records = fetcher.fetch_national_budget_payload(client, settings)

    # The newest report IS the annual one, so the exchequer parse is skipped.
    assert not exchequer.called
    assert len(records) == 10
    assert {r["provenance_extra"]["measure"] for r in records} == {"expenditure"}
    assert freshness.get("national_budget")["mode"] == "live"
    assert freshness.get_publisher_edition("national_budget")["edition"] == "FY 2025/26"


def test_fetcher_refuses_a_report_whose_cover_disagrees_with_its_slug(tmp_path):
    from seeding.domains.national_budget import fetcher

    pages = _pages("ngbirr_fy2025_26_annual_pages.json")
    report = fetcher.AnnualReport(url="https://cob.go.ke/x?wpdmdl=1", fiscal_year="FY 2026/27", start_year=2026)
    fake_pdf = tmp_path / "ng.pdf"
    fake_pdf.write_bytes(b"%PDF-1.7\n")
    from seeding.config import SeedingSettings

    settings = SeedingSettings(cache_path=tmp_path / "c")
    with patch("seeding.pdf_download.get_or_download_pdf", return_value=fake_pdf), patch.object(
        fetcher, "_extract_page_texts", return_value=[{"page": k, "text": v} for k, v in pages.items()]
    ):
        records, status = fetcher._fetch_annual_sector_expenditure(None, settings, report)
    assert records == [] and status.startswith("refused(")


# ── The gate: red when COB has an annual report we do not publish ──────────


def _job(db_session, edition):
    from models import IngestionJob, IngestionStatus

    job = IngestionJob(
        domain="national_budget", status=IngestionStatus.COMPLETED,
        started_at=datetime(2026, 9, 26, 2, 30),
        meta={"source_mode": "live", **({"publisher_edition": edition} if edition else {})},
    )
    db_session.add(job)
    db_session.commit()


def _execution_finding(session):
    from seeding.staleness import run_all

    return [f for f in run_all(session) if f.label.startswith("Execution by sector")]


def test_gate_fails_when_cob_lists_an_annual_report_we_do_not_publish(db_session, seed_country, seed_source_doc):
    """RED before #241: run_all had no such finding at all — the nightly was
    [OK] while production served an empty panel."""
    _seed_national(db_session, seed_country, seed_source_doc)
    _job(db_session, {"dataset": "cob_ng_birr_annual", "edition": "FY 2025/26", "url": "u"})
    [finding] = _execution_finding(db_session)
    assert finding.level == "FAIL"
    assert "FY 2025/26" in finding.message and "NO edition" in finding.message


def test_gate_is_ok_when_we_publish_the_publishers_newest(db_session, seed_country, seed_source_doc):
    _, fy2526, common = _seed_national(db_session, seed_country, seed_source_doc)
    db_session.add(_expenditure_line(fy2526, common, "Health", 164.92e9, 157.20e9, "p.243"))
    _job(db_session, {"dataset": "cob_ng_birr_annual", "edition": "FY 2025/26", "url": "u"})
    [finding] = _execution_finding(db_session)
    assert finding.level == "OK"


def test_gate_warns_when_the_run_recorded_no_edition(db_session, seed_country, seed_source_doc):
    _, fy2526, common = _seed_national(db_session, seed_country, seed_source_doc)
    db_session.add(_expenditure_line(fy2526, common, "Health", 164.92e9, 157.20e9, "p.243"))
    _job(db_session, None)
    [finding] = _execution_finding(db_session)
    assert finding.level == "WARN" and "UNKNOWN" in finding.message


def test_sector_list_matches_the_quarterly_parsers_names():
    """One sector must not have two names across the two parsers."""
    from seeding.domains.national_budget.pdf_parser import _SECTORS as QUARTERLY

    assert {n for _, n in SECTORS} == {n for _, n in QUARTERLY}
