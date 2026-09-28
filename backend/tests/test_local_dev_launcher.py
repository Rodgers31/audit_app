"""The normal development entry point must fail before a remote connection."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts" / "local_dev.py"


@pytest.mark.parametrize("command", ["check", "api"])
@pytest.mark.parametrize(
    "inherited",
    [
        {"DATABASE_URL": "postgresql://u:p@db.production.example/postgres"},
        {"DATABASE_URL": "postgresql://u:p@127.0.0.1:55432/auditgava_local_dev?host=production.example"},
        {"DB_HOST": "aws-0.example.pooler.supabase.com"},
        {"NEXT_PUBLIC_API_URL": "https://api.production.example"},
        {"NEXT_PUBLIC_SUPABASE_URL": "https://project.supabase.co"},
    ],
)
def test_launcher_rejects_inherited_remote_targets(inherited, tmp_path, command):
    env = {**os.environ, **inherited, "LOCAL_DEV_DATA_DIR": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, str(LAUNCHER), command],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "Refusing inherited remote" in result.stderr


def test_launcher_accepts_explicit_loopback_configuration(tmp_path):
    env = {
        k: v for k, v in os.environ.items()
        if k not in {"DATABASE_URL", "DB_HOST", "NEXT_PUBLIC_API_URL", "NEXT_PUBLIC_SUPABASE_URL"}
    }
    env["LOCAL_DEV_DATA_DIR"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, str(LAUNCHER), "check"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
