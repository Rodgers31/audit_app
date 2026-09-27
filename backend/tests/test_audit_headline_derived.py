"""The homepage audit headline is derived from extracted findings (issue #233).

Before: ``/audits/federal`` read its opinion banner, basis, emphasis and key
statistics from ``backend/data/reference/oag_national_audit_data.json`` — a
hand-written file the publication gate withheld on every request — so the
homepage showed "Audit opinion not yet published here" and three em-dashes
beside 813 extracted findings that state their opinion sections outright.
``/accountability/missing-funds`` read three hand-written county cases that
cited nothing, so it was permanently empty.

The shapes below are the production shapes, measured on a clone taken
2026-09-26: headings are the Blue Book extractor's ``heading`` values
verbatim, and ``opinion`` is its sticky "Unmodified Opinion" label.

Every endpoint test here is written so it FAILS against origin/main by
assertion, not by import: the derived fields simply are not there.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from models import (
    Audit,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    Extraction,
    FiscalPeriod,
    Severity,
    SourceDocument,
)

REPORT_URL = "https://www.oagkenya.go.ke/wp-content/uploads/2026/05/NG-2024-2025.pdf"
OLD_REPORT_URL = "https://www.oagkenya.go.ke/wp-content/uploads/2025/05/NG-2023-2024.pdf"
COUNTY_URL = "https://www.oagkenya.go.ke/wp-content/uploads/2023/02/CG-2020-2021-VOL-I.pdf"


class _Seeder:
    def __init__(self, db):
        self.db = db
        self._eid = 7000

    def entity(self, name, type_=EntityType.MINISTRY):
        self._eid += 1
        e = Entity(
            id=self._eid,
            country_id=1,
            type=type_,
            canonical_name=name,
            slug=f"derived-{self._eid}",
        )
        self.db.add(e)
        self.db.flush()
        return e

    def finding(
        self,
        entity,
        doc,
        period,
        *,
        title,
        heading="",
        opinion="",
        page,
        body="The report states the matter.",
        severity=Severity.WARNING,
        no=None,
    ):
        text = f"{title} {body}".strip()
        ext = Extraction(
            source_document_id=doc.id,
            extractor="oag_blue_book",
            page_number=page,
            extracted_json={
                "title": title,
                "heading": heading,
                "opinion": opinion,
                "pdf_page": page,
                "paragraph_no": no,
                "finding_text": text,
                "entity_name": f"County Executive of {entity.canonical_name.removesuffix(' County')}" if entity.type == EntityType.COUNTY else entity.canonical_name,
            },
        )
        self.db.add(ext)
        self.db.flush()
        a = Audit(
            entity_id=entity.id,
            period_id=period.id,
            finding_text=text,
            severity=severity,
            source_document_id=doc.id,
            extraction_id=ext.id,
            page_ref=f"p.{page}",
        )
        self.db.add(a)
        self.db.flush()
        return a


def _doc(db, doc_id, url, title, fetched):
    d = SourceDocument(
        id=doc_id,
        country_id=1,
        publisher="Office of the Auditor-General",
        title=title,
        url=url,
        fetch_date=fetched,
        doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,
    )
    db.add(d)
    db.flush()
    return d


def _period(db, pid, label, y0):
    p = FiscalPeriod(
        id=pid,
        country_id=1,
        label=label,
        start_date=datetime(y0, 7, 1),
        end_date=datetime(y0 + 1, 6, 30),
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def national_report(db_session, seed_country):
    """One FY2024/25 national report, plus an older one that must not count."""
    db = db_session
    s = _Seeder(db)
    doc = _doc(db, 9001, REPORT_URL, "NG-2024-2025.pdf", datetime(2026, 7, 19, tzinfo=timezone.utc))
    old = _doc(db, 9000, OLD_REPORT_URL, "NG-2023-2024.pdf", datetime(2025, 7, 1, tzinfo=timezone.utc))
    fy25 = _period(db, 9025, "FY2024/25", 2024)
    fy24 = _period(db, 9024, "FY2023/24", 2023)

    treasury = s.entity("The National Treasury")
    medical = s.entity("State Department for Medical Services")
    devolution = s.entity("State Department for Devolution")
    gender = s.entity("State Department for Gender and Affirmative Action")
    commission = s.entity("Independent Electoral and Boundaries Commission", EntityType.COMMISSION)

    # Qualified, twice, on two pages — counted once, cited at the lower page.
    s.finding(treasury, doc, fy25, title="Unreconciled Balances", heading="Basis for Qualified Opinion", page=22)
    s.finding(treasury, doc, fy25, title="Unsupported Payments", heading="Basis for Qualified Opinion", page=21)
    s.finding(treasury, doc, fy25, title="Unresolved Prior Year Matters", heading="Other Matter", page=24)
    # One vote, two reports: a disclaimer on one, a qualification on another.
    s.finding(medical, doc, fy25, title="Missing Records", heading="Basis for Disclaimer of Opinion", page=295)
    s.finding(medical, doc, fy25, title="Unsupported Pending Bills", heading="Basis for Qualified Opinion", page=264)
    s.finding(medical, doc, fy25, title="Unresolved Prior Years' Audit Matters", heading="Other Matter", page=296)
    # An unmodified opinion stated, and nothing modified found.
    s.finding(
        devolution, doc, fy25, title="Budgetary Control and Performance",
        heading="Emphasis of Matter", opinion="Unmodified Opinion", page=151,
    )
    s.finding(
        devolution, doc, fy25, title="Budgetary Control and Performance",
        heading="Emphasis of Matter", opinion="Unmodified Opinion", page=160,
    )
    # "Unqualified Opinion" is the pre-2016 name for a CLEAN opinion — the
    # substring "qualified" must never file it as a modified one.
    s.finding(commission, doc, fy25, title="Late Submission", heading="Other Matter", opinion="Unqualified Opinion", page=834)
    # No heading and no label: the extractor could not read its opinion.
    s.finding(gender, doc, fy25, title="Unapproved In-Posts", page=737, no=2291)
    # p.39 shape: a REAL finding whose body the extractor lost (a table follows
    # it). It keeps its place in the paragraph sequence, so it counts.
    s.finding(treasury, doc, fy25, title="Unconfirmed Loan Balances", heading="Basis for Qualified Opinion", page=39, body="", no=52)
    # p.538 shape: paragraph 1692 introduces last year's unresolved issues as a
    # numbered TABLE; the extractor reads each row as a body-less "finding"
    # with the sticky heading. Rows 1-2 sit behind the running sequence
    # (1692 → 1693), so they are table rows, not findings of this report.
    energy = s.entity("State Department for Energy")
    s.finding(energy, doc, fy25, title="Unresolved Prior Year Audit Matters", heading="Other Matter", page=538, no=1692)
    s.finding(energy, doc, fy25, title="Inaccuracies in Wages of Temporary Employees", heading="Emphasis of Matter", page=538, body="", no=1)
    s.finding(energy, doc, fy25, title="Unaccounted for Motor Vehicles", heading="Basis for Qualified Opinion", page=538, body="", no=2)
    s.finding(energy, doc, fy25, title="Other Information", heading="Other Matter", page=538, no=1693)
    # The OLDER report: an adverse opinion that must not leak into FY2024/25.
    s.finding(treasury, old, fy24, title="Old Matter", heading="Basis for Adverse Opinion", page=40)
    db.commit()
    return {"doc": doc}


def _headline(client):
    r = client.get("/api/v1/audits/federal")
    assert r.status_code == 200, r.text
    return r.json()


class TestTheOpinionIsDerived:
    def test_the_banner_counts_come_from_the_section_headings(self, client, national_report):
        """RED on origin/main: there is no ``headline`` at all — the banner's
        only source was the withheld file, so it rendered "not yet published"."""
        d = _headline(client)
        h = d.get("headline")
        assert h, "no derived headline in /audits/federal"

        assert h["source_document"]["id"] == 9001, "scoped to the latest report"
        assert h["entities_with_findings"] == 6
        # Treasury, Medical (modified); Devolution, IEBC (clean label). Gender
        # carries neither, so its opinion was NOT read.
        assert h["entities_opinion_read"] == 4
        assert h["modified_opinions"] == [
            {"opinion": "Disclaimer", "entities": 1, "findings": 1},
            {"opinion": "Qualified", "entities": 2, "findings": 4},
        ]

    def test_a_category_nobody_found_is_absent_never_zero(self, client, national_report):
        """The older report's Adverse must not leak in, and "none found" is
        not published as ``Adverse: 0`` — absence is not a count."""
        h = _headline(client)["headline"]
        assert "Adverse" not in {m["opinion"] for m in h["modified_opinions"]}

    def test_unqualified_is_not_read_as_qualified(self, client, national_report):
        h = _headline(client)["headline"]
        named = {e["entity"] for e in h["entities"]}
        assert "Independent Electoral and Boundaries Commission" not in named

    def test_every_entity_cites_the_first_page_it_was_found_on(self, client, national_report):
        h = _headline(client)["headline"]
        by = {(e["entity"], e["opinion"]): e for e in h["entities"]}
        t = by[("The National Treasury", "Qualified")]
        assert t["page_ref"] == "p.21" and t["findings"] == 3
        assert t["source_url"] == f"{REPORT_URL}#page=21"
        d = by[("State Department for Medical Services", "Disclaimer")]
        assert d["source_url"] == f"{REPORT_URL}#page=295"
        # Most severe first.
        assert h["entities"][0]["opinion"] == "Disclaimer"

    def test_no_vote_is_ever_called_clean(self, client, national_report):
        """A vote groups several separately audited reports, so an
        "Unmodified Opinion" on one says nothing about the rest."""
        h = _headline(client)["headline"]
        assert all(e["opinion"] in ("Adverse", "Disclaimer", "Qualified") for e in h["entities"])

    def test_recurring_and_emphasis_are_the_reports_own_words(self, client, national_report):
        h = _headline(client)["headline"]
        assert h["recurring_prior_year"]["entities"] == 3
        assert h["recurring_prior_year"]["findings"] == 3
        e = h["emphasis_of_matter"]
        assert (e["entities"], e["findings"]) == (1, 2)
        assert e["most_common_title"] == "Budgetary Control and Performance"
        assert e["source_url"] == f"{REPORT_URL}#page=151"


class TestTableRowsAreNotFindings:
    def test_rows_of_the_prior_year_table_are_excluded_and_counted(self, client, national_report):
        """Production: 304 of 813 FY2024/25 rows are these. Counting them put
        last year's issues into this year's Emphasis-of-Matter and opinion
        counts, and "7. Unaccounted for Motor Vehicles" onto the
        unaccounted-funds page as a finding of this report."""
        h = _headline(client)["headline"]
        assert h["excluded_table_rows"] == 2
        # The table row carried the sticky "Emphasis of Matter" heading.
        assert (h["emphasis_of_matter"]["entities"], h["emphasis_of_matter"]["findings"]) == (1, 2)
        # …and the other sat under a sticky "Basis for Qualified Opinion".
        assert "State Department for Energy" not in {e["entity"] for e in h["entities"]}

    def test_a_real_finding_with_a_lost_body_is_kept(self, client, national_report):
        h = _headline(client)["headline"]
        t = next(e for e in h["entities"] if e["entity"] == "The National Treasury")
        assert t["findings"] == 3, "p.39 paragraph 52 is a finding, not a table row"

    def test_a_table_row_is_not_an_unaccounted_case(self, client, national_report):
        d = client.get("/api/v1/accountability/missing-funds").json()
        energy = [c for c in d["cases"] if c["entity"] == "State Department for Energy"]
        assert energy == []


class TestTheStaticFileIsGone:
    def test_the_file_fields_are_no_longer_served(self, client, national_report):
        """RED on origin/main: these keys were served (empty) from the file."""
        d = _headline(client)
        for gone in (
            "opinion_type",
            "basis_for_qualification",
            "emphasis_of_matter",
            "key_statistics",
            "ministries_with_adverse_findings",
            "ministries_with_clean_findings",
            "opinion_summary_reason",
            "total_amount_questioned_label",
        ):
            assert gone not in d, f"{gone} still served"
        assert d["total_amount_questioned"] is None
        assert d["total_amount_questioned_reason"] == "not_extracted"

    def test_the_files_are_deleted(self):
        from pathlib import Path

        ref = Path(__file__).resolve().parents[1] / "data" / "reference"
        assert not (ref / "oag_national_audit_data.json").exists()
        assert not (ref / "oag_audit_data.json").exists()

    def test_an_empty_report_says_why_instead_of_rendering_zeros(self, client, seed_country):
        d = _headline(client)
        assert d["headline"] is None
        assert d["headline_reason"] == "no_extraction_backed_findings"


# --------------------------------------------------------------------------
# bootstrap no longer seeds audit findings from the fixtures
# --------------------------------------------------------------------------


@pytest.fixture()
def bootstrapped_from_scratch(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import bootstrap
    from models import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Sess = sessionmaker(bind=engine)
    monkeypatch.setattr(bootstrap, "SessionLocal", Sess)
    bootstrap.initialize_reference_data()
    with Sess() as s:
        yield s


def test_bootstrap_writes_no_audit_rows_and_no_hand_written_cases(bootstrapped_from_scratch):
    """RED on origin/main: a fresh database got the county fixture's findings
    for 8 counties, the national file's 25 findings, and three hand-written
    missing-funds cases on entity.meta — none citing a document."""
    s = bootstrapped_from_scratch
    assert s.query(Audit).count() == 0
    offenders = [
        e.canonical_name
        for e in s.query(Entity).all()
        if {"missing_funds_cases", "audit_summary"} & set((e.meta or {}))
    ]
    assert offenders == []


# --------------------------------------------------------------------------
# /accountability/missing-funds: the Auditor-General's "Unaccounted" findings
# --------------------------------------------------------------------------


@pytest.fixture()
def unaccounted(db_session, seed_country):
    db = db_session
    s = _Seeder(db)
    vol1 = _doc(db, 9101, COUNTY_URL, "CG-2020-2021-VOL-I.pdf", datetime(2026, 9, 3, tzinfo=timezone.utc))
    no_url = _doc(db, 9102, None, "An unopenable report", datetime(2026, 9, 3, tzinfo=timezone.utc))
    fy21 = _period(db, 9021, "FY2020/21", 2020)
    narok = s.entity("Narok County", EntityType.COUNTY)
    laikipia = s.entity("Laikipia County", EntityType.COUNTY)
    kitui = s.entity("Kitui County", EntityType.COUNTY)

    s.finding(
        narok, vol1, fy21, title="Unaccounted Expenditure on Transfers to Polytechnics",
        heading="Basis for Adverse Opinion", page=322,
        body="The statement of receipts and payments reflects an expenditure of Kshs.727,165,800.",
    )
    s.finding(laikipia, vol1, fy21, title="Loss of Funds - Use of Goods and Services", heading="Basis for Qualified Opinion", page=302)
    # "Unaccounted" in the BODY, not the title: the Auditor-General did not
    # head this finding as unaccounted, so it is not listed.
    s.finding(
        kitui, vol1, fy21, title="Unsupported Expenditure", heading="Basis for Qualified Opinion",
        page=73, body="Payments remained unaccounted for at the time of audit.",
    )
    # A matching title on a document nobody can open: withheld, and counted.
    s.finding(kitui, no_url, fy21, title="Unaccounted for Fixed Assets", page=74)
    db.commit()
    return {"narok": narok, "kitui": kitui}


class TestUnaccountedFindings:
    def test_the_page_lists_the_reports_unaccounted_findings(self, client, unaccounted):
        """RED on origin/main: the endpoint read entity.meta cases, so an
        extracted "Unaccounted …" finding never reached this page."""
        d = client.get("/api/v1/accountability/missing-funds").json()
        titles = [c["title"] for c in d["cases"]]
        assert titles == [
            "Loss of Funds - Use of Goods and Services",
            "Unaccounted Expenditure on Transfers to Polytechnics",
        ]
        assert d["total_cases"] == 2
        assert d["affected_counties"] == 2
        narok = next(c for c in d["cases"] if c["county_name"] == "Narok County")
        assert narok["source"]["page_url"] == f"{COUNTY_URL}#page=322"
        assert narok["fiscal_year"] == "FY2020/21"
        assert narok["heading"] == "Basis for Adverse Opinion"
        assert narok["excerpt"].startswith("The statement of receipts")

    def test_no_total_is_published(self, client, unaccounted):
        """The amount column holds the paragraph's only KES figure, which is
        often the balance under discussion — Embu p.126's KES 2.71B is total
        compensation of employees. So no sum, with a reason, never a 0."""
        d = client.get("/api/v1/accountability/missing-funds").json()
        assert d["total_amount"] is None
        assert d["total_amount_reason"] == "no_amount_extracted"
        assert all("amount" not in c for c in d["cases"])

    def test_a_withheld_match_is_counted_not_dropped(self, client, unaccounted):
        d = client.get("/api/v1/accountability/missing-funds").json()
        assert d["withheld"]["count"] == 1

    def test_the_county_view_is_scoped_to_its_county(self, db_session, unaccounted):
        from services.audit_derived import derive_unaccounted_cases

        out = derive_unaccounted_cases(db_session, entity_ids=[unaccounted["kitui"].id])
        assert out["cases"] == []
        assert sum(out["withheld"].values()) == 1


@pytest.mark.parametrize(
    "heading,expected",
    [
        ("Basis for Qualified Opinion", "Qualified"),
        ("Basis for Adverse Opinion", "Adverse"),
        ("Basis for Disclaimer of Opinion", "Disclaimer"),
        ("basis  for\nqualified opinion", "Qualified"),
        ("Basis for Conclusion", None),
        ("Unqualified Opinion", None),
        ("Emphasis of Matter", None),
        ("", None),
        (None, None),
    ],
)
def test_heading_matcher(heading, expected):
    from services.audit_derived import modified_opinion_from_heading

    assert modified_opinion_from_heading(heading) == expected


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Unaccounted for Motor Vehicles", True),
        ("Unaccounted Project Assets", True),
        ("Loss of Funds - Use of Goods and Services", True),
        ("Unsupported Expenditure", False),
        ("Irregular Payment of Acting Allowances", False),
        ("Lost Achievements Due to Delayed Payments", False),
        ("Missing Job Designations in the Payroll Database", False),
    ],
)
def test_unaccounted_title_matcher(title, expected):
    from services.audit_derived import is_unaccounted_title

    assert is_unaccounted_title(title) is expected
