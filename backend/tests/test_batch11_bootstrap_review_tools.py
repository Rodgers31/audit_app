"""Replay tool failure boundaries; no provider or production transport."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import types

import pytest

PACKET = Path(__file__).resolve().parents[2] / "docs/admin/implementation/batch11-issue-603-evidence"


def load(name):
    spec = importlib.util.spec_from_file_location("batch11_review_" + name, PACKET / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("host,allowed", [("127.0.0.1", True), ("127.1.2.3", True), ("::1", True),
    ("localhost", False), ("owned.invalid", False), ("192.0.2.10", False), ("", False), (None, False)])
def test_transport_allows_only_literal_loopback(host, allowed):
    assert load("full_replay").loopback_literal(host) is allowed


def test_failed_run_without_container_preserves_primary_failure(tmp_path, monkeypatch):
    calls = []
    def docker(*args, check=True):
        calls.append((args, check))
        if args[0] == "run":
            return subprocess.CompletedProcess(args, 125, "", "image missing")
        assert args[0] == "inspect" and check is False
        return subprocess.CompletedProcess(args, 1, "", "container absent")
    monkeypatch.setitem(sys.modules, "batch11_bootstrap_fixture.postgres", types.SimpleNamespace(docker=docker))
    out = tmp_path / "output"
    monkeypatch.setattr(sys, "argv", ["linux_replay.py", "--runtime-root", str(tmp_path), "--out", str(out)])
    with pytest.raises(RuntimeError, match="Linux replay failed; raw output preserved"):
        load("linux_replay").main()
    assert (out / "execution.log").read_text() == "image missing"
    assert len(calls) == 2 and calls[-1][1] is False


def test_junit_inventory_reads_one_snapshot(tmp_path, monkeypatch):
    module = load("verify")
    path = tmp_path / "results.xml"
    path.write_text('<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"><testcase classname="c" name="a"/></testsuite></testsuites>')
    original = module.ET.parse
    calls = []
    def parse(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(module.ET, "parse", parse)
    result = module.inventory(path)
    assert result["counts"]["passed"] == 1 and len(calls) == 1
