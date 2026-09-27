"""The freshness gate that could not see a four-year gap.

On 2026-09-24 the nightly printed [OK] for every freshness gate while every
county finding on the site was FY2020/21 and OAG had published FY2021/22 to
FY2024/25. The audits table was moving (the national Blue Book reloads
nightly), the domain reached its publisher, and no table lost rows. None of
those gates asks "has the publisher got a year out that we hold nothing for?"
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from seeding import staleness
from seeding.staleness import COUNTY_AUDIT_LABEL, FAIL, OK, WARN, check_county_audit_coverage

LISTING = [
    "2016/2017", "2017/2018", "2018/2019", "2019/2020", "2020/2021",
    "2021/2022", "2022/2023", "2023/2024", "2024/2025",
]


@pytest.fixture()
def db(db_session):
    from models import Country, Entity, EntityType

    country = Country(
        name="Kenya", iso_code="KEN", currency="KES",
        timezone="Africa/Nairobi", default_locale="en-KE",
    )
    db_session.add(country)
    db_session.flush()
    for i in range(47):
        db_session.add(
            Entity(country_id=country.id, type=EntityType.COUNTY,
                   canonical_name=f"Example{chr(65 + i // 26)}{chr(65 + i % 26)} County", slug=f"county-{i}")
        )
    db_session.add(
        Entity(country_id=country.id, type=EntityType.MINISTRY,
               canonical_name="The National Treasury", slug="the-national-treasury")
    )
    db_session.flush()
    return db_session


def _counties(session):
    from models import Entity, EntityType

    return session.query(Entity).filter(Entity.type == EntityType.COUNTY).all()


def _findings(session, audit_year, entities, publishable=True, roles=("executives", "assemblies")):
    from models import (
        Audit, DocumentStatus, DocumentType, Extraction, FiscalPeriod, Severity, SourceDocument,
    )

    doc = SourceDocument(
        country_id=entities[0].country_id, publisher="Office of the Auditor-General",
        title="vol.pdf", url=f"https://www.oagkenya.go.ke/v{audit_year}.pdf",
        fetch_date=datetime(2026, 9, 1), doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,
    )
    period = FiscalPeriod(
        country_id=entities[0].country_id, label=f"FY{audit_year - 1}/{str(audit_year)[2:]}-{publishable}",
        start_date=datetime(audit_year - 1, 7, 1), end_date=datetime(audit_year, 6, 30),
    )
    session.add_all([doc, period])
    session.flush()
    for e in entities:
        for role in roles:
            auditee = f"County {'Executive' if role == 'executives' else 'Assembly'} of {e.canonical_name.removesuffix(' County')}"
            ext = Extraction(source_document_id=doc.id, page_number=1,
                extractor="oag_county_volume", confidence=0.9,
                extracted_json={"fiscal_year": f"{audit_year - 1}/{audit_year}",
                    "entity_name": auditee, "auditee": auditee,
                    "volume_kind": role, "pdf_page": 1})
            session.add(ext)
            session.flush()
            session.add(Audit(entity_id=e.id, period_id=period.id, finding_text="x",
                severity=Severity.WARNING, source_document_id=doc.id,
                extraction_id=ext.id, audit_year=audit_year, page_ref="p.1", publishable=publishable))
    session.flush()


def _audits_run(session, listing, when=datetime(2026, 9, 26, 2, 30), dry_run=False, key=True,
                volumes=None):
    from models import IngestionJob, IngestionStatus

    meta = {"oag_county_discovery": {"listing_fiscal_years": listing}} if key else {}
    meta["county_volumes"] = volumes if volumes is not None else {
        "discovered": 8, "processed": [f"{year}/{year+1} {role}" for year in range(2021, 2025) for role in ("executives", "assemblies")],
        "already_current": [], "deferred": [], "failed": [], "partial": [],
    }
    session.add(
        IngestionJob(domain="audits", status=IngestionStatus.COMPLETED, dry_run=dry_run,
                     started_at=when, meta=meta)
    )
    session.flush()


def _only(findings):
    assert len(findings) == 1, findings
    return findings[0]


class TestCoverage:
    def test_red_on_the_state_production_is_in_today(self, db):
        """1,498 county findings across 47 counties, all FY2020/21. The
        listing publishes four later years."""
        _findings(db, 2021, _counties(db))
        _audits_run(db, LISTING)
        f = _only(check_county_audit_coverage(db))
        assert f.level == FAIL
        assert "2021/2022, 2022/2023, 2023/2024, 2024/2025" in f.message
        assert "newest county year published is FY2020/2021" in f.message

    def test_national_findings_do_not_count_as_county_coverage(self, db):
        from models import Entity, EntityType

        treasury = db.query(Entity).filter(Entity.type == EntityType.MINISTRY).all()
        for year in (2022, 2023, 2024, 2025):
            _findings(db, year, treasury)
        _audits_run(db, LISTING)
        assert _only(check_county_audit_coverage(db)).level == FAIL

    def test_a_withheld_finding_does_not_count(self, db):
        for year in (2022, 2023, 2024, 2025):
            _findings(db, year, _counties(db), publishable=False)
        _audits_run(db, LISTING)
        assert _only(check_county_audit_coverage(db)).level == FAIL

    def test_green_once_every_listed_year_is_held_for_every_county(self, db):
        for year in (2022, 2023, 2024, 2025):
            _findings(db, year, _counties(db))
        _audits_run(db, LISTING)
        assert _only(check_county_audit_coverage(db)).level == OK

    def test_years_before_the_floor_are_not_required(self, db):
        """OAG lists 2016/17 on; the nightly ingests from 2021/22."""
        for year in (2022, 2023, 2024, 2025):
            _findings(db, year, _counties(db))
        _audits_run(db, LISTING)
        f = _only(check_county_audit_coverage(db))
        assert f.level == OK and "2016/2017" not in f.message

    def test_partial_county_coverage_warns(self, db):
        for year in (2022, 2023, 2024):
            _findings(db, year, _counties(db))
        _findings(db, 2025, _counties(db)[:40])
        _audits_run(db, LISTING)
        f = _only(check_county_audit_coverage(db))
        assert f.level == WARN and "2024/2025 (40/47 counties)" in f.message

    def test_a_new_year_on_the_listing_turns_it_red(self, db):
        for year in (2022, 2023, 2024, 2025):
            _findings(db, year, _counties(db))
        _audits_run(db, LISTING + ["2025/2026"])
        f = _only(check_county_audit_coverage(db))
        assert f.level == FAIL and "2025/2026" in f.message


class TestTheBacklogIsNamed:
    """A fiscal year counts as held once ANY volume of it loads for all 47
    counties. On the prod-clone simulation the gate read OK after run 1 while
    'FY2021/22 assemblies' was still deferred: every county had executive
    findings. The job metadata named the deferral and no gate read it."""

    def _covered(self, db):
        for year in (2022, 2023, 2024, 2025):
            _findings(db, year, _counties(db))

    def test_a_deferred_volume_warns_even_when_every_year_is_covered(self, db):
        self._covered(db)
        _audits_run(db, LISTING, volumes={"discovered": 8, "deferred": ["2021/2022 assemblies"], "failed": []})
        levels = {f.level: f.message for f in check_county_audit_coverage(db)}
        assert WARN in levels and "2021/2022 assemblies" in levels[WARN]
        assert FAIL not in levels

    def test_a_failed_volume_warns(self, db):
        self._covered(db)
        _audits_run(db, LISTING, volumes={"discovered": 8, "deferred": [],
                                          "failed": ["2023/2024 executives: fetch: not a PDF"]})
        levels = {f.level: f.message for f in check_county_audit_coverage(db)}
        assert "2023/2024 executives" in levels[WARN]

    def test_a_clean_run_stays_ok(self, db):
        self._covered(db)
        _audits_run(db, LISTING, volumes={"discovered": 8, "processed": [f"{year}/{year+1} {role}" for year in range(2021, 2025) for role in ("executives", "assemblies")], "already_current": [], "deferred": [], "failed": []})
        assert _only(check_county_audit_coverage(db)).level == OK


class TestAbsenceIsNotHealth:
    def test_no_recorded_listing_warns(self, db):
        _findings(db, 2021, _counties(db))
        f = _only(check_county_audit_coverage(db))
        assert f.level == WARN and "Unrecorded is not the same as covered" in f.message

    def test_a_run_whose_listing_was_unreadable_falls_back_to_the_last_one_read(self, db):
        _findings(db, 2021, _counties(db))
        _audits_run(db, LISTING, when=datetime(2026, 9, 25, 2, 30))
        _audits_run(db, [], when=datetime(2026, 9, 26, 2, 30))  # WAF night
        f = _only(check_county_audit_coverage(db))
        assert f.level == FAIL and "read 2026-09-25" in f.message

    def test_a_dry_run_listing_is_not_evidence(self, db):
        _findings(db, 2021, _counties(db))
        _audits_run(db, LISTING, dry_run=True)
        assert _only(check_county_audit_coverage(db)).level == WARN

    def test_a_listing_naming_no_year_from_the_floor_warns(self, db):
        _audits_run(db, ["2016/2017", "2017/2018"])
        f = _only(check_county_audit_coverage(db))
        assert f.level == WARN and "named no fiscal year" in f.message


class TestWiring:
    def test_the_nightly_runs_it(self, db):
        """seed.yml calls run_all; a check it does not call gates nothing."""
        _findings(db, 2021, _counties(db))
        _audits_run(db, LISTING)
        labels = {
            (f.label, f.level)
            for f in staleness.run_all(db, now=datetime(2026, 9, 26, tzinfo=timezone.utc))
        }
        assert (COUNTY_AUDIT_LABEL, FAIL) in labels


class TestUntrustedCoverageMetadata:
    @pytest.mark.parametrize("bad", [[1], "broken", True, 42,
        {"oag_county_discovery": [1]},
        {"oag_county_discovery": {"listing_fiscal_years": "2024/2025"}},
        {"oag_county_discovery": {"listing_fiscal_years": [None]}},
        {"oag_county_discovery": {"listing_fiscal_years": ["2024/2030"]}},
        {"oag_county_discovery": {"listing_fiscal_years": LISTING}, "county_volumes": [1]},
    ])
    def test_malformed_latest_run_is_not_healthy(self, db, bad):
        from models import IngestionJob

        for year in (2022, 2023, 2024, 2025):
            _findings(db, year, _counties(db))
        _audits_run(db, LISTING, when=datetime(2026, 9, 25))
        _audits_run(db, LISTING)
        db.query(IngestionJob).order_by(IngestionJob.id.desc()).first().meta = bad
        db.flush()
        assert any(f.level != OK for f in check_county_audit_coverage(db))

    def test_executive_findings_cannot_stand_in_for_assemblies(self, db):
        _findings(db, 2025, _counties(db), roles=("executives",))
        _audits_run(db, ["2024/2025"], volumes={"discovered": 1, "deferred": [], "failed": []})
        assert any(f.level != OK for f in check_county_audit_coverage(db))

    def test_partial_extraction_is_not_a_complete_volume(self, db):
        from models import IngestionJob

        _findings(db, 2025, _counties(db))
        _audits_run(db, ["2024/2025"], volumes={"discovered": 2, "deferred": [], "failed": []})
        job = db.query(IngestionJob).one()
        job.meta = {**job.meta, "documents": [{"extractions": {"partial": True}}]}
        db.flush()
        assert any(f.level != OK for f in check_county_audit_coverage(db))


@pytest.mark.parametrize("bad", [[1], "broken", 17, True,
    {"source_mode": ["live"]}, {"source_mode": "refused", "source_fallback_reason": ["why"]}])
def test_full_validation_reaches_county_gate_with_malformed_job_metadata(db, bad):
    from models import IngestionJob

    _audits_run(db, LISTING)
    db.query(IngestionJob).one().meta = bad
    db.flush()
    findings = staleness.run_all(db, now=datetime(2026, 9, 26, tzinfo=timezone.utc))
    assert any(f.label == COUNTY_AUDIT_LABEL and f.level != OK for f in findings)
    assert not any(f.label == "audits ingestion" and f.level == OK for f in findings)
