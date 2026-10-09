"""Exercise the committed receipt runner with a fresh owned SQLite path."""

import json
from pathlib import Path
import sqlite3
import subprocess
import sys


RUNNER = (Path(__file__).resolve().parents[2] /
          "docs/admin/implementation/batch8-producer-evidence/run_check.py")


def test_fresh_receipt_directory_allows_real_database_child(tmp_path):
    output = tmp_path / "new-parent" / "receipts"
    assert not output.exists()
    child = """
import socket
def deny(*args, **kwargs):
    raise AssertionError("Receipt runner fixture attempted socket transport")
socket.socket.connect = deny
socket.socket.connect_ex = deny
from database import engine
from sqlalchemy import text
with engine.begin() as connection:
    connection.execute(text("CREATE TABLE runner_probe (value TEXT NOT NULL)"))
    connection.execute(text("INSERT INTO runner_probe VALUES ('actual-sqlite-child')"))
print("actual-sqlite-child-committed")
"""
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--label", "fresh-directory",
         "--output-dir", str(output), "--lint-packages", str(tmp_path / "lint"),
         "--", sys.executable, "-c", child],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads((output / "fresh-directory.json").read_text())
    assert receipt["exit_status"] == 0
    assert receipt["verdict"] == "PASS"
    assert "actual-sqlite-child-committed" in receipt["stdout"]
    with sqlite3.connect(output / "runner.sqlite") as connection:
        assert connection.execute("SELECT value FROM runner_probe").fetchall() == [
            ("actual-sqlite-child",)
        ]
