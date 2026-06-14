"""Tests for the Treasury BROP pending-bills parser.

These pin the parsing behaviour the ``pending_bills`` domain
depends on after switching off the broken NG-BIRR + allocated-minus-
absorbed proxy. The internal helpers are tested against the actual
shapes observed in the September-2025 BROP; the public
``parse_brop_pdf`` entry point is smoke-tested via a stubbed
pdfplumber so we don't ship a 2.5 MB fixture PDF in the repo.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from seeding.domains.pending_bills import brop_parser as bp


# ── _parse_kes_billion / _parse_kes_million ─────────────────────────


class TestNumberParsing:
    def test_billion_scale(self):
        assert bp._parse_kes_billion("525.9") == Decimal("525900000000")

    def test_billion_with_comma(self):
        assert bp._parse_kes_billion("1,234.5") == Decimal(
            "1234500000000"
        )

    def test_million_scale(self):
        assert bp._parse_kes_million("78,949.1") == Decimal(
            "78949100000"
        )

    @pytest.mark.parametrize(
        "func", [bp._parse_kes_billion, bp._parse_kes_million]
    )
    @pytest.mark.parametrize("token", ["", " ", "-", None])
    def test_returns_none_for_empty_or_dash(self, func, token):
        """BROP renders missing cells as '-'; the parser must keep
        them as None so the writer leaves the column unset rather
        than writing 0 (which would be a real value)."""
        assert func(token) is None


# ── _normalise_county ───────────────────────────────────────────────


class TestNormaliseCounty:
    def test_exact_match(self):
        assert bp._normalise_county("Nairobi") == "Nairobi"

    def test_apostrophe_stripped(self):
        """'Murang'a' is the canonical form in KENYAN_COUNTIES; the
        BROP renders it the same way. Both sides normalise to
        'muranga' so the match works without losing the canonical
        apostrophe."""
        assert bp._normalise_county("Murang'a") == "Murang'a"

    def test_hyphen_to_space(self):
        """Some BROP cells use 'Tharaka-Nithi'; canonical is
        'Tharaka Nithi'. Hyphens normalise to spaces on both sides."""
        assert bp._normalise_county("Tharaka-Nithi") == "Tharaka Nithi"

    def test_prefix_match_for_truncated_wrap(self):
        """pdfplumber occasionally drops the second line of a
        wrapped county name, so 'Tharaka' arrives without 'Nithi'.
        We prefix-match against KENYAN_COUNTIES, but ONLY when the
        prefix is unambiguous — no second county shares 'Tharaka' as
        its first word, so this is safe."""
        assert bp._normalise_county("Tharaka") == "Tharaka Nithi"
        assert bp._normalise_county("Elgeyo") == "Elgeyo Marakwet"

    def test_returns_none_for_non_county(self):
        assert bp._normalise_county("Sub-Total") is None
        assert bp._normalise_county("Total") is None
        assert bp._normalise_county("Banana") is None


# ── _detect_national_paragraph ──────────────────────────────────────


_REAL_PARA_18 = """\
17. Some other paragraph about external financing.

Pending Bills

18. The total outstanding National Government pending bills as at
30th June 2025 amounted to KSh 525.9 billion. These comprise of
KSh 404.3 billion (76.9 percent) and KSh 121.6 billion (23.1
percent) for the State Corporations and MDAs, respectively.
"""


class TestDetectNationalParagraph:
    def _stub_pdf(self, text: str) -> MagicMock:
        page = MagicMock()
        page.extract_text.return_value = text
        pdf = MagicMock()
        pdf.pages = [page] * 5  # search range is first 30 pages
        return pdf

    def test_extracts_three_amounts_and_date(self):
        result = bp._detect_national_paragraph(
            self._stub_pdf(_REAL_PARA_18), "FY 2024/25"
        )
        assert result is not None
        assert result.total == Decimal("525900000000")
        assert result.state_corporations == Decimal("404300000000")
        assert result.mdas == Decimal("121600000000")
        assert result.as_at_date == date(2025, 6, 30)

    def test_returns_none_when_paragraph_absent(self):
        result = bp._detect_national_paragraph(
            self._stub_pdf(
                "Just some narrative without the para-18 anchor."
            ),
            "FY 2024/25",
        )
        assert result is None

    def test_falls_back_to_fy_end_date_when_as_at_missing(self):
        """If the para-18 anchor matches but the 'as at' date phrase
        is rephrased / dropped in a future BROP, the as-at date must
        be inferred from the FY label (Jun 30 of FY's second
        calendar year). The previous ``date(2000, 6, 30)`` placeholder
        would have produced a wrong natural key in the writer
        (Copilot review on PR #81)."""
        para_without_date = (
            "Pending Bills\n"
            "18. The total outstanding National Government pending bills "
            "amounted to KSh 525.9 billion. These comprise of KSh 404.3 "
            "billion (76.9 percent) and KSh 121.6 billion (23.1 percent) "
            "for the State Corporations and MDAs, respectively."
        )
        result = bp._detect_national_paragraph(
            self._stub_pdf(para_without_date), "FY 2024/25"
        )
        assert result is not None
        # FY 2024/25 → ends 30 June 2025.
        assert result.as_at_date == date(2025, 6, 30)


class TestInferFyEndDate:
    def test_short_form_fy_label(self):
        assert bp._infer_fy_end_date("FY 2024/25") == date(2025, 6, 30)

    def test_long_form_fy_label(self):
        assert bp._infer_fy_end_date("FY 2024/2025") == date(2025, 6, 30)

    def test_fallback_when_label_unparseable(self):
        """Last-resort: a recent FY-end (today's most recent Jun 30).
        The exact date depends on the test's wall-clock so we just
        assert it's not the legacy date(2000, ...) sentinel."""
        result = bp._infer_fy_end_date("FY ?")
        assert result.year >= 2024
        assert (result.month, result.day) == (6, 30)


# ── _COUNTY_ROW_RE + _parse_county_row_numbers ──────────────────────


class TestCountyRowRegex:
    def test_full_row(self):
        """Real Nairobi row from BROP 2025 Table 10. Eight numeric
        tokens because the Assembly column collapses to a single
        sub-total (no Recurrent/Development split for Nairobi
        Assembly)."""
        line = (
            "1. Nairobi 78,949.1 7,169.4 86,118.6 650.6 650.6 "
            "86,769.2 43,564.27 199.2"
        )
        m = bp._COUNTY_ROW_RE.match(line)
        assert m is not None
        assert m.group("no") == "1"
        assert m.group("county") == "Nairobi"
        tokens = m.group("rest").split()
        # Last 3 tokens are always Total / FY budget / %.
        assert tokens[-3:] == ["86,769.2", "43,564.27", "199.2"]

    def test_row_with_dash_for_missing_cell(self):
        """'Kilifi 3,820.1 5,367.4 9,187.4 68.2 - 68.2 9,255.6
        21,406.50 43.2' — the dash represents an empty assembly
        development cell."""
        line = (
            "2. Kilifi 3,820.1 5,367.4 9,187.4 68.2 - 68.2 "
            "9,255.6 21,406.50 43.2"
        )
        m = bp._COUNTY_ROW_RE.match(line)
        assert m is not None
        assert m.group("county") == "Kilifi"

    def test_two_word_county_name(self):
        line = (
            "23. Trans Nzoia 805.4 703.0 1,508.4 - 1,508.4 "
            "10,455.02 14.4"
        )
        m = bp._COUNTY_ROW_RE.match(line)
        assert m is not None
        assert m.group("county") == "Trans Nzoia"

    def test_row_with_apostrophe(self):
        """Murang'a's apostrophe must NOT terminate the county name
        match early."""
        line = (
            "16. Murang'a 1,588.1 333.4 1,921.5 72.2 72.2 "
            "1,993.7 10,743.65 18.6"
        )
        m = bp._COUNTY_ROW_RE.match(line)
        assert m is not None
        assert m.group("county") == "Murang'a"


class TestParseCountyRowNumbers:
    def test_full_six_breakdown_row_with_preserved_dash(self):
        """Kilifi-shaped row: pdfplumber renders the missing
        assembly-development cell as a literal '-' token. We MUST
        keep that as a positional ``None`` placeholder so subsequent
        cells stay column-aligned. Pre-fix bug: the dash was filtered
        out, shifting the assembly_subtotal into ``asm_dev`` and
        misattributing the value (Copilot review on PR #81)."""
        # 9 tokens: exec_R, exec_D, exec_Sub, asm_R, "-", asm_Sub,
        # total, fy_budget, pct.
        tokens = [
            "3,820.1", "5,367.4", "9,187.4",
            "68.2", "-", "68.2",
            "9,255.6", "21,406.50", "43.2",
        ]
        out = bp._parse_county_row_numbers(tokens)
        assert out is not None
        # Executive cells fully populated.
        assert out["exec_rec"] == Decimal("3820100000")
        assert out["exec_dev"] == Decimal("5367400000")
        assert out["exec_sub"] == Decimal("9187400000")
        # Assembly: recurrent + subtotal both 68.2M, dev correctly None.
        assert out["asm_rec"] == Decimal("68200000")
        assert out["asm_dev"] is None
        assert out["asm_sub"] == Decimal("68200000")
        # Reliable last-three columns.
        assert out["total"] == Decimal("9255600000")
        assert out["fy_budget"] == Decimal("21406500000")

    def test_short_row_leaves_assembly_unset(self):
        """When pdfplumber drops a dash entirely (Nairobi-shaped: 8
        tokens with no '-'), we can't tell which assembly cell was
        omitted from the text. Persist exec + last-three columns and
        leave the ambiguous cells as None rather than guess."""
        # 8 tokens — pdfplumber dropped one assembly cell. Last 3 are
        # total/budget/pct; first 3 are exec_R/D/Sub; middle 2 are
        # ambiguous between (asm_R, asm_Sub) and (asm_R, asm_D).
        tokens = [
            "78,949.1", "7,169.4", "86,118.6",
            "650.6", "650.6",
            "86,769.2", "43,564.27", "199.2",
        ]
        out = bp._parse_county_row_numbers(tokens)
        assert out is not None
        assert out["exec_rec"] == Decimal("78949100000")
        assert out["exec_dev"] == Decimal("7169400000")
        assert out["exec_sub"] == Decimal("86118600000")
        # Ambiguous cells unset.
        assert "asm_rec" not in out
        assert "asm_dev" not in out
        assert "asm_sub" not in out
        # Reliable columns still present.
        assert out["total"] == Decimal("86769200000")


# ── _dehyphenate_text ───────────────────────────────────────────────


class TestDehyphenateText:
    def test_joins_hyphen_split_county_names(self):
        text = "30. Tharaka-\nNithi 468.6 176.2 644.7"
        out = bp._dehyphenate_text(text)
        # Should join into a single line.
        assert "Tharaka-Nithi" in out

    def test_does_not_join_unrelated_lines(self):
        """Only joins when the line ENDS in '-' and the next starts
        with an uppercase letter — must not stitch normal paragraphs."""
        text = "Some sentence ending in punctuation.\nAnother paragraph."
        assert bp._dehyphenate_text(text) == text


# ── parse_brop_pdf (integration via stubbed pdfplumber) ─────────────


class TestParseBropPdfIntegration:
    def test_emits_national_plus_counties(self, tmp_path):
        cover_page = MagicMock()
        cover_page.extract_text.return_value = (
            "REPUBLIC OF KENYA\nTHE NATIONAL TREASURY\n"
            "2025 BUDGET REVIEW AND OUTLOOK PAPER\nSEPTEMBER 2025"
        )

        para_page = MagicMock()
        para_page.extract_text.return_value = _REAL_PARA_18

        table_page = MagicMock()
        table_page.extract_text.return_value = (
            "Table 10: County Governments Pending Bills as at 30th June 2025\n"
            "1. Nairobi 78,949.1 7,169.4 86,118.6 650.6 650.6 86,769.2 "
            "43,564.27 199.2\n"
            "2. Kilifi 3,820.1 5,367.4 9,187.4 68.2 - 68.2 9,255.6 "
            "21,406.50 43.2\n"
            "Total 122,625.9 49,121.0 171,746.9 4,232.7 924.5 5,157.3 "
            "176,904.2 601,689.14 29\n"
        )

        fake_pdf = MagicMock()
        fake_pdf.pages = [cover_page] * 3 + [para_page, table_page]
        fake_pdf.__enter__ = lambda s: fake_pdf
        fake_pdf.__exit__ = lambda *a: None

        with patch.object(bp.pdfplumber, "open", return_value=fake_pdf):
            result = bp.parse_brop_pdf(tmp_path / "fake.pdf")

        assert result.fiscal_year_label == "FY 2024/25"
        assert result.national is not None
        assert result.national.total == Decimal("525900000000")
        # 2 county rows extracted (Total filtered out by end marker).
        assert len(result.counties) == 2
        names = {c.county for c in result.counties}
        assert names == {"Nairobi", "Kilifi"}

    def test_county_table_anchored_on_title(self, tmp_path):
        """The BROP has at least one OTHER table earlier with
        county-style numbered rows. Without title-anchoring our
        county regex would happily match those too. Verify we ignore
        them when the Table 10 title hasn't appeared yet."""
        cover_page = MagicMock()
        cover_page.extract_text.return_value = (
            "2025 BUDGET REVIEW AND OUTLOOK PAPER"
        )
        # Earlier table (e.g. revenue per county) — same row shape,
        # different data, no Table 10 title.
        decoy_page = MagicMock()
        decoy_page.extract_text.return_value = (
            "Table 5: County Revenue Performance\n"
            "1. Nairobi 100.0 200.0 300.0 50.0 60.0 110.0 410.0 "
            "1000.0 41.0\n"
        )
        # The real Table 10 page comes after, with different numbers.
        table_page = MagicMock()
        table_page.extract_text.return_value = (
            "Table 10: County Governments Pending Bills as at 30th June 2025\n"
            "1. Nairobi 78,949.1 7,169.4 86,118.6 650.6 650.6 86,769.2 "
            "43,564.27 199.2\n"
            "Total 122,625.9 49,121.0 171,746.9 4,232.7 924.5 5,157.3 "
            "176,904.2 601,689.14 29\n"
        )

        fake_pdf = MagicMock()
        fake_pdf.pages = [cover_page] * 3 + [decoy_page, table_page]
        fake_pdf.__enter__ = lambda s: fake_pdf
        fake_pdf.__exit__ = lambda *a: None

        with patch.object(bp.pdfplumber, "open", return_value=fake_pdf):
            result = bp.parse_brop_pdf(tmp_path / "fake.pdf")

        # Decoy Nairobi (total=410M) ignored; real Nairobi (total=86,769.2M) kept.
        assert len(result.counties) == 1
        assert result.counties[0].total == Decimal("86769200000")

    def test_raises_when_neither_section_matches(self, tmp_path):
        cover_page = MagicMock()
        cover_page.extract_text.return_value = (
            "2025 BUDGET REVIEW AND OUTLOOK PAPER"
        )
        empty_page = MagicMock()
        empty_page.extract_text.return_value = "no useful content"

        fake_pdf = MagicMock()
        fake_pdf.pages = [cover_page] * 3 + [empty_page]
        fake_pdf.__enter__ = lambda s: fake_pdf
        fake_pdf.__exit__ = lambda *a: None

        with patch.object(bp.pdfplumber, "open", return_value=fake_pdf):
            with pytest.raises(ValueError, match="No pending-bills data"):
                bp.parse_brop_pdf(tmp_path / "fake.pdf")
