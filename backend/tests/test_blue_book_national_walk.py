"""The national Blue Book walk past paragraph 999, and re-extracting it.

Measured on the FY2024/25 national Blue Book (source document 2392, md5
7e6a6850102a3cadcba38e1f7af9cae3, 915 pages). OAG numbers its paragraphs
continuously across the whole book, 1 to 2819. It does not restart them per
vote. The walk's three-digit pattern stopped at 999, so from vote 1091 on
(pdf p.312) the only numbered lines it could match were the 1, 2, 3 rows of
each "Unresolved Prior Year Matters" table. 329 of the 813 rows production
holds for that document are such rows: 304 with no body, and 25 whose "body"
is the NEXT real paragraph, filed under the row's number and title.

Every fixture line below is copied from that document, with its page.

The second half pins the re-extraction. ``extract_blue_book`` skipped any
document whose md5 had not moved, so a fixed walk never reached a document it
had already read. And ``audits.extraction_id`` is a foreign key, so replacing
the rows a published finding points at has to keep or remove that finding,
never orphan it.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from models import (
    Audit,
    Country,
    DocumentStatus,
    DocumentType,
    Extraction,
    SourceDocument,
)
from seeding.config import SeedingSettings
from seeding.extractors import oag_blue_book as bb
from seeding.extractors.oag_blue_book import PageText, parse_blue_book, segment_chapter


def _page(n: int, text: str) -> PageText:
    return PageText(page_number=n, text=text, method="pdfplumber")


def _paragraphs(findings):
    return [f.paragraph_no for f in findings]


# ── the walk ──────────────────────────────────────────────────────────

#: Vote 1109, pdf p.448. ¶1403's body lists last year's issues in a table
#: numbered 1, 2, 3. ¶1404 is the next real finding.
WATER_P448 = _page(
    1,
    "STATE DEPARTMENT FOR WATER AND SANITATION - VOTE 1109\n"
    "REPORT ON THE FINANCIAL STATEMENTS\n"
    "Qualified Opinion\n"
    "Basis for Qualified Opinion\n"
    "1402. Pending Accounts Payable\n"
    "The statement of financial position reflects pending bills of\n"
    "Kshs.1,234,567 which were not settled.\n"
    "1403. Unresolved Issues in 2020/2021 Report\n"
    "Parliament had directed the State Department to resolve fifty-one (51)\n"
    "issues which were listed in the report of 2020/2021, as detailed below;\n"
    "No. Audit Issue\n"
    "1. Pending Bills\n"
    "2. Unsatisfactory Implementation of Project - Sagana River Restoration\n"
    "Project\n"
    "3. Delayed Projects Completion - Kanini Irrigation\n"
    "8. Lack of Risk Management Policy\n"
    "1404. Failure to Drill Community Boreholes\n"
    "The State Department did not drill the boreholes it had contracted.\n"
    "1",
)


class TestFourDigitParagraphs:
    def test_paragraphs_past_999_are_findings(self):
        findings, _ = segment_chapter(
            [WATER_P448], 1109, "State Department for Water and Sanitation", 1, 1, 0
        )
        assert _paragraphs(findings) == [1402, 1403, 1404]

    def test_prior_year_table_rows_stay_in_the_finding_that_lists_them(self):
        findings, _ = segment_chapter(
            [WATER_P448], 1109, "State Department for Water and Sanitation", 1, 1, 0
        )
        titles = [f.title for f in findings]
        assert "Pending Bills" not in titles
        assert "Lack of Risk Management Policy" not in titles
        by_no = {f.paragraph_no: f for f in findings}
        assert "1. Pending Bills" in by_no[1403].finding_text
        assert "8. Lack of Risk Management Policy" in by_no[1403].finding_text

    def test_a_table_row_never_carries_the_next_paragraphs_text(self):
        """The 25-row shape: row "8." held ¶1404's text in production."""
        findings, _ = segment_chapter(
            [WATER_P448], 1109, "State Department for Water and Sanitation", 1, 1, 0
        )
        holders = [f for f in findings if "Failure to Drill" in f.finding_text]
        assert [(f.paragraph_no, f.title) for f in holders] == [
            (1404, "Failure to Drill Community Boreholes")
        ]


#: Vote 1152, pdf p.575-576. ¶1813 appears nowhere in the report. Under the
#: strict prev+1 rule, every later paragraph of the vote was lost (51).
ENERGY_SKIP = _page(
    1,
    "STATE DEPARTMENT FOR ENERGY - VOTE 1152\n"
    "1812. Unconfirmed Status of Long Outstanding Payables\n"
    "The payables of Kshs.10,000 have been outstanding since 2019.\n"
    "1814. There were no material issues relating to effectiveness of internal\n"
    "controls, risk management and governance.\n"
    "1815. As required by Financing Agreement ADF Loan No. 2100150032195 dated\n"
    "11 December, 2019, I report based on my audit that the project complied.\n"
    "1817. Budgetary Control and Performance\n"
    "The project had a final budget of Kshs.500,000 against actual\n"
    "expenditure of Kshs.250,000.\n"
    "1",
)


class TestSkippedNumbers:
    def test_an_oag_skip_does_not_end_the_chapter(self):
        findings, _ = segment_chapter(
            [ENERGY_SKIP], 1152, "State Department for Energy", 1, 1, 0
        )
        assert _paragraphs(findings) == [1812, 1815, 1817]

    def test_a_wrapped_year_line_is_not_a_paragraph(self):
        """Pdf p.573: "2019. The supplementary financing ..." inside ¶1805.

        The year band 1990-2100 holds 83 real paragraphs in this book
        (votes 1169, 1173, 1174), so it cannot simply be refused. A year
        line is refused because it is not the next number.
        """
        page = _page(
            1,
            "STATE DEPARTMENT FOR ENERGY - VOTE 1152\n"
            "1805. Delayed Completion of the Olkaria Line\n"
            "The line was contracted in 2016 and was to be completed by June\n"
            "2019. The supplementary financing was for the construction of the\n"
            "132kV line.\n"
            "1806. Idle Transformers\n"
            "Transformers worth Kshs.3,000 were idle.\n"
            "1",
        )
        findings, _ = segment_chapter(
            [page], 1152, "State Department for Energy", 1, 1, 0
        )
        assert _paragraphs(findings) == [1805, 1806]
        assert "2019. The supplementary financing" in findings[0].finding_text

    def test_a_real_paragraph_in_the_year_band_is_a_finding(self):
        """Vote 1169, pdf p.637: ¶1990 is a real finding, not a year."""
        page = _page(
            1,
            "STATE DEPARTMENT FOR AGRICULTURE - VOTE 1169\n"
            "1989. Unsupported Expenditure\n"
            "Expenditure of Kshs.7,000 was not supported.\n"
            "1990. Unconfirmed Summary of Fixed Assets Register Balance\n"
            "The register reflects Kshs.9,000 that was not confirmed.\n"
            "1",
        )
        findings, _ = segment_chapter(
            [page], 1169, "State Department for Agriculture", 1, 1, 0
        )
        assert _paragraphs(findings) == [1989, 1990]


class TestAppendixRule:
    def test_an_appendix_cited_in_prose_does_not_end_the_chapter(self):
        """Pdf p.39: ¶52 lost its body, and vote 1071 everything after it."""
        page = _page(
            1,
            "THE NATIONAL TREASURY - VOTE 1071\n"
            "52. Unconfirmed Loan Balances\n"
            "Appendix 11 to the financial statements reflects summary schedule of\n"
            "outstanding loans of Kshs.5,000 that could not be confirmed.\n"
            "53. Unsupported Receipts\n"
            "Receipts of Kshs.6,000 were not supported.\n"
            "1",
        )
        findings, _ = segment_chapter(
            [page], 1071, "The National Treasury", 1, 1, 0
        )
        assert _paragraphs(findings) == [52, 53]
        assert "Appendix 11 to the financial statements" in findings[0].finding_text

    def test_the_appendices_heading_still_ends_the_last_chapter(self):
        """POSITIVE CONTROL. Pdf p.890 sits inside vote 2151's page range.

        The rows after "Appendix A: Unmodified Opinion" list the MDAs by
        opinion. None of them is a finding.
        """
        page = _page(
            1,
            "INDEPENDENT POLICING OVERSIGHT AUTHORITY - VOTE 2151\n"
            "2811. Budgetary Control and Performance\n"
            "The Authority had a final budget of Kshs.8,000.\n"
            "APPENDICES\n"
            "Appendix A: Unmodified Opinion\n"
            "2812. State Department for Public Works\n"
            "2813. Office of the Director of Public Prosecutions\n"
            "1",
        )
        findings, _ = segment_chapter(
            [page], 2151, "Independent Policing Oversight Authority", 1, 1, 0
        )
        assert _paragraphs(findings) == [2811]

    def test_a_lettered_appendix_heading_alone_ends_the_chapter(self):
        page = _page(
            1,
            "THE SENATE - VOTE 2044\n"
            "2686. Budgetary Control and Performance\n"
            "The Senate had a final budget of Kshs.8,000.\n"
            "Appendix B: Qualified Opinion\n"
            "2687. State Department for Foreign Affairs\n"
            "1",
        )
        findings, _ = segment_chapter([page], 2044, "The Senate", 1, 1, 0)
        assert _paragraphs(findings) == [2686]


class TestCleanStatements:
    @pytest.mark.parametrize(
        "line",
        [
            # Pdf p.488, vote 1109 ¶1523, verbatim (sic).
            "The were no material issues noted relating to other information.",
            # Pdf p.624, vote 1166 ¶1965, verbatim (sic).
            "There were not material issues relating Other Information",
        ],
    )
    def test_oag_typos_of_the_clean_statement_are_not_findings(self, line):
        page = _page(
            1,
            "STATE DEPARTMENT FOR WATER AND SANITATION - VOTE 1109\n"
            f"1523. {line}\n"
            "1524. Pending Bills\n"
            "Bills of Kshs.1,000 were not paid.\n"
            "1",
        )
        findings, _ = segment_chapter(
            [page], 1109, "State Department for Water and Sanitation", 1, 1, 0
        )
        assert _paragraphs(findings) == [1524]


class TestWholeBook:
    def test_numbering_continues_across_votes(self):
        """Vote 1072 opens at ¶274 in the real book, not at ¶1."""
        toc = _page(
            1,
            "Table of Contents\n"
            "1071 The National Treasury ........................ 1\n"
            "1072 State Department for Economic Planning ...... 2\n",
        )
        p1 = _page(
            2,
            "THE NATIONAL TREASURY - VOTE 1071\n"
            "999. Pending Bills\n"
            "Bills of Kshs.1,000 were not paid.\n"
            "1000. Idle Assets\n"
            "Assets of Kshs.2,000 were idle.\n"
            "1",
        )
        p2 = _page(
            3,
            "STATE DEPARTMENT FOR ECONOMIC PLANNING - VOTE 1072\n"
            "1001. Unsupported Expenditure\n"
            "Expenditure of Kshs.3,000 was not supported.\n"
            "2",
        )
        res = parse_blue_book([toc, p1, p2], "NATIONAL-GOVERNMENT-2024-2025.pdf")
        assert [(f.vote, f.paragraph_no) for f in res.findings] == [
            (1071, 999),
            (1071, 1000),
            (1072, 1001),
        ]


# ── re-extraction ─────────────────────────────────────────────────────

#: Two votes, as the walk before this change read them. Vote 1109's page
#: carries the prior-year table, so the old walk wrote its rows as findings.
TOC = _page(
    1,
    "Table of Contents\n"
    "1071 The National Treasury ........................ 1\n"
    "1109 State Department for Water and Sanitation ... 2\n",
)
TREASURY = _page(
    2,
    "THE NATIONAL TREASURY - VOTE 1071\n"
    "REPORT ON THE FINANCIAL STATEMENTS\n"
    "Qualified Opinion\n"
    "Basis for Qualified Opinion\n"
    "52. Unconfirmed Loan Balances\n"
    "Appendix 11 to the financial statements reflects summary schedule of\n"
    "outstanding loans of Kshs.5,000 that could not be confirmed.\n"
    "53. Unsupported Receipts\n"
    "Receipts of Kshs.6,000 were not supported.\n"
    "1",
)
WATER = PageText(page_number=3, text=WATER_P448.text[:-1] + "2", method="pdfplumber")
PAGES = [TOC, TREASURY, WATER]
URL = (
    "https://www.oagkenya.go.ke/wp-content/uploads/2026/05/"
    "AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf"
)
MD5 = "7e6a6850102a3cadcba38e1f7af9cae3"


def _legacy_rows(doc):
    """What production holds: the pre-change walk's output for PAGES.

    Written as rows, not by running old code, so the test states exactly the
    three shapes at stake: ¶52 with its body cut off at the appendix line,
    a table row with no body, and a table row whose body is ¶1404's text.
    """

    def row(vote, entity, no, title, text, page):
        return Extraction(
            source_document_id=doc.id,
            page_number=page,
            extractor=bb.EXTRACTOR_ID,
            confidence=0.90,
            extracted_json={
                "schema": "oag_blue_book/v1",
                "vote": vote,
                "entity_name": entity,
                "fiscal_year": "2024/2025",
                "paragraph_no": no,
                "title": title,
                "finding_text": text,
                "pdf_page": page,
                "printed_page": page - 1,
                "subreport": "REPORT ON THE FINANCIAL STATEMENTS",
                "opinion": "Qualified Opinion",
                "heading": "Basis for Qualified Opinion",
                "sub_section": None,
                "severity": "WARNING",
                "amounts": [],
                "extraction_method": "pdfplumber",
            },
        )

    water = "State Department for Water and Sanitation"
    return [
        row(1071, "The National Treasury", 52, "Unconfirmed Loan Balances",
            "Unconfirmed Loan Balances", 2),
        row(1109, water, 1, "Pending Bills", "Pending Bills", 3),
        row(1109, water, 8, "Lack of Risk Management Policy",
            "Lack of Risk Management Policy 1404. Failure to Drill Community "
            "Boreholes The State Department did not drill the boreholes it had "
            "contracted.", 3),
    ]


@pytest.fixture()
def national_doc(db_session, tmp_path, monkeypatch):
    country = db_session.query(Country).filter_by(iso_code="KEN").one_or_none()
    if country is None:
        country = Country(
            name="Kenya", iso_code="KEN", currency="KES",
            timezone="Africa/Nairobi", default_locale="en-KE",
        )
        db_session.add(country)
        db_session.flush()
    pdf = tmp_path / "blue-book.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub; read_pages is patched")
    doc = SourceDocument(
        id=2392,
        country_id=country.id,
        publisher="Office of the Auditor-General",
        title="AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf",
        url=URL,
        md5=MD5,
        file_path=str(pdf),
        fetch_date=datetime(2026, 8, 29, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,
        # The stamp every document extracted before this change carries: an
        # md5 and no walk version.
        meta={"extracted_md5": MD5},
    )
    db_session.add(doc)
    db_session.flush()
    reads = []

    def _read(path, **_kw):
        reads.append(path)
        return list(PAGES)

    monkeypatch.setattr(bb, "read_pages", _read)
    doc._test_reads = reads
    return doc


def _load(db_session, doc, fresh=()):
    from seeding.domains.audits.loader import load_blue_book_extractions
    from seeding.types import DomainRunContext

    return load_blue_book_extractions(
        db_session, doc, SeedingSettings(),
        DomainRunContext(since=None, dry_run=False),
        fresh_extraction_ids=fresh,
    )


def _published(db_session, doc):
    """Legacy rows extracted and loaded, as production holds them."""
    db_session.add_all(_legacy_rows(doc))
    db_session.flush()
    _load(db_session, doc)
    db_session.flush()
    return {
        a.extraction_id: a
        for a in db_session.query(Audit).filter_by(source_document_id=doc.id)
    }


def _findings(db_session, doc):
    rows = (
        db_session.query(Extraction)
        .filter_by(source_document_id=doc.id, extractor=bb.EXTRACTOR_ID)
        .all()
    )
    return sorted(
        (r.extracted_json["vote"], r.extracted_json["paragraph_no"]) for r in rows
    )



def _reviewed_extract(db, doc):
    """Explicit fixture review of the obsolete prior-year table rows."""
    from seeding.extractors.reconciliation import ReconciliationRequired
    try:
        return bb.extract_blue_book(db, doc, SeedingSettings())
    except ReconciliationRequired as exc:
        return bb.extract_blue_book(db, doc, SeedingSettings(), review={
            "proposal": exc.proposal, "source_complete": True,
            "reason": "Checked PAGES fixture: prior-year table rows are not findings.",
        })

class TestReExtraction:
    def test_an_older_walk_is_re_read_although_the_bytes_did_not_move(
        self, db_session, national_doc
    ):
        _published(db_session, national_doc)

        stats = _reviewed_extract(db_session, national_doc)

        assert national_doc._test_reads, "skipped on md5 alone"
        assert not stats.get("skipped_unchanged")
        assert _findings(db_session, national_doc) == [
            (1071, 52), (1071, 53), (1109, 1402), (1109, 1403), (1109, 1404),
        ]
        assert national_doc.meta["extractor_version"] == bb.EXTRACTOR_VERSION

    def test_the_current_walk_at_the_same_bytes_is_not_re_read(
        self, db_session, national_doc
    ):
        """POSITIVE CONTROL: the version stamp must not re-read every night."""
        _reviewed_extract(db_session, national_doc)
        national_doc._test_reads.clear()

        stats = _reviewed_extract(db_session, national_doc)

        assert national_doc._test_reads == []
        assert stats["skipped_unchanged"] is True

    @pytest.mark.parametrize(
        "meta",
        [
            {"extracted_md5": MD5, "extractor_version": "not-a-version"},
            {"extracted_md5": MD5, "extractor_version": None},
            {"extracted_md5": MD5, "extractor_version": True},
        ],
    )
    def test_an_unreadable_version_stamp_means_re_read(
        self, db_session, national_doc, meta
    ):
        """Fail closed: a stamp that is not the current version is not current."""
        db_session.add_all(_legacy_rows(national_doc))
        national_doc.meta = meta
        db_session.flush()

        _reviewed_extract(db_session, national_doc)

        assert national_doc._test_reads

    def test_a_surviving_finding_keeps_its_row_and_its_published_audit(
        self, db_session, national_doc
    ):
        before = _published(db_session, national_doc)
        para52 = next(
            eid for eid, a in before.items()
            if a.external_reference.endswith("-V1071-P52")
        )
        audit_id = before[para52].id

        stats = _reviewed_extract(db_session, national_doc)
        _load(db_session, national_doc, stats.get("fresh_extraction_ids", ()))
        db_session.flush()

        kept = db_session.get(Audit, audit_id)
        assert kept is not None, "¶52's published audit was deleted and re-made"
        assert kept.extraction_id == para52
        assert "outstanding loans of Kshs.5,000" in kept.finding_text

    def test_table_rows_and_their_audits_are_removed(
        self, db_session, national_doc
    ):
        _published(db_session, national_doc)

        stats = _reviewed_extract(db_session, national_doc)
        _load(db_session, national_doc, stats.get("fresh_extraction_ids", ()))
        db_session.flush()

        titles = sorted(
            a.provenance[0]["title"]
            for a in db_session.query(Audit).filter_by(
                source_document_id=national_doc.id
            )
        )
        assert "Pending Bills" not in titles
        assert "Lack of Risk Management Policy" not in titles
        assert stats["removed"] == 2
        assert stats["audits_removed"] == 2

    def test_every_finding_ends_with_exactly_one_audit(
        self, db_session, national_doc
    ):
        _published(db_session, national_doc)

        stats = _reviewed_extract(db_session, national_doc)
        _load(db_session, national_doc, stats.get("fresh_extraction_ids", ()))
        db_session.flush()

        ext_ids = sorted(
            r.id for r in db_session.query(Extraction).filter_by(
                source_document_id=national_doc.id
            )
        )
        audit_ext_ids = sorted(
            a.extraction_id for a in db_session.query(Audit).filter_by(
                source_document_id=national_doc.id
            )
        )
        assert audit_ext_ids == ext_ids
        assert len(ext_ids) == 5

    def test_a_reissued_document_with_published_findings_does_not_break(
        self, db_session, national_doc
    ):
        """The md5 path deleted rows ``audits.extraction_id`` still named.

        Postgres refuses that delete (the column is a foreign key), so a
        re-issued Blue Book would have failed extraction every night.
        """
        _published(db_session, national_doc)
        national_doc.md5 = "0000000000000000000000000000beef"
        db_session.flush()

        _reviewed_extract(db_session, national_doc)
        db_session.flush()

        assert _findings(db_session, national_doc) == [
            (1071, 52), (1071, 53), (1109, 1402), (1109, 1403), (1109, 1404),
        ]

    def test_a_row_something_else_still_cites_is_refused_not_orphaned(
        self, db_session, national_doc
    ):
        """Fail closed on a reference the replacement does not own.

        Audits are the only facts loaded from these rows. If another table
        ever cites one that is going away, stop and say so rather than delete
        evidence a published figure stands on.
        """
        from models import PovertyIndex

        rows = _legacy_rows(national_doc)
        db_session.add_all(rows)
        db_session.flush()
        table_row = rows[1]
        db_session.add(
            PovertyIndex(year=2025, publishable=False, extraction_id=table_row.id)
        )
        db_session.flush()

        with pytest.raises(bb.ExtractionStillReferenced, match="poverty_indices"):
            _reviewed_extract(db_session, national_doc)
        assert db_session.get(Extraction, table_row.id) is not None

    def test_a_re_read_that_finds_nothing_keeps_every_row(
        self, db_session, national_doc, monkeypatch
    ):
        """A walk that suddenly reads nothing is broken, not a report emptied.

        Replacing would delete every published finding of the document.
        """
        before = _published(db_session, national_doc)
        monkeypatch.setattr(bb, "read_pages", lambda _p, **_kw: [TOC])

        with pytest.raises(bb.EmptyReExtraction):
            _reviewed_extract(db_session, national_doc)

        assert _findings(db_session, national_doc) == [
            (1071, 52), (1109, 1), (1109, 8),
        ]
        assert db_session.query(Audit).filter_by(
            source_document_id=national_doc.id
        ).count() == len(before)
        assert "extractor_version" not in national_doc.meta

    def test_an_unchanged_finding_is_kept_not_rewritten(
        self, db_session, national_doc
    ):
        """``confidence`` is Numeric: it reads back as Decimal("0.90"), which
        is not equal to 0.9. Compared raw, every surviving row of documents
        2395 and 2396 (1,498, byte-identical) was counted and written as
        "updated" on the prod clone."""
        _reviewed_extract(db_session, national_doc)
        db_session.commit()
        db_session.expire_all()
        national_doc.meta = {**national_doc.meta, "extractor_version": 1}
        db_session.flush()

        stats = _reviewed_extract(db_session, national_doc)

        assert (stats["kept"], stats["updated"], stats["created"]) == (5, 0, 0)
