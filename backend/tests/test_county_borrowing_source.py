"""Fail-closed transport, parsing and selection boundaries, no network."""
import pytest
from pydantic import ValidationError
from seeding import county_borrowing_contract as source
from seeding.config import SeedingSettings
from seeding.source_plan import build_plan,DAILY,LEGACY_DOMAINS


@pytest.mark.parametrize('flag',[1,0,'1','True','TRUE','yes',None,{},[]])
def test_literal_opt_in_only(flag):
    with pytest.raises(ValidationError):SeedingSettings(_env_file=None,county_borrowing_ingestion_enabled=flag)


@pytest.mark.parametrize('body',[None,b'',b'%PDF-invalid\n%%EOF',True,{},b'x'*100])
def test_unknown_missing_malformed_or_changed_edition_refuses(body):
    with pytest.raises(source.CountyBorrowingRefused):source.parse_publication('treasury_guaranteed_stock_2025',body)


def test_arbitrary_source_url_is_never_transport_input():
    with pytest.raises(source.CountyBorrowingRefused):source.fetch_publication('http://127.0.0.1/secret')


def test_opt_in_plan_keeps_daily_frozen_and_allows_explicit_manual_domain():
    args=dict(domain='',dry_run='false',cra='false',opendata='false',discovery='false')
    assert build_plan(event='schedule',schedule=DAILY,county_borrowing='true',**args).domains==LEGACY_DOMAINS
    args['domain']='county_borrowing'
    with pytest.raises(ValueError,match='opt-in'):build_plan(event='workflow_dispatch',schedule='',**args)
    assert build_plan(event='workflow_dispatch',schedule='',county_borrowing='true',**args).domains==('county_borrowing',)

import httpx
from test_county_borrowing_producer import specimen  # noqa: F401


def test_transport_executes_the_reviewed_request_and_releases_the_response(specimen,monkeypatch):
    spec,body,_=specimen
    client_type=httpx.Client
    calls=[]
    responses=[]
    def respond(request):
        calls.append(request)
        response=httpx.Response(200,headers={'content-type':'application/pdf'},stream=httpx.ByteStream(body))
        responses.append(response)
        return response
    def client(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        assert kwargs['timeout']==15
        return client_type(**kwargs,transport=httpx.MockTransport(respond))
    monkeypatch.setattr(source.httpx,'Client',client)
    payload,stamp=source.fetch_publication(spec['id'])
    assert payload==body and stamp.utcoffset() is not None
    assert len(calls)==1 and str(calls[0].url)==spec['url']
    assert calls[0].method=='GET' and 'authorization' not in calls[0].headers
    assert calls[0].headers['accept-encoding']=='identity'
    assert responses[0].is_closed
    assert source.parse_publication(spec['id'],payload)['artifact_sha256']==spec['sha256']


@pytest.mark.parametrize('failure',['redirect','http_error','wrong_mime','oversized','timeout'])
def test_transport_refuses_hostile_responses_without_retry_or_follow(specimen,monkeypatch,failure):
    spec,body,_=specimen
    client_type=httpx.Client
    calls=[]
    responses=[]
    def respond(request):
        calls.append(request)
        status=302 if failure=='redirect' else 500 if failure=='http_error' else 200
        response=httpx.Response(status,headers={
            'content-type':'text/html' if failure=='wrong_mime' else 'application/pdf',
            'location':'http://127.0.0.1/private'},stream=httpx.ByteStream(body+b'x' if failure=='oversized' else body))
        responses.append(response)
        return response
    monkeypatch.setattr(source.httpx,'Client',lambda **kwargs:client_type(**kwargs,transport=httpx.MockTransport(respond)))
    if failure=='timeout':
        ticks=iter([0])
        monkeypatch.setattr(source.time,'monotonic',lambda:next(ticks,source.MAX_SECONDS+1))
    with pytest.raises(source.CountyBorrowingRefused):source.fetch_publication(spec['id'])
    assert len(calls)==1 and str(calls[0].url)==spec['url']
    assert responses[0].is_closed
"""No-sleep fragmented-stream deadline control. Uses only MockTransport."""
import pytest
import httpx
from test_county_borrowing_producer import specimen
from seeding import county_borrowing_contract as source


def test_fragmented_stream_checks_deadline_before_full_64k_chunk(specimen,monkeypatch):
    spec,_,_=specimen
    clock={'elapsed':0,'chunks':0,'closed':False}
    class Fragmented(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(16):
                clock['elapsed']+=10
                clock['chunks']+=1
                yield b'x'
        def close(self):clock['closed']=True
    client_type=httpx.Client
    def respond(request):return httpx.Response(200,headers={'content-type':'application/pdf'},stream=Fragmented())
    monkeypatch.setattr(source.httpx,'Client',lambda **kwargs:client_type(**kwargs,transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(source.time,'monotonic',lambda:clock['elapsed'])
    with pytest.raises(source.CountyBorrowingRefused,match='time bound'):
        source.fetch_publication(spec['id'])
    print('FRAGMENTED_STREAM_DEADLINE',clock,flush=True)
    assert clock['closed'] is True
    assert clock['chunks']<=7, '60-second deadline was not checked as each transport fragment arrived'


def test_encoded_response_refuses_before_any_decompression(specimen,monkeypatch):
    import gzip
    spec,body,_=specimen
    client_type=httpx.Client
    def respond(request):
        return httpx.Response(200,headers={'content-type':'application/pdf','content-encoding':'gzip'},
                              stream=httpx.ByteStream(gzip.compress(body)))
    monkeypatch.setattr(source.httpx,'Client',lambda **kwargs:client_type(**kwargs,transport=httpx.MockTransport(respond)))
    with pytest.raises(source.CountyBorrowingRefused):source.fetch_publication(spec['id'])


def test_deadline_is_rechecked_when_the_stream_finishes_without_another_fragment(specimen,monkeypatch):
    """An EOF/close wait can exceed the budget after the last body fragment."""
    spec,body,_=specimen
    clock={'elapsed':0,'closed':False}
    class LateEnd(httpx.SyncByteStream):
        def __iter__(self):
            yield body
            clock['elapsed']=source.MAX_SECONDS+1
        def close(self):clock['closed']=True
    client_type=httpx.Client
    def respond(request):
        return httpx.Response(200,headers={'content-type':'application/pdf'},stream=LateEnd())
    monkeypatch.setattr(source.httpx,'Client',lambda **kwargs:client_type(**kwargs,transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(source.time,'monotonic',lambda:clock['elapsed'])
    with pytest.raises(source.CountyBorrowingRefused,match='time bound'):
        source.fetch_publication(spec['id'])
    assert clock['closed'] is True
