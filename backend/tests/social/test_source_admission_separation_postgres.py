"""Source qualification is independent of financial draft generation.

Only the assigned disposable PostgreSQL fixture is used. Publisher-shaped
source bodies are synthetic; this is not production source adoption.
"""
from decimal import Decimal
import pytest
from sqlalchemy import select, func

from models import RevenueBySource
from social.models import SocialPost, SocialPublication
from social.generation.models import SourceCursor
from seeding.generation_dispatch import dispatch_committed_generation
from seeding.source_observations import read_revenue_financial_observation, SourceObservationUnavailable
from test_b83_generation_postgres import pg
from test_native_financial_changes_postgres import ingest_revenue


@pytest.mark.parametrize('admit,generate,qualified', [
    ('true', 'false', True),
    ('false', 'true', False),
    ('false', 'false', False),
    ('true', 'true', True),
])
def test_financial_generation_does_not_grant_source_admission(
    pg, tmp_path, monkeypatch, admit, generate, qualified,
):
    factory, _ = pg
    monkeypatch.setenv('SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED', admit)
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED', generate)
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'false')
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED', 'false')
    job, record = ingest_revenue(factory, tmp_path, monkeypatch)
    with factory() as db:
        row = db.get(RevenueBySource, record)
        assert row.amount_billion_kes == 560
        assert row.publishable is qualified
    if qualified:
        value = read_revenue_financial_observation(factory, record_id=record, ingestion_id=job)
        assert Decimal(value['facts'][0]['value']) == Decimal('560')
    else:
        with pytest.raises(SourceObservationUnavailable):
            read_revenue_financial_observation(factory, record_id=record, ingestion_id=job)
    assert dispatch_committed_generation(factory, domain='revenue_by_source', ingestion_id=job, dry_run=False) is None
    with factory() as db:
        for model in (SocialPost, SocialPublication, SourceCursor):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_source_only_admission_cannot_open_a_live_generation_hook(pg, tmp_path, monkeypatch):
    factory, _ = pg
    monkeypatch.setenv('SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED', 'true')
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED', 'false')
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'true')
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED', 'false')
    job, record = ingest_revenue(factory, tmp_path, monkeypatch)
    value = read_revenue_financial_observation(factory, record_id=record, ingestion_id=job)
    assert Decimal(value['facts'][0]['value']) == Decimal('560')
    result = dispatch_committed_generation(factory, domain='revenue_by_source', ingestion_id=job, dry_run=False)
    assert result['state'] == 'disabled' and result['reason'] == 'financial_environment_disabled'
    assert result['drafts_created'] == result['processed'] == 0
    with factory() as db:
        for model in (SocialPost, SocialPublication, SourceCursor):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_source_admission_cannot_turn_catalogue_date_into_financial_authority(pg, tmp_path, monkeypatch):
    from test_kra_catalogue_postgres import ingest
    from seeding.source_observations import read_revenue_report_observation
    factory, _ = pg
    monkeypatch.setenv('SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED', 'true')
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED', 'false')
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'false')
    job, report = ingest(factory, tmp_path)
    value = read_revenue_report_observation(factory, record_id=report, ingestion_id=job)
    assert value['report']['published_on'] is None
    assert value['report']['evidence_kind'] == 'publisher_catalogue'
    with factory() as db:
        rows = list(db.scalars(select(RevenueBySource)))
        assert rows and all(row.publishable is False for row in rows)
        records = [row.id for row in rows]
    for record in records:
        with pytest.raises(SourceObservationUnavailable):
            read_revenue_financial_observation(factory, record_id=record, ingestion_id=job)
