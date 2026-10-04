"""Summary transfers aggregates, never job diagnostics or evidence bodies."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from models import IngestionJob, IngestionStatus


def seed_jobs(engine):
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        for i in range(100):
            db.add(IngestionJob(domain=('national_budget','revenue_by_source')[i%2],
                status=list(IngestionStatus)[i%5],dry_run=bool(i%2),
                items_processed=i,items_created=i//2,items_updated=i//3,
                errors=['PRIVATE_BODY_'+('x'*32768)],meta={'evidence':'PRIVATE_METADATA_'+('y'*32768)},
                created_at=now-timedelta(days=1 if i<80 else 40)))
        db.commit()


def expected_stats(days):
    indexes = range(80 if days else 100)
    return {'total_jobs':len(indexes),
        **{s.value:sum(i%5==index for i in indexes) for index,s in enumerate(IngestionStatus)},
        'total_items_processed':sum(indexes),'total_items_created':sum(i//2 for i in indexes),
        'total_items_updated':sum(i//3 for i in indexes),
        'domains':{name:sum(i%2==index for i in indexes) for index,name in enumerate(('national_budget','revenue_by_source'))}}


@pytest.mark.parametrize('days',[30,None,0])
def test_stats_output_is_equivalent_while_selected_rows_and_bytes_are_bounded(pg_fixture,days):
    from routers.admin import get_ingestion_stats
    engine,probe = pg_fixture
    seed_jobs(engine)
    with Session(engine) as db:
        with probe.capture():
            result = asyncio.run(get_ingestion_stats(days=days,db=db))
    assert result.model_dump()==expected_stats(days)
    samples = probe.selected('ingestion_jobs')
    assert len(samples)==1
    assert sum(s.rows for s in samples)<=10
    assert sum(s.selected_value_bytes for s in samples)<4096
    assert not any('metadata' in s.columns or 'errors' in s.columns for s in samples)


def test_empty_and_future_only_stats_preserve_zero_semantics(pg_fixture):
    from routers.admin import get_ingestion_stats
    engine,_ = pg_fixture
    with Session(engine) as db:
        result=asyncio.run(get_ingestion_stats(days=30,db=db)).model_dump()
        assert result['total_jobs']==0 and result['domains']=={}
        assert all(value==0 for name,value in result.items() if name!='domains')
    seed_jobs(engine)
    with Session(engine) as db:
        result=asyncio.run(get_ingestion_stats(days=-1,db=db)).model_dump()
        assert result['total_jobs']==0 and result['domains']=={}


def test_summary_selected_byte_estimate_excludes_diagnostic_bodies(pg_fixture):
    from routers.admin import get_ingestion_stats
    engine,probe=pg_fixture
    seed_jobs(engine)
    with Session(engine) as db,probe.capture():
        asyncio.run(get_ingestion_stats(days=30,db=db))
    assert sum(s.selected_value_bytes for s in probe.selected('ingestion_jobs'))<4096
