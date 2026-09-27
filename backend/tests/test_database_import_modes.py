"""Database modules resolve their helper in both supported launch modes."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("module", ["database", "database_enhanced"])
@pytest.mark.parametrize("package", [False, True])
def test_database_import_mode(module, package):
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "DATABASE_URL": "postgresql://test:test@localhost/unused"}
    env.pop("PYTHONPATH", None)
    name = f"backend.{module}" if package else module
    result = subprocess.run(
        [sys.executable, "-c", f"import {name} as db; assert db.engine.url.drivername == 'postgresql+psycopg2'"],
        cwd=root if package else root / "backend", env=env,
        text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
