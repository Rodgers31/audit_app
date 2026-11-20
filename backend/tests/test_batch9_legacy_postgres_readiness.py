from unittest.mock import Mock, call

import psycopg2
import pytest

from tests.batch9_legacy_fixture import batch9_legacy_target as fixture


def test_readiness_retries_the_authenticated_host_connection(monkeypatch):
    connection = Mock()
    connect = Mock(side_effect=[psycopg2.OperationalError("connection refused"), connection])
    monkeypatch.setattr(psycopg2, "connect", connect)
    clock = Mock()
    clock.monotonic.return_value = 0
    monkeypatch.setattr(fixture, "time", clock)

    fixture._wait_for_authenticated_postgres()

    assert connect.call_args_list == [call(**fixture.connect_args(), connect_timeout=2)] * 2
    clock.sleep.assert_called_once_with(.2)
    connection.close.assert_called_once_with()


def test_readiness_stops_when_the_owned_tcp_endpoint_does_not_accept(monkeypatch):
    connect = Mock(side_effect=psycopg2.OperationalError("connection refused"))
    monkeypatch.setattr(psycopg2, "connect", connect)
    clock = Mock()
    clock.monotonic.side_effect = [0, 0, 41]
    monkeypatch.setattr(fixture, "time", clock)

    with pytest.raises(RuntimeError, match="authenticated TCP readiness timed out"):
        fixture._wait_for_authenticated_postgres()

    connect.assert_called_once_with(**fixture.connect_args(), connect_timeout=2)
