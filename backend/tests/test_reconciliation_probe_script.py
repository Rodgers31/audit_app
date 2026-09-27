"""The independently runnable stale-session probe must certify refusal."""

import json
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("optimized", [False, True])
def test_standalone_probe_preserves_newer_evidence(optimized, tmp_path):
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts/reproduce_reconciliation_stale_session.py"
    )
    command = [sys.executable]
    if optimized:
        command.append("-O")
    command.append(str(script))
    result = subprocess.run(
        command,
        cwd=tmp_path,  # Import resolution cannot depend on the checkout cwd.
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    assert rows == [
        {
            "explicit_refresh": refresh,
            "stale_review": "refused",
            "stored_text": "NEWER CORRECTION B",
        }
        for refresh in (False, True)
    ]
    assert "PASS: both stale reviews refused" in result.stdout
