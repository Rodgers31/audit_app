"""Explicit, default-off native composition. Starts no worker or scheduler."""
from contextlib import asynccontextmanager
import asyncio
import os
import sys

from ..adapters import MetaAdapterConfig
from ..connections.config import load_config as load_meta_config
from ..connections.crypto import CredentialCipher
from ..media.config import config_from_environment
from ..media.config import MediaConfig
from ..media.runtime import MediaRuntime, build_media_runtime
from ..media.storage import R2Storage
from ..service import SocialError
from .native_runtime import create_native_registration


def load_media_runtime(values):
    return build_media_runtime(config_from_environment(values))


def validate_worker_native_environment(values):
    """Pure preflight before reserving authority or constructing any SDK."""
    if (values.get('SOCIAL_NATIVE_ENABLED', 'false') != 'true'
            or values.get('SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED', 'false') != 'true'):
        raise ValueError('Native worker gates are not accepted')
    load_meta_config(values).require_ready()
    if not config_from_environment(values).enabled:
        raise ValueError('Private media gates are not accepted')


async def _close(registration, transports, runtime):
    failed = cancelled = False
    closers = [registration.close] if registration is not None else [item.aclose for item in transports]
    for close in closers:
        try:
            await close()
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            failed = True
    if runtime is not None and isinstance(runtime.storage, R2Storage):
        try:
            runtime.storage.client.close()
        except Exception:
            failed = True
    return failed, cancelled


@asynccontextmanager
async def native_runtime(engine, *, environ=None, transport_factory=None, shared_media_runtime=None):
    values = os.environ if environ is None else environ
    registration = None
    runtime = None
    transports = []
    invalid = False
    try:
        enabled = values.get('SOCIAL_NATIVE_ENABLED', 'false')
        verified = values.get('SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED', 'false')
        if enabled not in ('true', 'false') or verified not in ('true', 'false'):
            raise ValueError()
        if enabled == 'true':
            if verified != 'true':
                raise ValueError()
            config = load_meta_config(values)
            config.require_ready()
            selected_runtime = shared_media_runtime
            if selected_runtime is None:
                runtime = selected_runtime = load_media_runtime(values)
            if (not isinstance(selected_runtime, MediaRuntime) or not selected_runtime.config.enabled
                    or not isinstance(selected_runtime.storage, R2Storage)
                    or not {'image/jpeg', 'image/png'} <= set(selected_runtime.available_mimes())):
                raise ValueError()
            if transport_factory is None:
                import httpx
                transport_factory = lambda: httpx.AsyncHTTPTransport(retries=0,
                    limits=httpx.Limits(max_connections=2, max_keepalive_connections=2))
            def transport():
                result = transport_factory()
                transports.append(result)
                return result
            registration = create_native_registration(engine,
                MetaAdapterConfig(config.graph_version, True, True, config.app_secret),
                cipher=CredentialCipher(config.active_key_version, config.encryption_keys),
                storage=selected_runtime.storage, storage_origin=selected_runtime.storage.origin,
                transport_factory=transport)
    except Exception:
        # Raise after leaving the handler; secret-bearing decoder/SDK exceptions
        # must not survive as __context__ on a public startup error.
        invalid = True
    if invalid:
        _, cancelled = await _close(registration, transports, runtime)
        if cancelled:
            raise asyncio.CancelledError()
        raise SocialError('NATIVE_CONFIGURATION_INVALID',
            'Explicit validated Meta and private-media configuration is required.', 503)
    try:
        yield registration
    finally:
        pending_cancel = isinstance(sys.exc_info()[1], asyncio.CancelledError)
        failed, cancelled = await _close(registration, transports, runtime)
        if cancelled or pending_cancel:
            raise asyncio.CancelledError()
        if failed:
            raise SocialError('NATIVE_SHUTDOWN_FAILED', 'Native resources could not all be closed.', 503)


@asynccontextmanager
async def installed_native_runtime(app, engine, **kwargs):
    if hasattr(app.state, 'social_native_registration') or hasattr(app.state, 'social_media_runtime'):
        raise SocialError('NATIVE_CONFIGURATION_INVALID', 'Native adapters are already installed.', 503)
    values = kwargs.get('environ')
    values = os.environ if values is None else values
    try:
        shared = load_media_runtime(values)
    except Exception:
        shared = MediaRuntime(MediaConfig(), None, None, 'Media storage or inspection configuration is unavailable.')
    try:
        app.state.social_media_runtime = shared
        async with native_runtime(engine, shared_media_runtime=shared, **kwargs) as registration:
            if registration is not None:
                app.state.social_native_registration = registration
            try:
                yield registration
            finally:
                if registration is not None and getattr(app.state, 'social_native_registration', None) is registration:
                    del app.state.social_native_registration
                if getattr(app.state, 'social_media_runtime', None) is shared:
                    del app.state.social_media_runtime
    finally:
        pending_cancel = isinstance(sys.exc_info()[1], asyncio.CancelledError)
        if getattr(app.state, 'social_media_runtime', None) is shared:
            del app.state.social_media_runtime
        failed, cancelled = await _close(None, [], shared)
        if cancelled or pending_cancel:
            raise asyncio.CancelledError()
        if failed:
            raise SocialError('NATIVE_SHUTDOWN_FAILED', 'Native resources could not all be closed.', 503)
