"""Explicit server composition only: importing cannot enable OAuth or spend money."""
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit
import re

from ..connections.config import valid_redirect
from ..connections.crypto import CredentialCipher
from ..service import SocialError

SCOPES = {
    'threads': ('threads_basic', 'threads_content_publish'),
    'x': ('tweet.read', 'users.read', 'tweet.write', 'media.write', 'offline.access'),
}


@dataclass(frozen=True)
class ConnectionConfig:
    platform: str
    enabled: bool = False
    access_verified: bool = False
    client_id: str = ''
    client_secret: str = field(default='', repr=False)
    redirect_uris: tuple[str, ...] = ()
    active_key_version: str = ''
    encryption_keys: dict[str, str] = field(default_factory=dict, repr=False)
    # Independent connection/read admission. This never grants publishing budget.
    connection_budget_microusd: int = 0
    # Exact console-approved Accounts API application configuration, never inferred.
    tiktok_oauth: object | None = field(default=None, repr=False)
    tiktok_requested_scopes: tuple[str, ...] = ()

    @property
    def scopes(self):
        return self.tiktok_requested_scopes if self.platform == 'tiktok' else SCOPES.get(self.platform, ())

    def valid_redirect(self, value):
        # The Business Accounts API requires a registered trailing slash.
        if self.platform == 'tiktok' and isinstance(value, str) and value.endswith('/'):
            value = value[:-1]
        if not isinstance(value,str):
            return False
        try:
            parsed = urlsplit(value)
        except ValueError:
            return False
        if parsed.path == '/admin/social/accounts/platform-callback':
            value = urlunsplit(parsed._replace(path='/admin/social/accounts/callback'))
        return valid_redirect(value)

    def blockers(self):
        result = []
        if self.platform == 'tiktok':
            from ..adapters.tiktok_oauth import TikTokOAuthConfig
            if (not isinstance(self.tiktok_oauth, TikTokOAuthConfig) or self.tiktok_oauth.product_access_verified is not True
                    or not self.tiktok_requested_scopes or not {'video.publish', 'video.upload'} & set(self.tiktok_requested_scopes)
                    or self.tiktok_oauth.client_id != self.client_id or self.tiktok_oauth.client_secret != self.client_secret
                    or self.redirect_uris != (self.tiktok_oauth.redirect_uri,)):
                return ['PRODUCT_ACCESS_UNAVAILABLE']
        elif self.platform not in SCOPES:
            return ['PRODUCT_ACCESS_UNAVAILABLE']
        if self.enabled is not True:
            result.append('CONNECTIONS_DISABLED')
        if self.access_verified is not True:
            result.append('PRODUCT_ACCESS_UNVERIFIED')
        if (not isinstance(self.client_id, str) or not 1 <= len(self.client_id) <= 256 or any(c.isspace() or ord(c) < 32 for c in self.client_id)
                or not isinstance(self.client_secret, str) or not self.client_secret):
            result.append('APP_CREDENTIALS_MISSING')
        elif self.platform == 'threads' and not re.fullmatch(r'[0-9]{1,64}', self.client_id):
            result.append('APP_ID_INVALID')
        if not self.redirect_uris or any(not self.valid_redirect(u) for u in self.redirect_uris):
            result.append('REDIRECT_CONFIGURATION_INVALID')
        if self.platform == 'x' and (type(self.connection_budget_microusd) is not int or self.connection_budget_microusd <= 0):
            result.append('X_ZERO_BUDGET')
        try:
            CredentialCipher(self.active_key_version, self.encryption_keys)
        except SocialError:
            result.append('ENCRYPTION_CONFIGURATION_INVALID')
        return result

    def require_ready(self):
        if self.blockers():
            raise SocialError('CONNECTIONS_UNAVAILABLE', 'Connection access, configuration and any required budget must be explicitly verified.', 503)

    def require_redirect(self, value):
        if not self.valid_redirect(value) or value not in self.redirect_uris:
            raise SocialError('REDIRECT_MISMATCH', 'Use the exact registered callback URL.', 422)
