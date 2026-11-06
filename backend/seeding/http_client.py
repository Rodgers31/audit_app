"""HTTP client tailored for seeding workloads."""

from __future__ import annotations

import logging
import math
import ssl
import signal
import threading
import re
import os
import tempfile
import time
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

import httpx
from tenacity import (
    Retrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from . import tls_chain
from .config import SeedingSettings
from .rate_limiter import RateLimiter
from .storage import SimpleHTTPCache
from services.receipt_store import configured_receipt_store, ReceiptStore
from services.response_receipts import capture_response

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


def _certificate_failure(exception: BaseException) -> bool:
    """Certificate/authority refusal is permanent for this verified origin."""
    seen = set()
    while exception is not None and id(exception) not in seen:
        seen.add(id(exception))
        if isinstance(exception, ssl.SSLCertVerificationError):
            return True
        if "CERTIFICATE_VERIFY_FAILED" in str(exception) or "certificate verify failed" in str(exception).lower():
            return True
        exception = exception.__cause__ or exception.__context__
    return False


def _positive_bound(value, name, *, integer=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value <= 0
            or integer and type(value) is not int):
        raise ValueError(f"{name} must be a finite positive {'integer' if integer else 'number'}")
    return value


@contextmanager
def _wall_clock_budget(seconds):
    """Interrupt DNS, rate-limit waits and body reads without extending CLI alarm.

    The seeder runs synchronously in a main-thread process. Unsupported direct
    callers refuse rather than silently offer a cooperative-only deadline.
    """
    if threading.current_thread() is not threading.main_thread() or not hasattr(signal, "setitimer"):
        raise ValueError("Bounded acquisition requires a main-thread interval timer")
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_delay, previous_interval = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()
    # An earlier domain alarm retains its stronger refusal contract.
    owns_timer = previous_delay == 0 or previous_delay > seconds
    def expired(signum, frame):
        raise httpx.TimeoutException("body acquisition wall-clock deadline exceeded")
    if owns_timer:
        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        if owns_timer:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
            if previous_delay:
                signal.setitimer(signal.ITIMER_REAL,
                    max(0.000001, previous_delay - (time.monotonic() - started)), previous_interval)


def _is_retryable(exception: BaseException) -> bool:
    if _certificate_failure(exception):
        return False
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
        receipt_store: Optional[ReceiptStore] = None,
    ) -> None:
        self._settings = settings
        self._logger = request_logger or logger
        tokens, period = settings.rate_limit_window
        self._rate_limiter = rate_limiter or RateLimiter(
            tokens=tokens, period_seconds=period
        )
        self._cache = cache
        self.receipt_store = receipt_store if receipt_store is not None else configured_receipt_store(settings)
        self._client = client or httpx.Client(
            timeout=settings.timeout_seconds,
            headers=settings.default_headers,
            follow_redirects=settings.http_follow_redirects,
        )
        # Built on demand, per host, only for publishers that send an
        # incomplete certificate chain. See seeding/tls_chain.py.
        self._injected_client = client is not None
        self._chain_clients: Dict[str, httpx.Client] = {}

    def _client_for(self, url: str) -> httpx.Client:
        """The client to use for ``url``.

        Some publishers serve their leaf certificate without the intermediate
        that signs it, which OpenSSL cannot chain and so refuses. For those
        hosts — and only those — this returns a client whose trust store has
        been completed with intermediates fetched and verified up to a root
        certifi already carries. Verification stays ON throughout; a host that
        cannot be completed safely keeps the normal client and is allowed to
        fail.
        """
        # getattr, not attribute access: tests build this surface with
        # object.__new__ and set only the fields they need, so __init__ has
        # not necessarily run.
        if getattr(self, "_injected_client", True) or not tls_chain.needs_completion(url):
            return self._client
        host = (urlparse(url).hostname or "").lower()
        chain_clients = getattr(self, "_chain_clients", None)
        if chain_clients is None:
            return self._client
        if host not in chain_clients:
            chain_clients[host] = tls_chain.verified_client(
                url, timeout=self._settings.timeout_seconds,
                headers=self._settings.default_headers,
                follow_redirects=self._settings.http_follow_redirects,
            )
        return chain_clients[host]

    def close(self) -> None:
        for client in getattr(self, "_chain_clients", {}).values():
            if client is not self._client:
                client.close()
        getattr(self, "_chain_clients", {}).clear()
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
        if "max_seconds" in kwargs or "max_bytes" in kwargs or "allowed_hosts" in kwargs:
            if method.upper() != "GET":
                raise ValueError("Bounded body acquisition requires GET")
            return self._bounded_get(url, raise_for_status=raise_for_status, **kwargs)
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
                # Cache acquisition time is unknown: do not invent a new download.
                cached_receipt = capture_response(
                    cached_response,
                    getattr(self, "receipt_store", None),
                    acquisition_kind="cached_acquisition_time_unknown",
                )
                cached_response.extensions["response_receipt"] = cached_receipt
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
                    response = self._client_for(url).request(
                        method_upper, url, **kwargs
                    )
                if raise_for_status:
                    response.raise_for_status()
                break

        if response is None:  # pragma: no cover - defensive
            raise RuntimeError("HTTP request did not produce a response")

        response.extensions["seeding_cache"] = False
        if method_upper == "GET" and not kwargs.get("stream"):
            kind = "api" if "json" in response.headers.get("content-type", "").lower() else "web"
            response.extensions["response_receipt"] = capture_response(
                response, getattr(self, "receipt_store", None), source_kind=kind
            )
        if (
            use_cache
            and self._cache
            and method_upper == "GET"
            and response.status_code == 200
            and not kwargs.get("stream")
        ):
            self._cache.set(response)
        return response

    def _bounded_get(self, url, *, max_seconds, **kwargs):
        _positive_bound(max_seconds, "max_seconds")
        with _wall_clock_budget(max_seconds):
            return self._bounded_get_body(url, max_seconds=max_seconds, **kwargs)

    def _bounded_get_body(self, url, *, max_seconds, max_bytes, allowed_hosts,
                     raise_for_status=True, **kwargs):
        """Acquire a small official body under cumulative retry/deadline caps.

        Partial bodies are discarded. Only the completed response is captured;
        a cache cannot turn retained bytes into a fresh source observation.
        """
        _positive_bound(max_seconds, "max_seconds")
        _positive_bound(max_bytes, "max_bytes", integer=True)
        attempts = _positive_bound(self._settings.max_retries, "max_retries", integer=True)
        backoff = _positive_bound(self._settings.retry_backoff, "retry_backoff")
        if (type(allowed_hosts) not in (set, frozenset) or not allowed_hosts
                or any(type(host) is not str or not host for host in allowed_hosts)):
            raise ValueError("Explicit official host set required")
        def check_origin(target):
            parsed = urlparse(str(target))
            if (parsed.scheme != "https" or parsed.hostname not in allowed_hosts
                    or parsed.username is not None or parsed.password is not None
                    or parsed.port not in (None, 443)):
                raise ValueError("Official HTTPS origin required")
        check_origin(url)
        if kwargs.pop("cache", False) or kwargs.pop("stream", False):
            raise ValueError("Bounded acquisition requires a fresh complete body")
        kwargs.pop("follow_redirects", None)
        supplied_timeout = kwargs.pop("timeout", self._settings.timeout_seconds)
        _positive_bound(supplied_timeout, "timeout")
        deadline = time.monotonic() + max_seconds
        consumed = 0
        for attempt in range(attempts):
            target = httpx.URL(url)
            try:
                # Redirects consume the same deadline and bytes, and are checked
                # before the next connection, not after an unsafe fetch.
                for redirects in range(6):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise httpx.TimeoutException("body acquisition deadline exceeded")
                    with self._rate_limiter.context():
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise httpx.TimeoutException("body acquisition deadline exceeded")
                        transport_client = self._client_for(str(target))
                        with transport_client.stream(
                            "GET", target, follow_redirects=False,
                            timeout=min(remaining, supplied_timeout), **kwargs
                        ) as response:
                            if response.status_code in (301, 302, 303, 307, 308):
                                redirected = response.url.join(response.headers["location"])
                                check_origin(redirected)
                                if ((redirected.scheme, redirected.host, redirected.port)
                                        != (target.scheme, target.host, target.port)
                                        and (any(h in response.request.headers for h in
                                                 ("authorization", "cookie", "proxy-authorization"))
                                             or getattr(transport_client, "auth", None) is not None
                                             or kwargs.get("auth") is not None
                                             or bool(getattr(transport_client, "cookies", None)))):
                                    # Manual stream() calls reapply client headers,
                                    # auth flows and cookies (including Set-Cookie
                                    # received on this redirect). Stripping only a
                                    # local headers dict cannot prevent that leak.
                                    raise ValueError("Credential-bearing official redirect refused")
                                target = redirected
                                continue
                            if raise_for_status:
                                response.raise_for_status()
                            if response.status_code != 200:
                                raise ValueError("Complete bounded acquisition requires HTTP 200")
                            chunks = []
                            for chunk in response.iter_bytes():
                                consumed += len(chunk)
                                if consumed > max_bytes:
                                    raise ValueError("Cumulative response byte cap exceeded")
                                if time.monotonic() >= deadline:
                                    raise httpx.TimeoutException("body acquisition deadline exceeded")
                                chunks.append(chunk)
                            if time.monotonic() >= deadline:
                                raise httpx.TimeoutException("body acquisition deadline exceeded")
                            decoded_headers = {k: v for k, v in response.headers.items()
                                               if k not in ("content-encoding", "content-length")}
                            complete = httpx.Response(response.status_code, headers=decoded_headers,
                                content=b"".join(chunks), request=response.request)
                            complete.extensions["seeding_cache"] = False
                            complete.extensions["response_receipt"] = capture_response(
                                complete, getattr(self, "receipt_store", None), source_kind="web")
                            return complete
                raise ValueError("Official redirect limit exceeded")
            except Exception as exc:
                if not _is_retryable(exc) or attempt + 1 >= attempts:
                    raise
                delay = min(backoff * 2 ** attempt, backoff * 8)
                if time.monotonic() + delay >= deadline:
                    raise httpx.TimeoutException("body recovery deadline exhausted") from exc
                self._logger.warning("Bounded body recovery attempt %d: %s", attempt + 1, type(exc).__name__)
                time.sleep(delay)
        raise RuntimeError("No acquisition attempted")

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("HEAD", url, **kwargs)

    def download_receipt(self, url: str) -> Optional[dict]:
        """Receipt for a completed full response from this client's last download."""
        return getattr(self, "_download_receipts", {}).get(url)

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

        Reconnects share the wall-clock and cumulative byte caps, with at most
        the configured transient attempts. Per-operation timeouts are capped
        by remaining time; partial bodies may resume under the rules below.

        Redirects are refused before their target is resolved or contacted,
        regardless of the injected/default client's redirect policy. A caller
        must separately review a publisher's replacement URL. A final receipt
        URL check cannot undo an already-followed redirect.

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
        _positive_bound(max_seconds, "max_seconds")
        if max_bytes is not None:
            _positive_bound(max_bytes, "max_bytes", integer=True)
        dest = Path(dest_path)
        if not hasattr(self, "_download_receipts"):
            self._download_receipts = {}
        self._download_receipts.pop(url, None)
        full_response = None
        base_headers = dict(headers or {})
        # Fail a dead connection fast (no bytes at all / no handshake), but let
        # a slow steady stream run up to the wall-clock cap the loop enforces.
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
        transferred = 0
        max_attempts = _positive_bound(getattr(getattr(self, "_settings", None), "max_retries", 3), "max_retries", integer=True)
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

                if max_bytes is not None and _on_disk() > max_bytes:
                    tmp.unlink(missing_ok=True)
                    raise PdfDownloadError(f"retained partial exceeded {max_bytes}-byte cap: {url}")
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
                    # Interrupt blocking limiter, DNS/connect and read phases;
                    # per-operation timeouts cannot bound total acquisition.
                    with _wall_clock_budget(remaining), self._rate_limiter.context():
                        with self._client_for(url).stream(
                            "GET", url, headers=request_headers, follow_redirects=False,
                            timeout=httpx.Timeout(min(remaining, 30.0), connect=min(remaining, 15.0))
                        ) as response:
                            if 300 <= response.status_code < 400:
                                # Even raise_for_status=False must not consume a
                                # redirect body, retain it, or treat it as a PDF.
                                raise PdfDownloadError("Source download redirects refused")
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
                                range_start = _range_start(response)
                                if range_start != offset:
                                    raise PdfDownloadError("Unverified Content-Range cannot resume a PDF")
                            if mode == "wb":
                                _remember_validator(response)
                            with tmp.open(mode) as handle:
                                for chunk in response.iter_bytes():
                                    transferred += len(chunk)
                                    if max_bytes is not None and transferred > max_bytes:
                                        raise PdfDownloadError(f"cumulative transfer exceeded {max_bytes}-byte cap: {url}")
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
                            # A single complete decoded body is distinct from
                            # assembled ranges or a stream interrupted at EOF.
                            if mode == "wb" and response.status_code == 200:
                                full_response = (response.status_code, dict(response.headers), response.request)
                    # iter_bytes() ran to completion => the server closed the
                    # body normally, so we have the whole document.
                    complete = True
                    break
                except (httpx.TransportError, httpx.StreamError) as exc:
                    if _certificate_failure(exc):
                        # Trust refusal is neither byte progress nor a resumable
                        # outage. The PDF cache wrapper preserves last-good bytes.
                        tmp.unlink(missing_ok=True)
                        if validator_path is not None:
                            validator_path.unlink(missing_ok=True)
                        raise
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
                    if attempt >= max_attempts:
                        # Progress never grants unlimited reconnect attempts.
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
            if full_response is not None:
                from services.response_receipts import capture_response

                status, response_headers, request = full_response
                store = getattr(self, "receipt_store", None)
                if store is None:
                    store = configured_receipt_store(self._settings)
                # iter_bytes() already decoded transfer content. Reusing the
                # encoding header would make httpx decompress these bytes twice.
                decoded_headers = {k: v for k, v in response_headers.items() if k.lower() not in ("content-encoding", "content-length")}
                receipt = capture_response(httpx.Response(status, headers=decoded_headers,
                    content=dest.read_bytes(), request=request), store, source_kind="pdf")
                from services.response_receipts import copy_receipt

                receipt = copy_receipt(
                    receipt,
                    content_encoding=response_headers.get("content-encoding"),
                    digest_scope="decoded_stream_body",
                )
                self._download_receipts[url] = receipt
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
