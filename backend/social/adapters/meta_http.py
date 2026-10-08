"""One bounded Graph request per durable operation, with no wire retry."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import hashlib
import hmac
import json
import re

import httpx


REMOTE_ID = re.compile(r"[0-9]{1,64}(?:_[0-9]{1,64})?\Z")
MAX_RESPONSE_BYTES = 65536


def remote_id(value, *, composite=False):
    pattern = REMOTE_ID if composite else re.compile(r"[0-9]{1,64}\Z")
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError("Invalid remote identity")
    return value


class MetaHTTPFailure(Exception):
    """Only allowlisted classifications escape the HTTP boundary."""
    def __init__(self, code, *, ambiguous=False, retry_safe=False, http_status=None,
                 provider_code=None, next_action_at=None):
        super().__init__(code)
        self.code, self.ambiguous, self.retry_safe = code, ambiguous, retry_safe
        self.http_status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None
        self.provider_code = provider_code
        self.next_action_at = next_action_at


@dataclass(frozen=True)
class GraphResponse:
    value: dict = field(repr=False)
    http_status: int
    next_action_at: datetime | None = None


class _PrivateProofTransport(httpx.AsyncBaseTransport):
    """Add secret query proof below HTTPX/Sentry request instrumentation."""
    def __init__(self, transport):
        self.transport = transport

    async def handle_async_request(self, request):
        proof = request.extensions.pop("meta_private_proof", None)
        outgoing = request
        if proof:
            outgoing = httpx.Request(request.method, request.url.copy_merge_params({"appsecret_proof": proof}),
                                     headers=request.headers, stream=request.stream, extensions=request.extensions)
        response = await self.transport.handle_async_request(outgoing)
        response.request = request
        return response

    async def aclose(self):
        await self.transport.aclose()


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _retry_time(value, now):
    if not isinstance(value, str) or len(value) > 100:
        return None
    try:
        if re.fullmatch(r"[0-9]{1,6}", value):
            seconds = int(value)
        else:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                return None
            seconds = int((date - now).total_seconds())
        # A delay beyond the worker's 24-hour lifetime must block there; never
        # shorten the provider's delay to a sooner resend.
        return now + timedelta(seconds=max(1, min(86400, seconds)))
    except (ValueError, TypeError, OverflowError):
        return None


class MetaHTTP:
    def __init__(self, config, *, transport: httpx.AsyncBaseTransport, now):
        if not isinstance(transport, httpx.AsyncBaseTransport):
            raise ValueError("An explicit async HTTP transport is required")
        self.config, self.now = config, now
        self.client = httpx.AsyncClient(transport=_PrivateProofTransport(transport),
            timeout=httpx.Timeout(15, connect=5), follow_redirects=False, trust_env=False,
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=2))

    async def close(self):
        await self.client.aclose()

    async def request(self, method, node, *, token, edge=None, fields=None, data=None, files=None):
        remote_id(node, composite=True)
        if method not in {"GET", "POST"} or edge not in {None, "feed", "photos", "media", "media_publish", "content_publishing_limit"}:
            raise ValueError("Unsupported Graph operation")
        if not isinstance(token, str) or not 0 < len(token) <= 16384 or any(ord(c) < 32 or ord(c) == 127 for c in token):
            raise MetaHTTPFailure("AUTHORIZATION_REQUIRED", retry_safe=True)
        path = node + ("/" + edge if edge else "")
        params = {"fields": fields} if fields else {}
        proof = hmac.new(self.config.app_secret.encode(), token.encode(), hashlib.sha256).hexdigest() if self.config.app_secret else None
        response = None
        try:
            request = self.client.build_request(method,
                f"https://graph.facebook.com/{self.config.graph_version}/{path}", params=params,
                headers={"Authorization": "Bearer " + token, "Accept-Encoding": "identity"},
                data=data, files=files, extensions={"meta_private_proof": proof})
            response = await self.client.send(request, stream=True)
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise ValueError("Unexpected compressed response")
            chunks, size = [], 0
            async for chunk in response.aiter_bytes(chunk_size=16384):
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise ValueError("Response exceeded bound")
                chunks.append(chunk)
            value = json.loads(b"".join(chunks), object_pairs_hook=_no_duplicates,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(value, dict):
                raise ValueError("Graph response must be an object")
        except (httpx.HTTPError, ValueError, TypeError, RecursionError):
            raise MetaHTTPFailure("PROVIDER_OUTCOME_UNCERTAIN", ambiguous=True,
                                  http_status=response.status_code if response else None) from None
        finally:
            if response is not None:
                await response.aclose()
        status = response.status_code
        next_at = _retry_time(response.headers.get("retry-after"), self.now())
        error = value.get("error")
        if "error" in value or not 200 <= status < 300:
            # Server failures, redirects, response conflicts and malformed error
            # shapes cannot prove a dispatched mutation was rejected.
            code = error.get("code") if isinstance(error, dict) else None
            if status >= 500 or status < 400 or type(code) is not int or not 0 < code <= 2147483647 or "id" in value or "post_id" in value:
                raise MetaHTTPFailure("PROVIDER_OUTCOME_UNCERTAIN", ambiguous=True, http_status=status)
            if code == 190:
                safe = "TOKEN_REVOKED"
            elif code in {10, 200, 283, 368}:
                safe = "PERMISSION_DENIED"
            elif code in {4, 17, 32, 613, 80004}:
                safe = "RATE_LIMITED"
            elif code in {1, 2}:
                safe = "TEMPORARY_REJECTION"
            elif code in {100, 324, 9004}:
                safe = "INVALID_MEDIA_OR_PARAMETER"
            else:
                safe = "PROVIDER_REJECTED"
            raise MetaHTTPFailure(safe, retry_safe=True, http_status=status,
                                  provider_code=str(code), next_action_at=next_at)
        return GraphResponse(value, status, next_at)
