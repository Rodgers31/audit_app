"""Tests for the USD/KES exchange rate utility."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from utils.exchange_rate import FALLBACK_RATE, get_usd_kes_rate, _fetch_rate


@pytest.fixture(autouse=True)
def _clear_caches(tmp_path, monkeypatch):
    """Disable file and Redis caches for each test."""
    # Point file cache to a temp file (always missing = no file cache hit)
    monkeypatch.setattr("utils.exchange_rate.FILE_CACHE_PATH", str(tmp_path / "rate.json"))
    # Make Redis unavailable so we fall through to HTTP
    with patch("utils.exchange_rate._get_redis_cache", return_value=None):
        yield


class TestFetchRate:
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"rates": {"KES": 131.5}}
        mock_resp.raise_for_status = MagicMock()

        with patch("utils.exchange_rate.httpx.get", return_value=mock_resp):
            assert _fetch_rate("https://example.com") == 131.5

    def test_missing_kes(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"rates": {"EUR": 0.92}}
        mock_resp.raise_for_status = MagicMock()

        with patch("utils.exchange_rate.httpx.get", return_value=mock_resp):
            assert _fetch_rate("https://example.com") is None

    def test_network_error(self):
        with patch("utils.exchange_rate.httpx.get", side_effect=httpx.ConnectError("fail")):
            assert _fetch_rate("https://example.com") is None


class TestGetUsdKesRate:
    def test_returns_cached_value(self, tmp_path, monkeypatch):
        """File cache hit returns cached value without HTTP call."""
        import json, time
        cache_file = tmp_path / "rate.json"
        cache_file.write_text(json.dumps({"rate": 130.0, "timestamp": time.time()}))
        monkeypatch.setattr("utils.exchange_rate.FILE_CACHE_PATH", str(cache_file))
        monkeypatch.setattr("utils.exchange_rate._get_redis_cache", lambda: None)

        with patch("utils.exchange_rate.httpx.get") as mock_get:
            assert get_usd_kes_rate() == 130.0
            mock_get.assert_not_called()

    def test_fetches_and_caches_on_miss(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"rates": {"KES": 132.0}}
        mock_resp.raise_for_status = MagicMock()

        with patch("utils.exchange_rate.httpx.get", return_value=mock_resp):
            rate = get_usd_kes_rate()

        assert rate == 132.0

    def test_falls_back_on_all_failures(self):
        with patch("utils.exchange_rate.httpx.get", side_effect=httpx.ConnectError("fail")):
            assert get_usd_kes_rate() == FALLBACK_RATE

    def test_tries_fallback_url(self):
        fail_resp = httpx.ConnectError("fail")
        ok_resp = MagicMock()
        ok_resp.json.return_value = {"rates": {"KES": 133.0}}
        ok_resp.raise_for_status = MagicMock()

        with patch("utils.exchange_rate.httpx.get", side_effect=[fail_resp, ok_resp]):
            assert get_usd_kes_rate() == 133.0
