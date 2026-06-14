"""Tests for the NG-BIRR sectoral PDF parser.

The internal parsing helpers are pinned here against the actual
shapes observed in the COB FY 2025/26 H1 NG-BIRR. The class-level
``NgBirrSectoralParser.parse()`` smoke-tests the whole pipeline
through a stub ``pdfplumber`` page so we don't ship a 13 MB fixture
PDF in the repo.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from seeding.domains.national_budget import pdf_parser as ng_pdf


# ── _parse_kes_billion ──────────────────────────────────────────────


class TestParseKesBillion:
    def test_standard_thousands_and_decimal(self):
        """Real-shape values like '1,234.56' parse as 1234.56 billion."""
        assert ng_pdf._parse_kes_billion("1,234.56") == Decimal(
            "1234560000000"
        )

    def test_misread_decimal_recovers(self):
        """pdfplumber occasionally returns '95,23' where the decimal
        point was misread as a comma. Without recovery this would be
        a 100x overstatement (9523B vs the correct 95.23B); a real
        FY 2025/26 H1 row hit this."""
        assert ng_pdf._parse_kes_billion("95,23") == Decimal("95230000000")

    def test_thousands_separator_3_digits_after_comma(self):
        """A trailing 3-digit fragment is genuine thousands grouping
        and must NOT be promoted to a decimal point."""
        assert ng_pdf._parse_kes_billion("1,234") == Decimal(
            "1234000000000"
        )

    def test_misread_decimal_with_thousands_prefix(self):
        """Mixed: thousands grouping + misread decimal in same cell."""
        assert ng_pdf._parse_kes_billion("1,234,56") == Decimal(
            "1234560000000"
        )

    @pytest.mark.parametrize("cell", ["", " ", "-", "n/a", "NA", None])
    def test_returns_none_for_empty_or_sentinels(self, cell):
        """Empty / sentinel cells become None so the caller skips the
        row instead of writing a garbage value."""
        assert ng_pdf._parse_kes_billion(cell) is None


# ── _row_matches_sector ─────────────────────────────────────────────


class TestRowMatchesSector:
    def test_matches_short_code(self):
        """Single-token codes (ARUD, EIICT, …) are the common case
        in COB's sector tables."""
        assert (
            ng_pdf._row_matches_sector(["ARUD", "1", "2"])
            == "Agriculture, Rural and Urban Development"
        )

    def test_matches_multi_word_code(self):
        """'National Security' has a space; the function must still
        recognise it as a sector, not stop at the first token."""
        assert (
            ng_pdf._row_matches_sector(["National Security", "1", "2"])
            == "National Security"
        )

    def test_case_insensitive(self):
        assert (
            ng_pdf._row_matches_sector(["health", "1", "2"]) == "Health"
        )

    def test_returns_none_for_total_row(self):
        """The 'Total' row at the bottom of every sector table must
        be filtered out — it isn't a sector and would double-count."""
        assert ng_pdf._row_matches_sector(["Total", "407.10", "145.04"]) is None

    def test_returns_none_for_subheader_row(self):
        """Pdfplumber sometimes returns the header row as a data row
        when a table has a multi-line header — must be ignored."""
        assert ng_pdf._row_matches_sector(["Sector", "Net Estimates", ""]) is None

    def test_returns_none_for_empty_row(self):
        assert ng_pdf._row_matches_sector([]) is None
        assert ng_pdf._row_matches_sector([None, "1"]) is None


# ── _extract_sector_rows ────────────────────────────────────────────


_REAL_DEV_TABLE = [
    ["Sector", "First Six Months of FY 25/26", "", "", "", "", ""],
    ["", "Net Estimates", "Exchequer Issues", "Exch %",
     "Net Estimates", "Exchequer Issues", "Exch %"],
    ["ARUD", "41.46", "21.92", "53", "38.2", "19.34", "51"],
    ["EIICT", "130.80", "38.97", "30", "109.4", "37.57", "34"],
    ["Health", "18.78", "4.78", "25", "20.0", "5.0", "25"],
    # PAIR row carries the misread-decimal scenario in the recurrent
    # equivalent table; here it's a normal cell so we just use a
    # different sector to round out coverage.
    ["National Security", "1.00", "0.10", "10", "0.5", "0.05", "10"],
    ["Total", "407.10", "145.04", "36", "351.29", "129.82", "37"],
]


class TestExtractSectorRows:
    def test_extracts_only_sector_rows(self):
        rows = ng_pdf._extract_sector_rows(_REAL_DEV_TABLE)
        sectors = [r[0] for r in rows]
        # 4 sector rows expected; header/subheader/Total skipped.
        assert sectors == [
            "Agriculture, Rural and Urban Development",
            "Energy, Infrastructure and ICT",
            "Health",
            "National Security",
        ]

    def test_pulls_current_period_columns_only(self):
        """Cols 1-2 are CURRENT period; cols 4-5 are the comparative
        prior year and must NOT leak into the output."""
        rows = ng_pdf._extract_sector_rows(_REAL_DEV_TABLE)
        arud = next(r for r in rows if r[0].startswith("Agriculture"))
        assert arud[1] == Decimal("41460000000")   # current net
        assert arud[2] == Decimal("21920000000")   # current exch

    def test_skips_row_with_unparseable_cell(self):
        bad = list(_REAL_DEV_TABLE)
        bad.insert(2, ["GECA", "garbage", "5.50", "1", "2", "3", "4"])
        rows = ng_pdf._extract_sector_rows(bad)
        assert "General Economic and Commercial Affairs" not in [r[0] for r in rows]


# ── _detect_period ──────────────────────────────────────────────────


def _stub_pdf_with_cover(text: str) -> MagicMock:
    """Build a MagicMock pdfplumber.PDF whose first page returns the
    given text. _detect_period only reads the first 3 pages."""
    page = MagicMock()
    page.extract_text.return_value = text
    pdf = MagicMock()
    pdf.pages = [page, page, page]
    return pdf


class TestDetectPeriod:
    def test_first_six_months_h1(self):
        info = ng_pdf._detect_period(
            _stub_pdf_with_cover("NATIONAL GOVERNMENT BIRR\nFIRST SIX MONTHS\nFY 2025/2026")
        )
        assert info.label == "FY 2025/26 H1"
        assert info.start_date == date(2025, 7, 1)
        assert info.end_date == date(2025, 12, 31)

    def test_first_quarter_q1(self):
        info = ng_pdf._detect_period(
            _stub_pdf_with_cover("NG-BIRR\nFIRST QUARTER\nFY 2024/2025")
        )
        assert info.label == "FY 2024/25 Q1"
        assert info.end_date == date(2024, 9, 30)

    def test_first_nine_months_uses_actual_march_31(self):
        """End-month March has 31 days, not 30. Pre-fix code
        hard-coded month-30 for the (3, 6, 9) bucket and produced
        2025-03-30, mismatching the bulletin's stated period
        (Copilot review on PR #81)."""
        info = ng_pdf._detect_period(
            _stub_pdf_with_cover(
                "NATIONAL GOVERNMENT BIRR\nFIRST NINE MONTHS\nFY 2024/2025"
            )
        )
        assert info.label == "FY 2024/25 9M"
        assert info.end_date == date(2025, 3, 31)

    def test_annual_when_no_subperiod_descriptor(self):
        """If only a 'FY YYYY/YYYY' label is present, treat as annual:
        end on Jun 30 of the FY's second calendar year."""
        info = ng_pdf._detect_period(
            _stub_pdf_with_cover("ANNUAL NATIONAL GOVERNMENT BIRR FY 2023/2024")
        )
        assert info.label == "FY 2023/24"
        assert info.end_date == date(2024, 6, 30)

    def test_returns_none_when_no_fy_label(self):
        """A page that doesn't carry an 'FY YYYY/YYYY' label is
        unparseable — better to fail loud than guess."""
        assert ng_pdf._detect_period(
            _stub_pdf_with_cover("just a random page")
        ) is None


# ── NgBirrSectoralParser.parse (integration via stubbed pdfplumber) ─


class TestNgBirrSectoralParser:
    def test_emits_one_record_per_sector_per_subcategory(self, tmp_path):
        """Stubs pdfplumber so we don't ship a 13 MB fixture PDF.
        Verifies the dev + recurrent paths both feed the output and
        that the period info is threaded through."""
        rec_table = [
            ["Sector", "Net Est", "Exch", "%", "Net Est", "Exch", "%"],
            ["Health", "74.78", "40.90", "55", "56.43", "28.12", "50"],
            ["Education", "601.03", "348.57", "58", "554.03", "263.1", "48"],
        ]
        dev_table = _REAL_DEV_TABLE

        cover_page = MagicMock()
        cover_page.extract_text.return_value = (
            "NATIONAL GOVERNMENT BIRR\nFIRST SIX MONTHS\nFY 2025/2026"
        )

        dev_page = MagicMock()
        dev_page.extract_text.return_value = (
            "Table 2.5: Sectoral Development Estimates and Exchequer Issues"
        )
        dev_page.extract_tables.return_value = [dev_table]

        rec_page = MagicMock()
        rec_page.extract_text.return_value = (
            "Table 2.6: Sectoral Recurrent Estimates and Exchequer Issues"
        )
        rec_page.extract_tables.return_value = [rec_table]

        fake_pdf = MagicMock()
        fake_pdf.pages = [cover_page, cover_page, cover_page, dev_page, rec_page]
        fake_pdf.__enter__ = lambda s: fake_pdf
        fake_pdf.__exit__ = lambda *a: None

        with patch.object(ng_pdf.pdfplumber, "open", return_value=fake_pdf):
            parser = ng_pdf.NgBirrSectoralParser(tmp_path / "fake.pdf")
            period, records = parser.parse()

        assert period.label == "FY 2025/26 H1"
        # 4 dev sector rows + 2 recurrent sector rows.
        assert len(records) == 6
        subs = {(r.sector, r.subcategory) for r in records}
        assert ("Health", "Recurrent") in subs
        assert ("Education", "Recurrent") in subs
        assert ("Agriculture, Rural and Urban Development", "Development") in subs

    def test_raises_when_no_tables_found(self, tmp_path):
        """A PDF that has the period descriptor but neither dev nor
        recurrent sector table must raise so the fetcher logs the
        warning and falls back to fixture rather than silently
        emitting zero records."""
        cover_page = MagicMock()
        cover_page.extract_text.return_value = (
            "NG-BIRR FIRST SIX MONTHS FY 2024/2025"
        )
        # No table-2.5/2.6 titled pages.
        other_page = MagicMock()
        other_page.extract_text.return_value = "Some unrelated page"
        other_page.extract_tables.return_value = []

        fake_pdf = MagicMock()
        fake_pdf.pages = [cover_page, cover_page, cover_page, other_page]
        fake_pdf.__enter__ = lambda s: fake_pdf
        fake_pdf.__exit__ = lambda *a: None

        with patch.object(ng_pdf.pdfplumber, "open", return_value=fake_pdf):
            parser = ng_pdf.NgBirrSectoralParser(tmp_path / "fake.pdf")
            with pytest.raises(ValueError, match="No sectoral aggregate"):
                parser.parse()
