"""Inline scripts in GitHub workflows must actually parse.

On 2026-09-02 a routine f-string was added to the nightly seed workflow:

    src = f" | source={mode or 'unrecorded'}"

It sat inside a ``python -c "..."`` block — a DOUBLE-QUOTED shell string — so
its double quotes terminated that string. The shell then parsed the remainder
as a pipeline (``or: command not found``) and Python received a truncated line
(``NameError: name 'f' is not defined``). Every nightly from 2026-09-03 died
with exit 127 before seeding anything, and production data froze silently: the
job that failed is the one whose whole purpose is reporting whether the seed
worked.

Nothing caught it. The YAML was valid, the Python was valid, and the bug lived
only in the seam between them. These tests check that seam.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOWS = sorted(
    (Path(__file__).resolve().parents[2] / ".github" / "workflows").glob("*.yml")
)


def _run_steps():
    """Every ``run:`` script in every workflow, with where it came from."""
    for wf in WORKFLOWS:
        doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
        for job_name, job in (doc.get("jobs") or {}).items():
            for i, step in enumerate(job.get("steps") or []):
                script = step.get("run")
                if script:
                    label = step.get("name") or f"step {i}"
                    yield f"{wf.name}::{job_name}::{label}", script


assert WORKFLOWS, "no workflow files found — this test would pass vacuously"

RUN_STEPS = list(_run_steps())
STEP_IDS = [where for where, _ in RUN_STEPS]
assert RUN_STEPS, "no run: steps found — these tests would pass vacuously"


@pytest.mark.parametrize("where,script", RUN_STEPS, ids=STEP_IDS)
def test_no_double_quote_inside_a_python_dash_c_block(where, script):
    """``python -c "`` cannot contain a double quote. Use a quoted heredoc.

    This is the exact defect that killed the nightly. The fix is
    ``python <<'PY' ... PY``, which the shell does not interpret at all.
    """
    # Find the block by its INTENDED extent — from `python -c "` to the line
    # that is just a closing quote — not by the first quote encountered. The
    # first quote encountered IS the bug: matching to it made this check pass
    # on the exact workflow that was failing in CI.
    lines = script.split("\n")
    starts = [i for i, ln in enumerate(lines) if re.search(r'python[0-9.]* -c "\s*$', ln)]
    for start in starts:
        end = next(
            (j for j in range(start + 1, len(lines)) if lines[j].strip() == '"'),
            len(lines),
        )
        body = "\n".join(lines[start + 1 : end])
        offenders = [ln.strip() for ln in body.split("\n") if '"' in ln]
        assert not offenders, (
            f"{where}: a double quote inside `python -c \"...\"` ends the shell "
            f"string early — the rest is parsed as shell, not Python. "
            f"Use `python <<'PY' ... PY`. Offending line(s): {offenders[:3]}"
        )


@pytest.mark.parametrize("where,script", RUN_STEPS, ids=STEP_IDS)
def test_the_shell_can_parse_the_script(where, script):
    """``bash -n`` on every run block that has no GitHub expressions.

    Steps carrying ``${{ }}`` are skipped: those are substituted by Actions
    before the shell sees them, so parsing them here would be testing the
    wrong string.
    """
    if "${{" in script:
        pytest.skip("contains GitHub expressions, substituted before execution")
    result = subprocess.run(
        ["bash", "-n"], input=script, text=True, capture_output=True
    )
    assert result.returncode == 0, f"{where}: {result.stderr.strip()[:300]}"


def test_the_seed_result_check_still_reports_the_source_mode():
    """Positive control for the block that broke.

    The line that triggered the failure is a real feature — it reports whether
    a domain served live data or a git-tracked fixture, which is how a silently
    frozen pipeline is meant to become visible. The fix must keep it, not
    delete it.
    """
    seed = next(w for w in WORKFLOWS if w.name == "seed.yml")
    doc = yaml.safe_load(seed.read_text(encoding="utf-8"))
    step = next(
        s
        for s in doc["jobs"]["seed"]["steps"]
        if s.get("name") == "Check ingestion job results"
    )
    body = re.search(r"python <<'PY'\n(.*?)\nPY", step["run"], re.S)
    assert body, "the ingestion-result check is no longer a quoted heredoc"
    compile(body.group(1), "<heredoc>", "exec")
    assert "source=" in body.group(1), "source-mode reporting was dropped"
    assert "STALE" in body.group(1), "the fixture-vs-live distinction was dropped"
