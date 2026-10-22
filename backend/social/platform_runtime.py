"""Default-off platform policy and explicit credential composition, no I/O."""
from dataclasses import dataclass
import json

from pydantic import Field, StrictBool, StrictStr

from .contracts import StrictModel
from .adapters import ThreadsAdapterConfig, XAdapterConfig, TikTokAdapterConfig
from .adapters.tiktok_oauth import TikTokOAuthConfig
from .connections.crypto import CredentialCipher
from .connections.callback_ingress import verified_callbacks
from .platform_connections.config import ConnectionConfig
from .platform_events import EventConfig
from .service import SocialError


class PlatformPolicy(StrictModel):
    connections_enabled: StrictBool = False
    threads_insights_enabled: StrictBool = False
    adapter_enabled: StrictBool = False
    access_verified: StrictBool = False
    operational_gates_verified: StrictBool = False
    unattended_publication_verified: StrictBool = False
    media_uploads_enabled: StrictBool = False
    connection_budget_microusd: int = Field(default=0,strict=True,ge=0)
    media_request_cost_microusd: int | None = Field(default=None,strict=True,gt=0)
    verified_origins: tuple[StrictStr,...] = ()
    authorization_url: StrictStr = ''
    scopes: tuple[StrictStr,...] = ()
    events_enabled: StrictBool = False
    subscription_verified: StrictBool = False
    subscriptions: tuple[tuple[StrictStr,StrictStr],...] = ()
    account_ids: tuple[StrictStr,...] = ()


@dataclass(frozen=True)
class PlatformRuntimeSettings:
    connections: dict
    adapters: dict
    events: dict
    cipher: CredentialCipher | None
    tiktok_verified_origins: tuple[str,...] = ()



def _configuration_json(value):
    """Duplicate keys never choose a different operational policy silently."""
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError('Ambiguous configuration key')
            result[key] = item
        return result
    return json.loads(value, object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite configuration value')))

def load_platform_settings(values):
    """Only named policy/configuration inputs; no dotenv, grants or provisioning.

    SOCIAL_PLATFORM_POLICY is an object keyed threads/x/tiktok. Credentials and
    callbacks use <PLATFORM>_CLIENT_ID/_CLIENT_SECRET/_REDIRECT_URIS. Missing
    policy constructs no provider, key ring, media SDK or HTTP client.
    """
    try:
        raw=_configuration_json(values.get('SOCIAL_PLATFORM_POLICY','{}'))
        if not isinstance(raw,dict) or set(raw)-{'threads','x','tiktok'}:
            raise ValueError()
        if not raw:
            return PlatformRuntimeSettings({}, {}, {}, None)
        policies={name:PlatformPolicy.model_validate(policy) for name,policy in raw.items()}
        keys=_configuration_json(values.get('SOCIAL_CREDENTIAL_KEYS','{}'))
        active=values.get('SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION','')
        if (not isinstance(keys,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in keys.items())
                or not isinstance(active,str)):
            raise ValueError()
        connections,adapters,events={},{},{}
        origins=()
        for name,policy in policies.items():
            prefix=name.upper()
            ingress=verified_callbacks(values.get(prefix+'_VERIFIED_CALLBACK_INGRESS_URIS','[]'))
            redirects=_configuration_json(values.get(prefix+'_REDIRECT_URIS','[]'))
            if not isinstance(redirects,list) or any(not isinstance(v,str) for v in redirects):
                raise ValueError()
            client_id,secret=values.get(prefix+'_CLIENT_ID',''),values.get(prefix+'_CLIENT_SECRET','')
            if not isinstance(client_id,str) or not isinstance(secret,str):
                raise ValueError()
            tiktok=None
            if name=='tiktok' and (policy.connections_enabled or policy.adapter_enabled):
                if len(redirects)!=1:
                    raise ValueError()
                tiktok=TikTokOAuthConfig(client_id,secret,redirects[0],policy.authorization_url,policy.access_verified)
                origins=policy.verified_origins
                from .adapters.tiktok import verified_fetch_url
                if policy.adapter_enabled and (not origins or any(verified_fetch_url(origin+'fixture',origins) is None for origin in origins)):
                    raise ValueError()
            config=ConnectionConfig(platform=name,enabled=policy.connections_enabled,access_verified=policy.access_verified,
                client_id=client_id,client_secret=secret,redirect_uris=tuple(redirects),active_key_version=active,encryption_keys=keys,
                connection_budget_microusd=policy.connection_budget_microusd,tiktok_oauth=tiktok,tiktok_requested_scopes=policy.scopes,threads_insights_enabled=policy.threads_insights_enabled,verified_callback_ingress_uris=ingress)
            if policy.connections_enabled:
                config.require_ready()
            connections[name]=config
            if name=='threads':
                adapter=ThreadsAdapterConfig(enabled=policy.adapter_enabled,operational_gates_verified=policy.operational_gates_verified,media_uploads_enabled=policy.media_uploads_enabled)
            elif name=='x':
                adapter=XAdapterConfig(enabled=policy.adapter_enabled,operational_gates_verified=policy.operational_gates_verified,
                    media_uploads_enabled=policy.media_uploads_enabled,media_request_cost_microusd=policy.media_request_cost_microusd)
            else:
                adapter=TikTokAdapterConfig(enabled=policy.adapter_enabled,operational_gates_verified=policy.operational_gates_verified,product_access_verified=policy.access_verified,unattended_publication_verified=policy.unattended_publication_verified)
            if policy.adapter_enabled and (not policy.access_verified or not adapter.ready):
                raise ValueError()
            adapters[name]=adapter
            if policy.events_enabled:
                if name=='x':
                    raise ValueError()
                event=EventConfig(name,True,policy.subscription_verified,policy.access_verified,client_id,secret,
                    values.get(prefix+'_WEBHOOK_VERIFY_TOKEN',''),policy.subscriptions,policy.account_ids)
                event.require_ready()
                events[name]=event
        required=any(p.connections_enabled or p.adapter_enabled for p in policies.values())
        return PlatformRuntimeSettings(connections,adapters,events,CredentialCipher(active,keys) if required else None,origins)
    except Exception:
        pass
    raise SocialError('PLATFORM_CONFIGURATION_INVALID','Explicit validated platform policy and stable server configuration are required.',503)
