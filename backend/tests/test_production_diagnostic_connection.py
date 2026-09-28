"""The diagnostic command must reject an unencrypted remote target before connecting."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _module():
    path = ROOT / "scripts" / "production_diagnostic.py"
    spec = importlib.util.spec_from_file_location("production_diagnostic_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://reader@db.example/prod",
        "postgresql://reader@db.example/prod?sslmode=disable",
        "postgresql://reader@db.example/prod?sslmode=prefer",
        "postgresql://reader@127.0.0.1/prod?hostaddr=203.0.113.10&sslmode=disable",
    ],
)
def test_unsafe_diagnostic_target_is_rejected_before_connect(monkeypatch, url):
    connect = Mock(side_effect=AssertionError("attempted a connection"))
    monkeypatch.setitem(sys.modules, "psycopg2", SimpleNamespace(connect=connect))
    monkeypatch.setenv("PRODUCTION_DIAGNOSTIC_DATABASE_URL", url)
    with pytest.raises(ValueError):
        _module().main()
    connect.assert_not_called()


class _FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, statement):
        pass

    def fetchone(self):
        return ("on",)

    def fetchall(self):
        return []


class _FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def set_session(self, readonly):
        assert readonly is True

    def cursor(self):
        return _FakeCursor()


@pytest.mark.parametrize(
    "url,expected_mode",
    [
        ("postgresql://reader@db.example/prod?sslmode=require", "require"),
        ("postgresql://reader@db.example/prod?sslmode=verify-full", "verify-full"),
        ("postgresql://reader@127.0.0.1/local?sslmode=disable", None),
    ],
)
def test_diagnostic_enforces_tls_for_remote_but_allows_local_container(
    monkeypatch, url, expected_mode
):
    connect = Mock(return_value=_FakeConnection())
    monkeypatch.setitem(sys.modules, "psycopg2", SimpleNamespace(connect=connect))
    monkeypatch.setenv("PRODUCTION_DIAGNOSTIC_DATABASE_URL", url)
    _module().main()
    kwargs = connect.call_args.kwargs
    assert kwargs.get("sslmode") == expected_mode
    if expected_mode is None:
        assert kwargs["hostaddr"] == "127.0.0.1"
