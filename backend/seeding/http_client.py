"""HTTP client tailored for seeding workloads."""

from __future__ import annotations

import logging
import os
import tempfile
import time
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from tenacity import (
    Retrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .config import SeedingSettings
from .rate_limiter import RateLimiter
from .storage import SimpleHTTPCache

logger = logging.getLogger("seeding.http")


class PdfDownloadError(Exception):
    """A streamed PDF download failed (timeout, oversize, or non-PDF body).

    Deliberately a plain ``Exception`` — unlike the CLI's ``DomainTimeoutError``
    (a ``BaseException``) — so a domain fetcher's ``except Exception`` fixture
    fallback catches it and recovers cleanly, instead of the per-domain SIGALRM
    firing mid-parse and hard-failing the whole run (issue #119).
    """


def _is_retryable(exception: BaseException) -> bool:
    if isinstance(exception, httpx.HTTPStatusError):
        status = exception.response.status_code
        return status >= 500 or status == 429
    return isinstance(exception, httpx.TransportError)


class SeedingHttpClient(AbstractContextManager["SeedingHttpClient"]):
    """Synchronous HTTP client with rate limiting, retry, and optional caching."""

    def __init__(
        self,
        settings: SeedingSettings,
        rate_limiter: Optional[RateLimiter] = None,
        cache: Optional[SimpleHTTPCache] = None,
        client: Optional[httpx.Client] = None,
        request_logger: Optional[logging.Logger] = None,
    ) -> None:
        self._settings = settings
        self._logger = request_logger or logger
        tokens, period = settings.rate_limit_window
        self._rate_limiter = rate_limiter or RateLimiter(
            tokens=tokens, period_seconds=period
        )
        self._cache = cache
        self._client = client or httpx.Client(
            timeout=settings.timeout_seconds,
            headers=settings.default_headers,
            follow_redirects=settings.http_follow_redirects,
        )

    def close(self) -> None:
        self._client.close()

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - trivial
        self.close()
        return None

    def __enter__(self) -> "SeedingHttpClient":  # pragma: no cover - trivial
        return self

    def request(
        self,
        method: str,
        url: str,
        *,
        raise_for_status: bool = True,
        cache: Optional[bool] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        method_upper = method.upper()
        params = kwargs.get("params")
        use_cache = cache if cache is not None else self._settings.http_cache_enabled
        cached_response: Optional[httpx.Response] = None
        if (
            use_cache
            and self._cache
            and method_upper == "GET"
            and not kwargs.get("stream")
            and kwargs.get("data") is None
            and kwargs.get("files") is None
        ):
            cached_response = self._cache.get(method_upper, url, params=params)
            if cached_response is not None:
                self._logger.debug(
                    "HTTP cache hit",
                    extra={"url": url, "method": method_upper},
                )
                return cached_response

        self._logger.debug(
            "HTTP request",
            extra={"url": url, "method": method_upper, "cached": False},
        )

        retryer = Retrying(
            reraise=True,
            stop=stop_after_attempt(max(self._settings.max_retries, 1)),
            wait=wait_exponential(
                multiplier=self._settings.retry_backoff,
                min=self._settings.retry_backoff,
                max=self._settings.retry_backoff * 8,
            ),
            retry=retry_if_exception(_is_retryable),
            before_sleep=before_sleep_log(self._logger, logging.WARNING),
        )

        response: Optional[httpx.Response] = None
        for attempt in retryer:
            with attempt:
                with self._rate_limiter.context():
                    response = self._client.request(method_upper, url, **kwargs)
                if raise_for_status:
                    response.raise_for_status()
                break

        if response is None:  # pragma: no cover - defensive
            raise RuntimeError("HTTP request did not produce a response")

        response.extensions["seeding_cache"] = False
        if (
            use_cache
            and self._cache
            and method_upper == "GET"
            and response.status_code == 200
            and not kwargs.get("stream")
        ):
            self._cache.set(response)
        return response

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("HEAD", url, **kwargs)

    def download_to_file(
        self,
        url: str,
        dest_path: Path,
        *,
        max_seconds: float,
        max_bytes: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
        raise_for_status: bool = True,
    ) -> int:
        """Stream a GET body to ``dest_path`` under a TOTAL wall-clock cap.

        Returns the number of bytes written. Raises :class:`PdfDownloadError`
        if the full body is not received within ``max_seconds`` or if it
        exceeds ``max_bytes``.

        Writes atomically: the body streams to a sibling temp file that is
        ``os.replace``-d into ``dest_path`` only after the full transfer
        succeeds, and the temp is removed on any failure. So a timeout,
        byte-cap breach, or transport error never leaves a truncated file at
        ``dest_path`` for a later run to mistake for a complete download.

        Why not ``request()``: ``request()`` reads the whole body eagerly with
        httpx's *per-operation* timeout — a read timeout only bounds the gap
        *between* chunks, so a slow-but-steady 48MB body streams for minutes
        without ever tripping it. This streams chunk-by-chunk and checks a
        monotonic deadline each iteration, so total elapsed time is bounded.

        Single attempt, no tenacity retry: re-pulling a large, already-slow
        body on a transient error would blow the very budget this guards. The
        per-operation timeout below still fails a fully-stalled socket fast;
        the loop deadline handles a slow trickle.
        """
        dest = Path(dest_path)
        request_headers = dict(headers or {})
        # Fail a dead connection fast (no bytes at all / no handshake), but let
        # a slow steady stream run up to the wall-clock cap the loop enforces.
        per_op = min(float(max_seconds), 30.0)
        timeout = httpx.Timeout(per_op, connect=min(float(max_seconds), 15.0))
        start = time.monotonic()
        written = 0
        # Stream to a sibling temp and atomically promote on success so a
        # partial transfer never lands at dest_path (see docstring).
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=dest.name + ".", suffix=".part", dir=str(dest.parent)
        )
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            with self._rate_limiter.context():
                with self._client.stream(
                    "GET", url, headers=request_headers, timeout=timeout
                ) as response:
                    if raise_for_status:
                        response.raise_for_status()
                    with tmp.open("wb") as handle:
                        for chunk in response.iter_bytes():
                            if time.monotonic() - start > max_seconds:
                                raise PdfDownloadError(
                                    f"download exceeded {max_seconds:.0f}s "
                                    f"wall-clock cap after {written} bytes: {url}"
                                )
                            if (
                                max_bytes is not None
                                and written + len(chunk) > max_bytes
                            ):
                                raise PdfDownloadError(
                                    f"download exceeded {max_bytes}-byte cap: {url}"
                                )
                            handle.write(chunk)
                            written += len(chunk)
            os.replace(tmp, dest)
        except BaseException:
            # Clean up the partial temp on ANY failure (incl. a SIGALRM-driven
            # BaseException) — then re-raise unchanged.
            tmp.unlink(missing_ok=True)
            raise
        return written


def create_http_client(settings: SeedingSettings) -> SeedingHttpClient:
    cache_backend: Optional[SimpleHTTPCache] = None
    if settings.http_cache_enabled:
        cache_backend = SimpleHTTPCache(settings.cache_path, settings.cache_ttl_seconds)
    return SeedingHttpClient(settings=settings, cache=cache_backend)


__all__ = ["SeedingHttpClient", "create_http_client"]
