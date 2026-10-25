"""Registration/replay cannot manufacture source-acquisition evidence."""
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from harness import budget_records, seed_country
from models import BudgetLine, DocumentStatus, DocumentType, SourceDocument
from seeding.config import SeedingSettings
from seeding.domains.national_budget.writer import persist_national_budget_records
from seeding.types import DomainRunContext


def records():
    # Two records exercise both initial lookup and the invocation-local cache.
    return [replace(r, source_url='https://cob.go.ke/fixture-registration-only.pdf')
            for r in budget_records(2)]


def snapshot(source):
    return {c.key: getattr(source, 'meta' if c.key == 'metadata' else c.key)
            for c in SourceDocument.__table__.columns}


@pytest.mark.parametrize('status', list(DocumentStatus))
@pytest.mark.parametrize('verified', [False, True])
def test_fixture_registration_preserves_existing_source(pg_fixture, status, verified):
    engine, _ = pg_fixture
    country_id, _ = seed_country(engine)
    values = records()
    old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with Session(engine) as db:
        source = SourceDocument(country_id=country_id, publisher='Existing publisher',
            title='Existing acquisition', url=values[0].source_url,
            doc_type=DocumentType.REPORT, status=status, fetch_date=old,
            last_seen_at=old, last_verified_at=old if verified else None,
            md5='a'*32 if verified else None, http_status=200 if verified else None,
            content_type='application/pdf' if verified else None,
            file_path='/retained/original.pdf' if verified else None,
            meta={'acquisition': 'preserve', 'nested': {'value': 1}})
        db.add(source)
        db.commit()
        before = snapshot(source)
        identity = source.id
    with Session(engine) as db:
        result = persist_national_budget_records(db, values, SeedingSettings(),
            DomainRunContext(since=None, dry_run=False))
        assert not result.errors and result.created == 2
        db.commit()
    with Session(engine) as db:
        assert snapshot(db.get(SourceDocument, identity)) == before
        assert db.query(BudgetLine).count() == 2


def test_new_fixture_registration_is_unfetched_and_replay_preserves_it(pg_fixture):
    engine, _ = pg_fixture
    seed_country(engine)
    values = records()
    with Session(engine) as db:
        result = persist_national_budget_records(db, values, SeedingSettings(),
            DomainRunContext(since=None, dry_run=False))
        assert not result.errors and result.created == 2
        db.commit()
        source = db.scalar(select(SourceDocument))
        assert source.status == DocumentStatus.FAILED
        assert source.md5 is source.http_status is source.last_verified_at is None
        before = snapshot(source)
    with Session(engine) as db:
        result = persist_national_budget_records(db, values, SeedingSettings(),
            DomainRunContext(since=None, dry_run=False))
        assert not result.errors and result.created == result.updated == 0
        db.commit()
    with Session(engine) as db:
        assert snapshot(db.scalar(select(SourceDocument))) == before
        assert db.query(BudgetLine).count() == 2
