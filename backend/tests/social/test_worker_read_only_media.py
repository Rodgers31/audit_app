"""Native composition must not require HTTP upload enablement (#700)."""
import asyncio
import base64
import json
import socket
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine

from social.worker.startup import validate_worker_native_environment, native_runtime, installed_native_runtime


def values():
    return dict(SOCIAL_NATIVE_ENABLED='true', SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED='true',
        SOCIAL_WORKER_MEDIA_READS_ENABLED='true', SOCIAL_MEDIA_ENABLED='false',
        META_CONNECTIONS_ENABLED='true', META_APP_CONFIGURATION_VALIDATED='true',
        META_APP_ID='123', META_APP_SECRET='inert-secret', META_ACCESS_MODE='owned_standard',
        META_REDIRECT_URIS='["https://admin.example.test/admin/social/accounts/callback"]',
        SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION='v1',
        SOCIAL_CREDENTIAL_KEYS=json.dumps({'v1': base64.urlsafe_b64encode(b'0' * 32).decode()}),
        SOCIAL_MEDIA_R2_ENDPOINT='https://' + 'a' * 32 + '.r2.cloudflarestorage.com',
        SOCIAL_MEDIA_BUCKET='media-test', SOCIAL_MEDIA_ACCESS_KEY='inert-access',
        SOCIAL_MEDIA_SECRET_KEY='inert-storage-secret', AWS_EC2_METADATA_DISABLED='true')


def test_native_read_preflight_accepts_uploads_off_only_with_explicit_read_gate():
    validate_worker_native_environment(values())
    for flag in ('false', '', 'TRUE', '1'):
        with pytest.raises(ValueError):
            validate_worker_native_environment(dict(values(), SOCIAL_WORKER_MEDIA_READS_ENABLED=flag))
    missing = values()
    del missing['SOCIAL_WORKER_MEDIA_READS_ENABLED']
    with pytest.raises(ValueError):
        validate_worker_native_environment(missing)
    for key in ('SOCIAL_MEDIA_R2_ENDPOINT', 'SOCIAL_MEDIA_BUCKET', 'SOCIAL_MEDIA_ACCESS_KEY', 'SOCIAL_MEDIA_SECRET_KEY'):
        with pytest.raises(ValueError):
            validate_worker_native_environment(dict(values(), **{key: ''}))


def test_real_sdk_read_composition_exposes_no_storage_write_and_keeps_http_upload_runtime_off(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Paused native composition performed network IO')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    engine = create_engine('sqlite://')  # Construction only, no DB access at this seam.
    app = SimpleNamespace(state=SimpleNamespace())

    async def exercise():
        async with installed_native_runtime(app, engine, environ=values()) as registration:
            assert registration is not None
            assert app.state.social_media_runtime.config.enabled is False
            assert app.state.social_media_runtime.storage is None
            port = registration.media_access.storage
            assert all(callable(getattr(port, name, None)) for name in ('head', 'download', 'preview'))
            assert all(not hasattr(port, name) for name in ('authorize_upload', 'finalize', 'delete', 'client'))
        assert not hasattr(app.state, 'social_media_runtime')
        assert not hasattr(app.state, 'social_native_registration')
    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()
