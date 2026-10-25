"""Inert actual ASGI transport and encrypted lifecycle. No provider network."""
import json
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit, urlencode
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from social.connections.api import router as admin_router, service
from social.connections.direct_api import router, callback_html
from social.connections.direct_callback import DirectCallback, callback_fields, fields
from social.connections.config import load_config
from social.connections.contracts import DirectStartCommand, DirectCompleteCommand, CompleteCommand
from social.connections.models import SocialOAuthFlow
from social.http_boundary import require_admin, get_db
from social.http_policy import SocialNoStoreMiddleware
from social.models import SocialCommandReceipt, SocialAuditEvent, SocialAccount
from social.service import SocialError
from test_connections_support import db, config, graph, svc, ACTOR, SESSION, BINDING, USER, PAGE, select_asset

ORIGIN = 'https://admin.example.test'
API = 'https://api.example.test'
CALLBACK = API + '/api/v1/social/oauth/meta/callback'
LAUNCH = API + '/api/v1/social/oauth/meta/launch'
ADMIN = '/api/v1/admin/social/connections/meta/direct'


def direct_config(config):
    return replace(config, direct_callback_enabled=True, admin_origin=ORIGIN,
        redirect_uris=(CALLBACK,), verified_callback_ingress_uris=(CALLBACK,))


def client(db, config, graph, *, actor=ACTOR, session_id=SESSION, admin=True):
    app = FastAPI()
    app.include_router(admin_router); app.include_router(router)
    app.add_middleware(SocialNoStoreMiddleware)
    def isolated():
        with Session(db.bind, expire_on_commit=False) as session:
            yield session
    def fake(db=Depends(get_db)):
        return svc(db, config, graph)
    app.dependency_overrides[get_db] = isolated
    app.dependency_overrides[service] = fake
    if admin:
        app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=str(actor), roles=['admin'], session_id=str(session_id))
    return TestClient(app, base_url=API, raise_server_exceptions=False)


def headers():
    return {'Origin': ORIGIN, 'Idempotency-Key': str(uuid4())}


def started(c):
    r = c.post(ADMIN + '/start', headers=headers(), json={'admin_origin': ORIGIN, 'reason': 'Inert connection'})
    assert r.status_code == 200, r.text
    v = r.json()
    assert set(v) == {'flow_id', 'launch_url', 'launch_token', 'expires_at'}
    return v


def launch(c, flow):
    r = c.post(flow['launch_url'], headers={'Origin': ORIGIN}, data={'flow_id': flow['flow_id'], 'launch_token': flow['launch_token']}, follow_redirects=False)
    assert r.status_code == 303, r.text
    assert r.headers['location'].startswith('https://www.facebook.com/v26.0/dialog/oauth?')
    assert 'Secure' in r.headers['set-cookie'] and 'HttpOnly' in r.headers['set-cookie'] and 'SameSite=lax' in r.headers['set-cookie'] and 'Domain=' not in r.headers['set-cookie']
    return parse_qs(urlsplit(r.headers['location']).query)['state'][0]


def stage(c, state, **params):
    return c.get(CALLBACK, params={'state': state, **params})


def finish(c, flow, key=None):
    return c.post(ADMIN + '/complete', headers=key or headers(), json={'flow_id': flow['flow_id']})


def test_success_encrypts_callback_and_exchanges_only_under_authenticated_session(db, config, graph):
    cfg = direct_config(config); c = client(db, cfg, graph)
    flow = started(c); state = launch(c, flow)
    r = stage(c, state, code='INERT-code')
    assert r.status_code == 200, r.text
    assert graph.calls == []
    assert all(secret not in r.text for secret in (state, 'INERT-code', flow['launch_token']))
    assert 'auditgava-meta-ready' in r.text and flow['flow_id'] in r.text
    assert ORIGIN in r.text and 'history.replaceState' in r.text
    saved = db.get(SocialOAuthFlow, UUID(flow['flow_id']))
    assert b'INERT-code' not in saved.encrypted_verifier
    value = svc(db, cfg, graph).cipher.decrypt(saved.id, 'oauth_start', saved.key_version, saved.encrypted_verifier)
    assert value == {'transport': 'direct-v1', 'admin_origin': ORIGIN, 'callback': {'code': 'INERT-code', 'denied': False}}
    db.rollback()
    assert finish(client(db, cfg, graph, session_id=uuid4()), flow).status_code == 409
    assert finish(client(db, cfg, graph, actor=uuid4()), flow).status_code == 409
    assert finish(client(db, cfg, graph, admin=False), flow).status_code in {401,403}
    assert graph.calls == []
    key = headers(); response = finish(c, flow, key)
    assert response.status_code == 200, response.text
    calls = len(graph.calls)
    assert finish(c, flow, key).json() == response.json() and len(graph.calls) == calls
    assert finish(c, flow).status_code == 409
    assert all(secret not in response.text for secret in (state, 'INERT-code', USER, PAGE, flow['launch_token']))
    # Exchange uses exactly the registered direct redirect; no publishing endpoints.
    assert CALLBACK.encode().replace(b':', b'%3A').replace(b'/', b'%2F') in graph.calls[0].content
    assert not any(r.url.host != 'graph.facebook.com' for r in graph.calls)
    assert db.scalar(select(SocialAccount.id)) is None
    receipts = json.dumps([r.response for r in db.scalars(select(SocialCommandReceipt))])
    audit = json.dumps([e.details for e in db.scalars(select(SocialAuditEvent))])
    assert all(secret not in receipts + audit for secret in (state, 'INERT-code', flow['launch_token'], USER, PAGE))
    db.rollback()
    selected = select_asset(svc(db, cfg, graph), UUID(flow['flow_id']))
    assert len(selected['accounts']) == 2 and all(a['publishing_enabled'] is False for a in selected['accounts'])


@pytest.mark.parametrize('case', ['unlaunched','wrong_cookie','wrong_origin','replay_launch','replay_callback','expired','privacy','wrong_host','held','pending'])
def test_rejections_never_exchange(db, config, graph, case):
    cfg = direct_config(config); c = client(db, cfg, graph); flow = started(c)
    if case == 'wrong_origin':
        r = c.post(LAUNCH, headers={'Origin':'https://evil.example'}, data={'flow_id':flow['flow_id'],'launch_token':flow['launch_token']})
    elif case == 'unlaunched':
        saved = db.get(SocialOAuthFlow, UUID(flow['flow_id']))
        state = svc(db, cfg, graph).cipher.decrypt(saved.id,'oauth_start',saved.key_version,saved.encrypted_verifier)['state']; db.rollback()
        r = stage(c,state,code='INERT')
    else:
        state = launch(c, flow)
        if case == 'replay_launch':
            r = c.post(LAUNCH,headers={'Origin':ORIGIN},data={'flow_id':flow['flow_id'],'launch_token':flow['launch_token']})
        elif case == 'pending':
            r = finish(c, flow)
        else:
            if case in {'expired','privacy'}:
                saved = db.get(SocialOAuthFlow,UUID(flow['flow_id']))
                if case == 'expired': saved.expires_at = svc(db,cfg,graph).base.now() - timedelta(seconds=1)
                else: saved.privacy_blocked_at = svc(db,cfg,graph).base.now()
                db.commit()
            if case == 'wrong_cookie': c.cookies.clear()
            if case == 'held': c = client(db,replace(cfg,verified_callback_ingress_uris=()),graph)
            if case == 'wrong_host': r = c.get('https://other.example.test/api/v1/social/oauth/meta/callback',params={'state':state,'code':'INERT'})
            else:
                r = stage(c,state,code='INERT')
                if case == 'replay_callback':
                    assert r.status_code == 200
                    r = stage(c,state,code='DIFFERENT-INERT')
    assert r.status_code in {409,422,503}, r.text
    assert graph.calls == []
    assert r.headers['cache-control'] == 'private, no-store' and r.headers['referrer-policy'] == 'no-referrer'


def test_denial_consumes_without_provider_or_error_reflection(db, config, graph):
    cfg = direct_config(config); c = client(db,cfg,graph); flow = started(c); state = launch(c,flow)
    r = stage(c,state,error='access_denied',error_reason='INERT-reason',error_description='<script>INERT</script>')
    assert r.status_code == 200 and 'INERT' not in r.text
    r = finish(c,flow)
    assert r.status_code == 409 and r.json()['detail']['code'] == 'OAUTH_DENIED'
    saved = db.get(SocialOAuthFlow,UUID(flow['flow_id']))
    assert saved.status == 'failed' and saved.encrypted_verifier is None
    assert graph.calls == []


@pytest.mark.parametrize('raw', [b'', b'code=a', b'state=a&code=x', b'state=' + b'a'*43 + b'&code=x&code=y', b'state=' + b'a'*43 + b'&code=x&%63ode=y', b'state='+b'a'*43+b'&code=x&error=denied', b'state='+b'a'*43+b'&access_token=INERT', b'state='+b'a'*43+b'&code=%ZZ', b'state='+b'a'*43+b'&code=%FF', b'state='+b'a'*43+b'&code=%00', b'state='+b'a'*43+b'&code='+b'x'*4097, b'x'*8193])
def test_ambiguous_or_malformed_queries_rejected(raw):
    with pytest.raises(SocialError): callback_fields(raw)


def test_encoded_success_and_no_html_reflection(db, config, graph):
    c = client(db,direct_config(config),graph); flow = started(c); state = launch(c,flow)
    r = c.get(CALLBACK + '?state=' + state + '&code=INERT%2B%2F%3F%26%3Cscript%3E')
    assert r.status_code == 200 and 'INERT' not in r.text
    assert finish(c,flow).status_code == 200


def test_provider_unknown_effect_is_not_retried(db,config,graph):
    cfg=direct_config(config)
    def failed(request):
        graph.calls.append(request)
        raise RuntimeError('INERT-secret-exception')
    c=client(db,cfg,failed); flow=started(c); state=launch(c,flow); assert stage(c,state,code='INERT-code').status_code==200
    first=finish(c,flow); second=finish(c,flow)
    assert first.status_code==500 and second.status_code==409 and len(graph.calls)==1
    assert 'INERT' not in first.text + second.text
    saved=db.get(SocialOAuthFlow,UUID(flow['flow_id'])); assert saved.status=='failed' and saved.encrypted_verifier is None


def test_unqualified_transport_cannot_start_or_resume_or_use_legacy_complete(db,config,graph):
    cfg=direct_config(config); c=client(db,cfg,graph); flow=started(c); state=launch(c,flow); assert stage(c,state,code='INERT').status_code==200
    blocked=client(db,replace(cfg,verified_callback_ingress_uris=()),graph)
    assert finish(blocked,flow).status_code==503
    legacy=c.post('/api/v1/admin/social/connections/meta/complete',headers=headers(),json={'state':state,'code':'INERT','redirect_uri':CALLBACK})
    assert legacy.status_code==422 and legacy.json()['detail']['code']=='DIRECT_CALLBACK_REQUIRED'
    assert graph.calls==[]


def test_safe_headers_cover_missing_routes_and_outer_failures(db,config,graph):
    c=client(db,direct_config(config),graph)
    for r in [c.get(CALLBACK), c.post(CALLBACK), c.get(CALLBACK+'/INERT-secret?code=INERT-secret')]:
        assert r.status_code in {404,405,409}
        assert r.headers['referrer-policy']=='no-referrer' and r.headers['cache-control']=='private, no-store'
        assert 'INERT-secret' not in r.text


@pytest.mark.parametrize('suffix', ['/', '//'])
@pytest.mark.parametrize('method', ['GET', 'POST', 'HEAD'])
def test_callback_slash_redirects_never_relay_query(db, config, graph, suffix, method):
    c = client(db, direct_config(config), graph)
    response = c.request(method, CALLBACK + suffix, params={'state': 'a' * 43, 'code': 'INERT-slash-code'}, follow_redirects=False)
    assert 'INERT-slash-code' not in response.headers.get('location', '')
    assert response.status_code == 409
    assert 'location' not in response.headers
    if method != 'HEAD':
        assert 'history.replaceState' in response.text and 'auditgava-meta-ready' not in response.text
    assert 'INERT' not in response.text
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['referrer-policy'] == 'no-referrer'
    assert graph.calls == []


@pytest.mark.parametrize('status', [201, 204, 302, 307, 308, 429])
def test_callback_outer_non_success_never_relays_query(status):
    async def early_response(scope, receive, send):
        await send({'type': 'http.response.start', 'status': status, 'headers': [(b'location', b'/callback?code=INERT-early-code&state=INERT-early-state')]})
        await send({'type': 'http.response.body', 'body': b'INERT-early-body'})
    c = TestClient(SocialNoStoreMiddleware(early_response), base_url=API)
    response = c.get(CALLBACK + '?code=INERT-early-code&state=INERT-early-state', follow_redirects=False)
    assert response.status_code == (status if status >= 400 else 409)
    assert 'location' not in response.headers
    assert 'history.replaceState' in response.text and 'auditgava-meta-ready' not in response.text
    assert 'INERT' not in response.text


def test_environment_defaults_do_not_admit_direct_transport():
    cfg=load_config({}); assert cfg.direct_callback_enabled is False
    with pytest.raises(SocialError): cfg.require_direct()
    assert load_config({'META_DIRECT_CALLBACK_ENABLED':'TRUE'}).direct_callback_enabled is None


def test_actual_security_stack_preserves_callback_script_hash(db,config,graph):
    from middleware.security import SecurityHeadersMiddleware
    from social.connections.api import service
    c=client(db,direct_config(config),graph)
    # The real global middleware rewrites CSP after the route has returned.
    c.app.user_middleware.insert(1, __import__('starlette.middleware',fromlist=['Middleware']).Middleware(SecurityHeadersMiddleware))
    flow=started(c); state=launch(c,flow); r=stage(c,state,code='INERT')
    assert r.status_code==200
    import re,base64,hashlib
    script=re.search(r'<script>(.*?)</script>',r.text).group(1)
    expected="'sha256-"+base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()+"'"
    assert expected in r.headers['content-security-policy']
    assert "default-src 'none'" in r.headers['content-security-policy']


def test_review_failure_callback_scrubs_history(db,config,graph):
    c=client(db,direct_config(config),graph)
    r=stage(c,'a'*43,code='INERT-missing-cookie')
    assert r.status_code==409 and 'history.replaceState' in r.text
    assert 'INERT' not in r.text and 'auditgava-meta-ready' not in r.text


def test_review_direct_mode_never_falls_back_to_legacy(db,config,graph):
    cfg=replace(config,direct_callback_enabled=True,admin_origin=ORIGIN)
    c=client(db,cfg,graph)
    r=c.post('/api/v1/admin/social/connections/meta/start',headers=headers(),json={'redirect_uri':config.redirect_uris[0],'reason':'Inert stale config'})
    assert r.status_code==503 and graph.calls==[]


def test_review_default_port_cannot_claim_available(config):
    for cfg in [replace(direct_config(config),admin_origin=ORIGIN+':443'), replace(direct_config(config),redirect_uris=(CALLBACK.replace('api.example.test','api.example.test:443'),),verified_callback_ingress_uris=(CALLBACK.replace('api.example.test','api.example.test:443'),))]:
        assert 'DIRECT_CALLBACK_CONFIGURATION_INVALID' in cfg.oauth_blockers()


def test_review_origin_change_invalidates_original_launch(db,config,graph):
    cfg=direct_config(config); c=client(db,cfg,graph); flow=started(c)
    changed=client(db,replace(cfg,admin_origin='https://different.example.test'),graph)
    r=changed.post(LAUNCH,headers={'Origin':'https://different.example.test'},data={'flow_id':flow['flow_id'],'launch_token':flow['launch_token']})
    assert r.status_code==409 and graph.calls==[]


def test_review_shared_exchange_seam_rejects_unclaimed_calls(db,config,graph):
    service=svc(db,direct_config(config),graph)
    with pytest.raises(SocialError):
        service.exchange_claimed(uuid4(),uuid4(),'wrong','complete',uuid4(),{},'INERT-unclaimed',CALLBACK,uuid4())
    assert graph.calls==[]


def test_review_receipt_replay_rechecks_exact_redirect(db,config,graph):
    cfg=direct_config(config);c=client(db,cfg,graph);flow=started(c);state=launch(c,flow);assert stage(c,state,code='INERT').status_code==200
    key=headers();assert finish(c,flow,key).status_code==200; n=len(graph.calls)
    other=CALLBACK.replace('api.example.test','other.example.test')
    changed=client(db,replace(cfg,redirect_uris=(other,),verified_callback_ingress_uris=(other,)),graph)
    assert finish(changed,flow,key).status_code==409 and len(graph.calls)==n


@pytest.mark.parametrize('payload',[{'code':None,'denied':False},{'code':True,'denied':False},{'code':'INERT','denied':0},{'code':'INERT','denied':False,'access_token':'INERT'},{'code':'x'*4097,'denied':False}])
def test_review_malformed_encrypted_payload_never_exchanges(db,config,graph,payload):
    cfg=direct_config(config);c=client(db,cfg,graph);flow=started(c);state=launch(c,flow);assert stage(c,state,code='INERT').status_code==200
    row=db.get(SocialOAuthFlow,UUID(flow['flow_id']));service=svc(db,cfg,graph)
    row.key_version,row.encrypted_verifier=service.cipher.encrypt(row.id,'oauth_start',{'transport':'direct-v1','admin_origin':ORIGIN,'callback':payload});db.commit()
    r=finish(c,flow)
    assert r.status_code==409 and graph.calls==[]


@pytest.mark.parametrize('host',['127.000.000.001','0x7f000001','2130706433','127.1'])
def test_review_noncanonical_numeric_origins_are_unavailable(config,host):
    cfg=replace(direct_config(config),admin_origin='https://'+host)
    assert 'DIRECT_CALLBACK_CONFIGURATION_INVALID' in cfg.oauth_blockers()
