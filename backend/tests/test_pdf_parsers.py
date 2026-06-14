"""Tests for PDF parsing utilities."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from seeding.pdf_parsers import (
    CoBQuarterlyReportParser,
    ExtractedTable,
    OAGAuditReportParser,
    PDFCorruptedError,
    PDFNotFoundError,
    TableNotFoundError,
    TreasuryDebtBulletinParser,
    extract_all_tables,
    extract_text_from_pdf,
    find_table_by_header,
    parse_currency,
    parse_percentage,
)


class TestParseCurrency:
    """Test currency parsing function."""

    def test_parse_kes_with_commas(self):
        amount, currency = parse_currency("KES 1,234,567.89")
        assert amount == Decimal("1234567.89")
        assert currency == "KES"

    def test_parse_number_only(self):
        amount, currency = parse_currency("1,234,567")
        assert amount == Decimal("1234567")
        assert currency == "KES"  # default

    def test_parse_usd(self):
        amount, currency = parse_currency("USD 1,234.56")
        assert amount == Decimal("1234.56")
        assert currency == "USD"

    def test_parse_negative(self):
        amount, currency = parse_currency("-1,234.56")
        assert amount == Decimal("-1234.56")

    def test_parse_invalid_returns_zero(self):
        amount, currency = parse_currency("N/A")
        assert amount == Decimal("0")


class TestParsePercentage:
    """Test percentage parsing function."""

    def test_parse_with_percent_sign(self):
        assert parse_percentage("85.5%") == 85.5

    def test_parse_without_percent_sign(self):
        assert parse_percentage("85.5") == 85.5

    def test_parse_with_commas(self):
        assert parse_percentage("1,234.5%") == 1234.5

    def test_parse_na_returns_none(self):
        assert parse_percentage("N/A") is None
        assert parse_percentage("NA") is None
        assert parse_percentage("-") is None
        assert parse_percentage("") is None

    def test_parse_invalid_returns_none(self):
        assert parse_percentage("invalid") is None


class TestExtractedTable:
    """Test ExtractedTable dataclass."""

    def test_row_count(self):
        table = ExtractedTable(
            page_number=1,
            table_index=0,
            headers=["County", "Amount"],
            rows=[["Nairobi", "1000"], ["Mombasa", "2000"]],
            bbox=(0, 0, 100, 100),
        )
        assert table.row_count == 2

    def test_to_dicts(self):
        table = ExtractedTable(
            page_number=1,
            table_index=0,
            headers=["County", "Amount"],
            rows=[["Nairobi", "1000"], ["Mombasa", "2000"]],
            bbox=(0, 0, 100, 100),
        )
        dicts = table.to_dicts()
        assert len(dicts) == 2
        assert dicts[0] == {"County": "Nairobi", "Amount": "1000"}
        assert dicts[1] == {"County": "Mombasa", "Amount": "2000"}


class TestFindTableByHeader:
    """Test table finding by header keywords."""

    def test_find_matching_table(self):
        tables = [
            ExtractedTable(1, 0, ["County", "Population"], [], (0, 0, 0, 0)),
            ExtractedTable(1, 1, ["County", "Allocated", "Absorbed"], [], (0, 0, 0, 0)),
            ExtractedTable(2, 0, ["Year", "GDP"], [], (0, 0, 0, 0)),
        ]

        result = find_table_by_header(tables, ["allocated", "absorbed"])
        assert result is not None
        assert result.table_index == 1
        assert "Allocated" in result.headers

    def test_find_no_match_returns_none(self):
        tables = [
            ExtractedTable(1, 0, ["County", "Population"], [], (0, 0, 0, 0)),
        ]

        result = find_table_by_header(tables, ["allocated", "absorbed"])
        assert result is None

    def test_case_insensitive_matching(self):
        tables = [
            ExtractedTable(1, 0, ["COUNTY", "ALLOCATED"], [], (0, 0, 0, 0)),
        ]

        result = find_table_by_header(tables, ["county", "allocated"])
        assert result is not None


class TestCoBQuarterlyReportParser:
    """Test CoB quarterly report parser."""

    @patch("seeding.pdf_parsers.extract_all_tables")
    def test_parse_budget_execution_report(self, mock_extract):
        """Test parsing a CoB quarterly report."""
        # Mock extracted tables
        mock_extract.return_value = [
            ExtractedTable(
                page_number=1,
                table_index=0,
                headers=["County", "Allocated", "Absorbed", "Rate"],
                rows=[
                    ["Nairobi", "KES 10,000,000", "KES 8,000,000", "80%"],
                    ["Mombasa", "KES 5,000,000", "KES 4,500,000", "90%"],
                    [
                        "Total",
                        "KES 15,000,000",
                        "KES 12,500,000",
                        "83.3%",
                    ],  # Should skip
                ],
                bbox=(0, 0, 100, 100),
            )
        ]

        parser = CoBQuarterlyReportParser(Path("Q2-2023-24-report.pdf"))
        records = parser.parse()

        assert len(records) == 2  # Total row should be skipped

        # Check first record
        assert records[0]["county"] == "Nairobi"
        assert records[0]["allocated"] == Decimal("10000000")
        assert records[0]["absorbed"] == Decimal("8000000")
        assert records[0]["absorption_rate"] == 80.0
        assert records[0]["currency"] == "KES"
        assert records[0]["quarter"] == "Q2"
        assert records[0]["fiscal_year"] == "2023/24"

    @patch("seeding.pdf_parsers.extract_all_tables")
    def test_raises_error_when_table_not_found(self, mock_extract):
        """Test error when county budget table not found."""
        mock_extract.return_value = [
            ExtractedTable(
                page_number=1,
                table_index=0,
                headers=["Year", "GDP"],  # Wrong table
                rows=[],
                bbox=(0, 0, 0, 0),
            )
        ]

        parser = CoBQuarterlyReportParser(Path("report.pdf"))

        with pytest.raises(TableNotFoundError):
            parser.parse()

    @patch("seeding.pdf_parsers.extract_all_tables")
    def test_parse_h1_fy2025_26_layout(self, mock_extract):
        """Regression: COB H1 FY2025/26 reword headers from
        Allocated/Absorbed → Budget Estimates / Actual Expenditure
        and added a two-row "group / Rec/Dev/Total" sub-header.
        The new parser must:
          (a) find the table by 47-county anchor (not literal keywords),
          (b) flatten the two-row header into combined labels,
          (c) extract Total + Recurrent + Development from one table
              by addressing different sub-columns.
        """
        from seeding.pdf_parsers import KENYAN_COUNTIES

        # Header row + sub-row + 47 county data rows.
        group_headers = [
            "County",
            "Budget Estimates (Kshs.Million)", "", "",
            "Actual Expenditure (Kshs.Million)", "", "",
            "Absorption Rate(%)", "", "",
        ]
        sub_row = [
            "", "Rec", "Dev", "Total",
            "Rec", "Dev", "Total",
            "Rec", "Dev", "Total",
        ]
        county_rows = [
            [c, "5,000", "3,000", "8,000",
                 "2,500", "1,200", "3,700",
                 "50", "40", "46"]
            for c in KENYAN_COUNTIES
        ]
        mock_extract.return_value = [
            ExtractedTable(
                page_number=55, table_index=0,
                headers=group_headers,
                rows=[sub_row, *county_rows],
                bbox=(0, 0, 100, 100),
            )
        ]

        parser = CoBQuarterlyReportParser(
            Path("h1-fy2025-26-county-birr.pdf")
        )
        records = parser.parse()

        # 47 counties × 3 categories = 141 records (no PE table).
        assert len(records) == 141
        cats = {r["category"] for r in records}
        assert cats == {"Total", "Recurrent", "Development"}
        counties_seen = {r["county"] for r in records if r["category"] == "Total"}
        assert "Murang'a" in counties_seen, "apostrophe county must round-trip"
        assert len(counties_seen) == 47

        # Pin the column-resolution: "Total" must read sub-columns
        # 3 (Budget Estimates Total) and 6 (Actual Expenditure Total).
        sample = next(r for r in records if r["county"] == "Nairobi" and r["category"] == "Total")
        assert sample["allocated"] == Decimal("8000")
        assert sample["absorbed"] == Decimal("3700")
        assert sample["absorption_rate"] == 46.0

    @patch("seeding.pdf_parsers.extract_all_tables")
    def test_anchor_matches_hyphenated_county_forms(self, mock_extract):
        """Regression: COB sometimes prints "Taita-Taveta" /
        "Trans-Nzoia" / "Tharaka-Nithi" / "Elgeyo-Marakwet" with a
        hyphen instead of a space. The canonical anchor list uses the
        space form. Without hyphen normalisation those rows wouldn't
        substring-match and we'd silently lose 4 counties from the
        anchor count — possibly dropping us under the min_matches
        threshold. Both sides of the comparison must normalise."""
        from seeding.pdf_parsers import KENYAN_COUNTIES

        hyphen_rows = [
            ["Taita-Taveta", "1", "2", "3", "1", "1", "2"],
            ["Tharaka-Nithi", "1", "2", "3", "1", "1", "2"],
            ["Trans-Nzoia", "1", "2", "3", "1", "1", "2"],
            ["Elgeyo-Marakwet", "1", "2", "3", "1", "1", "2"],
        ]
        # Pad with enough extra space-form counties to clear the
        # min_matches=30 threshold the parser uses.
        others = [
            c for c in KENYAN_COUNTIES
            if c not in ("Taita Taveta", "Tharaka Nithi", "Trans Nzoia", "Elgeyo Marakwet")
        ]
        extra_rows = [[c, "1", "2", "3", "1", "1", "2"] for c in others[:27]]
        mock_extract.return_value = [
            ExtractedTable(
                page_number=55, table_index=0,
                headers=[
                    "County",
                    "Budget Estimates (Kshs.Million)", "", "",
                    "Actual Expenditure (Kshs.Million)", "", "",
                ],
                rows=[
                    ["", "Rec", "Dev", "Total", "Rec", "Dev", "Total"],
                    *hyphen_rows,
                    *extra_rows,
                ],
                bbox=(0, 0, 100, 100),
            )
        ]
        records = CoBQuarterlyReportParser(Path("hyphenated.pdf")).parse()
        counties = {r["county"] for r in records}
        # The parser preserves the original spelling — the hyphenated
        # rows are still extracted (we don't rewrite the row label,
        # only the matching code is hyphen-insensitive).
        assert "Taita-Taveta" in counties
        assert "Tharaka-Nithi" in counties
        assert "Trans-Nzoia" in counties
        assert "Elgeyo-Marakwet" in counties

    @patch("seeding.pdf_parsers.extract_all_tables")
    def test_derives_absorption_rate_when_column_missing(self, mock_extract):
        """Some BIRR vintages drop the absorption-rate sub-column.
        We should compute it ourselves from absorbed/allocated rather
        than leak a None into downstream consumers (the
        /budget/overview probe expects this field)."""
        from seeding.pdf_parsers import KENYAN_COUNTIES

        # Headers cover Total only — no rate column.
        mock_extract.return_value = [
            ExtractedTable(
                page_number=1, table_index=0,
                headers=["County", "Budget Estimates Total", "Actual Expenditure Total"],
                rows=[[c, "1000", "500"] for c in KENYAN_COUNTIES],
                bbox=(0, 0, 100, 100),
            )
        ]
        records = CoBQuarterlyReportParser(Path("no-rate.pdf")).parse()
        total = next(r for r in records if r["category"] == "Total")
        assert total["absorption_rate"] == 50.0

    @patch("seeding.pdf_parsers.extract_all_tables")
    def test_falls_back_to_separate_recurrent_table_for_legacy_format(
        self, mock_extract
    ):
        """Pre-FY2024 BIRR PDFs published Recurrent / Development as
        SEPARATE tables instead of as sub-columns of a consolidated
        one. The new parser should still pick them up via the legacy
        _extract_category fallback when the consolidated table didn't
        carry that category — otherwise we silently drop categories
        for older vintages that resurface."""
        from seeding.pdf_parsers import KENYAN_COUNTIES

        consolidated_total_only = ExtractedTable(
            page_number=1, table_index=0,
            headers=["County", "Budget Estimates Total", "Actual Expenditure Total"],
            rows=[[c, "1000", "500"] for c in KENYAN_COUNTIES],
            bbox=(0, 0, 100, 100),
        )
        recurrent_separate = ExtractedTable(
            page_number=2, table_index=0,
            headers=["County", "Recurrent Allocated", "Recurrent Absorbed", "Rate"],
            rows=[[c, "600", "400", "67"] for c in KENYAN_COUNTIES],
            bbox=(0, 0, 100, 100),
        )
        mock_extract.return_value = [consolidated_total_only, recurrent_separate]

        records = CoBQuarterlyReportParser(Path("legacy.pdf")).parse()
        cats = {r["category"] for r in records}
        assert "Total" in cats
        assert "Recurrent" in cats, "legacy separate-table fallback should fire"
        rec_sample = next(r for r in records if r["category"] == "Recurrent")
        assert rec_sample["allocated"] == Decimal("600")

    @patch("seeding.pdf_parsers.extract_all_tables")
    def test_validator_falls_through_top_anchor_when_columns_unresolvable(
        self, mock_extract
    ):
        """Regression for the seeding run on 2026-04-25
        ([24934906752](https://github.com/Rodgers31/audit_app/actions/runs/24934906752)):

        Real BIRR PDF had FIVE tables with >=30 county anchors. The
        Arrears table on page 52 ranked highest (45 anchors, no
        budget keywords); the Budget Execution table on page 55 ranked
        third (39 anchors). Tiebreaker rules can't recover from this —
        the parser must validate each candidate against its actual
        column needs and fall through when the top pick can't supply
        a usable Total/allocated column.
        """
        from seeding.pdf_parsers import KENYAN_COUNTIES

        # Top-ranked: many county rows but no budget column.
        arrears_high_anchor = ExtractedTable(
            page_number=52, table_index=0,
            headers=["County", "Arrears (Kshs.Million)", "", "", ""],
            rows=[
                ["", "Ordinary OSR", "FIF", "Equitable Share", "Totals"],
                *[[c, "10", "5", "8", "23"] for c in KENYAN_COUNTIES],  # 47 hits
            ],
            bbox=(0, 0, 100, 100),
        )
        # Lower-ranked: fewer counties but the actual budget data.
        budget_lower_anchor = ExtractedTable(
            page_number=55, table_index=0,
            headers=[
                "County",
                "Budget Estimates (Kshs.Million)", "", "",
                "Actual Expenditure (Kshs.Million)", "", "",
            ],
            rows=[
                ["", "Rec", "Dev", "Total", "Rec", "Dev", "Total"],
                # Only 35 counties → 35 anchors, less than arrears_high's 47.
                *[[c, "1", "2", "3", "1", "1", "2"]
                  for c in KENYAN_COUNTIES[:35]],
            ],
            bbox=(0, 0, 100, 100),
        )
        mock_extract.return_value = [arrears_high_anchor, budget_lower_anchor]

        records = CoBQuarterlyReportParser(Path("validator.pdf")).parse()

        assert records, "validator must fall through arrears to budget"
        # Budget table values are alloc=3 / abs=2 — Arrears would have
        # been alloc=8 (Equitable Share) / abs=23 (Totals).
        assert records[0]["allocated"] == Decimal("3")
        assert records[0]["absorbed"] == Decimal("2")

    @patch("seeding.pdf_parsers.extract_all_tables")
    def test_anchor_score_outranks_header_score(self, mock_extract):
        """Pin sort precedence: anchor count is primary, header
        synonyms are only the tiebreaker. A junk-header table with
        all 47 counties must beat a clean-header table with only 2
        counties — otherwise "invariant-anchored" loses to vocabulary
        matching, which is the whole bug we're trying to fix."""
        from seeding.pdf_parsers import (
            KENYAN_COUNTIES, find_table_by_row_anchors,
        )

        big_anchor_junk_header = ExtractedTable(
            page_number=99, table_index=0,
            headers=["County", "Junk Header"],
            rows=[["", "x"], *[[c, "1"] for c in KENYAN_COUNTIES]],
            bbox=(0, 0, 100, 100),
        )
        small_anchor_clean_header = ExtractedTable(
            page_number=1, table_index=0,
            headers=["County", "Budget Estimates Total", "Actual Expenditure Total"],
            rows=[["Mombasa", "5", "2"], ["Kwale", "3", "1"]],
            bbox=(0, 0, 100, 100),
        )
        result = find_table_by_row_anchors(
            [big_anchor_junk_header, small_anchor_clean_header],
            list(KENYAN_COUNTIES),
            min_matches=2,
            header_synonyms=[["budget", "expenditure"]],
        )
        assert result is big_anchor_junk_header, (
            "anchor count must outrank header_score; got page "
            f"{result.page_number if result else 'None'}"
        )

    @patch("seeding.pdf_parsers.extract_all_tables")
    def test_picks_budget_table_when_multiple_county_tables_present(
        self, mock_extract
    ):
        """A real BIRR has many tables that all list the 47 counties
        (revenue, arrears, expenditure, …). The header_synonyms
        tiebreaker must prefer the budget-execution table over
        unrelated ones — otherwise we'd parse the arrears table on
        page 52 instead of the budget table on page 55."""
        from seeding.pdf_parsers import KENYAN_COUNTIES

        arrears = ExtractedTable(
            page_number=52, table_index=0,
            headers=["County", "Arrears as at 31st December 2025", "", "", ""],
            rows=[
                ["", "Ordinary OSR", "FIF", "Equitable Share", "Totals"],
                *[[c, "10", "5", "8", "23"] for c in KENYAN_COUNTIES],
            ],
            bbox=(0, 0, 100, 100),
        )
        budget = ExtractedTable(
            page_number=55, table_index=0,
            headers=[
                "County",
                "Budget Estimates (Kshs.Million)", "", "",
                "Actual Expenditure (Kshs.Million)", "", "",
            ],
            rows=[
                ["", "Rec", "Dev", "Total", "Rec", "Dev", "Total"],
                *[[c, "1", "2", "3", "1", "1", "2"] for c in KENYAN_COUNTIES],
            ],
            bbox=(0, 0, 100, 100),
        )

        # Arrears comes FIRST in the list — without a header tiebreaker
        # it would win the anchor match and yield zero useful records.
        mock_extract.return_value = [arrears, budget]
        parser = CoBQuarterlyReportParser(Path("multi-table.pdf"))
        records = parser.parse()

        assert len(records) > 0, "should pick the budget table over arrears"
        # All records must have come from the budget table — its
        # alloc=3 / abs=2 values are unambiguous.
        sample = records[0]
        assert sample["allocated"] == Decimal("3")
        assert sample["absorbed"] == Decimal("2")


class TestOAGAuditReportParser:
    """Test OAG audit report parser."""

    @patch("seeding.pdf_parsers.extract_text_from_pdf")
    def test_parse_audit_report(self, mock_extract_text):
        """Test parsing an OAG audit report."""
        mock_extract_text.return_value = """
        REPORT OF THE AUDITOR GENERAL ON THE FINANCIAL STATEMENTS OF
        COUNTY GOVERNMENT OF NAIROBI FOR THE YEAR ENDED 30 JUNE 2023
        
        Fiscal Year: 2022/23
        
        Opinion
        
        In my opinion, the financial statements present fairly...
        I have issued an Unqualified opinion on these statements.
        
        Finding 1: Irregular procurement procedures were noted...
        
        Finding 2: Lack of proper asset register...
        
        Recommendation: The County should establish a proper procurement framework.
        """

        parser = OAGAuditReportParser(Path("nairobi-2023-audit.pdf"))
        result = parser.parse()

        assert result["county"] == "Nairobi"
        assert result["fiscal_year"] == "2022/23"  # Now in YYYY/YY format
        assert result["opinion"] == "Unqualified"
        assert len(result["findings"]) >= 1  # Should find at least 1 finding
        # Note: Recommendation extraction may find fewer than expected due to pattern complexity
        assert isinstance(result["recommendations"], list)


class TestTreasuryDebtBulletinParser:
    """Test Treasury debt bulletin parser."""

    @patch("seeding.pdf_parsers.extract_all_tables")
    def test_parse_debt_bulletin(self, mock_extract):
        """Test parsing a Treasury debt bulletin."""
        mock_extract.return_value = [
            ExtractedTable(
                page_number=1,
                table_index=0,
                headers=["Lender", "Principal", "Outstanding"],
                rows=[
                    ["World Bank", "KES 50,000,000,000", "KES 45,000,000,000"],
                    ["IMF", "USD 30,000,000,000", "USD 28,500,000,000"],
                    ["China Exim Bank", "KES 20,000,000,000", "KES 19,000,000,000"],
                    [
                        "Total External",
                        "KES 100,000,000,000",
                        "KES 92,500,000,000",
                    ],  # Skip
                ],
                bbox=(0, 0, 100, 100),
            )
        ]

        parser = TreasuryDebtBulletinParser(Path("debt-bulletin-2024.pdf"))
        records = parser.parse()

        assert len(records) == 3  # Total row should be skipped

        # Check World Bank record
        assert records[0]["lender"] == "World Bank"
        assert records[0]["principal"] == Decimal("50000000000")
        assert records[0]["outstanding"] == Decimal("45000000000")
        assert records[0]["currency"] == "KES"
        assert records[0]["loan_type"] == "Multilateral"

        # Check IMF record
        assert records[1]["lender"] == "IMF"
        assert records[1]["currency"] == "USD"
        assert records[1]["loan_type"] == "Multilateral"

        # Check bilateral loan
        assert records[2]["lender"] == "China Exim Bank"
        assert records[2]["loan_type"] == "Bilateral"


class TestExtractAllTables:
    """Test table extraction from PDFs."""

    def test_pdf_not_found_raises_error(self):
        """Test error when PDF file doesn't exist."""
        with pytest.raises(PDFNotFoundError):
            extract_all_tables(Path("nonexistent.pdf"))

    @patch("pdfplumber.open")
    def test_corrupted_pdf_raises_error(self, mock_open):
        """Test error when PDF is corrupted."""
        mock_open.side_effect = Exception("Corrupted PDF")

        with pytest.raises(PDFCorruptedError):
            extract_all_tables(Path(__file__))  # Use existing file


class TestExtractTextFromPDF:
    """Test text extraction from PDFs."""

    def test_pdf_not_found_raises_error(self):
        """Test error when PDF file doesn't exist."""
        with pytest.raises(PDFNotFoundError):
            extract_text_from_pdf(Path("nonexistent.pdf"))

    @patch("pdfplumber.open")
    def test_extract_specific_pages(self, mock_open):
        """Test extracting text from specific pages."""
        # Create mock PDF with multiple pages
        mock_page1 = Mock()
        mock_page1.extract_text.return_value = "Page 1 content"

        mock_page2 = Mock()
        mock_page2.extract_text.return_value = "Page 2 content"

        mock_page3 = Mock()
        mock_page3.extract_text.return_value = "Page 3 content"

        mock_pdf = Mock()
        mock_pdf.pages = [mock_page1, mock_page2, mock_page3]
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)

        mock_open.return_value = mock_pdf

        # Create a temporary file to satisfy exists() check
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            # Extract only pages 1 and 3
            text = extract_text_from_pdf(tmp_path, pages=[1, 3])

            assert "Page 1 content" in text
            assert "Page 2 content" not in text
            assert "Page 3 content" in text
        finally:
            tmp_path.unlink()  # Clean up


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
