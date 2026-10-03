"""Read-only Meta discovery and OAuth exchange. No publication endpoints exist here."""
import hashlib
import hmac
import logging
import json
import time
import re
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx

from .config import SCOPES, PAGE_SCOPES, IG_SCOPES
from ..service import SocialError


class _GraphLogRedaction(logging.Filter):
    """HTTPX logs full request URLs, including debug_token's required input_token.

    Replace Graph URL arguments before *any* handler receives them. No raw
    provider exceptions, payloads, headers or bodies are logged by this module.
    """
    def filter(self, record):
        def safe(arg):
            if isinstance(arg, httpx.URL):
                return str(arg.copy_with(query=None)) if arg.host == 'graph.facebook.com' else arg
            if isinstance(arg, str):
                return re.sub(r'https://graph\.facebook\.com/[^\s\"\']+', lambda m: urlunsplit((*urlsplit(m[0])[:3], '', '')), arg)
            return arg
        if isinstance(record.args, tuple):
            record.args = tuple(safe(arg) for arg in record.args)
        record.msg = safe(record.msg)
        return True


def install_graph_log_redaction():
    logger = logging.getLogger('httpx')
    if not any(isinstance(f, _GraphLogRedaction) for f in logger.filters):
        logger.addFilter(_GraphLogRedaction())


def _identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,64}', value):
        raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta returned an incomplete account identity. Reconnect after checking the app configuration.', 502)
    return value


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta returned an incomplete account identity.', 502)
    return value


def _expiry(value):
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta returned invalid credential expiry metadata.', 502)
    if value == 0:
        return None
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    except (OverflowError, ValueError, OSError):
        raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta returned invalid credential expiry metadata.', 502) from None


class MetaProvider:
    def __init__(self, config, *, client=None):
        config.require_ready()
        self.config = config
        install_graph_log_redaction()
        self.client = client or httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=False, trust_env=False, limits=httpx.Limits(max_connections=2, max_keepalive_connections=2))
        self.owns_client = client is None

    def close(self):
        if self.owns_client:
            self.client.close()

    def authorize_url(self, state, redirect_uri):
        self.config.require_redirect(redirect_uri)
        return f'https://www.facebook.com/{self.config.graph_version}/dialog/oauth?' + urlencode({'client_id': self.config.app_id, 'redirect_uri': redirect_uri, 'state': state, 'response_type': 'code', 'scope': ','.join(SCOPES), 'auth_type': 'rerequest'})

    def _request(self, method, path, *, token=None, params=None, data=None):
        # Path is internal, never derived from a returned provider URL.
        headers = {'Accept-Encoding': 'identity'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        try:
            request = self.client.build_request(method, f'https://graph.facebook.com/{self.config.graph_version}/{path}', params=params, data=data, headers=headers)
            response = self.client.send(request, stream=True)
            try:
                # Stream raw identity bytes before allocation; reject unexpected
                # compression rather than letting a decompression bomb expand.
                if response.headers.get('content-encoding', 'identity').lower() != 'identity':
                    raise ValueError()
                chunks, size, started = [], 0, time.monotonic()
                for chunk in response.iter_bytes(chunk_size=16384):
                    size += len(chunk)
                    if size > 1_000_000 or time.monotonic() - started > 30:
                        raise ValueError()
                    chunks.append(chunk)
                value = json.loads(b''.join(chunks))
            finally:
                response.close()
        except httpx.HTTPError:
            raise SocialError('PROVIDER_UNAVAILABLE', 'Meta could not complete this read or exchange. Restart the connection flow; an authorization code is never automatically replayed.', 502, retryable=False) from None
        except (ValueError, TypeError):
            raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta returned an invalid response. Restart the connection flow.', 502) from None
        if not isinstance(value, dict):
            raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta returned an invalid response.', 502)
        if response.status_code >= 300 or 'error' in value:
            error = value.get('error')
            code = error.get('code') if isinstance(error, dict) else None
            if code == 190:
                raise SocialError('GRANT_REVOKED', 'Meta authorization expired or was revoked. Reconnect this account.', 409)
            if code in {10, 200}:
                raise SocialError('PERMISSIONS_REQUIRED', 'Meta permissions or Page access are insufficient. Review the app grant and reconnect.', 409)
            raise SocialError('PROVIDER_REJECTED', 'Meta rejected this connection operation. Check the app configuration and reconnect.', 502)
        return value

    def _proof(self, token):
        return hmac.new(self.config.app_secret.encode(), token.encode(), hashlib.sha256).hexdigest()

    def inspect_token(self, token, *, expected_type, expected_page_id=None):
        if expected_type not in {'USER','PAGE'}:
            raise SocialError('PROVIDER_RESPONSE_INVALID', 'A supported credential kind is required.', 502)
        value = self._request('GET', 'debug_token', token=self.config.app_id + '|' + self.config.app_secret, params={'input_token': token}).get('data')
        if not isinstance(value, dict) or value.get('is_valid') is not True or str(value.get('app_id')) != self.config.app_id or value.get('type') != expected_type:
            raise SocialError('GRANT_REVOKED', 'Meta authorization is invalid for this app. Reconnect this account.')
        if expected_page_id:
            identity = self._request('GET', 'me', token=token, params={'fields':'id', 'appsecret_proof': self._proof(token)})
            if _identity(identity.get('id')) != expected_page_id:
                raise SocialError('PROVIDER_RESPONSE_INVALID', 'The derived Page token identifies a different Page.', 502)
        scopes = value.get('scopes')
        if not isinstance(scopes, list) or any(not isinstance(s, str) or len(s) > 100 for s in scopes):
            raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta did not return usable permission metadata.', 502)
        expires = _expiry(value.get('expires_at'))
        data_expires = _expiry(value.get('data_access_expires_at'))
        now = datetime.now(timezone.utc)
        if any(v and datetime.fromisoformat(v) <= now for v in (expires, data_expires)):
            raise SocialError('GRANT_REVOKED', 'Meta authorization expired. Reconnect this account.')
        return {'scopes': sorted(set(scopes) & set(SCOPES)), 'access_expires_at': expires, 'data_access_expires_at': data_expires, 'external_user_id': _identity(value.get('user_id')), 'granular_scopes': value.get('granular_scopes', [])}

    def _paged(self, path, fields, token):
        result, seen, cursor = [], set(), None
        for _ in range(20):
            params = {'fields': fields, 'limit': 100, 'appsecret_proof': self._proof(token)}
            if cursor:
                params['after'] = cursor
            value = self._request('GET', path, token=token, params=params)
            data = value.get('data')
            if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
                raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta returned an invalid account list.', 502)
            result.extend(data)
            if len(result) > 100:
                raise SocialError('DISCOVERY_LIMIT_EXCEEDED', 'This grant contains more than 100 Pages. Limit the grant to the intended AuditGava assets and reconnect.', 409)
            paging = value.get('paging', {})
            if not isinstance(paging, dict):
                raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta returned invalid pagination.', 502)
            if not paging.get('next'):
                return result
            cursor = paging.get('cursors', {}).get('after') if isinstance(paging.get('cursors'), dict) else None
            if not isinstance(cursor, str) or not cursor or len(cursor) > 2048 or cursor in seen:
                raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta returned incomplete or repeated pagination.', 502)
            seen.add(cursor)
        raise SocialError('DISCOVERY_LIMIT_EXCEEDED', 'Meta account discovery exceeded its bounded page limit. Limit the grant and reconnect.')

    def discover(self, code, redirect_uri):
        self.config.require_redirect(redirect_uri)
        short = self._request('POST', 'oauth/access_token', data={'client_id': self.config.app_id, 'client_secret': self.config.app_secret, 'redirect_uri': redirect_uri, 'code': code})
        token = short.get('access_token')
        if not isinstance(token, str) or not token or len(token) > 16384:
            raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta did not return a usable authorization grant.', 502)
        long_lived = self._request('POST', 'oauth/access_token', data={'grant_type': 'fb_exchange_token', 'client_id': self.config.app_id, 'client_secret': self.config.app_secret, 'fb_exchange_token': token})
        token = long_lived.get('access_token')
        if not isinstance(token, str) or not token or len(token) > 16384:
            raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta did not return a usable long-lived grant.', 502)
        metadata = self.inspect_token(token, expected_type='USER')
        permissions = self._paged('me/permissions', 'permission,status', token)
        actual = {item.get('permission') for item in permissions if item.get('status') == 'granted'}
        metadata['scopes'] = sorted(set(metadata['scopes']) & actual)
        if 'pages_show_list' not in metadata['scopes']:
            raise SocialError('PERMISSIONS_REQUIRED', 'Page discovery permission was not granted. Reconnect and explicitly grant Page access.')
        pages = self._paged('me/accounts', 'id,name,access_token,tasks,instagram_business_account', token)
        choices, ids = [], set()
        for page in pages:
            page_id = _identity(page.get('id'))
            if page_id in ids:
                raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta returned duplicate Page identities.', 502)
            ids.add(page_id)
            page_token = page.get('access_token')
            if not isinstance(page_token, str) or not page_token or len(page_token) > 16384:
                continue  # A Page without a derived token is not a connectable destination.
            page_metadata = self.inspect_token(page_token, expected_type='PAGE', expected_page_id=page_id)
            if page_metadata['external_user_id'] != metadata['external_user_id']:
                raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta returned a Page grant owned by a different user.', 502)
            scopes = set(metadata['scopes']) & set(page_metadata['scopes'])
            granular = metadata['granular_scopes']
            if not isinstance(granular, list):
                raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta returned invalid asset-specific permissions.', 502)
            linked = page.get('instagram_business_account')
            asset_ids = {page_id}
            if isinstance(linked, dict):
                asset_ids.add(_identity(linked.get('id')))
            for grant in granular:
                if not isinstance(grant, dict):
                    raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta returned invalid asset-specific permissions.', 502)
                scope, targets = grant.get('scope'), grant.get('target_ids')
                if targets is not None and (not isinstance(targets, list) or any(not isinstance(t, str) for t in targets)):
                    raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta returned invalid asset-specific permissions.', 502)
                if scope in scopes and targets is not None and not asset_ids.intersection(targets):
                    scopes.remove(scope)
            tasks = page.get('tasks', [])
            if not isinstance(tasks, list) or any(not isinstance(t, str) or len(t) > 100 for t in tasks):
                raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta returned invalid Page tasks.', 502)
            page_metadata['scopes'] = sorted(scopes)
            ig = page.get('instagram_business_account')
            ig_detail = None
            if isinstance(ig, dict) and 'instagram_basic' in scopes:
                ig_id = _identity(ig.get('id'))
                ig_detail = self._request('GET', ig_id, token=page_token, params={'fields': 'id,username,name', 'appsecret_proof': self._proof(page_token)})
                if _identity(ig_detail.get('id')) != ig_id:
                    raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta returned an inconsistent linked Instagram identity.', 502)
                username = ig_detail.get('username')
                if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_.]{1,30}', username):
                    raise SocialError('PROVIDER_RESPONSE_INVALID', 'Meta returned an invalid Instagram handle.', 502)
                # This selected Facebook Login product discovers professional
                # identities through Page.instagram_business_account. IGUser
                # does not expose the Instagram Login account_type field.
                ig_detail = {'id': ig_id, 'name': _name(ig_detail.get('name') or username), 'username': username, 'professional': True, 'professional_proof': 'facebook_page_instagram_business_account'}
            choices.append({'page_id': page_id, 'display_name': _name(page.get('name')), 'tasks': sorted(set(tasks)), 'instagram': ig_detail, 'page_eligible': PAGE_SCOPES <= scopes and bool({'CREATE_CONTENT','MANAGE'} & set(tasks)), 'instagram_eligible': bool(ig_detail and ig_detail['professional'] and IG_SCOPES <= scopes and {'CREATE_CONTENT','MANAGE'} & set(tasks)), 'missing_page_scopes': sorted(PAGE_SCOPES - scopes), 'missing_instagram_scopes': sorted(IG_SCOPES - scopes), 'page_token': page_token, 'metadata': page_metadata})
        return {'user_token': token, 'metadata': metadata, 'choices': choices}
