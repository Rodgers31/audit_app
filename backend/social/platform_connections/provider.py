"""Pinned official OAuth contracts: Threads v1.0 and X v2, checked 2026-10-16.

No publication, upload, redirect following or automatic HTTP retry exists here.
"""
import base64
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from ..connections.provider import _SecretQueryTransport
from ..service import SocialError


def invalid():
    return SocialError('PROVIDER_RESPONSE_INVALID', 'The provider returned invalid identity, grant or expiry evidence.', 502)


def token(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 16384 or any(not 33 <= ord(c) <= 126 for c in value):
        raise invalid()
    return value


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,64}', value):
        raise invalid()
    return value


def challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).decode().rstrip('=')


def unique_fields(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate provider field')
        value[key] = item
    return value


class OAuthProvider:
    def __init__(self, config, *, transport=None, admission=None):
        config.require_ready()
        self.config = config
        self.admission = admission
        self._admit()
        self.client = httpx.Client(transport=_SecretQueryTransport(transport or httpx.HTTPTransport(retries=0, trust_env=False)), timeout=httpx.Timeout(15, connect=5), trust_env=False, follow_redirects=False)

    def close(self):
        self.client.close()

    def _admit(self, cost=0):
        self.config.require_ready()
        if self.config.platform == 'x':
            if not callable(self.admission):
                raise SocialError('X_BUDGET_UNAVAILABLE', 'A durable X connection-read budget is required.', 503)
            if self.admission(cost) is not True:
                raise SocialError('X_BUDGET_UNAVAILABLE', 'The durable X read reservation was not confirmed.', 503)

    def authorize_url(self, state, redirect_uri, verifier):
        self.config.require_redirect(redirect_uri)
        self._admit()
        params = dict(client_id=self.config.client_id, redirect_uri=redirect_uri, state=state, response_type='code', scope=(',' if self.config.platform == 'threads' else ' ').join(self.config.scopes))
        if self.config.platform == 'x':
            params.update(code_challenge=challenge(verifier), code_challenge_method='S256')
        url = 'https://threads.com/oauth/authorize' if self.config.platform == 'threads' else 'https://x.com/i/oauth2/authorize'
        return url + '?' + urlencode(params)

    def _request(self, method, path, *, access_token=None, data=None, params=None, private=None, auth=None):
        if self.config.platform == 'x' and (method, path) not in {('POST','/2/oauth2/token'), ('GET','/2/users/me')}:
            raise SocialError('UNSUPPORTED_CONNECTION_OPERATION', 'This endpoint is outside the pinned OAuth contract.', 422)
        # Every individual request repeats admission, including paid identity reads.
        # Official current user lookup price ceiling: $0.010/read. Token
        # exchanges are not charged here, but still require actual budget access.
        self._admit(10000 if self.config.platform == 'x' and path == '/2/users/me' else 0)
        base = 'https://graph.threads.com' if self.config.platform == 'threads' else 'https://api.x.com'
        headers = {'Accept-Encoding': 'identity'}
        if access_token:
            headers['Authorization'] = 'Bearer ' + token(access_token)
        request = self.client.build_request(method, base + path, headers=headers, data=data, params=params, extensions={'meta_secret_query': private or {}})
        failure = None
        try:
            response = self.client.send(request, auth=auth, stream=True)
            try:
                if response.headers.get('content-encoding', 'identity').lower() != 'identity':
                    raise invalid()
                chunks, total, started = [], 0, time.monotonic()
                for chunk in response.iter_bytes(chunk_size=16384):
                    total += len(chunk)
                    if total > 1_000_000 or time.monotonic() - started > 30:
                        raise invalid()
                    chunks.append(chunk)
                value = json.loads(b''.join(chunks), object_pairs_hook=unique_fields)
            finally:
                response.close()
        except httpx.HTTPError:
            failure = SocialError('PROVIDER_UNAVAILABLE', 'The provider exchange or read failed. Reconnect; authorization codes are never replayed.', 502)
        except (ValueError, TypeError):
            failure = invalid()
        if failure is not None:
            # No retained raw HTTP/parser exception (including private wire URL).
            raise failure
        if not isinstance(value, dict):
            raise invalid()
        if not 200 <= response.status_code < 300 or 'error' in value or value.get('errors'):
            raise SocialError('PROVIDER_REJECTED', 'The provider rejected the grant or required permissions. Reconnect after reviewing access.', 502)
        return value

    def _x_token(self, data):
        return self._request('POST', '/2/oauth2/token', data=data, auth=httpx.BasicAuth(self.config.client_id, self.config.client_secret))

    def _bundle(self, result, scopes, subject):
        expires = result.get('expires_in')
        if type(expires) is not int or not 0 < expires <= 366 * 86400 or not isinstance(result.get('token_type'), str) or result['token_type'].lower() != 'bearer':
            raise invalid()
        if self.config.platform == 'x' and not result.get('refresh_token'):
            raise invalid()
        if not set(self.config.scopes) <= set(scopes):
            raise SocialError('PERMISSIONS_REQUIRED', 'The provider grant lacks the required permissions.', 409)
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        return {'access_token': token(result.get('access_token')), 'refresh_token': token(result['refresh_token']) if self.config.platform == 'x' else None, 'scopes': sorted(scopes), 'subject': subject, 'issued_at': now.isoformat(), 'expires_at': (now + timedelta(seconds=expires)).isoformat()}

    def _inspect(self, result, *, expected=None, threads_user_id=None):
        access = token(result.get('access_token'))
        if self.config.platform == 'threads':
            me = self._request('GET', '/v1.0/me', access_token=access, params={'fields': 'id,username,name'})
            app = self._request('GET', '/oauth/access_token', params={'grant_type': 'client_credentials'}, private={'client_id': self.config.client_id, 'client_secret': self.config.client_secret})
            inspected = self._request('GET', '/debug_token', private={'access_token': token(app.get('access_token')), 'input_token': access}).get('data')
            if not isinstance(inspected, dict) or inspected.get('is_valid') is not True or str(inspected.get('app_id')) != self.config.client_id or inspected.get('type') != 'USER':
                raise SocialError('GRANT_REVOKED', 'The Threads grant is invalid, revoked or belongs to another application.', 409)
            if identity(inspected.get('user_id')) != identity(me.get('id')):
                raise SocialError('IDENTITY_MISMATCH', 'The inspected grant and observed identity differ.', 409)
            scopes = inspected.get('scopes')
            if not isinstance(scopes, list) or len(scopes) > 100 or any(not isinstance(s, str) for s in scopes):
                raise invalid()
            for field in ('expires_at', 'data_access_expires_at'):
                if type(inspected.get(field)) is not int or inspected[field] <= datetime.now(timezone.utc).timestamp():
                    raise SocialError('GRANT_REVOKED', 'The Threads token or data-access grant has expired.', 409)
        else:
            me = self._request('GET', '/2/users/me', access_token=access, params={'user.fields': 'name,username'}).get('data')
            if not isinstance(me, dict) or not isinstance(result.get('scope'), str):
                raise invalid()
            scopes = result['scope'].split()
        subject = identity(me.get('id'))
        if (expected is not None and subject != expected) or (threads_user_id is not None and subject != threads_user_id):
            raise SocialError('IDENTITY_MISMATCH', 'The returned grant belongs to another identity.', 409)
        username = me.get('username')
        name = me.get('name') or username
        if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_.]{1,64}', username) or not isinstance(name, str) or not 1 <= len(name) <= 200:
            raise invalid()
        bundle = self._bundle(result, scopes, subject)
        if self.config.platform == 'threads':
            # Respect both token expiry and separately revocable data-access expiry.
            bundle['expires_at'] = min(datetime.fromisoformat(bundle['expires_at']), datetime.fromtimestamp(inspected['expires_at'], timezone.utc)).isoformat()
            bundle['data_access_expires_at'] = datetime.fromtimestamp(inspected['data_access_expires_at'], timezone.utc).isoformat()
        return bundle | {'username': username, 'display_name': name}

    def exchange(self, code, redirect_uri, verifier):
        self.config.require_redirect(redirect_uri)
        self._admit()
        if self.config.platform == 'threads':
            short = self._request('POST', '/oauth/access_token', data={'client_id': self.config.client_id, 'client_secret': self.config.client_secret, 'grant_type': 'authorization_code', 'redirect_uri': redirect_uri, 'code': code})
            user = identity(str(short.get('user_id', '')))
            result = self._request('GET', '/access_token', params={'grant_type': 'th_exchange_token'}, private={'client_secret': self.config.client_secret, 'access_token': token(short.get('access_token'))})
            return self._inspect(result, threads_user_id=user)
        result = self._x_token({'grant_type': 'authorization_code', 'code': code, 'redirect_uri': redirect_uri, 'code_verifier': verifier})
        return self._inspect(result)

    def refresh(self, bundle):
        self._admit()
        if self.config.platform == 'threads':
            now = datetime.now(timezone.utc)
            if (now - datetime.fromisoformat(bundle['issued_at'])).total_seconds() < 86400 or datetime.fromisoformat(bundle['expires_at']) <= now:
                raise SocialError('REFRESH_INELIGIBLE', 'Threads requires an unexpired long-lived token at least 24 hours old.', 409)
            result = self._request('GET', '/refresh_access_token', params={'grant_type': 'th_refresh_token'}, private={'access_token': token(bundle['access_token'])})
        else:
            result = self._x_token({'grant_type': 'refresh_token', 'refresh_token': token(bundle.get('refresh_token'))})
            # Omitted scope on refresh retains the prior grant; an explicit scope is verified.
            result.setdefault('scope', ' '.join(bundle['scopes']))
            if not result.get('refresh_token'):
                result['refresh_token'] = bundle.get('refresh_token')
        return self._inspect(result, expected=bundle['subject'])
