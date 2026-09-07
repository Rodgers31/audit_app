"""`debt_instruments.publishable` must be a verdict, not a literal.

Issue #137 step 4. This is the ladder's fourth table, and it does not take the
same rung as the other three — the reason is measured, not assumed.

WHY page_ref IS THE WRONG RUNG HERE
------------------------------------
Steps (b) and (c) gated `fiscal_summaries` and `audits` on `page_ref`, because
both come from PDFs and a page is what a reader turns to. `debt_instruments`
does not:

    source_document 2432
      title  CBK — Issues of Treasury Bonds
      url    https://www.centralbank.go.ke/bills-bonds/treasury-bonds/
      HTTP/2 200, content-type: text/html; charset=UTF-8

It is an HTML table. It has no pages. Measured on production 2026-09-07, all
**56 of 56** rows carry `page_ref IS NULL`, and they carry it correctly — there
is no page number that could go there. Requiring one would withhold the entire
register over a category error rather than a provenance gap, which is the
error #137 already ruled out for the national population rows.

So `page_ref` stays NULL on this table by design, and this suite pins that, so
a later "require page_ref everywhere" sweep cannot silently blank the maturity
ladder.

WHAT THE ACTUAL DEFECT IS
--------------------------
`instrument_writer.py` sets the column with a literal:

    values = dict(
        ...
        # The register traces to a document a reader can open, at a URL
        # that is the table itself. That is what publishable asserts here.
        publishable=True,
        quarantine_reason=None,
    )

The comment states a rule. Nothing checks it. Every row is stamped `True`
whatever it contains, so `publishable` on this table is not a verdict — it is a
constant wearing a verdict's name, and `/api/v1/debt/instruments` filters on it
(`main.py:9620`) believing otherwise.

A gate that cannot return False measures nothing. On production all 56 rows
happen to be sound — valid ISINs, positive face values, a resolvable source —
so the constant is not currently publishing anything wrong. That is luck, and
it is exactly the condition under which a dead check goes unnoticed: the day
the CBK page changes shape and the extractor emits a blank ISIN or a zero face
value, the column still says True and the ladder still draws the bar.

THE RUNG THIS SOURCE ADMITS
----------------------------
A reader checking a row opens the CBK table and looks for the security. What
locates it there is its **ISIN** — `KE4000001109` — which is a first-class
column, is what CBK keys the table on, and unlike a synthesised locator can
actually be malformed or missing. So the rule is:

    the source document resolves (a non-blank URL)
    AND the row carries a well-formed ISIN a reader can search that page for
    AND the face value is a positive amount

Deriving a `page_ref` string from the row's own `isin` and `issue_no` was
considered and rejected: a locator computed from the data it locates can never
be absent, so a gate on it can never fail — provenance theatre in place of the
constant it replaced.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from models import (
    DebtInstrument,
    DocumentStatus,
    DocumentType,
    SourceDocument,
)

#: A row shaped like production's: id 113, the first line of the ladder.
SOUND_ROW = dict(
    isin="KE4000001109",
    issue_no="IFB1/2014/12",
    instrument_type="infrastructure_bond",
    face_value=Decimal("15420550000.00"),
    unit="KES",
    coupon_rate=Decimal("11.000"),
    tenor_years=Decimal("12.0"),
    maturity_date=datetime(2026, 10, 12),
    tranches=1,
)

CBK_TABLE_URL = "https://www.centralbank.go.ke/bills-bonds/treasury-bonds/"


@pytest.fixture()
def cbk_doc(db_session, seed_country):
    """The CBK bond table as a source document — a URL, and no pages."""
    doc = SourceDocument(
        id=2432,
        country_id=seed_country.id,
        publisher="Central Bank of Kenya",
        title="CBK — Issues of Treasury Bonds",
        url=CBK_TABLE_URL,
        fetch_date=datetime(2026, 9, 7, tzinfo=timezone.utc),
        doc_type=DocumentType.OTHER,
        status=DocumentStatus.AVAILABLE,
    )
    db_session.add(doc)
    db_session.commit()
    return doc


def _row(**overrides):
    fields = dict(SOUND_ROW)
    fields.update(overrides)
    return DebtInstrument(**fields)


def _reason(row, doc):
    from services.publication_gate import bond_register_withheld_reason

    return bond_register_withheld_reason(row, doc)


class TestTheRuleCanActuallyFail:
    """The point of step 4: a verdict that can return False.

    Each case is a row the current literal stamps `publishable=True`.
    """

    def test_a_sound_row_publishes(self, cbk_doc):
        assert _reason(_row(), cbk_doc) is None

    def test_a_source_document_with_no_url_withholds(self, cbk_doc):
        cbk_doc.url = None
        assert _reason(_row(), cbk_doc) == "source_document_has_no_url"

    def test_a_blank_source_url_withholds(self, cbk_doc):
        cbk_doc.url = "   "
        assert _reason(_row(), cbk_doc) == "source_document_has_no_url"

    def test_no_source_document_at_all_withholds(self):
        assert _reason(_row(), None) == "source_document_has_no_url"

    @pytest.mark.parametrize("isin", [None, "", "   ", "NOTANISIN", "KE123", "1234567890"])
    def test_a_row_without_a_usable_isin_withholds(self, cbk_doc, isin):
        """The ISIN is what a reader searches the CBK page for."""
        assert _reason(_row(isin=isin), cbk_doc) == "no_isin_locator"

    @pytest.mark.parametrize("face", [None, Decimal("0"), Decimal("-1")])
    def test_a_non_positive_face_value_withholds(self, cbk_doc, face):
        """A redemption line of zero is not a redemption line."""
        assert _reason(_row(face_value=face), cbk_doc) == "no_face_value"


class TestPageRefIsNotTheRungHere:
    """Pinned so a later sweep cannot blank the register by uniformity.

    All 56 production rows have `page_ref IS NULL` and are correct to. The
    source is `text/html`; there is no page to cite.
    """

    def test_a_null_page_ref_still_publishes(self, cbk_doc):
        assert _reason(_row(page_ref=None), cbk_doc) is None

    def test_the_whole_production_shaped_register_publishes(self, cbk_doc):
        from services.publication_gate import publishable_bond_register_rows

        rows = [
            _row(isin=f"KE400000{n:04d}", maturity_date=datetime(2026 + n % 20, 1, 1))
            for n in range(56)
        ]
        published = publishable_bond_register_rows(rows, cbk_doc)
        assert len(published) == 56, (
            "a page_ref requirement would blank the maturity ladder over a "
            "source that has no pages"
        )


class TestTheWriterComputesTheVerdict:
    """`publishable=True` in a values dict is the defect, not the shorthand."""

    def test_the_writer_does_not_hardcode_the_column(self, db_session, seed_country):
        """Written against the writer's behaviour, not its source text."""
        from seeding.domains.national_debt import instrument_writer

        register = {
            "source_url": CBK_TABLE_URL,
            "as_of": "2026-09-07",
            "coverage": {"coverage_ratio": 0.6271},
            "withheld_isins": {},
            "securities": [
                {
                    "isin": "KE4000001109",
                    "issue_no": "IFB1/2014/12",
                    "instrument_type": "infrastructure_bond",
                    "face_value_kes": 15420550000.0,
                    "coupon_rate": 11.0,
                    "tenor_years": 12.0,
                    "maturity_date": "2026-10-12",
                    "tranches": 1,
                },
                {
                    # Same register, one unusable row: no ISIN to search for.
                    "isin": "",
                    "issue_no": "FXD1/2021/005",
                    "instrument_type": "fixed_coupon_bond",
                    "face_value_kes": 57566300000.0,
                    "coupon_rate": 11.277,
                    "tenor_years": 5.0,
                    "maturity_date": "2026-11-09",
                    "tranches": 1,
                },
            ],
        }
        instrument_writer.write_bond_register(db_session, register)
        db_session.commit()

        rows = {r.issue_no: r for r in db_session.query(DebtInstrument).all()}
        good = rows["IFB1/2014/12"]
        bad = rows["FXD1/2021/005"]

        assert good.publishable is True
        assert good.quarantine_reason is None
        assert bad.publishable is False, (
            "the writer stamped publishable=True on a row with no ISIN"
        )
        assert bad.quarantine_reason == "no_isin_locator"


class TestTheEndpointSeparatesTwoKindsOfWithholding:
    """`withheld_isins` already means something else, and must keep meaning it.

    The document's metadata carries six ISINs the EXTRACTOR could not settle
    (ambiguous maturities), and the response reports them as `withheld_isins` /
    `withheld_count`. Gate withholding is a different fact with a different
    remedy, and folding it into that count would make a reader think the six
    covered it.
    """

    def test_gate_withholding_is_reported_separately(
        self, db_session, client, cbk_doc
    ):
        cbk_doc.meta = {
            "coverage": {"coverage_ratio": 0.6271},
            "withheld_isins": {"KE4000003808": {"reason": "isin_covers_two_securities"}},
            "as_of": "2026-09-07",
        }
        db_session.add(
            _row(source_document_id=cbk_doc.id, publishable=True, quarantine_reason=None)
        )
        db_session.add(
            _row(
                # Genuinely unusable: nothing here to search the CBK table for.
                isin="NOTANISIN",
                issue_no="FXD1/2021/005",
                maturity_date=datetime(2027, 3, 1),
                source_document_id=cbk_doc.id,
                publishable=False,
                quarantine_reason="no_isin_locator",
            )
        )
        db_session.commit()

        body = client.get("/api/v1/debt/instruments").json()
        assert body["withheld_count"] == 1, "the extractor's count must not move"
        assert body.get("withheld_by_gate") == {
            "count": 1,
            "by_reason": {"no_isin_locator": 1},
        }, body.get("withheld_by_gate")

    def test_a_clean_register_states_zero_rather_than_omitting_the_key(
        self, db_session, client, cbk_doc
    ):
        cbk_doc.meta = {"withheld_isins": {}, "coverage": {}}
        db_session.add(
            _row(source_document_id=cbk_doc.id, publishable=True, quarantine_reason=None)
        )
        db_session.commit()

        body = client.get("/api/v1/debt/instruments").json()
        assert body["withheld_by_gate"] == {"count": 0, "by_reason": {}}


class TestTheEndpointDoesNotTrustAStaleColumn:
    """The filter and the disclosure must be the same rule, not two.

    `publishable` is written by the seeder and read by the request, and those
    happen at different times. Production's 56 rows were all stamped `True` by
    the literal this change removes, so on the first deploy the column is a
    record of the OLD rule while the endpoint answers under the new one.

    Filtering on the column while computing the disclosure from the rule would
    let a row be published AND counted as withheld in the same response. Both
    now come from `bond_register_withheld_reason`, so they cannot disagree.
    """

    def test_a_row_the_rule_rejects_is_not_published_even_if_the_column_says_true(
        self, db_session, client, cbk_doc
    ):
        cbk_doc.meta = {"withheld_isins": {}, "coverage": {}}
        db_session.add(
            _row(source_document_id=cbk_doc.id, publishable=True, quarantine_reason=None)
        )
        db_session.add(
            _row(
                isin="NOTANISIN",
                issue_no="FXD1/2021/005",
                maturity_date=datetime(2027, 3, 1),
                source_document_id=cbk_doc.id,
                # Stale: what the old literal would have written.
                publishable=True,
                quarantine_reason=None,
            )
        )
        db_session.commit()

        body = client.get("/api/v1/debt/instruments").json()
        served = {i["isin"] for i in body["instruments"]}
        assert served == {"KE4000001109"}
        assert body["withheld_by_gate"] == {
            "count": 1,
            "by_reason": {"no_isin_locator": 1},
        }
        assert body["instrument_count"] == 1

    def test_all_rows_withheld_is_not_reported_as_nothing_ingested(
        self, db_session, client, cbk_doc
    ):
        """"No register has been ingested" would be false and misdirect a fix."""
        cbk_doc.meta = {"withheld_isins": {}, "coverage": {}}
        db_session.add(
            _row(isin="NOTANISIN", source_document_id=cbk_doc.id, publishable=True)
        )
        db_session.commit()

        body = client.get("/api/v1/debt/instruments").json()
        assert body["status"] == "unavailable"
        assert body["reason"] == "all_rows_withheld_by_gate", body.get("reason")
        assert body["withheld_by_gate"]["count"] == 1
        assert "not a finding that no government debt falls due" in body["message"]


class TestBothCausesWithhold:
    """The rule and the column are independent, and either one holds a row back.

    `publishable` is the general quarantine channel — an operator, or a future
    cause, marking one row — and it predates this gate. Recomputing the rule
    per request and filtering on THAT alone would un-quarantine every row held
    back for a reason this rule does not happen to name. Recomputing is still
    necessary in the other direction, because production's column was written
    by the literal and cannot be trusted to reject. So: either withholds.
    """

    def test_a_column_quarantine_withholds_a_row_the_rule_accepts(
        self, db_session, client, cbk_doc
    ):
        cbk_doc.meta = {"withheld_isins": {}, "coverage": {}}
        db_session.add(
            _row(
                source_document_id=cbk_doc.id,
                publishable=False,
                quarantine_reason="probe",
            )
        )
        db_session.add(
            _row(
                isin="KE4000009999",
                issue_no="FXD1/2021/005",
                maturity_date=datetime(2027, 3, 1),
                source_document_id=cbk_doc.id,
                publishable=True,
                quarantine_reason=None,
            )
        )
        db_session.commit()

        body = client.get("/api/v1/debt/instruments").json()
        assert {i["isin"] for i in body["instruments"]} == {"KE4000009999"}

    def test_the_disclosure_repeats_the_stored_word(self, db_session, client, cbk_doc):
        """A quarantined row is reported under the reason the column records."""
        cbk_doc.meta = {"withheld_isins": {}, "coverage": {}}
        db_session.add(
            _row(source_document_id=cbk_doc.id, publishable=False,
                 quarantine_reason="probe")
        )
        db_session.add(
            _row(isin="KE4000009999", issue_no="FXD1/2021/005",
                 maturity_date=datetime(2027, 3, 1),
                 source_document_id=cbk_doc.id, publishable=True)
        )
        db_session.commit()

        body = client.get("/api/v1/debt/instruments").json()
        assert body["withheld_by_gate"] == {"count": 1, "by_reason": {"probe": 1}}

    def test_a_quarantine_with_no_reason_still_gets_a_word(
        self, db_session, client, cbk_doc
    ):
        """`publishable=False` with a NULL reason must not report as nothing."""
        cbk_doc.meta = {"withheld_isins": {}, "coverage": {}}
        db_session.add(
            _row(source_document_id=cbk_doc.id, publishable=False,
                 quarantine_reason=None)
        )
        db_session.add(
            _row(isin="KE4000009999", issue_no="FXD1/2021/005",
                 maturity_date=datetime(2027, 3, 1),
                 source_document_id=cbk_doc.id, publishable=True)
        )
        db_session.commit()

        body = client.get("/api/v1/debt/instruments").json()
        assert body["withheld_by_gate"] == {"count": 1, "by_reason": {"quarantined": 1}}
