"""Tests for the streaming PDF downloader and cross-run PDF cache.

Locks in the two guards added for issue #119:
  * download_to_file enforces a TOTAL wall-clock cap (not httpx's per-chunk
    timeout) and raises a plain PdfDownloadError on breach, so a slow-CDN
    night falls back to the fixture instead of the per-domain SIGALRM firing
    mid-parse.
  * get_or_download_pdf reuses a cached PDF across runs and never caches a
    partial or non-PDF body.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from seeding.config import SeedingSettings
from seeding.http_client import PdfDownloadError, SeedingHttpClient
from seeding.pdf_download import get_or_download_pdf

_PDF_BODY = b"%PDF-1.7\n" + b"county budget rows\n" * 64


@pytest.fixture()
def settings(tmp_path) -> SeedingSettings:
    s = SeedingSettings(
        storage_path=tmp_path / "storage",
        cache_path=tmp_path / "cache",
        log_path=tmp_path / "logs" / "seed.log",
        retry_backoff=0.01,
        max_retries=1,
        http_cache_enabled=False,
        # Keep the rate limiter from sleeping during the test.
        rate_limit="1000/sec",
    )
    s.ensure_directories()
    return s


def _make_client(settings: SeedingSettings, handler) -> SeedingHttpClient:
    transport = httpx.MockTransport(handler)
    inner = httpx.Client(transport=transport, headers=settings.default_headers)
    return SeedingHttpClient(settings, cache=None, client=inner)


class TestDownloadToFile:
    def test_streams_body_to_disk_and_returns_size(self, settings, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=_PDF_BODY, request=request)

        dest = tmp_path / "out.pdf"
        with _make_client(settings, handler) as client:
            written = client.download_to_file(
                "https://cob.go.ke/download/x?wpdmdl=1", dest, max_seconds=180
            )

        assert written == len(_PDF_BODY)
        assert dest.read_bytes() == _PDF_BODY

    def test_raises_when_total_wallclock_cap_exceeded(self, settings, tmp_path):
        """A slow-but-steady stream that never trips httpx's per-chunk read
        timeout must still be aborted by the total wall-clock deadline."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=_PDF_BODY, request=request)

        # start=0, then every per-chunk check sees 10_000s elapsed > cap.
        clock = iter([0.0] + [10_000.0] * 64)
        dest = tmp_path / "slow.pdf"
        with _make_client(settings, handler) as client:
            with patch(
                "seeding.http_client.time.monotonic", lambda: next(clock)
            ):
                with pytest.raises(PdfDownloadError, match="wall-clock cap"):
                    client.download_to_file(
                        "https://cob.go.ke/download/x?wpdmdl=1",
                        dest,
                        max_seconds=180,
                    )

        # No truncated file at dest, and no leftover temp — a failed download
        # must not poison a later run that reuses the path (Copilot #120).
        assert not dest.exists()
        assert list(tmp_path.glob("*.part")) == []

    def test_raises_when_max_bytes_exceeded(self, settings, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=_PDF_BODY, request=request)

        dest = tmp_path / "big.pdf"
        with _make_client(settings, handler) as client:
            with pytest.raises(PdfDownloadError, match="byte cap"):
                client.download_to_file(
                    "https://cob.go.ke/download/x?wpdmdl=1",
                    dest,
                    max_seconds=180,
                    max_bytes=8,
                )

        assert not dest.exists()
        assert list(tmp_path.glob("*.part")) == []


class TestGetOrDownloadPdf:
    def _cache_dir(self, settings):
        return settings.cache_path / "pdfs"

    def test_downloads_then_serves_from_cache(self, settings):
        """Second call for the same URL must be a cache hit — no second
        network round-trip."""
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, content=_PDF_BODY, request=request)

        url = "https://cob.go.ke/download/county-birr?wpdmdl=16378"
        with _make_client(settings, handler) as client:
            first = get_or_download_pdf(
                client,
                url,
                cache_dir=self._cache_dir(settings),
                ttl_seconds=30 * 86_400,
                max_seconds=180,
            )
            second = get_or_download_pdf(
                client,
                url,
                cache_dir=self._cache_dir(settings),
                ttl_seconds=30 * 86_400,
                max_seconds=180,
            )

        assert first == second
        assert first.read_bytes() == _PDF_BODY
        assert calls["n"] == 1, "expected the second call to hit the cache"

    def test_rejects_and_does_not_cache_non_pdf_body(self, settings):
        """A 200 that returns an HTML error page must raise and leave nothing
        in the cache (so the next run retries rather than reusing junk)."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, content=b"<html>blocked</html>", request=request
            )

        url = "https://cob.go.ke/download/county-birr?wpdmdl=16378"
        cache_dir = self._cache_dir(settings)
        with _make_client(settings, handler) as client:
            with pytest.raises(PdfDownloadError, match="not a PDF"):
                get_or_download_pdf(
                    client,
                    url,
                    cache_dir=cache_dir,
                    ttl_seconds=30 * 86_400,
                    max_seconds=180,
                )

        # No cached .pdf, and no leftover temp files poisoning the dir.
        assert list(cache_dir.glob("*.pdf")) == []

    def test_metadata_write_failure_does_not_discard_download(self, settings):
        """A failed sidecar write must not turn a successful download into an
        exception (which the domain would treat as a reason to fall back to the
        fixture). The PDF stays available; only the cache bookkeeping is lost
        (Copilot #120)."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=_PDF_BODY, request=request)

        url = "https://cob.go.ke/download/county-birr?wpdmdl=16378"
        cache_dir = self._cache_dir(settings)
        real_write_text = Path.write_text

        def flaky_write_text(self, *args, **kwargs):
            # Only the JSON sidecar uses write_text; the PDF is streamed to disk
            # and os.replace-d, so this targets the metadata write alone.
            if self.suffix == ".json":
                raise OSError("simulated disk full")
            return real_write_text(self, *args, **kwargs)

        with _make_client(settings, handler) as client:
            with patch.object(Path, "write_text", flaky_write_text):
                pdf_path = get_or_download_pdf(
                    client,
                    url,
                    cache_dir=cache_dir,
                    ttl_seconds=30 * 86_400,
                    max_seconds=180,
                )

        assert pdf_path.exists()
        assert pdf_path.read_bytes() == _PDF_BODY
        # No sidecar written → the next run just re-downloads (cache miss).
        assert list(cache_dir.glob("*.json")) == []

    def test_expired_entry_triggers_redownload(self, settings):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, content=_PDF_BODY, request=request)

        url = "https://cob.go.ke/download/county-birr?wpdmdl=16378"
        cache_dir = self._cache_dir(settings)
        with _make_client(settings, handler) as client:
            get_or_download_pdf(
                client, url, cache_dir=cache_dir, ttl_seconds=3600, max_seconds=180
            )
            # ttl_seconds=0 disables reuse → forces a fresh download.
            get_or_download_pdf(
                client, url, cache_dir=cache_dir, ttl_seconds=0, max_seconds=180
            )

        assert calls["n"] == 2
