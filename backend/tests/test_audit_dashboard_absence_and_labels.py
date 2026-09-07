"""Absence must not render as zero, and a body must not be filed under a
category it does not belong to.

Four defects on ``/api/v1/audit/summary``, all confirmed against the
production database on 2026-09-06 and all pinned here.

1. ``total_irregular_expenditure`` summed ``query_type == "Financial
   Irregularity"`` inside ``coalesce(..., 0)``. No row has ever carried that
   value, so the endpoint published ``0.0`` — "Kenya's irregular expenditure:
   KES 0" — for a figure nobody measured.

2. ``total_unsupported_expenditure`` summed ``status != "Resolved"``: the
   amount on findings of every type, under a specific OAG accounting term. The
   clause is inert as well as wrong — no row in ``audits`` has ever had the
   status "Resolved" — so production published the sum of every publishable
   amount, KES 214,814,058,083.86, as "unsupported expenditure".

3. ``worst_counties`` had no entity-type filter. Production returned "State
   Department for Medical Services", "Executive Office of the President" and
   "State Department for Immigration and Citizen Services" under a field named
   ``county_name``.

4. ``findings_by_opinion`` was ``{"Unmodified Opinion": 182, "Unqualified
   Opinion": 9}`` across 2,312 findings — the same opinion under its current
   and superseded ISA 700 names, counted as two categories, with no Qualified,
   Adverse or Disclaimer opinion anywhere in the set.

Every test here pairs the absence case with a **control** that seeds the thing
being measured and asserts it still comes through. Without the control, a fix
that nulls the field unconditionally passes and the endpoint stops reporting
figures it does have.
"""

from datetime import datetime

import pytest
from models import Audit, Entity, EntityType, FiscalPeriod, Severity


@pytest.fixture()
def audit_period(db_session, seed_country):
    fp = FiscalPeriod(
        id=500,
        country_id=seed_country.id,
        label="FY2024/25",
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    db_session.add(fp)
    db_session.commit()
    return fp


def _published(figure):
    """The number a reader ends up seeing, whatever shape carries it.

    Deliberately shape-tolerant. The fix changes these fields from a bare
    ``float`` to ``{"value": …, "reason": …}``, and an assertion written
    against the new shape alone fails on the old code with a TypeError — which
    proves the shape changed, not that the endpoint stopped publishing a
    number nobody measured. Read through both and the red output names the
    defect: ``assert 0.0 is None``.
    """
    if isinstance(figure, dict):
        return figure.get("value")
    return figure


def _reason(figure):
    return figure.get("reason") if isinstance(figure, dict) else None


def _audit(entity_id, period_id, doc_id, **kw):
    """An audit row that passes the publication gate by default."""
    fields = dict(
        entity_id=entity_id,
        period_id=period_id,
        source_document_id=doc_id,
        finding_text="Expenditure could not be confirmed.",
        severity=Severity.CRITICAL,
        status="published_report",
        audit_year=2024,
    )
    fields.update(kw)
    return Audit(**fields)


# ── 1 + 2. Absence must not render as zero ───────────────────────────────


class TestExpenditureAbsence:
    """The production shape: findings exist, none is classified."""

    @pytest.fixture()
    def seed_unclassified(self, db_session, seed_country, seed_source_doc, audit_period):
        county = Entity(
            id=500,
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name="Kisumu County",
            slug="kisumu-absence",
        )
        db_session.add(county)
        db_session.flush()
        # query_type is the OAG report SECTION, which is what the real
        # extractor writes — never a class of expenditure.
        db_session.add_all(
            [
                _audit(
                    county.id,
                    audit_period.id,
                    seed_source_doc.id,
                    query_type="Report on the Financial Statements",
                    amount=21_624_772_127,
                ),
                _audit(
                    county.id,
                    audit_period.id,
                    seed_source_doc.id,
                    query_type="Report on Lawfulness and Effectiveness in the "
                    "Use of Public Resources",
                    amount=3_000_000,
                ),
            ]
        )
        db_session.commit()
        return county

    def test_irregular_expenditure_is_absent_not_zero(self, client, seed_unclassified):
        data = client.get("/api/v1/audit/summary").json()
        figure = data["total_irregular_expenditure"]
        assert _published(figure) is None, (
            "no finding is classified as irregular expenditure, so KES 0 is a "
            "claim the data does not support"
        )
        assert _reason(figure), "absence must state why"

    def test_unsupported_expenditure_is_absent_not_zero(self, client, seed_unclassified):
        data = client.get("/api/v1/audit/summary").json()
        figure = data["total_unsupported_expenditure"]
        assert _published(figure) is None
        assert _reason(figure)

    def test_unsupported_is_not_the_sum_of_every_unresolved_amount(
        self, client, seed_unclassified
    ):
        """The specific production defect: a general quantity under a specific
        accounting name. 21,624,772,127 + 3,000,000 is what the old query
        returned, because neither row has the status "Resolved"."""
        data = client.get("/api/v1/audit/summary").json()
        assert _published(data["total_unsupported_expenditure"]) != 21_627_772_127.0

    def test_findings_are_still_counted(self, client, seed_unclassified):
        """Withdrawing the money figures must not withdraw the findings."""
        assert client.get("/api/v1/audit/summary").json()["total_findings"] == 2

    def test_empty_database_reports_absence_not_zero(self, client):
        data = client.get("/api/v1/audit/summary").json()
        assert data["total_findings"] == 0
        assert _published(data["total_irregular_expenditure"]) is None
        assert _published(data["total_unsupported_expenditure"]) is None


class TestExpenditureControl:
    """The control: classify the findings and the figures publish again."""

    @pytest.fixture()
    def seed_classified(self, db_session, seed_country, seed_source_doc, audit_period):
        county = Entity(
            id=501,
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name="Nakuru County",
            slug="nakuru-control",
        )
        db_session.add(county)
        db_session.flush()
        db_session.add_all(
            [
                _audit(
                    county.id,
                    audit_period.id,
                    seed_source_doc.id,
                    query_type="Financial Irregularity",
                    amount=50_000_000,
                ),
                _audit(
                    county.id,
                    audit_period.id,
                    seed_source_doc.id,
                    query_type="Financial Irregularity",
                    amount=30_000_000,
                ),
                _audit(
                    county.id,
                    audit_period.id,
                    seed_source_doc.id,
                    query_type="Unsupported Expenditure",
                    amount=12_500_000,
                ),
            ]
        )
        db_session.commit()
        return county

    def test_classified_irregular_expenditure_publishes(self, client, seed_classified):
        figure = client.get("/api/v1/audit/summary").json()[
            "total_irregular_expenditure"
        ]
        assert _published(figure) == 80_000_000
        assert _reason(figure) is None

    def test_classified_unsupported_expenditure_publishes(self, client, seed_classified):
        figure = client.get("/api/v1/audit/summary").json()[
            "total_unsupported_expenditure"
        ]
        assert _published(figure) == 12_500_000
        assert _reason(figure) is None

    def test_classified_but_amountless_is_absent_not_zero(
        self, client, db_session, seed_country, seed_source_doc, audit_period
    ):
        """A third case the old coalesce collapsed: the class exists, the
        amounts do not. SUM() over all-NULL is NULL, and 0 would say the
        findings questioned nothing."""
        county = Entity(
            id=502,
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name="Garissa County",
            slug="garissa-amountless",
        )
        db_session.add(county)
        db_session.flush()
        db_session.add(
            _audit(
                county.id,
                audit_period.id,
                seed_source_doc.id,
                query_type="Financial Irregularity",
                amount=None,
            )
        )
        db_session.commit()
        figure = client.get("/api/v1/audit/summary").json()[
            "total_irregular_expenditure"
        ]
        assert _published(figure) is None
        assert "none records an amount" in _reason(figure)


# ── 3. The county ranking ────────────────────────────────────────────────


class TestWorstCountiesIsWithheld:
    """The ranking is withdrawn, not re-categorised.

    It began as a category defect: production ranked "State Department for
    Medical Services", "Executive Office of the President" and "State
    Department for Immigration and Citizen Services" under a field named
    ``county_name``, 16 MINISTRY entities carrying KES 73.4Bn of the KES
    214.8Bn. Filtering to ``EntityType.COUNTY`` fixes that in one line.

    It does not fix the list. The ORDER is the claim — these are the worst
    counties — and the order rests on ``Audit.amount``, taken from any finding
    paragraph carrying one ``Kshs.`` figure, usually the balance under
    discussion (credibility audit F1). 152 county findings record one; the rest
    do not. Mombasa County led at KES 21.62Bn on a single finding. A filtered
    version of that list is a correctly-categorised false statement about which
    counties fared worst, so the whole ranking goes.
    """

    @pytest.fixture()
    def seed_mixed_entities(
        self, db_session, seed_country, seed_source_doc, audit_period
    ):
        """A ministry that out-spends every county, exactly as production has."""
        ministry = Entity(
            id=97,
            country_id=seed_country.id,
            type=EntityType.MINISTRY,
            canonical_name="State Department for Medical Services",
            slug="sd-medical-services",
        )
        president = Entity(
            id=80,
            country_id=seed_country.id,
            type=EntityType.MINISTRY,
            canonical_name="Executive Office of the President",
            slug="eop",
        )
        county = Entity(
            id=4,
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name="Mombasa County",
            slug="mombasa-worst",
        )
        db_session.add_all([ministry, president, county])
        db_session.flush()
        db_session.add_all(
            [
                _audit(
                    ministry.id, audit_period.id, seed_source_doc.id,
                    amount=25_197_083_648,
                    query_type="Report on the Financial Statements",
                ),
                _audit(
                    president.id, audit_period.id, seed_source_doc.id,
                    amount=13_684_847_839,
                    query_type="Report on the Financial Statements",
                ),
                _audit(
                    county.id, audit_period.id, seed_source_doc.id,
                    amount=21_624_772_127,
                    query_type="Report on the Financial Statements",
                ),
            ]
        )
        db_session.commit()

    def test_ranking_is_null_with_a_reason(self, client, seed_mixed_entities):
        data = client.get("/api/v1/audit/summary").json()
        assert data["worst_counties"] is None
        assert data["worst_counties_reason"]

    def test_absence_is_null_not_an_empty_list(self, client, seed_mixed_entities):
        """``[]`` would read as "no county has a single finding", which is a
        claim about the world and a false one here."""
        assert client.get("/api/v1/audit/summary").json()["worst_counties"] != []

    def test_no_county_named_key_carries_a_non_county(
        self, client, db_session, seed_mixed_entities
    ):
        """The tripwire the deleted type-filter tests leave behind.

        It is not idle: run against pre-fix code it fires with
        ``'State Department for Medical Services' is not a county and is
        published under a county-named key``. It passes today because nothing
        is published, and that is the point — it sweeps the whole response
        rather than one field, so restoring the list without an entity-type
        filter fails here in whatever shape the list comes back in, not only
        in the assertion written for its old one.
        """
        data = client.get("/api/v1/audit/summary").json()
        non_counties = {
            e.canonical_name
            for e in db_session.query(Entity)
            .filter(Entity.type != EntityType.COUNTY)
            .all()
        }

        def walk(node, under_county_key):
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, under_county_key or "county" in key.lower())
            elif isinstance(node, list):
                for item in node:
                    walk(item, under_county_key)
            elif isinstance(node, str) and under_county_key:
                assert node not in non_counties, (
                    f"{node!r} is not a county and is published under a "
                    f"county-named key"
                )

        walk(data, False)

    def test_the_underlying_findings_are_still_served(
        self, client, seed_mixed_entities
    ):
        """The control. Withdrawing the RANKING must not withdraw the data —
        every finding, its entity and its own stated amount stay available,
        each attached to the document it came from, which is the form the
        Auditor-General actually supports."""
        items = client.get("/api/v1/audit/findings").json()["items"]
        assert len(items) == 3
        amounts = {i["amount"] for i in items}
        assert 21_624_772_127 in amounts
        assert 25_197_083_648 in amounts
        assert all(i["source_document_url"] for i in items)


# ── 4. The opinion facet ─────────────────────────────────────────────────


class TestOpinionFacet:
    def _seed(self, db_session, country, doc, period, opinions, base_id=600):
        county = Entity(
            id=base_id,
            country_id=country.id,
            type=EntityType.COUNTY,
            canonical_name="Tana River County",
            slug=f"tana-river-{base_id}",
        )
        db_session.add(county)
        db_session.flush()
        db_session.add_all(
            [
                _audit(county.id, period.id, doc.id, audit_opinion=o)
                for o in opinions
            ]
        )
        db_session.commit()

    def test_clean_only_facet_is_withheld(
        self, client, db_session, seed_country, seed_source_doc, audit_period
    ):
        """The production shape: 182 Unmodified + 9 Unqualified, nothing else."""
        self._seed(
            db_session, seed_country, seed_source_doc, audit_period,
            ["Unmodified Opinion"] * 3 + ["Unqualified Opinion"] * 2,
        )
        data = client.get("/api/v1/audit/summary").json()
        assert data["findings_by_opinion"] is None, (
            "a facet in which every opinion is clean has not been shown to be "
            "complete, and reads as a finding about the entities"
        )
        assert data["findings_by_opinion_reason"]

    def test_facet_publishes_once_a_modified_opinion_exists(
        self, client, db_session, seed_country, seed_source_doc, audit_period
    ):
        """The control — and the gate goes green on its own once the extractor
        stops dropping modified opinions."""
        self._seed(
            db_session, seed_country, seed_source_doc, audit_period,
            ["Unmodified Opinion"] * 3 + ["Qualified Opinion"] * 2,
            base_id=601,
        )
        data = client.get("/api/v1/audit/summary").json()
        assert data["findings_by_opinion"] == {
            "Unmodified Opinion": 3,
            "Qualified Opinion": 2,
        }
        assert data["findings_by_opinion_reason"] is None

    def test_superseded_label_is_not_a_second_category(
        self, client, db_session, seed_country, seed_source_doc, audit_period
    ):
        """"Unqualified" is the pre-revision name for "Unmodified". Two keys
        for one opinion double-counted it into two chart bars and two filter
        options."""
        self._seed(
            db_session, seed_country, seed_source_doc, audit_period,
            ["Unmodified Opinion"] * 3
            + ["Unqualified Opinion"] * 2
            + ["Adverse Opinion"],
            base_id=602,
        )
        facet = client.get("/api/v1/audit/summary").json()["findings_by_opinion"]
        assert facet == {"Unmodified Opinion": 5, "Adverse Opinion": 1}
        assert "Unqualified Opinion" not in facet

    def test_trends_applies_the_same_gate(
        self, client, db_session, seed_country, seed_source_doc, audit_period
    ):
        """Withholding on /summary while /trends serves the same facet year by
        year would move the defect, not fix it."""
        self._seed(
            db_session, seed_country, seed_source_doc, audit_period,
            ["Unmodified Opinion"] * 3 + ["Unqualified Opinion"] * 2,
            base_id=603,
        )
        data = client.get("/api/v1/audit/trends").json()
        assert data["opinion_per_year"] is None
        assert data["opinion_per_year_reason"]


# ── The opinion canonicaliser, unit level ────────────────────────────────


class TestCanonicalOpinion:
    """The fold must not run in the wrong direction. "Unqualified" contains
    "qualified" as a substring, and a careless ``in`` test would file the clean
    opinion as a modified one — turning the gate this module implements into a
    machine for publishing exactly the facet it exists to withhold."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Unmodified Opinion", "Unmodified Opinion"),
            ("Unqualified Opinion", "Unmodified Opinion"),
            ("unqualified", "Unmodified Opinion"),
            ("Qualified Opinion", "Qualified Opinion"),
            ("Qualified", "Qualified Opinion"),
            ("Adverse Opinion", "Adverse Opinion"),
            ("Disclaimer of Opinion", "Disclaimer of Opinion"),
            ("Disclaimer", "Disclaimer of Opinion"),
            (None, None),
            ("", None),
            ("   ", None),
        ],
    )
    def test_canonical_names(self, raw, expected):
        from services.audit_opinions import canonical_opinion

        assert canonical_opinion(raw) == expected

    def test_unqualified_is_not_filed_as_qualified(self):
        from services.audit_opinions import canonical_opinion, has_modified_opinion

        assert canonical_opinion("Unqualified Opinion") != "Qualified Opinion"
        assert not has_modified_opinion({"Unmodified Opinion": 191})

    def test_unrecognised_label_is_kept_not_folded(self):
        """An unanticipated label must stay visible under its own name rather
        than be absorbed into an opinion it may not be — and it does not by
        itself unlock the facet, because it is not evidence of a modified
        opinion."""
        from services.audit_opinions import canonical_opinion, opinion_facet

        assert canonical_opinion("Emphasis of Matter") == "Emphasis of Matter"
        counts, reason = opinion_facet({"Emphasis of Matter": 4})
        assert counts is None
        assert reason

    def test_empty_input_is_an_empty_facet_not_a_withheld_one(self):
        """Nothing to be flattering about, and a gate that cannot be observed
        on an empty database is not observable at all."""
        from services.audit_opinions import opinion_facet

        assert opinion_facet({}) == ({}, None)
