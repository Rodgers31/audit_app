"""Gates on the OAG county-audit extractor.

`oag_county_audits` shipped with `parser_id=None` — "county report parser not
yet implemented" — so its documents were fetched, registered and never read.
The nightly said so every run: "no parser — fetch/register only". County
audit findings on the site therefore came from a hand-maintained fixture.

Every gate gets a test that makes it FIRE. These findings are the most
consequential data the site carries — an amount attributed to the wrong county
or fiscal year is a public accusation against the wrong government — so the
extractor refuses rather than guesses, and the refusals are what is pinned
here.

Fixture text is the real Homa Bay report (County-Assembly-of-Homa-Bay-2021-2022).
"""

import pytest

from seeding.extractors.oag_county_audit import (
    OPINIONS,
    CountyAuditError,
    build_result,
    county_of,
    parse_amounts,
    parse_auditee,
    parse_fiscal_year,
    parse_opinion,
    severity_for,
)

KNOWN = {"homabay": "Homa Bay", "nairobi": "Nairobi", "taitataveta": "Taita Taveta"}

HEAD = """REPORT OF THE AUDITOR-GENERAL ON COUNTY ASSEMBLY OF HOMA BAY
FOR THE YEAR ENDED 30 JUNE, 2022
PREAMBLE
I draw your attention to the contents of my report which is in three parts:
"""

BODY = """REPORT ON THE FINANCIAL STATEMENTS
Basis for Qualified Opinion
1. Exchequer Releases
The statement receipts and payments for the year under review reflects total
exchequer releases of Kshs.1,122,267,322 which is at variance with the balance
of Kshs.1,177,145,243 resulting to an unreconciled variance of Kshs.54,877,921.
2. Compensation of Employees
The statement reflects Kshs.470,385,703 against an approved budget.
Other Matter
1. Budgetary Control and Performance
The statement reflects final receipts budget of Kshs.1,100,678,005.
REPORT ON LAWFULNESS AND EFFECTIVENESS IN USE OF PUBLIC RESOURCES
Basis for Conclusion
1. Finance Cost
Interest of Kshs.4,952,549 was charged.
"""


def pages(head=HEAD, body=BODY):
    return [(1, head), (2, body)]


class TestFieldParsers:
    def test_reads_the_auditee_from_the_title(self):
        assert parse_auditee(HEAD) == "County Assembly Of Homa Bay"

    def test_maps_an_assembly_and_a_government_to_the_same_county(self):
        """Two auditees, one county — both findings belong to Homa Bay."""
        assert county_of("County Assembly Of Homa Bay", KNOWN) == "Homa Bay"
        assert county_of("County Government Of Homa Bay", KNOWN) == "Homa Bay"

    def test_year_ended_30_june_2022_is_fy_2021_22(self):
        """Kenya's FY runs 1 Jul - 30 Jun; off-by-one files the wrong year."""
        assert parse_fiscal_year(HEAD) == "2021/2022"

    def test_reads_the_opinion_from_the_basis_heading(self):
        assert parse_opinion(BODY) == "Qualified"

    def test_captures_written_figures_only(self):
        amounts = parse_amounts("reflects Kshs.1,122,267,322 and Kshs 54,877,921.50")
        assert amounts == [1122267322.0, 54877921.50]

    def test_a_rounded_phrase_is_not_an_audited_amount(self):
        assert parse_amounts("about Kshs. 1.2 billion") == []

    @pytest.mark.parametrize(
        "opinion,severity",
        [("Adverse", "CRITICAL"), ("Disclaimer", "CRITICAL"),
         ("Qualified", "WARNING"), ("Unqualified", "INFO")],
    )
    def test_severity_follows_the_opinion(self, opinion, severity):
        assert severity_for(opinion) == severity


class TestHappyPath:
    def test_extracts_the_report_identity_and_findings(self):
        r = build_result(pages(), known_counties=KNOWN)
        assert r.county_name == "Homa Bay"
        assert r.fiscal_year_label == "2021/2022"
        assert r.opinion == "Qualified"
        assert len(r.findings) == 4

    def test_numbering_that_restarts_still_yields_unique_keys(self):
        """The bug this guards: part A's finding 1 and 'Other Matter' finding 1
        and part B's finding 1 are three different findings."""
        r = build_result(pages(), known_counties=KNOWN)
        keys = [(f.section, f.sub_section, f.paragraph_no) for f in r.findings]
        assert len(set(keys)) == len(keys) == 4

    def test_findings_carry_their_section_and_page(self):
        r = build_result(pages(), known_counties=KNOWN)
        first = r.findings[0]
        assert first.section == "A"
        assert first.sub_section.lower().startswith("basis for qualified")
        assert first.pdf_page == 2
        assert 1122267322.0 in first.amounts


class TestGatesFire:
    def test_refuses_a_document_with_no_auditee(self):
        with pytest.raises(CountyAuditError) as e:
            build_result(pages(head="SOME OTHER DOCUMENT\n"), known_counties=KNOWN)
        assert e.value.reason == "auditee_not_found"

    def test_refuses_an_auditee_that_is_not_a_known_county(self):
        """Rather than filing findings against a county that does not exist."""
        head = HEAD.replace("HOMA BAY", "ATLANTIS")
        with pytest.raises(CountyAuditError) as e:
            build_result(pages(head=head), known_counties=KNOWN)
        assert e.value.reason == "county_not_resolved"

    def test_refuses_a_report_that_does_not_state_its_year(self):
        head = HEAD.replace("FOR THE YEAR ENDED 30 JUNE, 2022", "UNDATED")
        with pytest.raises(CountyAuditError) as e:
            build_result(pages(head=head), known_counties=KNOWN)
        assert e.value.reason in ("auditee_not_found", "fiscal_year_not_found")

    def test_refuses_an_opinion_it_does_not_recognise(self):
        body = BODY.replace("Basis for Qualified Opinion", "Basis for Vibes Opinion")
        with pytest.raises(CountyAuditError) as e:
            build_result(pages(body=body), known_counties=KNOWN)
        assert e.value.reason == "opinion_not_recognised"

    def test_refuses_a_report_with_no_findings(self):
        body = "REPORT ON THE FINANCIAL STATEMENTS\nBasis for Qualified Opinion\nprose only.\n"
        with pytest.raises(CountyAuditError) as e:
            build_result(pages(body=body), known_counties=KNOWN)
        assert e.value.reason == "no_findings_extracted"

    def test_rejects_a_page_of_undecodable_glyphs_rather_than_publishing_mojibake(self):
        broken = "(cid:3)(cid:11)(cid:82)" * 60
        with pytest.raises(CountyAuditError) as e:
            build_result(pages(body=broken), known_counties=KNOWN)
        assert e.value.reason in ("opinion_not_recognised", "no_findings_extracted")

    def test_every_recognised_opinion_is_one_oag_issues(self):
        assert OPINIONS == ("Unqualified", "Qualified", "Adverse", "Disclaimer")


class TestUnreadableFiles:
    """OAG rotates its URLs; a 404 returns HTML saved with a .pdf name.

    Without a guard, pdfminer's "No /Root object!" propagates out of the
    extractor and aborts the whole audits run over one bad document. Found by
    pointing the extractor at a real dead OAG URL.
    """

    def test_a_non_pdf_quarantines_instead_of_raising(self, tmp_path):
        from seeding.extractors.oag_county_audit import read_pages

        bad = tmp_path / "404.pdf"
        bad.write_text("<html><body>Not Found</body></html>")
        with pytest.raises(CountyAuditError) as e:
            read_pages(bad)
        assert e.value.reason == "pdf_unreadable"

    def test_a_missing_file_is_reported_not_swallowed(self, tmp_path):
        from seeding.extractors.oag_county_audit import read_pages

        with pytest.raises(CountyAuditError) as e:
            read_pages(tmp_path / "absent.pdf")
        assert e.value.reason == "pdf_unreadable"


class TestConsolidatedVolumesAreRefused:
    """OAG publishes county audits in TWO shapes, and this parser reads one.

    Single-entity:  "REPORT OF THE AUDITOR-GENERAL ON COUNTY ASSEMBLY OF
                     HOMA BAY" — ~11 pages, one auditee. Handled.

    Consolidated:   "REPORT OF THE AUDITOR-GENERAL FOR THE COUNTY GOVERNMENTS
                     FOR THE FINANCIAL YEAR 2020/2021 VOLUME II - COUNTY
                     ASSEMBLIES" — 232 and 469 pages, all 47 counties behind a
                     "Code | County Assembly" table of contents. NOT handled.

    Verified against both real volumes. The distinction is "ON <entity>" versus
    "FOR THE COUNTY GOVERNMENTS", and getting it wrong would attribute every
    county's findings to whichever name the title regex happened to catch.
    Refusing is the correct behaviour until a consolidated parser exists.
    """

    CONSOLIDATED_HEAD = (
        "Enhancing Accountability\nREPORT\nOF\nTHE AUDITOR - GENERAL\nFOR\n"
        "THE COUNTY GOVERNMENTS\nFOR\nTHE FINANCIAL YEAR\n2020/2021\n"
        "VOLUME II - COUNTY ASSEMBLIES\n"
    )

    def test_a_consolidated_volume_is_refused_not_mis_attributed(self):
        with pytest.raises(CountyAuditError) as e:
            build_result(
                [(1, self.CONSOLIDATED_HEAD), (2, BODY)], known_counties=KNOWN
            )
        assert e.value.reason == "auditee_not_found"

    def test_the_single_entity_shape_is_still_accepted(self):
        """POSITIVE CONTROL — the refusal above is about shape, not strictness."""
        r = build_result(pages(), known_counties=KNOWN)
        assert r.county_name == "Homa Bay"


class TestConsolidatedVolumesViaBlueBook:
    """The consolidated volumes are read by the Blue Book machinery, taught
    two county-shaped forms.

    Verified against both real volumes:
        VOLUME I  (county executives, 469pp) -> 47 entities,  986 findings
        VOLUME II (county assemblies, 232pp) -> 47 entities,  512 findings

    Two things had to be learned, and each was failing CLOSED rather than
    producing garbage:

      1. parse_toc required a 4-digit vote ("1011 State Department ...");
         the county form numbers 1..47 with a period. It returned 0 entries.
      2. The chapter check confirmed a chapter by finding VOTE-nnnn in the
         page header. County volumes have no such line on ANY page (0 of 232),
         so every chapter was skipped "rather than mis-attributing findings".
    """

    def test_parse_toc_reads_the_county_sequence_form(self):
        from seeding.extractors.oag_blue_book import PageText, parse_toc

        toc = parse_toc([
            PageText(3, "Table of Contents\n"
                        "Introduction ................................ iii\n"
                        "1. County Assembly of Mombasa ............... 1\n"
                        "2. County Assembly of Kwale ................. 4\n", "pdfplumber"),
        ])
        assert toc == [(1, "County Assembly of Mombasa", 1),
                       (2, "County Assembly of Kwale", 4)]

    def test_a_roman_numeral_page_is_not_an_entity(self):
        """"Introduction ..... iii" is front matter, not a county."""
        from seeding.extractors.oag_blue_book import PageText, parse_toc

        toc = parse_toc([PageText(3, "Introduction ......... iii\n", "pdfplumber")])
        assert toc == []

    def test_the_vote_form_takes_precedence_over_the_county_form(self):
        """A national book's front matter can hold short numbered lists.

        Trying both patterns together would let "1. Introduction ..... 3"
        become an entity in a document that has real votes.
        """
        from seeding.extractors.oag_blue_book import PageText, parse_toc

        toc = parse_toc([
            PageText(2, "1. Introduction ....................... 3\n"
                        "1011 State Department for Basic Education ... 5\n", "pdfplumber"),
        ])
        assert toc == [(1011, "State Department for Basic Education", 5)]

    def test_a_chapter_is_confirmed_by_its_entity_heading(self):
        from seeding.extractors.oag_blue_book import _entity_in_head

        assert _entity_in_head(
            "County Assembly of Nairobi City",
            "COUNTY ASSEMBLY OF NAIROBI CITY\nREPORT ON THE FINANCIAL STATEMENTS",
        )

    def test_a_different_county_cannot_confirm_the_chapter(self):
        """The guard that keeps findings on the right county."""
        from seeding.extractors.oag_blue_book import _entity_in_head

        assert not _entity_in_head(
            "County Assembly of Kilifi", "COUNTY ASSEMBLY OF KISUMU\n"
        )

    def test_a_partial_name_cannot_confirm_the_chapter(self):
        from seeding.extractors.oag_blue_book import _entity_in_head

        assert not _entity_in_head("County Assembly of Kilifi", "COUNTY ASSEMBLY OF\n")
