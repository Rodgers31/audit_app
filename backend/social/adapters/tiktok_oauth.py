"""Server-only, exact Accounts API token helpers; persistence is caller-owned.

The connection service must consume state once, encrypt token grants, and save
refresh rotation under its durable credential-version compare-and-swap. These
helpers never persist secrets, retry a one-use code, or grant access themselves.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from .tiktok_http import TikTokHTTP, TikTokHTTPFailure, bounded_string, identity


@dataclass(frozen=True)
class TikTokOAuthConfig:
    client_id: str
    client_secret: str = field(repr=False)
    redirect_uri: str
    authorization_url: str
    product_access_verified: bool = False

    def __post_init__(self):
        if type(self.product_access_verified) is not bool:
            raise ValueError("Accounts API product approval must be explicit")
        bounded_string(self.client_id, maximum=128)
        bounded_string(self.client_secret)
        redirect = urlsplit(self.redirect_uri)
        if (not 10 <= len(self.redirect_uri) <= 512 or redirect.scheme != "https" or not redirect.hostname
                or redirect.username or redirect.password or redirect.port is not None or redirect.query
                or redirect.fragment or not redirect.path.endswith("/") or "\\" in self.redirect_uri
                or not self.redirect_uri.isascii() or any(c.isspace() for c in self.redirect_uri)):
            raise ValueError("Use the exact registered TikTok redirect URI")
        auth = urlsplit(self.authorization_url)
        if (auth.scheme != "https" or auth.hostname != "www.tiktok.com" or auth.path != "/v2/auth/authorize"
                or auth.username or auth.password or auth.port is not None or auth.fragment
                or "\\" in self.authorization_url or not self.authorization_url.isascii()
                or any(c.isspace() for c in self.authorization_url)):
            raise ValueError("Use the provider-console Accounts API authorization URL")
        query = parse_qs(auth.query, keep_blank_values=True)
        if not query or any(len(v) != 1 or not v[0] for v in query.values()) or "state" in query:
            raise ValueError("Configured authorization URL must be static and unambiguous")
        if query.get("redirect_uri") != [self.redirect_uri]:
            raise ValueError("Authorization URL redirect mismatch")
        # Never construct an app ID, scopes, or a grant path from assumptions.

    def begin_url(self, state):
        if not self.product_access_verified:
            raise ValueError("TikTok Accounts API product access unavailable")
        if not isinstance(state, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", state):
            raise ValueError("Opaque durable OAuth state required")
        parts = urlsplit(self.authorization_url)
        query = parse_qs(parts.query, keep_blank_values=True)
        query.update(state=[state], disable_auto_auth=["1"])
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode({k: v[0] for k, v in query.items()}), ""))


@dataclass(frozen=True)
class TikTokTokenGrant:
    open_id: str
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    granted_scopes: tuple[str, ...]
    access_expires_at: datetime
    refresh_expires_at: datetime
    request_id: str | None

    def credential_bundle(self):
        """Only for the encrypted durable connection store, never API DTOs."""
        return {"open_id": self.open_id, "access_token": self.access_token,
            "refresh_token": self.refresh_token, "scopes": list(self.granted_scopes)}


class TikTokAccountsOAuth:
    def __init__(self, config, *, transport, now=None):
        if not isinstance(config, TikTokOAuthConfig):
            raise ValueError("Explicit Accounts API OAuth configuration required")
        self.config = config
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.http = TikTokHTTP(transport=transport, now=self.now)

    async def close(self):
        await self.http.close()

    def authorization_url(self, state):
        return self.config.begin_url(state)

    def _base(self):
        if not self.config.product_access_verified:
            raise TikTokHTTPFailure("ACCOUNT_INELIGIBLE")
        return {"client_id": self.config.client_id, "client_secret": self.config.client_secret}

    def _grant(self, response, *, expected_open_id=None):
        try:
            data = response.data
            open_id = identity(data.get("open_id"))
            if expected_open_id is not None and open_id != expected_open_id:
                raise ValueError("Refresh changed account identity")
            if data.get("token_type") != "Bearer":
                raise ValueError("Invalid token type")
            access = bounded_string(data.get("access_token"))
            refresh = bounded_string(data.get("refresh_token"))
            scope = data.get("scope")
            if not isinstance(scope, str) or len(scope) > 20000:
                raise ValueError("Invalid scope set")
            scopes = tuple(scope.split(","))
            if len(scopes) > 200 or len(scopes) != len(set(scopes)) or any(not re.fullmatch(r"[a-z][a-z0-9_.]{0,99}", value) for value in scopes):
                raise ValueError("Invalid scope set")
            access_seconds, refresh_seconds = data.get("expires_in"), data.get("refresh_token_expires_in")
            if (type(access_seconds) is not int or not 0 < access_seconds <= 86400
                    or type(refresh_seconds) is not int or not 0 < refresh_seconds <= 31536000):
                raise ValueError("Invalid provider expiry")
            now = self.now()
            return TikTokTokenGrant(open_id, access, refresh, tuple(sorted(scopes)),
                now + timedelta(seconds=access_seconds), now + timedelta(seconds=refresh_seconds), response.request_id)
        except (ValueError, TypeError, OverflowError):
            # The provider may already have consumed a code or rotated tokens.
            # Never turn malformed/unknown grant data into a safe retry.
            raise TikTokHTTPFailure("TOKEN_GRANT_UNCERTAIN", ambiguous=True) from None

    async def exchange(self, auth_code):
        body = self._base()
        try:
            bounded_string(auth_code, maximum=4096)
        except ValueError:
            raise TikTokHTTPFailure("AUTHORIZATION_REQUIRED") from None
        body.update(grant_type="authorization_code", auth_code=auth_code, redirect_uri=self.config.redirect_uri)
        response = await self.http.request("POST", "tt_user/oauth2/token/", data=body)
        return self._grant(response)

    async def refresh(self, refresh_token, *, expected_open_id):
        body = self._base()
        try:
            bounded_string(refresh_token)
            identity(expected_open_id)
        except ValueError:
            raise TikTokHTTPFailure("AUTHORIZATION_REQUIRED") from None
        body.update(grant_type="refresh_token", refresh_token=refresh_token)
        # The current exact endpoint table/example has no redirect_uri on
        # refresh despite the overview's generic wording; do not invent it.
        response = await self.http.request("POST", "tt_user/oauth2/refresh_token/", data=body)
        return self._grant(response, expected_open_id=expected_open_id)
