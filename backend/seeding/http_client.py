"""HTTP client tailored for seeding workloads."""

from __future__ import annotations

import logging
import re
import os
import tempfile
import time
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Callable, Dict, Optional

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


class PdfDownloadIncomplete(PdfDownloadError):
    """A resumable download ran out of wall-clock before the body ended.

    Carries how far it got so the caller can log real progress, and — unlike
    a plain failure — signals that the partial file was DELIBERATELY RETAINED
    for the next run to resume from. This is what makes a 12MB PDF reachable
    over a 43 KB/s link that no single run's budget can span.
    """

    def __init__(self, message: str, *, bytes_downloaded: int, resumable: bool = True):
        super().__init__(message)
        self.bytes_downloaded = bytes_downloaded
        self.resumable = resumable


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
        resume_part: Optional[Path] = None,
        completion_check: Optional[Callable[[Path], bool]] = None,
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

        RESUMPTION (``resume_part``)
        ---------------------------
        Some publishers serve large PDFs slowly enough that NO single run can
        finish them: cob.go.ke measured 43 KB/s against a 12,407,501-byte
        report, i.e. ~290s of transfer against a 180s cap — so every nightly
        run downloaded ~6MB, timed out, discarded it, and fell back to a
        git-tracked fixture. Forever.

        Passing ``resume_part`` makes progress durable. The partial body is
        written there and KEPT on timeout; the next call sends
        ``Range: bytes=<size>-`` and appends, so the file completes across
        runs and then lives in the cache.

        Correctness:
        * ``206`` is not enough on its own — it says "partial content", not
          "the bytes you asked for". ``Content-Range`` is PARSED and its start
          offset must equal the offset we requested; anything else restarts
          from zero. Reported by review on PR #136: the previous code trusted
          the status alone, so a server answering with a different range would
          have appended bytes to the wrong position.
        * ``200`` means the server IGNORED the range and is resending from
          zero -> the partial is truncated and rewritten, never appended to
          (appending would splice a duplicate prefix into the file).
        * ``If-Range`` carries the ETag/Last-Modified recorded when the
          partial was started. If the publisher re-issued the document since,
          the server MUST send ``200`` with the whole new entity instead of a
          range — which the branch above already handles by restarting. Without
          it, a resume across nightly runs could splice an old prefix onto a
          new suffix, and the result would still pass both the ``%PDF-`` header
          and ``%%EOF`` trailer checks. Also reported on PR #136.

        The md5-overlap comparison that used to be cited here was a one-off
        manual check during development, not a runtime guarantee; it has been
        replaced by the two checks above, which run on every resume.
        """
        dest = Path(dest_path)
        base_headers = dict(headers or {})
        # Fail a dead connection fast (no bytes at all / no handshake), but let
        # a slow steady stream run up to the wall-clock cap the loop enforces.
        per_op = min(float(max_seconds), 30.0)
        timeout = httpx.Timeout(per_op, connect=min(float(max_seconds), 15.0))
        start = time.monotonic()
        dest.parent.mkdir(parents=True, exist_ok=True)

        resuming = resume_part is not None
        validator_path = (
            Path(str(resume_part) + ".validator") if resume_part else None
        )

        def _saved_validator() -> Optional[str]:
            """ETag/Last-Modified recorded when this partial was started."""
            if validator_path is None or not validator_path.exists():
                return None
            try:
                return validator_path.read_text(encoding="utf-8").strip() or None
            except OSError:
                return None

        def _remember_validator(response) -> None:
            if validator_path is None:
                return
            token = response.headers.get("etag") or response.headers.get(
                "last-modified"
            )
            try:
                if token:
                    validator_path.write_text(token, encoding="utf-8")
                else:
                    validator_path.unlink(missing_ok=True)
            except OSError:  # pragma: no cover - best effort, never fatal
                pass

        def _range_start(response) -> Optional[int]:
            """First byte index the server actually sent, from Content-Range.

            ``Content-Range: bytes 1024-2047/4096`` -> 1024. Returns None when
            the header is absent or unparseable, which the caller treats as
            "cannot confirm" and restarts rather than guessing.
            """
            raw = response.headers.get("content-range", "")
            match = re.match(r"\s*bytes\s+(\d+)-", raw, re.IGNORECASE)
            return int(match.group(1)) if match else None
        if resuming:
            tmp = Path(resume_part)
            tmp.parent.mkdir(parents=True, exist_ok=True)
        else:
            fd, tmp_name = tempfile.mkstemp(
                prefix=dest.name + ".", suffix=".part", dir=str(dest.parent)
            )
            os.close(fd)
            tmp = Path(tmp_name)

        def _on_disk() -> int:
            return tmp.stat().st_size if tmp.exists() else 0

        def _already_whole() -> bool:
            """Is what we have on disk already the complete document?

            These publishers send no ``Content-Length``, so the only
            authoritative end-of-document signal is the format's own (for
            PDF, the ``%%EOF`` trailer). Checking it after every pass is what
            makes a transport error on the FINAL chunk a success rather than
            an infinite resume loop re-requesting past EOF.
            """
            if completion_check is None or not tmp.exists():
                return False
            try:
                return bool(completion_check(tmp))
            except Exception:  # a malformed partial is simply "not done yet"
                return False

        started_at = _on_disk()
        complete = False
        attempt = 0
        try:
            # Reconnect loop. A single stream is not enough on these CDNs: the
            # link both trickles (43 KB/s measured on cob.go.ke) and drops
            # mid-body. Each pass resumes from whatever is already on disk, so
            # a flaky-but-fast link finishes within one run, and a merely slow
            # one keeps its progress for the next (see the class docstring).
            while True:
                attempt += 1
                remaining = max_seconds - (time.monotonic() - start)
                if remaining <= 0:
                    break

                if _already_whole():
                    # Nothing left to fetch — a previous pass (or run) already
                    # brought down the whole document.
                    complete = True
                    break

                offset = _on_disk()
                request_headers = dict(base_headers)
                if offset:
                    request_headers["Range"] = f"bytes={offset}-"
                    validator = _saved_validator()
                    if validator:
                        # If the entity changed, the server answers 200 with
                        # the whole new document and the branch below restarts
                        # — instead of splicing an old prefix to a new suffix.
                        request_headers["If-Range"] = validator

                mode = "ab" if offset else "wb"
                try:
                    with self._rate_limiter.context():
                        with self._client.stream(
                            "GET", url, headers=request_headers, timeout=timeout
                        ) as response:
                            if raise_for_status:
                                response.raise_for_status()
                            if offset and response.status_code != 206:
                                # Server ignored the range and is resending
                                # from zero. Appending would splice a
                                # duplicate prefix — restart the file instead.
                                logger.warning(
                                    "Resume at byte %d refused (HTTP %s, not "
                                    "206); restarting from zero: %s",
                                    offset,
                                    response.status_code,
                                    url,
                                )
                                mode = "wb"
                            elif offset:
                                # 206 alone does not say WHICH bytes these are.
                                # RFC 9110 requires Content-Range on a 206, and
                                # Treasury sends it ("bytes 1000-1999/1473917").
                                started_at = _range_start(response)
                                if started_at is not None and started_at != offset:
                                    logger.warning(
                                        "Resume at byte %d got Content-Range "
                                        "starting at %d (header: %r); "
                                        "restarting from zero rather than "
                                        "appending to the wrong offset: %s",
                                        offset,
                                        started_at,
                                        response.headers.get("content-range"),
                                        url,
                                    )
                                    mode = "wb"
                                elif started_at is None:
                                    # Non-compliant 206 with no Content-Range.
                                    # Behave as before (append) rather than
                                    # restart: cob.go.ke's TLS certificate is
                                    # expired as of 2026-09-02 so its range
                                    # behaviour could not be re-probed, and
                                    # hard-restarting a server that DOES honour
                                    # the offset would turn a working resume
                                    # into an endless re-download of 12MB.
                                    # Loud, because appending on an unverified
                                    # offset is the risk the check exists for.
                                    logger.warning(
                                        "Resume at byte %d got a 206 with NO "
                                        "Content-Range; appending unverified. "
                                        "If this server ignores ranges the "
                                        "result is spliced — the %%%%EOF check "
                                        "is the only remaining guard: %s",
                                        offset,
                                        url,
                                    )
                            if mode == "wb":
                                _remember_validator(response)
                            with tmp.open(mode) as handle:
                                for chunk in response.iter_bytes():
                                    if time.monotonic() - start > max_seconds:
                                        handle.flush()
                                        os.fsync(handle.fileno())
                                        raise PdfDownloadIncomplete(
                                            f"download exceeded "
                                            f"{max_seconds:.0f}s wall-clock "
                                            f"cap at {_on_disk()} bytes: {url}",
                                            bytes_downloaded=_on_disk(),
                                            resumable=resuming,
                                        )
                                    if (
                                        max_bytes is not None
                                        and handle.tell() + len(chunk) > max_bytes
                                    ):
                                        raise PdfDownloadError(
                                            f"download exceeded {max_bytes}-byte "
                                            f"cap: {url}"
                                        )
                                    handle.write(chunk)
                    # iter_bytes() ran to completion => the server closed the
                    # body normally, so we have the whole document.
                    complete = True
                    break
                except (httpx.TransportError, httpx.StreamError) as exc:
                    # Bytes already written are valid (append-only, offsets
                    # server-verified), so this is progress, not corruption.
                    # Reconnect if there is budget left.
                    if _already_whole():
                        # The stream broke on the last chunk but the document
                        # is whole. Treat as success, not as a failed resume.
                        logger.info(
                            "Transfer interrupted at EOF but document is "
                            "complete (%d bytes): %s", _on_disk(), url,
                        )
                        complete = True
                        break
                    advanced = _on_disk() - offset
                    logger.warning(
                        "Transfer interrupted after +%d bytes (%s: %s); "
                        "%d bytes on disk, reconnecting: %s",
                        advanced,
                        type(exc).__name__,
                        exc,
                        _on_disk(),
                        url,
                    )
                    if advanced <= 0 and attempt >= 3:
                        # Three reconnects with zero progress: the endpoint is
                        # not going to serve us. Stop burning the budget.
                        raise PdfDownloadIncomplete(
                            f"download stalled at {_on_disk()} bytes after "
                            f"{attempt} attempts: {url}",
                            bytes_downloaded=_on_disk(),
                            resumable=resuming,
                        ) from exc

            if not complete:
                raise PdfDownloadIncomplete(
                    f"download exceeded {max_seconds:.0f}s wall-clock cap at "
                    f"{_on_disk()} bytes: {url}",
                    bytes_downloaded=_on_disk(),
                    resumable=resuming,
                )

            written = _on_disk()
            os.replace(tmp, dest)
        except PdfDownloadIncomplete:
            # Deliberately KEEP a resumable partial: it is the progress this
            # mechanism exists to preserve.
            if not resuming:
                tmp.unlink(missing_ok=True)
            raise
        except BaseException:
            # Byte-cap breach, HTTP status error, or a SIGALRM-driven abort.
            # A partial from THIS run may be meaningless, but bytes carried in
            # from previous runs are still valid, so only discard when nothing
            # was inherited.
            if not resuming or started_at == 0:
                tmp.unlink(missing_ok=True)
            raise
        return written


def create_http_client(settings: SeedingSettings) -> SeedingHttpClient:
    cache_backend: Optional[SimpleHTTPCache] = None
    if settings.http_cache_enabled:
        cache_backend = SimpleHTTPCache(settings.cache_path, settings.cache_ttl_seconds)
    return SeedingHttpClient(settings=settings, cache=cache_backend)


__all__ = ["SeedingHttpClient", "create_http_client"]
