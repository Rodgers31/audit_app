"""The HTTP cache must not replay decoded bodies with a gzip header.

``SimpleHTTPCache.set()`` stored ``response.content`` — which httpx has
ALREADY decompressed — together with the original ``Content-Encoding:
gzip`` header. Every cache HIT then failed with:

    Error -3 while decompressing data: incorrect header check

as httpx tried to gunzip plain bytes. Because the failure only appeared on
the SECOND request inside the TTL, it looked intermittent, and each
occurrence silently dropped a domain to its fixture. Observed live against
the World Bank API, the CBK listing page and the OAG media API.
"""

from __future__ import annotations

import gzip

import httpx
import pytest
from seeding.storage import SimpleHTTPCache

PAYLOAD = b'{"hello": "world", "rows": [1, 2, 3]}'


def _gzip_response(url: str) -> httpx.Response:
    """A faithful model of what httpx hands back for a gzip-encoded body.

    The WIRE bytes are compressed and the headers advertise gzip; httpx
    decodes on access, so ``.content`` yields the plain payload while
    ``Content-Encoding: gzip`` remains on the response. That combination is
    precisely what the cache used to persist incorrectly.
    """
    request = httpx.Request("GET", url)
    compressed = gzip.compress(PAYLOAD)
    return httpx.Response(
        status_code=200,
        headers=[
            ("content-type", "application/json"),
            ("content-encoding", "gzip"),
            ("content-length", str(len(compressed))),
        ],
        content=compressed,
        request=request,
    )


class TestGzipRoundTrip:
    def test_cached_gzip_response_is_readable(self, tmp_path):
        """THE defect: reading a cached gzip response raised Error -3."""
        cache = SimpleHTTPCache(tmp_path, ttl_seconds=3600)
        url = "https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CN"
        cache.set(_gzip_response(url))

        hit = cache.get("GET", url)
        assert hit is not None, "expected a cache hit"
        # Before the fix this raised zlib.error / httpx.DecodingError.
        assert hit.content == PAYLOAD
        assert hit.json()["hello"] == "world"

    def test_stale_encoding_headers_are_not_persisted(self, tmp_path):
        cache = SimpleHTTPCache(tmp_path, ttl_seconds=3600)
        url = "https://cob.go.ke/wp-json/wp/v2/media"
        cache.set(_gzip_response(url))
        hit = cache.get("GET", url)
        assert "content-encoding" not in hit.headers
        # The stored Content-Length described the COMPRESSED body, so it is
        # dropped; httpx re-derives one for the decoded body it now holds,
        # and that value must describe the payload we actually serve.
        assert int(hit.headers["content-length"]) == len(PAYLOAD)

    def test_useful_headers_survive(self, tmp_path):
        cache = SimpleHTTPCache(tmp_path, ttl_seconds=3600)
        url = "https://example.gov.ke/x.json"
        cache.set(_gzip_response(url))
        hit = cache.get("GET", url)
        assert hit.headers["content-type"] == "application/json"
        assert hit.status_code == 200

    def test_uncompressed_response_still_round_trips(self, tmp_path):
        cache = SimpleHTTPCache(tmp_path, ttl_seconds=3600)
        url = "https://example.gov.ke/plain.json"
        request = httpx.Request("GET", url)
        cache.set(
            httpx.Response(
                200,
                headers=[("content-type", "application/json")],
                content=PAYLOAD,
                request=request,
            )
        )
        assert cache.get("GET", url).content == PAYLOAD
