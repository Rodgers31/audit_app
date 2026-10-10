"""#589: persistent state and actual web startup must agree on readiness."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name("batch10_readiness_fixture")


@pytest.fixture(scope="module")
def readiness_postgres():
    from batch10_readiness_fixture.postgres import postgres

    with postgres() as url:
        yield url


def probe(tmp_path, mode, url=None):
    env = dict(
        PATH=os.environ["PATH"],
        PYTHONPATH=f'{FIXTURE}:{ROOT / "backend"}',
        DATABASE_URL=url or f'sqlite:///{tmp_path / "batch10-readiness-probe.sqlite"}',
        PYTHON_DOTENV_DISABLED="1",
        PYTHONDONTWRITEBYTECODE="1",
        BATCH10_READINESS_INERT="1",
        JWT_SECRET_KEY="batch10-readiness-inert-key",
        AUTO_SEEDER_ENABLED="false",
        AUTO_WARMUP_ENABLED="false",
        ENABLE_ETL_SCHEDULER="false",
        SEED_STORAGE_PATH=str(tmp_path / "owned-cache"),
    )
    command = [sys.executable, str(FIXTURE / "probe.py"), mode]
    child = subprocess.Popen(
        command,
        cwd=ROOT / "backend",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        log, _ = child.communicate(timeout=50)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        log, _ = child.communicate(timeout=10)
        pytest.fail("SETUP/TIMEOUT: " + log)
    finally:
        if url is None:
            database = tmp_path / "batch10-readiness-probe.sqlite"
            for suffix in ("", "-journal", "-wal", "-shm"):
                database.with_name(database.name + suffix).unlink(missing_ok=True)
    print("COMMAND", command, "\n" + log)
    assert child.returncode == 0, "SETUP/PROCESS failure: " + log
    results = [
        json.loads(line.removeprefix("READINESS_RESULT "))
        for line in log.splitlines()
        if line.startswith("READINESS_RESULT ")
    ]
    assert len(results) == 1, "Missing actual readiness observation"
    return results[0]


@pytest.mark.parametrize(
    "mode",
    [
        "empty",
        "valid",
        "partial",
        "arbitrary",
        "duplicate",
        "wrong_country",
        "blank_slug",
        "count_decoy",
    ],
)
def test_nonbudget_writer_readiness_and_next_normal_start(
    tmp_path, readiness_postgres, mode
):
    from sqlalchemy.engine import make_url

    schema = "batch10_readiness_" + uuid4().hex
    admin = create_engine(readiness_postgres)
    with admin.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = make_url(readiness_postgres).update_query_dict(
        {"options": "-csearch_path=" + schema}
    )
    url = scoped.render_as_string(hide_password=False)
    try:
        result = probe(tmp_path, mode, url)
        expected = 200 if mode == "valid" else 503
        assert (
            result["first"]["code"] == expected
        ), "FALSE_READY: required canonical references are unavailable"
        if expected == 503:
            assert (
                result["first"]["body"]["reason"]
                == "required_county_references_unavailable"
            )
            assert "next_normal_start" in result["first"]["body"]["retry"]
            assert len(json.dumps(result["first"]["body"])) < 256
        assert (
            result["during"] == result["before"]
        ), "Bootstrap mutated state while non-budget writer was active"
        assert result["live"]["code"] == 200
        assert result["finished"]["jobs"][0][2] == "COMPLETED"
        assert all(
            row[8] != "None" for row in result["finished"]["claims"]
        )  # released_at
        if mode in {"empty", "partial", "valid", "count_decoy"}:
            assert result["second"]["code"] == 200
            assert result["after"]["counties"] == (48 if mode == "count_decoy" else 47)
        # Independent observer uses a new connection after child process exit.
        observer = create_engine(scoped)
        try:
            with observer.connect() as db:
                assert (
                    db.scalar(text("SELECT count(*) FROM entities WHERE type='COUNTY'"))
                    == result["after"]["counties"]
                )
                assert (
                    db.scalar(
                        text(
                            "SELECT count(*) FROM ingestion_jobs WHERE domain='audits' AND status='COMPLETED'"
                        )
                    )
                    == 1
                )
        finally:
            observer.dispose()
    finally:
        with admin.begin() as db:
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.mark.parametrize(
    "mode",
    [
        "exception",
        "db_failure",
        "unavailable",
        "no_data",
        "cancel",
        "check_failure",
        "cancel_check",
        "malformed_fixture",
    ],
)
def test_repeated_real_lifespans_cannot_reuse_previous_ready(tmp_path, mode):
    result = probe(tmp_path, "life_" + mode)
    assert result["first"]["code"] == 200
    assert (
        result["second"]["code"] == 503
    ), "STALE_READY: a failed/cancelled new lifespan inherited readiness"
    assert result["shutdown"]["code"] == 503
    if mode != "unavailable":
        assert result["immediate"]["code"] == 503
        assert result["live"]["code"] == 200
        assert result["final"]["code"] == 503
    assert "must-not-leak" not in json.dumps(result["second"])


def test_liveness_serves_while_actual_pool_prewarm_query_is_blocked(tmp_path):
    result = probe(tmp_path, "prewarm")
    assert not result[
        "failures"
    ], "LIVENESS_BLOCKED_BY_PREWARM: stalled database blocked the HTTP event loop"
    assert result["live"]["code"] == 200
    assert result["ready"]["code"] == 200
    assert result["shutdown"]["code"] == 503
