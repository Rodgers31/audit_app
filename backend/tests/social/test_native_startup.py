"""The actual composition boundary stays inert until both explicit gates pass."""
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine


def startup():
    from social.worker.startup import native_runtime, installed_native_runtime
    return native_runtime, installed_native_runtime


@pytest.mark.asyncio
async def test_disabled_composition_does_not_read_dependencies_or_build_transport():
    runtime, _ = startup()
    async with runtime(None, environ={}, transport_factory=lambda: pytest.fail('transport')) as registration:
        assert registration is None


@pytest.mark.asyncio
@pytest.mark.parametrize('values', [
    {'SOCIAL_NATIVE_ENABLED': 'yes'},
    {'SOCIAL_NATIVE_ENABLED': True},
    {'SOCIAL_NATIVE_ENABLED': 'true'},
    {'SOCIAL_NATIVE_ENABLED': 'true', 'SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED': 'false'},
    {'SOCIAL_NATIVE_ENABLED': 'true', 'SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED': True},
    {'SOCIAL_NATIVE_ENABLED': 'true', 'SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED': 'true'},
])
async def test_incomplete_or_malformed_gates_refuse_before_transport(values):
    runtime, _ = startup()
    with pytest.raises(Exception) as result:
        async with runtime(None, environ=values, transport_factory=lambda: pytest.fail('transport')):
            pytest.fail('invalid configuration admitted')
    assert str(result.value) == 'NATIVE_CONFIGURATION_INVALID'
    assert result.value.__context__ is None


def ready(monkeypatch):
    from cryptography.fernet import Fernet
    from social.connections.config import MetaConfig
    from social.media.config import MediaConfig
    from social.media.runtime import MediaRuntime
    from social.media.storage import R2Storage
    import social.worker.startup as module
    from unittest.mock import Mock
    cfg = MetaConfig(True, True, '123', 'fixture-secret', 'v26.0',
        ('https://example.test/admin/social/accounts/callback',), 'owned_standard',
        'v1', {'v1': Fernet.generate_key().decode()})
    monkeypatch.setattr(module, 'load_meta_config', lambda values: cfg)
    storage = R2Storage(Mock(), 'media-test', 'https://' + 'a'*32 + '.r2.cloudflarestorage.com')
    runtime = MediaRuntime(MediaConfig(enabled=True, endpoint='https://'+'a'*32+'.r2.cloudflarestorage.com',
        bucket='media-test', access_key='fixture', secret_key='fixture'), storage,
        Mock(available_mimes=lambda: ('image/jpeg','image/png')))
    monkeypatch.setattr(module, 'load_media_runtime', lambda values: runtime)
    return module


@pytest.mark.asyncio
async def test_explicit_registration_and_transport_shutdown(monkeypatch):
    runtime, _ = startup()
    ready(monkeypatch)
    engine = create_engine('sqlite://')
    transports = []
    class Transport(httpx.AsyncBaseTransport):
        closes = 0
        async def handle_async_request(self, request):
            pytest.fail('startup contacted Meta')
        async def aclose(self):
            self.closes += 1
    def factory():
        item = Transport(); transports.append(item); return item
    try:
        async with runtime(engine, environ={'SOCIAL_NATIVE_ENABLED':'true',
                'SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED':'true'}, transport_factory=factory) as registration:
            assert set(registration.adapters) == {('facebook','facebook_pages'), ('instagram','instagram_graph_facebook_login')}
            assert registration.credential_loader and registration.media_access
        assert [item.closes for item in transports] == [1, 1]
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_partial_factory_failure_closes_earlier_transport(monkeypatch):
    runtime, _ = startup(); ready(monkeypatch)
    engine = create_engine('sqlite://')
    class Transport(httpx.AsyncBaseTransport):
        closes = 0
        async def aclose(self): self.closes += 1
    transport = Transport()
    calls = 0
    def factory():
        nonlocal calls
        calls += 1
        if calls == 2: raise ValueError('private-marker')
        return transport
    try:
        with pytest.raises(Exception) as result:
            async with runtime(engine, environ={'SOCIAL_NATIVE_ENABLED':'true',
                    'SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED':'true'}, transport_factory=factory):
                pytest.fail('partial registry admitted')
        assert str(result.value) == 'NATIVE_CONFIGURATION_INVALID'
        assert result.value.__context__ is None
        assert transport.closes == 1
    finally: engine.dispose()


@pytest.mark.asyncio
async def test_web_installation_is_removed_and_closed_after_exception(monkeypatch):
    _, installed = startup(); ready(monkeypatch)
    engine = create_engine('sqlite://'); app = SimpleNamespace(state=SimpleNamespace())
    try:
        with pytest.raises(RuntimeError, match='application failure'):
            async with installed(app, engine, environ={'SOCIAL_NATIVE_ENABLED':'true',
                    'SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED':'true'},
                    transport_factory=lambda: httpx.MockTransport(lambda request: pytest.fail('network'))):
                assert app.state.social_native_registration.adapters
                raise RuntimeError('application failure')
        assert not hasattr(app.state,'social_native_registration')
    finally: engine.dispose()
