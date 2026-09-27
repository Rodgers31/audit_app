"""County pending bills read from the Controller of Budget's year-end report (#238).

The county page's pending-bills figure used to come from Table 10 of the
Treasury's Budget Review and Outlook Paper. That table is the CoB's, reprinted:
BROP 2025 Table 10 is the CoB's FY 2024/25 Table 2.9 row for row, less Narok
(6,151.50m, left blank), and BROP 2026 Table 11 is the CoB's NINE-MONTH table
(31 March 2026) verbatim, printed after the CoB had published 30 June 2026.
So the figure is now read from the original: the full-year County Governments
Budget Implementation Review Report, table of trade payables at 30 June.

Every test here runs on the report's own rows (``fixtures/
cbirr_county_payables_tables.py``), including one that assembles a stand-in
PDF from those pages and runs the whole reader over it. A test that needs the
real 53MB file runs only when ``CBIRR_FY2526_PDF`` points at it.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
import cbirr_county_payables_tables as fx  # noqa: E402

from seeding.pdf_parsers import (  # noqa: E402
    KENYAN_COUNTIES,
    CountyTableIncomplete,
    NotAYearEndTable,
    chapter_closing_total,
    check_payables_against_printed_total,
    classify_payables_row,
    county_payables_rows,
    parse_caption_date,
    payables_toc_entries,
)

D = Decimal


def _read(pages):
    rows, printed = county_payables_rows([(p, t) for p, t in pages])
    return rows, printed


# --------------------------------------------------------------------------
# Table 2.10, FY 2025/26
# --------------------------------------------------------------------------


class TestTheYearEndTable:
    def test_all_47_counties_sum_to_the_printed_grand_total(self):
        rows, printed = _read(fx.FY2526_TABLE_PAGES)
        check_payables_against_printed_total(rows, printed, "fy2526")

        assert sorted(rows) == sorted(KENYAN_COUNTIES)
        assert printed["total"] == D("172526.69")
        classified = {c: classify_payables_row(r) for c, r in rows.items()}
        reported = [c for c in classified.values() if c["status"] == "reported"]
        assert len(reported) == 46
        assert sum(D(c["total_millions"]) for c in reported) == D("172526.69")
        assert classified["Nairobi"]["total_millions"] == "86899.38"
        # The ageing analysis on p.53 lists the same counties; it is not read.
        assert rows["Baringo"]["cells"]["total"] == (True, D("870.23"))

    def test_nandi_did_not_report_and_is_absent_not_zero(self):
        """Its row prints "-" in every column and "0" in the ratio column."""
        rows, _ = _read(fx.FY2526_TABLE_PAGES)
        nandi = classify_payables_row(rows["Nandi"])

        assert nandi["status"] == "not_reported"
        assert nandi["total_millions"] is None

    def test_the_counties_the_cob_marks_inconsistent_are_the_asterisked_rows(self):
        rows, _ = _read(fx.FY2526_TABLE_PAGES)
        marked = sorted(c for c, r in rows.items() if r["cob_marked_inconsistent"])
        assert marked == [
            "Bomet", "Bungoma", "Kilifi", "Kisumu", "Laikipia", "Makueni",
            "Marsabit", "Migori", "Murang'a", "Nakuru", "Narok", "Nyeri",
            "Tharaka Nithi", "Turkana",
        ]

    def test_counties_whose_assembly_printed_nothing_are_executive_only(self):
        """The report: Nandi, and the Assemblies of Elgeyo Marakwet,
        Kirinyaga, Kisumu, Lamu, Nyamira, Samburu, Tana River, Uasin Gishu
        and West Pokot, did not report."""
        rows, _ = _read(fx.FY2526_TABLE_PAGES)
        no_assembly = sorted(
            c for c, r in rows.items() if not classify_payables_row(r)["assembly_printed"]
        )
        assert no_assembly == [
            "Elgeyo Marakwet", "Kirinyaga", "Kisumu", "Lamu", "Nandi", "Nyamira",
            "Samburu", "Tana River", "Uasin Gishu", "West Pokot",
        ]
        uasin = classify_payables_row(rows["Uasin Gishu"])
        assert (uasin["total_millions"], uasin["assembly_millions"]) == ("1153.72", None)


class TestThePreviousYearsLayout:
    def test_fy2024_25_reads_whole_including_the_row_the_brop_left_blank(self):
        """Page 58 splits the budget column in two: 11 cells, not 10."""
        rows, printed = _read(fx.FY2425_TABLE_PAGES)
        check_payables_against_printed_total(rows, printed, "fy2425")

        classified = {c: classify_payables_row(r) for c, r in rows.items()}
        assert printed["total"] == D("183028.75")
        assert all(c["status"] == "reported" for c in classified.values())
        assert classified["Narok"]["total_millions"] == "6151.50"
        # BROP 2025 prints 2,380.5 for Tana River; the CoB prints 2,353.25.
        assert classified["Tana River"]["total_millions"] == "2353.25"
        assert classified["Baringo"]["budget_millions"] == "8983.76"


# --------------------------------------------------------------------------
# refusing a table that is not whole
# --------------------------------------------------------------------------


def _drop_county(pages, county):
    out = []
    for p, table in pages:
        out.append((p, [r for r in table if (r[0] or "").replace("*", "").strip() != county]))
    return out


def _edit_cell(pages, county, col, value):
    out = []
    for p, table in pages:
        new = []
        for r in table:
            r = list(r)
            # The payables table's row, not the ageing table's (6 cells).
            if len(r) >= 10 and (r[0] or "").replace("*", "").strip() == county:
                r[col] = value
            new.append(r)
        out.append((p, new))
    return out


class TestRefusal:
    def test_a_missing_county_refuses_the_table(self):
        rows, printed = _read(_drop_county(fx.FY2526_TABLE_PAGES, "Kisii"))
        with pytest.raises(CountyTableIncomplete, match="Kisii"):
            check_payables_against_printed_total(rows, printed, "t")

    def test_a_misread_grand_total_refuses_the_table(self):
        """A row read from the wrong column keeps the count right; the sum
        against the printed Total is what catches it."""
        pages = _edit_cell(fx.FY2526_TABLE_PAGES, "Kisii", 7, "12,477.00")
        rows, printed = _read(pages)
        with pytest.raises(CountyTableIncomplete, match="total rows sum"):
            check_payables_against_printed_total(rows, printed, "t")

    def test_no_total_row_refuses_the_table(self):
        pages = [(p, [r for r in t if (r[0] or "").strip() != "Total"]) for p, t in fx.FY2526_TABLE_PAGES]
        rows, printed = _read(pages)
        with pytest.raises(CountyTableIncomplete, match="no Total row"):
            check_payables_against_printed_total(rows, printed, "t")

    def test_a_county_twice_refuses_the_table(self):
        page, table = fx.FY2526_TABLE_PAGES[1]
        dup = [(page, table), (page, [table[0], table[2]])]
        with pytest.raises(CountyTableIncomplete, match="twice"):
            county_payables_rows(dup)


class TestOneRow:
    @staticmethod
    def _row(**cells):
        base = {
            "executive_recurrent": (True, D("1")), "executive_development": (True, D("1")),
            "executive": (True, D("2")), "assembly_recurrent": (False, None),
            "assembly_development": (False, None), "assembly": (False, None),
            "total": (True, D("2")), "budget": (True, D("100")), "pct_of_budget": (True, D("2")),
        }
        base.update(cells)
        return {"county": "Kisii", "page": 52, "cob_marked_inconsistent": False, "cells": base}

    def test_a_row_that_adds_up_is_reported(self):
        assert classify_payables_row(self._row())["total_millions"] == "2"

    def test_a_printed_zero_is_a_figure(self):
        out = classify_payables_row(self._row(executive=(True, D("0")), total=(True, D("0.00"))))
        assert (out["status"], out["total_millions"]) == ("reported", "0.00")

    def test_a_total_that_is_not_a_number_is_withheld(self):
        out = classify_payables_row(self._row(total=(True, None)))
        assert (out["status"], out["total_millions"]) == ("withheld", None)

    def test_sub_totals_that_contradict_the_total_are_withheld(self):
        out = classify_payables_row(self._row(total=(True, D("9"))))
        assert out["status"] == "withheld"
        assert "Executive + Assembly" in out["withheld_reason"]

    def test_sub_totals_with_no_total_are_withheld_not_absent(self):
        out = classify_payables_row(self._row(total=(False, None)))
        assert out["status"] == "withheld"


# --------------------------------------------------------------------------
# dates and the List of Tables
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("30 June 2026", date(2026, 6, 30)),
        ("30th June 2025", date(2025, 6, 30)),
        ("30 Jun 2026", date(2026, 6, 30)),
        ("30 June, 2026", date(2026, 6, 30)),
        ("June 30, 2025", date(2025, 6, 30)),
        ("31st March 2026", date(2026, 3, 31)),
        ("September 30 2025", date(2025, 9, 30)),
        ("the end of the year", None),
        ("31 June 2026", None),
    ],
)
def test_caption_dates(text, expected):
    assert parse_caption_date(text) == expected


class TestTheListOfTables:
    def test_it_names_the_county_table_its_date_and_page(self):
        toc = payables_toc_entries("\n".join(fx.FY2526_TOC_LINES))
        assert toc["counties"] == ("2.10", date(2026, 6, 30), 17)

    def test_it_names_every_county_chapter_table_but_nandis(self):
        toc = payables_toc_entries("\n".join(fx.FY2526_TOC_LINES))
        assert sorted(toc["county"]) == sorted(c for c in KENYAN_COUNTIES if c != "Nandi")
        assert toc["county"]["Uasin Gishu"][0] == "3.678"
        # "Nairobi City County Trade Payables" is Nairobi.
        assert toc["county"]["Nairobi"][0] == "3.470"

    def test_ageing_and_salary_arrears_tables_are_not_payables_tables(self):
        entries = payables_toc_entries("\n".join(fx.FY2526_TOC_LINES))
        nums = {v[0] for v in entries["county"].values()} | {entries["counties"][0]}
        assert "2.13" not in nums  # Salary Arrears and Statutory Deductions ...
        assert "3.679" not in nums  # Uasin Gishu County Executive ... Ageing


# --------------------------------------------------------------------------
# the chapter cross-check
# --------------------------------------------------------------------------


class TestTheChapterTable:
    @pytest.mark.parametrize(
        "county, closing",
        [
            ("Uasin Gishu", D("1481436003")),  # formula label "e=a-c*b"
            ("Nairobi City", D("86899384227")),  # no formula: "Outstanding Trade"
            ("Busia", D("2594370956")),  # "523, 441,337" — spaced thousands
            ("Baringo", D("870231430")),
            ("Kiambu", D("5800134663")),
        ],
    )
    def test_the_closing_total_of_each_layout_this_edition_uses(self, county, closing):
        assert chapter_closing_total(fx.FY2526_CHAPTER_BLOCKS[county]["text"]) == closing

    @pytest.mark.parametrize("table", ["3.364", "3.3"])
    def test_the_previous_years_across_the_page_layout_is_not_read(self, table):
        """RED on the first rule written ("the last Total row"): it read
        Nairobi's County Assembly, 650,598,395, as the county's closing
        balance — a note that would have told readers the report disagrees
        with itself by 86 billion."""
        assert chapter_closing_total(fx.FY2425_CHAPTER_BLOCKS[table]["text"]) is None

    def test_a_header_row_of_step_letters_is_not_read(self):
        block = (
            "Table 3.999: Somewhere County Trade Payables as of 30 June 2026\n"
            "a b c d e=a-b-c+d\n"
            "Total 1,000 2,000 300 400 2,300\n"
        )
        assert chapter_closing_total(block) is None


# --------------------------------------------------------------------------
# the whole reader, over a stand-in PDF built from the report's own pages
# --------------------------------------------------------------------------


class _Page:
    def __init__(self, text="", tables=()):
        self._text, self._tables = text, list(tables)

    def extract_text(self):
        return self._text

    def extract_tables(self):
        return [list(map(list, t)) for t in self._tables]

    def flush_cache(self):
        pass


class _Pdf:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _stand_in(toc_lines, *, with_chapters=True):
    pages = [_Page() for _ in range(900)]
    pages[8] = _Page("List of Tables\n" + "\n".join(toc_lines))
    by_page = {}
    for p, t in fx.FY2526_TABLE_PAGES:
        by_page.setdefault(p, []).append(t)
    for p, tables in by_page.items():
        text = "Table 2.10: Trade Payables for the Counties as of 30 June 2026" if p == 51 else ""
        pages[p - 1] = _Page(text, tables)
    if with_chapters:
        for block in fx.FY2526_CHAPTER_BLOCKS.values():
            pages[block["pdf_page"] - 1] = _Page(block["text"])
    return _Pdf(pages)


@pytest.fixture()
def stand_in(monkeypatch, tmp_path):
    import seeding.pdf_parsers as pp

    path = tmp_path / "cbirr.pdf"
    path.write_bytes(b"%PDF-1.7 stand-in")

    def install(pdf):
        monkeypatch.setattr(pp.pdfplumber, "open", lambda _p: pdf)
        return path

    return install


def test_the_whole_reader_on_the_reports_own_pages(stand_in):
    from seeding.pdf_parsers import cbirr_year_end_trade_payables

    out = {e["county"]: e for e in cbirr_year_end_trade_payables(stand_in(_stand_in(fx.FY2526_TOC_LINES)))}

    assert len(out) == 47
    nairobi = out["Nairobi"]
    assert (nairobi["as_at"], nairobi["fiscal_year"], nairobi["table"]) == (
        "2026-06-30", "FY 2025/26", "Table 2.10",
    )
    assert nairobi["total_millions"] == "86899.38"
    assert nairobi["page"] == 52
    assert out["Nandi"]["status"] == "not_reported"
    # The chapter cross-check, where the stand-in carries the chapter page.
    assert out["Uasin Gishu"]["chapter_total_millions"] == "1481.44"
    assert out["Uasin Gishu"]["chapter_table"] == "Table 3.678"
    assert out["Nairobi"]["chapter_total_millions"] == "86899.38"
    # Where it does not, no cross-check — never a guess.
    assert out["Kisii"]["chapter_total_millions"] is None


def test_a_quarterly_table_is_refused(stand_in):
    """Year-end only: the stock is seasonal, and the quarterly editions print
    0.00 where the annual prints "-"."""
    from seeding.pdf_parsers import cbirr_year_end_trade_payables

    toc = [
        line.replace("as of 30 June 2026", "as of 31st March 2026")
        for line in fx.FY2526_TOC_LINES
    ]
    with pytest.raises(NotAYearEndTable, match="not 30 June"):
        cbirr_year_end_trade_payables(stand_in(_stand_in(toc)))


# --------------------------------------------------------------------------
# the fetcher: which edition, and what reaches the writer
# --------------------------------------------------------------------------


LISTING = "\n".join(
    f"<a onclick=\"location.href='https://cob.go.ke/download/{slug}/?wpdmdl={n}'\" href='#'>Download</a>"
    for slug, n in (
        ("county-governments-budget-implementation-review-report-fy-2024-25", 16263),
        ("county-governments-budget-implementation-review-report-the-first-quarter-of-fy-2025-26", 16323),
        ("county-governments-budget-implementation-review-report-first-half-of-fy-2025-26", 16349),
        ("county-governments-budget-implementation-review-report-for-the-first-nine-months-of-fy-2025-26", 16378),
        ("county-governments-budget-implementation-review-report-for-the-financial-year-2025-26", 16482),
        ("national-government-budget-implementation-review-report-fy-2025-26", 16490),
    )
)


def test_only_full_year_editions_are_candidates_newest_first():
    from seeding.domains.pending_bills.fetcher import year_end_cbirr_links

    links = year_end_cbirr_links(LISTING)
    assert [link.rsplit("=", 1)[1] for link in links] == ["16482", "16263"]


def _entries():
    rows, _ = _read(fx.FY2526_TABLE_PAGES)
    out = []
    for county in KENYAN_COUNTIES:
        e = classify_payables_row(rows[county])
        e.update(
            as_at="2026-06-30", fiscal_year="FY 2025/26", table="Table 2.10",
            chapter_table=None, chapter_page=None, chapter_total_millions=None,
        )
        out.append(e)
    return out


def test_the_payload_states_every_reported_county_and_no_other():
    from seeding.domains.pending_bills.fetcher import county_payables_payload
    from seeding.domains.pending_bills.parser import parse_pending_bills_payload

    payload = county_payables_payload(_entries(), "https://cob.go.ke/x?wpdmdl=16482")
    records = {r.entity_name: r for r in parse_pending_bills_payload(payload)}

    assert payload["publication"] == "cob_cbirr_year_end"
    assert len(records) == 46
    assert "Nandi County" not in records
    assert records["Nairobi County"].total_pending == D("86899380000.00")
    assert records["Nairobi County"].as_at == "2026-06-30"
    assert sum(r.total_pending for r in records.values()) == D("172526690000.00")


def test_notes_are_what_the_report_says_and_rounding_is_not_a_note():
    from seeding.domains.pending_bills.fetcher import _reader_notes

    entries = {e["county"]: e for e in _entries()}
    uasin = {**entries["Uasin Gishu"], "chapter_total_millions": "1481.44",
             "chapter_table": "Table 3.678", "chapter_page": 861}
    vihiga = {**entries["Vihiga"], "chapter_total_millions": "810.64"}  # 0.60m: rounding
    turkana = entries["Turkana"]

    assert [n["code"] for n in _reader_notes(uasin)] == [
        "assembly_not_printed", "chapter_table_differs",
    ]
    assert _reader_notes(uasin)[1]["chapter_total"] == "1481440000.00"
    assert _reader_notes(vihiga) == []
    assert [n["code"] for n in _reader_notes(turkana)] == ["cob_marked_inconsistent"]


@pytest.mark.skipif(
    not os.environ.get("CBIRR_FY2526_PDF"),
    reason="set CBIRR_FY2526_PDF to the 53MB FY 2025/26 CBIRR to run",
)
def test_the_real_report():
    from seeding.pdf_parsers import cbirr_year_end_trade_payables

    out = {e["county"]: e for e in cbirr_year_end_trade_payables(Path(os.environ["CBIRR_FY2526_PDF"]))}
    assert sum(D(e["total_millions"]) for e in out.values() if e["total_millions"]) == D("172526.69")
    differs = sorted(
        c for c, e in out.items()
        if e["total_millions"] and e["chapter_total_millions"]
        and abs(D(e["total_millions"]) - D(e["chapter_total_millions"])) >= 1
    )
    assert differs == [
        "Bomet", "Elgeyo Marakwet", "Kajiado", "Narok", "Tharaka Nithi",
        "Turkana", "Uasin Gishu",
    ]


def test_the_fetcher_declares_the_publications_the_gate_reads():
    """Two copies of each string: a typo in either would unpublish a side."""
    from seeding.domains.pending_bills import fetcher
    from services import publication_gate as gate

    assert fetcher.COB_YEAR_END_PUBLICATION == gate.COUNTY_PENDING_BILLS_PUBLICATION
    assert fetcher.BROP_PUBLICATION == gate.NATIONAL_PENDING_BILLS_PUBLICATION
    assert gate.COUNTY_PENDING_BILLS_PUBLICATION != gate.NATIONAL_PENDING_BILLS_PUBLICATION


# --------------------------------------------------------------------------
# found by an adversarial pass after the tests above were green
# --------------------------------------------------------------------------


def _insert_column(pages, at):
    """A phantom empty column, as a changed layout would read."""
    return [(p, [list(r[:at]) + [""] + list(r[at:]) for r in t]) for p, t in pages]


class TestFoundByTheAdversarialPass:
    def test_a_shifted_column_refuses_the_table_rather_than_withholding_every_row(self):
        """The shift moves the Total row too, so the column sums agreed; every
        row then failed its own arithmetic, the payload was empty, the writer
        retired nothing, and last year's figures stood as current."""
        page_pairs = [(p, [r[:10] for r in t]) for p, t in fx.FY2526_TABLE_PAGES]
        rows, printed = _read(_insert_column(page_pairs, 4))
        with pytest.raises(CountyTableIncomplete, match="do not add up"):
            check_payables_against_printed_total(rows, printed, "t")

    def test_a_fetch_with_no_county_stated_is_a_failure(self):
        from seeding.domains.pending_bills.fetcher import (
            CountyPayablesUnavailable,
            check_county_payables_entries,
        )

        entries = [{**e, "status": "withheld"} for e in _entries()]
        with pytest.raises(CountyPayablesUnavailable, match="no county"):
            check_county_payables_entries(entries, "https://c/x-2025-26/?wpdmdl=1")

    def test_a_table_for_another_year_than_the_edition_is_refused(self):
        from seeding.domains.pending_bills.fetcher import (
            CountyPayablesUnavailable,
            check_county_payables_entries,
        )

        entries = [{**e, "as_at": "2025-06-30"} for e in _entries()]
        with pytest.raises(CountyPayablesUnavailable, match="FY 2025/26"):
            check_county_payables_entries(
                entries,
                "https://cob.go.ke/download/county-governments-budget-implementation-"
                "review-report-for-the-financial-year-2025-26/?wpdmdl=16482",
            )
        check_county_payables_entries(_entries(), "https://c/report-fy-2025-26/?wpdmdl=1")

    def test_the_list_of_tables_prefers_this_years_county_table(self):
        lines = [
            "Table 2.9: Pending Bills for the Counties as at 30th June 2025 .......16",
        ] + fx.FY2526_TOC_LINES
        assert payables_toc_entries("\n".join(lines))["counties"][:2] == (
            "2.10", date(2026, 6, 30),
        )

    @pytest.mark.parametrize(
        "block",
        [
            # A Sub-Total is one entity's figure.
            "Table 3.9: X County Trade Payables as of 30 June 2026\n"
            "Total 1 2 3\nTotal 4 5 6\n"
            "Outstanding trade payables e=a-c*b County Executive 1 2 3\n"
            "Sub-Total 255,932,238 1,150,673,060 1,406,605,299\n",
            # A negative closing balance is not a stock.
            "Table 3.9: X County Trade Payables as of 30 June 2026\n"
            "Total 1 2 3\nTotal 4 5 6\n"
            "e=a-c*b County Assembly\n"
            "Total 255,932,238 752,969,552 -1,481,436,003\n",
            # Printed in millions, which would be read as shillings.
            "Table 3.9: X County Trade Payables as of 30 June 2026 (Kshs. Million)\n"
            "Total 1 2 3\nTotal 4 5 6\n"
            "e=a-c*b County Assembly\n"
            "Total 255.93 897.79 1,153.72\n",
            # A column header that starts "Outstanding", above every Total row.
            "Table 3.9: X County Trade Payables as of 30 June 2026\n"
            "Outstanding trade payables as of 30 June 2026 Development Recurrent Total\n"
            "County Executive\n"
            "Total 400,000,000 600,000,000 1,000,000,000\n"
            "County Assembly\n"
            "Total 50,000,000 100,000,000 150,000,000\n",
        ],
        ids=["sub-total", "negative", "millions", "header-first"],
    )
    def test_the_chapter_check_does_not_guess(self, block):
        assert chapter_closing_total(block) is None

    def test_a_total_with_no_sub_totals_is_withheld(self):
        out = classify_payables_row(TestOneRow._row(
            executive=(False, None), total=(True, D("0.45")),
        ))
        assert out["status"] == "withheld"

    def test_an_asterisk_anywhere_in_the_label_is_the_cobs_flag(self):
        page, table = next(
            (p, t) for p, t in fx.FY2526_TABLE_PAGES
            if any((r[0] or "").startswith("Kilifi") for r in t)
        )
        edited = [
            ["*Kilifi" if (r[0] or "").startswith("Kilifi") else r[0], *r[1:]] for r in table
        ]
        rows, _ = county_payables_rows([(page, edited)])
        assert rows["Kilifi"]["cob_marked_inconsistent"] is True


class TestTheGateFoundByTheAdversarialPass:
    @staticmethod
    def _row(provenance, amount=1e9):
        from types import SimpleNamespace

        return SimpleNamespace(
            debt_category=SimpleNamespace(value="pending_bills"),
            outstanding=amount, principal=amount, provenance=provenance,
        )

    COB = {"publication": "cob_cbirr_year_end", "category": "county", "as_at": "2026-06-30"}

    @pytest.mark.parametrize("as_at", [None, "", "2026-6-30", "2026-06-30T00:00:00", "2026-99-99", 20260630])
    def test_a_county_figure_needs_the_day_it_is_stated_at(self, as_at):
        from services.publication_gate import county_pending_bills

        assert county_pending_bills([self._row({**self.COB, "as_at": as_at})]) is None

    def test_a_list_shaped_county_row_is_not_published(self):
        """The retirement sweep reads dicts only: a list-shaped row would never
        be retired, and would be summed beside its successor."""
        from services.publication_gate import county_pending_bills

        assert county_pending_bills([self._row([dict(self.COB)])]) is None
        assert county_pending_bills([self._row(dict(self.COB))]) == 1e9

    def test_a_national_line_on_a_county_entity_is_not_the_countys_figure(self):
        from services.publication_gate import county_pending_bills

        national = {"publication": "treasury_brop", "category": "mda", "as_at": "2026-06-30"}
        assert county_pending_bills([self._row(national)]) is None


def test_the_national_date_is_the_paragraphs_own_or_none():
    """The page's other "as at 31st March" date, or a date inferred from the
    fiscal year, was stamped as the national figure's day, and would have let
    a national and a county figure of different days be added up."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from seeding.domains.pending_bills import brop_parser
    from seeding.domains.pending_bills.fetcher import _brop_result_to_payload

    para = (
        "20. The total outstanding National Government pending bills amounted to "
        "KSh 600.0 billion. These comprise of KSh 450.0 billion (75 percent) and "
        "KSh 150.0 billion (25 percent) for the State Corporations and MDAs, "
        "respectively.\n62. As at 31st March 2026, County Governments reported ..."
    )
    page = MagicMock()
    page.extract_text.return_value = para
    pdf = MagicMock()
    pdf.pages = [page]
    national = brop_parser._detect_national_paragraph(pdf, "FY 2025/26")
    assert national.as_at_stated is False
    payload = _brop_result_to_payload(
        SimpleNamespace(fiscal_year_label="FY 2025/26", national=national, counties=[]),
        "https://t/brop.pdf",
    )
    assert [r["as_at"] for r in payload["pending_bills"]] == [None, None]

    page.extract_text.return_value = para.replace(
        "pending bills amounted", "pending bills as of 30th June 2026 amounted"
    )
    stated = brop_parser._detect_national_paragraph(pdf, "FY 2025/26")
    assert (stated.as_at_stated, stated.as_at_date) == (True, date(2026, 6, 30))
