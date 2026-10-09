"""Real CLI/worker/adapter/orphan processes, inert registry, owned loopback DB."""
import os
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from admin_etl_dispatch import accept, TriggerBody
from test_batch9_reconciliation import signed, read, ROOT
from test_batch9_reconciliation import owned  # noqa: F401 -- registers the owned pytest fixture
from seeding.reconciliation import ReconciliationRefused, make_plan, apply_plan


def wait_for(read_value, condition, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = read_value()
        if condition(value):
            return value
        time.sleep(0.05)
    raise AssertionError("Owned process did not reach required marker")


def setup(db, mode):
    with db.connection.begin():
        db.connection.execute(text("CREATE TABLE batch9_control(mode text NOT NULL)"))
        db.connection.execute(text("CREATE TABLE batch9_effects(job_id integer)"))
        db.connection.execute(text("CREATE TABLE batch9_markers(stage text,job_id integer)"))
        db.connection.execute(text("INSERT INTO batch9_control VALUES (:mode)"), {"mode": mode})


def environment(db, tmp_path):
    return {"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHON_DOTENV_DISABLED": "1", "PYTHONPATH": str(ROOT / "tests/batch9_reconciliation_fixture") + os.pathsep + str(ROOT),
            "DATABASE_URL": db.url, "ADMIN_ETL_DISPATCH_ENABLED": "true",
            "BATCH9_RECONCILIATION_INERT_PROCESS": "true", "SEED_LOG_PATH": str(tmp_path / "seed.jsonl"),
            "SEED_STORAGE_PATH": str(tmp_path / "storage"), "SEED_CACHE_PATH": str(tmp_path / "cache")}


def start(db, tmp_path, module="seeding.cli", args=("seed", "--domain", "audits")):
    output = (tmp_path / (module.replace(".", "-") + ".log")).open("a")
    process = subprocess.Popen([sys.executable, "-m", module, *args], cwd=ROOT,
        env=environment(db, tmp_path), stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
    output.close()
    return process


def stop(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def selected(db):
    rows = read(db, "SELECT id,domain FROM seeding_domain_claims WHERE released_at IS NULL")
    assert len(rows) == 1
    return {"domain": rows[0]["domain"], "claim_id": str(rows[0]["id"]), "legacy_job_ids": []}


def terminate_writer_backends(db):
    pid = read(db, "SELECT pg_backend_pid() AS pid")[0]["pid"]
    with db.admin.connect() as admin:
        killed = admin.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:database AND pid<>:operator"),
                               {"database": db.name, "operator": pid}).all()
        assert killed and all(v[0] for v in killed)
    wait_for(lambda: read(db, "SELECT count(*) AS n FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()")[0]["n"], lambda n: n == 0)


@pytest.mark.parametrize("mode,expected_effects", [("before", 0), ("after", 1)])
def test_live_native_disconnected_lock_is_not_quiescence_and_next_real_cli_runs(owned, tmp_path, mode, expected_effects):
    setup(owned, mode)
    process = start(owned, tmp_path, args=("seed", "--all"))
    try:
        stage = "entered" if mode == "before" else "committed"
        wait_for(lambda: read(owned, "SELECT stage FROM batch9_markers"), lambda rows: any(r["stage"] == stage for r in rows))
        claim = selected(owned)
        policy, bad_evidence, _ = signed(owned, claim)
        owned.admission(False)
        with pytest.raises(ReconciliationRefused, match="sessions"):
            make_plan(owned.connection, policy, bad_evidence)
        # A stopped host process is still alive. Kill its actual DB backends;
        # neither backend disappearance nor a stale PID is a quiescence proof.
        os.killpg(process.pid, signal.SIGSTOP)
        terminate_writer_backends(owned)
        assert process.poll() is None
        policy, live_evidence, _ = signed(owned, claim, writer_state="live")
        with pytest.raises(ReconciliationRefused, match="Live or uncertain"):
            make_plan(owned.connection, policy, live_evidence)
        assert len(read(owned, "SELECT * FROM seeding_domain_claims WHERE released_at IS NULL")) == 1
        stop(process)
        assert process.returncode == -signal.SIGKILL
        policy, evidence, _ = signed(owned, claim)
        plan = make_plan(owned.connection, policy, evidence)
        apply_plan(owned.connection, policy, evidence, plan)
        assert read(owned, "SELECT count(*) AS n FROM batch9_effects")[0]["n"] == expected_effects
        owned.admission(True)
        with owned.connection.begin():
            owned.connection.execute(text("UPDATE batch9_control SET mode='normal'"))
        next_run = start(owned, tmp_path)
        try:
            assert next_run.wait(timeout=15) == 0, (tmp_path / "seeding-cli.log").read_text()
        finally:
            stop(next_run)
        assert read(owned, "SELECT count(*) AS n FROM batch9_effects")[0]["n"] == expected_effects + 1
    finally:
        stop(process)


@pytest.mark.parametrize("mode,expected_effects", [("before", 0), ("after", 1)])
def test_supervisor_death_with_actual_live_orphan_refuses_then_dispatch_reconciles_atomically(owned, tmp_path, monkeypatch, mode, expected_effects):
    setup(owned, mode)
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "true")
    supervisor = start(owned, tmp_path, "admin_etl_dispatch_worker", ())
    try:
        worker = wait_for(lambda: read(owned, "SELECT generation FROM etl_dispatch_worker WHERE ready"), bool)[0]
        with owned.factory() as session:
            accepted = accept(session, SimpleNamespace(id="operator", email="owned@example.invalid"), "oag",
                              TriggerBody(dispatch_generation=str(worker["generation"])), str(uuid4()))
        command_id = accepted.command.id
        stage = "entered" if mode == "before" else "committed"
        wait_for(lambda: read(owned, "SELECT stage FROM batch9_markers"), lambda rows: any(r["stage"] == stage for r in rows))
        claim = selected(owned)
        os.killpg(supervisor.pid, signal.SIGSTOP)
        os.kill(supervisor.pid, signal.SIGKILL)
        supervisor.wait(timeout=5)
        # The real adapter child stays stopped/alive in the dead parent's group.
        orphan = subprocess.check_output(["ps", "-axo", "pid=,pgid=,command="], text=True)
        members = [line for line in orphan.splitlines() if "admin_etl_dispatch_adapter" in line and int(line.split()[1]) == supervisor.pid]
        assert members, "Actual adapter orphan must remain alive"
        owned.admission(False)
        terminate_writer_backends(owned)
        policy, live_evidence, _ = signed(owned, claim, writer_state="live")
        with pytest.raises(ReconciliationRefused):
            make_plan(owned.connection, policy, live_evidence)
        assert len(read(owned, "SELECT * FROM seeding_domain_claims WHERE released_at IS NULL")) == 1
        stop(supervisor)  # Kills the orphan group too.
        with owned.connection.begin():
            owned.connection.execute(text("UPDATE etl_dispatch_worker SET ready=false"))
        policy, evidence, _ = signed(owned, claim)
        original = read(owned, "SELECT * FROM seeding_domain_claims")[0]
        plan = make_plan(owned.connection, policy, evidence)
        apply_plan(owned.connection, policy, evidence, plan)
        command = read(owned, "SELECT * FROM etl_dispatch_commands")[0]
        assert command["id"] == command_id and command["status"] == "interrupted" and command["outcome"] == "execution_unverified"
        assert command["job_id"] is None
        assert read(owned, "SELECT * FROM etl_dispatch_domains")[0]["command_id"] is None
        current = read(owned, "SELECT * FROM seeding_domain_claims")[0]
        assert current["returned_at"] == original["returned_at"] and current["job_id"] == original["job_id"]
        assert current["entry_id"] == original["entry_id"] and current["released_at"]
        assert read(owned, "SELECT * FROM ingestion_jobs")[0]["status"] == "FAILED"
        assert read(owned, "SELECT count(*) AS n FROM batch9_effects")[0]["n"] == expected_effects
        owned.admission(True)
        with owned.connection.begin():
            owned.connection.execute(text("UPDATE batch9_control SET mode='normal'"))
        replacement = start(owned, tmp_path, "admin_etl_dispatch_worker", ())
        try:
            next_worker = wait_for(lambda: read(owned, "SELECT generation FROM etl_dispatch_worker WHERE ready"),
                                   lambda rows: rows and rows[0]["generation"] != worker["generation"])[0]
            with owned.factory() as session:
                next_command = accept(session, SimpleNamespace(id="operator", email="owned@example.invalid"), "oag",
                    TriggerBody(dispatch_generation=str(next_worker["generation"])), str(uuid4())).command.id
            wait_for(lambda: read(owned, f"SELECT status FROM etl_dispatch_commands WHERE id='{next_command}'"),
                     lambda rows: rows and rows[0]["status"] == "completed")
            assert read(owned, "SELECT count(*) AS n FROM batch9_effects")[0]["n"] == expected_effects + 1
        finally:
            stop(replacement)
    finally:
        stop(supervisor)
