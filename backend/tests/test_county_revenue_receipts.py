"""County revenue: total is a real sum of parts from the CBIRR, or absent (#238).

``/counties/{id}/comprehensive`` published, for Nairobi::

    "revenue": {"total_revenue": 10789420000.0,
                "local_revenue": 10789420000.0,
                "equitable_share": 33831470000.0}

``total_revenue`` was own-source revenue under another name, and
``equitable_share`` was the budget minus it — a residual nobody published. The
Controller of Budget prints what each county actually received, stream by
stream, in Chapter 3 of the CBIRR: Nairobi received KSh 14,242,390,384 of
equitable share and KSh 26,035,120,532 in total in the first nine months of
FY2025/26 (Table 3.444).
"""

from __future__ import annotations

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from models import BudgetLine, Entity, EntityType, FiscalPeriod
from seeding.pdf_parsers import ExtractedTable, county_revenue_receipts

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
from cbirr_9m_fy2025_26_revenue_tables import REVENUE_TABLES  # noqa: E402


def _tables(county):
    return [
        ExtractedTable(t["page_number"], 0, t["headers"], t["rows"], (0, 0, 0, 0))
        for t in REVENUE_TABLES[county]
    ]


# --------------------------------------------------------------------------
# the extractor, on the report's own rows
# --------------------------------------------------------------------------


class TestReadFromTheReport:
    def test_nairobi_reconciles_to_its_printed_grand_total(self):
        streams, why = county_revenue_receipts(_tables("Nairobi"))

        assert why == ""
        assert streams["Total"] == (Decimal("44620889339"), Decimal("26035120532"))
        assert streams["Equitable Share"] == (
            Decimal("21417000000"), Decimal("14242390384")
        )
        assert streams["Additional Allocations"][1] == Decimal("59060570")
        # The parts are the total — the property that makes it publishable.
        parts = sum(v[1] for k, v in streams.items() if k != "Total")
        assert parts == streams["Total"][1]

    def test_a_table_without_most_subtotals_reconciles_on_its_items(self):
        """Bomet prints Sub-Totals for two of five sections."""
        streams, why = county_revenue_receipts(_tables("Bomet"))

        assert why == ""
        assert streams["Total"][1] == Decimal("5521238598")
        assert streams["Equitable Share"][1] == Decimal("4046361531")

    def test_a_section_that_lost_its_letter_still_opens_a_section(self):
        """Turkana numbers its grants section "3", not "C". The heading names a
        different stream after equitable share has closed, so it is the next
        section — and the grants sub-total does not land on equitable share."""
        streams, why = county_revenue_receipts(_tables("Turkana"))

        assert why == ""
        assert streams["Equitable Share"][1] == Decimal("9238563949")
        assert streams["Total"][1] == Decimal("11349697596")

    def test_two_subtotals_under_one_section_are_refused_not_merged(self):
        """Without that heading, the grants rows and their sub-total fall under
        equitable share. The streams would still add up to the Grand Total,
        which is exactly why reconciliation alone is not enough."""
        tables = _tables("Turkana")
        stripped = []
        for t in tables:
            rows = [r for r in t.rows if not r[1].startswith("Conditional Allocations from")]
            stripped.append(ExtractedTable(t.page_number, 0, t.headers, rows, (0, 0, 0, 0)))

        streams, why = county_revenue_receipts(stripped)

        assert streams is None
        assert why == "a_section_has_two_subtotals"

    def test_a_table_whose_streams_do_not_add_up_is_refused(self):
        tables = _tables("Nairobi")
        rows = [list(r) for r in tables[0].rows]
        for row in rows:
            if row[1] == "Grand Total":
                row[3] = "26,035,220,532"  # KSh 100,000 more than the streams
        tables[0] = ExtractedTable(613, 0, tables[0].headers, rows, (0, 0, 0, 0))

        streams, why = county_revenue_receipts(tables)

        assert streams is None
        assert why.startswith("streams_do_not_sum_to_grand_total")

    def test_no_grand_total_is_refused(self):
        tables = _tables("Nairobi")
        rows = [r for r in tables[0].rows if r[1] != "Grand Total"]
        streams, why = county_revenue_receipts(
            [ExtractedTable(613, 0, tables[0].headers, rows, (0, 0, 0, 0))]
        )
        assert (streams, why) == (None, "no_grand_total")


def test_the_category_is_spelled_once_on_each_side():
    """pdf_parsers keeps no backend import (its source keys the parse cache),
    so the category is written twice. This is what keeps them one string."""
    from seeding import pdf_parsers
    from services import county_budget

    assert pdf_parsers.REVENUE_RECEIPTS_CATEGORY == county_budget.REVENUE_RECEIPTS_CATEGORY
    assert pdf_parsers.REVENUE_TOTAL == county_budget.REVENUE_RECEIPTS_TOTAL
    assert county_budget.REVENUE_RECEIPTS_CATEGORY.lower() in (
        county_budget.NON_SECTOR_CATEGORIES
    )


def test_shilling_amounts_are_not_scaled_as_millions(tmp_path):
    """Chapter 2 aggregates are KSh millions; Chapter 3 streams are shillings.
    A KSh 50,000 refund scaled as millions would publish as KSh 50 billion."""
    from unittest.mock import patch

    from seeding.config import SeedingSettings
    from seeding.domains.counties_budget import fetcher

    settings = SeedingSettings(
        storage_path=tmp_path / "s", cache_path=tmp_path / "c",
        log_path=tmp_path / "l" / "x.log", live_pdf_fetch_enabled=False,
        enrich_with_worldbank=False,
    )
    settings.ensure_directories()
    cached = tmp_path / "x.pdf"
    cached.write_bytes(b"%PDF")
    parsed = [
        {
            "county": "Nairobi", "category": "Revenue Receipts",
            "subcategory": "Other Revenue", "allocated": Decimal("0"),
            "absorbed": Decimal("50000"), "absorption_rate": None,
            "currency": "KES", "amounts_in": "kes", "quarter": "9M",
            "fiscal_year": "2025/26",
        },
        {
            "county": "Nairobi", "category": "Total", "subcategory": None,
            "allocated": Decimal("44620.89"), "absorbed": Decimal("32122.66"),
            "absorption_rate": None, "currency": "KES", "quarter": "9M",
            "fiscal_year": "2025/26",
        },
    ]
    with patch("seeding.pdf_download.get_or_download_pdf", return_value=cached), patch(
        "seeding.parse_cache.parse_with_cache", return_value=parsed
    ):
        out = fetcher._download_and_parse_county_pdf(None, "https://cob.go.ke/x", settings)

    by_cat = {r["category"]: r for r in out}
    assert by_cat["Revenue Receipts"]["actual_amount"] == 50_000
    assert by_cat["Total"]["allocated_amount"] == pytest.approx(44_620_890_000)


# --------------------------------------------------------------------------
# the API
# --------------------------------------------------------------------------

NAIROBI_STREAMS = {
    "Balance Brought Forward": (1_000_000_000, 737_746_179),
    "Equitable Share": (21_417_000_000, 14_242_390_384),
    "Additional Allocations": (625_838_750, 59_060_570),
    "Own Source Revenue": (19_942_050_589, 9_440_565_157),
    "Facility Improvement Financing": (1_236_000_000, 1_348_850_165),
    "Appropriations in Aid": (400_000_000, 206_508_077),
    "Other Revenue": (0, 0),
    "Total": (44_620_889_339, 26_035_120_532),
}


@pytest.fixture()
def cbirr_period(db_session, seed_country, seed_source_doc):
    period = FiscalPeriod(
        id=9001, country_id=seed_country.id, label="FY2025/26 9M",
        start_date=datetime(2025, 7, 1), end_date=datetime(2026, 3, 31),
    )
    nairobi = Entity(
        id=3, country_id=seed_country.id, type=EntityType.COUNTY,
        canonical_name="Nairobi County", slug="nairobi-county",
    )
    baringo = Entity(
        id=33, country_id=seed_country.id, type=EntityType.COUNTY,
        canonical_name="Baringo County", slug="baringo-county",
    )
    db_session.add_all([period, nairobi, baringo])
    db_session.flush()

    def line(entity, category, allocated, spent, subcategory=None):
        return BudgetLine(
            entity_id=entity.id, period_id=period.id, category=category,
            subcategory=subcategory, allocated_amount=allocated,
            actual_spent=spent, currency="KES",
            source_document_id=seed_source_doc.id,
        )

    rows = [
        line(nairobi, "Total", 44_620_890_000, 32_122_660_000),
        line(nairobi, "Own Source Revenue", 21_178_050_000, 10_789_420_000),
        line(baringo, "Total", 9_542_030_000, 4_092_380_000),
        line(baringo, "Own Source Revenue", 651_940_000, 326_510_000),
    ]
    rows += [
        line(nairobi, "Revenue Receipts", target, actual, subcategory=stream)
        for stream, (target, actual) in NAIROBI_STREAMS.items()
    ]
    db_session.add_all(rows)
    db_session.commit()
    return period


def _comprehensive(client, county):
    from main import clear_all_caches

    clear_all_caches()
    response = client.get(f"/api/v1/counties/{county}/comprehensive")
    assert response.status_code == 200, response.text[:300]
    return response.json()


def test_total_revenue_is_what_the_county_received(client, cbirr_period):
    revenue = _comprehensive(client, "nairobi-county")["revenue"]

    assert revenue["total_revenue"] == 26_035_120_532
    assert revenue["equitable_share"] == 14_242_390_384
    assert revenue["additional_allocations"] == 59_060_570
    # Cash includes the chapter's liquor AiA; preserve Table 2.1 separately.
    assert revenue["local_revenue"] == 10_995_923_399
    assert revenue["summary_table_own_source_revenue"] == 10_789_420_000
    assert revenue["local_revenue_basis"] == "cash_receipts"
    assert revenue["total_revenue"] != revenue["local_revenue"]
    assert revenue["fiscal_year"] == "FY2025/26 9M"
    assert sum(s["actual"] for s in revenue["streams"]) == revenue["total_revenue"]


def test_without_a_reconciled_table_total_revenue_is_absent(client, cbirr_period):
    """Baringo has own-source revenue and no revenue table rows.

    RED before #238: total_revenue came back as the own-source 326.51M, and
    equitable_share as the budget minus it (9.22B)."""
    revenue = _comprehensive(client, "baringo-county")["revenue"]

    assert revenue["local_revenue"] == 326_510_000
    assert revenue["total_revenue"] is None
    assert revenue["equitable_share"] is None
    assert revenue["streams"] == []
    assert revenue["total_revenue_absent_reason"] == "no_reconciled_cbirr_revenue_table"


def test_revenue_rows_are_never_counted_as_budget(client, cbirr_period):
    """The receipts sit in budget_lines; no budget figure may include them."""
    from main import clear_all_caches

    clear_all_caches()
    listed = {c["name"]: c for c in client.get("/api/v1/counties").json()}
    detail = _comprehensive(client, "nairobi-county")

    assert listed["Nairobi"]["total_budget"] == 44_620_890_000
    assert "Revenue Receipts" not in listed["Nairobi"]["sector_breakdown"]
    assert detail["budget"]["total_allocated"] == 44_620_890_000
    assert "Revenue Receipts" not in detail["budget"]["sector_breakdown"]


@pytest.fixture()
def contradicting_report(db_session, seed_country, seed_source_doc):
    """Mombasa in the FY2025/26 CBIRR: Table 2.1 and its own revenue table
    disagree on own-source revenue by KSh 14.9B."""
    period = FiscalPeriod(
        id=9002, country_id=seed_country.id, label="FY2025/26",
        start_date=datetime(2025, 7, 1), end_date=datetime(2026, 6, 30),
    )
    mombasa = Entity(
        id=47, country_id=seed_country.id, type=EntityType.COUNTY,
        canonical_name="Mombasa County", slug="mombasa-county",
    )
    db_session.add_all([period, mombasa])
    db_session.flush()
    streams = {
        "Balance Brought Forward": (219_300_000, 191_000_000),
        "Equitable Share": (8_383_390_000, 8_383_390_000),
        "Additional Allocations": (1_734_140_000, 1_001_800_000),
        "Own Source Revenue": (6_664_570_000, 3_799_700_000),
        "Facility Improvement Financing": (1_723_610_000, 2_414_890_000),
        "Total": (18_725_000_000, 15_790_780_000),
    }
    rows = [
        BudgetLine(
            entity_id=47, period_id=period.id, category="Total",
            allocated_amount=18_725_000_000, actual_spent=13_641_310_000,
            currency="KES", source_document_id=seed_source_doc.id,
        ),
        BudgetLine(
            entity_id=47, period_id=period.id, category="Own Source Revenue",
            allocated_amount=8_388_180_000, actual_spent=21_126_230_000,
            currency="KES", source_document_id=seed_source_doc.id,
        ),
    ] + [
        BudgetLine(
            entity_id=47, period_id=period.id, category="Revenue Receipts",
            subcategory=name, allocated_amount=t, actual_spent=a, currency="KES",
            source_document_id=seed_source_doc.id,
        )
        for name, (t, a) in streams.items()
    ]
    db_session.add_all(rows)
    db_session.commit()


def test_distinct_summary_measure_does_not_erase_reconciled_cash_receipts(
    client, contradicting_report
):
    """RED before #238: total_revenue was the 21.13B own-source figure."""
    revenue = _comprehensive(client, "mombasa-county")["revenue"]

    assert revenue["local_revenue"] == 6_214_590_000
    assert revenue["summary_table_own_source_revenue"] == 21_126_230_000
    assert revenue["total_revenue"] == 15_790_780_000
    assert revenue["equitable_share"] == 8_383_390_000
    assert revenue["total_revenue_absent_reason"] is None
    assert revenue["own_source_disagreement"] == {
        "summary_table": 21_126_230_000,
        "county_revenue_table": 6_214_590_000,
    }


def test_agreeing_tables_are_published_and_say_so(client, cbirr_period):
    """Control: Nairobi's Table 2.1 own-source figure is its county table's
    ordinary OSR + FIF (9,440,565,157 + 1,348,850,165 = 10,789,415,322 against
    10,789,420,000 printed to the 10,000) — Table 2.1 leaves its liquor A-i-A
    out — so the revenue table is published and nothing is flagged."""
    revenue = _comprehensive(client, "nairobi-county")["revenue"]
    assert revenue["own_source_disagreement"] is None
    assert revenue["total_revenue"] == 26_035_120_532


# --------------------------------------------------------------------------
# found by an adversarial pass: inputs that published and should not have
# --------------------------------------------------------------------------


def _edit(county, fn):
    """The county's real tables with ``fn(row) -> row`` applied to every row."""
    return [
        ExtractedTable(t.page_number, 0, t.headers, [fn(list(r)) for r in t.rows], (0, 0, 0, 0))
        for t in _tables(county)
    ]


class TestRefusesWhatItCannotStandBehind:
    @pytest.mark.parametrize("blank", ["", "-"])
    def test_a_table_with_no_numbers_is_not_a_zero_revenue(self, blank):
        tables = _edit("Nairobi", lambda r: r[:2] + [blank] * (len(r) - 2))
        streams, why = county_revenue_receipts(tables)
        assert streams is None, streams

    def test_a_heading_that_lost_its_letter_does_not_fold_into_the_stream_above(self):
        """Bomet's OSR section prints no Sub-Total; with its FIF heading
        numbered "5" instead of lettered "E", FIF was summed into OSR and the
        table still reconciled."""
        def renumber(r):
            if r[0] == "E" and "Facility" in (r[1] or ""):
                r[0] = "5"
            return r

        streams, why = county_revenue_receipts(_edit("Bomet", renumber))
        assert streams is None or (
            "Facility Improvement Financing" in streams
            and streams["Own Source Revenue"][1] == Decimal("88046345")
        ), streams

    @pytest.mark.parametrize("bad", ["NaN", "Infinity", "sNaN"])
    def test_a_non_number_in_a_cell_is_a_refusal_not_a_crash(self, bad):
        def poison(r):
            if r[1] == "Equitable Share":
                r[3] = bad
            return r

        streams, why = county_revenue_receipts(_edit("Nairobi", poison))
        assert streams is None

    @pytest.mark.parametrize("cell", ["1e6", "1_000_000", "1,000,000-"])
    def test_loose_number_forms_are_not_numbers(self, cell):
        from seeding.pdf_parsers import _kes_cell

        assert _kes_cell(cell) is None

    def test_an_unreadable_target_is_absent_not_zero(self):
        def poison(r):
            if r[1] == "Grand Total":
                r[2] = "n/a"
            return r

        streams, why = county_revenue_receipts(_edit("Nairobi", poison))
        assert streams is None or streams["Total"][0] is None

    def test_a_negative_total_is_refused(self):
        def negate(r):
            return r[:2] + [
                f"({c})" if c and c[0].isdigit() else c for c in r[2:]
            ]

        streams, why = county_revenue_receipts(_edit("Nairobi", negate))
        assert streams is None


class TestTheBlockChecksWhatItPublishes:
    GOOD = {
        "Equitable Share": {"target": 1.0, "actual": 1_000e6},
        "Own Source Revenue": {"target": 1.0, "actual": 100e6},
        "Total": {"target": 2.0, "actual": 1_100e6},
    }

    def _block(self, receipts, local=100e6):
        from main import county_revenue_block

        return county_revenue_block(
            receipts, local_revenue=local, own_source_target=None, fiscal_year="FY2025/26"
        )

    def test_control_publishes(self):
        assert self._block(self.GOOD)["total_revenue"] == 1_100e6

    def test_without_table_2_1_the_contradiction_check_cannot_run(self):
        result = self._block(self.GOOD, local=None)
        assert result["total_revenue"] == 1_100e6
        assert result["summary_table_own_source_revenue"] is None
        assert result["own_source_disagreement"] is None

    @pytest.mark.parametrize("local", [float("nan"), float("inf"), True])
    def test_a_non_figure_own_source_is_not_agreement(self, local):
        result = self._block(self.GOOD, local=local)
        assert result["total_revenue"] == 1_100e6
        assert result["summary_table_own_source_revenue"] is None
        assert result["own_source_disagreement"] is None

    def test_streams_that_do_not_sum_to_the_total_are_withheld(self):
        receipts = dict(self.GOOD, Total={"target": 2.0, "actual": 9_000e6})
        assert self._block(receipts)["total_revenue"] is None

    def test_a_total_alone_is_withheld(self):
        assert self._block({"Total": {"target": 1.0, "actual": 5e9}})["total_revenue"] is None

    def test_a_nan_stream_is_withheld(self):
        receipts = dict(self.GOOD)
        receipts["Equitable Share"] = {"target": 1.0, "actual": float("nan")}
        assert self._block(receipts)["total_revenue"] is None


def test_a_revenue_table_that_raises_costs_that_county_only(monkeypatch):
    """The revenue extraction runs inside the CBIRR parse; an exception there
    used to abort the whole parse and every county's budget rows with it."""
    from pathlib import Path

    from seeding import pdf_parsers

    def boom(tables):
        raise ArithmeticError("a cell nobody anticipated")

    from types import SimpleNamespace

    caption = "Table 3.444: Nairobi City County, Revenue Performance in the first nine months"
    pages = [
        SimpleNamespace(
            extract_text=(lambda i=i: caption if i == 612 else ""),
            close=lambda: None,
        )
        for i in range(1, 700)
    ]
    pdf = SimpleNamespace(pages=pages)

    class _Ctx:
        def __enter__(self):
            return pdf

        def __exit__(self, *exc):
            return False

    called = []

    def boom(tables):
        called.append(True)
        raise ArithmeticError("a cell nobody anticipated")

    monkeypatch.setattr(pdf_parsers, "county_revenue_receipts", boom)
    monkeypatch.setattr(pdf_parsers.pdfplumber, "open", lambda _p: _Ctx())
    parser = pdf_parsers.CoBQuarterlyReportParser(Path("report-2025-26.pdf"))
    parser.tables = _tables("Nairobi")

    assert parser._extract_county_revenue_receipts() == []
    assert called, "the extractor was never reached — the test proves nothing"


def test_cash_receipts_and_summary_measure_remain_distinct_on_every_county_view(
    client, contradicting_report
):
    listing = client.get("/api/v1/counties").json()[0]
    detail = client.get("/api/v1/counties/047").json()
    comprehensive = _comprehensive(client, "mombasa-county")
    for row in [listing, detail]:
        assert row["revenue_collection"] == 6_214_590_000
        assert row["revenue"]["local_revenue_basis"] == "cash_receipts"
        assert row["revenue"]["summary_table_own_source_revenue"] == 21_126_230_000
        assert row["revenue"]["own_source_disagreement"] is not None
    assert comprehensive["revenue"]["local_revenue"] == 6_214_590_000
    assert comprehensive["revenue"]["total_revenue"] == 15_790_780_000
    assert (
        comprehensive["revenue"]["total_revenue_basis"]
        == "cash_receipts_including_opening_balance"
    )
