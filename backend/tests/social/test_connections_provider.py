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
    provider=MetaProvider(config,transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=stream)))
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
    provider=MetaProvider(config,transport=httpx.MockTransport(wrong_identity))
    with pytest.raises(SocialError,match='PROVIDER_RESPONSE_INVALID'):provider.discover('fake-code',REDIRECT)
    def repeated(request):
        if request.url.path=='/v26.0/me/accounts':return httpx.Response(200,json={'data':[],'paging':{'next':'https://attacker.example','cursors':{'after':'repeat'}}})
        return original(request)
    provider=MetaProvider(config,transport=httpx.MockTransport(repeated))
    with pytest.raises(SocialError,match='PROVIDER_RESPONSE_INVALID'):provider.discover('fake-code',REDIRECT)

def test_granular_asset_permissions_do_not_authorize_other_page(config,graph):
    original=graph.__call__
    def restricted(request):
        response=original(request)
        if request.url.path=='/v26.0/debug_token' and request.url.params['input_token']==USER:
            body=response.json();body['data']['granular_scopes']=[{'scope':'pages_manage_posts','target_ids':['902']},{'scope':'instagram_content_publish','target_ids':['801']}]
            return httpx.Response(200,json=body)
        return response
    provider=MetaProvider(config,transport=httpx.MockTransport(restricted))
    grant=provider.discover('fake-code',REDIRECT)
    assert not grant['choices'][0]['page_eligible']
    assert grant['choices'][0]['missing_page_scopes']==['pages_manage_posts']
    assert grant['choices'][0]['instagram_eligible'] is True

@pytest.mark.parametrize('payload',[[],None,{'data':None},{'data':{'is_valid':'true','app_id':'123','type':'USER','scopes':list(SCOPES),'user_id':'701'}}])
def test_malformed_debug_proof_never_certifies_valid_grant(config,payload):
    provider=MetaProvider(config,transport=httpx.MockTransport(lambda request:httpx.Response(200,json=payload)))
    with pytest.raises(SocialError):provider.inspect_token(USER,expected_type='USER')

def test_facebook_login_uses_actual_linked_iguser_fields_not_instagram_login_type(config,graph):
    provider=MetaProvider(config,transport=httpx.MockTransport(graph))
    grant=provider.discover('fake-code',REDIRECT)
    assert grant['choices'][0]['instagram']['professional_proof']=='facebook_page_instagram_business_account'
    ig_reads=[r for r in graph.calls if r.url.path=='/v26.0/801']
    assert len(ig_reads)==1 and ig_reads[0].url.params['fields']=='id,username,name'

def test_client_hooks_and_response_urls_never_observe_debug_secret(config,graph):
    provider=MetaProvider(config,transport=httpx.MockTransport(graph))
    observed=[]
    provider.client.event_hooks['request']=[lambda request:observed.append(str(request.url))]
    provider.client.event_hooks['response']=[lambda response:observed.append(str(response.request.url))]
    provider.discover('fake-code',REDIRECT)
    assert observed and all(USER not in url and PAGE not in url and 'input_token=' not in url and 'appsecret_proof=' not in url for url in observed)
    assert any(request.url.params.get('input_token')==USER for request in graph.calls)  # Real wire shape is preserved.


def test_actual_sentry_httpx_tracing_does_not_capture_secret_queries():
    import subprocess,sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[3]
    result=subprocess.run([sys.executable,'-c','''
import json
import httpx
import sentry_sdk
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.transport import Transport
from cryptography.fernet import Fernet
from social.connections.config import MetaConfig
from social.connections.provider import MetaProvider
sent=[]
class MemoryTransport(Transport):
    def capture_envelope(self,envelope):
        event=envelope.get_transaction_event()
        if event is not None:sent.append(event)
sentry_sdk.init(dsn="https://fake@example.test/1",transport=MemoryTransport(),integrations=[HttpxIntegration()],default_integrations=False,auto_enabling_integrations=False,traces_sample_rate=1.0)
config=MetaConfig(enabled=True,app_configuration_validated=True,app_id="123",app_secret="fake-sensitive-app-secret",redirect_uris=("https://admin.example.test/admin/social/accounts/callback",),access_mode="owned_standard",active_key_version="v1",encryption_keys={"v1":Fernet.generate_key().decode()})
def fake(request):
    assert request.url.params["input_token"]=="fake-sensitive-debug-token"
    return httpx.Response(200,json={"data":{"app_id":"123","type":"USER","user_id":"701","is_valid":True,"scopes":["pages_show_list"],"expires_at":0}})
# Prove this installed integration captures the ordinary HTTPX query: the
# control is entirely fake and this subprocess has no remote Sentry transport.
with sentry_sdk.start_transaction(name="unsafe_control"):
    with httpx.Client(transport=httpx.MockTransport(fake)) as client:
        client.get("https://graph.facebook.com/v26.0/debug_token",params={"input_token":"fake-sensitive-debug-token"})
assert len(sent)==1 and "fake-sensitive-debug-token" in json.dumps(sent.pop())
with sentry_sdk.start_transaction(name="fake_meta_connection"):
    provider=MetaProvider(config,transport=httpx.MockTransport(fake))
    provider.inspect_token("fake-sensitive-debug-token",expected_type="USER")
    provider.close()
sentry_sdk.flush()
serialized=json.dumps(sent)
assert len(sent)==1 and "debug_token" in serialized and sent[0]["spans"]
assert "fake-sensitive-debug-token" not in serialized
assert "fake-sensitive-app-secret" not in serialized
assert "input_token" not in serialized
print("secret-free tracing verified")
'''],cwd=root,text=True,capture_output=True)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='secret-free tracing verified'
