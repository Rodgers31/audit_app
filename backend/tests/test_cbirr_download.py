"""The shared CBIRR download: one fetch, keyed on what the server serves (#230).

COB re-issues files under the same ``?wpdmdl=`` link ("... Final 5.pdf") and
sends no ETag, Last-Modified or Content-Length. These tests pin that a
re-issue is fetched, that two domains share one download, and that the
listing's newest edition is found in the page COB actually serves.

Imports only ``seeding.pdf_download`` at module level, so the file collects
against the code before this change and its failures there are behavioural.
"""

from __future__ import annotations

import json
import pathlib

import httpx
import pytest

from seeding.config import SeedingSettings
from seeding.http_client import SeedingHttpClient

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "cob_cbirr"
LISTING = (FIXTURES / "listing_2026-09-26.html").read_text(encoding="utf-8")
EDITION_URL = (
    "https://cob.go.ke/download/county-governments-budget-implementation-review-"
    "report-for-the-financial-year-2025-26/?wpdmdl=16482"
)

_PDF_A = b"%PDF-1.7\n" + b"edition A\n" * 64 + b"%%EOF\n"
_PDF_B = b"%PDF-1.7\n" + b"edition B, re-issued\n" * 64 + b"%%EOF\n"


@pytest.fixture()
def settings(tmp_path) -> SeedingSettings:
    s = SeedingSettings(
        storage_path=tmp_path / "storage",
        cache_path=tmp_path / "cache",
        log_path=tmp_path / "logs" / "seed.log",
        retry_backoff=0.01,
        max_retries=1,
        http_cache_enabled=False,
        rate_limit="1000/sec",
    )
    s.ensure_directories()
    return s


def _client(settings, handler) -> SeedingHttpClient:
    inner = httpx.Client(transport=httpx.MockTransport(handler), headers=settings.default_headers)
    return SeedingHttpClient(settings, cache=None, client=inner)


class _Server:
    """cob.go.ke as observed: HEAD names the file, GET streams it."""

    def __init__(self, filename: str, body: bytes):
        self.filename, self.body = filename, body
        self.gets = 0
        self.heads = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        headers = {"Content-disposition": f'attachment;filename="{self.filename}"'}
        if request.method == "HEAD":
            self.heads += 1
            return httpx.Response(200, headers=headers, request=request)
        self.gets += 1
        return httpx.Response(200, content=self.body, headers=headers, request=request)


class TestContentKeyedCache:
    def _get(self, settings, server, fingerprint):
        from seeding.pdf_download import get_or_download_pdf

        with _client(settings, server) as client:
            return get_or_download_pdf(
                client, EDITION_URL, cache_dir=settings.cache_path / "pdfs",
                ttl_seconds=86400, max_seconds=60, fingerprint=fingerprint,
            )

    def test_same_link_reissued_is_downloaded_again(self, settings):
        server = _Server("CGBIRR FY 2025_26 August 2026 Final 5.pdf", _PDF_A)
        self._get(settings, server, "Final 5")
        assert server.gets == 1
        self._get(settings, server, "Final 5")
        assert server.gets == 1, "same fingerprint is a cache hit"
        server.body = _PDF_B
        path = self._get(settings, server, "Final 6")
        assert server.gets == 2, "a re-issue under the same link must be fetched"
        assert path.read_bytes() == _PDF_B

    def test_sidecar_records_the_bytes(self, settings):
        import hashlib

        from seeding.pdf_download import cached_pdf_meta

        self._get(settings, _Server("x.pdf", _PDF_A), "fp")
        meta = cached_pdf_meta(settings.cache_path / "pdfs", EDITION_URL)
        assert meta["sha256"] == hashlib.sha256(_PDF_A).hexdigest()
        assert meta["fingerprint"] == "fp"

    def test_pre_fingerprint_entry_is_adopted_not_refetched(self, settings):
        """Every PDF in the CI cache on the day this ships has no recorded
        fingerprint. Evicting them would cost COB's 50MB at 43 KB/s."""
        server = _Server("x.pdf", _PDF_A)
        self._get(settings, server, None)  # the old code path
        assert server.gets == 1
        self._get(settings, server, "Final 5")
        assert server.gets == 1
        from seeding.pdf_download import cached_pdf_meta

        meta = cached_pdf_meta(settings.cache_path / "pdfs", EDITION_URL)
        assert meta["fingerprint_adopted"] is True

    def test_partial_of_the_old_issue_is_not_resumed(self, settings):
        from seeding.pdf_download import _part_path

        cache = settings.cache_path / "pdfs"
        cache.mkdir(parents=True, exist_ok=True)
        part = _part_path(cache, EDITION_URL)
        part.write_bytes(_PDF_A[:40])
        part.with_suffix(".part.json").write_text(json.dumps({"fingerprint": "Final 5"}))
        path = self._get(settings, _Server("x.pdf", _PDF_B), "Final 6")
        assert path.read_bytes() == _PDF_B  # not A's head spliced onto B

    def test_two_domains_share_one_download(self, settings):
        """counties_budget and stalled_projects both call download_cbirr."""
        from seeding import cob_cbirr

        cob_cbirr._FINGERPRINTS.clear()
        server = _Server("CGBIRR FY 2025_26 August 2026 Final 5.pdf", _PDF_A)
        with _client(settings, server) as client:
            first = cob_cbirr.download_cbirr(client, EDITION_URL, settings)
            second = cob_cbirr.download_cbirr(client, EDITION_URL, settings)
        assert (server.gets, server.heads) == (1, 1)
        assert first.path == second.path and first.sha256 == second.sha256
        assert "Final 5" in first.fingerprint


class TestListing:
    def test_newest_edition_first_from_the_live_page(self):
        from seeding.cob_cbirr import parse_listing

        editions = parse_listing(LISTING)
        assert len(editions) == 20
        assert editions[0].wpdmdl == 16482
        assert editions[0].url == EDITION_URL
        assert [e.wpdmdl for e in editions] == sorted((e.wpdmdl for e in editions), reverse=True)
