"""A fixture whose facts are now derived stops counting as stale.

``bootstrap_provenance`` censused fixture FILES READ, so ``oag_audit_data.json``
counted against the staleness gate at 365 days even after the county-audit
extractor took over everything in it. The gate's message then blamed a file
that publishes nothing, and buried the two that genuinely still need a live
path.

The danger in "superseded" is obvious: it is one short step from an excuse
that stale data hides behind. So every test here is really about the ways it
must REFUSE to fire — no session, a county the extractor missed, a case that
could still be published, an error mid-check. The one happy-path test is the
smallest part of this file on purpose.
"""

import json
from datetime import date, datetime, timezone

import pytest

import bootstrap
from models import (
    Audit,
    Country,
    DocumentType,
    Entity,
    EntityType,
    Extraction,
    FiscalPeriod,
    Severity,
    SourceDocument,
)

FIXTURE = json.loads(bootstrap.AUDIT_DATA_PATH.read_text())
FIXTURE_COUNTIES = sorted(
    {
        str(e.get("county") or "").strip()
        for e in (FIXTURE.get("audit_queries") or [])
        + (FIXTURE.get("missing_funds_cases") or [])
    }
    - {""}
)


@pytest.fixture()
def seeded(db_session):
    """Every county the fixture names, each with one extracted finding.

    This is the state production is actually in — verified 2026-09-05: all 8
    counties carry 25-49 extraction-backed findings each.
    """
    country = Country(
        name="Kenya",
        iso_code="KEN",
        currency="KES",
        timezone="Africa/Nairobi",
        default_locale="en-KE",
    )
    db_session.add(country)
    db_session.flush()

    period = FiscalPeriod(
        country_id=country.id,
        label="FY2021/22",
        start_date=date(2021, 7, 1),
        end_date=date(2022, 6, 30),
    )
    doc = SourceDocument(
        title="Report of the Auditor-General",
        url="https://www.oagkenya.go.ke/report.pdf",
        publisher="Office of the Auditor-General",
        doc_type=DocumentType.AUDIT,
        country_id=country.id,
        fetch_date=datetime.now(timezone.utc),
    )
    db_session.add_all([period, doc])
    db_session.flush()

    entities = {}
    for name in FIXTURE_COUNTIES:
        entity = Entity(
            country_id=country.id,
            type=EntityType.COUNTY,
            # The census resolves the same way the seeding loop does.
            canonical_name=f"{name} County",
            slug=name.lower().replace(" ", "-"),
        )
        db_session.add(entity)
        db_session.flush()
        ext = Extraction(
            source_document_id=doc.id,
            extractor="oag_county_audit",
            extracted_json={"paragraph_no": 1},
            page_number=3,
        )
        db_session.add(ext)
        db_session.flush()
        db_session.add(
            Audit(
                entity_id=entity.id,
                period_id=period.id,
                finding_text=f"{name} finding",
                severity=Severity.WARNING,
                source_document_id=doc.id,
                extraction_id=ext.id,
            )
        )
        entities[name] = entity
    db_session.flush()
    return db_session, entities


def _county_file(provenance):
    return next(
        f for f in provenance["files"] if f["file"] == bootstrap.AUDIT_DATA_PATH.name
    )


class TestItFires:
    def test_the_county_fixture_is_superseded_once_every_county_is_covered(self, seeded):
        session, _ = seeded
        p = bootstrap.bootstrap_provenance(session)

        assert _county_file(p)["superseded"] is True
        assert bootstrap.AUDIT_DATA_PATH.name not in p["stale_files"]
        assert bootstrap.AUDIT_DATA_PATH.name in p["superseded_files"]

    def test_it_says_what_the_evidence_was(self, seeded):
        """A bare True is not auditable."""
        session, _ = seeded
        evidence = _county_file(bootstrap.bootstrap_provenance(session))[
            "supersession_evidence"
        ]
        assert "extraction-backed" in evidence
        assert "publication gate" in evidence

    def test_the_stale_detail_stops_blaming_it(self, seeded):
        """The point of the change: the message names the files that matter."""
        session, _ = seeded
        p = bootstrap.bootstrap_provenance(session)

        assert p["source_fallback_reason"] == "fixture_stale"
        assert "oag_national_audit_data.json" in p["source_fallback_detail"]
        assert "already superseded" in p["source_fallback_detail"]

    def test_the_age_is_still_reported(self, seeded):
        """Superseded is not hidden — the file is still read, and still old."""
        session, _ = seeded
        assert _county_file(bootstrap.bootstrap_provenance(session))["age_days"] > 180


class TestItRefusesToFire:
    def test_without_a_database_nothing_is_superseded(self):
        """No evidence means stale. This is how every non-DB caller sees it."""
        p = bootstrap.bootstrap_provenance()

        assert _county_file(p)["superseded"] is False
        assert bootstrap.AUDIT_DATA_PATH.name in p["stale_files"]
        assert "without a database" in _county_file(p)["supersession_evidence"]

    def test_one_uncovered_county_is_enough_to_keep_it_stale(self, seeded):
        """The fixture is still what that county gets served.

        Partial supersession is not supersession — this is the test that stops
        it becoming a blanket excuse as soon as the extractor touches ONE
        county.
        """
        session, entities = seeded
        victim = FIXTURE_COUNTIES[0]
        session.query(Audit).filter(
            Audit.entity_id == entities[victim].id
        ).delete(synchronize_session=False)
        session.flush()

        p = bootstrap.bootstrap_provenance(session)

        assert _county_file(p)["superseded"] is False
        assert bootstrap.AUDIT_DATA_PATH.name in p["stale_files"]
        assert victim in _county_file(p)["supersession_evidence"]

    def test_a_finding_with_no_extraction_does_not_count_as_coverage(self, seeded):
        """Same discriminator the deferral uses, for the same reason."""
        session, entities = seeded
        victim = FIXTURE_COUNTIES[0]
        for audit in session.query(Audit).filter(
            Audit.entity_id == entities[victim].id
        ):
            audit.extraction_id = None
        session.flush()

        assert _county_file(bootstrap.bootstrap_provenance(session))["superseded"] is False

    def test_a_county_that_resolves_to_no_entity_keeps_it_stale(self, seeded):
        session, entities = seeded
        victim = FIXTURE_COUNTIES[0]
        entities[victim].canonical_name = "Something Else Entirely"
        session.flush()

        p = bootstrap.bootstrap_provenance(session)

        assert _county_file(p)["superseded"] is False
        assert "resolve to no entity" in _county_file(p)["supersession_evidence"]

    def test_a_publishable_missing_funds_case_keeps_it_stale(
        self, seeded, monkeypatch, tmp_path
    ):
        """The second consumer, which nothing defers.

        These cases are withheld only because they carry no source document.
        Give one a document and a page and it is published straight out of a
        year-old file — so the file is not superseded.
        """
        session, _ = seeded
        doc = session.query(SourceDocument).first()
        payload = json.loads(json.dumps(FIXTURE))
        payload["missing_funds_cases"][0]["source_document_id"] = doc.id
        payload["missing_funds_cases"][0]["page_ref"] = "p. 12"
        # Same basename, so the census keys line up with the real file.
        stand_in = tmp_path / bootstrap.AUDIT_DATA_PATH.name
        stand_in.write_text(json.dumps(payload))
        monkeypatch.setattr(bootstrap, "AUDIT_DATA_PATH", stand_in)

        p = bootstrap.bootstrap_provenance(session)

        assert _county_file(p)["superseded"] is False
        assert "would still be published" in _county_file(p)["supersession_evidence"]

    def test_a_check_that_raises_leaves_the_fixture_stale(self, seeded):
        """An error is not evidence of supersession."""
        session, _ = seeded

        def _boom(_session):
            raise RuntimeError("database went away")

        original = dict(bootstrap._SUPERSESSION_CHECKS)
        bootstrap._SUPERSESSION_CHECKS["county_audit_findings"] = _boom
        try:
            p = bootstrap.bootstrap_provenance(session)
        finally:
            bootstrap._SUPERSESSION_CHECKS.clear()
            bootstrap._SUPERSESSION_CHECKS.update(original)

        assert _county_file(p)["superseded"] is False
        assert "database went away" in _county_file(p)["supersession_evidence"]


class TestTheOtherFixturesAreUntouched:
    @pytest.mark.parametrize(
        "name", ["oag_national_audit_data.json", "enhanced_county_data.json"]
    )
    def test_a_fixture_with_no_check_is_never_superseded(self, seeded, name):
        """Nothing is superseded by default — only by a check that passed."""
        session, _ = seeded
        f = next(f for f in bootstrap.bootstrap_provenance(session)["files"] if f["file"] == name)

        assert f["superseded"] is False
        assert f["supersession_evidence"] is None
        assert name in bootstrap.bootstrap_provenance(session)["stale_files"]

    def test_the_gate_still_fails(self, seeded):
        """The whole run must stay red while any live path is not working."""
        from seeding.staleness import DECLARED_NO_SOURCE_REASONS

        session, _ = seeded
        p = bootstrap.bootstrap_provenance(session)

        assert p["is_stale"] is True
        assert p["source_fallback_reason"] not in DECLARED_NO_SOURCE_REASONS
