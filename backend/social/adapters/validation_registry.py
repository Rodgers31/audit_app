"""Local native validation only; constructs no delivery clients or material.

This does not attest storage, credentials for an account, or worker readiness.
The worker independently requires its installed runtime at mutation admission.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
import os

from ..service import SocialError
from .config import MetaAdapterConfig, native_app_material_valid
from .meta_validation import FacebookPageValidation, InstagramFacebookLoginValidation


@dataclass(frozen=True)
class NativeValidationRegistry:
    adapters: Mapping


def load_native_validation_registry(environ=None):
    values = os.environ if environ is None else environ
    invalid = False
    try:
        enabled = values.get('SOCIAL_NATIVE_ENABLED', 'false')
        verified = values.get('SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED', 'false')
        if enabled not in ('true', 'false') or verified not in ('true', 'false'):
            raise ValueError()
        if enabled == 'false':
            return None
        if verified != 'true':
            raise ValueError()
        # Reuse the actual Meta configuration validator, including app-access,
        # API version and in-memory encryption configuration checks. No SDK or
        # R2/media/web-upload runtime is needed to validate factual text.
        from ..connections.config import load_config
        config = load_config(values)
        config.require_ready()
        rules = MetaAdapterConfig(config.graph_version, True, True, config.app_secret)
        if not native_app_material_valid(rules):
            raise ValueError()
        return NativeValidationRegistry(MappingProxyType({
            ('facebook', 'facebook_pages'): FacebookPageValidation(rules),
            ('instagram', 'instagram_graph_facebook_login'): InstagramFacebookLoginValidation(rules),
        }))
    except (ValueError, TypeError, SocialError):
        invalid = True
    if invalid:
        # Do not retain a secret-bearing decoder exception as public context.
        raise SocialError('NATIVE_CONFIGURATION_INVALID', 'Native validation configuration is unavailable.', 503)


def registry_adapters(registration, engine, *, borrowed=False):
    """Validate the trusted typed port; never accept legacy platform-name sets."""
    if not borrowed:
        typed = isinstance(registration, NativeValidationRegistry)
    else:
        from ..worker.native_runtime import NativeRegistration
        from ..worker.materials import CredentialMaterialLoader, VerifiedMediaAccess
        typed = (isinstance(registration, NativeRegistration)
            and isinstance(registration.credential_loader, CredentialMaterialLoader)
            and registration.credential_loader.engine is engine
            and isinstance(registration.media_access, VerifiedMediaAccess))
    adapters = getattr(registration, 'adapters', None)
    if not typed or not isinstance(adapters, Mapping) or not adapters:
        raise SocialError('NATIVE_REGISTRY_INVALID', 'A nonempty native validation registry is required.', 503)
    snapshot = dict(adapters)
    for key, adapter in snapshot.items():
        pure_valid = True
        if isinstance(registration, NativeValidationRegistry):
            pure_valid = False
            config = getattr(adapter, 'config', None)
            if isinstance(config, MetaAdapterConfig):
                try:
                    checked = MetaAdapterConfig(config.graph_version, config.enabled,
                        config.operational_gates_verified, config.app_secret)
                    pure_valid = (type(adapter) is {
                        ('facebook', 'facebook_pages'): FacebookPageValidation,
                        ('instagram', 'instagram_graph_facebook_login'): InstagramFacebookLoginValidation,
                    }.get(key) and checked.ready and native_app_material_valid(checked))
                except (ValueError, TypeError):
                    pass
        if (not isinstance(key, tuple) or len(key) != 2
                or any(not isinstance(part, str) or not part for part in key)
                or key != (getattr(adapter, 'platform', None), getattr(adapter, 'product', None))
                or not callable(getattr(adapter, 'capabilities', None))
                or not callable(getattr(adapter, 'validate', None))
                or not pure_valid):
            raise SocialError('NATIVE_REGISTRY_INVALID', 'The native validation registry is malformed.', 503)
    return MappingProxyType(snapshot)
