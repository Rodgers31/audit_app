from http.client import HTTPConnection
from urllib.parse import urlsplit
import pytest
from scripts.social_media_browser_fixture import browser_fixture, image_bytes, MAX_REQUESTS

def raw_request(origin,method,path,headers,body=b''):
    p=urlsplit(origin)
    conn=HTTPConnection(p.hostname,p.port,timeout=3)
    try:
        conn.putrequest(method,path)
        for name,value in headers: conn.putheader(name,value)
        conn.endheaders(body)
        r=conn.getresponse()
        return r.status,r.read()
    finally: conn.close()

@pytest.mark.parametrize('duplicate', ['Origin','Access-Control-Request-Headers','Access-Control-Request-Method'])
def test_preflight_refuses_duplicate_origin_or_request_header_fields(duplicate):
    with browser_fixture() as (origins,objects,obs):
        headers=[('Origin',origins['app']),('Access-Control-Request-Method','PUT'),('Access-Control-Request-Headers','content-type, if-none-match')]
        value={'Origin':'https://foreign.invalid','Access-Control-Request-Headers':'*','Access-Control-Request-Method':'DELETE'}[duplicate]
        headers.append((duplicate,value))
        status,_=raw_request(origins['objects'],'OPTIONS','/png?fixture_grant=controlled',headers)
        assert status==403
        assert objects=={}

def test_put_refuses_duplicate_origin():
    with browser_fixture() as (origins,objects,obs):
        body=image_bytes('PNG')
        headers=[('Origin',origins['app']),('Origin','https://foreign.invalid'),('Content-Type','image/png'),('If-None-Match','*'),('Content-Length',str(len(body)))]
        status,_=raw_request(origins['objects'],'PUT','/png?fixture_grant=controlled',headers,body)
        assert status==403
        assert objects=={}

def test_request_cap_counts_unsupported_methods_before_any_put():
    with browser_fixture() as (origins,objects,obs):
        for _ in range(MAX_REQUESTS): raw_request(origins['objects'],'HEAD','/png',[])
        body=image_bytes('PNG')
        headers=[('Content-Type','image/png'),('If-None-Match','*'),('Content-Length',str(len(body)))]
        status,_=raw_request(origins['objects'],'PUT','/png?fixture_grant=controlled',headers,body)
        assert status==429
        assert objects=={}
