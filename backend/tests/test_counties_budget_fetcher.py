"""Tests for the counties_budget fetcher's COB discovery strategies.

Added April-2026 after a live-seed smoke test revealed:
  * The COB landing pages return HTTP 415 when the seeder sends the
    default `Accept: */*` (WAF/Cloudflare Accept-negotiation).
  * The COB WordPress REST API at /wp-json/wp/v2/media returns 200
    reliably and is the preferred discovery path.

These tests lock in the contract so regressions on either path are
caught locally rather than silently falling through to the fixture.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List
from unittest.mock import patch

import httpx
import pytest
from seeding.config import SeedingSettings
from seeding.domains.counties_budget import fetcher as cb_fetcher
from seeding.http_client import SeedingHttpClient


@pytest.fixture()
def settings(tmp_path) -> SeedingSettings:
    s = SeedingSettings(
        storage_path=tmp_path / "storage",
        cache_path=tmp_path / "cache",
        log_path=tmp_path / "logs" / "seed.log",
        retry_backoff=0.01,
        max_retries=1,
        http_cache_enabled=False,
        live_pdf_fetch_enabled=True,
    )
    s.ensure_directories()
    return s


def _make_client(
    settings: SeedingSettings, handler
) -> SeedingHttpClient:
    """Build a SeedingHttpClient backed by an httpx.MockTransport."""
    transport = httpx.MockTransport(handler)
    inner = httpx.Client(
        transport=transport, headers=settings.default_headers
    )
    return SeedingHttpClient(settings, cache=None, client=inner)


def _wp_api_payload(
    pdfs: List[Dict[str, Any]], *, non_pdf_count: int = 0
) -> List[Dict[str, Any]]:
    """Build a WP REST media response with the supplied PDF entries
    and some non-county noise (press releases, logos) in front."""
    noise = [
        {
            "id": 9000 + i,
            "date": "2024-01-01T00:00:00",
            "slug": f"unrelated-logo-{i}",
            "title": {"rendered": f"Press kit logo {i}"},
            "mime_type": "image/png",
            "source_url": f"https://cob.go.ke/wp-content/uploads/logo-{i}.png",
        }
        for i in range(non_pdf_count)
    ]
    return noise + pdfs


class TestWpApiDiscovery:
    """The WP REST API path must be tried first and must pick the
    newest county-tagged PDF."""

    def test_picks_newest_county_pdf_from_api(self, settings):
        """The API returns items date-desc; fetcher should pick the
        best-scoring county-related PDF that also responds 200 to a
        HEAD probe (the liveness check guards against stale feed
        entries — cf. prod bug where a 2015 404'd link was chosen)."""
        captured_requests: List[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            if "wp-json/wp/v2/media" in request.url.path:
                body = _wp_api_payload(
                    [
                        {
                            "id": 100,
                            "date": "2025-03-15T09:00:00",
                            "slug": "consolidated-county-birr-fy2024-25-q2",
                            "title": {
                                "rendered": "Consolidated County BIRR FY2024/25 Q2"
                            },
                            "mime_type": "application/pdf",
                            "source_url": (
                                "https://cob.go.ke/wp-content/uploads/"
                                "2025/03/county-birr-fy2024-25-q2.pdf"
                            ),
                        },
                        {
                            "id": 99,
                            "date": "2024-12-01T09:00:00",
                            "slug": "national-government-birr-annual",
                            "title": {
                                "rendered": "National Government BIRR Annual"
                            },
                            "mime_type": "application/pdf",
                            "source_url": (
                                "https://cob.go.ke/wp-content/uploads/"
                                "2024/12/ng-birr-annual.pdf"
                            ),
                        },
                    ]
                )
                return httpx.Response(
                    200, json=body, request=request
                )
            # HEAD probes of PDF URLs: report 200 so the liveness
            # check accepts the chosen candidate.
            if request.method == "HEAD" and request.url.path.endswith(".pdf"):
                return httpx.Response(200, request=request)
            # Any other URL is unexpected — force an obvious failure
            return httpx.Response(500, request=request)

        with _make_client(settings, handler) as client:
            url = cb_fetcher._discover_latest_county_birr_via_wp_api(
                client, settings
            )

        assert url == (
            "https://cob.go.ke/wp-content/uploads/"
            "2025/03/county-birr-fy2024-25-q2.pdf"
        )
        # Must have sent Accept: application/json, not the default */*.
        wp_req = next(
            r for r in captured_requests if "wp-json" in r.url.path
        )
        assert wp_req.headers.get("accept") == "application/json"

    def test_returns_none_when_no_county_pdfs(self, settings):
        """If the API returns only non-county PDFs, the discovery
        helper must return None so the HTML fallback can try."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_wp_api_payload(
                    [
                        {
                            "id": 1,
                            "date": "2025-01-01T00:00:00",
                            "slug": "national-budget-circular",
                            "title": {"rendered": "National Budget Circular"},
                            "mime_type": "application/pdf",
                            "source_url": (
                                "https://cob.go.ke/wp-content/uploads/"
                                "2025/01/ng-circular.pdf"
                            ),
                        }
                    ]
                ),
                request=request,
            )

        with _make_client(settings, handler) as client:
            url = cb_fetcher._discover_latest_county_birr_via_wp_api(
                client, settings
            )
        assert url is None

    def test_falls_through_when_top_candidate_404s(self, settings):
        """Regression: CI run 24901989493 returned a 2015 Makueni file
        as 'latest' and that URL had since been removed from the CDN,
        returning 404. The selector must HEAD-probe candidates in
        rank order and skip dead ones, falling through to a live
        alternate rather than poisoning the whole domain run."""

        def handler(request: httpx.Request) -> httpx.Response:
            if "wp-json/wp/v2/media" in request.url.path:
                return httpx.Response(
                    200,
                    json=_wp_api_payload(
                        [
                            # Top-ranked by score (consolidated + c-birr)
                            # but the CDN has since deleted it.
                            {
                                "id": 50,
                                "date": "2025-04-01T00:00:00",
                                "slug": "consolidated-county-birr-fy2025-26",
                                "title": {
                                    "rendered": "Consolidated County BIRR FY2025/26"
                                },
                                "mime_type": "application/pdf",
                                "source_url": (
                                    "https://cob.go.ke/wp-content/uploads/"
                                    "2025/04/stale.pdf"
                                ),
                            },
                            # Lower score (only matches "county") but
                            # still alive — should be returned after
                            # the first candidate 404s.
                            {
                                "id": 40,
                                "date": "2025-03-01T00:00:00",
                                "slug": "county-backup-report",
                                "title": {
                                    "rendered": "County Backup Report"
                                },
                                "mime_type": "application/pdf",
                                "source_url": (
                                    "https://cob.go.ke/wp-content/uploads/"
                                    "2025/03/alive.pdf"
                                ),
                            },
                        ]
                    ),
                    request=request,
                )
            if request.method == "HEAD":
                if "stale.pdf" in request.url.path:
                    return httpx.Response(404, request=request)
                if "alive.pdf" in request.url.path:
                    return httpx.Response(200, request=request)
            return httpx.Response(500, request=request)

        with _make_client(settings, handler) as client:
            url = cb_fetcher._discover_latest_county_birr_via_wp_api(
                client, settings
            )

        assert url is not None
        assert url.endswith("alive.pdf"), f"expected fallthrough to alive.pdf, got {url}"

    def test_skips_items_without_pdf_source_url(self, settings):
        """Items whose source_url is missing or not a .pdf must be
        ignored, not blindly returned."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 1,
                        "date": "2025-02-01T00:00:00",
                        "slug": "county-report",
                        "title": {"rendered": "County Report"},
                        "mime_type": "application/pdf",
                        "source_url": None,
                    }
                ],
                request=request,
            )

        with _make_client(settings, handler) as client:
            url = cb_fetcher._discover_latest_county_birr_via_wp_api(
                client, settings
            )
        assert url is None


class TestHtmlFallback:
    """When the WP API is unavailable, the fetcher falls back to the
    HTML landing pages with browser-shaped headers so the CDN does not
    reply with 415."""

    def test_html_fallback_sends_browser_accept_header(self, settings):
        """Regression: default `Accept: */*` triggered HTTP 415 on
        cob.go.ke. Verify the fetcher sends a browser-style Accept."""
        captured_requests: List[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            # Simulate the production bug: reject `*/*` with 415.
            accept = request.headers.get("accept", "")
            if "text/html" not in accept:
                return httpx.Response(415, request=request)
            # Otherwise return a minimal HTML page with a county PDF link.
            body = (
                '<html><body><a href="/wp-content/uploads/2025/03/'
                'consolidated-county-birr-q2.pdf">Latest</a></body></html>'
            )
            return httpx.Response(200, text=body, request=request)

        with _make_client(settings, handler) as client:
            url = cb_fetcher._discover_latest_county_birr_via_html(
                client, settings
            )

        # Must have discovered the PDF; 415 reproduced the prod bug.
        assert url is not None
        assert url.endswith("consolidated-county-birr-q2.pdf")
        # Must have sent a browser-style Accept header on at least
        # one landing-page probe.
        html_probes = [
            r
            for r in captured_requests
            if "publications" in r.url.path or "reports" in r.url.path
        ]
        assert html_probes, "expected at least one HTML landing probe"
        assert any(
            "text/html" in (r.headers.get("accept") or "")
            for r in html_probes
        )

    def test_html_fallback_returns_none_when_all_pages_unreachable(
        self, settings
    ):
        """If every landing URL 415s or 5xxs, return None rather than
        raising — the outer fetcher then falls through to the fixture."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(415, request=request)

        with _make_client(settings, handler) as client:
            url = cb_fetcher._discover_latest_county_birr_via_html(
                client, settings
            )
        assert url is None


class TestWpdmLinkParsing:
    """COB wraps PDFs in the WordPress Download Manager plugin. The
    regex must pick up `?wpdmdl=NNN` anchors and pick the newest (by
    ID) county-matching link, since higher IDs == newer uploads."""

    def test_picks_highest_wpdmdl_county_link(self):
        """Given three WPDM download links, two county + one national,
        return the county link with the highest ID.

        Uses realistic COB HTML (single-line onclick handlers — that's
        how the WPDM plugin emits them in production).
        """
        html = (
            "<html><body>"
            """<a class='wpdm-download-link' href='#' onclick="location.href='https://cob.go.ke/download/national-government-birr-q1-fy2025-26/?wpdmdl=16350';return false;">NG Q1</a>"""
            """<a class='wpdm-download-link' href='#' onclick="location.href='https://cob.go.ke/download/county-governments-birr-first-half-fy2025-26/?wpdmdl=16349';return false;">County H1</a>"""
            """<a class='wpdm-download-link' href='#' onclick="location.href='https://cob.go.ke/download/county-governments-birr-q1-fy2025-26/?wpdmdl=16323';return false;">County Q1</a>"""
            "</body></html>"
        )
        url = cb_fetcher._discover_latest_county_birr_pdf(
            html, "https://cob.go.ke/publications/"
        )
        # Must pick the county link with the highest wpdmdl (16349),
        # not the national link (even though 16350 is higher) and not
        # the older county one (16323).
        assert url is not None
        assert "wpdmdl=16349" in url
        assert "county-governments-birr-first-half-fy2025-26" in url

    def test_falls_back_to_wpdm_pool_when_no_county_match(self):
        """If no WPDM link is county-related, return the newest overall
        WPDM link rather than None — the outer parser validates the PDF
        structure so a mismatched slug isn't silently accepted."""
        html = (
            """<a onclick="location.href='https://cob.go.ke/download/foo/?wpdmdl=900';return false;">A</a>"""
            """<a onclick="location.href='https://cob.go.ke/download/bar/?wpdmdl=1000';return false;">B</a>"""
        )
        url = cb_fetcher._discover_latest_county_birr_pdf(
            html, "https://cob.go.ke/publications/"
        )
        assert url is not None
        assert "wpdmdl=1000" in url

    def test_still_handles_direct_pdf_hrefs_when_no_wpdm_present(self):
        """Legacy / fixture HTML with direct .pdf hrefs must still work."""
        html = '<a href="/wp-content/uploads/county-birr-q2.pdf">Latest</a>'
        url = cb_fetcher._discover_latest_county_birr_pdf(
            html, "https://cob.go.ke/publications/"
        )
        assert url is not None
        assert url.endswith("county-birr-q2.pdf")


class TestFetchBudgetPayloadStrategyOrder:
    """The outer `fetch_budget_payload` must prefer the WP API and only
    probe the HTML pages when the API yields nothing."""

    def test_wp_api_success_skips_html_probe(self, settings):
        """If the WP API returns a usable PDF, the fetcher must NOT
        hit any /publications/ landing page — saves latency and avoids
        the 415 noise entirely."""
        seen_urls: List[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_urls.append(str(request.url))
            if "wp-json" in request.url.path:
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": 7,
                            "date": "2025-03-01T00:00:00",
                            "slug": "consolidated-county-birr",
                            "title": {
                                "rendered": "Consolidated County BIRR"
                            },
                            "mime_type": "application/pdf",
                            "source_url": (
                                "https://cob.go.ke/wp-content/uploads/"
                                "2025/03/county-birr.pdf"
                            ),
                        }
                    ],
                    request=request,
                )
            # Liveness-probe HEAD on the chosen PDF must succeed.
            if request.method == "HEAD" and request.url.path.endswith(".pdf"):
                return httpx.Response(200, request=request)
            # Any other URL is an unexpected code path.
            return httpx.Response(500, request=request)

        with _make_client(settings, handler) as client:
            # Stub the PDF-download step so we don't actually parse.
            with patch.object(
                cb_fetcher, "_download_and_parse_county_pdf"
            ) as mock_dl:
                mock_dl.return_value = [{"ok": True}]
                result = cb_fetcher._fetch_from_cob_county_pdf(
                    client, settings
                )

        assert result == [{"ok": True}]
        # No /publications/ or /reports/ landing pages were probed.
        assert not any(
            "/publications/" in u or "/reports/" in u for u in seen_urls
        )
