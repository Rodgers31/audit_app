"""A fixture whose facts are now derived stops counting as stale.

``bootstrap_provenance`` censuses fixture FILES READ, and a file is excused
from the staleness gate only by a check, run against the database, proving
nothing in it can reach a reader.

The danger in "superseded" is obvious: it is one short step from an excuse
that stale data hides behind. So every test here is really about the ways it
must REFUSE to fire. The two OAG audit fixtures this file used to exercise
were retired in issue #233 once those checks passed on a production clone;
what remains is ``enhanced_county_data.json`` and the generic machinery.
"""

import json
from datetime import date, datetime, timezone

import pytest

import bootstrap
from models import (
    BudgetLine,
    DocumentType,
    Entity,
    EntityType,
    FiscalPeriod,
    Loan,
    PopulationData,
    SourceDocument,
)

# ==========================================================================
# enhanced_county_data.json
# ==========================================================================

COUNTY_FIXTURE = json.loads(bootstrap.COUNTY_DATA_PATH.read_text())["county_data"]
A_COUNTY = sorted(COUNTY_FIXTURE)[0]


@pytest.fixture()
def county_reference(db_session):
    """One county from the file, holding figures that are NOT the file's.

    The baseline is therefore "superseded", so each test below adds exactly
    one thing that must take it back to stale. Anything that fails to is a
    hole in the check.
    """
    from models import Country

    country = Country(
        name="Kenya",
        iso_code="KEN",
        currency="KES",
        timezone="Africa/Nairobi",
        default_locale="en-KE",
    )
    db_session.add(country)
    db_session.flush()

    entity = Entity(
        country_id=country.id,
        type=EntityType.COUNTY,
        canonical_name=f"{A_COUNTY} County",
        slug=A_COUNTY.lower().replace(" ", "-"),
        # Figures that came from somewhere else: one shilling off the file's,
        # which is the smallest difference that is still a different claim.
        meta={
            "metrics": {
                "FY2024/25": {
                    field: float(COUNTY_FIXTURE[A_COUNTY][field]) + 1
                    for field in bootstrap._MODELLED_COUNTY_METRICS
                    if COUNTY_FIXTURE[A_COUNTY].get(field) is not None
                }
            }
        },
    )
    period = FiscalPeriod(
        country_id=country.id,
        label="FY2024/25",
        start_date=date(2024, 7, 1),
        end_date=date(2025, 6, 30),
    )
    db_session.add_all([entity, period])
    db_session.flush()
    return db_session, country, entity, period


def _fixture_minted_doc(session, country_id):
    """A document of the shape ``_ensure_source_document`` mints for the file."""
    doc = SourceDocument(
        title=f"{A_COUNTY} County Budget FY2024/25",
        publisher="County Treasury",
        doc_type=DocumentType.BUDGET,
        country_id=country_id,
        fetch_date=datetime.now(timezone.utc),
        meta={"source": bootstrap.COUNTY_DATA_PATH.name, "county": A_COUNTY},
    )
    session.add(doc)
    session.flush()
    return doc


def _reference_file(provenance):
    return next(
        f
        for f in provenance["files"]
        if f["file"] == bootstrap.COUNTY_DATA_PATH.name
    )


class TestCountyReferenceData:
    def test_the_baseline_is_superseded(self, county_reference):
        """Nothing traces to the file, so nothing holds it back."""
        session, *_ = county_reference

        assert _reference_file(bootstrap.bootstrap_provenance(session))["superseded"] is True

    def test_stored_metrics_that_match_the_file_keep_it_stale(self, county_reference):
        """The decisive one, and what production actually looks like.

        A Controller of Budget figure would not match a
        population-times-4,500 estimate to the shilling, so an exact match
        means the stored figure IS this file's.
        """
        session, _, entity, _ = county_reference
        entity.meta = {
            "metrics": {
                "FY2024/25": {
                    f: COUNTY_FIXTURE[A_COUNTY][f]
                    for f in bootstrap._MODELLED_COUNTY_METRICS
                    if COUNTY_FIXTURE[A_COUNTY].get(f) is not None
                }
            }
        }
        session.flush()

        f = _reference_file(bootstrap.bootstrap_provenance(session))
        assert f["superseded"] is False
        assert "modelled figures exactly" in f["supersession_evidence"]

    def test_matching_population_alone_does_not_keep_it_stale(self, county_reference):
        """Census 2019 is a real count.

        A live source would legitimately agree with it, so treating that
        agreement as evidence would strand the file as stale forever, for a
        figure that is not in dispute.
        """
        session, _, entity, _ = county_reference
        meta = dict(entity.meta)
        meta["metrics"]["FY2024/25"]["population"] = COUNTY_FIXTURE[A_COUNTY]["population"]
        entity.meta = meta
        session.flush()

        assert _reference_file(bootstrap.bootstrap_provenance(session))["superseded"] is True

    @pytest.mark.parametrize("surface", ["loan", "population", "budget_line"])
    def test_a_row_on_a_document_this_file_minted_keeps_it_stale(
        self, county_reference, surface
    ):
        """Each of the three tables the file writes, checked on its own.

        counties_budget writes BudgetLine rows only, so loans and population
        have no live source at all — but all three are gated here, because
        which one is outstanding is exactly what the evidence has to say.
        """
        from models import DebtCategory

        session, country, entity, period = county_reference
        doc = _fixture_minted_doc(session, country.id)

        if surface == "loan":
            session.add(
                Loan(
                    entity_id=entity.id,
                    lender="County Treasury",
                    debt_category=DebtCategory.DOMESTIC_BONDS,
                    principal=1_000_000,
                    outstanding=1_000_000,
                    currency="KES",
                    issue_date=date(2024, 7, 1),
                    source_document_id=doc.id,
                )
            )
            expected = "loan row(s)"
        elif surface == "population":
            session.add(
                PopulationData(
                    entity_id=entity.id,
                    year=2019,
                    total_population=666_763,
                    source_document_id=doc.id,
                )
            )
            expected = "population row(s)"
        else:
            session.add(
                BudgetLine(
                    entity_id=entity.id,
                    period_id=period.id,
                    category="total",
                    allocated_amount=1_000_000,
                    currency="KES",
                    source_document_id=doc.id,
                )
            )
            expected = "budget-line row(s)"
        session.flush()

        f = _reference_file(bootstrap.bootstrap_provenance(session))
        assert f["superseded"] is False
        assert expected in f["supersession_evidence"]

    def test_documents_are_found_by_what_they_declare_not_their_publisher(
        self, county_reference
    ):
        """Under-counting documents would call the file superseded.

        That is the one direction this must never fail in, so the lookup keys
        on the meta the writer records, not on a title or publisher that a
        later change could alter.
        """
        session, country, entity, period = county_reference
        doc = _fixture_minted_doc(session, country.id)
        doc.publisher = "Somebody Else Entirely"
        doc.title = "Renamed"
        session.flush()
        session.add(
            PopulationData(
                entity_id=entity.id,
                year=2019,
                total_population=666_763,
                source_document_id=doc.id,
            )
        )
        session.flush()

        assert _reference_file(bootstrap.bootstrap_provenance(session))["superseded"] is False

    def test_an_unreadable_file_is_not_superseded(self, county_reference, monkeypatch, tmp_path):
        session, *_ = county_reference
        missing = tmp_path / bootstrap.COUNTY_DATA_PATH.name
        monkeypatch.setattr(bootstrap, "COUNTY_DATA_PATH", missing)

        f = _reference_file(bootstrap.bootstrap_provenance(session))
        assert f["superseded"] is False
        assert "could not read" in f["supersession_evidence"]


class TestTheOtherFixturesAreUntouched:
    def test_a_fixture_with_no_check_is_never_superseded(self, county_reference):
        """Nothing is superseded by default — only by a check that passed.

        Asserted against ``_supersession`` directly rather than a named file:
        every declaration carries a check now, and the invariant being
        pinned is about the DEFAULT, not about which files happen to lack one.
        """
        session, *_ = county_reference
        assert bootstrap._supersession({"live_source": "audits"}, session) == (
            False,
            None,
        )

    def test_a_declaration_naming_a_missing_check_is_not_superseded(self, county_reference):
        """A typo in the table must not read as proof."""
        session, *_ = county_reference
        superseded, evidence = bootstrap._supersession(
            {"live_source": "audits", "superseded_check": "no_such_check"}, session
        )
        assert superseded is False
        assert "no_such_check" in evidence

    def test_the_gate_still_fails_while_any_live_path_is_broken(self, county_reference):
        """The whole run must stay red while any live path is not working.

        The state this fixture builds clears every check, so the condition
        is created explicitly: one file that is NOT superseded must be enough
        to keep the census stale and out of the by-design exemption.
        """
        from seeding.staleness import DECLARED_NO_SOURCE_REASONS

        session, *_ = county_reference

        def _not_superseded(_session):
            return False, "the live path is not working"

        original = dict(bootstrap._SUPERSESSION_CHECKS)
        bootstrap._SUPERSESSION_CHECKS["county_reference_data"] = _not_superseded
        try:
            p = bootstrap.bootstrap_provenance(session)
        finally:
            bootstrap._SUPERSESSION_CHECKS.clear()
            bootstrap._SUPERSESSION_CHECKS.update(original)

        assert p["is_stale"] is True
        assert p["source_fallback_reason"] == "fixture_stale"
        assert p["source_fallback_reason"] not in DECLARED_NO_SOURCE_REASONS
