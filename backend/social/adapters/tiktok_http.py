"""Bounded Accounts API v1.3 transport. No automatic retries or redirects."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re

import httpx

from .platform_http import parse_retry_after


BASE_URL = "https://business-api.tiktok.com/open_api/v1.3/"
ALLOWED = {
    ("GET", "business/video/settings/"), ("GET", "business/video/list/"), ("GET", "business/publish/status/"),
    ("POST", "business/video/publish/"), ("POST", "business/photo/publish/"),
    ("POST", "tt_user/oauth2/token/"), ("POST", "tt_user/oauth2/refresh_token/"),
}


def bounded_string(value, *, maximum=16384):
    if not isinstance(value, str) or not 0 < len(value) <= maximum or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Invalid provider material")
    return value


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.~:-]{1,256}", value):
        raise ValueError("Invalid provider identity")
    return value


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate response key")
        value[key] = item
    return value


class TikTokHTTPFailure(Exception):
    def __init__(self, code, *, ambiguous=False, http_status=None, provider_code=None, next_action_at=None):
        super().__init__(code)
        self.code, self.ambiguous = code, ambiguous
        self.http_status, self.provider_code, self.next_action_at = http_status, provider_code, next_action_at


@dataclass(frozen=True)
class TikTokResponse:
    data: dict = field(repr=False)
    request_id: str | None
    http_status: int


class TikTokHTTP:
    def __init__(self, *, transport, now):
        if not isinstance(transport, httpx.AsyncBaseTransport):
            raise ValueError("An explicit async HTTP transport is required")
        self.now = now
        self.client = httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(20, connect=5),
            follow_redirects=False, trust_env=False,
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=2))

    async def close(self):
        await self.client.aclose()

    async def request(self, method, path, *, token=None, data=None, params=None, maximum_bytes=65536):
        if type(maximum_bytes) is not int or not 1 <= maximum_bytes <= 65536:
            raise ValueError("Invalid response bound")
        if (method, path) not in ALLOWED:
            raise ValueError("Unsupported TikTok operation")
        headers = {"Accept-Encoding": "identity"}
        if token is not None:
            headers["Access-Token"] = bounded_string(token)
        response = None
        try:
            request = self.client.build_request(method, BASE_URL + path, headers=headers, json=data, params=params)
            response = await self.client.send(request, stream=True)
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise ValueError("Compressed response refused")
            chunks, size = [], 0
            async for chunk in response.aiter_bytes(chunk_size=16384):
                size += len(chunk)
                if size > maximum_bytes:
                    raise ValueError("Response exceeds bound")
                chunks.append(chunk)
            value = json.loads(b"".join(chunks), object_pairs_hook=_unique,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(value, dict):
                raise ValueError("Response must be an object")
        except (httpx.HTTPError, ValueError, TypeError, RecursionError):
            raise TikTokHTTPFailure("PROVIDER_OUTCOME_UNCERTAIN", ambiguous=True,
                http_status=response.status_code if response is not None else None) from None
        finally:
            if response is not None:
                await response.aclose()
        code = value.get("code")
        if type(code) is not int or not 0 <= code <= 2147483647:
            raise TikTokHTTPFailure("PROVIDER_OUTCOME_UNCERTAIN", ambiguous=True, http_status=response.status_code)
        if not 200 <= response.status_code < 300 or code != 0:
            # A server failure or response containing accepted task data cannot
            # establish that a dispatched mutation did not happen.
            if response.status_code >= 500 or response.status_code < 200 or 300 <= response.status_code < 400 or value.get("data"):
                raise TikTokHTTPFailure("PROVIDER_OUTCOME_UNCERTAIN", ambiguous=True, http_status=response.status_code)
            next_at = parse_retry_after(response.headers.get("retry-after"), self.now())
            safe = "RATE_LIMITED" if response.status_code == 429 else "PROVIDER_REJECTED"
            if response.status_code in {401, 403}:
                safe = "AUTHORIZATION_REQUIRED" if response.status_code == 401 else "PERMISSION_DENIED"
            raise TikTokHTTPFailure(safe, http_status=response.status_code, provider_code=str(code), next_action_at=next_at)
        if not isinstance(value.get("data"), dict):
            raise TikTokHTTPFailure("PROVIDER_OUTCOME_UNCERTAIN", ambiguous=True, http_status=response.status_code)
        request_id = value.get("request_id")
        if request_id is not None and (not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id)):
            request_id = None
        return TikTokResponse(value["data"], request_id, response.status_code)
