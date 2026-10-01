"""Execute the CLI and actual SQLAlchemy/DBAPI construction without remote I/O."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import psycopg2
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/verification/oag_boundary_correction.py"


@pytest.fixture
def tool():
    spec = importlib.util.spec_from_file_location("oag_boundary_connection_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def arguments(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--pdf", "unused.pdf",
                                      "--manifest", "unused.json", "--output", str(tmp_path / "out.json")])


@pytest.mark.parametrize("scheme", ["postgresql", "postgresql+psycopg2", "postgres"])
@pytest.mark.parametrize("mode", ["require", "verify-ca", "verify-full"])
def test_remote_cli_pins_documented_tls_at_actual_dbapi_boundary(
    tool, monkeypatch, tmp_path, capsys, scheme, mode
):
    arguments(monkeypatch, tmp_path)
    monkeypatch.setenv("OAG_BOUNDARY_DATABASE_URL", f"{scheme}://reader:synthetic@db.example:5432/review?sslmode={mode}")
    monkeypatch.setenv("PGSSLMODE", "disable")
    monkeypatch.setenv("PGGSSENCMODE", "require")
    calls = []

    class StopBeforeNetwork(Exception):
        pass

    def connect(*args, **kwargs):
        calls.append((args, kwargs))
        raise StopBeforeNetwork

    def run(engine, pdf, manifest, **kwargs):
        # Real Engine.connect invokes the actual driver's connect boundary.
        # Stop there instead of opening a remote connection or DB transaction.
        assert engine.dialect.driver == "psycopg2"
        with pytest.raises(StopBeforeNetwork):
            engine.connect()
        assert kwargs["commit"] is False
        assert kwargs["recover"] is False
        return {"outcome": "read_only_dry_run", "plan_sha256": "synthetic-plan"}

    monkeypatch.setattr(psycopg2, "connect", connect)
    monkeypatch.setattr(tool, "run", run)
    tool.main()
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert not args
    assert kwargs["host"] == "db.example"
    assert kwargs["dbname"] == "review"
    assert kwargs["sslmode"] == mode
    assert kwargs["connect_timeout"] == 8
    assert kwargs["gssencmode"] == "disable"
    assert "synthetic" not in capsys.readouterr().out.replace("synthetic-plan", "")


@pytest.mark.parametrize("host,expected_address", [
    ("127.0.0.1", "127.0.0.1"), ("localhost", "127.0.0.1"), ("[::1]", "::1"),
])
def test_loopback_cli_pins_local_address_even_with_libpq_redirect_env(
    tool, monkeypatch, tmp_path, host, expected_address
):
    arguments(monkeypatch, tmp_path)
    monkeypatch.setenv("OAG_BOUNDARY_DATABASE_URL", f"postgresql://reader@{host}:55431/local")
    monkeypatch.setenv("PGHOSTADDR", "203.0.113.10")
    monkeypatch.setenv("PGSSLMODE", "verify-full")
    monkeypatch.setenv("PGGSSENCMODE", "require")
    calls = []

    class StopBeforeNetwork(Exception):
        pass

    def connect(*args, **kwargs):
        calls.append(kwargs)
        raise StopBeforeNetwork

    def run(engine, *args, **kwargs):
        with pytest.raises(StopBeforeNetwork):
            engine.connect()
        return {"outcome": "read_only_dry_run", "plan_sha256": "local-control"}

    monkeypatch.setattr(psycopg2, "connect", connect)
    monkeypatch.setattr(tool, "run", run)
    tool.main()
    assert calls[0]["hostaddr"] == expected_address
    assert calls[0]["sslmode"] == "disable"
    assert calls[0]["connect_timeout"] == 8
    assert calls[0]["gssencmode"] == "disable"


@pytest.mark.parametrize("url", [
    "postgresql://reader:synthetic@db.example/review",
    *[f"postgresql://reader:synthetic@db.example/review?sslmode={mode}"
      for mode in ("", "disable", "allow", "prefer", "Require", "unknown")],
    "postgresql://reader:synthetic@db.example/review?sslmode=require&sslmode=verify-full",
    "postgresql://reader:synthetic@db.example/review?sslmode=require&sslmode=require",
    "postgresql://reader:synthetic@db.example/review?sslmode=require&hostaddr=127.0.0.1",
    "postgresql://reader:synthetic@127.0.0.1/review?hostaddr=203.0.113.10",
    "postgresql://reader:synthetic@db.example/review?sslmode=require&host=localhost",
    "postgresql://reader:synthetic@db.example/review?sslmode=require&service=other",
    "postgresql://reader:synthetic@db.example/review?sslmode=require&options=-csearch_path%3Devil",
    "postgresql://reader:synthetic@db.example/review?sslmode=require&connect_timeout=0",
    "postgresql://reader:synthetic@db.example/review?sslmode=require&sslrootcert=/unexpected",
    "postgresql://reader:synthetic@db.example/review?sslmode=require&arbitrary=",
    "postgresql://reader:synthetic@db.example/review?sslmode=require&arbitrary",
    "postgresql://reader:synthetic@127.0.0.1/review?sslmode=disable",
    "postgresql+asyncpg://reader:synthetic@db.example/review?sslmode=require",
    "postgresql+psycopg://reader:synthetic@db.example/review?sslmode=require",
    "sqlite:////tmp/unexpected.db",
    "postgresql:///review?sslmode=require",
    "postgresql://reader:synthetic@db.example/?sslmode=require",
    "postgresql://reader:synthetic@db.example/review?sslmode=require#fragment",
    "postgresql://reader:synthetic@[broken/review?sslmode=require",
])
def test_unsafe_cli_connections_refuse_before_engine_creation(
    tool, monkeypatch, tmp_path, url
):
    arguments(monkeypatch, tmp_path)
    monkeypatch.setenv("OAG_BOUNDARY_DATABASE_URL", url)
    create = Mock(side_effect=AssertionError("engine construction must not occur"))
    run = Mock(side_effect=AssertionError("correction must not run"))
    monkeypatch.setattr(tool, "create_engine", create)
    monkeypatch.setattr(tool, "run", run)
    with pytest.raises(ValueError) as error:
        tool.main()
    assert url not in str(error.value)
    assert "synthetic" not in str(error.value)
    create.assert_not_called()
    run.assert_not_called()
    assert not (tmp_path / "out.json").exists()


def test_dedicated_url_required_without_dotenv_or_database_url_fallback(tool, monkeypatch, tmp_path):
    arguments(monkeypatch, tmp_path)
    monkeypatch.delenv("OAG_BOUNDARY_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://reader:synthetic@localhost/other")
    create = Mock()
    monkeypatch.setattr(tool, "create_engine", create)
    with pytest.raises((KeyError, ValueError)):
        tool.main()
    create.assert_not_called()


def test_cli_error_boundary_never_prints_driver_url(tool, monkeypatch, capsys):
    monkeypatch.setattr(tool, "main", Mock(side_effect=RuntimeError(
        "postgresql://reader:synthetic-secret@db.example/review?sslmode=require")))
    with pytest.raises(SystemExit) as exit_status:
        tool.cli()
    assert exit_status.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "OAG boundary correction failed: RuntimeError\n"


def test_actual_cli_subprocess_refuses_weak_remote_tls_without_printing_url(tmp_path):
    raw = "postgresql://reader:synthetic-secret@db.example/review?sslmode=prefer"
    env = {**os.environ, "PYTHON_DOTENV_DISABLED": "1", "OAG_BOUNDARY_DATABASE_URL": raw}
    result = subprocess.run([sys.executable, str(SCRIPT), "--pdf", "unused.pdf", "--manifest",
                             "unused.json", "--output", str(tmp_path / "out.json")],
                            env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "OAG boundary correction failed: ValueError\n"
    assert raw not in result.stderr
    assert "synthetic-secret" not in result.stderr
    assert not (tmp_path / "out.json").exists()
