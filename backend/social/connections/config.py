"""Explicit, fail-closed connection configuration. No generated encryption keys."""
import json
import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from ..service import SocialError

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

    def blockers(self):
        errors = []
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

    def require_ready(self):
        if self.blockers():
            raise SocialError('CONNECTIONS_UNAVAILABLE', 'Meta connections are unavailable until server configuration and registered app access are validated.', 503)

    def require_redirect(self, value):
        if not valid_redirect(value) or value not in self.redirect_uris:
            raise SocialError('REDIRECT_MISMATCH', 'Use the exact registered connection callback URL.', 422)


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
    return u.scheme == 'https' and bool(u.hostname) and not (u.username or u.password or u.query or u.fragment) and u.path == '/admin/social/accounts/callback'


def load_config():
    """Read only explicitly named server configuration; never load a dotenv file."""
    try:
        keys = json.loads(os.getenv('SOCIAL_CREDENTIAL_KEYS', '{}'))
        redirects = json.loads(os.getenv('META_REDIRECT_URIS', '[]'))
        if not isinstance(keys, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in keys.items()):
            keys = {}
        if not isinstance(redirects, list) or not all(isinstance(v, str) for v in redirects):
            redirects = []
    except (ValueError, TypeError):
        keys, redirects = {}, []
    return MetaConfig(enabled=os.getenv('META_CONNECTIONS_ENABLED') == 'true', app_configuration_validated=os.getenv('META_APP_CONFIGURATION_VALIDATED') == 'true', app_id=os.getenv('META_APP_ID', ''), app_secret=os.getenv('META_APP_SECRET', ''), graph_version=os.getenv('META_GRAPH_VERSION', 'v26.0'), redirect_uris=tuple(redirects), access_mode=os.getenv('META_ACCESS_MODE', 'unverified'), active_key_version=os.getenv('SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION', ''), encryption_keys=keys)
