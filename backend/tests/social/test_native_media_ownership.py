"""Actual HTTP media and status routes share lifecycle-owned storage clients."""
from contextlib import asynccontextmanager
from uuid import uuid4

import boto3
from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy.orm import Session

from social.api import router as social_router
from social.http_boundary import AdminUser, get_db, require_admin
from social.media.api import router as media_router
from social.media.config import MediaConfig
import social.media.runtime as media_module
from social.worker.startup import installed_native_runtime
from test_media_support import ACTOR, ENDPOINT, media_db
from test_native_startup import ready


@pytest.mark.parametrize('native', [False, True])
def test_http_media_and_status_share_one_client_and_close_it_once(media_db, monkeypatch, native):
    module = ready(monkeypatch)
    cfg = MediaConfig(enabled=True, endpoint=ENDPOINT, bucket='media-test', access_key='fixture', secret_key='fixture')
    monkeypatch.setattr(media_module, 'config_from_environment', lambda *args: cfg)
    monkeypatch.setattr(module, 'load_media_runtime', lambda values: media_module.build_media_runtime(cfg))
    actual_client = boto3.client
    clients, closes = [], []
    def sdk(*args, **kwargs):
        client = actual_client(*args, **kwargs)
        clients.append(client)
        original = client.close
        def close():
            closes.append(client)
            original()
        client.close = close
        return client
    monkeypatch.setattr(boto3, 'client', sdk)
    values = {'SOCIAL_NATIVE_ENABLED':'true' if native else 'false',
              'SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED':'true' if native else 'false'}
    @asynccontextmanager
    async def lifespan(app):
        async with installed_native_runtime(app, media_db.bind, environ=values,
                transport_factory=lambda: httpx.MockTransport(lambda r: pytest.fail('Unexpected Meta request'))):
            yield
    app = FastAPI(lifespan=lifespan)
    app.include_router(media_router); app.include_router(social_router)
    def database():
        with Session(media_db.bind, expire_on_commit=False) as db: yield db
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[require_admin] = lambda: AdminUser(id=str(ACTOR),email=None,roles=['admin'])
    media_module.media_runtime.cache_clear()
    try:
        with TestClient(app) as client:
            caps = client.get('/api/v1/admin/social/media/capabilities')
            status = client.get('/api/v1/admin/social/system/status')
            assert caps.status_code == status.status_code == 200
            assert caps.json()['upload_available'] and status.json()['media_upload_available']
        assert len(clients) == 1, 'Startup, media routes and status constructed separate R2 clients'
        assert closes == clients, 'The HTTP media client escaped app shutdown'
        assert not hasattr(app.state,'social_media_runtime')
    finally:
        media_module.media_runtime.cache_clear()
        for client in clients:
            if client not in closes: client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('native', [False, True])
async def test_app_shutdown_preserves_cancellation_when_sdk_close_fails(media_db, monkeypatch, native):
    import asyncio
    from types import SimpleNamespace
    module = ready(monkeypatch)
    runtime = module.load_media_runtime({})
    runtime.storage.client.close.side_effect = RuntimeError('PRIVATE_SDK_CLOSE_MARKER')
    app = SimpleNamespace(state=SimpleNamespace())
    with pytest.raises(asyncio.CancelledError):
        async with installed_native_runtime(app, media_db.bind,
                environ={'SOCIAL_NATIVE_ENABLED':'true' if native else 'false',
                         'SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED':'true' if native else 'false'},
                transport_factory=lambda: httpx.MockTransport(lambda r: pytest.fail('Meta request'))):
            raise asyncio.CancelledError()
    assert runtime.storage.client.close.call_count == 1
    assert not hasattr(app.state,'social_media_runtime')
    assert not hasattr(app.state,'social_native_registration')
