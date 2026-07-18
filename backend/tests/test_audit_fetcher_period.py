"""Regression tests for OAG audit-report fiscal-period derivation.

Root-cause context (nightly "Validation failed" issues #121-132): the
live OAG fetcher extracted real findings every night but emitted them
with ``period_label=""`` and no ``start_date``/``end_date``/``audit_year``.
The parser drops any finding missing those fields, so 100% of live
findings were silently discarded (``processed=0``) and the audit table
stayed frozen at 25 rows — below the validation gate's ``>= 50``.

These tests lock in that a fetched finding now carries a fiscal period
derived from the report filename / text, and — critically — that such a
finding SURVIVES the parser end-to-end.
"""

from __future__ import annotations

from seeding.domains.audits.fetcher import (
    _derive_fiscal_period,
    _extract_findings_from_text,
    _fy_from_span,
)
from seeding.domains.audits.parser import parse_audit_payload


class TestDeriveFiscalPeriod:
    def test_from_filename_four_digit_span(self):
        url = (
            "https://www.oagkenya.go.ke/wp-content/uploads/2023/11/"
            "County-Assembly-of-Homa-Bay-2021-2022.pdf"
        )
        assert _derive_fiscal_period(url, "") == (
            "2021/2022",
            "2021-07-01",
            "2022-06-30",
            2022,
        )

    def test_from_filename_two_digit_span(self):
        url = "https://www.oagkenya.go.ke/x/Nakuru-County-2021-22.pdf"
        assert _derive_fiscal_period(url, "") == (
            "2021/2022",
            "2021-07-01",
            "2022-06-30",
            2022,
        )

    def test_national_report_filename(self):
        url = (
            "https://www.oagkenya.go.ke/wp-content/uploads/2026/05/"
            "AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf"
        )
        assert _derive_fiscal_period(url, "") == (
            "2024/2025",
            "2024-07-01",
            "2025-06-30",
            2025,
        )

    def test_upload_path_date_is_not_mistaken_for_fy(self):
        # "/uploads/2023/11/" is a publish date, not a fiscal year — the
        # real FY is later in the filename.
        url = "https://www.oagkenya.go.ke/wp-content/uploads/2023/11/Kisumu-2020-2021.pdf"
        label, start, end, year = _derive_fiscal_period(url, "")
        assert (label, year) == ("2020/2021", 2021)

    def test_fallback_to_year_ended_text(self):
        text = "Report on the Financial Statements for the year ended 30 June 2022."
        assert _derive_fiscal_period("no-year-here.pdf", text) == (
            "2021/2022",
            "2021-07-01",
            "2022-06-30",
            2022,
        )

    def test_inline_fy_span_in_text(self):
        text = "County Government of Mombasa\nFinancial Year 2022/23\nQualified Opinion"
        assert _derive_fiscal_period("x.pdf", text)[0] == "2022/2023"

    def test_source_preferred_over_text(self):
        url = "Bomet-2021-2022.pdf"
        text = "for the year ended 30 June 2019"
        # Filename wins.
        assert _derive_fiscal_period(url, text)[3] == 2022

    def test_no_fiscal_year_returns_none_tuple(self):
        assert _derive_fiscal_period("performance-audit.pdf", "no dates at all") == (
            None,
            None,
            None,
            None,
        )


class TestFyFromSpan:
    def test_consecutive_years_accepted(self):
        assert _fy_from_span(2021, 2022) == (
            "2021/2022",
            "2021-07-01",
            "2022-06-30",
            2022,
        )

    def test_multi_year_range_rejected(self):
        # A "2019-2023" strategic-plan span is not a fiscal year.
        assert _fy_from_span(2019, 2023) is None

    def test_same_year_rejected(self):
        assert _fy_from_span(2022, 2022) is None


class TestFetcherOutputSurvivesParser:
    """The end-to-end regression: findings the fetcher emits must now be
    KEPT by the parser (previously 100% were dropped)."""

    SOURCE = (
        "https://www.oagkenya.go.ke/wp-content/uploads/2023/11/"
        "County-Government-of-Nakuru-2021-2022.pdf"
    )
    TEXT = (
        "County Government of Nakuru\n\n"
        "The audit revealed irregular expenditure of KSh 12,500,000 that was "
        "unaccounted for during the financial year. The payments lacked "
        "supporting documentation and were not authorised in accordance with "
        "the PFM Act, an unsupported and irregular use of public funds.\n\n"
    )

    def test_extracted_findings_carry_period(self):
        findings = _extract_findings_from_text(self.TEXT, self.SOURCE)
        assert findings, "expected at least one finding"
        f = findings[0]
        assert f["period_label"] == "2021/2022"
        assert f["start_date"] == "2021-07-01"
        assert f["end_date"] == "2022-06-30"
        assert f["audit_year"] == 2022

    def test_findings_are_not_dropped_by_parser(self):
        findings = _extract_findings_from_text(self.TEXT, self.SOURCE)
        records = parse_audit_payload(findings)
        # The bug was: len(records) == 0 for len(findings) >= 1.
        assert len(records) == len(findings) >= 1
        rec = records[0]
        assert rec.period_label == "2021/2022"
        assert rec.audit_year == 2022
        assert rec.start_date.isoformat() == "2021-07-01"
        assert rec.end_date.isoformat() == "2022-06-30"
