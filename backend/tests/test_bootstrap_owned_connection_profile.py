"""Owned fixture transport accepts bounded timing without losing its pins."""
from math import inf, nan
import os

import pytest

from batch9_bootstrap_fixture import owned_database as owned

URL = "postgresql+psycopg2://batch9_bootstrap:batch9-inert-local@127.0.0.1:55492/batch9-bootstrap-fixture"


@pytest.fixture(autouse=True)
def isolated_libpq_environment(monkeypatch):
    # Reach the intended argument boundary regardless of the developer's PG* env.
    # monkeypatch restores every original value after each test.
    for name in tuple(os.environ):
        if name.startswith("PG"):
            monkeypatch.delenv(name)


@pytest.mark.parametrize("supplied", [None, {}, {
    "connect_timeout": 3, "keepalives": 1, "keepalives_idle": 5,
    "keepalives_interval": 1, "keepalives_count": 2, "tcp_user_timeout": 5000,
}, {
    "connect_timeout": 8, "keepalives": 0, "keepalives_idle": 60,
    "keepalives_interval": 60, "keepalives_count": 10, "tcp_user_timeout": 60000,
}], ids=["omitted", "empty", "actual-request-profile", "bounded-edges"])
def test_owned_engine_preserves_caller_timing_and_authoritative_transport(monkeypatch, supplied):
    calls = []
    monkeypatch.setattr(owned, "create_engine", lambda url, **kwargs: calls.append((url, kwargs)) or "engine")
    args = {} if supplied is None else {"connect_args": supplied}
    assert owned.owned_engine(URL, pool_size=2, **args) == "engine"
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url.render_as_string(hide_password=False) == URL
    assert kwargs["pool_size"] == 2
    transport = kwargs["connect_args"]
    assert {key: transport[key] for key in ("host", "hostaddr", "port", "dbname", "user", "password", "sslmode", "gssencmode")} == {
        "host": "127.0.0.1", "hostaddr": "127.0.0.1", "port": 55492,
        "dbname": "batch9-bootstrap-fixture", "user": "batch9_bootstrap",
        "password": "batch9-inert-local", "sslmode": "disable", "gssencmode": "disable",
    }
    assert transport["connect_timeout"] == (supplied or {}).get("connect_timeout", 8)
    assert all(transport[key] == value for key, value in (supplied or {}).items())


@pytest.mark.parametrize("supplied", [
    {"connect_timeout": True}, {"connect_timeout": False},
    {"connect_timeout": "3"}, {"connect_timeout": 3.0},
    {"connect_timeout": nan}, {"connect_timeout": inf},
    {"connect_timeout": 0}, {"connect_timeout": -1}, {"connect_timeout": 9},
    {"keepalives": 2}, {"keepalives_idle": 61}, {"keepalives_interval": 0},
    {"keepalives_count": 11}, {"tcp_user_timeout": 60001},
    None, [],
] + [{key: "unowned"} for key in (
    "host", "hostaddr", "port", "dbname", "user", "password", "sslmode",
    "gssencmode", "options", "service", "passfile", "sslrootcert", "unknown",
)], ids=[
    "bool-true", "bool-false", "string", "integral-float", "nan", "infinity",
    "zero-timeout", "negative-timeout", "relaxed-timeout", "invalid-keepalive",
    "relaxed-idle", "zero-interval", "relaxed-count", "relaxed-tcp-timeout",
    "null-container", "list-container",
] + ["reject-" + key for key in (
    "host", "hostaddr", "port", "dbname", "user", "password", "sslmode",
    "gssencmode", "options", "service", "passfile", "sslrootcert", "unknown",
)])
def test_owned_engine_refuses_invalid_or_redirecting_arguments_before_engine(monkeypatch, supplied):
    calls = []
    monkeypatch.setattr(owned, "create_engine", lambda *args, **kwargs: calls.append((args, kwargs)))
    with pytest.raises(ValueError, match="bounded owned connection timing"):
        owned.owned_engine(URL, connect_args=supplied)
    assert calls == []


def test_owned_engine_keeps_only_url_authorized_schema(monkeypatch):
    calls = []
    monkeypatch.setattr(owned, "create_engine", lambda url, **kwargs: calls.append((url, kwargs)))
    schema = "bootstrap_" + "a" * 32
    scoped = owned.schema_url(URL, schema)
    owned.owned_engine(scoped, allow_schema=True, connect_args={"connect_timeout": 3})
    assert len(calls) == 1
    assert dict(calls[0][0].query) == {"options": "-csearch_path=" + schema}
    assert "options" not in calls[0][1]["connect_args"]


def test_owned_engine_refuses_ambient_libpq_redirect_before_engine(monkeypatch):
    calls = []
    monkeypatch.setattr(owned, "create_engine", lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setenv("PGHOST", "unowned-fixture.invalid")
    with pytest.raises(ValueError, match="owned bootstrap database"):
        owned.owned_engine(URL, connect_args={"connect_timeout": 3})
    assert calls == []
