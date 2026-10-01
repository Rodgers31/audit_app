"""Retired formula generator refuses every entry path before filesystem writes."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from seeding.domains.counties_budget.real_budget_fetcher import RealBudgetDataFetcher


@pytest.mark.parametrize("existing", [False, True])
def test_constructor_refuses_before_creating_or_overwriting_output(tmp_path, existing):
    output = tmp_path / "generated"
    if existing:
        output.mkdir()
        (output / "budgets.json").write_bytes(b"archival evidence; do not overwrite")
    before = {
        str(p.relative_to(tmp_path)): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    with pytest.raises(RuntimeError, match="withdrawn"):
        RealBudgetDataFetcher(output_dir=str(output)).fetch_county_budget_allocations()
    after = {
        str(p.relative_to(tmp_path)): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    assert after == before
    assert output.exists() is existing


@pytest.mark.parametrize("instance", [None, "uninitialized", "forged"])
def test_direct_unbound_method_cannot_bypass_constructor(tmp_path, instance):
    output = tmp_path / "direct"
    obj = None if instance is None else object.__new__(RealBudgetDataFetcher)
    if instance == "forged":
        obj.output_dir = str(output)
    with pytest.raises(RuntimeError, match="withdrawn"):
        RealBudgetDataFetcher.fetch_county_budget_allocations(obj)
    assert not output.exists()


@pytest.mark.parametrize("entry", ["script", "module"])
def test_cli_exits_nonzero_without_changing_default_fixture_or_making_files(
    tmp_path, entry
):
    module = sys.modules[RealBudgetDataFetcher.__module__]
    script = Path(module.__file__).resolve()
    fixture = script.parents[2] / "real_data" / "budgets.json"
    before = fixture.read_bytes()
    command = (
        [sys.executable, str(script)]
        if entry == "script"
        else [sys.executable, "-m", RealBudgetDataFetcher.__module__]
    )
    env = {
        **os.environ,
        "PYTHONPATH": str(script.parents[3]),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    # Refuse writes even on the unfixed baseline: this test cannot touch the
    # tracked default fixture while proving that the CLI tries to reach it.
    guard = tmp_path / "sitecustomize.py"
    guard.write_text(
        "import sys\n"
        "def refuse(event, args):\n"
        "    if event == 'os.mkdir' or (event == 'open' and len(args) > 2 and args[2] & 0x243):\n"
        "        raise RuntimeError('filesystem write attempted before withdrawal')\n"
        "sys.addaudithook(refuse)\n"
    )
    env["PYTHONPATH"] = str(tmp_path) + os.pathsep + env["PYTHONPATH"]
    result = subprocess.run(
        command, cwd=script.parents[4], env=env, text=True, capture_output=True, timeout=20
    )
    assert result.returncode != 0
    assert "withdrawn" in result.stderr
    assert "filesystem write attempted" not in result.stderr
    assert fixture.read_bytes() == before
    assert not (tmp_path / "budgets.json").exists()
