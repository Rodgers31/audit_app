"""Sanitized official-contract fixtures; no live provider calls or credentials."""
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from social.connections.contracts import StartCommand, CompleteCommand, AccountCommand
from social.connections.service import session_binding
from social.models import Base, SocialAccount, SocialAuditEvent, SocialCommandReceipt
from social.platform_connections.api import router, service as api_service
from social.platform_connections.config import ConnectionConfig
from social.platform_connections.contracts import ConfirmCommand
from social.platform_connections.models import PlatformCredential, PlatformOAuthFlow, SocialPlatformConnectionBudget
from social.platform_connections.provider import OAuthProvider, challenge
from social.platform_connections.service import PlatformConnectionService
from social.platform_budget import SocialPlatformBudget
from social.http_boundary import get_db, require_admin
from social.service import SocialError
from social.connections.service import digest

REDIRECT = 'https://admin.example.test/admin/social/accounts/callback'
ACTOR, SESSION = uuid4(), uuid4()
BINDING = session_binding(ACTOR, SESSION)
ACCESS = 'fake-access-grant-no-live-value'
REFRESH = 'fake-refresh-grant-no-live-value'


@pytest.fixture
def db():
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    @event.listens_for(engine, 'connect')
    def fk(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')
    tables = [table for table in Base.metadata.sorted_tables if table.name.startswith('social_')]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def config(platform='threads'):
    return ConnectionConfig(platform=platform, enabled=True, access_verified=True, client_id='123', client_secret='fake-client-secret', redirect_uris=(REDIRECT,), active_key_version='v1', encryption_keys={'v1': Fernet.generate_key().decode()}, connection_budget_microusd=100000)


class ProviderFixture:
    def __init__(self, db, platform):
        self.db, self.platform, self.calls = db, platform, []
        self.missing = False
        self.identity = '901'
        self.fail = False
        self.rotated = False
        self.debug_valid = True
        self.debug_app = '123'
    def __call__(self, request):
        # This assertion executes in the provider request, after durable consume.
        assert not self.db.in_transaction()
        self.calls.append(request)
        if self.fail:
            raise httpx.ReadTimeout('fake sensitive provider URL ' + ACCESS, request=request)
        if request.url.path == '/oauth/access_token' and request.method == 'GET':
            return httpx.Response(200, json={'access_token': 'fake-app-grant-not-live', 'token_type': 'bearer'})
        if request.url.path == '/oauth/access_token':
            return httpx.Response(200, json={'access_token': ACCESS, 'user_id': '901'})
        if request.url.path == '/debug_token':
            scopes = list(self.cfg.scopes)
            if self.missing: scopes.pop()
            return httpx.Response(200, json={'data': {'app_id': self.debug_app, 'type': 'USER', 'is_valid': self.debug_valid, 'user_id': self.identity, 'scopes': scopes, 'expires_at': int((datetime.now(timezone.utc) + timedelta(days=60)).timestamp()), 'data_access_expires_at': int((datetime.now(timezone.utc) + timedelta(days=90)).timestamp())}})
        if request.url.path in ('/access_token', '/refresh_access_token', '/2/oauth2/token'):
            scopes = list(self.cfg.scopes)
            if self.missing:
                scopes.pop()
            return httpx.Response(200, json={'access_token': ACCESS, 'token_type': 'bearer', 'expires_in': 5184000 if self.platform == 'threads' else 7200, 'refresh_token': REFRESH + ('-rotated' if self.rotated else ''), 'scope': ' '.join(scopes)})
        if request.url.path == '/v1.0/me/permissions':
            scopes = list(self.cfg.scopes)
            if self.missing:
                scopes.pop()
            return httpx.Response(200, json={'data': [{'permission': s, 'status': 'granted'} for s in scopes]})
        if request.url.path in ('/v1.0/me', '/2/users/me'):
            me = {'id': self.identity, 'username': 'auditgava', 'name': 'AuditGava'}
            return httpx.Response(200, json=me if self.platform == 'threads' else {'data': me})
        raise AssertionError(request.url.path)


def build(db, platform='threads', cfg=None, connection_budget=True):
    cfg = cfg or config(platform)
    fixture = ProviderFixture(db, platform)
    fixture.cfg = cfg
    if platform == 'x' and connection_budget:
        with db.begin():
            db.add(SocialPlatformConnectionBudget(client_key=digest('x:' + cfg.client_id), enabled=True, access_verified=True, limit_microusd=100000, reserved_microusd=0, version=1))
    svc = PlatformConnectionService(db, cfg, provider_factory=lambda c: OAuthProvider(c, transport=httpx.MockTransport(fixture), admission=svc.connection_admission))
    return svc, fixture


def start(svc, key=None):
    value = svc.start(ACTOR, BINDING, 'POST start', key or uuid4(), StartCommand(redirect_uri=svc.config.redirect_uris[0], reason='Connect the owned account'), uuid4())
    state = parse_qs(urlsplit(value['authorize_url']).query)['state'][0]
    return value, state


def complete(svc, state, key=None, actor=ACTOR, binding=BINDING, redirect=REDIRECT):
    return svc.complete(actor, binding, 'POST complete', key or uuid4(), CompleteCommand(code='fake-one-use-code', state=state, redirect_uri=redirect), uuid4())


def confirmed(svc):
    flow, state = start(svc)
    choice = complete(svc, state, redirect=svc.config.redirect_uris[0])
    return svc.confirm(UUID(flow['flow_id']), ACTOR, BINDING, 'POST confirm', uuid4(), ConfirmCommand(external_account_id=choice['external_account_id'], reason='Confirm observed owned identity'), uuid4())


@pytest.mark.parametrize('platform', ['threads', 'x'])
def test_full_durable_flow_no_secret_receipts_restart_and_pkce(db, platform):
    svc, graph = build(db, platform)
    start_key, complete_key = uuid4(), uuid4()
    flow, state = start(svc, start_key)
    assert start(svc, start_key)[0] == flow
    with db.begin():
        row = db.get(PlatformOAuthFlow, UUID(flow['flow_id']))
        secret = svc.cipher.decrypt(row.id, svc.purpose('start'), row.key_version, row.encrypted_secret)
        assert secret['state'] == state and secret['verifier'].encode() not in row.encrypted_secret
    if platform == 'x':
        query = parse_qs(urlsplit(flow['authorize_url']).query)
        assert query['code_challenge'] == [challenge(secret['verifier'])]
        assert query['code_challenge_method'] == ['S256']
    choice = complete(svc, state, complete_key)
    calls = len(graph.calls)
    # Fresh service instance replays the receipt, never the provider request.
    restarted = PlatformConnectionService(db, svc.config, provider_factory=lambda _: pytest.fail('unexpected provider replay'))
    assert complete(restarted, state, complete_key) == choice and len(graph.calls) == calls
    assert restarted.choice(UUID(flow['flow_id']), ACTOR, BINDING) == choice
    selected = svc.confirm(UUID(flow['flow_id']), ACTOR, BINDING, 'POST confirm', uuid4(), ConfirmCommand(external_account_id='901', reason='Confirm exact account'), uuid4())
    assert selected['account']['publishing_enabled'] is False
    account_id = UUID(selected['account']['id'])
    with db.begin():
        assert svc.material(account_id)['access_token'] == ACCESS
        assert db.get(SocialAccount, account_id).credential_id is None
        saved = json.dumps([r.response for r in db.scalars(select(SocialCommandReceipt))]) + json.dumps([r.details for r in db.scalars(select(SocialAuditEvent))])
        for secret_value in [ACCESS, REFRESH, state, secret['verifier'], 'fake-one-use-code']:
            assert secret_value not in saved
        assert db.get(PlatformOAuthFlow, UUID(flow['flow_id'])).encrypted_secret is None
    assert all(r.url.host == ('graph.threads.com' if platform == 'threads' else 'api.x.com') for r in graph.calls)
    if platform == 'x':
        exchanged = parse_qs(graph.calls[0].content.decode())
        assert exchanged['code_verifier'] == [secret['verifier']]


@pytest.mark.parametrize('platform', ['threads', 'x'])
@pytest.mark.parametrize('hostility', ['actor', 'session', 'expired', 'redirect', 'missing_permissions', 'identity', 'timeout'])
def test_reject_hostility_and_consume_before_http(db, platform, hostility):
    cfg = replace(config(platform), redirect_uris=(REDIRECT, 'https://other.example.test/admin/social/accounts/callback'))
    svc, graph = build(db, platform, cfg)
    flow, state = start(svc)
    kwargs = {}
    if hostility == 'actor': kwargs['actor'] = uuid4()
    if hostility == 'session': kwargs['binding'] = session_binding(ACTOR, uuid4())
    if hostility == 'redirect': kwargs['redirect'] = cfg.redirect_uris[1]
    if hostility == 'expired':
        with db.begin(): db.get(PlatformOAuthFlow, UUID(flow['flow_id'])).expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    if hostility == 'missing_permissions': graph.missing = True
    if hostility == 'identity': graph.identity = '902' if platform == 'threads' else '../evil'
    if hostility == 'timeout': graph.fail = True
    with pytest.raises(SocialError): complete(svc, state, **kwargs)
    if hostility in ('actor', 'session', 'expired', 'redirect'):
        assert graph.calls == []
    else:
        count = len(graph.calls)
        with pytest.raises(SocialError, match='OAUTH_STATE_USED'): complete(svc, state)
        assert len(graph.calls) == count
        with db.begin(): assert db.get(PlatformOAuthFlow, UUID(flow['flow_id'])).status == 'failed'


@pytest.mark.parametrize('gate', ['budget', 'access', 'disabled'])
def test_x_all_provider_entries_refuse_without_budget_access(db, gate):
    svc, graph = build(db, 'x')
    _, state = start(svc)
    changes = {'budget': {'connection_budget_microusd': 0}, 'access': {'access_verified': False}, 'disabled': {'enabled': False}}[gate]
    disabled = replace(svc.config, **changes)
    svc.config = disabled
    for operation in (lambda: start(svc), lambda: complete(svc, state), lambda: OAuthProvider(disabled, transport=httpx.MockTransport(graph))):
        with pytest.raises(SocialError, match='CONNECTIONS_UNAVAILABLE'): operation()
    assert graph.calls == []
    admitted = PlatformConnectionService(db, replace(disabled, enabled=True, access_verified=True, connection_budget_microusd=1))
    provider = OAuthProvider(admitted.config, transport=httpx.MockTransport(graph), admission=admitted.connection_admission)
    provider.config = disabled
    for operation in (lambda: provider.authorize_url('state', REDIRECT, 'v'), lambda: provider.exchange('code', REDIRECT, 'v'), lambda: provider.refresh({}), lambda: provider._request('GET', '/2/users/me')):
        with pytest.raises(SocialError, match='CONNECTIONS_UNAVAILABLE'): operation()
    provider.close()
    assert graph.calls == []


def test_tiktok_unavailable_even_accidental_enabled_configuration(db):
    svc, graph = build(db, 'tiktok', config('tiktok'))
    assert svc.status()['blockers'] == ['PRODUCT_ACCESS_UNAVAILABLE']
    with pytest.raises(SocialError, match='CONNECTIONS_UNAVAILABLE'): start(svc)
    assert graph.calls == []


@pytest.mark.parametrize('defect', ['wrong_app', 'revoked'])
def test_threads_debug_token_rejects_wrong_application_or_revocation(db, defect):
    svc, graph = build(db)
    _, state = start(svc)
    if defect == 'wrong_app': graph.debug_app = '999'
    else: graph.debug_valid = False
    with pytest.raises(SocialError, match='GRANT_REVOKED'):
        complete(svc, state)


@pytest.mark.parametrize('platform', ['threads', 'x'])
def test_refresh_rotation_eligibility_and_sticky_unknown_outcome(db, platform):
    svc, graph = build(db, platform)
    selected = confirmed(svc)
    account_id = UUID(selected['account']['id'])
    credential_id = UUID(selected['credential_id'])
    body = AccountCommand(expected_credential_id=credential_id, expected_credential_version=1, reason='Renew owned grant')
    if platform == 'threads':
        with pytest.raises(SocialError, match='REFRESH_INELIGIBLE'):
            svc.refresh(account_id, ACTOR, BINDING, 'POST refresh', uuid4(), body, uuid4())
        with db.begin():
            row = db.get(PlatformCredential, credential_id)
            grant = svc.cipher.decrypt(row.id, svc.purpose('credential'), row.key_version, row.encrypted_bundle)
            grant['issued_at'] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
            row.issued_at = datetime.fromisoformat(grant['issued_at'])
            row.key_version, row.encrypted_bundle = svc.cipher.encrypt(row.id, svc.purpose('credential'), grant)
    graph.rotated = True
    key = uuid4()
    result = svc.refresh(account_id, ACTOR, BINDING, 'POST refresh', key, body, uuid4())
    assert result['credential_version'] == 2 and result['refresh_pending'] is False
    count = len(graph.calls)
    assert svc.refresh(account_id, ACTOR, BINDING, 'POST refresh', key, body, uuid4()) == result
    assert len(graph.calls) == count
    if platform == 'x':
        with db.begin(): assert svc.material(account_id)['refresh_token'] == REFRESH + '-rotated'
        graph.fail = True
        body = body.model_copy(update={'expected_credential_version': 2})
        with pytest.raises(SocialError, match='PROVIDER_UNAVAILABLE'):
            svc.refresh(account_id, ACTOR, BINDING, 'POST refresh', uuid4(), body, uuid4())
        count = len(graph.calls)
        with pytest.raises(SocialError, match='CREDENTIAL_BUSY'):
            svc.refresh(account_id, ACTOR, BINDING, 'POST refresh', uuid4(), body, uuid4())
        assert len(graph.calls) == count
        with db.begin():
            assert db.get(PlatformCredential, credential_id).refresh_claim is not None
            with pytest.raises(SocialError, match='CREDENTIAL_UNAVAILABLE'): svc.material(account_id)


def test_real_router_admin_binding_no_store_and_response_redaction(db):
    cfg = config('threads')
    graph = ProviderFixture(db, 'threads'); graph.cfg = cfg
    app = FastAPI(); app.include_router(router)
    def isolated():
        with Session(db.bind, expire_on_commit=False) as session: yield session
    def fake(provider: str, db=Depends(get_db)):
        return PlatformConnectionService(db, cfg, provider_factory=lambda c: OAuthProvider(c, transport=httpx.MockTransport(graph)))
    app.dependency_overrides[get_db] = isolated
    app.dependency_overrides[api_service] = fake
    client = TestClient(app, raise_server_exceptions=False)
    prefix = '/api/v1/admin/social/platform-connections/threads'
    denied = client.get(prefix + '/status')
    assert denied.status_code in (401, 403) and denied.headers['cache-control'] == 'private, no-store'
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=str(ACTOR), session_id=str(SESSION), roles=['admin'])
    def headers(): return {'Idempotency-Key': str(uuid4())}
    started = client.post(prefix + '/start', headers=headers(), json={'redirect_uri': REDIRECT, 'reason': 'Owned account'})
    assert started.status_code == 200, started.text
    state = parse_qs(urlsplit(started.json()['authorize_url']).query)['state'][0]
    done = client.post(prefix + '/complete', headers=headers(), json={'state': state, 'code': 'fake-code', 'redirect_uri': REDIRECT})
    assert done.status_code == 200, done.text
    selected = client.post(prefix + '/flows/' + done.json()['flow_id'] + '/confirm', headers=headers(), json={'external_account_id': '901', 'reason': 'Explicit confirmation'})
    assert selected.status_code == 200, selected.text
    for response in (done, selected):
        assert ACCESS not in response.text and REFRESH not in response.text and state not in response.text
        assert response.headers['cache-control'] == 'private, no-store'


def build_tiktok(db, *, mutate_on_settings=None):
    from social.adapters.tiktok_oauth import TikTokOAuthConfig
    from social.platform_connections.tiktok_provider import TikTokConnectionProvider
    redirect = REDIRECT + '/'
    oauth = TikTokOAuthConfig(client_id='123', client_secret='fake-client-secret', redirect_uri=redirect, authorization_url='https://www.tiktok.com/v2/auth/authorize?client_key=123&redirect_uri=https%3A%2F%2Fadmin.example.test%2Fadmin%2Fsocial%2Faccounts%2Fcallback%2F&scope=video.publish%2Cvideo.upload', product_access_verified=True)
    cfg = replace(config('tiktok'), redirect_uris=(redirect,), tiktok_oauth=oauth, tiktok_requested_scopes=('video.publish', 'video.upload'))
    calls = []
    async def fixture(request):
        assert not db.in_transaction()
        calls.append(request)
        if request.url.path.endswith('/business/video/settings/'):
            if mutate_on_settings: mutate_on_settings()
            data = {'privacy_level_options': ['SELF_ONLY', 'PUBLIC_TO_EVERYONE'], 'comment_disabled': True, 'duet_disabled': False, 'stitch_disabled': True, 'max_video_post_duration_sec': 300}
        else:
            assert request.url.path.endswith(('/tt_user/oauth2/token/', '/tt_user/oauth2/refresh_token/'))
            data = {'open_id': 'owned-tiktok-account', 'access_token': ACCESS, 'refresh_token': REFRESH, 'scope': 'video.publish,video.upload', 'token_type': 'Bearer', 'expires_in': 3600, 'refresh_token_expires_in': 86400}
        return httpx.Response(200, json={'code': 0, 'message': 'OK', 'request_id': 'sanitized-provider-request', 'data': data})
    svc = PlatformConnectionService(db, cfg, provider_factory=lambda c: TikTokConnectionProvider(c, transport_factory=lambda: httpx.MockTransport(fixture)))
    return svc, calls


def test_tiktok_durable_official_grant_confirmation_and_creator_settings(db):
    svc, calls = build_tiktok(db)
    selected = confirmed(svc)
    account = selected['account']
    assert account['handle'] is None and account['profile_url'] is None and account['publishing_enabled'] is False
    assert account['display_name'] == 'TikTok account owned-tiktok-account'
    account_id = UUID(account['id'])
    settings = svc.creator_settings(account_id)
    assert settings['settings']['privacy_level_options'] == ['PUBLIC_TO_EVERYONE', 'SELF_ONLY']
    assert settings['settings']['comment_disabled'] is True
    assert settings['external_account_id'] == 'owned-tiktok-account'
    assert len(settings['settings_hash']) == 64
    assert ACCESS not in json.dumps(settings) and REFRESH not in json.dumps(settings)
    body = AccountCommand(expected_credential_id=UUID(selected['credential_id']), expected_credential_version=1, reason='Renew observed owned account')
    renewed = svc.refresh(account_id, ACTOR, BINDING, 'POST refresh', uuid4(), body, uuid4())
    assert renewed['credential_version'] == 2
    assert [r.url.path for r in calls] == ['/open_api/v1.3/tt_user/oauth2/token/', '/open_api/v1.3/business/video/settings/', '/open_api/v1.3/tt_user/oauth2/refresh_token/']


def test_tiktok_settings_revalidate_disconnect_during_provider_read(db):
    account_ids = []
    def disconnect():
        with Session(db.bind) as other, other.begin():
            other.get(SocialAccount, account_ids[0]).connection_state = 'disconnected'
    svc, calls = build_tiktok(db, mutate_on_settings=disconnect)
    selected = confirmed(svc)
    account_ids.append(UUID(selected['account']['id']))
    with pytest.raises(SocialError, match='CREDENTIAL_UNAVAILABLE'):
        svc.creator_settings(account_ids[0])
    assert len(calls) == 2


@pytest.mark.parametrize('platform', ['threads', 'x'])
def test_confirm_freezes_actual_registered_adapter_contract_and_no_x_budget(db, platform):
    from social.adapters.threads import ThreadsAdapter, ThreadsAdapterConfig
    from social.adapters.x import XAdapter, XAdapterConfig
    import asyncio
    svc, _ = build(db, platform)
    adapter = ThreadsAdapter(ThreadsAdapterConfig(enabled=True, operational_gates_verified=True), transport=httpx.MockTransport(lambda r: pytest.fail('unexpected provider call'))) if platform == 'threads' else XAdapter(XAdapterConfig(enabled=True, operational_gates_verified=True), transport=httpx.MockTransport(lambda r: pytest.fail('unexpected provider call')))
    svc.available_adapters = {(adapter.platform, adapter.product): adapter}
    selected = confirmed(svc)
    snapshot = selected['account']['capabilities']
    assert snapshot['adapter_available'] is True
    if platform == 'threads':
        assert snapshot['eligible'] is True and snapshot['price_class'] == 'free'
        assert snapshot['limits']['max_media_count'] == 20
    else:
        assert snapshot['eligible'] is False and snapshot['price_class'] == 'paid'
    asyncio.run(adapter.close())


def test_x_refresh_uses_valid_refresh_grant_after_access_token_expiry(db):
    svc, graph = build(db, 'x')
    selected = confirmed(svc)
    credential_id = UUID(selected['credential_id'])
    with db.begin():
        row = db.get(PlatformCredential, credential_id)
        row.access_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    body = AccountCommand(expected_credential_id=credential_id, expected_credential_version=1, reason='Renew expired access using valid refresh grant')
    result = svc.refresh(UUID(selected['account']['id']), ACTOR, BINDING, 'POST refresh', uuid4(), body, uuid4())
    assert result['credential_version'] == 2


@pytest.mark.parametrize('gate', ['absent', 'disabled', 'access', 'zero', 'exhausted'])
def test_x_actual_app_budget_blocks_start_without_creating_flow(db, gate):
    svc, graph = build(db, 'x', connection_budget=gate != 'absent')
    if gate != 'absent':
        with db.begin():
            row = db.get(SocialPlatformConnectionBudget, digest('x:' + svc.config.client_id))
            if gate == 'disabled': row.enabled = False
            if gate == 'access': row.access_verified = False
            if gate == 'zero': row.limit_microusd = 0
            if gate == 'exhausted': row.reserved_microusd = row.limit_microusd
    with pytest.raises(SocialError, match='X_BUDGET_UNAVAILABLE'):
        start(svc)
    with db.begin(): assert db.scalar(select(PlatformOAuthFlow.id)) is None
    assert graph.calls == []


def test_x_paid_identity_read_reserves_before_http_and_unknown_retains(db):
    svc, graph = build(db, 'x')
    seen = []
    def ambiguous(request):
        if request.url.path == '/2/users/me':
            assert not db.in_transaction()
            with Session(db.bind) as independent:
                row = independent.get(SocialPlatformConnectionBudget, digest('x:' + svc.config.client_id))
                seen.append(row.reserved_microusd)
                assert row.reserved_microusd == 10000
            raise httpx.ReadTimeout(ACCESS, request=request)
        return graph(request)
    svc.provider_factory = lambda c: OAuthProvider(c, transport=httpx.MockTransport(ambiguous), admission=svc.connection_admission)
    _, state = start(svc)
    with pytest.raises(SocialError, match='PROVIDER_UNAVAILABLE'):
        complete(svc, state)
    assert seen == [10000]
    with db.begin():
        assert db.get(SocialPlatformConnectionBudget, digest('x:' + svc.config.client_id)).reserved_microusd == 10000
    with pytest.raises(SocialError, match='OAUTH_STATE_USED'):
        complete(svc, state)
    assert seen == [10000]


@pytest.mark.parametrize('trigger', ['suppress', 'alter'])
def test_x_suppressed_or_altered_reservation_refuses_paid_http(db, trigger):
    from sqlalchemy import text
    svc, graph = build(db, 'x')
    with db.begin():
        if trigger == 'suppress':
            db.execute(text('CREATE TRIGGER b15_connection_suppress BEFORE UPDATE ON social_platform_connection_budgets BEGIN SELECT RAISE(IGNORE); END'))
        else:
            db.execute(text('CREATE TRIGGER b15_connection_alter AFTER UPDATE ON social_platform_connection_budgets BEGIN UPDATE social_platform_connection_budgets SET reserved_microusd=NEW.reserved_microusd+1 WHERE client_key=NEW.client_key; END'))
    _, state = start(svc)
    with pytest.raises(SocialError, match='X_BUDGET_RESERVATION_FAILED'):
        complete(svc, state)
    assert [r.url.path for r in graph.calls] == ['/2/oauth2/token']
    with db.begin():
        assert db.get(SocialPlatformConnectionBudget, digest('x:' + svc.config.client_id)).reserved_microusd == 0


def test_x_legacy_positive_config_without_durable_admission_port_cannot_construct(db):
    with pytest.raises(SocialError, match='X_BUDGET_UNAVAILABLE'):
        OAuthProvider(config('x'), transport=httpx.MockTransport(lambda r: pytest.fail('unexpected provider HTTP')))


@pytest.mark.parametrize('platform', ['threads', 'x'])
def test_local_key_rotation_versioned_idempotent_and_preserves_ownership(db, platform):
    svc, graph = build(db, platform)
    selected = confirmed(svc)
    account_id, credential_id = UUID(selected['account']['id']), UUID(selected['credential_id'])
    keys = svc.config.encryption_keys | {'v2': Fernet.generate_key().decode()}
    svc.config = replace(svc.config, enabled=False, active_key_version='v2', encryption_keys=keys)
    body = AccountCommand(expected_credential_id=credential_id, expected_credential_version=1, reason='Rotate stable encrypted credential key')
    key = uuid4()
    count = len(graph.calls)
    rotated = svc.rotate_key(account_id, ACTOR, BINDING, 'POST rotate', key, body, uuid4())
    assert rotated['credential_version'] == 2
    assert svc.rotate_key(account_id, ACTOR, BINDING, 'POST rotate', key, body, uuid4()) == rotated
    assert len(graph.calls) == count
    claim = uuid4()
    with db.begin():
        row = db.get(PlatformCredential, credential_id)
        assert row.key_version == 'v2'
        assert svc.cipher.decrypt(row.id, svc.purpose('credential'), row.key_version, row.encrypted_bundle)['access_token'] == ACCESS
        row.refresh_claim = claim
    with pytest.raises(SocialError, match='CREDENTIAL_BUSY'):
        svc.rotate_key(account_id, ACTOR, BINDING, 'POST rotate', uuid4(), body.model_copy(update={'expected_credential_version': 2}), uuid4())
    with db.begin():
        row = db.get(PlatformCredential, credential_id)
        assert row.refresh_claim == claim and row.version == 2


def test_platform_callback_configuration_accepts_the_real_ui_callback():
    cfg = replace(config(), redirect_uris=('https://admin.example.test/admin/social/accounts/platform-callback',))
    assert cfg.blockers() == []
    cfg.require_redirect('https://admin.example.test/admin/social/accounts/platform-callback')
