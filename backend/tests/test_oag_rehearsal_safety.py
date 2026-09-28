"""The local replay must reject a production destination before engine creation."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture()
def rehearsal(monkeypatch):
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts/verification/oag_county_rehearsal.py"
    )
    spec = spec_from_file_location("oag_rehearsal_under_test", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    module.create_engine = Mock(return_value=object())
    return module


@pytest.mark.parametrize(
    "driver,host",
    [
        ("postgresql", "127.0.0.1"),
        ("postgresql+psycopg2", "localhost"),
        ("postgresql", "[::1]"),
    ],
)
def test_known_local_clone_is_accepted_without_connecting(
    rehearsal, monkeypatch, driver, host
):
    raw = f"{driver}://u@{host}/codex_oag_probe"
    monkeypatch.setenv("OAG_REHEARSAL_DATABASE_URL", raw)
    assert rehearsal.local_engine() is rehearsal.create_engine.return_value
    rehearsal.create_engine.assert_called_once_with(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "postgresql://u@production.example/codex_oag_probe",
        "postgresql://u@127.0.0.1/audit_prod",
        "postgresql://u@127.0.0.1/codex_oag_probe?host=production.example",
        "postgresql://u@localhost/codex_oag_probe?hostaddr=203.0.113.10",
        "postgresql://u@localhost/codex_oag_probe?dbname=audit_prod",
        "postgresql://u@localhost/codex_oag_probe?service=production",
        "postgresql://u@localhost/codex_oag_probe?host=127.0.0.1&host=production.example",
        "mysql://u@localhost/codex_oag_probe",
        "postgresql+asyncpg://u@localhost/codex_oag_probe",
        "postgresql://u@localhost/",
    ],
)
def test_unsafe_target_is_refused_before_engine_creation(rehearsal, monkeypatch, raw):
    monkeypatch.setenv("OAG_REHEARSAL_DATABASE_URL", raw)
    with pytest.raises(ValueError):
        rehearsal.local_engine()
    rehearsal.create_engine.assert_not_called()


def test_missing_destination_is_refused_before_engine_creation(rehearsal, monkeypatch):
    monkeypatch.delenv("OAG_REHEARSAL_DATABASE_URL", raising=False)
    with pytest.raises((ValueError, KeyError)):
        rehearsal.local_engine()
    rehearsal.create_engine.assert_not_called()
