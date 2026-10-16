"""Explicit Meta v26 metrics reads. No scheduler, uploads, writes or paid APIs."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID
import asyncio
import hashlib
import json

import httpx
from pydantic import Field
from sqlalchemy import select

from ..adapters.config import MetaAdapterConfig
from ..adapters.meta_http import MetaHTTP, remote_id
from ..connections.crypto import CredentialCipher
from ..connections.models import SocialCredential
from ..contracts import Hash, StrictModel, ResolvedPostPayload, canonical_hash
from ..models import SocialAccount, SocialPostTarget
from ..service import SocialError, utc
from .contracts import Metric, MetricRequest

METRICS = {
    'facebook': {'post_media_view': 'count', 'post_total_media_view_unique': 'unique_accounts', 'post_clicks': 'count'},
    'instagram': {'views': 'count', 'reach': 'unique_accounts', 'saved': 'count', 'shares': 'count', 'total_interactions': 'count'},
}
PRODUCTS = {'facebook': 'facebook_pages', 'instagram': 'instagram_graph_facebook_login'}
SCOPES = {'facebook': {'read_insights', 'pages_read_engagement'},
          'instagram': {'instagram_basic', 'instagram_manage_insights', 'pages_read_engagement'}}


class CollectionCommand(StrictModel):
    """One exact generation, not permission to scan all accounts or targets."""
    account_id: UUID
    credential_id: UUID
    credential_version: Annotated[int, Field(strict=True, gt=0)]
    parent_credential_id: UUID
    parent_credential_version: Annotated[int, Field(strict=True, gt=0)]
    payload_hash: Hash
    remote_id: Annotated[str, Field(strict=True, min_length=1, max_length=512)]
    runtime_hash: Hash


def parse_insights(value, platform, now):
    """Only scalar lifetime metrics; the provider supplies no exact window dates."""
    if platform not in METRICS or type(value) is not dict or type(value.get('data')) is not list or len(value['data']) > 20 or 'error' in value:
        raise ValueError('Invalid insights response')
    found = {}
    ends = {}
    for item in value['data']:
        if (type(item) is not dict or item.get('name') not in METRICS[platform]
                or item['name'] in found or item.get('period') != 'lifetime'
                or type(item.get('values')) is not list or len(item['values']) != 1
                or type(item['values'][0]) is not dict or not {'value'} <= set(item['values'][0]) <= {'value', 'end_time'}
                or type(item['values'][0]['value']) is not int or not 0 <= item['values'][0]['value'] <= 2**53-1
                or 'total_value' in item):
            raise ValueError('Invalid lifetime scalar metric')
        found[item['name']] = item['values'][0]['value']
        if 'end_time' in item['values'][0]:
            end = item['values'][0]['end_time']
            if type(end) is not str:
                raise ValueError('Invalid provider window end')
            end = datetime.fromisoformat(end.replace('Z', '+00:00'))
            if end.tzinfo is None or end > now:
                raise ValueError('Invalid provider window end')
            ends[item['name']] = end
    return tuple(Metric(name=name, api_version='v26.0', unit=unit, period='lifetime',
        window_start=None, window_end=ends.get(name), collected_at=now, available_until=now+timedelta(hours=1),
        status='available' if name in found else 'unavailable', value=found.get(name),
        reason=None if name in found else 'Provider returned no data; availability or eligibility is unknown.')
        for name, unit in METRICS[platform].items())


@dataclass(frozen=True)
class MetaMetricsPort:
    platform: str
    request_hash: str
    config: MetaAdapterConfig = field(repr=False)
    token: str = field(repr=False)
    zero_cost: Literal[True] = True

    def authorize(self, request):
        if (type(request) is not MetricRequest or request.platform != self.platform
                or canonical_hash(request.model_dump(mode='json')) != self.request_hash
                or not self.config.ready or not self.config.app_secret
                or request.deadline.tzinfo is None or not datetime.now(timezone.utc) < request.deadline <= datetime.now(timezone.utc)+timedelta(seconds=10)):
            raise ValueError('Metrics authorization expired or changed')
    def collect(self, request):
        self.authorize(request)
        return asyncio.run(self._read(request))

    async def _read(self, request, *, transport=None):
        """Private injected transport is used only by controlled endpoint tests."""
        self.authorize(request)
        graph = MetaHTTP(self.config, transport=transport if transport is not None else httpx.AsyncHTTPTransport(retries=0), now=lambda: datetime.now(timezone.utc))
        try:
            # An independent overall deadline bounds DNS/connect and trickled bodies.
            async with asyncio.timeout(max(0.001, (request.deadline-datetime.now(timezone.utc)).total_seconds())):
                response = await graph.request('GET', request.remote_id, token=self.token, edge='insights',
                    query={'metric': ','.join(METRICS[self.platform]), 'period': 'lifetime'}, maximum_bytes=request.max_response_bytes)
            return parse_insights(response.value, self.platform, datetime.now(timezone.utc))
        except Exception:
            pass  # Emit the fixed failure outside the handler so raw HTTP context cannot escape.
        finally:
            await graph.close()
        raise ValueError('Native metrics read failed')


@dataclass(frozen=True)
class AnalyticsRuntime:
    enabled: bool = False
    authorized_platforms: tuple[str, ...] = ()
    operational_gates_verified: bool = False
    free_access_verified: bool = False
    cipher: CredentialCipher | None = field(default=None, repr=False)
    app_secret: str = field(default='', repr=False)
    generation: int = 1

    def __post_init__(self):
        if type(self.generation) is not int or not 1 <= self.generation <= 2**31-1:
            raise ValueError('Invalid analytics runtime generation')
        if (any(type(v) is not bool for v in (self.enabled, self.operational_gates_verified, self.free_access_verified))
                or type(self.authorized_platforms) is not tuple or len(set(self.authorized_platforms)) != len(self.authorized_platforms)
                or any(p not in METRICS for p in self.authorized_platforms)):
            raise ValueError('Invalid analytics runtime')
        if self.enabled and (not self.authorized_platforms or not self.operational_gates_verified
                or not self.free_access_verified or not isinstance(self.cipher, CredentialCipher)
                or not isinstance(self.app_secret, str) or not 1 <= len(self.app_secret) <= 16384
                or any(ord(c) < 33 or ord(c) > 126 for c in self.app_secret)):
            raise ValueError('Verified free native analytics material is required')

    def fingerprint(self):
        sources = [Path(__file__), Path(__file__).with_name('analytics.py'), Path(__file__).with_name('contracts.py'),
                   Path(__file__).parent.parent / 'adapters' / 'meta_http.py']
        return canonical_hash({'sources': {str(p.name): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
            'enabled': self.enabled, 'platforms': self.authorized_platforms, 'generation': self.generation,
            'operational': self.operational_gates_verified, 'free': self.free_access_verified, 'version': 'v26.0'})

    def material(self, db, target, command, *, decrypt=True):
        if type(command) is not CollectionCommand or not self.enabled or command.runtime_hash != self.fingerprint():
            raise SocialError('ANALYTICS_DISABLED', 'Exact enabled native analytics runtime authorization is required.', 503)
        account = db.scalar(select(SocialAccount).where(SocialAccount.id == command.account_id).with_for_update().execution_options(populate_existing=True))
        if (not account or target.account_id != account.id or account.platform not in self.authorized_platforms
                or account.api_product != PRODUCTS[account.platform] or account.connection_method != 'facebook_login'
                or account.connection_state != 'connected' or account.credential_id != command.credential_id
                or target.state != 'published' or target.visibility_state != 'public'
                or target.primary_remote_id != command.remote_id or target.payload_hash != command.payload_hash
                or account.publish_lease_token is not None or target.lease_token is not None):
            raise SocialError('METRICS_AUTHORIZATION_CHANGED', 'The published target or account authorization changed.')
        try:
            payload = ResolvedPostPayload.model_validate(target.resolved_payload)
            if (payload.account_id != account.id or payload.platform != account.platform or payload.api_product != account.api_product
                    or payload.external_account_id != account.external_account_id or payload.content_hash != command.payload_hash
                    or canonical_hash(payload.model_dump(mode='json', exclude={'content_hash'})) != command.payload_hash
                    or (account.platform == 'facebook' and payload.format == 'reel')):
                raise ValueError()
        except Exception:
            raise SocialError('METRICS_PAYLOAD_CHANGED', 'The immutable published payload cannot be verified.') from None
        remote_id(account.external_account_id)
        remote_id(command.remote_id, composite=account.platform == 'facebook')
        if account.platform == 'facebook' and not command.remote_id.startswith(account.external_account_id + '_'):
            raise SocialError('METRICS_AUTHORIZATION_CHANGED', 'The remote post is outside the authorized Page.')
        credential = db.scalar(select(SocialCredential).where(SocialCredential.id == command.credential_id).with_for_update().execution_options(populate_existing=True))
        parent = db.scalar(select(SocialCredential).where(SocialCredential.id == command.parent_credential_id).with_for_update().execution_options(populate_existing=True))
        now = datetime.now(timezone.utc)
        for row, version, kind in ((credential, command.credential_version, 'facebook_page'), (parent, command.parent_credential_version, 'facebook_user')):
            if (not row or row.version != version or row.provider != 'meta' or row.credential_kind != kind
                    or row.revoked_at is not None or row.refresh_lease_token is not None
                    or any(v is not None and utc(v) <= now + timedelta(seconds=10) for v in (row.access_expires_at, row.data_access_expires_at))):
                raise SocialError('METRICS_CREDENTIAL_CHANGED', 'Credential generation, renewal or expiry prevents collection.')
        if credential.parent_credential_id != parent.id or type(account.granted_scopes) is not list or not SCOPES[account.platform] <= set(account.granted_scopes):
            raise SocialError('METRICS_SCOPE_REQUIRED', 'Existing credentials do not authorize these insights reads.')
        if not decrypt:
            return account.platform
        try:
            bundle = self.cipher.decrypt(credential.id, 'facebook_page', credential.key_version, credential.encrypted_bundle)
            grant = self.cipher.decrypt(parent.id, 'facebook_user', parent.key_version, parent.encrypted_bundle)
            if (set(bundle) != {'access_token', 'page_id', 'external_user_id', 'scopes'}
                    or set(grant) != {'access_token', 'external_user_id', 'scopes'}
                    or bundle['external_user_id'] != grant['external_user_id']
                    or set(bundle['scopes']) != set(account.granted_scopes)
                    or not set(bundle['scopes']) <= set(grant['scopes'])
                    or (account.platform == 'facebook' and bundle['page_id'] != account.external_account_id)):
                raise ValueError()
            # Instagram insights explicitly use the parent Facebook USER token.
            token = bundle['access_token'] if account.platform == 'facebook' else grant['access_token']
            if type(token) is not str or not 1 <= len(token) <= 16384 or any(ord(c) < 33 or ord(c) > 126 for c in token):
                raise ValueError()
            return account.platform, token
        except Exception:
            raise SocialError('METRICS_MATERIAL_UNAVAILABLE', 'Encrypted read credentials could not be verified.', 503) from None

    def prepare(self, db, target, command, request):
        if (type(request) is not MetricRequest or type(command) is not CollectionCommand
                or request.account_id != command.account_id or request.target_id != target.id
                or request.remote_id != command.remote_id
                or type(request.max_records) is not int or request.max_records != 20
                or type(request.max_response_bytes) is not int or request.max_response_bytes != 32768
                or request.deadline.tzinfo is None
                or not datetime.now(timezone.utc) < request.deadline <= datetime.now(timezone.utc)+timedelta(seconds=10)):
            raise SocialError('METRICS_REQUEST_CHANGED', 'The read request does not match its exact authorization.')
        platform, token = self.material(db, target, command)
        if request.platform != platform:
            raise SocialError('METRICS_REQUEST_CHANGED', 'The requested provider differs from its authorization.')
        return MetaMetricsPort(platform, canonical_hash(request.model_dump(mode='json')),
            MetaAdapterConfig('v26.0', True, True, self.app_secret), token)


def configured_runtime(environ=None):
    """Read existing process configuration only; never load dotenv or create keys."""
    import os
    values = os.environ if environ is None else environ
    enabled = values.get('SOCIAL_ANALYTICS_ENABLED', 'false')
    if enabled not in {'true', 'false'}:
        raise ValueError('Invalid analytics enablement')
    if enabled == 'false':
        return AnalyticsRuntime()
    if values.get('SOCIAL_ANALYTICS_OPERATIONAL_GATES_VERIFIED') != 'true' or values.get('SOCIAL_ANALYTICS_FREE_ACCESS_VERIFIED') != 'true':
        raise ValueError('Analytics operational and zero-cost gates are required')
    from ..connections.config import load_config
    config = load_config(values)
    return AnalyticsRuntime(True, tuple(values.get('SOCIAL_ANALYTICS_PLATFORMS', '').split(',')), True, True,
        CredentialCipher(config.active_key_version, config.encryption_keys), config.app_secret, int(values['SOCIAL_ANALYTICS_GENERATION']))


def request_analytics_runtime(request):
    runtime = getattr(request.app.state, 'social_analytics_runtime', None)
    if runtime is None:
        return AnalyticsRuntime()
    if type(runtime) is not AnalyticsRuntime:
        raise SocialError('ANALYTICS_CONFIGURATION_INVALID', 'Native analytics configuration is invalid.', 503)
    return runtime


def capability_status(db, runtime):
    """A fixture registry or enabled flag alone cannot advertise collection."""
    if not runtime.enabled:
        return False, 'Native metrics collection is disabled. Stored observations remain readable.'
    # Bounded metadata-only admission. No provider reads or credential writes.
    targets = db.scalars(select(SocialPostTarget).join(SocialAccount, SocialAccount.id == SocialPostTarget.account_id).where(
        SocialAccount.platform.in_(runtime.authorized_platforms), SocialAccount.connection_state == 'connected',
        SocialPostTarget.state == 'published', SocialPostTarget.visibility_state == 'public').order_by(SocialPostTarget.id).limit(50)).all()
    for target in targets:
        account = db.get(SocialAccount, target.account_id)
        credential = db.get(SocialCredential, account.credential_id) if account.credential_id else None
        parent = db.get(SocialCredential, credential.parent_credential_id) if credential and credential.parent_credential_id else None
        if credential is None or parent is None:
            continue
        try:
            command = CollectionCommand(account_id=account.id, credential_id=credential.id, credential_version=credential.version,
                parent_credential_id=parent.id, parent_credential_version=parent.version, payload_hash=target.payload_hash,
                remote_id=target.primary_remote_id, runtime_hash=runtime.fingerprint())
            runtime.material(db, target, command)
        except (SocialError, ValueError, TypeError):
            continue
        return True, 'Native zero-cost collection is available for an authorized published Meta target. Use the explicit one-target operator command; account quotas still apply.'
    return False, 'No eligible native target found in the bounded capability check (50 targets maximum). Check product, existing insights permissions, credential generations and expiry. X, Threads and TikTok metrics are unavailable.'
