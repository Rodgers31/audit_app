from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from social.studio.native_metrics import AnalyticsRuntime, CollectionCommand, parse_insights


def test_lifetime_window_is_unknown_and_missing_not_zero():
    now = datetime.now(timezone.utc)
    values = parse_insights({'data': [{'name': 'post_media_view', 'period': 'lifetime', 'values': [{'value': 0}]}]}, 'facebook', now)
    assert values[0].value == 0
    assert values[0].window_start is None and values[0].window_end is None
    assert values[1].value is None and values[1].status == 'unavailable'


@pytest.mark.parametrize('data', [None, {}, '', {'data': {}}, {'data': [None]}, {'data': [{'name':'alien'}]}])
def test_bad_provider_shapes_refuse(data):
    with pytest.raises(ValueError):
        parse_insights(data, 'facebook', datetime.now(timezone.utc))


def test_default_runtime_has_no_native_capability():
    assert AnalyticsRuntime().enabled is False

from cryptography.fernet import Fernet
from dataclasses import replace
import asyncio
import httpx
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from social.connections.crypto import CredentialCipher
from social.connections.models import SocialCredential
from social.contracts import canonical_hash
from social.models import SocialAccount, SocialAuditEvent, SocialPostTarget
from social.service import SocialError
from social.studio.analytics import collect, observations
from social.studio.contracts import MetricRequest
from social.studio.models import MetricCollection
from social.studio.native_metrics import MetaMetricsPort, capability_status, configured_runtime
from test_domain_support import db
from test_studio import published, source
from test_domain_support import account, ACTOR
from social.models import SocialPublication
from uuid import UUID
from test_native_meta_adapters import payload


def native_fixture(db, platform='facebook'):
    acc = account(db, platform)
    post = source(db)
    publication = SocialPublication(id=uuid4(), post_id=UUID(post['id']), revision_id=UUID(post['revision_id']),
        authorization_kind='human', approved_by=ACTOR, approved_at=datetime.now(timezone.utc), approved_hash='a'*64)
    db.add(publication)
    db.flush()
    value = payload(platform=platform, account_id=acc.id)
    acc.external_account_id, acc.api_product = value.external_account_id, value.api_product
    acc.connection_method, acc.publishing_enabled = 'facebook_login', False
    scopes = ['read_insights', 'pages_read_engagement'] if platform == 'facebook' else ['instagram_basic', 'instagram_manage_insights', 'pages_read_engagement']
    acc.granted_scopes = scopes
    cipher = CredentialCipher('fixture', {'fixture': Fernet.generate_key().decode()})
    parent = SocialCredential(id=uuid4(), credential_kind='facebook_user', version=1)
    cred = SocialCredential(id=uuid4(), credential_kind='facebook_page', parent_credential_id=parent.id, version=1)
    for row in (parent, cred):
        bundle = {'access_token': 'fixture-page-token' if row is cred else 'fixture-user-token', 'external_user_id': '123', 'scopes': scopes}
        if row is cred:
            bundle['page_id'] = '901'
        row.key_version, row.encrypted_bundle = cipher.encrypt(row.id, row.credential_kind, bundle)
        db.add(row)
        db.flush()
    acc.credential_id = cred.id
    target = SocialPostTarget(id=uuid4(), publication_id=publication.id, account_id=acc.id,
        primary_remote_id='901_777' if platform == 'facebook' else '777', resolved_payload=value.model_dump(mode='json'),
        payload_hash=value.content_hash, capability_version='v26.0', state='published', visibility_state='public',
        published_at=datetime.now(timezone.utc), confirmation_kind='fixture')
    db.add(target)
    db.commit()
    runtime = AnalyticsRuntime(True, (platform,), True, True, cipher, 'fixture-app-secret')
    cmd = CollectionCommand(account_id=acc.id, credential_id=cred.id, credential_version=1,
        parent_credential_id=parent.id, parent_credential_version=1, payload_hash=target.payload_hash,
        remote_id=target.primary_remote_id, runtime_hash=runtime.fingerprint())
    return target, runtime, cmd


def test_real_composition_durable_observations_restart_and_quota(db, monkeypatch):
    target, runtime, command = native_fixture(db)
    assert capability_status(db, runtime)[0] is True
    db.rollback()
    # Executes real port/parser with injected wire only; durable orchestration is real.
    def bounded(port, request):
        assert port.token == 'fixture-page-token'
        assert port.request_hash == canonical_hash(request.model_dump(mode='json'))
        return asyncio.run(port._read(request, transport=httpx.MockTransport(lambda r: httpx.Response(200,
            json={'data': [{'name': 'post_media_view', 'period': 'lifetime', 'values': [{'value': 0}]}]}))))
    monkeypatch.setattr('social.studio.analytics.bounded_collect', bounded)
    factory = sessionmaker(bind=db.bind)
    collection = collect(factory, target.id, runtime, enabled=True, authorization=command)
    with factory() as restarted:
        result = observations(restarted, target.id)
        assert result['collections'][0]['id'] == str(collection)
        assert [m['value'] for m in result['collections'][0]['metrics']] == [0, None, None]
        assert restarted.scalar(select(SocialAuditEvent).where(SocialAuditEvent.action == 'metrics.reserved')).details['authorization'] == command.model_dump(mode='json')
        assert restarted.get(SocialAccount, target.account_id).publishing_enabled is False
    with pytest.raises(SocialError, match='METRICS_QUOTA'):
        collect(factory, target.id, runtime, enabled=True, authorization=command)


@pytest.mark.parametrize('field,value', [('credential_version',2), ('parent_credential_version',2), ('payload_hash','a'*64), ('remote_id','901_666'), ('runtime_hash','0'*64), ('account_id',uuid4())])
def test_exact_authorization_refuses_before_wire(db, monkeypatch, field, value):
    target, runtime, command = native_fixture(db)
    calls = []
    monkeypatch.setattr('social.studio.analytics.bounded_collect', lambda *_: calls.append(1))
    with pytest.raises(SocialError):
        collect(sessionmaker(bind=db.bind), target.id, runtime, enabled=True, authorization=command.model_copy(update={field:value}))
    assert calls == []
    assert db.scalar(select(MetricCollection)) is None


def test_generation_change_during_read_discards_but_consumes_quota(db, monkeypatch):
    target, runtime, command = native_fixture(db)
    factory = sessionmaker(bind=db.bind)
    def read(port, request):
        with factory() as other, other.begin():
            other.get(SocialCredential, command.credential_id).version += 1
        return parse_insights({'data':[]}, 'facebook', datetime.now(timezone.utc))
    monkeypatch.setattr('social.studio.analytics.bounded_collect', read)
    with pytest.raises(SocialError, match='METRICS_AUTHORIZATION_CHANGED'):
        collect(factory, target.id, runtime, enabled=True, authorization=command)
    with factory() as restarted:
        row = restarted.scalar(select(MetricCollection))
        assert row.state == 'failed'
        assert observations(restarted, target.id)['collections'][0]['metrics'] == []


@pytest.mark.parametrize('mutation', ['scope', 'refresh', 'revoked', 'expired', 'envelope', 'payload'])
def test_credential_and_payload_boundaries(db, mutation):
    target, runtime, command = native_fixture(db)
    cred = db.get(SocialCredential, command.credential_id)
    if mutation == 'scope':
        db.get(SocialAccount, command.account_id).granted_scopes = []
    elif mutation == 'refresh':
        cred.refresh_lease_token, cred.refresh_lease_expires_at = uuid4(), datetime.now(timezone.utc)-timedelta(seconds=1)
    elif mutation == 'revoked':
        cred.revoked_at = datetime.now(timezone.utc)
    elif mutation == 'expired':
        cred.access_expires_at = datetime.now(timezone.utc)+timedelta(seconds=5)
    elif mutation == 'envelope':
        cred.encrypted_bundle = b'bad'
    else:
        from sqlalchemy import update
        db.execute(update(SocialPostTarget).where(SocialPostTarget.id == target.id).values(resolved_payload={}))
    db.commit()
    assert capability_status(db, runtime)[0] is False
    db.rollback()
    with pytest.raises(SocialError):
        collect(sessionmaker(bind=db.bind), target.id, runtime, enabled=True, authorization=command)


def test_instagram_uses_parent_user_token(db):
    target, runtime, command = native_fixture(db, 'instagram')
    request = MetricRequest(platform='instagram', account_id=target.account_id, target_id=target.id,
        remote_id='777', deadline=datetime.now(timezone.utc)+timedelta(seconds=10))
    assert runtime.prepare(db, target, command, request).token == 'fixture-user-token'


@pytest.mark.parametrize('bad', [True, False, 0, -1, float('nan'), float('inf'), None, '1'])
def test_command_generation_strict(bad):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        CollectionCommand(account_id=uuid4(), credential_id=uuid4(), credential_version=bad,
            parent_credential_id=uuid4(), parent_credential_version=1, payload_hash='a'*64, remote_id='777', runtime_hash='b'*64)


def test_configuration_and_fixture_registry_do_not_certify_native(db):
    assert configured_runtime({}).enabled is False
    with pytest.raises(ValueError):
        configured_runtime({'SOCIAL_ANALYTICS_ENABLED':'yes'})
    with pytest.raises(ValueError):
        AnalyticsRuntime(True, ('x',), True, True)
    with pytest.raises(ValueError):
        AnalyticsRuntime(True, ('facebook',), True, False)
    target = published(db)
    assert capability_status(db, AnalyticsRuntime())[0] is False


@pytest.mark.parametrize('body', [b'{"data":[],"data":[]}', b'{"data": NaN}', b'{}', b'['+b'0'*40000+b']'])
def test_wire_bad_bytes_and_redaction(body):
    from social.adapters.config import MetaAdapterConfig
    req = MetricRequest(platform='facebook', account_id=uuid4(), target_id=uuid4(), remote_id='901_777', deadline=datetime.now(timezone.utc)+timedelta(seconds=10))
    port = MetaMetricsPort('facebook', canonical_hash(req.model_dump(mode='json')), MetaAdapterConfig('v26.0', True, True, 'fixture-secret'), 'fixture-token')
    with pytest.raises(ValueError, match='Native metrics read failed') as exc:
        asyncio.run(port._read(req, transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))))
    assert 'fixture-token' not in str(exc.value)


def test_transport_proof_no_redirects_and_exact_query():
    from social.adapters.config import MetaAdapterConfig
    req = MetricRequest(platform='facebook', account_id=uuid4(), target_id=uuid4(), remote_id='901_777', deadline=datetime.now(timezone.utc)+timedelta(seconds=10))
    port = MetaMetricsPort('facebook', canonical_hash(req.model_dump(mode='json')), MetaAdapterConfig('v26.0', True, True, 'fixture-secret'), 'fixture-token')
    calls = []
    def wire(request):
        calls.append(request)
        assert request.method == 'GET' and request.url.host == 'graph.facebook.com'
        assert request.url.path == '/v26.0/901_777/insights'
        assert request.url.params['period'] == 'lifetime'
        assert request.headers['authorization'] == 'Bearer fixture-token'
        assert 'access_token' not in request.url.params and 'appsecret_proof' in request.url.params
        return httpx.Response(302, headers={'location':'https://example.org/leak'}, json={})
    with pytest.raises(ValueError):
        asyncio.run(port._read(req, transport=httpx.MockTransport(wire)))
    assert len(calls) == 1


def test_provider_end_time_preserved_without_invented_start():
    now = datetime.now(timezone.utc)
    end = now-timedelta(days=1)
    values = parse_insights({'data':[{'name':'post_media_view','period':'lifetime','values':[{'value':1,'end_time':end.isoformat()}]}]}, 'facebook', now)
    assert values[0].window_start is None and values[0].window_end == end


class LocalForward(httpx.AsyncBaseTransport):
    def __init__(self, port):
        self.port = port
        self.inner = httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request):
        local = httpx.Request(request.method, request.url.copy_with(scheme='http', host='127.0.0.1', port=self.port), headers=request.headers)
        return await self.inner.handle_async_request(local)

    async def aclose(self):
        await self.inner.aclose()


@pytest.mark.parametrize('mode', ['success', 'oversize', 'delayed', 'compressed', 'status'])
def test_real_http_local_endpoint_deadline_bytes_and_failure(mode):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    import time
    from social.adapters.config import MetaAdapterConfig
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_GET(self):
            calls.append(self.path)
            if mode == 'delayed':
                time.sleep(.25)
            self.send_response(503 if mode == 'status' else 200)
            if mode == 'compressed':
                self.send_header('Content-Encoding', 'gzip')
            self.end_headers()
            try:
                self.wfile.write(b'x'*32769 if mode == 'oversize' else b'{"data":[]}')
            except (BrokenPipeError, ConnectionResetError):
                pass  # Owned client intentionally closes on deadline.
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    req = MetricRequest(platform='facebook', account_id=uuid4(), target_id=uuid4(), remote_id='901_777', deadline=datetime.now(timezone.utc)+timedelta(seconds=.15 if mode == 'delayed' else 5))
    port = MetaMetricsPort('facebook', canonical_hash(req.model_dump(mode='json')), MetaAdapterConfig('v26.0', True, True, 'fixture-secret'), 'fixture-token')
    try:
        if mode == 'success':
            assert len(asyncio.run(port._read(req, transport=LocalForward(server.server_port)))) == 3
        else:
            with pytest.raises(ValueError, match='Native metrics read failed') as exc:
                asyncio.run(port._read(req, transport=LocalForward(server.server_port)))
            assert exc.value.__context__ is None
        assert len(calls) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_operator_default_off_before_database_import(tmp_path, monkeypatch, capsys):
    from social_metrics import main
    monkeypatch.delenv('SOCIAL_ANALYTICS_ENABLED', raising=False)
    assert main([str(uuid4()), '--authorization', str(tmp_path/'absent')]) == 1
    assert main([str(uuid4()), '--authorization', str(tmp_path/'absent'), '--enable-native-collection']) == 1
    assert 'No automatic retry' in capsys.readouterr().out


def test_interruption_retains_durable_reservation_after_restart(db, monkeypatch):
    target, runtime, command = native_fixture(db)
    def interrupt(*_):
        raise KeyboardInterrupt()
    monkeypatch.setattr('social.studio.analytics.bounded_collect', interrupt)
    factory = sessionmaker(bind=db.bind)
    with pytest.raises(KeyboardInterrupt):
        collect(factory, target.id, runtime, enabled=True, authorization=command)
    with factory() as restarted:
        row = restarted.scalar(select(MetricCollection))
        assert row.state == 'reserved'
    with pytest.raises(SocialError, match='METRICS_QUOTA'):
        collect(factory, target.id, runtime, enabled=True, authorization=command)


def test_native_failed_read_retains_quota_and_safe_reason(db, monkeypatch):
    target, runtime, command = native_fixture(db)
    def failed(*_):
        raise RuntimeError('fixture-token-never-persist')
    monkeypatch.setattr('social.studio.analytics.bounded_collect', failed)
    factory = sessionmaker(bind=db.bind)
    with pytest.raises(SocialError, match='METRICS_COLLECTION_FAILED'):
        collect(factory, target.id, runtime, enabled=True, authorization=command)
    with factory() as restarted:
        row = restarted.scalar(select(MetricCollection))
        assert row.state == 'failed' and 'fixture-token' not in row.reason
    with pytest.raises(SocialError, match='METRICS_QUOTA'):
        collect(factory, target.id, runtime, enabled=True, authorization=command)


def test_port_exact_request_binding_refuses_before_network(db):
    target, runtime, command = native_fixture(db)
    req = MetricRequest(platform='facebook', account_id=target.account_id, target_id=target.id,
        remote_id=target.primary_remote_id, deadline=datetime.now(timezone.utc)+timedelta(seconds=10))
    port = runtime.prepare(db, target, command, req)
    with pytest.raises(ValueError, match='authorization'):
        port.collect(req.model_copy(update={'remote_id':'901_333'}))


@pytest.mark.parametrize('field,value', [('platform','instagram'), ('account_id',uuid4()), ('target_id',uuid4()), ('remote_id','999_888'), ('max_records',True), ('max_response_bytes',True)])
def test_prepare_binds_exact_request_to_operator_authorization(db, field, value):
    target, runtime, command = native_fixture(db)
    req = MetricRequest(platform='facebook', account_id=target.account_id, target_id=target.id,
        remote_id=target.primary_remote_id, deadline=datetime.now(timezone.utc)+timedelta(seconds=10))
    with pytest.raises(SocialError, match='METRICS_REQUEST_CHANGED'):
        runtime.prepare(db, target, command, req.model_copy(update={field:value}))


from dataclasses import dataclass

@dataclass(frozen=True)
class LocalProcessPort(MetaMetricsPort):
    local_port: int = 0

    async def _read(self, request, **_):
        return await super()._read(request, transport=LocalForward(self.local_port))


def test_native_composition_spawned_process_real_local_http(db, monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from social.studio.analytics import bounded_collect
    target, runtime, command = native_fixture(db)
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_GET(self):
            calls.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"data":[{"name":"post_media_view","period":"lifetime","values":[{"value":0}]}]}')
    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def local_only(port, request):
        owned = LocalProcessPort(port.platform, port.request_hash, port.config, port.token, local_port=server.server_port)
        return bounded_collect(owned, request)
    monkeypatch.setattr('social.studio.analytics.bounded_collect', local_only)
    try:
        factory = sessionmaker(bind=db.bind)
        collection_id = collect(factory, target.id, runtime, enabled=True, authorization=command)
        with factory() as restarted:
            assert restarted.get(MetricCollection, collection_id).state == 'collected'
            assert observations(restarted,target.id)['collections'][0]['metrics'][0]['value'] == 0
        assert len(calls) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_capabilities_http_truth_requires_native_eligible_account(db):
    from test_studio_api import client
    from social.studio.runtime import StudioRuntime
    target, runtime, command = native_fixture(db)
    api = client(db, StudioRuntime())
    base = '/api/v1/admin/social/studio/capabilities'
    assert api.get(base).json()['analytics_collection_available'] is False
    api.app.state.social_analytics_runtime = runtime
    response = api.get(base)
    assert response.status_code == 200 and response.json()['analytics_collection_available'] is True
    assert response.json()['uploads_enabled'] is False
    assert response.headers['cache-control'] == 'private, no-store'
    db.get(SocialAccount, command.account_id).granted_scopes = []
    db.commit()
    assert api.get(base).json()['analytics_collection_available'] is False
    api.app.state.social_analytics_runtime = {'facebook': object()}
    assert api.get(base).status_code == 503
