"""Tests for audit parser enhancements.

Covers:
  - Opinion extraction
  - KES amount parsing
  - Query-type classification
  - Management response extraction
  - Recurring findings detection
  - Full parse() integration
"""

from decimal import Decimal

import pytest

from etl.audit_parser import AuditParser


@pytest.fixture()
def parser():
    return AuditParser()


# ---- Opinion extraction ----


class TestExtractOpinion:
    def test_qualified_opinion(self, parser):
        assert parser.extract_opinion("We issued a Qualified Opinion on the accounts.") == "Qualified"

    def test_unqualified_opinion(self, parser):
        assert parser.extract_opinion("The auditor expressed an Unqualified Opinion.") == "Unqualified"

    def test_adverse_opinion(self, parser):
        assert parser.extract_opinion("An Adverse Opinion was given due to material misstatements.") == "Adverse"

    def test_disclaimer_of_opinion(self, parser):
        assert parser.extract_opinion("The auditor issued a Disclaimer of Opinion.") == "Disclaimer"

    def test_disclaimer_takes_priority(self, parser):
        text = "Disclaimer of Opinion\nThis is not a qualified opinion."
        assert parser.extract_opinion(text) == "Disclaimer"

    def test_no_opinion_found(self, parser):
        assert parser.extract_opinion("The county budget was approved.") is None

    def test_case_insensitive(self, parser):
        assert parser.extract_opinion("QUALIFIED OPINION on financial statements") == "Qualified"


# ---- KES amount extraction ----


class TestExtractKesAmount:
    def test_kes_with_commas(self, parser):
        result = parser.extract_kes_amount("The total was KES 12,345,678")
        assert result == Decimal("12345678")

    def test_ksh_notation(self, parser):
        result = parser.extract_kes_amount("Paid Ksh. 500,000 for supplies")
        assert result == Decimal("500000")

    def test_ksh_million(self, parser):
        result = parser.extract_kes_amount("Amount of KES 50 million was unaccounted")
        assert result == Decimal("50000000")

    def test_ksh_billion(self, parser):
        result = parser.extract_kes_amount("Budget of KSh 1.5 billion allocated")
        assert result == Decimal("1500000000")

    def test_sh_notation(self, parser):
        result = parser.extract_kes_amount("Sh. 2,500,000 was paid irregularly")
        assert result == Decimal("2500000")

    def test_no_amount(self, parser):
        assert parser.extract_kes_amount("No monetary value mentioned") is None

    def test_decimal_amount(self, parser):
        result = parser.extract_kes_amount("KES 1,234.56 was spent")
        assert result == Decimal("1234.56")


# ---- Query-type classification ----


class TestClassifyQueryType:
    def test_financial_irregularity(self, parser):
        assert parser.classify_query_type("Unsupported payment of KES 5M") == "Financial Irregularity"

    def test_asset_management(self, parser):
        assert parser.classify_query_type("The asset register was not updated") == "Asset Management"

    def test_procurement(self, parser):
        assert parser.classify_query_type("Procurement irregularities in tender process") == "Procurement"

    def test_non_compliance(self, parser):
        assert parser.classify_query_type("Non-compliance with PFM Act") == "Non-Compliance"

    def test_payroll_hr(self, parser):
        assert parser.classify_query_type("Ghost workers on the payroll") == "Payroll/HR"

    def test_revenue_under_collection(self, parser):
        assert parser.classify_query_type("Own-source revenue below target") == "Revenue Under-Collection"

    def test_cash_management(self, parser):
        assert parser.classify_query_type("Bank reconciliation not done") == "Cash Management"

    def test_weak_internal_controls(self, parser):
        assert parser.classify_query_type("Weak internal controls over expenditure") == "Weak Internal Controls"

    def test_unclassifiable(self, parser):
        assert parser.classify_query_type("The sky is blue") is None

    def test_embezzlement(self, parser):
        assert parser.classify_query_type("Suspected embezzlement of funds") == "Financial Irregularity"


# ---- Management response extraction ----


class TestExtractManagementResponses:
    def test_management_response_section(self, parser):
        text = (
            "Finding: Irregular payment of KES 5M\n"
            "Management Response:\n"
            "The county has initiated recovery proceedings and will ensure compliance.\n"
            "AUDIT RECOMMENDATION"
        )
        responses = parser.extract_management_responses(text)
        assert len(responses) == 1
        assert "recovery proceedings" in responses[0]

    def test_entity_response_section(self, parser):
        text = (
            "Issue noted.\n"
            "Entity Response:\n"
            "We acknowledge the finding and have taken corrective action.\n"
            "NEXT SECTION HEADING"
        )
        responses = parser.extract_management_responses(text)
        assert len(responses) == 1
        assert "corrective action" in responses[0]

    def test_no_response_found(self, parser):
        text = "Finding: Some audit finding with no management section."
        responses = parser.extract_management_responses(text)
        assert responses == []

    def test_multiple_responses(self, parser):
        text = (
            "Management Response:\n"
            "First response text.\n"
            "ANOTHER SECTION\n"
            "Management Response:\n"
            "Second response text.\n"
            "FINAL SECTION"
        )
        responses = parser.extract_management_responses(text)
        assert len(responses) == 2


# ---- Recurring findings detection ----


class TestDetectRecurringFindings:
    def test_consecutive_years_flagged(self):
        findings = [
            {"query_type": "Procurement", "audit_year": 2021},
            {"query_type": "Procurement", "audit_year": 2022},
            {"query_type": "Asset Management", "audit_year": 2021},
        ]
        result = AuditParser.detect_recurring_findings(findings)
        procurement = [r for r in result if r["query_type"] == "Procurement"]
        assert all(r["recurring"] for r in procurement)
        assert procurement[0]["recurring_years"] == [2021, 2022]

    def test_non_consecutive_not_flagged(self):
        findings = [
            {"query_type": "Procurement", "audit_year": 2019},
            {"query_type": "Procurement", "audit_year": 2022},
        ]
        result = AuditParser.detect_recurring_findings(findings)
        assert all(not r["recurring"] for r in result)

    def test_single_finding_not_recurring(self):
        findings = [{"query_type": "Procurement", "audit_year": 2022}]
        result = AuditParser.detect_recurring_findings(findings)
        assert result[0]["recurring"] is False

    def test_empty_input(self):
        assert AuditParser.detect_recurring_findings([]) == []

    def test_no_query_type_skipped(self):
        findings = [
            {"query_type": None, "audit_year": 2021},
            {"query_type": None, "audit_year": 2022},
        ]
        result = AuditParser.detect_recurring_findings(findings)
        assert all(not r["recurring"] for r in result)

    def test_three_consecutive_years(self):
        findings = [
            {"query_type": "Cash Management", "audit_year": 2020},
            {"query_type": "Cash Management", "audit_year": 2021},
            {"query_type": "Cash Management", "audit_year": 2022},
        ]
        result = AuditParser.detect_recurring_findings(findings)
        assert all(r["recurring"] for r in result)
        assert result[0]["recurring_years"] == [2020, 2021, 2022]


# ---- Full parse integration ----


class TestParseIntegration:
    def test_parse_with_opinion_and_query_type(self, parser):
        extraction = {
            "pages": [
                {
                    "page_number": 1,
                    "text": (
                        "County Government of Nakuru\n"
                        "Financial Year 2022/23\n"
                        "Qualified Opinion\n"
                        "Finding: Unsupported payment of KES 12,345,678 for procurement.\n"
                        "Recommendation: Recover the amount."
                    ),
                }
            ],
            "tables": [],
        }
        meta = {"title": "Nakuru County Audit Report FY 2022/23", "file_path": "nakuru.pdf"}
        results = parser.parse(extraction, meta)

        assert len(results) >= 1
        # All findings share the document-level opinion
        assert results[0]["audit_opinion"] == "Qualified"
        # Find the actual financial finding (not the opinion line itself)
        finding = next(r for r in results if "Unsupported" in r["finding_text"])
        assert finding["query_type"] in ("Financial Irregularity", "Procurement")
        assert finding["amount_kes"] == 12345678.0

    def test_parse_with_management_response(self, parser):
        extraction = {
            "pages": [
                {
                    "page_number": 1,
                    "text": (
                        "County Government of Kisumu\n"
                        "Unqualified Opinion\n"
                        "Finding: Irregular expenditure of KES 5,000,000\n"
                        "Management Response:\n"
                        "The county has taken steps to address this issue.\n"
                        "AUDIT RECOMMENDATIONS"
                    ),
                }
            ],
            "tables": [],
        }
        meta = {"title": "Kisumu Audit FY 2023/24"}
        results = parser.parse(extraction, meta)

        assert len(results) >= 1
        assert results[0]["audit_opinion"] == "Unqualified"
        assert results[0]["management_response"] is not None
        assert "taken steps" in results[0]["management_response"]

    def test_parse_no_opinion(self, parser):
        extraction = {
            "pages": [
                {
                    "page_number": 1,
                    "text": "Finding: Pending bills of KES 1,000,000",
                }
            ],
            "tables": [],
        }
        meta = {"title": "Test report"}
        results = parser.parse(extraction, meta)
        assert len(results) >= 1
        assert results[0]["audit_opinion"] is None


# ---- Entity inference covers every county ----


class TestInferEntityCoversAll47:
    """``COUNTY_NAMES`` held 45 of the 47 counties: Kwale and Murang'a were missing.

    Found when the county-selection guard was widened to the whole tree (issue
    #206) and flagged the roster as a hand-picked subset. It was not a verdict,
    it was a gap: a Kwale report was never attributed to Kwale. Title inference
    found nothing, and the first-page fallback handed the report — and every
    finding parsed from it — to whichever OTHER county page 1 happened to name.
    """

    def test_a_kwale_report_is_attributed_to_kwale(self, parser):
        hint = parser.infer_entity(
            "Report of the Auditor-General on the County Executive of Kwale", []
        )
        assert hint is not None and hint["canonical_name"] == "Kwale County", hint

    def test_a_muranga_report_is_attributed_to_muranga(self, parser):
        hint = parser.infer_entity(
            "Report of the Auditor-General on the County Executive of Murang'a", []
        )
        assert hint is not None and hint["canonical_name"] == "Murang'a County", hint

    def test_a_neighbour_named_on_page_one_does_not_take_the_report(self, parser):
        pages = [{"text": "Kwale County borders Mombasa County to the north-east."}]
        hint = parser.infer_entity("Kwale County Executive 2023/24", pages)
        assert hint is not None and hint["canonical_name"] == "Kwale County", hint

    # The three below were added in the consolidation review of #245. The
    # title case above passes because the title names Kwale; with no county in
    # the title, the page-one fallback took the first county in COUNTY_NAMES'
    # order that the text mentioned, not the first the text names, and it
    # matched only the straight-apostrophe spelling of Murang'a.

    def test_page_one_attribution_takes_the_county_named_first(self, parser):
        pages = [{"text": "County Executive of Kwale. Kwale borders Mombasa to the north-east."}]
        hint = parser.infer_entity("Report of the Auditor-General 2023/24", pages)
        assert hint is not None and hint["canonical_name"] == "Kwale County", hint

    @pytest.mark.parametrize("spelling", ["Murang\u2019a", "Muranga", "MURANG\u2019A"])
    def test_muranga_is_recognised_however_it_is_spelled(self, parser, spelling):
        hint = parser.infer_entity(
            f"Report of the Auditor-General on the County Executive of {spelling}", []
        )
        assert hint is not None and hint["canonical_name"] == "Murang'a County", hint

    @pytest.mark.parametrize(
        "spelling, county",
        [("Elgeyo-Marakwet", "Elgeyo Marakwet"), ("Tharaka-Nithi", "Tharaka Nithi"),
         ("Taita-Taveta", "Taita Taveta")],
    )
    def test_hyphenated_county_names_are_recognised(self, parser, spelling, county):
        hint = parser.infer_entity(f"County Executive of {spelling} 2023/24", [])
        assert hint is not None and hint["canonical_name"] == f"{county} County", hint

    def test_a_muranga_report_naming_nairobi_later_stays_muranga(self, parser):
        pages = [{"text": "County Executive of Murang\u2019a — funds transferred to Nairobi."}]
        hint = parser.infer_entity("Report of the Auditor-General 2023/24", pages)
        assert hint is not None and hint["canonical_name"] == "Murang'a County", hint

    def test_the_roster_is_all_47(self):
        from etl.audit_parser import COUNTY_NAMES
        from etl.entity_resolver import COUNTY_NAMES as RESOLVER_COUNTY_NAMES

        def canon(name):
            return name.lower().replace("-", " ").replace("'", "")

        assert {canon(c) for c in COUNTY_NAMES} == {
            canon(c) for c in RESOLVER_COUNTY_NAMES
        }
        assert len({canon(c) for c in COUNTY_NAMES}) == 47
