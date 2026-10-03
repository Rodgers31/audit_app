"""Unit checks for explicit, bounded and safe worker construction."""
import json
import logging
from uuid import uuid4

import pytest

from social.worker.config import WorkerConfig, create_worker_engine
from social.worker.logging import event


def test_config_requires_explicit_postgres_and_bounds():
    for url in ("", "sqlite://", "mysql://localhost/test"):
        with pytest.raises(ValueError):
            WorkerConfig(url)
    for setting in ({"external_slots": 3}, {"max_submissions": 6},
                    {"retry_lifetime_seconds": 86401}, {"renewal_seconds": 120}):
        with pytest.raises(ValueError):
            WorkerConfig("postgresql://localhost/social_test", **setting)


def test_engine_has_two_connections_and_zero_overflow():
    engine = create_worker_engine(WorkerConfig("postgresql://localhost/social_test"))
    try:
        assert engine.pool.size() == 2
        assert engine.pool._max_overflow == 0
        assert engine.hide_parameters
    finally:
        engine.dispose()


def test_structured_log_excludes_sensitive_unapproved_fields(caplog):
    logger = logging.getLogger("social.worker.test")
    with caplog.at_level(logging.INFO):
        event(logger, "operation_finished", target_id=uuid4(), outcome="published",
              duration_ms=12, text="SECRET_COPY", credential="SECRET_TOKEN",
              remote_url="https://signed.invalid/?secret=PRIVATE", database_url="SECRET_DSN")
    result = json.loads(caplog.records[-1].message)
    assert result["outcome"] == "published"
    assert result["duration_ms"] == 12
    assert set(result) == {"event", "target_id", "outcome", "duration_ms"}
    assert "SECRET" not in caplog.text and "signed.invalid" not in caplog.text


@pytest.mark.parametrize("setting", [
    {"external_slots": True}, {"max_submissions": True}, {"maintenance_batch_size": True},
    {"lease_seconds": True}, {"active_scan_seconds": 0}, {"idle_scan_seconds": float("nan")},
    {"idle_heartbeat_seconds": float("inf")}, {"renewal_seconds": True},
])
def test_direct_config_guards_reject_hostile_numeric_values(setting):
    with pytest.raises(ValueError):
        WorkerConfig("postgresql://localhost/social_test", **setting)


def test_cli_requires_explicit_database_and_never_uses_database_url_environment(monkeypatch,capsys):
    from social.worker.__main__ import main
    monkeypatch.setenv("DATABASE_URL","postgresql://secret-production.invalid/forbidden")
    with pytest.raises(SystemExit) as stopped:
        main([])
    assert stopped.value.code == 2
    output = capsys.readouterr()
    assert "--database-url" in output.err and "secret-production" not in output.err
