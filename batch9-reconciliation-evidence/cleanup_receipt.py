"""Verify ownership, stop only this lane's local DB, and read back the receipt."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = "batch9-reconciliation-a46a-db"
EXPECTED_ID = "b70fa66e1693ac4c41ce20a58142672631367db1208630c08da59b2a7b62d843"
URL = "postgresql+psycopg2://postgres:batch9-inert-local@127.0.0.1:55493/postgres"
SOURCE_FILES = (
    "backend/models.py", "backend/seeding/reconciliation.py",
    "backend/seeding/reconcile_operator.py",
    "backend/alembic/versions/e583b9c9a001_reconciliation_evidence.py",
    "backend/tests/test_batch9_reconciliation.py",
    "backend/tests/test_batch9_reconciliation_constraints.py",
    "backend/tests/test_batch9_reconciliation_processes.py",
    "backend/tests/test_batch9_reconciliation_migration.py",
    "backend/tests/batch9_reconciliation_fixture/sitecustomize.py",
)


def run(command):
    value = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=30)
    assert value.returncode == 0, (command, value.stderr)
    return {"command": command, "exit_code": value.returncode,
            "stdout": value.stdout, "stderr": value.stderr}


def main():
    destination = ROOT / "batch9-reconciliation-evidence/cleanup.json"
    assert not destination.exists(), "append-only receipt"
    before = run(["docker", "inspect", "--format",
                  "{{json .Id}} {{json .Name}} {{json .State.Running}} {{json .NetworkSettings.Ports}}", CONTAINER])
    identity, name, running, ports = before["stdout"].strip().split(" ", 3)
    assert json.loads(identity) == EXPECTED_ID and json.loads(name) == "/" + CONTAINER
    assert json.loads(running) is True
    assert json.loads(ports)["5432/tcp"] == [{"HostIp": "127.0.0.1", "HostPort": "55493"}]
    engine = create_engine(URL, poolclass=NullPool)
    with engine.connect() as connection:
        databases = connection.execute(text(
            "SELECT datname FROM pg_database WHERE datname LIKE 'batch9-reconciliation-%' ORDER BY datname"
        )).scalars().all()
        assert databases == ["batch9-reconciliation-a46a"], databases
        sessions = connection.execute(text(
            "SELECT datname, backend_type FROM pg_stat_activity WHERE datname LIKE 'batch9-reconciliation-%'"
        )).mappings().all()
        assert not sessions, sessions
    engine.dispose()
    processes = run(["ps", "-axo", "pid=,ppid=,stat=,command="])
    owned = [line for line in processes["stdout"].splitlines()
             if "batch9-reconciliation-" in line and
             any(pattern in line for pattern in ("-m seeding.", "--operator-child", "--adapter"))]
    assert not owned, owned
    stopped = run(["docker", "stop", "--time", "10", CONTAINER])
    after = run(["docker", "inspect", "--format", "{{json .Id}} {{json .State.Running}}", CONTAINER])
    identity, running = after["stdout"].strip().split(" ", 1)
    assert json.loads(identity) == EXPECTED_ID and json.loads(running) is False
    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", 55493)) != 0, "Owned port still accepting"
    # Broad ps output is used only for filtering; do not export unrelated commands.
    receipt = {"generated_by": str(Path(__file__).relative_to(ROOT)),
               "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "generated_at": datetime.now(timezone.utc).isoformat(),
               "target_commit": run(["git", "rev-parse", "HEAD"])["stdout"].strip(),
               "source_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in SOURCE_FILES},
               "runtime": run([os.sys.executable, "--version"]),
               "container_before": before, "databases_before": databases,
               "target_sessions_before": [dict(row) for row in sessions],
               "owned_processes_remaining": owned,
               "container_stop": stopped, "container_after": after,
               "loopback_port_accepting_after": False,
               "retained": "Stopped owned container data, managed worktree, inert owned runtimes and evidence retained for review; no production or shared service changed.",
               "verdict": "PASSED"}
    destination.write_text(json.dumps(receipt, indent=2) + "\n")
    assert json.loads(destination.read_text()) == receipt
    print("Owned container stopped; no fixture DB/session/process leftovers; receipt readback passed")


if __name__ == "__main__":
    main()
