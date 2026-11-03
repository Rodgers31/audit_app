"""Saved-grant reads have no OAuth exchange, media or delivery authority."""
import hmac
import re

import httpx

from ..adapters.config import MetaAdapterConfig, native_app_material_valid
from ..service import SocialError
from .config import MetaConfig
from .provider import MetaProvider


def _unavailable():
    return SocialError('GRANT_VERIFICATION_UNAVAILABLE',
        'Saved-grant verification requires validated read-only Meta configuration.', 503)


def _identity(config):
    if type(config) is not MetaConfig:
        raise _unavailable()
    invalid = False
    try:
        if any(type(getattr(config, field)) is not str for field in ('app_id', 'app_secret', 'graph_version', 'access_mode')):
            raise ValueError()
        config.require_ready()
        rules = MetaAdapterConfig(config.graph_version, app_secret=config.app_secret)
        invalid = not native_app_material_valid(rules)
    except (SocialError, ValueError, TypeError, AttributeError):
        invalid = True
    if invalid:
        raise _unavailable()
    return config.app_id, config.graph_version, config.app_secret, config.business_discovery_enabled, config.access_mode


class _ReadOnlyGraphTransport(httpx.BaseTransport):
    """Enforce the read surface after private query injection, before network I/O."""
    def __init__(self, transport, version):
        self.transport, self.version = transport, version

    def handle_request(self, request):
        url = request.url
        prefix = '/' + self.version + '/'
        raw_path = url.raw_path.split(b'?', 1)[0].decode('ascii')
        path = raw_path.removeprefix(prefix)
        fields = {'debug_token': None, 'me': 'id',
            'me/permissions': 'permission,status',
            'me/accounts': 'id,name,tasks,instagram_business_account'}
        numeric = re.fullmatch('[0-9]{1,64}', path) is not None
        allowed = {'input_token'} if path == 'debug_token' else {'fields', 'appsecret_proof'}
        if path in ('me/permissions', 'me/accounts'):
            allowed |= {'limit', 'after'}
        expected = 'id,username,name' if numeric else fields.get(path)
        if (request.method != 'GET' or url.scheme != 'https' or url.host != 'graph.facebook.com'
                or url.port not in (None, 443) or url.username or url.password or url.fragment
                or any(name in request.headers for name in ('x-http-method-override', 'x-http-method', 'x-method-override'))
                or not raw_path.startswith(prefix) or not (path in fields or numeric)
                or len(url.params.multi_items()) != len(set(url.params.keys()))
                or not set(url.params) <= allowed or request.read()
                or (expected is not None and url.params.get('fields') != expected)):
            raise _unavailable()
        return self.transport.handle_request(request)

    def close(self):
        self.transport.close()


class _SavedGrantReads:
    __slots__ = ('__provider',)

    def __init__(self, config, transport):
        self.__provider = MetaProvider(config, transport=_ReadOnlyGraphTransport(
            transport if transport is not None else httpx.HTTPTransport(retries=0, trust_env=False,
                limits=httpx.Limits(max_connections=2, max_keepalive_connections=2)), config.graph_version))

    def inspect_saved_grant(self, user_token, page_token, page_id):
        return self.__provider.inspect_saved_grant(user_token, page_token, page_id)

    def close(self):
        self.__provider.close()


class SavedGrantVerificationAuthority:
    __slots__ = ('__config', '__identity', '__transport')

    def __init__(self, config, *, transport=None):
        self.__identity = _identity(config)
        self.__config, self.__transport = config, transport

    def require_for(self, config):
        actual, original = _identity(config), _identity(self.__config)
        for value in (actual, original):
            if (value[1] != self.__identity[1] or value[3] is not self.__identity[3] or value[4] != self.__identity[4]
                    or not hmac.compare_digest(value[0], self.__identity[0])
                    or not hmac.compare_digest(value[2], self.__identity[2])):
                raise _unavailable()

    def open_provider(self, config):
        self.require_for(config)
        return _SavedGrantReads(self.__config, self.__transport)
