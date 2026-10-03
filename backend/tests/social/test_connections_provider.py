import httpx
import pytest
from social.connections.provider import MetaProvider,_expiry
from social.service import SocialError
from test_connections_support import *

class OversizedStream(httpx.SyncByteStream):
    def __init__(self): self.yields=0;self.closed=False
    def __iter__(self):
        for _ in range(200):
            self.yields+=1
            yield b'a'*16384
    def close(self): self.closed=True

def test_graph_stream_limit_stops_before_full_body_allocation(config):
    stream=OversizedStream()
    provider=MetaProvider(config,client=httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=stream))))
    with pytest.raises(SocialError,match='PROVIDER_RESPONSE_INVALID'):provider._request('GET','me')
    assert stream.closed and stream.yields < 65

@pytest.mark.parametrize('expiry',[True,False,-1,float('nan'),float('inf'),'never',10**100])
def test_expiry_metadata_rejects_hostile_numeric_values(expiry):
    with pytest.raises(SocialError,match='PROVIDER_RESPONSE_INVALID'):_expiry(expiry)

def test_page_token_identity_and_repeated_pagination_fail_closed(config,graph):
    original=graph.__call__
    def wrong_identity(request):
        if request.url.path=='/v26.0/me':return httpx.Response(200,json={'id':'999'})
        return original(request)
    provider=MetaProvider(config,client=httpx.Client(transport=httpx.MockTransport(wrong_identity)))
    with pytest.raises(SocialError,match='PROVIDER_RESPONSE_INVALID'):provider.discover('fake-code',REDIRECT)
    def repeated(request):
        if request.url.path=='/v26.0/me/accounts':return httpx.Response(200,json={'data':[],'paging':{'next':'https://attacker.example','cursors':{'after':'repeat'}}})
        return original(request)
    provider=MetaProvider(config,client=httpx.Client(transport=httpx.MockTransport(repeated)))
    with pytest.raises(SocialError,match='PROVIDER_RESPONSE_INVALID'):provider.discover('fake-code',REDIRECT)

def test_granular_asset_permissions_do_not_authorize_other_page(config,graph):
    original=graph.__call__
    def restricted(request):
        response=original(request)
        if request.url.path=='/v26.0/debug_token' and request.url.params['input_token']==USER:
            body=response.json();body['data']['granular_scopes']=[{'scope':'pages_manage_posts','target_ids':['902']},{'scope':'instagram_content_publish','target_ids':['801']}]
            return httpx.Response(200,json=body)
        return response
    provider=MetaProvider(config,client=httpx.Client(transport=httpx.MockTransport(restricted)))
    grant=provider.discover('fake-code',REDIRECT)
    assert not grant['choices'][0]['page_eligible']
    assert grant['choices'][0]['missing_page_scopes']==['pages_manage_posts']
    assert grant['choices'][0]['instagram_eligible'] is True

@pytest.mark.parametrize('payload',[[],None,{'data':None},{'data':{'is_valid':'true','app_id':'123','type':'USER','scopes':list(SCOPES),'user_id':'701'}}])
def test_malformed_debug_proof_never_certifies_valid_grant(config,payload):
    provider=MetaProvider(config,client=httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=payload))))
    with pytest.raises(SocialError):provider.inspect_token(USER,expected_type='USER')

def test_facebook_login_uses_actual_linked_iguser_fields_not_instagram_login_type(config,graph):
    provider=MetaProvider(config,client=httpx.Client(transport=httpx.MockTransport(graph)))
    grant=provider.discover('fake-code',REDIRECT)
    assert grant['choices'][0]['instagram']['professional_proof']=='facebook_page_instagram_business_account'
    ig_reads=[r for r in graph.calls if r.url.path=='/v26.0/801']
    assert len(ig_reads)==1 and ig_reads[0].url.params['fields']=='id,username,name'
