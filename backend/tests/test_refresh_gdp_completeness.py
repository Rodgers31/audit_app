"""Exercise the actual request and retained response, including pagination."""
import copy
import math

import httpx
import pytest

from seeding.config import SeedingSettings
from seeding.domains.debt_timeline import fetcher
from seeding.freshness import get, reset
from seeding.http_client import SeedingHttpClient
from services.receipt_store import LocalReceiptStore


def _client(tmp_path, *, always_partial=False, years=None, values=None, metadata=None):
    def publisher(request):
        size = int(request.url.params.get('per_page', '50'))
        rows = [dict(indicator={'id': 'NY.GDP.MKTP.CN'},
                     country={'id': 'KE'}, countryiso3code='KEN',
                     date=str(year), value=(values or {}).get(year, year * 100_000_000), unit='')
                for year in (range(2025, 1959, -1) if years is None else years)]
        header = dict(page=1, pages=3 if always_partial else math.ceil(len(rows) / size), total=len(rows))
        header.update(metadata or {})
        payload = [header, rows[:size]]
        return httpx.Response(200, json=payload)
    settings = SeedingSettings(_env_file=None, storage_path=tmp_path,
                               http_cache_enabled=False, rate_limit='1000/sec')
    return SeedingHttpClient(settings,
        client=httpx.Client(transport=httpx.MockTransport(publisher)),
        receipt_store=LocalReceiptStore(tmp_path / 'receipts'))


def test_timeline_reads_complete_history_including_older_years(tmp_path):
    with _client(tmp_path) as client:
        values = fetcher._fetch_wb_gdp(client)
    assert len(values) == 66
    assert values[1960] == 196_000_000_000
    assert values[2025] == 202_500_000_000
    assert values.evidence[1960][0]['checks']['bytes'] is True


def test_a_still_partial_response_cannot_confer_gdp_authority(tmp_path):
    with _client(tmp_path, always_partial=True) as client:
        with pytest.raises(ValueError, match='partial or missing completeness'):
            fetcher._fetch_wb_gdp(client)


def test_partial_gdp_refresh_is_not_reported_as_fully_live(tmp_path, monkeypatch):
    base = dict(metadata={}, timeline=[dict(year=2025, total=1000, gdp=2000, gdp_ratio=50)])
    monkeypatch.setattr(fetcher, 'load_json_resource', lambda **kwargs: copy.deepcopy(base))
    monkeypatch.setattr(fetcher, '_overlay_cbk_public_debt', lambda payload, *_: (payload, 1))
    reset('debt_timeline')
    try:
        with _client(tmp_path, always_partial=True) as client:
            fetcher.fetch_debt_timeline_payload(client, client._settings)
        outcome = get('debt_timeline')
        assert outcome['mode'] == 'partial'
        assert outcome['reason'] == 'gdp_refresh_unavailable'
    finally:
        reset('debt_timeline')


@pytest.mark.parametrize('field', ['page', 'pages', 'total'])
def test_boolean_completeness_metadata_is_not_a_complete_response(tmp_path, field):
    with _client(tmp_path, years=(2025,), metadata={field: True}) as client:
        with pytest.raises(ValueError, match='completeness'):
            fetcher._fetch_wb_gdp(client)


@pytest.mark.parametrize('value', [0, -0.0, 0.4])
def test_zero_gdp_does_not_claim_freshness_or_keep_a_stale_ratio(tmp_path, monkeypatch, value):
    base = dict(metadata={}, timeline=[dict(year=2025, total=1000, gdp=2000, gdp_ratio=50)])
    monkeypatch.setattr(fetcher, 'load_json_resource', lambda **kwargs: copy.deepcopy(base))
    monkeypatch.setattr(fetcher, '_overlay_cbk_public_debt', lambda payload, *_: (payload, 1))
    reset('debt_timeline')
    try:
        with _client(tmp_path, values={2025: value}) as client:
            payload = fetcher.fetch_debt_timeline_payload(client, client._settings)
        assert payload['timeline'][0]['gdp'] == 2000
        assert payload['timeline'][0]['gdp_ratio'] is None
        assert get('debt_timeline')['mode'] == 'partial'
    finally:
        reset('debt_timeline')


def test_incomplete_debt_stock_coverage_cannot_be_hidden_by_complete_gdp(tmp_path, monkeypatch):
    base = dict(metadata={}, timeline=[dict(year=y, total=1000) for y in (2024, 2025)])
    monkeypatch.setattr(fetcher, 'load_json_resource', lambda **kwargs: copy.deepcopy(base))
    monkeypatch.setattr(fetcher, '_overlay_cbk_public_debt', lambda payload, *_: (payload, 1))
    reset('debt_timeline')
    try:
        with _client(tmp_path) as client:
            fetcher.fetch_debt_timeline_payload(client, client._settings)
        assert get('debt_timeline')['reason'] == 'debt_stock_refresh_incomplete'
    finally:
        reset('debt_timeline')


def test_boolean_base_year_is_not_an_observation_year(tmp_path, monkeypatch):
    base = dict(metadata={}, timeline=[dict(year=True, total=1000)])
    monkeypatch.setattr(fetcher, 'load_json_resource', lambda **kwargs: copy.deepcopy(base))
    with _client(tmp_path) as client:
        with pytest.raises(ValueError, match='calendar years'):
            fetcher.fetch_debt_timeline_payload(client, client._settings)


def test_disabled_gdp_does_not_keep_an_old_ratio_after_stock_refresh(tmp_path, monkeypatch):
    base = dict(metadata={}, timeline=[dict(year=2025, total=1000, gdp=2000, gdp_ratio=50)])
    monkeypatch.setattr(fetcher, 'load_json_resource', lambda **kwargs: copy.deepcopy(base))
    def stock(payload, *_):
        payload['timeline'][0]['total'] = 1200
        return payload, 1
    monkeypatch.setattr(fetcher, '_overlay_cbk_public_debt', stock)
    with _client(tmp_path) as client:
        settings = client._settings.model_copy(update={'enrich_with_worldbank': False})
        payload = fetcher.fetch_debt_timeline_payload(client, settings)
    assert payload['timeline'][0]['gdp'] == 2000
    assert payload['timeline'][0]['gdp_ratio'] is None
