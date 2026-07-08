"""Tests for the national_budget fetcher's live-PDF path (issue #119 guard).

Mirrors the counties_budget coverage: a slow-CDN NG-BIRR download must fall
back to the fixture — via the wall-clock-capped, cross-run-cached
get_or_download_pdf helper — rather than hard-failing the domain, and the
happy path must route through that helper (not an eager, uncapped client.get).
"""

from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from seeding.config import SeedingSettings
from seeding.domains.national_budget import fetcher as nb_fetcher
from seeding.http_client import PdfDownloadError, SeedingHttpClient


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
        rate_limit="1000/sec",
    )
    s.ensure_directories()
    return s


def _make_client(settings: SeedingSettings, handler) -> SeedingHttpClient:
    transport = httpx.MockTransport(handler)
    inner = httpx.Client(transport=transport, headers=settings.default_headers)
    return SeedingHttpClient(settings, cache=None, client=inner)


def _page_handler(request: httpx.Request) -> httpx.Response:
    # The COB reports-page fetch; discovery is patched, so any 200 is fine.
    return httpx.Response(200, text="<html></html>", request=request)


def test_download_timeout_recovers_via_fixture(settings):
    """A wall-clock-capped download raises a plain PdfDownloadError, which
    fetch_national_budget_payload's `except Exception` catches → fixture.
    (Unlike the CLI's BaseException DomainTimeoutError, which would abort the
    whole run — the exact issue #119 failure mode.)"""
    fake_pdf_url = "https://cob.go.ke/download/ng-birr?wpdmdl=16376"
    with _make_client(settings, _page_handler) as client:
        with patch.object(
            nb_fetcher, "_discover_latest_ng_birr_pdf", return_value=fake_pdf_url
        ), patch.object(
            client,
            "download_to_file",
            side_effect=PdfDownloadError(
                "download exceeded 180s wall-clock cap after 4096 bytes"
            ),
        ):
            payload = nb_fetcher.fetch_national_budget_payload(client, settings)

    # Recovered cleanly with real fixture rows — no exception propagated.
    assert isinstance(payload, list)
    assert len(payload) > 0


def test_live_path_routes_through_cached_download_helper(settings, tmp_path):
    """The happy path must fetch via get_or_download_pdf (cross-run cache +
    wall-clock cap) and pass the settings-derived cache dir / TTL / cap — not
    an eager uncapped client.get."""
    fake_pdf = tmp_path / "ng.pdf"
    fake_pdf.write_bytes(b"%PDF-1.7\nx")
    fake_pdf_url = "https://cob.go.ke/download/ng-birr?wpdmdl=16376"

    class _Rec:
        sector = "Health"
        subcategory = None
        net_estimates = 100
        exchequer_issues = 90

    period = type(
        "_Period",
        (),
        {
            "label": "FY 2025/26 9M",
            "start_date": datetime.date(2025, 7, 1),
            "end_date": datetime.date(2026, 3, 31),
        },
    )()

    with _make_client(settings, _page_handler) as client:
        with patch.object(
            nb_fetcher, "_discover_latest_ng_birr_pdf", return_value=fake_pdf_url
        ), patch(
            "seeding.pdf_download.get_or_download_pdf", return_value=fake_pdf
        ) as mock_dl, patch(
            "seeding.domains.national_budget.pdf_parser.NgBirrSectoralParser"
        ) as MockParser:
            MockParser.return_value.parse.return_value = (period, [_Rec()])
            payload = nb_fetcher.fetch_national_budget_payload(client, settings)

    assert mock_dl.called, "expected the fetcher to use get_or_download_pdf"
    kwargs = mock_dl.call_args.kwargs
    assert kwargs["cache_dir"] == settings.cache_path / "pdfs"
    assert kwargs["max_seconds"] == settings.pdf_download_timeout_seconds
    assert kwargs["ttl_seconds"] == settings.pdf_cache_ttl_seconds
    assert [r["category"] for r in payload] == ["Health"]
