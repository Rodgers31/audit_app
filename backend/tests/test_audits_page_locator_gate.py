"""A published audit finding must name a page a reader can turn to.

Issue #137 step (c). ``services/publication_gate.py`` asked for this itself:

    **Close this gap in Stage 1** by adding ``page_ref`` to ``audits``
    alongside the ``publishable`` column, backfilling it during extraction,
    and then tightening ``publishable_audit_criterion`` to require it.

Stage 1 did the first two. This does the third.

THE TWO REASONS THE GAP WAS LEFT OPEN HAVE BOTH EXPIRED
--------------------------------------------------------
The module docstring justified the asymmetry — missing-funds cases need
document + URL + page, audits needed only document + URL — on two grounds:

1. *"``Audit`` has no page column."* It has one. Measured on production
   2026-09-07: 2,311 of 2,338 rows carry a ``page_ref``, every one of the form
   ``p.NNN``. None is blank and none is numeric-only.

2. *"Requiring a page would withhold audit id 902 — the single genuine
   extraction in the table."* Audit 902 is **already withheld**: it is 89.6%
   ``(cid:NN)`` glyph codes off a cover page, so the text-integrity clause
   catches it, and it carries ``publishable = False`` today. It was never the
   genuine extraction the docstring took it for.

WHAT IT COSTS: ONE ROW, AND THAT ROW IS NOT A FINDING
------------------------------------------------------
Measured on production 2026-09-07. Of 2,338 audit rows, 2,312 pass the current
gate and 26 are withheld (25 hang off source_document 1836, which has no URL;
1 is audit 902's glyph text). Requiring a locator withholds exactly **one more**:

    audit id 901 | entity 46 Homa Bay | doc 2391 | page_ref NULL
                 | severity CRITICAL  | amount NULL | extraction_id NULL

Its ``finding_text`` is the report's front matter:

    REPORT OF THE AUDITOR-GENERAL ON COUNTY ASSEMBLY OF HOMA BAY
    FOR THE YEAR ENDED 30 JUNE, 2022
    PREAMBLE
    I draw your attention to the contents of my report which is in three
    parts: A. Report on the Financial Statements ... B. Report on Lawfulness
    and Effecti

— 500 characters, cut mid-word, with no amount. Source document 2391 produced
exactly one audit row, and this is it. It is Homa Bay's **only** CRITICAL
finding, and it is counted in two published figures:

    /api/v1/audit/summary        total_findings   2312
    /api/v1/counties/043         audit_findings_count 38

So the cost is not a finding lost. It is a page of boilerplate stopping being
published as a critical audit finding, and two counts becoming correct.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from models import (
    Audit,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    FiscalPeriod,
    Severity,
    SourceDocument,
)

#: Every case that decides whether a string names a page. Shared by the Python
#: predicate and the SQL criterion so the two are tested against ONE table
#: rather than against each other's assumptions.
LOCATOR_CASES = [
    # (value, is a locator a reader can turn to)
    ("p.701", True),
    ("p. 42", True),
    ("Annex VII", True),
    ("701", True),
    ("+5", True),
    ("p.0", True),        # textual: "p.0" does not parse as a number
    (None, False),
    ("", False),
    ("   ", False),
    ("\t\n", False),
    ("0", False),         # page 0 of a 400-page report is not a citation
    ("00", False),
    ("0.0", False),
    ("-3", False),
    ("-0", False),
    (" -3 ", False),
]


@pytest.fixture()
def locator_fixture(db_session, seed_country, seed_source_doc):
    """A resolvable document, an entity and a period to hang findings on."""
    county = Entity(
        id=301,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Homa Bay",
        slug="homa-bay-locator",
    )
    period = FiscalPeriod(
        id=301,
        country_id=seed_country.id,
        label="FY2021/22",
        start_date=datetime(2021, 7, 1),
        end_date=datetime(2022, 6, 30),
    )
    db_session.add_all([county, period])
    db_session.flush()
    return {"county": county, "period": period, "doc": seed_source_doc}


def _add_finding(db_session, ctx, *, page_ref, text="Unsupported expenditure", **kw):
    audit = Audit(
        entity_id=ctx["county"].id,
        period_id=ctx["period"].id,
        finding_text=text,
        severity=kw.pop("severity", Severity.WARNING),
        source_document_id=kw.pop("source_document_id", ctx["doc"].id),
        query_type="financial_audit",
        status="Unresolved",
        page_ref=page_ref,
        **kw,
    )
    db_session.add(audit)
    db_session.commit()
    return audit


def _published_ids(db_session):
    from services.publication_gate import publishable_audit_criterion

    return {
        a.id
        for a in db_session.query(Audit).filter(publishable_audit_criterion()).all()
    }


class TestTheGateRequiresALocator:
    def test_a_finding_with_a_page_publishes(self, db_session, locator_fixture):
        a = _add_finding(db_session, locator_fixture, page_ref="p.409")
        assert a.id in _published_ids(db_session)

    def test_a_finding_without_a_page_is_withheld(self, db_session, locator_fixture):
        """The shape of audit 901: resolvable document, readable text, no page."""
        a = _add_finding(db_session, locator_fixture, page_ref=None)
        assert a.id not in _published_ids(db_session)

    @pytest.mark.parametrize(
        "value,is_locator", [(v, ok) for v, ok in LOCATOR_CASES if v is not None]
    )
    def test_each_locator_shape(self, db_session, locator_fixture, value, is_locator):
        a = _add_finding(db_session, locator_fixture, page_ref=value)
        assert (a.id in _published_ids(db_session)) is is_locator, (
            f"page_ref={value!r} should {'publish' if is_locator else 'be withheld'}"
        )


class TestTheSqlAndPythonFormsAgree:
    """One rule, two expressions — so the two must be pinned to each other.

    ``_has_page_locator`` is Python and runs over materialised rows;
    ``publishable_audit_criterion`` is SQL and runs at 47 call sites. Two
    copies of a rule that must agree is the drift this module exists to
    prevent, so the copies are tested against a shared case table rather than
    trusted to stay in step.
    """

    @pytest.mark.parametrize("value,is_locator", LOCATOR_CASES)
    def test_python_predicate(self, value, is_locator):
        from services.publication_gate import _has_page_locator

        assert _has_page_locator(value) is is_locator

    @pytest.mark.parametrize("value,is_locator", LOCATOR_CASES)
    def test_sql_criterion_matches_the_python_predicate(
        self, db_session, locator_fixture, value, is_locator
    ):
        from services.publication_gate import _has_page_locator

        a = _add_finding(db_session, locator_fixture, page_ref=value)
        in_sql = a.id in _published_ids(db_session)
        assert in_sql is _has_page_locator(value), (
            f"SQL and Python disagree on page_ref={value!r}: "
            f"SQL says {'publish' if in_sql else 'withhold'}, "
            f"Python says {'publish' if _has_page_locator(value) else 'withhold'}"
        )


class TestTheWithheldReasonIsTheRightWord:
    """A row withheld for a missing page must not be reported as unreadable text.

    ``count_withheld_by_reason`` derives its second bucket by subtracting the
    first from the total. Its comment says that keeps the parts summing "even
    if a third cause is added without updating this function" — but the sum is
    not the only thing that matters. Under subtraction a third cause is
    silently filed under ``finding_text_unreadable_cid``, which is precisely
    the mislabelling this function was written to fix, reappearing one layer
    down.
    """

    def test_a_missing_page_is_not_called_unreadable_text(
        self, db_session, locator_fixture
    ):
        from services.publication_gate import count_withheld_by_reason

        _add_finding(db_session, locator_fixture, page_ref=None)
        reasons = count_withheld_by_reason(db_session)
        assert reasons.get("finding_text_unreadable_cid") == 0, (
            "a finding with perfectly readable text was reported as unreadable "
            f"glyphs: {reasons}"
        )
        assert reasons.get("no_page_reference") == 1

    def test_the_three_causes_are_reported_separately(
        self, db_session, locator_fixture, seed_country
    ):
        from services.publication_gate import (
            count_withheld_audits,
            count_withheld_by_reason,
        )

        unopenable = SourceDocument(
            id=1836,
            country_id=seed_country.id,
            publisher="Office of the Auditor General",
            title="Report of the Auditor General on the National Government",
            url=None,
            fetch_date=datetime(2024, 12, 15, tzinfo=timezone.utc),
            doc_type=DocumentType.AUDIT,
            status=DocumentStatus.AVAILABLE,
        )
        db_session.add(unopenable)
        db_session.flush()

        _add_finding(db_session, locator_fixture, page_ref="p.10",
                     source_document_id=unopenable.id)          # no url
        _add_finding(db_session, locator_fixture, page_ref="p.11",
                     text="VISION (cid:23)(cid:24) STATEMENT")  # unreadable
        _add_finding(db_session, locator_fixture, page_ref=None)  # no locator
        _add_finding(db_session, locator_fixture, page_ref="p.12")  # publishable

        reasons = count_withheld_by_reason(db_session)
        assert reasons == {
            "source_document_has_no_url": 1,
            "finding_text_unreadable_cid": 1,
            "no_page_reference": 1,
        }, reasons
        assert sum(reasons.values()) == count_withheld_audits(db_session) == 3

    def test_every_reason_key_is_always_present(self, db_session, locator_fixture):
        """Zeros included — an absent key cannot be told from a zero count."""
        from services.publication_gate import count_withheld_by_reason

        _add_finding(db_session, locator_fixture, page_ref="p.99")
        reasons = count_withheld_by_reason(db_session)
        assert set(reasons) == {
            "source_document_has_no_url",
            "finding_text_unreadable_cid",
            "no_page_reference",
        }
        assert sum(reasons.values()) == 0


class TestTheProductionShape:
    """Audit 901 against a genuine Homa Bay finding, as production holds them."""

    def test_the_preamble_is_withheld_and_the_finding_is_not(
        self, db_session, locator_fixture
    ):
        preamble = _add_finding(
            db_session,
            locator_fixture,
            page_ref=None,
            severity=Severity.CRITICAL,
            text=(
                "REPORT OF THE AUDITOR-GENERAL ON COUNTY ASSEMBLY OF HOMA BAY\n"
                "FOR THE YEAR ENDED 30 JUNE, 2022\nPREAMBLE\nI draw your "
                "attention to the contents of my report which is in three parts:"
            ),
        )
        genuine = _add_finding(
            db_session,
            locator_fixture,
            page_ref="p.409",
            text=(
                "Inaccuracies in County Own Generated Receipts As disclosed in "
                "Note 3 to the financial statements..."
            ),
            amount=Decimal("12500000"),
        )

        published = _published_ids(db_session)
        assert genuine.id in published, "a real finding with a page must publish"
        assert preamble.id not in published, (
            "the report's preamble is published as a CRITICAL audit finding"
        )


class TestTheBackfillWritesTheRightWord:
    """`audits.quarantine_reason` is what an operator reads to know why.

    The backfill assigns the reason by elimination — "not the URL clause, and
    not publishable, therefore unreadable text". With a third clause that
    reasoning stamps `finding_text_unreadable_cid` onto rows whose text is
    perfectly readable and whose only defect is that they cite no page. The
    column, the response and the log are supposed to say the same word about a
    row; here they would all say the same wrong one.
    """

    def test_a_row_with_no_page_is_stamped_no_page_reference(
        self, db_session, locator_fixture
    ):
        from services.publication_gate import backfill_publishable_audits

        a = _add_finding(db_session, locator_fixture, page_ref=None)
        backfill_publishable_audits(db_session)
        db_session.commit()
        db_session.refresh(a)

        assert a.publishable is False
        assert a.quarantine_reason == "no_page_reference", (
            f"stamped {a.quarantine_reason!r} on a row whose text is readable"
        )

    def test_a_readable_located_row_is_published_and_unstamped(
        self, db_session, locator_fixture
    ):
        from services.publication_gate import backfill_publishable_audits

        a = _add_finding(db_session, locator_fixture, page_ref="p.409")
        backfill_publishable_audits(db_session)
        db_session.commit()
        db_session.refresh(a)

        assert a.publishable is True
        assert a.quarantine_reason is None

    def test_the_stats_count_every_withheld_row(self, db_session, locator_fixture):
        """`withheld` was no_url + cid; a third cause must not fall out of it."""
        from services.publication_gate import backfill_publishable_audits

        _add_finding(db_session, locator_fixture, page_ref=None)
        _add_finding(db_session, locator_fixture, page_ref="p.12")
        stats = backfill_publishable_audits(db_session)
        db_session.commit()

        assert stats == {"published": 1, "withheld": 1}, stats

    def test_the_column_agrees_with_the_criterion_row_for_row(
        self, db_session, locator_fixture
    ):
        """The stored verdict and the runtime predicate must never disagree."""
        from services.publication_gate import backfill_publishable_audits

        for value, _ in LOCATOR_CASES:
            _add_finding(db_session, locator_fixture, page_ref=value)
        backfill_publishable_audits(db_session)
        db_session.commit()

        published = _published_ids(db_session)
        for audit in db_session.query(Audit).all():
            assert audit.publishable is (audit.id in published), (
                f"audit {audit.id} page_ref={audit.page_ref!r}: column says "
                f"{audit.publishable}, criterion says {audit.id in published}"
            )


class TestAReaderCanSeeWhy:
    """A withheld count without a reason is a number nobody can act on.

    `count_withheld_by_reason` was built for PR #135's review finding — that
    collapsing two causes into one integer reports rows under a reason that
    does not apply to them — and then never wired to anything: before this
    change it had no caller outside its own module and its tests. So the API
    published *how many* findings were held back and never *why*.

    That was survivable while both causes were properties of the source
    document. It is not now: a reader who can see "27 withheld" cannot tell
    the 25 nobody can open from the one nobody can locate, and those want
    different fixes from different people.
    """

    def test_the_summary_says_why_not_just_how_many(
        self, db_session, client, locator_fixture
    ):
        _add_finding(db_session, locator_fixture, page_ref=None)
        _add_finding(db_session, locator_fixture, page_ref="p.12")

        body = client.get("/api/v1/audits/statistics").json()
        assert "withheld_findings" in body
        assert body["withheld_findings"] == 1
        assert body.get("withheld_findings_by_reason") == {
            "source_document_has_no_url": 0,
            "finding_text_unreadable_cid": 0,
            "no_page_reference": 1,
        }, body.get("withheld_findings_by_reason")

    def test_the_breakdown_always_sums_to_the_count(
        self, db_session, client, locator_fixture, seed_country
    ):
        unopenable = SourceDocument(
            id=1837,
            country_id=seed_country.id,
            publisher="Office of the Auditor General",
            title="Report of the Auditor General",
            url=None,
            fetch_date=datetime(2024, 12, 15, tzinfo=timezone.utc),
            doc_type=DocumentType.AUDIT,
            status=DocumentStatus.AVAILABLE,
        )
        db_session.add(unopenable)
        db_session.flush()
        _add_finding(db_session, locator_fixture, page_ref="p.10",
                     source_document_id=unopenable.id)
        _add_finding(db_session, locator_fixture, page_ref="p.11",
                     text="VISION (cid:23) STATEMENT")
        _add_finding(db_session, locator_fixture, page_ref=None)
        _add_finding(db_session, locator_fixture, page_ref="p.12")

        body = client.get("/api/v1/audits/statistics").json()
        assert sum(body["withheld_findings_by_reason"].values()) == (
            body["withheld_findings"]
        )

    def test_the_breakdown_is_scoped_like_the_count_it_explains(
        self, db_session, client, locator_fixture
    ):
        """`/audits/federal` counts national rows; its reasons must match.

        A federal endpoint explaining its withheld count with global figures
        would state numbers that do not mean what the field name says — the
        same defect `count_withheld_audits` already documents for the count.
        The county row seeded here must not appear in the federal breakdown.
        """
        _add_finding(db_session, locator_fixture, page_ref=None)  # a COUNTY row

        body = client.get("/api/v1/audits/federal").json()
        reasons = body.get("withheld_findings_by_reason")
        assert reasons is not None, "federal states a withheld count with no reasons"
        assert sum(reasons.values()) == body["withheld_findings"]
        assert reasons["no_page_reference"] == 0, (
            "a county finding leaked into the federal breakdown"
        )


class TestAnEmptyRecurringListSaysWhyItIsEmpty:
    """Zero recurring findings is a claim about Kenyan county audits.

    Before this change `/api/v1/audit/recurring` published exactly one
    recurring finding nationally: Homa Bay, "Report on the Financial
    Statements", `years_appeared: [2021, 2022]`, KES 351,032,723 across 17
    finding ids. It spanned two years only because one of those ids was 901 —
    the preamble — carrying `audit_year = 2022`. Every other id in the group
    is 2021. The single recurrence the site reported was a report's title
    page being dated.

    Withholding 901 makes that total 0, which is the honest answer. But a bare
    `total: 0` reads as "nothing recurs", and what is actually true is
    narrower: no entity-and-section group in the PUBLISHED rows appears in two
    different audit years. Absence has to say which absence it is.
    """

    def test_an_empty_result_carries_a_reason(self, db_session, client, locator_fixture):
        _add_finding(db_session, locator_fixture, page_ref="p.12", audit_year=2021)

        body = client.get("/api/v1/audit/recurring").json()
        assert body["total"] == 0
        assert body.get("absent_reason"), (
            "an empty recurring list states 0 with nothing a reader can do "
            f"with it: {body}"
        )

    def test_a_populated_result_carries_no_reason(
        self, db_session, client, locator_fixture
    ):
        """The reason is for absence only — present data explains itself."""
        _add_finding(db_session, locator_fixture, page_ref="p.12", audit_year=2021)
        _add_finding(db_session, locator_fixture, page_ref="p.13", audit_year=2022)

        body = client.get("/api/v1/audit/recurring").json()
        assert body["total"] == 1
        assert body.get("absent_reason") is None

    def test_the_reason_names_the_years_the_data_covers(
        self, db_session, client, locator_fixture
    ):
        """"No recurrence" over a single year is a fact about coverage."""
        _add_finding(db_session, locator_fixture, page_ref="p.12", audit_year=2021)

        reason = client.get("/api/v1/audit/recurring").json()["absent_reason"]
        assert "2021" in reason, (
            f"the reason does not say what the published data covers: {reason!r}"
        )
