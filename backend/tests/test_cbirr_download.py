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
        self._get(settings, server, None)
        assert server.gets == 1
        # Rewrite the sidecar exactly as the pre-fingerprint code wrote it:
        # url, created_at, bytes — no "fingerprint" key at all.
        from seeding.pdf_download import _cache_paths

        _, meta_path = _cache_paths(settings.cache_path / "pdfs", EDITION_URL)
        legacy = json.loads(meta_path.read_text())
        meta_path.write_text(json.dumps({k: legacy[k] for k in ("url", "created_at", "bytes")}))
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


class TestAdversarialFindings:
    """An adversarial pass made the first version keep the wrong bytes."""

    def _get(self, settings, handler, fingerprint):
        from seeding.pdf_download import get_or_download_pdf

        with _client(settings, handler) as client:
            return get_or_download_pdf(
                client, EDITION_URL, cache_dir=settings.cache_path / "pdfs",
                ttl_seconds=86400, max_seconds=60, fingerprint=fingerprint,
            )

    def test_a_null_fingerprint_is_not_adopted_as_the_reissue(self, settings):
        """HEAD failed on the night A was fetched (fingerprint recorded as
        null); on a later night the server names "Final 6". A's bytes must
        not be relabelled Final 6."""
        server = _Server("x.pdf", _PDF_A)
        self._get(settings, server, None)
        server.body = _PDF_B
        path = self._get(settings, server, "Final 6")
        assert path.read_bytes() == _PDF_B

    def test_a_partial_of_a_known_issue_is_not_resumed_blind(self, settings):
        from seeding.pdf_download import _part_path

        cache = settings.cache_path / "pdfs"
        cache.mkdir(parents=True, exist_ok=True)
        part = _part_path(cache, EDITION_URL)
        part.write_bytes(_PDF_A[:40])
        part.with_suffix(".part.json").write_text(json.dumps({"fingerprint": "Final 5"}))
        def ranged(request):
            # cob.go.ke honours Range (206, to EOF) — which is what makes a
            # blind resume splice two documents together.
            rng = request.headers.get("range")
            if rng:
                start = int(rng.split("=")[1].split("-")[0])
                return httpx.Response(206, content=_PDF_B[start:], request=request)
            return httpx.Response(200, content=_PDF_B, request=request)

        path = self._get(settings, ranged, None)  # HEAD failed tonight
        assert path.read_bytes() == _PDF_B

    def test_a_failed_replacement_keeps_the_previous_good_file(self, settings):
        """A re-issue is announced but the new download fails: the cache must
        not be left empty (counties_budget shares this entry)."""
        from seeding.http_client import PdfDownloadError

        self._get(settings, _Server("x.pdf", _PDF_A), "Final 5")

        def html(request):
            return httpx.Response(200, content=b"<html>challenge</html>", request=request)

        with pytest.raises(PdfDownloadError):
            self._get(settings, html, "Final 6")
        from seeding.pdf_download import _cache_paths

        pdf, _ = _cache_paths(settings.cache_path / "pdfs", EDITION_URL)
        assert pdf.read_bytes() == _PDF_A

    def test_html_head_is_not_a_fingerprint(self, settings):
        from seeding.pdf_download import probe_fingerprint

        def challenge(request):
            return httpx.Response(200, headers={"Content-Type": "text/html", "Content-Length": "22"},
                                  request=request)

        with _client(settings, challenge) as client:
            assert probe_fingerprint(client, EDITION_URL) is None

    def test_a_per_request_etag_does_not_defeat_the_filename(self, settings):
        from seeding.pdf_download import probe_fingerprint

        n = {"i": 0}

        def handler(request):
            n["i"] += 1
            return httpx.Response(200, headers={
                "Content-disposition": 'attachment;filename="Final 5.pdf"', "ETag": f'"{n["i"]}"'},
                request=request)

        with _client(settings, handler) as client:
            assert probe_fingerprint(client, EDITION_URL) == probe_fingerprint(client, EDITION_URL)

    @pytest.mark.parametrize("sidecar", ["[]", '"x"', '{"created_at": null, "url": "u"}'])
    def test_a_malformed_sidecar_is_a_miss_not_an_error(self, settings, sidecar):
        from seeding.pdf_download import _cache_paths

        cache = settings.cache_path / "pdfs"
        cache.mkdir(parents=True, exist_ok=True)
        pdf, meta = _cache_paths(cache, EDITION_URL)
        pdf.write_bytes(_PDF_A)
        meta.write_text(sidecar)
        assert self._get(settings, _Server("x.pdf", _PDF_A), "Final 5").read_bytes() == _PDF_A
