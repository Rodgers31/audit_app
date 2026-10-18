"""Dormant own-post Threads / Accounts API counts; no publishing authority.

One exact request, one page, no retries. Reuse the existing provider transports.
The durable collection reservation must precede constructing these clients.
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import httpx
from sqlalchemy import select

from ..adapters.meta_http import MetaHTTPFailure, remote_id
from ..adapters.threads import ThreadsAdapter, ThreadsAdapterConfig
from ..adapters.tiktok_http import TikTokHTTP, TikTokHTTPFailure, identity
from ..contracts import ResolvedPostPayload, canonical_hash
from ..models import SocialAccount
from ..platform_connections.models import PlatformCredential
from ..platform_connections.provider import token
from ..service import SocialError, utc
from .contracts import Metric, MetricRequest

COUNTS = {
    'threads': {'views': 'count', 'likes': 'count', 'replies': 'count', 'reposts': 'count', 'quotes': 'count', 'shares': 'count'},
    'tiktok': {'likes': 'count', 'comments': 'count', 'shares': 'count', 'favorites': 'count', 'reach': 'unique_accounts', 'video_views': 'count'},
}
VERSIONS = {'threads': 'v1.0', 'tiktok': 'v1.3'}
SCOPES = {'threads': {'threads_basic', 'threads_manage_insights'}, 'tiktok': {'video.list'}}
PRODUCTS = {'threads': 'threads', 'tiktok': 'tiktok_accounts_api'}
FORMATS = {'threads': {'text', 'image', 'carousel', 'video'}, 'tiktok': {'video'}}
RATE_HOLD = 'Provider rate limited; collection held pending operator review.'
RATE_PREFIX = 'Provider rate limited; retry after '


def rate_limit_reason(next_at, now):
    if not isinstance(next_at, datetime) or next_at.tzinfo is None or next_at <= now:
        return RATE_HOLD
    return RATE_PREFIX + next_at.isoformat()


def check_read_hold(reason, now):
    """Durable server Retry-After survives restart; missing timing never retries."""
    if reason == RATE_HOLD:
        raise SocialError('METRICS_RATE_LIMITED', reason, 429)
    if isinstance(reason, str) and reason.startswith(RATE_PREFIX):
        try:
            after = datetime.fromisoformat(reason[len(RATE_PREFIX):])
            if after.tzinfo is None:
                raise ValueError()
        except ValueError:
            raise SocialError('METRICS_RATE_LIMITED', RATE_HOLD, 429) from None
        if now < after:
            raise SocialError('METRICS_RATE_LIMITED', reason, 429)


def unavailable(platform, now, reason):
    return tuple(Metric(name=name, api_version=VERSIONS[platform], unit=unit, period='lifetime',
        window_start=None, window_end=None, collected_at=now, available_until=now+timedelta(hours=1),
        status='unavailable', value=None, reason=reason) for name, unit in COUNTS[platform].items())


def parse_counts(value, platform, remote, now):
    """Strict finite integer counts only; missing/null is unknown, never zero."""
    if platform not in COUNTS or type(value) is not dict:
        raise ValueError('Invalid native metric response')
    remote_id(remote)
    found = {}
    if platform == 'threads':
        if 'error' in value or 'paging' in value or type(value.get('data')) is not list or len(value['data']) > len(COUNTS[platform]):
            raise ValueError('Invalid single-page insights')
        for item in value['data']:
            if (type(item) is not dict or type(item.get('name')) is not str or item['name'] not in COUNTS[platform]
                    or item['name'] in found or item.get('period') != 'lifetime' or 'total_value' in item
                    or type(item.get('values')) is not list or len(item['values']) != 1
                    or type(item['values'][0]) is not dict or set(item['values'][0]) != {'value'}
                    or item.get('id') != f"{remote}/insights/{item['name']}/lifetime"):
                raise ValueError('Invalid own-post lifetime insight')
            found[item['name']] = item['values'][0]['value']
    else:
        if (type(value.get('videos')) is not list or len(value['videos']) > 1
                or value.get('has_more') is not False or type(value.get('cursor')) is not int or value['cursor'] < 0):
            raise ValueError('Incomplete exact-target Accounts page')
        if value['videos']:
            item = value['videos'][0]
            if type(item) is not dict or item.get('item_id') != remote or item.get('media_type') != 'VIDEO':
                raise ValueError('Wrong Accounts post identity or format')
            found = {k: v for k, v in item.items() if k in COUNTS[platform]}
    if any(v is not None and (type(v) is not int or not 0 <= v <= 2**53-1) for v in found.values()):
        raise ValueError('Invalid scalar count')
    return tuple(Metric(name=name, api_version=VERSIONS[platform], unit=unit, period='lifetime',
        window_start=None, window_end=None, collected_at=now, available_until=now+timedelta(hours=1),
        status='available' if found.get(name) is not None else 'unavailable', value=found.get(name),
        reason=None if found.get(name) is not None else 'Provider omitted this count; eligibility, latency or visibility is unknown.')
        for name, unit in COUNTS[platform].items())


def material(runtime, db, target, command, *, decrypt=True):
    """No inherited Meta parent credential and no publishing-scope inference."""
    account = db.scalar(select(SocialAccount).where(SocialAccount.id == command.account_id).with_for_update().execution_options(populate_existing=True))
    if (not account or account.platform not in COUNTS or account.platform not in runtime.authorized_platforms
            or account.id not in runtime.authorized_native_accounts or account.api_product != PRODUCTS[account.platform]
            or account.connection_method != account.platform + '_oauth2' or account.connection_state != 'connected'
            or target.account_id != account.id or target.state != 'published' or target.visibility_state != 'public'
            or target.primary_remote_id != command.remote_id or target.payload_hash != command.payload_hash
            or target.lease_token is not None or account.publish_lease_token is not None
            or command.parent_credential_id is not None or command.parent_credential_version is not None):
        raise SocialError('METRICS_AUTHORIZATION_CHANGED', 'The exact approved native account or public target changed.')
    try:
        payload = ResolvedPostPayload.model_validate(target.resolved_payload)
        if (payload.account_id != account.id or payload.external_account_id != account.external_account_id
                or payload.platform != account.platform or payload.api_product != account.api_product
                or payload.format not in FORMATS[account.platform] or payload.content_hash != command.payload_hash
                or canonical_hash(payload.model_dump(mode='json', exclude={'content_hash'})) != command.payload_hash):
            raise ValueError()
        remote_id(command.remote_id)
        (remote_id if account.platform == 'threads' else identity)(account.external_account_id)
    except (ValueError, TypeError):
        raise SocialError('METRICS_PAYLOAD_CHANGED', 'The immutable published product, format or identity cannot be verified.') from None
    credential = db.scalar(select(PlatformCredential).where(PlatformCredential.id == command.credential_id).with_for_update().execution_options(populate_existing=True))
    now = datetime.now(timezone.utc)
    if (not credential or credential.account_id != account.id or credential.platform != account.platform
            or credential.version != command.credential_version or credential.revoked_at is not None
            or credential.refresh_claim is not None or utc(credential.access_expires_at) <= now+timedelta(seconds=10)
            or account.platform == 'threads' and credential.data_access_expires_at is None
            or credential.data_access_expires_at is not None and utc(credential.data_access_expires_at) <= now+timedelta(seconds=10)
            or type(account.granted_scopes) is not list or any(type(s) is not str for s in account.granted_scopes)
            or not SCOPES[account.platform] <= set(account.granted_scopes)):
        raise SocialError('METRICS_CREDENTIAL_CHANGED', 'Native metric grant generation, scopes, renewal or expiry prevents collection.')
    if not decrypt:
        return account.platform
    try:
        bundle = runtime.cipher.decrypt(credential.id, f'platform:{account.platform}:credential', credential.key_version, credential.encrypted_bundle)
        if (bundle.get('subject') != account.external_account_id or type(bundle.get('scopes')) is not list
                or any(type(s) is not str for s in bundle['scopes'])
                or set(bundle['scopes']) != set(account.granted_scopes)
                or (account.platform == 'tiktok' and bundle.get('open_id') != account.external_account_id)
                or (account.platform == 'threads' and datetime.fromisoformat(bundle['data_access_expires_at']) != utc(credential.data_access_expires_at))
                or datetime.fromisoformat(bundle['expires_at']) != utc(credential.access_expires_at)):
            raise ValueError()
        return account.platform, token(bundle.get('access_token'))
    except (SocialError, ValueError, TypeError, KeyError):
        raise SocialError('METRICS_MATERIAL_UNAVAILABLE', 'Encrypted native metric credentials cannot be verified.', 503) from None


@dataclass(frozen=True)
class PlatformMetricsPort:
    platform: str
    request_hash: str
    external_account_id: str
    access_token: str = field(repr=False)
    zero_cost: bool = True

    def authorize(self, request):
        now = datetime.now(timezone.utc)
        if (self.platform not in COUNTS or self.zero_cost is not True or type(request) is not MetricRequest
                or request.platform != self.platform or canonical_hash(request.model_dump(mode='json')) != self.request_hash
                or type(request.max_records) is not int or request.max_records != 20
                or type(request.max_response_bytes) is not int or request.max_response_bytes != 32768
                or request.deadline.tzinfo is None or not now < request.deadline <= now+timedelta(seconds=10)):
            raise ValueError('Metrics read authorization changed or expired')
        remote_id(request.remote_id)
        token(self.access_token)
        (remote_id if self.platform == 'threads' else identity)(self.external_account_id)

    def collect(self, request):
        self.authorize(request)
        return asyncio.run(self._read(request))

    async def _read(self, request, *, transport=None):
        self.authorize(request)
        wire = transport if transport is not None else httpx.AsyncHTTPTransport(retries=0, trust_env=False)
        client = ThreadsAdapter(ThreadsAdapterConfig(enabled=True, operational_gates_verified=True), transport=wire) if self.platform == 'threads' else TikTokHTTP(transport=wire, now=lambda: datetime.now(timezone.utc))
        failure = None
        try:
            async with asyncio.timeout(max(.001, (request.deadline-datetime.now(timezone.utc)).total_seconds())):
                if self.platform == 'threads':
                    value = await client._request('GET', request.remote_id, SimpleNamespace(page_access_token=self.access_token),
                        edge='insights', metrics=','.join(COUNTS['threads']), maximum_bytes=request.max_response_bytes)
                else:
                    response = await client.request('GET', 'business/video/list/', token=self.access_token,
                        params={'business_id': self.external_account_id, 'fields': json.dumps(['item_id', 'media_type', *COUNTS['tiktok']]),
                                'filters': json.dumps({'video_ids': [request.remote_id]}), 'max_count': 1}, maximum_bytes=request.max_response_bytes)
                    value = response.data
                return parse_counts(value, self.platform, request.remote_id, datetime.now(timezone.utc))
        except (MetaHTTPFailure, TikTokHTTPFailure) as error:
            now = datetime.now(timezone.utc)
            if error.code == 'RATE_LIMITED' or error.http_status == 429:
                return unavailable(self.platform, now, rate_limit_reason(error.next_action_at, now))
            failure = 'Provider refused the metrics read; permissions, visibility or availability is unknown.'
        except Exception:
            failure = 'Provider collection failed or returned invalid or late observations.'
        finally:
            await client.close()
        # Raise outside the raw handler, so provider credentials cannot escape as context.
        raise ValueError(failure)
