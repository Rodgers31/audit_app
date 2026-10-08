"""Explicit construction only; importing this module enables no providers."""
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .materials import CredentialMaterialLoader, VerifiedMediaAccess


@dataclass(frozen=True)
class NativeRegistration:
    adapters: Mapping
    credential_loader: CredentialMaterialLoader | None
    media_access: VerifiedMediaAccess | None

    async def close(self):
        for adapter in self.adapters.values():
            await adapter.close()


def create_native_registration(engine, config, *, cipher, storage, storage_origin, transport_factory):
    import re
    from sqlalchemy.engine import Engine
    from ..connections.crypto import CredentialCipher
    from ..adapters import MetaAdapterConfig, FacebookPageAdapter, InstagramFacebookLoginAdapter
    if not isinstance(config, MetaAdapterConfig):
        raise ValueError('Explicit native adapter configuration is required')
    if not config.ready:
        return NativeRegistration(MappingProxyType({}), None, None)
    if (not config.app_secret or any(ord(c) < 33 or ord(c) > 126 for c in config.app_secret)
            or not callable(transport_factory) or not isinstance(engine, Engine)
            or not isinstance(cipher, CredentialCipher) or getattr(storage, 'provider', None) != 'r2'
            or not isinstance(getattr(storage, 'bucket', None), str)
            or not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', storage.bucket)
            or not isinstance(storage_origin, str) or not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,251}[a-z0-9]', storage_origin)
            or any(not callable(getattr(storage, name, None)) for name in ('head', 'download', 'preview'))
            or (getattr(storage, 'origin', storage_origin) != storage_origin)):
        raise ValueError('Explicit verified application material and transport are required')
    adapters = {('facebook', 'facebook_pages'): FacebookPageAdapter(config, transport=transport_factory()),
                ('instagram', 'instagram_graph_facebook_login'): InstagramFacebookLoginAdapter(config, transport=transport_factory())}
    return NativeRegistration(MappingProxyType(adapters), CredentialMaterialLoader(engine, cipher),
                              VerifiedMediaAccess(engine, storage, allowed_origin=storage_origin))


def registered_adapters(request):
    """Optional server-injected registration, with no environment fallback."""
    registration = getattr(request.app.state, 'social_native_registration', None)
    if registration is None:
        return frozenset()
    if not isinstance(registration, NativeRegistration):
        from ..service import SocialError
        raise SocialError('ADAPTER_CONFIGURATION_INVALID', 'The configured native adapter registry is unavailable.', 503)
    return registration.adapters
