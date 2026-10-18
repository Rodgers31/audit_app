"""Strict platform startup composition; injected transports, no external I/O.

Enabled media objects here are local inert fixtures. They do not establish the
worker-only read-composition dependency in coordinator issue700 or enable live
uploads. Runtime factories are mocked at their actual registration boundary.
"""
import asyncio
from contextlib import asynccontextmanager
import json
from types import SimpleNamespace
from unittest.mock import Mock

from cryptography.fernet import Fernet
import httpx
import pytest
from sqlalchemy import create_engine

from social.platform_runtime import load_platform_settings
from social.service import SocialError
from social.worker.startup import installed_native_runtime, native_runtime, validate_worker_native_environment
from test_native_startup import ready

SECRET = 'fixture-runtime-private-material'
REDIRECT = 'https://admin.example.test/admin/social/accounts/callback'
STATE_NAMES = ('social_native_registration', 'social_media_runtime',
    'social_platform_connections_config', 'social_platform_events_config')


def run(awaitable):
    return asyncio.run(awaitable)


def environment(platform='threads', **changes):
    policy = dict(connections_enabled=True, adapter_enabled=True, access_verified=True, operational_gates_verified=True)
    if platform == 'x':
        policy['connection_budget_microusd'] = 100000
    if platform == 'tiktok':
        policy.update(verified_origins=['https://owned.example/media/'],
            authorization_url='https://www.tiktok.com/v2/auth/authorize?client_key=123&scope=video.publish&redirect_uri=https%3A%2F%2Fadmin.example.test%2Fadmin%2Fsocial%2Faccounts%2Fcallback%2F',
            scopes=['video.publish'], unattended_publication_verified=False)
    policy.update(changes)
    callback = REDIRECT + '/' if platform == 'tiktok' else REDIRECT
    return {'SOCIAL_PLATFORM_POLICY': json.dumps({platform: policy}),
        'SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION': 'v1',
        'SOCIAL_CREDENTIAL_KEYS': json.dumps({'v1': Fernet.generate_key().decode()}),
        platform.upper() + '_CLIENT_ID': '123', platform.upper() + '_CLIENT_SECRET': SECRET,
        platform.upper() + '_REDIRECT_URIS': json.dumps([callback])}


def assert_invalid(values):
    with pytest.raises(SocialError) as caught:
        load_platform_settings(values)
    assert caught.value.code == 'PLATFORM_CONFIGURATION_INVALID'
    assert SECRET not in str(caught.value) and caught.value.__context__ is None


def test_empty_policy_is_inert_and_does_not_borrow_environment(monkeypatch):
    monkeypatch.setenv('SOCIAL_PLATFORM_POLICY', json.dumps({'threads': {'adapter_enabled': True}}))
    monkeypatch.setenv('SOCIAL_CREDENTIAL_KEYS', SECRET)
    import social.platform_runtime as module
    monkeypatch.setattr(module, 'CredentialCipher', lambda *args: pytest.fail('Default off constructed a cipher'))
    result = load_platform_settings({})
    assert result.connections == result.adapters == result.events == {}
    assert result.cipher is None and result.tiktok_verified_origins == ()


@pytest.mark.parametrize('platform', ['threads', 'x', 'tiktok'])
def test_explicit_empty_policy_keeps_every_feature_off_without_keyring(platform):
    result = load_platform_settings({'SOCIAL_PLATFORM_POLICY': json.dumps({platform: {}})})
    assert result.cipher is None and result.events == {}
    assert result.connections[platform].enabled is False
    assert result.adapters[platform].ready is False


@pytest.mark.parametrize('platform', ['threads', 'x', 'tiktok'])
def test_ready_policy_constructs_exact_registered_product_without_io(platform):
    result = load_platform_settings(environment(platform))
    assert result.adapters[platform].ready
    assert result.connections[platform].enabled and result.connections[platform].access_verified
    assert result.events == {} and result.cipher is not None
    if platform == 'tiktok':
        assert result.tiktok_verified_origins == ('https://owned.example/media/',)
        assert result.adapters[platform].unattended_publication_verified is False
    if platform == 'x':
        assert result.connections[platform].connection_budget_microusd == 100000


@pytest.mark.parametrize('raw', ['', '[]', 'null', 'true', '{', '{"unknown":{}}',
    '{"threads":{"adapter_enabled":"true"}}', '{"x":{"connection_budget_microusd":true}}',
    '{"x":{"connection_budget_microusd":-1}}', '{"threads":{"unknown":true}}'])
def test_malformed_or_coerced_policy_never_enables_a_feature(raw):
    assert_invalid({'SOCIAL_PLATFORM_POLICY': raw})


@pytest.mark.parametrize('platform,changes', [('threads', {'access_verified': False}),
    ('threads', {'operational_gates_verified': False}), ('x', {'connection_budget_microusd': 0}),
    ('x', {'events_enabled': True}), ('x', {'media_request_cost_microusd': 0}),
    ('tiktok', {'verified_origins': []}), ('tiktok', {'verified_origins': ['https://owned.example/media']}),
    ('tiktok', {'authorization_url': 'https://wrong.example/auth'}), ('tiktok', {'scopes': []})])
def test_unaccepted_product_cost_and_origin_gates_are_rejected(platform, changes):
    assert_invalid(environment(platform, **changes))


@pytest.mark.parametrize('field,value', [('SOCIAL_CREDENTIAL_KEYS', 'not-json'),
    ('SOCIAL_CREDENTIAL_KEYS', '[]'), ('SOCIAL_CREDENTIAL_KEYS', '{"v1":"invalid"}'),
    ('THREADS_REDIRECT_URIS', '{}'), ('THREADS_REDIRECT_URIS', '[true]'),
    ('THREADS_REDIRECT_URIS', '["https://admin.example.test/unregistered"]'),
    ('THREADS_CLIENT_ID', 123), ('THREADS_CLIENT_SECRET', True)])
def test_server_material_shapes_are_strict(field, value):
    values = environment()
    values[field] = value
    assert_invalid(values)


@pytest.mark.parametrize('raw', ['{"threads":{},"threads":{"adapter_enabled":false}}',
    '{"threads":{"adapter_enabled":false,"adapter_enabled":false}}'])
def test_duplicate_policy_keys_are_not_ambiguous_configuration(raw):
    assert_invalid({'SOCIAL_PLATFORM_POLICY': raw})


def test_event_subscription_gate_is_separate_from_connection_and_adapter_gates():
    values = environment(events_enabled=True, subscription_verified=True, subscriptions=[['subscription123', 'account123']])
    values['THREADS_WEBHOOK_VERIFY_TOKEN'] = 'fixture-verification-token'
    result = load_platform_settings(values)
    assert result.events['threads'].enabled
    assert result.events['threads'].subscriptions == (('subscription123', 'account123'),)
    assert_invalid(environment(events_enabled=True))


class Registration:
    def __init__(self, events, name='platform'):
        self.adapters, self.credential_loader, self.media_access = {}, object(), object()
        self.events, self.name = events, name
    async def close(self):
        self.events.append(self.name + '-close')


def runtime_fixture(monkeypatch):
    module = ready(monkeypatch)
    shared = module.load_media_runtime({})
    events = []
    shared.storage.client.close.side_effect = lambda: events.append('storage-close')
    return module, shared, events


def test_platform_only_startup_uses_existing_registration_factory_and_owned_shutdown(monkeypatch):
    async def exercise():
        module, shared, events = runtime_fixture(monkeypatch)
        import social.worker.native_runtime as registration_module
        seen = []
        registration = Registration(events)
        def factory(engine, configurations, **kwargs):
            seen.append((engine, configurations, kwargs))
            return registration
        monkeypatch.setattr(registration_module, 'create_platform_registration', factory)
        monkeypatch.setattr(module, 'create_native_registration', lambda *a, **k: pytest.fail('Meta unexpectedly enabled'))
        engine, app = object(), SimpleNamespace(state=SimpleNamespace())
        async with installed_native_runtime(app, engine, environ=environment(), transport_factory=lambda: pytest.fail('No transport expected in mocked factory')) as installed:
            assert installed is registration
            assert app.state.social_native_registration is registration
            assert app.state.social_media_runtime is shared
            assert set(app.state.social_platform_connections_config) == {'threads'}
            assert app.state.social_platform_events_config == {}
        assert len(seen) == 1 and seen[0][0] is engine
        assert seen[0][1]['threads'].ready
        port = seen[0][2]['storage']
        assert not hasattr(port, 'client')
        assert port.bucket == shared.storage.bucket
        shared.storage.client.head_object.return_value = {'ContentLength': 1, 'ETag': 'fixture', 'Metadata': {}, 'ContentType': 'image/png'}
        assert port.head('fixture').size == 1
        shared.storage.client.head_object.assert_called_once_with(Bucket=shared.storage.bucket, Key='fixture')
        assert events == ['platform-close', 'storage-close']
        assert all(not hasattr(app.state, name) for name in STATE_NAMES)
    run(exercise())


def test_meta_defaults_and_registration_are_preserved_with_platform_policy_absent(monkeypatch):
    async def exercise():
        module, _, events = runtime_fixture(monkeypatch)
        import social.worker.native_runtime as registration_module
        monkeypatch.setattr(registration_module, 'create_platform_registration', lambda *a, **k: pytest.fail('Default off platform registry constructed'))
        engine = create_engine('sqlite://')
        try:
            async with native_runtime(engine, environ={'SOCIAL_NATIVE_ENABLED': 'true', 'SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED': 'true'},
                    transport_factory=lambda: httpx.MockTransport(lambda request: pytest.fail('Provider I/O'))) as registered:
                assert set(registered.adapters) == {('facebook', 'facebook_pages'), ('instagram', 'instagram_graph_facebook_login')}
                assert all(adapter.config.graph_version == 'v26.0' for adapter in registered.adapters.values())
            assert events == ['storage-close']
        finally:
            engine.dispose()
    run(exercise())


def test_registration_enter_failure_detaches_all_owned_app_state(monkeypatch):
    async def exercise():
        module, _, events = runtime_fixture(monkeypatch)
        app = SimpleNamespace(state=SimpleNamespace())
        @asynccontextmanager
        async def fail(*args, **kwargs):
            raise SocialError('NATIVE_CONFIGURATION_INVALID', 'Safe startup refusal', 503)
            yield
        monkeypatch.setattr(module, 'native_runtime', fail)
        with pytest.raises(SocialError, match='NATIVE_CONFIGURATION_INVALID'):
            async with installed_native_runtime(app, object(), environ=environment()):
                pytest.fail('Refused registration entered')
        assert all(not hasattr(app.state, name) for name in STATE_NAMES)
        assert events == ['storage-close']
    run(exercise())


def test_shutdown_preserves_state_replaced_by_another_owner(monkeypatch):
    async def exercise():
        module, _, events = runtime_fixture(monkeypatch)
        app = SimpleNamespace(state=SimpleNamespace())
        registration = Registration(events)
        @asynccontextmanager
        async def context(*args, **kwargs):
            yield registration
        monkeypatch.setattr(module, 'native_runtime', context)
        replacements = {name: object() for name in STATE_NAMES}
        async with installed_native_runtime(app, object(), environ=environment()):
            for name, replacement in replacements.items():
                setattr(app.state, name, replacement)
        assert all(getattr(app.state, name) is value for name, value in replacements.items())
        assert events == ['storage-close']
    run(exercise())


@pytest.mark.parametrize('existing', STATE_NAMES)
def test_preexisting_app_state_is_not_replaced_or_deleted(monkeypatch, existing):
    async def exercise():
        module, _, events = runtime_fixture(monkeypatch)
        prior = object()
        app = SimpleNamespace(state=SimpleNamespace(**{existing: prior}))
        with pytest.raises(SocialError):
            async with installed_native_runtime(app, object(), environ=environment()):
                pytest.fail('Existing owner replaced')
        assert getattr(app.state, existing) is prior
        assert all(not hasattr(app.state, name) for name in STATE_NAMES if name != existing)
    run(exercise())


def test_application_cancellation_removes_only_owned_state_and_closes_storage(monkeypatch):
    async def exercise():
        module, _, events = runtime_fixture(monkeypatch)
        app = SimpleNamespace(state=SimpleNamespace())
        registration = Registration(events)
        @asynccontextmanager
        async def context(*args, **kwargs):
            try:
                yield registration
            finally:
                events.append('registration-exit')
        monkeypatch.setattr(module, 'native_runtime', context)
        with pytest.raises(asyncio.CancelledError):
            async with installed_native_runtime(app, object(), environ=environment()):
                raise asyncio.CancelledError()
        assert all(not hasattr(app.state, name) for name in STATE_NAMES)
        assert events == ['registration-exit', 'storage-close']
    run(exercise())


def test_actual_platform_factory_failure_closes_partial_resources_and_detaches_state(monkeypatch):
    async def exercise():
        _, _, events = runtime_fixture(monkeypatch)
        import social.worker.native_runtime as registration_module
        class Transport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                pytest.fail('Startup attempted provider I/O')
            async def aclose(self):
                events.append('partial-transport-close')
        def fail_factory(engine, configurations, **kwargs):
            assert configurations['threads'].ready
            kwargs['transport_factory']()
            raise ValueError(SECRET)
        monkeypatch.setattr(registration_module, 'create_platform_registration', fail_factory)
        app = SimpleNamespace(state=SimpleNamespace())
        with pytest.raises(SocialError) as caught:
            async with installed_native_runtime(app, object(), environ=environment(), transport_factory=Transport):
                pytest.fail('Partial registration admitted')
        assert caught.value.code == 'NATIVE_CONFIGURATION_INVALID'
        assert caught.value.__context__ is None and SECRET not in str(caught.value)
        assert all(not hasattr(app.state, name) for name in STATE_NAMES)
        assert events == ['partial-transport-close', 'storage-close']
    run(exercise())


@pytest.mark.parametrize('key,value', [('SOCIAL_CREDENTIAL_KEYS', '[]'),
    ('SOCIAL_CREDENTIAL_KEYS', '{"v1":true}'),
    ('SOCIAL_CREDENTIAL_KEYS', '{"v1":"first","v1":"second"}'),
    ('SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION', True), ('THREADS_CLIENT_ID', 123), ('THREADS_CLIENT_SECRET', True)])
def test_supplied_disabled_configuration_is_still_unambiguous(key, value):
    assert_invalid({'SOCIAL_PLATFORM_POLICY': '{"threads":{}}', key: value})


def test_platform_worker_preflight_keeps_private_media_dependency_explicit(monkeypatch):
    import social.worker.startup as module
    # Coordination issue700 remains open: a genuine worker-only storage-read
    # policy must be supplied by the worker/media lane. Do not enable uploads.
    monkeypatch.setattr(module, 'config_from_environment', lambda _: SimpleNamespace(enabled=False))
    with pytest.raises(ValueError, match='Private media gates are not accepted'):
        validate_worker_native_environment(environment())
