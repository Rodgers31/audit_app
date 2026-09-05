"""Derived findings win over the hand-maintained fixture.

``backend/data/reference/oag_audit_data.json`` is 365 days old and is why
``bootstrap_reference_data`` fails the staleness gate. Since the county-audit
extractor landed, the same findings are derived from the OAG reports
themselves — 1,499 rows across all 47 counties, each carrying the source
document, page and extraction it came from.

Seeding both double-counts the same audit and puts rows with no traceable
extraction next to rows that have one. A county the extractor has NOT reached
still gets the fixture, so deferring loses nothing while coverage grows.

WHY THE TESTS CARE WHICH COLUMN
-------------------------------
``audits.source_document_id`` is NOT NULL, and the fixture path mints a
document of its own for every county it writes. So "has a source document" is
true of EVERY audit row and cannot separate the two. ``extraction_id`` — the
FK to the Layer-3 extractions row, set only by the audits loader — can.
``test_a_fixture_row_does_not_block_the_fixture`` is the test that tells the
two discriminators apart.
"""

from datetime import date, datetime, timezone

import pytest

FIXTURE_ENTRIES = [{"description": "Unsupported expenditure", "id": "Q1", "severity": "high"}]


@pytest.fixture()
def county(db_session):
    """A county with a fiscal period, and nothing else."""
    from models import Country, Entity, EntityType, FiscalPeriod

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
        canonical_name="Homa Bay County",
        slug="homa-bay-county",
    )
    period = FiscalPeriod(
        country_id=country.id,
        label="FY2021/22",
        start_date=date(2021, 7, 1),
        end_date=date(2022, 6, 30),
    )
    db_session.add_all([entity, period])
    db_session.flush()
    return db_session, country, entity, period


def _oag_report(session, country_id: int):
    """A real OAG county report, i.e. what a derived finding points at."""
    from models import DocumentType, SourceDocument

    doc = SourceDocument(
        title="County Assembly of Homa Bay 2021-2022",
        url="https://www.oagkenya.go.ke/county-assembly-of-homa-bay-2021-2022.pdf",
        publisher="Office of the Auditor-General",
        fetch_date=datetime.now(timezone.utc),
        doc_type=DocumentType.AUDIT,
        country_id=country_id,
    )
    session.add(doc)
    session.flush()
    return doc


def _extraction(session, doc_id: int):
    """The Layer-3 row a derived finding hangs off."""
    from models import Extraction

    ext = Extraction(
        source_document_id=doc_id,
        extractor="oag_county_audit",
        extracted_json={"paragraph_no": 1, "title": "Exchequer Releases"},
        page_number=3,
    )
    session.add(ext)
    session.flush()
    return ext


def _run_fixture_path(session, country, entity, period):
    """Drive the function that actually changed."""
    import bootstrap

    bootstrap._upsert_audit_records(
        session,
        entity_id=entity.id,
        period_id=period.id,
        country_id=country.id,
        county_name="Homa Bay",
        audit_entries=FIXTURE_ENTRIES,
    )
    session.flush()


class TestDerivedFindingsWin:
    def test_the_fixture_is_skipped_when_a_derived_finding_exists(self, county):
        """The behaviour asked for: extracted findings suppress the fixture."""
        from models import Audit, Severity

        session, country, entity, period = county
        doc = _oag_report(session, country.id)
        ext = _extraction(session, doc.id)
        session.add(
            Audit(
                entity_id=entity.id,
                period_id=period.id,
                finding_text="Exchequer releases variance",
                severity=Severity.WARNING,
                source_document_id=doc.id,
                extraction_id=ext.id,  # <- what makes it derived
            )
        )
        session.flush()
        before = session.query(Audit).count()

        _run_fixture_path(session, country, entity, period)

        assert session.query(Audit).count() == before, (
            "fixture findings were written alongside the extracted ones"
        )

    def test_a_county_without_derived_findings_still_gets_the_fixture(self, county):
        """POSITIVE CONTROL.

        Deferral must not become a blanket skip while the extractor's coverage
        is still growing — a county it has not reached would otherwise lose the
        only findings it has.
        """
        from models import Audit

        session, country, entity, period = county
        before = session.query(Audit).count()

        _run_fixture_path(session, country, entity, period)

        assert session.query(Audit).count() > before

    def test_a_fixture_row_does_not_block_the_fixture(self, county):
        """The discriminator has to be ``extraction_id``, not "has a document".

        ``source_document_id`` is NOT NULL and the fixture path mints a
        document per county, so a guard keyed on it treats the fixture's OWN
        previous output as if it were extracted, and the county's findings
        silently stop being maintained by either path.
        """
        from models import Audit, Severity

        session, country, entity, period = county
        doc = _oag_report(session, country.id)
        session.add(
            Audit(
                entity_id=entity.id,
                period_id=period.id,
                finding_text="Old fixture finding",
                severity=Severity.WARNING,
                source_document_id=doc.id,
                extraction_id=None,  # <- no extraction: not derived
            )
        )
        session.flush()
        before = session.query(Audit).count()

        _run_fixture_path(session, country, entity, period)

        assert session.query(Audit).count() > before, (
            "a row with no extraction was mistaken for an extracted finding"
        )
