"""Independent direct execution probes. No live publisher/network requests."""
import copy
from decimal import Decimal
import httpx, pytest
from seeding.config import SeedingSettings
from seeding.http_client import SeedingHttpClient, PdfDownloadError
from seeding.domains.debt_timeline.parser import DebtTimelineRecord,parse_debt_timeline_payload
from seeding.domains.debt_timeline.writer import write_debt_timeline_records
from test_refresh_review_debt import db
from models import DebtTimeline

URL='https://cog.go.ke/current-governors/'


def client(tmp_path, handler):
    settings=SeedingSettings(_env_file=None,storage_path=tmp_path,http_cache_enabled=False,rate_limit='1000/sec',max_retries=3,retry_backoff=.001)
    return SeedingHttpClient(settings,client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_completed_pdf_replay_obeys_byte_cap(tmp_path):
    part=tmp_path/'retained.part'
    part.write_bytes(b'%PDF-1.7\n'+b'a'*128+b'\n%%EOF\n')
    calls=[]
    def handler(req): calls.append(req);raise AssertionError('preexisting whole part needs no network')
    with client(tmp_path,handler) as c:
        from seeding.pdf_download import _looks_like_whole_pdf
        with pytest.raises(PdfDownloadError,match='byte'):
            c.download_to_file(URL,tmp_path/'out.pdf',resume_part=part,max_seconds=1,max_bytes=16,completion_check=_looks_like_whole_pdf)
    assert not (tmp_path/'out.pdf').exists()


@pytest.mark.parametrize('year',[True,False,0,-1,'2025',2025.5,10000])
def test_writer_direct_call_refuses_malformed_year(db,year):
    record=DebtTimelineRecord(year=year,external=Decimal('400'),domestic=Decimal('600'),total=Decimal('1000'),gdp=Decimal('2000'),gdp_ratio=Decimal('50'))
    with pytest.raises(ValueError):
        write_debt_timeline_records(db,[record],{})
    assert db.query(DebtTimeline).count()==0


@pytest.mark.parametrize('value',[None,{},[],True,float('nan'),float('inf'),-1,0])
def test_bounded_get_refuses_bad_direct_bounds(tmp_path,value):
    calls=[]
    def handler(req): calls.append(req);return httpx.Response(200,text='body')
    with client(tmp_path,handler) as c:
        with pytest.raises((ValueError,TypeError)):
            c._bounded_get(URL,max_seconds=value,max_bytes=1024,allowed_hosts={'cog.go.ke'})
    assert calls==[]


@pytest.mark.parametrize('payload',[None,{},[],{'timeline':[]},{'timeline':[True]},{'timeline':[{}]}])
def test_parser_bad_shapes(payload):
    with pytest.raises(ValueError): parse_debt_timeline_payload(payload)

"""Independent body/cache/pairing boundary attacks, all inert/local."""
import json,time
from pathlib import Path
import pytest
from seeding.extractors.cog_governors import parse_governors,GovernorsError,KENYAN_COUNTIES
from seeding.pdf_download import _fresh_cache_hit
from test_cog_governors import page,_synthetic


def test_cog_heading_outside_pair_block_cannot_replace_first_governor():
    roster=page([(_synthetic(county),county) for county in KENYAN_COUNTIES])
    malformed='<div><h3>H.E Fabricated Person</h3></div>'+roster
    try:
        result=parse_governors(malformed)
    except GovernorsError:
        return
    assert result.by_county[KENYAN_COUNTIES[0]]!='Fabricated Person'


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-float('inf'),True,'NaN'])
def test_pdf_cache_hostile_created_at_refuses(tmp_path,value):
    pdf=tmp_path/'owned.pdf';pdf.write_bytes(b'%PDF-1.7\nowned\n%%EOF\n')
    meta=tmp_path/'owned.json';meta.write_text(json.dumps({'created_at':value}))
    assert _fresh_cache_hit(pdf,meta,3600) is None


@pytest.mark.parametrize('data',[{},[],None,'garbage',{'created_at':time.time(),'sha256':'0'*64,'bytes':1}])
def test_pdf_cache_bad_metadata_refuses(tmp_path,data):
    pdf=tmp_path/'owned.pdf';pdf.write_bytes(b'%PDF-1.7\nowned\n%%EOF\n')
    meta=tmp_path/'owned.json';meta.write_text(json.dumps(data))
    assert _fresh_cache_hit(pdf,meta,3600) is None

"""Actual rate limiter contributes to bounded acquisition wall-clock."""
import time
import httpx,pytest
from seeding.rate_limiter import RateLimiter
from seeding.http_client import SeedingHttpClient
from seeding.config import SeedingSettings


def test_body_budget_bounds_actual_rate_limiter_wait(tmp_path):
    settings=SeedingSettings(_env_file=None,storage_path=tmp_path,http_cache_enabled=False,rate_limit='1000/sec',max_retries=1,retry_backoff=.001)
    limiter=RateLimiter(tokens=1,period_seconds=.25)
    limiter.acquire()
    with SeedingHttpClient(settings,rate_limiter=limiter,client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200,text='valid')))) as c:
        started=time.monotonic()
        with pytest.raises(httpx.TimeoutException):
            c._bounded_get('https://cog.go.ke/current-governors/',max_seconds=.01,max_bytes=1024,allowed_hosts={'cog.go.ke'})
        elapsed=time.monotonic()-started
    assert elapsed < .12, f'0.01s body budget took {elapsed:.3f}s waiting for actual RateLimiter'
