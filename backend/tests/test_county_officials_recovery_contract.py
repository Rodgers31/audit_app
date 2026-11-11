"""Actual client→parser→ORM with inert official-origin response bodies."""
import copy
from datetime import datetime,timedelta,timezone
import httpx
import pytest
from models import SourceDocument
from seeding.config import SeedingSettings
from seeding.http_client import SeedingHttpClient
from seeding.extractors.cog_governors import SOURCE_URL,DEPUTIES_SOURCE_URL,KENYAN_COUNTIES
from seeding.types import DomainRunContext
from tests.test_county_officials_deputies import counties
from tests.test_cog_governors import page,_synthetic

ROSTER=page([(_synthetic(c),c) for c in KENYAN_COUNTIES])
DEPUTIES=page([(_synthetic(c).replace('Mwangi','Wanjiru'),c) for c in KENYAN_COUNTIES])

@pytest.mark.parametrize('failure',['dns','challenge','partial','duplicate','unknown','oversize','split_cards'])
def test_failed_governors_preserve_names_and_honest_last_good_age(db_session,counties,tmp_path,monkeypatch,failure):
    import seeding.domains.county_officials as domain
    stamp=(datetime.now(timezone.utc)-timedelta(days=10)).isoformat()
    for row in counties.values():row.meta={'governor':'Previous Name','governor_provenance':{'fetched_at':stamp},'deputy_governor':'Prior Deputy'}
    db_session.commit()
    before={name:copy.deepcopy(row.meta) for name,row in counties.items()}
    bodies={'challenge':'<html>Just a moment captcha</html>','partial':page([(_synthetic(c),c) for c in KENYAN_COUNTIES[:-1]]),'duplicate':ROSTER.replace('</body>','<div class="captions"><h3>Another Person</h3><p><strong>County:</strong> Nairobi</p></div></body>'),'unknown':ROSTER.replace('> Baringo<','> Renamed County<'),'oversize':'x'*(4*1024*1024+1),'split_cards':''.join(f'<div><h3>{_synthetic(c)}</h3></div><div><strong>County:</strong> {c}</div>' for c in KENYAN_COUNTIES)}
    def handler(request):
        if failure=='dns':raise httpx.ConnectError('[Errno -3] Temporary failure in name resolution')
        return httpx.Response(200,text=bodies[failure])
    settings=SeedingSettings(_env_file=None,storage_path=tmp_path,http_cache_enabled=False,rate_limit='1000/sec',max_retries=2,retry_backoff=.001)
    client=SeedingHttpClient(settings,client=httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(domain,'create_http_client',lambda _:client)
    result=domain.run(db_session,settings,DomainRunContext(None,False))
    assert result.errors and result.items_processed==result.items_updated==0
    db_session.commit()
    assert {name:row.meta for name,row in counties.items()}==before
    assert db_session.query(SourceDocument).count()==0
    status=result.metadata['source_status']
    assert status['state']=='unavailable' and status['fixture_used'] is False
    assert status['stored_governors_retained']==status['dated_stored_governors']==47
    assert status['oldest_age_seconds']>=10*86400


def test_dns_recovery_writes_exact47_and_both_response_receipts(db_session,counties,tmp_path,monkeypatch):
    import seeding.domains.county_officials as domain
    calls=[]
    def handler(request):
        calls.append(str(request.url))
        if len(calls)==1:raise httpx.ConnectError('temporary DNS failure')
        return httpx.Response(200,text=ROSTER if str(request.url)==SOURCE_URL else DEPUTIES)
    settings=SeedingSettings(_env_file=None,storage_path=tmp_path,http_cache_enabled=False,rate_limit='1000/sec',max_retries=2,retry_backoff=.001)
    client=SeedingHttpClient(settings,client=httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(domain,'create_http_client',lambda _:client)
    result=domain.run(db_session,settings,DomainRunContext(None,False));db_session.commit()
    assert result.items_processed==47 and not result.errors
    assert calls==[SOURCE_URL,SOURCE_URL,DEPUTIES_SOURCE_URL]
    docs={d.url:d for d in db_session.query(SourceDocument).all()}
    for url in (SOURCE_URL,DEPUTIES_SOURCE_URL):
        assert docs[url].meta['response_receipt']['request_url']==url
        assert docs[url].meta['response_receipt']['acquired_at']
    assert result.metadata['source_status']['state']=='live'


def test_case_variant_cannot_make_one_person_govern_two_counties():
    from seeding.extractors.cog_governors import parse_governors,GovernorsError
    pairs=[(_synthetic(c),c) for c in KENYAN_COUNTIES]
    pairs[0]=('Same Person',pairs[0][1]);pairs[1]=('SAME PERSON',pairs[1][1])
    with pytest.raises(GovernorsError,match='governor_of_two_counties'):
        parse_governors(page(pairs))
