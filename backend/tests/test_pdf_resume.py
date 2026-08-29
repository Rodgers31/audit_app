"""Resumable PDF download — the fix for silently-frozen COB domains.

Root cause (traced 2026-08-29): cob.go.ke serves a 12,407,501-byte NG-BIRR
report at ~43 KB/s with no Content-Length and no Accept-Ranges advertised.
That needs ~290s; the wall-clock cap was 180s. So EVERY nightly run
downloaded ~6MB, threw it away, fell back to a git-tracked fixture, and
reported ``[OK]``. national_budget had persisted nothing for months.

The server does honour ``Range`` (verified: 206 with a byte-exact offset),
so progress is now durable across runs and reconnects within a run.

Every test here fails against the pre-fix downloader.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from seeding.http_client import PdfDownloadError, PdfDownloadIncomplete
from seeding.pdf_download import (
    _looks_like_whole_pdf,
    _part_path,
    _verify_pdf_complete,
)

WHOLE = b"%PDF-1.7\n" + b"x" * 400 + b"\ntrailer\n%%EOF\n"
HEAD = WHOLE[:200]          # a truncated body: valid header, no trailer
TAIL = WHOLE[200:]


class TestCompletenessDetection:
    """Without Content-Length, %%EOF is the only end-of-document signal."""

    def test_whole_pdf_accepted(self, tmp_path):
        p = tmp_path / "a.pdf"
        p.write_bytes(WHOLE)
        _verify_pdf_complete(p, "u")  # must not raise
        assert _looks_like_whole_pdf(p) is True

    def test_truncated_pdf_rejected(self, tmp_path):
        # THE defect this guards: a cut-off body still starts with %PDF-, so
        # the header check alone would cache and parse a partial document.
        p = tmp_path / "b.pdf"
        p.write_bytes(HEAD)
        assert _looks_like_whole_pdf(p) is False
        with pytest.raises(PdfDownloadError, match="truncated"):
            _verify_pdf_complete(p, "u")

    def test_non_pdf_rejected(self, tmp_path):
        p = tmp_path / "c.pdf"
        p.write_bytes(b"<html>error page</html>")
        assert _looks_like_whole_pdf(p) is False

    def test_missing_file_is_not_complete(self, tmp_path):
        assert _looks_like_whole_pdf(tmp_path / "nope.pdf") is False


class _FakeStream:
    """Minimal httpx-like streaming response."""

    def __init__(self, body: bytes, status: int = 200, chunk: int = 64,
                 fail_after: int | None = None):
        self.body, self.status_code, self._chunk = body, status, chunk
        self._fail_after = fail_after

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)

    def iter_bytes(self):
        sent = 0
        for i in range(0, len(self.body), self._chunk):
            piece = self.body[i:i + self._chunk]
            if self._fail_after is not None and sent >= self._fail_after:
                raise httpx.ReadTimeout("simulated mid-stream drop")
            yield piece
            sent += len(piece)


class _FakeClient:
    """Records Range headers so tests can assert resumption behaviour."""

    def __init__(self, responder):
        self._responder = responder
        self.ranges: list[str | None] = []

    def stream(self, method, url, headers=None, timeout=None):
        rng = (headers or {}).get("Range")
        self.ranges.append(rng)
        return self._responder(rng)


def _client_wrapper(fake):
    """Wrap a _FakeClient in the SeedingHttpClient surface used downstream."""
    from seeding.http_client import SeedingHttpClient

    obj = object.__new__(SeedingHttpClient)
    obj._client = fake

    class _NullLimiter:
        def context(self):
            from contextlib import nullcontext

            return nullcontext()

    obj._rate_limiter = _NullLimiter()
    return obj


class TestResumption:
    def test_partial_is_retained_and_resumed(self, tmp_path):
        """The core fix: a timed-out transfer keeps its bytes; the next call
        sends Range and appends, completing the document."""
        part = tmp_path / "doc.part"
        dest = tmp_path / "doc.pdf"

        # Pass 1: server drops after 200 bytes.
        fake = _FakeClient(lambda rng: _FakeStream(WHOLE, fail_after=200))
        client = _client_wrapper(fake)
        with pytest.raises(PdfDownloadError):
            client.download_to_file(
                "u", dest, max_seconds=5, resume_part=part,
                completion_check=_looks_like_whole_pdf,
            )
        assert part.exists(), "partial must be RETAINED for the next run"
        got = part.stat().st_size
        assert got > 0

        # Pass 2: server honours the range and serves the remainder.
        def responder(rng):
            assert rng == f"bytes={got}-", f"expected resume header, got {rng}"
            return _FakeStream(WHOLE[got:], status=206)

        fake2 = _FakeClient(responder)
        client2 = _client_wrapper(fake2)
        size = client2.download_to_file(
            "u", dest, max_seconds=5, resume_part=part,
            completion_check=_looks_like_whole_pdf,
        )
        assert dest.read_bytes() == WHOLE, "resumed file must be byte-identical"
        assert size == len(WHOLE)

    def test_server_ignoring_range_restarts_instead_of_splicing(self, tmp_path):
        """A 200 answer to a Range request means the server is resending from
        zero. Appending would splice a duplicate prefix — it must restart."""
        part = tmp_path / "doc.part"
        dest = tmp_path / "doc.pdf"
        part.write_bytes(WHOLE[:200])  # pretend a previous run got this far

        fake = _FakeClient(lambda rng: _FakeStream(WHOLE, status=200))
        client = _client_wrapper(fake)
        client.download_to_file(
            "u", dest, max_seconds=5, resume_part=part,
            completion_check=_looks_like_whole_pdf,
        )
        assert dest.read_bytes() == WHOLE, "must not contain a spliced prefix"

    def test_completion_detected_when_stream_breaks_at_eof(self, tmp_path):
        """Regression: a transport error on the FINAL chunk left a complete
        file being re-requested past EOF forever (observed live)."""
        part = tmp_path / "doc.part"
        dest = tmp_path / "doc.pdf"
        part.write_bytes(WHOLE)  # already whole, stream never closed cleanly

        fake = _FakeClient(lambda rng: pytest.fail("must not re-request"))
        client = _client_wrapper(fake)
        size = client.download_to_file(
            "u", dest, max_seconds=5, resume_part=part,
            completion_check=_looks_like_whole_pdf,
        )
        assert size == len(WHOLE)
        assert dest.read_bytes() == WHOLE
        assert fake.ranges == [], "no request should have been issued"

    def test_part_path_is_url_keyed(self, tmp_path):
        """A resumed transfer must only ever continue the SAME document."""
        a = _part_path(tmp_path, "https://x/a.pdf")
        b = _part_path(tmp_path, "https://x/b.pdf")
        assert a != b and a.suffix == ".part"
