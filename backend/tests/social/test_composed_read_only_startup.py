"""Read-only media admission survives platform + worker branch composition."""
import asyncio
import socket
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine

from social.worker.startup import installed_native_runtime, validate_worker_native_environment
from test_platform_runtime import environment
from test_worker_read_only_media import values


@pytest.mark.parametrize('meta', [False, True])
@pytest.mark.parametrize('platform', ['threads', 'x', 'tiktok'])
def test_platforms_start_with_uploads_off_and_private_read_gate(monkeypatch, meta, platform):
    configured = {**values(), **environment(platform)}
    configured['SOCIAL_NATIVE_ENABLED'] = 'true' if meta else 'false'
    if not meta:
        configured['META_APP_SECRET'] = ''  # Platform-only path must not borrow Meta access.
    validate_worker_native_environment(configured)
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('Native startup attempted network'))
    engine = create_engine('sqlite://')
    app = SimpleNamespace(state=SimpleNamespace())

    async def exercise():
        async with installed_native_runtime(app, engine, environ=configured) as registration:
            assert app.state.social_media_runtime.config.enabled is False
            assert app.state.social_media_runtime.storage is None
            assert {key[0] for key in registration.adapters} == ({'facebook', 'instagram', platform} if meta else {platform})
            port = registration.media_access.storage
            assert all(callable(getattr(port, name, None)) for name in ('head', 'download', 'preview', 'provider_fetch'))
            assert all(not hasattr(port, name) for name in ('authorize_upload', 'finalize', 'retire_payload', 'delete', 'client'))
        assert not hasattr(app.state, 'social_native_registration')
        assert not hasattr(app.state, 'social_media_runtime')
    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()
