"""Direct API callback: encrypted staging, never a browser code relay.

This changes the network boundary, not the host's collectors. Admission remains
required for the exact redirect. The launch nonce authorizes only one browser
binding; it cannot read a grant, exchange a code or select an identity.
"""
import hmac
import re
import secrets
from datetime import timedelta
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID, uuid4

from sqlalchemy import select

from ..service import SocialError, iso, utc
from .config import DIRECT_CALLBACK_PATH, DIRECT_LAUNCH_PATH, origin
from .models import SocialOAuthFlow
from .service import digest

NONCE = re.compile(r'^[A-Za-z0-9_-]{43}$')


def refused(code='OAUTH_CALLBACK_INVALID', status=409):
    return SocialError(code, 'This connection cannot continue. Return to Accounts and start a new connection.', status)


def fields(raw, allowed, maximum=8192):
    """Bound and reject ambiguous encodings, including decoded duplicate keys."""
    if type(raw) is not bytes or not 1 <= len(raw) <= maximum:
        raise refused()
    try:
        value = raw.decode('ascii')
        if re.search(r'%(?![0-9A-Fa-f]{2})', value):
            raise ValueError()
        pairs = parse_qsl(value, keep_blank_values=True, strict_parsing=True,
                          encoding='utf-8', errors='strict', max_num_fields=8)
        result = {}
        for key, item in pairs:
            if key not in allowed or key in result or not item or len(item) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in item):
                raise ValueError()
            result[key] = item
        return result
    except (ValueError, UnicodeError):
        pass
    raise refused()


def callback_fields(raw):
    value = fields(raw, {'code', 'state', 'error', 'error_reason', 'error_description'})
    if not NONCE.fullmatch(value.get('state', '')) or bool(value.get('code')) == bool(value.get('error')):
        raise refused()
    if 'code' in value and len(value) != 2:
        raise refused()
    return value['state'], value.get('code'), 'error' in value


def cookie_name(flow_id):
    return '__Host-auditgava-meta-' + UUID(str(flow_id)).hex


class DirectCallback:
    def __init__(self, service):
        self.svc = service
        self.db, self.config = service.db, service.config

    def _envelope(self, flow):
        if flow.status != 'initiated' or flow.encrypted_verifier is None or flow.privacy_blocked_at is not None:
            raise refused('OAUTH_STATE_USED')
        if utc(flow.expires_at) <= self.svc.base.now():
            raise refused('OAUTH_STATE_EXPIRED')
        value = self.svc.cipher.decrypt(flow.id, 'oauth_start', flow.key_version, flow.encrypted_verifier)
        if (type(value) is not dict or value.get('transport') != 'direct-v1'
                or value.get('admin_origin') != self.config.admin_origin
                or flow.redirect_uri != self.config.require_direct()):
            raise refused()
        keys = set(value)
        if keys in ({'transport', 'admin_origin', 'state', 'launch'}, {'transport', 'admin_origin', 'state', 'browser_hash'}):
            if type(value['state']) is not str or not NONCE.fullmatch(value['state']) or digest(value['state']) != flow.state_hash:
                raise refused()
            if 'launch' in value:
                if type(value['launch']) is not str or not NONCE.fullmatch(value['launch']):
                    raise refused()
            elif type(value['browser_hash']) is not str or not re.fullmatch(r'[a-f0-9]{64}', value['browser_hash']):
                raise refused()
        elif keys == {'transport', 'admin_origin', 'callback'}:
            payload = value['callback']
            if type(payload) is not dict or set(payload) != {'code', 'denied'} or type(payload['denied']) is not bool:
                raise refused()
            code = payload['code']
            if payload['denied']:
                if code is not None:
                    raise refused()
            elif type(code) is not str or not 1 <= len(code) <= 4096 or any(ord(c) < 32 or ord(c) == 127 for c in code):
                raise refused()
        else:
            raise refused()
        return value

    def _save(self, flow, envelope):
        flow.key_version, flow.encrypted_verifier = self.svc.cipher.encrypt(flow.id, 'oauth_start', envelope)
        flow.updated_at = self.svc.base.now()

    def start(self, actor, binding, route, key, body, request_id):
        callback = self.config.require_direct()
        if body.admin_origin != self.config.admin_origin:
            raise refused('OAUTH_ORIGIN_INVALID', 422)
        def action():
            if body.reconnect_account_id:
                from ..models import SocialAccount
                account = self.db.get(SocialAccount, body.reconnect_account_id)
                if not account or account.connection_method != 'facebook_login':
                    raise refused('NOT_FOUND', 404)
            state, launch = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            now = self.svc.base.now()
            flow = SocialOAuthFlow(id=uuid4(), actor_id=actor, binding_hash=binding,
                state_hash=digest(state), redirect_uri=callback, reconnect_account_id=body.reconnect_account_id,
                status='initiated', expires_at=now + timedelta(minutes=10))
            self._save(flow, {'transport': 'direct-v1', 'admin_origin': self.config.admin_origin, 'state': state, 'launch': launch})
            self.db.add(flow)
            self.svc._audit(actor, request_id, 'connection.started', reason=body.reason, details={'flow_id': str(flow.id)})
            return {'flow_id': str(flow.id), 'expires_at': iso(flow.expires_at)}
        _, result = self.svc.base.command(actor=actor, route=route, key=key,
            body=self.svc._body(body, binding), request_id=request_id, action=action)
        with self.db.begin():
            flow = self.svc._flow(UUID(result['flow_id']), actor, binding)
            value = self._envelope(flow)
            if 'launch' not in value:
                raise refused('OAUTH_STATE_USED')
            return dict(result, launch_url=origin(callback) + DIRECT_LAUNCH_PATH, launch_token=value['launch'])

    def launch(self, flow_id, token, request_origin):
        self.config.require_direct()
        if request_origin != self.config.admin_origin or type(token) is not str or not NONCE.fullmatch(token):
            raise refused('OAUTH_ORIGIN_INVALID')
        with self.db.begin():
            flow = self.db.scalar(select(SocialOAuthFlow).where(SocialOAuthFlow.id == flow_id).with_for_update().execution_options(populate_existing=True))
            if not flow:
                raise refused()
            value = self._envelope(flow)
            if 'launch' not in value or not hmac.compare_digest(value['launch'], token):
                raise refused('OAUTH_STATE_USED')
            browser = secrets.token_urlsafe(32)
            value.pop('launch')
            value['browser_hash'] = digest(browser)
            self._save(flow, value)
            # A fixed official provider URL, constructed server-side. No code or
            # token is present; state remains necessary on the provider leg.
            from urllib.parse import urlencode
            url = f'https://www.facebook.com/{self.config.graph_version}/dialog/oauth?' + urlencode({
                'client_id': self.config.app_id, 'redirect_uri': flow.redirect_uri, 'state': value['state'],
                'response_type': 'code', 'scope': ','.join(self.config.requested_scopes), 'auth_type': 'rerequest'})
            return url, cookie_name(flow.id), browser

    def stage(self, raw, cookies):
        self.config.require_direct()
        state, code, denied = callback_fields(raw)
        with self.db.begin():
            flow = self.db.scalar(select(SocialOAuthFlow).where(SocialOAuthFlow.state_hash == digest(state)).with_for_update().execution_options(populate_existing=True))
            if not flow:
                raise refused()
            value = self._envelope(flow)
            browser = cookies.get(cookie_name(flow.id))
            if type(browser) is not str or not NONCE.fullmatch(browser) or 'browser_hash' not in value or not hmac.compare_digest(value['browser_hash'], digest(browser)):
                raise refused()
            if 'callback' in value:
                raise refused('OAUTH_STATE_USED')
            value = {'transport': 'direct-v1', 'admin_origin': value['admin_origin'], 'callback': {'code': code, 'denied': denied}}
            self._save(flow, value)  # Destroy state, launch and browser binding after staging.
            return flow.id

    def complete(self, actor, binding, route, key, body, request_id):
        callback = self.config.require_direct()
        command_body = self.svc._body(body, binding)
        denied = False
        with self.db.begin():
            receipt = self.svc._receipt(actor, route, key, command_body)
            if receipt:
                # Read-only receipt replay still checks actor/session/expiry/privacy.
                flow = self.svc._flow(body.flow_id, actor, binding)
                if flow.redirect_uri != callback:
                    raise refused()
                return receipt.response
            flow = self.svc._flow(body.flow_id, actor, binding)
            value = self._envelope(flow)
            payload = value.get('callback')
            if type(payload) is not dict:
                raise refused('OAUTH_CALLBACK_PENDING')
            denied = payload['denied']
            code = payload['code']
            flow.status, flow.consumed_at, flow.encrypted_verifier = ('failed' if denied else 'exchanging'), self.svc.base.now(), None
            flow.updated_at = self.svc.base.now()
            self.svc._audit(actor, request_id, 'connection.state_consumed', details={'flow_id': str(flow.id)})
        if denied:
            raise refused('OAUTH_DENIED')
        self.svc._claimed_exchange = (body.flow_id, actor, binding, digest(code), callback)
        return self.svc.exchange_claimed(body.flow_id, actor, binding, route, key, command_body, code, callback, request_id)
