"""Sync request-thread bridge to the official async Accounts API token helper.

Each async HTTP client is created, used and closed on the same event loop.
No profile username is invented from a token subject; confirmation shows open_id.
"""
import asyncio
from datetime import datetime, timezone

import httpx

from ..adapters.tiktok_oauth import TikTokAccountsOAuth
from ..adapters.tiktok import TikTokAccountsAdapter, TikTokAdapterConfig
from ..adapters.tiktok_http import TikTokHTTPFailure
from ..service import SocialError


class TikTokConnectionProvider:
    def __init__(self, config, *, transport_factory=None):
        config.require_ready()
        self.config = config
        self.transport_factory = transport_factory or (lambda: httpx.AsyncHTTPTransport(retries=0, trust_env=False))

    def close(self):
        # Each exchange owns and closes its async transport before returning.
        return None

    def authorize_url(self, state, redirect_uri, verifier):
        self.config.require_ready()
        self.config.require_redirect(redirect_uri)
        return self.config.tiktok_oauth.begin_url(state)

    async def _run(self, *, code=None, bundle=None):
        self.config.require_ready()
        helper = TikTokAccountsOAuth(self.config.tiktok_oauth, transport=self.transport_factory())
        try:
            if code is not None:
                grant = await helper.exchange(code)
            else:
                if datetime.fromisoformat(bundle['refresh_expires_at']) <= datetime.now(timezone.utc):
                    raise SocialError('GRANT_EXPIRED', 'The TikTok refresh credential expired. Reconnect.', 409)
                grant = await helper.refresh(bundle['refresh_token'], expected_open_id=bundle['subject'])
        finally:
            await helper.close()
        if not set(self.config.scopes) <= set(grant.granted_scopes):
            raise SocialError('PERMISSIONS_REQUIRED', 'The approved TikTok Accounts API grant lacks required permissions.', 409)
        return grant.credential_bundle() | {'subject': grant.open_id, 'issued_at': datetime.now(timezone.utc).isoformat(), 'expires_at': grant.access_expires_at.isoformat(), 'refresh_expires_at': grant.refresh_expires_at.isoformat(), 'username': None, 'display_name': 'TikTok account ' + grant.open_id}

    def _call(self, **kwargs):
        failure = None
        try:
            return asyncio.run(self._run(**kwargs))
        except TikTokHTTPFailure:
            failure = SocialError('PROVIDER_UNAVAILABLE', 'The TikTok grant exchange failed or has an uncertain outcome. Reconnect without replaying its code.', 502)
        raise failure

    def exchange(self, code, redirect_uri, verifier):
        self.config.require_ready()
        self.config.require_redirect(redirect_uri)
        return self._call(code=code)

    def refresh(self, bundle):
        self.config.require_ready()
        return self._call(bundle=bundle)

    def creator_settings(self, bundle):
        self.config.require_ready()
        async def read():
            adapter = TikTokAccountsAdapter(TikTokAdapterConfig(product_access_verified=True), transport=self.transport_factory())
            try:
                return await adapter.creator_settings(bundle['subject'], bundle['access_token'])
            finally:
                await adapter.close()
        failure = None
        try:
            return asyncio.run(read())
        except TikTokHTTPFailure:
            failure = SocialError('PROVIDER_UNAVAILABLE', 'TikTok creator settings are unavailable. No privacy choice can be assumed.', 502)
        raise failure
