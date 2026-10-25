"""Explicit, fail-closed connection configuration. No generated encryption keys."""
import json
import os
import re
from ipaddress import IPv4Address
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from ..service import SocialError
from .callback_ingress import BLOCKER, ingress_qualified, require_ingress, verified_callbacks

SCOPES = ('pages_show_list', 'pages_read_engagement', 'pages_manage_posts', 'instagram_basic', 'instagram_content_publish')
PAGE_SCOPES = frozenset(SCOPES[:3])
IG_SCOPES = frozenset(('pages_show_list', 'pages_read_engagement', 'instagram_basic', 'instagram_content_publish'))


@dataclass(frozen=True)
class MetaConfig:
    enabled: bool = False
    app_configuration_validated: bool = False
    app_id: str = ''
    app_secret: str = field(default='', repr=False)
    graph_version: str = 'v26.0'
    redirect_uris: tuple[str, ...] = ()
    access_mode: str = 'unverified'
    active_key_version: str = ''
    encryption_keys: dict[str, str] = field(default_factory=dict, repr=False)
    business_discovery_enabled: bool = False
    verified_callback_ingress_uris: tuple[str, ...] = ()
    direct_callback_enabled: bool = False
    admin_origin: str = ''

    @property
    def requested_scopes(self):
        # Business-owned Pages can be omitted from /me/accounts without this
        # separately consented permission. It is not a publishing capability.
        return SCOPES + (('business_management',) if self.business_discovery_enabled is True else ())

    def blockers(self):
        errors = []
        if type(self.business_discovery_enabled) is not bool:
            errors.append('BUSINESS_DISCOVERY_CONFIGURATION_INVALID')
        if self.enabled is not True:
            errors.append('CONNECTIONS_DISABLED')
        if self.app_configuration_validated is not True:
            errors.append('APP_CONFIGURATION_UNVERIFIED')
        if not re.fullmatch(r'[0-9]{1,64}', self.app_id) or not self.app_secret:
            errors.append('APP_CREDENTIALS_MISSING')
        if not re.fullmatch(r'v[1-9][0-9]{0,2}\.0', self.graph_version):
            errors.append('API_VERSION_INVALID')
        if self.access_mode not in {'owned_standard', 'advanced'}:
            errors.append('ACCESS_MODE_UNVERIFIED')
        if not self.redirect_uris or any(not valid_redirect(u) for u in self.redirect_uris):
            errors.append('REDIRECT_CONFIGURATION_INVALID')
        try:
            from .crypto import CredentialCipher
            CredentialCipher(self.active_key_version, self.encryption_keys)
        except SocialError:
            errors.append('ENCRYPTION_CONFIGURATION_INVALID')
        return errors

    def oauth_blockers(self):
        errors = self.blockers()
        if (self.direct_callback_enabled is not False or any(type(u) is str and u.endswith(DIRECT_CALLBACK_PATH) for u in self.redirect_uris)) and not self.direct_transport_valid():
            errors.append('DIRECT_CALLBACK_CONFIGURATION_INVALID')
        if not ingress_qualified(self.redirect_uris, self.verified_callback_ingress_uris, valid_redirect):
            errors.append(BLOCKER)
        return errors

    def require_ready(self):
        if self.blockers():
            raise SocialError('CONNECTIONS_UNAVAILABLE', 'Meta connections are unavailable until server configuration and registered app access are validated.', 503)

    def require_redirect(self, value):
        if self.direct_callback_enabled is not False and not self.direct_transport_valid():
            raise SocialError('CALLBACK_INGRESS_UNVERIFIED', 'Direct callback transport is unavailable.', 503)
        if not valid_redirect(value) or value not in self.redirect_uris:
            raise SocialError('REDIRECT_MISMATCH', 'Use the exact registered connection callback URL.', 422)
        require_ingress(self.redirect_uris, self.verified_callback_ingress_uris, valid_redirect)
        if urlsplit(value).path == DIRECT_CALLBACK_PATH and not self.direct_transport_valid():
            raise SocialError('CALLBACK_INGRESS_UNVERIFIED', 'Direct callback transport is unavailable.', 503)

    def direct_transport_valid(self):
        return (self.direct_callback_enabled is True and valid_origin(self.admin_origin)
                and type(self.redirect_uris) is tuple and len(self.redirect_uris) == 1
                and valid_redirect(self.redirect_uris[0])
                and valid_origin(origin(self.redirect_uris[0]))
                and urlsplit(self.redirect_uris[0]).path == DIRECT_CALLBACK_PATH
                and origin(self.redirect_uris[0]) != self.admin_origin)

    def require_direct(self):
        # Check before DB/receipts, even when an earlier attempt was qualified.
        if not self.direct_transport_valid():
            raise SocialError('CALLBACK_INGRESS_UNVERIFIED', 'Direct callback transport is unavailable.', 503)
        self.require_ready()
        self.require_redirect(self.redirect_uris[0])
        return self.redirect_uris[0]


DIRECT_CALLBACK_PATH = '/api/v1/social/oauth/meta/callback'
DIRECT_LAUNCH_PATH = '/api/v1/social/oauth/meta/launch'


def origin(value):
    u = urlsplit(value)
    return u.scheme + '://' + u.netloc


def valid_origin(value):
    if type(value) is not str or len(value) > 512 or not re.fullmatch(r'https://[a-z0-9.-]+(?::[0-9]{1,5})?', value):
        return False
    try:
        u = urlsplit(value)
        # Browsers normalize shortened/octal/hex IPv4 hosts before Origin and
        # URL serialization. Accept only canonical dotted-decimal IP spelling.
        last_label = u.hostname.rsplit('.', 1)[-1]
        if last_label.isdigit() or re.fullmatch(r'0x[0-9a-f]+', last_label):
            if str(IPv4Address(u.hostname)) != u.hostname:
                return False
        return (bool(u.hostname) and all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in u.hostname.split('.'))
                and (u.port is None or (1 <= u.port <= 65535 and u.port != 443
                     and u.netloc.endswith(':' + str(u.port)))))
    except ValueError:
        return False


def valid_redirect(value):
    if not isinstance(value, str) or len(value) > 2048 or any(c.isspace() or ord(c) < 32 for c in value):
        return False
    if '\\' in value:
        return False
    try:
        u = urlsplit(value)
        if u.port is not None and not 1 <= u.port <= 65535:
            return False
    except ValueError:
        return False
    return u.scheme == 'https' and bool(u.hostname) and not (u.username or u.password or u.query or u.fragment) and '?' not in value and '#' not in value and u.path in {'/admin/social/accounts/callback', DIRECT_CALLBACK_PATH}


def load_config(environ=None):
    """Read only explicitly named server configuration; never load a dotenv file."""
    values = os.environ if environ is None else environ
    try:
        keys = json.loads(values.get('SOCIAL_CREDENTIAL_KEYS', '{}'))
        redirects = json.loads(values.get('META_REDIRECT_URIS', '[]'))
        if not isinstance(keys, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in keys.items()):
            keys = {}
        if not isinstance(redirects, list) or not all(isinstance(v, str) for v in redirects):
            redirects = []
    except (ValueError, TypeError):
        keys, redirects = {}, []
    return MetaConfig(enabled=values.get('META_CONNECTIONS_ENABLED') == 'true', app_configuration_validated=values.get('META_APP_CONFIGURATION_VALIDATED') == 'true', app_id=values.get('META_APP_ID', ''), app_secret=values.get('META_APP_SECRET', ''), graph_version=values.get('META_GRAPH_VERSION', 'v26.0'), redirect_uris=tuple(redirects), access_mode=values.get('META_ACCESS_MODE', 'unverified'), active_key_version=values.get('SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION', ''), encryption_keys=keys, business_discovery_enabled=values.get('META_BUSINESS_DISCOVERY_ENABLED') == 'true', verified_callback_ingress_uris=verified_callbacks(values.get('META_VERIFIED_CALLBACK_INGRESS_URIS', '[]')), direct_callback_enabled=values.get('META_DIRECT_CALLBACK_ENABLED', 'false') == 'true' if values.get('META_DIRECT_CALLBACK_ENABLED', 'false') in {'true', 'false'} else None, admin_origin=values.get('META_ADMIN_ORIGIN', ''))
