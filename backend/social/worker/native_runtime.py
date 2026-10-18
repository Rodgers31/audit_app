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
        import asyncio
        failed = cancelled = False
        for adapter in self.adapters.values():
            try:
                await adapter.close()
            except asyncio.CancelledError:
                cancelled = True
            except Exception:
                failed = True
        if cancelled:
            raise asyncio.CancelledError()
        if failed:
            raise RuntimeError('Native adapter shutdown failed')


def create_native_registration(engine, config, *, cipher, storage, storage_origin, transport_factory):
    import re
    from sqlalchemy.engine import Engine
    from ..connections.crypto import CredentialCipher
    from ..adapters import MetaAdapterConfig, FacebookPageAdapter, InstagramFacebookLoginAdapter
    from ..adapters.config import native_app_material_valid
    if not isinstance(config, MetaAdapterConfig):
        raise ValueError('Explicit native adapter configuration is required')
    if not config.ready:
        return NativeRegistration(MappingProxyType({}), None, None)
    if (not native_app_material_valid(config)
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


def create_platform_registration(engine, configurations, *, cipher, storage, storage_origin,
                                 transport_factory, connection_configurations=None, tiktok_verified_origins=()):
    """Explicit platform composition; no registration or network at import/startup.

    Merge the returned adapters into the same API and worker registration. The
    durable repository still admits every operation and reserves every X read.
    """
    from sqlalchemy.engine import Engine
    from ..adapters import ThreadsAdapter, ThreadsAdapterConfig, XAdapter, XAdapterConfig, TikTokAccountsAdapter, TikTokAdapterConfig
    from ..connections.crypto import CredentialCipher
    from ..platform_materials import PlatformCredentialMaterialLoader
    definitions = {'threads':(ThreadsAdapterConfig,ThreadsAdapter,'threads'),
        'x':(XAdapterConfig,XAdapter,'x_api_v2'),
        'tiktok':(TikTokAdapterConfig,TikTokAccountsAdapter,'tiktok_accounts_api')}
    if not isinstance(configurations, dict) or set(configurations)-definitions.keys():
        raise ValueError('Explicit supported platform configuration required')
    for name,config in configurations.items():
        if not isinstance(config,definitions[name][0]):
            raise ValueError('Invalid platform configuration')
    enabled={name:config for name,config in configurations.items() if config.ready}
    if not enabled:
        return NativeRegistration(MappingProxyType({}),None,None)
    if (not isinstance(engine,Engine) or not isinstance(cipher,CredentialCipher)
            or not callable(transport_factory) or getattr(storage,'provider',None) != 'r2'
            or not isinstance(storage_origin,str) or not storage_origin or '/' in storage_origin
            or getattr(storage,'origin',storage_origin) != storage_origin
            or any(not callable(getattr(storage,name,None)) for name in ('head','download','preview'))):
        raise ValueError('Verified platform material and media ports required')
    adapters={(name,definitions[name][2]):definitions[name][1](config,transport=transport_factory()) for name,config in enabled.items()}
    return NativeRegistration(MappingProxyType(adapters),
        PlatformCredentialMaterialLoader(engine,cipher,connection_configurations or {},tiktok_verified_origins=tiktok_verified_origins),
        VerifiedMediaAccess(engine,storage,allowed_origin=storage_origin,allow_long_provider_fetch='tiktok' in enabled))


def combine_native_registrations(meta, platforms):
    from ..platform_materials import CombinedCredentialLoader
    if not isinstance(meta,NativeRegistration) or not isinstance(platforms,NativeRegistration) or meta.adapters.keys() & platforms.adapters.keys():
        raise ValueError('Distinct native registrations required')
    return NativeRegistration(MappingProxyType({**meta.adapters,**platforms.adapters}),
        CombinedCredentialLoader(meta.credential_loader,platforms.credential_loader),platforms.media_access or meta.media_access)
