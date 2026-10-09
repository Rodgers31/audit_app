"""Public native CLI and separate worker processes; owned inert PostgreSQL only."""
from concurrent.futures import ThreadPoolExecutor
import os
import signal
import subprocess
import sys
import time

import pytest
from sqlalchemy import text

from test_batch7_etl_process import (process_pg, child_env, start_worker, stop_worker,
    capability, receipt, wait_for, ROOT)
from test_batch7_etl_postgres import pg, post, expire, URL
from admin_etl_dispatch_worker import claim, finish, register_worker
from seeding.exclusion import reserve
from uuid import uuid4

pytestmark = pytest.mark.skipif(not URL, reason="Owned PostgreSQL required")


def start_native(tmp_path, *args, env_extra=None, cwd=ROOT):
    env = child_env(tmp_path)
    env["SEED_LOG_PATH"] = str(tmp_path / "native.jsonl")
    env.update(env_extra or {})
    return subprocess.Popen([sys.executable, "-m", "seeding.cli", "seed", *(args or ("--domain", "audits", "--no-dry-run"))],
        env=env, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def mode(engine, value):
    with engine.begin() as conn:
        conn.execute(text("UPDATE batch7_control SET mode=:value"), {"value": value})


def count(engine, table):
    assert table in ("batch7_effects", "batch7_markers", "seeding_domain_claims")
    with engine.connect() as conn:
        return conn.scalar(text("SELECT count(*) FROM " + table + (" WHERE stage='entered'" if table == "batch7_markers" else "")))


def claim_counts(engine):
    with engine.connect() as conn:
        return tuple(conn.execute(text("SELECT count(*) FILTER (WHERE released_at IS NULL),count(*) FILTER (WHERE released_at IS NOT NULL) FROM seeding_domain_claims")).one())


def entered(engine):
    wait_for(lambda: count(engine, "batch7_markers"), lambda n: n == 1)


def assert_rejected(engine, tmp_path):
    other = start_native(tmp_path)
    try:
        assert other.wait(timeout=10) == 1
        assert count(engine, "batch7_markers") == 1
    finally:
        stop_worker(other)


def test_native_first_blocks_worker_then_normal_completion_allows_dispatch(process_pg, tmp_path):
    client, _, engine = process_pg
    mode(engine, "before")
    native = start_native(tmp_path)
    worker = None
    try:
        entered(engine)
        worker = start_worker(child_env(tmp_path))
        ready = wait_for(lambda: capability(client), lambda c: c.get("available") is True)
        identity = post(client, ready["generation"]).json()["command"]["id"]
        time.sleep(0.7)
        assert receipt(client, identity)["status"] == "queued"
        assert count(engine, "batch7_effects") == 0 and claim_counts(engine) == (1, 0)
        mode(engine, "normal")
        assert native.wait(timeout=10) == 0
        final = wait_for(lambda: receipt(client, identity), lambda c: c.get("status") == "completed")
        assert final["job_id"] > 0
        assert count(engine, "batch7_effects") == 2 and claim_counts(engine) == (0, 2)
    finally:
        stop_worker(native)
        if worker is not None:
            stop_worker(worker)


@pytest.mark.parametrize("arguments", [("--all", "--no-dry-run"), ("--domain", "audits", "--no-dry-run")])
def test_dispatch_first_blocks_real_cli_entry_then_completion_allows_native(process_pg, tmp_path, arguments):
    client, _, engine = process_pg
    mode(engine, "before")
    worker = start_worker(child_env(tmp_path))
    try:
        ready = wait_for(lambda: capability(client), lambda c: c.get("available") is True)
        identity = post(client, ready["generation"]).json()["command"]["id"]
        entered(engine)
        other = start_native(tmp_path, *arguments)
        try:
            assert other.wait(timeout=10) == 1
        finally:
            stop_worker(other)
        assert count(engine, "batch7_effects") == 0 and claim_counts(engine) == (1, 0)
        mode(engine, "normal")
        final = wait_for(lambda: receipt(client, identity), lambda c: c.get("status") == "completed")
        assert final["job_id"] > 0 and claim_counts(engine) == (0, 1)
        after = start_native(tmp_path, *arguments)
        try:
            assert after.wait(timeout=10) == 0
        finally:
            stop_worker(after)
        assert count(engine, "batch7_effects") == 2 and claim_counts(engine) == (0, 2)
    finally:
        stop_worker(worker)


@pytest.mark.parametrize("arguments", [("--all", "--no-dry-run"), ("--domain", "audits", "--no-dry-run")])
def test_simultaneous_native_cli_acquisition_has_one_writer_and_then_allows_next(process_pg, tmp_path, arguments):
    _, _, engine = process_pg
    mode(engine, "before")
    with ThreadPoolExecutor(2) as pool:
        runners = list(pool.map(lambda _: start_native(tmp_path, *arguments), range(2)))
    try:
        entered(engine)
        wait_for(lambda: [p.poll() for p in runners], lambda codes: codes.count(1) == 1)
        assert count(engine, "batch7_effects") == 0 and claim_counts(engine) == (1, 0)
        mode(engine, "normal")
        assert sorted(p.wait(timeout=10) for p in runners) == [0, 1]
        assert count(engine, "batch7_effects") == 1 and claim_counts(engine) == (0, 1)
        next_run = start_native(tmp_path, *arguments)
        runners.append(next_run)
        assert next_run.wait(timeout=10) == 0
        assert count(engine, "batch7_effects") == 2 and claim_counts(engine) == (0, 2)
    finally:
        for runner in runners:
            stop_worker(runner)


@pytest.mark.parametrize("phase,effects", [("before", 0), ("after", 1)])
def test_native_death_retains_claim_and_no_second_effect(process_pg, tmp_path, phase, effects):
    _, _, engine = process_pg
    mode(engine, phase)
    native = start_native(tmp_path)
    try:
        entered(engine)
        wait_for(lambda: count(engine, "batch7_effects"), lambda n: n == effects)
        os.killpg(native.pid, signal.SIGKILL)
        native.wait(timeout=5)
        mode(engine, "normal")
        assert_rejected(engine, tmp_path)
        assert count(engine, "batch7_effects") == effects and claim_counts(engine) == (1, 0)
    finally:
        stop_worker(native)


def test_lock_connection_loss_does_not_unlock_live_native_writer(process_pg, tmp_path):
    _, _, engine = process_pg
    mode(engine, "before")
    native = start_native(tmp_path)
    try:
        entered(engine)
        with engine.begin() as conn:
            pids = conn.scalars(text("SELECT DISTINCT pid FROM pg_locks WHERE locktype='advisory' AND granted")).all()
            assert len(pids) == 1
            assert conn.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": pids[0]}) is True
        assert native.poll() is None
        assert_rejected(engine, tmp_path)
        mode(engine, "normal")
        assert native.wait(timeout=10) == 1
        # Its actual writer connection can still commit after lock loss. The
        # retained durable claim prevents a conflicting second invocation.
        assert count(engine, "batch7_effects") == 1 and claim_counts(engine) == (1, 0)
        assert_rejected(engine, tmp_path)
    finally:
        stop_worker(native)


def test_live_orphan_adapter_survives_supervisor_death_and_blocks_native(process_pg, tmp_path):
    client, factory, engine = process_pg
    mode(engine, "after")
    worker = start_worker(child_env(tmp_path))
    restarted = None
    try:
        ready = wait_for(lambda: capability(client), lambda c: c.get("available") is True)
        identity = post(client, ready["generation"]).json()["command"]["id"]
        entered(engine)
        wait_for(lambda: count(engine, "batch7_effects"), lambda n: n == 1)
        os.kill(worker.pid, signal.SIGKILL)  # Child deliberately remains alive.
        worker.wait(timeout=5)
        expire(factory)
        restarted = start_worker(child_env(tmp_path))
        newer = wait_for(lambda: capability(client), lambda c: c.get("available") and c["generation"] != ready["generation"])
        queued = post(client, newer["generation"]).json()["command"]["id"]
        assert receipt(client, identity)["status"] == "interrupted"
        assert_rejected(engine, tmp_path)
        mode(engine, "normal")
        wait_for(lambda: receipt(client, identity), lambda c: c.get("outcome") == "execution_unverified")
        time.sleep(0.7)
        assert receipt(client, queued)["status"] == "queued"
        assert count(engine, "batch7_effects") == 1 and claim_counts(engine) == (1, 0)
    finally:
        # stop_worker ignores a dead leader; explicitly clean this owned group.
        try:
            os.killpg(worker.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stop_worker(worker)
        if restarted is not None:
            stop_worker(restarted)


@pytest.mark.parametrize("dry_run,mode_value,code,effects", [(True,"normal",0,0),(False,"failure",1,0),(False,"normal",0,1)])
def test_native_terminal_receipts_and_next_run(process_pg, tmp_path, dry_run, mode_value, code, effects):
    _, _, engine = process_pg
    mode(engine, mode_value)
    native = start_native(tmp_path, "--domain", "audits", "--dry-run" if dry_run else "--no-dry-run")
    try:
        assert native.wait(timeout=10) == code
        assert count(engine, "batch7_effects") == effects and claim_counts(engine) == (0, 1)
        with engine.connect() as conn:
            row = conn.execute(text("SELECT status::text,dry_run,items_created,metadata->>'seeding_claim_id' FROM ingestion_jobs")).one()
            assert row[0] == ("FAILED" if code else "COMPLETED") and row[1] == dry_run
            assert row[2] == (0 if code else 1) and row[3]
        mode(engine, "normal")
        next_run = start_native(tmp_path)
        try:
            assert next_run.wait(timeout=10) == 0
            assert count(engine, "batch7_effects") == effects + 1 and claim_counts(engine) == (0, 2)
        finally:
            stop_worker(next_run)
    finally:
        stop_worker(native)


@pytest.mark.parametrize("env_extra,error", [
    ({"SEED_DOMAIN_TIMEOUT_SECONDS": "1"}, "domain exceeded 1s budget; aborted by the CLI"),
    ({"SEED_TOTAL_TIMEOUT_SECONDS": "2"}, "stopped: global seed budget exhausted")])
def test_timeout_unwinds_in_process_then_releases_and_allows_next_run(process_pg, tmp_path, env_extra, error):
    # SIGALRM raises in the runner's own thread; the CLI regains control, rolls
    # back and records FAILED before acknowledging. Existing timeout semantics
    # (exit 1, global stop) are unchanged and the next scheduled run proceeds.
    _, _, engine = process_pg
    mode(engine, "before")
    native = start_native(tmp_path, env_extra=env_extra)
    try:
        assert native.wait(timeout=15) == 1
        assert claim_counts(engine) == (0, 1) and count(engine, "batch7_effects") == 0
        with engine.connect() as conn:
            row = conn.execute(text("SELECT status::text, errors FROM ingestion_jobs")).one()
            assert row[0] == "FAILED" and row[1] == [error]
        mode(engine, "normal")
        next_run = start_native(tmp_path)
        try:
            assert next_run.wait(timeout=10) == 0
            assert count(engine, "batch7_effects") == 1 and claim_counts(engine) == (0, 2)
        finally:
            stop_worker(next_run)
    finally:
        stop_worker(native)


def test_worker_is_blocked_by_a_retained_native_claim_alone(process_pg, tmp_path):
    # No RUNNING observation exists, so only the shared claim can stop the worker.
    client, factory, engine = process_pg
    with factory.begin() as db:
        assert reserve(db, "audits", uuid4())
    worker = start_worker(child_env(tmp_path))
    try:
        ready = wait_for(lambda: capability(client), lambda c: c.get("available") is True)
        identity = post(client, ready["generation"]).json()["command"]["id"]
        time.sleep(1.0)
        assert receipt(client, identity)["status"] == "queued"
        assert count(engine, "batch7_markers") == 0 and claim_counts(engine) == (1, 0)
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM ingestion_jobs WHERE status='RUNNING'")) == 0
    finally:
        stop_worker(worker)


def test_concurrently_launched_duplicate_adapters_run_once(process_pg, tmp_path):
    _, factory, engine = process_pg
    client = process_pg[0]
    mode(engine, "normal")
    generation = register_worker(factory)
    identity = post(client, generation).json()["command"]["id"]
    command_id, token = claim(factory, generation)
    argv = [sys.executable, "-m", "admin_etl_dispatch_adapter", identity, str(token), str(generation)]
    with ThreadPoolExecutor(3) as pool:
        children = list(pool.map(lambda _: subprocess.Popen(argv, env=child_env(tmp_path), cwd=ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True), range(3)))
    try:
        assert sorted(child.wait(timeout=15) for child in children) == [0, 1, 1]
        assert count(engine, "batch7_effects") == 1 and count(engine, "batch7_markers") == 1
        assert finish(factory, generation, command_id, token, 0) is True
        assert claim_counts(engine) == (0, 1)
    finally:
        for child in children:
            stop_worker(child)


def test_dispatch_lock_connection_loss_retains_claim_after_its_effect(process_pg, tmp_path):
    client, _, engine = process_pg
    mode(engine, "before")
    worker = start_worker(child_env(tmp_path))
    try:
        ready = wait_for(lambda: capability(client), lambda c: c.get("available") is True)
        identity = post(client, ready["generation"]).json()["command"]["id"]
        entered(engine)
        with engine.begin() as conn:
            pids = conn.scalars(text("SELECT DISTINCT pid FROM pg_locks WHERE locktype='advisory' AND granted")).all()
            assert len(pids) == 1
            assert conn.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": pids[0]}) is True
        mode(engine, "normal")
        final = wait_for(lambda: receipt(client, identity), lambda c: c.get("status") == "interrupted")
        assert final["outcome"] == "execution_unverified"
        # The adapter's writer committed; continuity was lost, so no release.
        assert count(engine, "batch7_effects") == 1 and claim_counts(engine) == (1, 0)
        assert_rejected(engine, tmp_path)
    finally:
        stop_worker(worker)
