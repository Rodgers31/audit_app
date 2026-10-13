"""Actual HTTP router, supervisor, adapter and native CLI on owned PostgreSQL."""
from contextlib import contextmanager
import json
import os
import signal
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx
from jose import jwt
import pytest
from sqlalchemy import text

from test_batch9_reconciliation import owned, read, ROOT  # noqa: F401

FIXTURE = ROOT / "scripts/batch12_rollout_fixture"


def wait_for(read_value, condition, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = read_value()
        if condition(value):
            return value
        time.sleep(0.05)
    raise AssertionError("Owned worker did not reach required receipt")


def environment(db, tmp_path, nonce, admin_subject):
    system_id = read(db, "SELECT system_identifier::text AS id FROM pg_control_system()")[0]["id"]
    return {"PATH": "/usr/bin:/bin", "PYTHON_DOTENV_DISABLED": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(FIXTURE) + os.pathsep + str(ROOT), "DATABASE_URL": db.url,
        "BATCH12_INERT_PROCESS": "true", "BATCH12_EXPECTED_DATABASE": db.name,
        "BATCH12_EXPECTED_SYSTEM_ID": system_id, "BATCH12_EXPECTED_NONCE": nonce,
        "BATCH12_ADMIN_SUBJECT": admin_subject, "SUPABASE_URL": "https://owned.invalid",
        "SUPABASE_JWT_SECRET": "batch12-inert-signing-key", "ADMIN_ETL_DISPATCH_ENABLED": "true",
        "ADMIN_ETL_DISPATCH_SOURCES": "oag", "AUTO_SEEDER_ENABLED": "false", "PARLIAMENT_PIPELINE_ENABLED": "0",
        "SEED_LOG_PATH": str(tmp_path / "seed.jsonl"), "SEED_STORAGE_PATH": str(tmp_path / "storage"),
        "SEED_CACHE_PATH": str(tmp_path / "cache")}


def group_members(pid):
    rows = subprocess.check_output(["ps", "-axo", "uid=,pid=,pgid=,command="], text=True).splitlines()
    return [line.split(None, 3) for line in rows if len(line.split(None, 3)) == 4 and int(line.split(None, 3)[2]) == pid]


@contextmanager
def process(tmp_path, env, module, *args):
    argv = [sys.executable, *(["-O"] if sys.flags.optimize else []), "-B", "-m", module, *args]
    path = tmp_path / (module + "-" + uuid4().hex + ".log")
    with path.open("xb") as log:
        child = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        birth = subprocess.check_output(["ps", "-p", str(child.pid), "-o", "lstart="], text=True).strip()
        try:
            yield child, path
        finally:
            # Reap only our exact Popen child first. An exited root appears as
            # a zombie with no module argv on Linux; it is not a foreign child.
            child.poll()
            members = group_members(child.pid)
            if members:
                if any(int(row[0]) != os.getuid() or not any(name in row[3] for name in (module, "admin_etl_dispatch_adapter")) for row in members):
                    raise RuntimeError("Owned process cleanup identity mismatch")
                os.killpg(child.pid, signal.SIGINT)
                try:
                    child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)
            else:
                child.wait(timeout=5)
            remaining = group_members(child.pid)
            receipt = {"argv": argv, "pid": child.pid, "birth": birth, "exit_code": child.returncode,
                       "remaining_group_members": remaining, "production_ready": False}
            (path.with_suffix(".receipt.json")).write_text(json.dumps(receipt, indent=2) + "\n")
            if remaining:
                raise RuntimeError("Owned process cleanup incomplete")


def headers(subject):
    token = jwt.encode({"sub": subject, "aud": "authenticated", "exp": int(time.time()) + 120},
                       "batch12-inert-signing-key", algorithm="HS256")
    return {"Authorization": "Bearer " + token}


@pytest.mark.parametrize("mode,dry_run,terminal,effects", [("normal", False, "completed", 1),
    ("normal", True, "completed", 0), ("failure", False, "failed", 0)])
def test_http_acceptance_correlates_one_actual_worker_execution(owned, tmp_path, mode, dry_run, terminal, effects):
    nonce, admin_subject = uuid4().hex, str(uuid4())
    with owned.connection.begin():
        owned.connection.execute(text("CREATE TABLE batch12_control(mode text NOT NULL, nonce text NOT NULL)"))
        owned.connection.execute(text("INSERT INTO batch12_control VALUES (:mode,:nonce)"), {"mode": mode, "nonce": nonce})
        owned.connection.execute(text("CREATE TABLE batch12_markers(job_id integer NOT NULL, pid integer NOT NULL, custody jsonb NOT NULL)"))
        owned.connection.execute(text("CREATE TABLE batch12_process_exit(pid integer PRIMARY KEY, exit_code integer NOT NULL, observer_pid integer NOT NULL)"))
        owned.connection.execute(text("CREATE TABLE batch12_effects(job_id integer NOT NULL)"))
    env = environment(owned, tmp_path, nonce, admin_subject)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 18060))
    with process(tmp_path, env, "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "18060") as (server, server_log), httpx.Client(base_url="http://127.0.0.1:18060", trust_env=False) as client:
        def server_response():
            try:
                return client.get("/api/v1/admin/etl/dispatch", headers=headers(admin_subject))
            except httpx.TransportError:
                if server.poll() is not None:
                    raise RuntimeError(f"Owned HTTP fixture exited {server.returncode}: {server_log.read_text()}")
                return None
        unavailable = wait_for(server_response, lambda r: r is not None)
        assert unavailable.status_code == 200 and unavailable.json()["available"] is False
        denied = client.post("/api/v1/admin/etl/trigger/oag", headers=headers(str(uuid4())), json={})
        assert denied.status_code == 403 and denied.headers["cache-control"] == "private, no-store"
        disabled = client.post("/api/v1/admin/etl/trigger/oag",
            headers={**headers(admin_subject), "Idempotency-Key": str(uuid4())},
            json={"dry_run": False, "dispatch_generation": str(uuid4())})
        assert disabled.status_code == 503
        assert read(owned, "SELECT count(*) AS n FROM admin_audit_log")[0]["n"] == 0
        assert read(owned, "SELECT count(*) AS n FROM etl_dispatch_commands")[0]["n"] == 0
        with process(tmp_path, env, "admin_etl_dispatch_worker") as (worker, _):
            ready = wait_for(server_response, lambda r: r is not None and r.json()["available"] is True).json()
            assert ready["sources"]["oag"]["available"] is True
            key = str(uuid4())
            request_headers = {**headers(admin_subject), "Idempotency-Key": key}
            body = {"dry_run": dry_run, "dispatch_generation": ready["generation"]}
            accepted = client.post("/api/v1/admin/etl/trigger/oag", headers=request_headers, json=body)
            assert accepted.status_code == 202, accepted.text
            payload = accepted.json()
            identity = payload["command"]["id"]
            assert payload["audit_recorded"] is True and payload["replayed"] is False
            replay = client.post("/api/v1/admin/etl/trigger/oag", headers=request_headers, json=body)
            assert replay.status_code == 202 and replay.json()["replayed"] is True and replay.json()["command"]["id"] == identity
            receipt = wait_for(lambda: client.get("/api/v1/admin/etl/commands/" + identity, headers=headers(admin_subject)),
                               lambda r: r.status_code == 200 and r.json()["status"] in ("completed", "failed", "interrupted"))
            assert receipt.json()["status"] == terminal and receipt.json()["job_id"] is not None
            assert "fixture-private-error" not in receipt.text
            jobs = read(owned, "SELECT * FROM ingestion_jobs")
            claims = read(owned, "SELECT * FROM seeding_domain_claims")
            markers = read(owned, "SELECT * FROM batch12_markers")
            commands = read(owned, "SELECT * FROM etl_dispatch_commands")
            audits = read(owned, "SELECT * FROM admin_audit_log")
            exits = read(owned, "SELECT * FROM batch12_process_exit")
            assert len(jobs) == len(claims) == len(markers) == len(commands) == len(audits) == len(exits) == 1
            assert jobs[0]["id"] == receipt.json()["job_id"] == markers[0]["job_id"] == claims[0]["job_id"]
            assert jobs[0]["metadata"]["dispatch_command_id"] == identity
            assert jobs[0]["metadata"]["dispatch_claim_token"] == jobs[0]["metadata"]["seeding_claim_id"] == str(claims[0]["id"])
            assert str(claims[0]["command_id"]) == identity and claims[0]["returned_at"] and claims[0]["released_at"]
            assert markers[0]["pid"] != worker.pid
            custody = markers[0]["custody"]
            assert custody["ppid"] == custody["pgid"] == exits[0]["observer_pid"] == worker.pid
            assert custody["uid"] == os.getuid() and custody["birth"]
            assert custody["argv"] == [str(ROOT / "admin_etl_dispatch_adapter.py"), identity,
                                        str(claims[0]["id"]), ready["generation"]]
            assert custody["optimized"] == 0  # Actual product child argv has no -O.
            assert exits[0]["pid"] == markers[0]["pid"]
            assert exits[0]["exit_code"] == (1 if mode == "failure" else 0)
            assert str(commands[0]["id"]) == identity
            assert commands[0]["audit_id"] == audits[0]["id"]
            assert commands[0]["actor_id"] == audits[0]["actor_id"] == admin_subject
            assert audits[0]["action"] == "etl.trigger" and audits[0]["target_type"] == "etl_command"
            assert audits[0]["target_id"] == identity and audits[0]["payload"]["dry_run"] is dry_run
            assert read(owned, "SELECT count(*) AS n FROM batch12_effects")[0]["n"] == effects
            (tmp_path / "correlation.json").write_text(json.dumps({"command": identity, "job_id": jobs[0]["id"],
                "claim": str(claims[0]["id"]), "handler_pid": markers[0]["pid"], "supervisor_pid": worker.pid,
                "adapter_custody": custody, "adapter_exit": dict(exits[0]), "audit_id": audits[0]["id"],
                "audit_actor": audits[0]["actor_id"], "audit_target": audits[0]["target_id"],
                "mode": mode, "dry_run": dry_run, "effects": effects, "audit_rows": 1, "production_ready": False}, indent=2) + "\n")
        assert worker.returncode == 0
