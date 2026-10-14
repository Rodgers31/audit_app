"""Execute the weekly/manual workflow shell with controlled bootstrap returns.

These are wrapper controls, not database integration: the real bootstrap and
PostgreSQL rehearsals are independently recorded in the Lane A handoff.
"""
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/seed.yml"
SUCCESS = "Bootstrap seeding completed successfully"
INCOMPLETE = "Bootstrap seeding deferred or incomplete"


def run_wrapper(tmp_path, body, optimized):
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["bootstrap"]["steps"]
    step, = [step for step in steps if step.get("name") == "Run bootstrap seeding"]
    backend = tmp_path / "backend"
    backend.mkdir()
    if body is not None:
        (backend / "bootstrap.py").write_text("def initialize_reference_data():\n    " + body + "\n")
    env = {
        "PATH": str(Path(sys.executable).parent) + os.pathsep + "/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONOPTIMIZE": "1" if optimized else "0",
        "PYTHON_DOTENV_DISABLED": "1",
    }
    return subprocess.run(
        ["/bin/bash", "-e", "-c", step["run"]], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=15,
    )


@pytest.mark.parametrize("optimized", [False, True], ids=["normal", "optimized"])
def test_admitted_bootstrap_reports_success(tmp_path, optimized):
    result = run_wrapper(tmp_path, "return True", optimized)
    assert result.returncode == 0, result.stderr
    assert result.stdout.count(SUCCESS) == 1
    assert INCOMPLETE not in result.stdout + result.stderr


@pytest.mark.parametrize("optimized", [False, True], ids=["normal", "optimized"])
@pytest.mark.parametrize("value", ["False", "None", "0", "1", "'false'", "{'success': False}"],
                         ids=["deferred", "absent", "zero", "truthy-integer", "truthy-string", "truthy-failure"])
def test_unadmitted_bootstrap_cannot_report_success(tmp_path, optimized, value):
    result = run_wrapper(tmp_path, "return " + value, optimized)
    assert result.returncode == 2, result.stdout + result.stderr
    assert SUCCESS not in result.stdout + result.stderr
    assert INCOMPLETE in result.stderr
    assert "inspect bootstrap logs and retained ownership before retry" in result.stderr


@pytest.mark.parametrize("optimized", [False, True], ids=["normal", "optimized"])
def test_bootstrap_exception_remains_a_visible_failure(tmp_path, optimized):
    result = run_wrapper(tmp_path, "raise RuntimeError('owned bootstrap exception')", optimized)
    assert result.returncode == 1
    assert "RuntimeError: owned bootstrap exception" in result.stderr
    assert SUCCESS not in result.stdout + result.stderr
    assert INCOMPLETE not in result.stdout + result.stderr


@pytest.mark.parametrize("optimized", [False, True], ids=["normal", "optimized"])
@pytest.mark.parametrize("body, diagnostic", [(None, "ModuleNotFoundError"),
                                             ("return (", "SyntaxError")],
                         ids=["missing-module", "malformed-module"])
def test_wrapper_import_failure_cannot_report_an_outcome(tmp_path, optimized, body, diagnostic):
    result = run_wrapper(tmp_path, body, optimized)
    assert result.returncode == 1
    assert diagnostic in result.stderr
    assert SUCCESS not in result.stdout + result.stderr
    assert INCOMPLETE not in result.stdout + result.stderr
