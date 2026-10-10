"""Source binding in the supported v2 recorder rejects external source bytes."""
import importlib.util
import json
from pathlib import Path
import subprocess
import os
import signal
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[3]
PACKET = ROOT / "docs/admin/implementation/batch11-issue-611-evidence"


def recorder():
    spec = importlib.util.spec_from_file_location("issue611_record_v2_controls", PACKET / "record_v2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(tmp_path, monkeypatch):
    root = tmp_path / "owned-source"
    root.mkdir()
    (root / "owned.txt").write_text("owned")
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True, timeout=10, env={"PATH": os.defpath, "HOME": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"})
    subprocess.run(["git", "-C", str(root), "add", "owned.txt"], check=True, capture_output=True, timeout=10, env={"PATH": os.defpath, "HOME": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"})
    module = recorder()
    monkeypatch.setattr(module, "ROOT", root)
    return module, root


def test_normal_source_inventory_reads_only_owned_ordinary_files(tmp_path, monkeypatch):
    module, root = fixture(tmp_path, monkeypatch)
    assert module.inventory() == {"owned.txt": module.digest(root / "owned.txt")}


@pytest.mark.parametrize("directory", [False, True])
def test_source_link_refuses_before_hashing_external_bytes(tmp_path, monkeypatch, directory):
    module, root = fixture(tmp_path, monkeypatch)
    outside = tmp_path / "external"
    outside.mkdir()
    (outside / "canary.txt").write_text("INERT_EXTERNAL_CANARY")
    if directory:
        (root / "linked").symlink_to(outside, target_is_directory=True)
    else:
        (root / "linked.txt").symlink_to(outside / "canary.txt")
    with pytest.raises(ValueError, match="Ordinary source files"):
        module.inventory()
    assert (outside / "canary.txt").read_text() == "INERT_EXTERNAL_CANARY"


def test_source_file_deletion_refuses_instead_of_omitting_identity(tmp_path, monkeypatch):
    module, root = fixture(tmp_path, monkeypatch)
    (root / "owned.txt").unlink()
    with pytest.raises(ValueError, match="Ordinary source files"):
        module.inventory()


@pytest.mark.parametrize("port", [True, 55531, 5432, "55545", 0])
def test_recorder_refuses_other_lane_or_malformed_owned_port(port):
    with pytest.raises(ValueError, match="owned PostgreSQL port"):
        recorder().environment(port)


@pytest.mark.parametrize("resist", [False, True])
def test_successful_parent_descendant_is_closed_before_acceptance(tmp_path, resist):
    module = recorder()
    ready, marker = tmp_path / "worker", tmp_path / "delayed-effect"
    code = """import os,signal,sys,time
from pathlib import Path
if os.fork() == 0:
    sink = os.open(os.devnull, os.O_RDWR)
    for fd in (0,1,2): os.dup2(sink, fd)
    if sys.argv[3] == 'True': signal.signal(signal.SIGTERM, signal.SIG_IGN)
    Path(sys.argv[1]).write_text(str(os.getpid()))
    time.sleep(4)
    Path(sys.argv[2]).write_text('INERT_DELAYED_EFFECT')
    os._exit(0)
"""
    child = subprocess.Popen([sys.executable, "-c", code, str(ready), str(marker), str(resist)],
                             env={"PATH": os.defpath, "HOME": "/dev/null"},
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        child.communicate(timeout=5)
        assert child.returncode == 0
        until = time.monotonic() + 2
        while not ready.exists() and time.monotonic() < until:
            time.sleep(0.01)
        assert ready.exists()
        assert module.group_alive(child.pid)
        lifecycle = module.cleanup_group(child.pid)
        assert lifecycle["survived_parent"] is True
        assert lifecycle["absent"] is True
        assert lifecycle["signals"] == ([15, 9] if resist else [15])
        assert module.group_alive(child.pid) is False
        assert not marker.exists()
    finally:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


@pytest.mark.parametrize("unexpected,interleaved", [(False, False), (True, False), (True, True)])
def test_actual_pytest_stdout_prevents_junit_xpass_false_acceptance(tmp_path, unexpected, interleaved):
    source = tmp_path / "tests" / "test_outcome.py"
    source.parent.mkdir()
    # A parameter named XPASS must remain an ordinary passing baseline.
    source.write_text("import pytest\n" + (
        '@pytest.mark.xfail(strict=False, reason="INERT_FALSE_GREEN")\n' if unexpected else
        '@pytest.mark.parametrize("label", ["XPASS"])\n'
    ) + ("def test_outcome():\n" if unexpected else "def test_outcome(label):\n")
        + ('    print("INERT_INTERLEAVED_OUTPUT")\n' if interleaved else "") + "    assert True\n")
    xml = tmp_path / "actual.xml"
    completed = subprocess.run([sys.executable, "-B", "-m", "pytest", "--confcutdir=tests",
        "-p", "no:cacheprovider", "tests/test_outcome.py", "-v", "-s", "--color=yes",
        f"--basetemp={tmp_path / 'tmp'}", f"--junitxml={xml}"], cwd=tmp_path,
        env={"PATH": os.defpath, "HOME": "/dev/null", "PYTHON_DOTENV_DISABLED": "1",
             "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, timeout=20)
    assert completed.returncode == 0
    module = recorder()
    assert module.junit_cases(xml) == [{"id": "tests.test_outcome::test_outcome" +
                                       ("" if unexpected else "[XPASS]"), "state": "passed"}]
    assert bool(module.unexpected_passes(completed.stdout)) is unexpected


def test_actual_successful_pytest_parent_with_unfinished_child_cannot_certify_completion(tmp_path):
    root = tmp_path / "source"
    tools = root / "docs/admin/implementation/batch11-issue-611-evidence"
    tools.mkdir(parents=True)
    for name in ("record_v2.py", "verify_run_v2.py"):
        (tools / name).write_bytes((PACKET / name).read_bytes())
    test = root / "backend/tests/test_incomplete.py"
    test.parent.mkdir(parents=True)
    test.write_text('''import os,subprocess,sys
from pathlib import Path
def test_incomplete():
    out=Path(__file__).resolve().parents[3]
    worker="import sys,time;from pathlib import Path;time.sleep(8);Path(sys.argv[1]).write_text('INERT_DELAYED_EFFECT');time.sleep(20)"
    child=subprocess.Popen([sys.executable,"-c",worker,str(out/"marker")],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    (out/"worker").write_text(str(child.pid)+","+str(os.getpgrp()))
    assert True
''')
    env = {"PATH": os.defpath, "HOME": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_AUTHOR_NAME": "Owned control", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Owned control", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
    for args in (["init", "-q"], ["add", "."], ["-c", "commit.gpgsign=false", "commit", "-qm", "Freeze completion control"]):
        subprocess.run(["git", *args], cwd=root, env=env, capture_output=True, timeout=10, check=True)
    output = tmp_path / "recorded"
    done = subprocess.run([sys.executable, "-B", str(tools / "record_v2.py"), "--python", sys.executable,
        "--out", str(output), "tests/test_incomplete.py"], cwd=root, env=env, capture_output=True, timeout=30)
    receipt = json.loads((output / "run.json").read_text())
    _, group = map(int, (tmp_path / "worker").read_text().split(","))
    try:
        assert receipt["child_exit"] == 0 and receipt["cases"] == [{"id": "tests.test_incomplete::test_incomplete", "state": "passed"}]
        assert receipt["process_group"]["survived_parent"] is True
        assert receipt["process_group"]["absent"] is True and recorder().group_alive(group) is False
        assert not (tmp_path / "marker").exists()
        assert done.returncode == 1 and receipt["verdict"] == "NOT_ACCEPTED"
        # A coherent false verdict cannot hide recorded unfinished work.
        receipt.update(verdict="PASS", verification_exit=0)
        (output / "run.json").write_text(json.dumps(receipt, indent=2) + "\n")
        for optimized in (False, True):
            read = subprocess.run([sys.executable, *(["-O"] if optimized else []), str(tools / "verify_run_v2.py"),
                str(output / "run.json")], cwd=root, env=env, capture_output=True, timeout=20)
            assert read.returncode == 1 and b"Closed owned process group readback required" in read.stderr
    finally:
        try:
            os.killpg(group, signal.SIGKILL)
        except ProcessLookupError:
            pass
