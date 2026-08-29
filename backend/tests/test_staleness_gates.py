"""Freshness gates must FIRE — a check that cannot fail is not a check.

These gates replace row-count floors that passed every night for months
("[OK] Audit Records: 27 rows (expected >= 20)") while the underlying
tables had not gained a row in 6-11 weeks. Every test below is a positive
control: it constructs the exact condition the nightly missed and asserts
the gate reports FAIL.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from models import (
    Audit,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    FiscalPeriod,
    IngestionJob,
    IngestionStatus,
    Severity,
    SourceDocument,
)
from seeding.staleness import (
    FAIL,
    OK,
    WARN,
    check_ingestion_freshness,
    check_table_freshness,
)

NOW = datetime(2026, 8, 29, tzinfo=timezone.utc)


def _finding(findings, label):
    return next(f for f in findings if f.label == label)


class TestTableFreshness:
    def test_fires_on_a_frozen_table(self, db_session, seed_country):
        """THE defect: audits frozen far beyond the OAG publication cycle."""
        doc = SourceDocument(
            id=9001, country_id=seed_country.id, publisher="OAG",
            title="t", url="https://x/y.pdf",
            fetch_date=NOW - timedelta(days=500),
            doc_type=DocumentType.AUDIT, status=DocumentStatus.AVAILABLE,
        )
        ent = Entity(id=9001, country_id=seed_country.id,
                     type=EntityType.MINISTRY, canonical_name="M", slug="m-stale")
        per = FiscalPeriod(id=9001, country_id=seed_country.id, label="FY2019/20",
                           start_date=datetime(2019, 7, 1),
                           end_date=datetime(2020, 6, 30))
        db_session.add_all([doc, ent, per])
        db_session.flush()
        db_session.add(Audit(
            entity_id=ent.id, period_id=per.id, finding_text="old",
            severity=Severity.INFO, source_document_id=doc.id,
            created_at=NOW - timedelta(days=500),
        ))
        db_session.commit()

        f = _finding(check_table_freshness(db_session, now=NOW), "Audit findings")
        assert f.level == FAIL
        assert "500 days old" in f.message

    def test_passes_when_data_is_current(self, db_session, seed_country):
        doc = SourceDocument(
            id=9002, country_id=seed_country.id, publisher="OAG", title="t",
            url="https://x/y.pdf", fetch_date=NOW - timedelta(days=2),
            doc_type=DocumentType.AUDIT, status=DocumentStatus.AVAILABLE,
        )
        ent = Entity(id=9002, country_id=seed_country.id,
                     type=EntityType.MINISTRY, canonical_name="M2", slug="m2-fresh")
        per = FiscalPeriod(id=9002, country_id=seed_country.id, label="FY2024/25",
                           start_date=datetime(2024, 7, 1),
                           end_date=datetime(2025, 6, 30))
        db_session.add_all([doc, ent, per])
        db_session.flush()
        db_session.add(Audit(
            entity_id=ent.id, period_id=per.id, finding_text="new",
            severity=Severity.INFO, source_document_id=doc.id,
            created_at=NOW - timedelta(days=2),
        ))
        db_session.commit()

        assert _finding(
            check_table_freshness(db_session, now=NOW), "Audit findings"
        ).level == OK

    def test_empty_table_is_not_silently_ok(self, db_session, seed_country):
        f = _finding(check_table_freshness(db_session, now=NOW), "Audit findings")
        assert f.level == FAIL
        assert "EMPTY" in f.message


class TestIngestionFreshness:
    def _job(self, domain, days_ago, mode, reason=None):
        meta = {"source_mode": mode} if mode else {}
        if reason:
            meta["source_fallback_reason"] = reason
        return IngestionJob(
            domain=domain, status=IngestionStatus.COMPLETED, dry_run=False,
            started_at=(NOW - timedelta(days=days_ago)).replace(tzinfo=None),
            items_processed=20, items_created=0, items_updated=0,
            errors=[], meta=meta,
        )

    def test_fires_when_every_run_used_a_fixture(self, db_session):
        """THE defect: national_budget processed 20 rows a night from a
        git-tracked fixture, wrote nothing, and reported [OK]."""
        for d in (1, 2, 3):
            db_session.add(self._job("national_budget", d, "fixture",
                                     "live_fetch_failed"))
        db_session.commit()

        f = _finding(
            check_ingestion_freshness(db_session, now=NOW), "national_budget ingestion"
        )
        assert f.level == FAIL
        assert "FIXTURE" in f.message and "live_fetch_failed" in f.message

    def test_passes_when_publisher_was_reached(self, db_session):
        db_session.add(self._job("national_budget", 3, "fixture", "x"))
        db_session.add(self._job("national_budget", 1, "live"))
        db_session.commit()
        assert _finding(
            check_ingestion_freshness(db_session, now=NOW), "national_budget ingestion"
        ).level == OK

    def test_unrecorded_provenance_is_not_reported_healthy(self, db_session):
        """Absence of evidence must never render as OK — that is the exact
        false-green this module exists to eliminate."""
        db_session.add(self._job("legacy_domain", 1, None))
        db_session.commit()
        f = _finding(
            check_ingestion_freshness(db_session, now=NOW), "legacy_domain ingestion"
        )
        assert f.level == WARN
        assert "not confirmed healthy" in f.message

    def test_missing_domain_is_flagged(self, db_session):
        f = _finding(
            check_ingestion_freshness(db_session, now=NOW, domains=["ghost"]),
            "ghost ingestion",
        )
        assert f.level == WARN
        assert "no run recorded" in f.message
