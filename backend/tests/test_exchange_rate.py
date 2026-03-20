"""Tests for the USD/KES exchange rate utility."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from utils.exchange_rate import FALLBACK_RATE, get_usd_kes_rate, _fetch_rate


@pytest.fixture(autouse=True)
def _clear_cache():
    """Ensure cache is clean for each test."""
    with patch("utils.exchange_rate.cache") as mock_cache:
        mock_cache.get.return_value = None
        yield mock_cache


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
    def test_returns_cached_value(self, _clear_cache):
        _clear_cache.get.return_value = 130.0
        assert get_usd_kes_rate() == 130.0

    def test_fetches_and_caches_on_miss(self, _clear_cache):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"rates": {"KES": 132.0}}
        mock_resp.raise_for_status = MagicMock()

        with patch("utils.exchange_rate.httpx.get", return_value=mock_resp):
            rate = get_usd_kes_rate()

        assert rate == 132.0
        _clear_cache.set.assert_called_once()

    def test_falls_back_on_all_failures(self, _clear_cache):
        with patch("utils.exchange_rate.httpx.get", side_effect=httpx.ConnectError("fail")):
            assert get_usd_kes_rate() == FALLBACK_RATE

    def test_tries_fallback_url(self, _clear_cache):
        fail_resp = httpx.ConnectError("fail")
        ok_resp = MagicMock()
        ok_resp.json.return_value = {"rates": {"KES": 133.0}}
        ok_resp.raise_for_status = MagicMock()

        with patch("utils.exchange_rate.httpx.get", side_effect=[fail_resp, ok_resp]):
            assert get_usd_kes_rate() == 133.0
