"""Replay tool failure boundaries; no provider or production transport."""
import importlib.util
import json
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


@pytest.mark.parametrize("mode", ["removed", "not_created", "daemon_before", "daemon_after", "permission_before", "permission_after",
    "failed_run_daemon", "remove_failure", "wrong_owner", "wrong_absent_name", "malformed_state", "survived"])
def test_linux_cleanup_requires_exact_owned_absence(tmp_path, monkeypatch, capsys, mode):
    """Execute the actual launcher at a controlled Docker result boundary."""
    calls, inspections = [], []
    owned = None
    def docker(*args, check=True):
        nonlocal owned
        calls.append((args, check))
        if args[0] == "run":
            owned = args[args.index("--name") + 1]
            return subprocess.CompletedProcess(args, 125 if mode == "failed_run_daemon" else int(mode == "not_created"),
                "owned actual run output", "primary run failure" if mode in ("not_created", "failed_run_daemon") else "")
        if args[0] == "rm":
            assert args[3] == "owned-container-id" and mode != "wrong_owner"
            if mode == "remove_failure":
                raise subprocess.CalledProcessError(1, args, stderr="owned remove permission failure")
            return subprocess.CompletedProcess(args, 0, "owned-container-id", "")
        assert args[0] == "inspect" and check is False
        inspections.append(args)
        after = len(inspections) > 1
        if mode == "failed_run_daemon" or mode == ("daemon_after" if after else "daemon_before"):
            return subprocess.CompletedProcess(args, 1, "", "Cannot connect to the Docker daemon at unix:///owned/inert.sock.")
        if mode == ("permission_after" if after else "permission_before"):
            return subprocess.CompletedProcess(args, 1, "", "permission denied while trying to connect to the Docker daemon")
        if mode == "wrong_absent_name":
            return subprocess.CompletedProcess(args, 1, "[]", "Error response from daemon: No such object: some-other-container")
        if mode == "malformed_state":
            return subprocess.CompletedProcess(args, 0, "[]", "")
        if mode == "not_created" or (after and mode != "survived"):
            return subprocess.CompletedProcess(args, 1, "[]", "Error response from daemon: No such object: " + owned)
        return subprocess.CompletedProcess(args, 0, json.dumps([dict(Id="owned-container-id", Name="/" + owned,
            Config=dict(Labels={"audit.owner": "someone-else" if mode == "wrong_owner" else "batch11-bootstrap"}))]), "")
    monkeypatch.setitem(sys.modules, "batch11_bootstrap_fixture.postgres", types.SimpleNamespace(docker=docker))
    out = tmp_path / "output"
    monkeypatch.setattr(sys, "argv", ["linux_replay.py", "--runtime-root", str(tmp_path), "--out", str(out)])
    error = None
    try:
        load("linux_replay").main()
    except RuntimeError as failure:
        error = failure
    output = capsys.readouterr().out
    assert (error is None) is (mode == "removed"), "DOCKER_UNKNOWN_FALSE_GREEN: " + output
    assert (out / "execution.log").read_text().startswith("owned actual run output")
    if mode in ("not_created", "failed_run_daemon"):
        assert str(error) == "Linux replay failed; raw output preserved"
    if mode == "failed_run_daemon":
        assert any("cleanup" in note.lower() and "unverified" in note.lower() for note in error.__notes__)
    if mode not in ("removed", "not_created"):
        assert "OWNED_LINUX_REMOVED" not in output and "OWNED_LINUX_NOT_CREATED" not in output
        assert (out / "cleanup-unverified.json").is_file()
    elif mode == "removed":
        assert "OWNED_LINUX_REMOVED" in output
        assert len(inspections) == 2
    else:
        assert "OWNED_LINUX_NOT_CREATED" in output
        assert not any(args[0] == "rm" for args, _ in calls)


@pytest.mark.parametrize("mode", ["fresh", "ancestor_link", "dangling_leaf", "source_internal", "traversal", "inherited"])
def test_linux_output_refuses_alias_before_docker(tmp_path, monkeypatch, mode):
    calls = []
    def docker(*args, check=True):
        calls.append(args)
        if args[0] == "run":
            return subprocess.CompletedProcess(args, 0, "owned safe execution", "")
        assert args[0] == "inspect"
        return subprocess.CompletedProcess(args, 1, "[]", "error: no such object: " + args[1])
    monkeypatch.setitem(sys.modules, "batch11_bootstrap_fixture.postgres", types.SimpleNamespace(docker=docker))
    module = load("linux_replay")
    output = tmp_path / "fresh-output"
    target = output
    if mode == "ancestor_link":
        parent = tmp_path / "alias-parent"
        parent.symlink_to(tmp_path, target_is_directory=True)
        output = parent / "fresh-output"
    elif mode == "dangling_leaf":
        output = tmp_path / "alias-leaf"
        output.symlink_to(target, target_is_directory=True)
    elif mode == "source_internal":
        output = module.Path(__file__).resolve().parents[2] / "forbidden-owned-output"
        target = output
    elif mode == "traversal":
        output = tmp_path / "missing-parent" / ".." / "fresh-output"
    elif mode == "inherited":
        output.mkdir()
        (output / "preserved.txt").write_text("owned previous output")
    monkeypatch.setattr(sys, "argv", ["linux_replay.py", "--runtime-root", str(tmp_path), "--out", str(output)])
    if mode == "fresh":
        module.main()
        assert calls and (target / "execution.log").read_text() == "owned safe execution"
    else:
        with pytest.raises(ValueError, match="Fresh external nonsymlink output required"):
            module.main()
        assert calls == [], "SOURCE_OR_OUTPUT_ALIAS_LAUNCHED_DOCKER"
        assert not target.exists() or mode == "inherited"
        if mode == "inherited":
            assert (target / "preserved.txt").read_text() == "owned previous output"
