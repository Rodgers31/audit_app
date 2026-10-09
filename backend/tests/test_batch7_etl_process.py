"""Actual dedicated processes + actual CLI with one inert registered handler."""
from pathlib import Path
import os
import signal
import subprocess
import sys
import time

import pytest
from sqlalchemy import text

from test_batch7_etl_postgres import pg, post, expire, AUTH, URL
from admin_etl_dispatch_worker import register_worker, claim, finish
from models import EtlDispatchDomain

pytestmark = pytest.mark.skipif(not URL, reason="Owned PostgreSQL required")
ROOT = Path(__file__).resolve().parents[1]


def wait_for(read, predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = read()
        if predicate(value):
            return value
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for isolated process observation")


def child_env(tmp_path):
    return {"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHON_DOTENV_DISABLED": "1", "PYTHONPATH": str(ROOT / "tests/batch7_etl_worker_fixture") + os.pathsep + str(ROOT),
        "DATABASE_URL": URL, "ADMIN_ETL_DISPATCH_ENABLED": "true", "BATCH7_ETL_INERT_PROCESS": "true",
        "SEED_STORAGE_PATH": str(tmp_path / "storage"), "SEED_CACHE_PATH": str(tmp_path / "cache")}


@pytest.fixture
def process_pg(pg):
    client, factory, engine = pg
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS batch7_control(mode text NOT NULL)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS batch7_effects(job_id integer)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS batch7_markers(stage text, job_id integer)"))
        conn.execute(text("TRUNCATE batch7_control,batch7_effects,batch7_markers"))
        conn.execute(text("INSERT INTO batch7_control VALUES ('normal')"))
    yield pg


def start_worker(env):
    return subprocess.Popen([sys.executable, "-m", "admin_etl_dispatch_worker"], env=env, cwd=ROOT,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def stop_worker(worker):
    if worker.poll() is None:
        os.killpg(worker.pid, signal.SIGCONT)
        os.killpg(worker.pid, signal.SIGINT)
        try:
            worker.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(worker.pid, signal.SIGKILL)
            worker.wait(timeout=3)


def capability(client):
    return client.get("/api/v1/admin/etl/dispatch", headers=AUTH).json()


def receipt(client, identity):
    return client.get("/api/v1/admin/etl/commands/" + identity, headers=AUTH).json()


def test_real_worker_and_native_cli_real_dry_run_failure_and_heartbeat(process_pg, tmp_path):
    client, factory, engine = process_pg
    worker = start_worker(child_env(tmp_path))
    try:
        ready = wait_for(lambda: capability(client), lambda c: c.get("available") is True)
        first_seen = ready["worker"]["last_seen_at"]
        ids = []
        for dry_run in (False, True):
            result = post(client, ready["generation"], dry_run=dry_run)
            assert result.status_code == 202, result.text
            identity = result.json()["command"]["id"]
            ids.append(identity)
            final = wait_for(lambda: receipt(client, identity), lambda c: c.get("status") not in ("queued", "running"))
            assert final["status"] == "completed" and final["job_id"] > 0 and final["version"] == 3
            with engine.connect() as conn:
                assert conn.scalar(text("SELECT count(*) FROM batch7_effects")) == 1
                observation = conn.execute(text("SELECT status,dry_run,metadata->>'dispatch_command_id',items_created FROM ingestion_jobs WHERE id=:id"), {"id": final["job_id"]}).one()
                assert tuple(observation) == ("COMPLETED", dry_run, identity, 1)
        with engine.begin() as conn:
            conn.execute(text("UPDATE batch7_control SET mode='failure'"))
        identity = post(client, ready["generation"]).json()["command"]["id"]
        failed = wait_for(lambda: receipt(client, identity), lambda c: c.get("status") not in ("queued", "running"))
        assert failed["status"] == failed["outcome"] == "failed" and failed["job_id"] > 0
        assert "Inert domain failure" not in str(failed)
        refreshed = wait_for(lambda: capability(client), lambda c: c["worker"]["last_seen_at"] != first_seen, timeout=8)
        assert refreshed["available"] is True
        competitor = start_worker(child_env(tmp_path))
        assert competitor.wait(timeout=10) == 1
    finally:
        stop_worker(worker)


@pytest.mark.parametrize("mode,expected_effects", [("before", 0), ("after", 1)])
def test_worker_death_before_after_effects_retains_block_and_never_replays(process_pg, tmp_path, mode, expected_effects):
    client, factory, engine = process_pg
    with engine.begin() as conn:
        conn.execute(text("UPDATE batch7_control SET mode=:mode"), {"mode": mode})
    worker = start_worker(child_env(tmp_path))
    restarted = None
    try:
        ready = wait_for(lambda: capability(client), lambda c: c.get("available") is True)
        identity = post(client, ready["generation"]).json()["command"]["id"]
        stage = "entered" if mode == "before" else "committed"
        def observed():
            with engine.connect() as conn:
                return conn.scalar(text("SELECT count(*) FROM batch7_markers WHERE stage=:stage"), {"stage": stage})
        wait_for(observed, lambda count: count == 1)
        os.killpg(worker.pid, signal.SIGKILL)
        worker.wait(timeout=3)
        expire(factory)
        restarted = start_worker(child_env(tmp_path))
        new_ready = wait_for(lambda: capability(client), lambda c: c.get("available") and c["generation"] != ready["generation"])
        final = receipt(client, identity)
        assert final["status"] == "interrupted" and final["outcome"] == "execution_unverified"
        queued = post(client, new_ready["generation"]).json()["command"]["id"]
        time.sleep(0.7)
        assert receipt(client, queued)["status"] == "queued"
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM batch7_effects")) == expected_effects
            assert conn.scalar(text("SELECT count(*) FROM batch7_markers WHERE stage='entered'")) == 1
        with factory() as db:
            assert str(db.get(EtlDispatchDomain, "audits").command_id) == identity
    finally:
        stop_worker(worker)
        if restarted is not None:
            stop_worker(restarted)


def test_expiry_does_not_stop_old_process_or_allow_conflicting_execution(process_pg, tmp_path):
    client, factory, engine = process_pg
    with engine.begin() as conn:
        conn.execute(text("UPDATE batch7_control SET mode='before'"))
    worker = start_worker(child_env(tmp_path))
    restarted = None
    try:
        ready = wait_for(lambda: capability(client), lambda c: c.get("available") is True)
        identity = post(client, ready["generation"]).json()["command"]["id"]
        def entered():
            with engine.connect() as conn:
                return conn.scalar(text("SELECT count(*) FROM batch7_markers"))
        wait_for(entered, lambda count: count == 1)
        # Pause only supervisor: its child remains alive after lease expiry.
        os.kill(worker.pid, signal.SIGSTOP)
        expire(factory)
        restarted = start_worker(child_env(tmp_path))
        new_ready = wait_for(lambda: capability(client), lambda c: c.get("available") and c["generation"] != ready["generation"])
        assert worker.poll() is None
        queued = post(client, new_ready["generation"]).json()["command"]["id"]
        time.sleep(0.7)
        assert receipt(client, identity)["status"] == "interrupted"
        assert receipt(client, queued)["status"] == "queued" and entered() == 1
        os.kill(worker.pid, signal.SIGCONT)
    finally:
        stop_worker(worker)
        if restarted is not None:
            stop_worker(restarted)


def test_duplicate_native_adapter_cannot_execute_same_claim_twice(process_pg, tmp_path):
    client, factory, engine = process_pg
    generation = register_worker(factory)
    identity = post(client, generation).json()["command"]["id"]
    claimed = claim(factory, generation)
    command = [sys.executable, "-m", "admin_etl_dispatch_adapter", identity, str(claimed[1]), str(generation)]
    for expected in (0, 1):
        result = subprocess.run(command, env=child_env(tmp_path), cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12)
        assert result.returncode == expected
    assert finish(factory, generation, *claimed, 0) is True
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM batch7_effects")) == 1


def test_independent_native_cli_honors_dispatch_domain_exclusion(process_pg, tmp_path):
    client, factory, engine = process_pg
    with engine.begin() as conn:
        conn.execute(text("UPDATE batch7_control SET mode='after'"))
    worker = start_worker(child_env(tmp_path))
    native = None
    try:
        ready = wait_for(lambda: capability(client), lambda c: c.get("available") is True)
        post(client, ready["generation"])
        def committed():
            with engine.connect() as conn:
                return conn.scalar(text("SELECT count(*) FROM batch7_effects"))
        wait_for(committed, lambda count: count == 1)
        # An independently launched unchanged CLI is outside adapter ownership.
        code = "from argparse import Namespace; from seeding.cli import run_seed_command; from seeding.config import SeedingSettings; raise SystemExit(run_seed_command(Namespace(domain=['audits'],all=False,since=None,dry_run=False),SeedingSettings(log_path=None)))"
        native = subprocess.Popen([sys.executable, "-c", code], env=child_env(tmp_path), cwd=ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        assert native.wait(timeout=10) == 1
        # Rejection is observed from the real CLI, with one committed effect.
        assert committed() == 1
    finally:
        if native is not None:
            stop_worker(native)
        stop_worker(worker)
