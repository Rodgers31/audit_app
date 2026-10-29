"""Read-only source navigation; synthetic cohorts never certify eligibility."""
import pytest
from social.generation.source_selection import source_records
from social.service import SocialError
from seeding import source_observations as adapter


def choose(**kw):
    return source_records(None, **dict(domain='pending_bills', ingestion_id=4,
                                       reports=False, page=1, **kw))


@pytest.mark.parametrize('field,value', [('ingestion_id',True),('ingestion_id',0),
    ('ingestion_id',2147483648),('reports',1),('page',True),('page',0),('page',41),('domain',None)])
def test_direct_calls_validate_bounds_before_reader(field,value):
    args=dict(domain='pending_bills',ingestion_id=4,reports=False,page=1);args[field]=value
    with pytest.raises(SocialError) as raised:
        source_records(None,**args)
    assert raised.value.code=='INVALID_SOURCE_SELECTION'


def test_pages_preserve_the_exact_bounded_cohort_without_writes(monkeypatch):
    calls=[]
    monkeypatch.setattr(adapter,'read_native_financial_record_ids',lambda factory,**kw:(calls.append(kw) or tuple(range(1,47))))
    first=choose();second=source_records(None,domain='pending_bills',ingestion_id=4,reports=False,page=2)
    assert first['record_ids']+second['record_ids']==list(range(1,47))
    assert first['has_more'] and not second['has_more']
    assert first['total']==second['total']==46 and len(calls)==2
    assert calls==[dict(ingestion_id=4,domain='pending_bills')]*2


@pytest.mark.parametrize('ids', [(1,1),(True,),tuple(range(1,1002)),(0,),[1],(2147483648,)])
def test_invalid_reader_results_never_become_candidates(monkeypatch,ids):
    monkeypatch.setattr(adapter,'read_native_financial_record_ids',lambda *a,**kw:ids)
    with pytest.raises(SocialError) as raised:choose()
    assert raised.value.code=='SOURCE_SELECTION_UNAVAILABLE'


def test_report_and_financial_ids_use_separate_existing_readers(monkeypatch):
    monkeypatch.setattr(adapter,'read_native_financial_record_ids',lambda *a,**kw:(1,))
    monkeypatch.setattr(adapter,'read_native_report_record_ids',lambda *a,**kw:(2,))
    assert choose()['record_ids']==[1]
    assert source_records(None,domain='pending_bills',ingestion_id=4,reports=True,page=1)['record_ids']==[2]
    with pytest.raises(SocialError):source_records(None,domain='opendata',ingestion_id=4,reports=False,page=1)


def test_stale_or_incomplete_lineage_refuses_without_guessing(monkeypatch):
    def refused(*a,**kw):raise adapter.SourceObservationUnavailable('Current report authority unavailable')
    monkeypatch.setattr(adapter,'read_native_financial_record_ids',refused)
    with pytest.raises(SocialError) as raised:choose()
    assert raised.value.code=='SOURCE_NOT_ELIGIBLE'


def test_operational_reader_failure_is_unavailable_not_an_eligibility_verdict(monkeypatch):
    def refused(*a,**kw):raise adapter.SourceObservationUnavailable('PostgreSQL committed snapshot required')
    monkeypatch.setattr(adapter,'read_native_financial_record_ids',refused)
    with pytest.raises(SocialError) as raised:choose()
    assert raised.value.code=='SOURCE_SELECTION_UNAVAILABLE'
    assert raised.value.status==503
