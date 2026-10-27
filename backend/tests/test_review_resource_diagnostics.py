"""Review regressions: bounded failures stay visible without leaking values."""
import asyncio
import logging

import pytest
from fastapi import HTTPException

import main
from services.endpoint_resources import capacity_unavailable


def test_peer_unexpected_error_is_sanitized_and_reported(monkeypatch, caplog):
    async def failed(**kwargs):
        raise RuntimeError('inert-provider-secret')

    monkeypatch.setattr(main, '_read_regional_peers', failed)
    with caplog.at_level(logging.ERROR), pytest.raises(HTTPException) as raised:
        asyncio.run(main.get_debt_sustainability(({'status': 'success'}, {})))
    assert raised.value.status_code == 500
    assert raised.value.detail == 'Internal server error'
    assert 'peer' in caplog.text.lower()
    assert 'inert-provider-secret' not in caplog.text
    assert main.get_debt_sustainability.__doc__


def test_busy_peer_is_explicit_retryable_admission_not_successful_absence(monkeypatch):
    async def busy(**kwargs):
        raise capacity_unavailable('Peer observation read is still running; retry shortly')

    monkeypatch.setattr(main, '_read_regional_peers', busy)
    with pytest.raises(HTTPException) as raised:
        asyncio.run(main.get_debt_sustainability(({'debt_to_gdp': 65.0}, {})))
    assert raised.value.status_code == 503
    assert raised.value.headers == {'Retry-After': '1', 'Cache-Control': 'no-store'}


def test_health_error_has_safe_operator_diagnostic(monkeypatch, caplog):
    from routers import health

    class FailedDB:
        def execute(self, statement):
            raise RuntimeError('inert-private-host SQL=inert-secret-query')

    monkeypatch.setattr(health.cache, 'health_check', lambda: {'status': 'healthy'})
    with caplog.at_level(logging.ERROR):
        body = asyncio.run(health.detailed_health_check(db=FailedDB()))
    assert body['components']['database']['error'] == 'Database connectivity check failed'
    assert 'database' in caplog.text.lower() and 'RuntimeError' in caplog.text
    assert 'inert-private-host' not in caplog.text + str(body)
    assert 'inert-secret-query' not in caplog.text + str(body)


def test_register_size_uses_accelerated_ascii_encoder_and_preserves_boundary(monkeypatch):
    modes = []
    original = main.json.JSONEncoder.iterencode

    def record(self, value, _one_shot=False):
        modes.append(_one_shot)
        return original(self, value, _one_shot=_one_shot)

    monkeypatch.setattr(main.json.JSONEncoder, 'iterencode', record)
    value = {'label': '\u00e9', 'rows': [1, 2, 3]}
    size = len(main.json.dumps(value, ensure_ascii=True))
    modes.clear()
    monkeypatch.setattr(main, 'MAX_PUBLIC_REGISTER_BYTES', size)
    assert main._complete_register_response(value) is value
    assert modes == [True], 'public register size check used the Python chunk encoder'
    monkeypatch.setattr(main, 'MAX_PUBLIC_REGISTER_BYTES', size - 1)
    with pytest.raises(HTTPException) as raised:
        main._complete_register_response(value)
    assert raised.value.status_code == 503
