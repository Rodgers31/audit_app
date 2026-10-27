"""UTC identities must survive the actual operations projection and API."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from models import IngestionStatus
from routers.admin import IngestionJobResponse
from routers.admin_operations import job_projection
from test_admin_operations_lane import AUTH, operations, seed


def observation(**changes):
    values=dict(id=1,domain='imf_weo',status=IngestionStatus.COMPLETED,dry_run=False,
        started_at=datetime(2026,10,27,4,38,48),finished_at=datetime(2026,10,27,4,39,18),
        created_at=datetime(2026,10,27,4,38,47),items_processed=188,items_created=0,items_updated=0)
    values.update(changes)
    return SimpleNamespace(**values)


def serialized(job):
    return IngestionJobResponse(**job_projection(job,error_count=0)).model_dump(mode='json')


def test_known_utc_naive_fields_are_explicit_and_duration_unchanged():
    result=serialized(observation())
    assert result['started_at']=='2026-10-27T04:38:48Z'
    assert result['finished_at']=='2026-10-27T04:39:18Z'
    assert result['created_at']=='2026-10-27T04:38:47Z'
    assert result['duration_seconds']==30


def test_aware_offsets_preserve_the_instant_and_mixed_duration():
    result=serialized(observation(started_at=datetime(2026,10,27,10,8,48,
        tzinfo=timezone(timedelta(hours=5,minutes=30)))))
    assert result['started_at']=='2026-10-27T04:38:48Z'
    assert result['duration_seconds']==30


def test_pending_unknown_timestamps_remain_unknown():
    result=serialized(observation(status=IngestionStatus.PENDING,started_at=None,
        finished_at=None,created_at=None))
    assert result['started_at'] is result['finished_at'] is result['created_at'] is None
    assert result['duration_seconds'] is None


@pytest.mark.parametrize('invalid',[False,0,1,'2026-10-27T04:38:48',[],{}])
def test_response_does_not_invent_instants_from_malformed_storage(invalid):
    fields=job_projection(observation(status=IngestionStatus.PENDING),error_count=0)
    fields['created_at']=invalid
    with pytest.raises((ValueError,TypeError,ValidationError)):
        IngestionJobResponse(**fields)


def test_actual_list_and_detail_have_identical_utc_instants(operations):
    client,factory,_=operations
    job_id=seed(factory,started_at=datetime(2026,10,27,4,38,48),
        finished_at=datetime(2026,10,27,4,39,18),created_at=datetime(2026,10,27,4,38,47))
    listing=client.get('/api/v1/admin/ingestion-jobs?days=365',headers=AUTH)
    detail=client.get(f'/api/v1/admin/ingestion-jobs/{job_id}',headers=AUTH)
    assert listing.status_code==detail.status_code==200
    selected=next(j for j in listing.json()['jobs'] if j['id']==job_id)
    for field,expected in [('started_at','2026-10-27T04:38:48Z'),
        ('finished_at','2026-10-27T04:39:18Z'),('created_at','2026-10-27T04:38:47Z')]:
        assert selected[field]==detail.json()[field]==expected
    assert selected['duration_seconds']==detail.json()['duration_seconds']==30
    assert 'no-store' in listing.headers['cache-control'] and 'no-store' in detail.headers['cache-control']
