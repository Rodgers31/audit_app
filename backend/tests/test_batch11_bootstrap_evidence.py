"""Current packet acceptance executes real pytest and refuses malformed proof."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
LANE = Path("docs/admin/implementation/batch11-issue-603-evidence")
RECORDER = LANE / "record_v2.py"


@pytest.fixture(scope="module")
def recorded(tmp_path_factory):
    home = tmp_path_factory.mktemp("batch11-packet")
    source = home / "source"
    (source / LANE).mkdir(parents=True)
    for name in ("publish.py", "verify.py"):
        shutil.copyfile(ROOT / LANE / name, source / LANE / name)
    shutil.copyfile(ROOT / RECORDER, source / RECORDER)
    (source / "backend/tests").mkdir(parents=True)
    (source / "backend/tests/test_owned.py").write_text(
        "import pytest\n@pytest.mark.parametrize('value',[1,2])\ndef test_owned(value):\n    assert value > 0\n")
    env = dict(PATH=os.environ["PATH"], PYTHON_DOTENV_DISABLED="1")
    for command in (["git", "init", "-q"], ["git", "add", "."],
            ["git", "-c", "user.name=Owned Fixture", "-c", "user.email=owned@example.invalid", "commit", "-qm", "owned fixture"]):
        subprocess.run(command, cwd=source, env=env, check=True, capture_output=True, timeout=10)
    packet = home / "packet"
    command = [sys.executable, str(source / LANE / "publish.py"), "--root", str(source),
        "--out", str(packet), "tests/test_owned.py"]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return source, packet, env


@pytest.mark.parametrize("optimized", [False, True])
@pytest.mark.parametrize("fault", ["valid", "bool_exit", "missing_runtime", "wrong_entry", "bool_counts", "empty_cases", "internal", "symlink",
    "null_timestamp", "unordered_time", "naive_timestamp", "invalid_environment", "enabled_dispatch", "secret_presence", "unredacted_input", "wrong_portable_entrypoint",
    "missing_cleanup", "bool_pid", "wrong_group", "surviving_group", "missing_absence", "cleanup_signal", "wrong_capture_schema", "historical_recorder",
    "missing_xpass_count", "bool_optimization"])
def test_packet_types_outputs_and_execution_identity(recorded, tmp_path, optimized, fault):
    source, original, env = recorded
    packet = tmp_path / "copy"
    shutil.copytree(original, packet)
    index = json.loads((packet / "INDEX.json").read_text())
    receipt = json.loads((packet / "receipt.json").read_text())
    if fault == "bool_exit":
        receipt["child_exit"] = False
    elif fault == "missing_runtime":
        receipt.pop("runtime")
    elif fault == "wrong_entry":
        receipt["command"][1:3] = ["-m", "fake_cli"]
    elif fault == "bool_counts":
        index["testcases"]["counts"]["failed"] = False
    elif fault == "empty_cases":
        index["testcases"]["identities"] = []
    elif fault == "null_timestamp":
        receipt["started_at"] = None
    elif fault == "unordered_time":
        receipt["ended_at"] = "2000-01-01T00:00:00+00:00"
    elif fault == "naive_timestamp":
        receipt["started_at"] = "2000-01-01T00:00:00"
    elif fault == "invalid_environment":
        receipt["environment"] = None
    elif fault == "enabled_dispatch":
        receipt["environment"]["ENABLE_ETL_SCHEDULER"] = "true"
    elif fault == "secret_presence":
        receipt["secret_environment_present"]["DATABASE_URL"] = True
    elif fault == "unredacted_input":
        receipt["environment"]["DATABASE_URL"] = "inert-unredacted-input"
        receipt["secret_environment_present"]["DATABASE_URL"] = True
    elif fault == "wrong_portable_entrypoint":
        index["portable_command"] = ["<python>", "-m", "fake_cli"]
    elif fault == "missing_cleanup":
        receipt.pop("process_cleanup")
    elif fault == "bool_pid":
        receipt["pid"] = True
    elif fault == "wrong_group":
        receipt["process_cleanup"]["group"] += 1
    elif fault == "surviving_group":
        receipt["process_cleanup"]["survivors_detected"] = True
    elif fault == "missing_absence":
        receipt["process_cleanup"]["group_absent"] = False
    elif fault == "cleanup_signal":
        receipt["process_cleanup"]["signals"] = ["SIGTERM"]
    elif fault == "wrong_capture_schema":
        receipt["capture_schema"] = True
    elif fault == "historical_recorder":
        receipt["generated_by"] = "docs/admin/implementation/batch10-readiness-evidence/record.py"
    elif fault == "missing_xpass_count":
        index["testcases"]["counts"].pop("xpassed")
    elif fault == "bool_optimization":
        receipt["runtime"]["recorder_optimization"] = True
    elif fault == "symlink":
        (packet / "receipt.txt").unlink()
        (packet / "receipt.txt").symlink_to(original / "receipt.txt")
    if fault not in {"valid", "symlink"}:
        (packet / "receipt.json").write_text(json.dumps(receipt))
        index["files"]["receipt.json"] = hashlib.sha256((packet / "receipt.json").read_bytes()).hexdigest()
        (packet / "INDEX.json").write_text(json.dumps(index))
    if fault == "internal":
        destination = source / "forbidden"
        # No source mutation is needed: the forbidden target can be absent.
        target = destination / "INDEX.json"
    else:
        target = packet / "INDEX.json"
    command = [sys.executable, *( ["-O"] if optimized else []), str(source / LANE / "verify.py"),
        "--root", str(source), "--index", str(target)]
    before = subprocess.check_output(["git", "status", "--porcelain"], cwd=source, env=env)
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
    assert (result.returncode == 0) is (fault == "valid"), "MALFORMED_PACKET_ACCEPTED: " + result.stdout + result.stderr
    after = subprocess.check_output(["git", "status", "--porcelain"], cwd=source, env=env)
    assert before == after == b""
    if fault == "valid":
        assert json.loads(result.stdout)["counts"]["passed"] == 2


def test_publisher_refuses_inherited_or_source_output(recorded):
    source, packet, env = recorded
    original = (packet / "INDEX.json").read_bytes()
    for output in (packet, source / "forbidden"):
        result = subprocess.run([sys.executable, str(source / LANE / "publish.py"), "--root", str(source),
            "--out", str(output), "tests/test_owned.py"], env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode != 0 and "Fresh external nonsymlink" in result.stderr
    assert (packet / "INDEX.json").read_bytes() == original


@pytest.mark.parametrize("optimized", [False, True])
@pytest.mark.parametrize("mode", ["xpass", "xpass_with_output", "pass_with_output"])
def test_actual_pytest_unexpected_success_cannot_certify_packet(recorded, tmp_path, optimized, mode):
    """Actual pytest XML omits non-strict XPASS; the raw outcome must also count."""
    source, _, env = recorded
    test = source / "backend/tests/test_actual_outcome.py"
    marked = mode != "pass_with_output"
    content = "import pytest\n"
    if marked:
        content += '@pytest.mark.xfail(strict=False, reason="owned unexpected-success control")\n'
    content += "def test_actual_outcome():\n"
    if mode.endswith("with_output"):
        content += '    print("owned output before the actual outcome")\n'
    content += "    assert 1 == 1\n"
    test.write_text(content)
    subprocess.run(["git", "add", "."], cwd=source, env=env, check=True, capture_output=True, timeout=10)
    subprocess.run(["git", "-c", "user.name=Owned Fixture", "-c", "user.email=owned@example.invalid",
                    "commit", "--allow-empty", "-qm", "actual outcome fixture"],
                   cwd=source, env=env, check=True, capture_output=True, timeout=10)
    packet = tmp_path / "actual-packet"
    command = [sys.executable, *(["-O"] if optimized else []), str(source / LANE / "publish.py"),
               "--root", str(source), "--out", str(packet), "tests/test_actual_outcome.py"]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    receipt = json.loads((packet / "receipt.json").read_text())
    assert receipt["child_exit"] == 0 and receipt["source_stable"] is True
    assert receipt["runtime"]["recorder_optimization"] == int(optimized)
    raw = (packet / "receipt.txt").read_text()
    if marked:
        assert "1 xpassed" in raw and "XPASS" in raw
        assert result.returncode != 0, "ACTUAL_XPASS_FALSE_GREEN: " + result.stdout + result.stderr
        assert "XPASS" in result.stderr or "Unexpected pytest success" in result.stderr
    else:
        assert "1 passed" in raw
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout.splitlines()[-1])["counts"]["passed"] == 1


@pytest.mark.parametrize("optimized", [False, True])
@pytest.mark.parametrize("inherit_output", [False, True])
def test_actual_surviving_owned_child_cannot_certify_packet(recorded, tmp_path, optimized, inherit_output):
    """An exited pytest parent cannot certify an owned group that still runs."""
    source, _, env = recorded
    pid_path = tmp_path / "owned-child.pid"
    test = source / "backend/tests/test_actual_owned_child.py"
    output_arguments = "" if inherit_output else ", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL"
    test.write_text(
        "import pathlib, subprocess, sys\n"
        "def test_actual_owned_child():\n"
        "    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], "
        "stdin=subprocess.DEVNULL" + output_arguments + ")\n"
        f"    pathlib.Path({str(pid_path)!r}).write_text(str(child.pid))\n"
        "    assert child.pid > 0\n")
    subprocess.run(["git", "add", "."], cwd=source, env=env, check=True, capture_output=True, timeout=10)
    subprocess.run(["git", "-c", "user.name=Owned Fixture", "-c", "user.email=owned@example.invalid",
                    "commit", "--allow-empty", "-qm", "actual owned child fixture"],
                   cwd=source, env=env, check=True, capture_output=True, timeout=10)
    packet = tmp_path / "actual-child-packet"
    result = subprocess.run([sys.executable, *(["-O"] if optimized else []), str(source / LANE / "publish.py"),
        "--root", str(source), "--out", str(packet), "tests/test_actual_owned_child.py"],
        env=env, capture_output=True, text=True, timeout=30)
    child = int(pid_path.read_text())
    group = None
    try:
        try:
            group = os.getpgid(child)
        except ProcessLookupError:
            pass
        assert (packet / "receipt.json").is_file(), result.stdout + result.stderr
        receipt = json.loads((packet / "receipt.json").read_text())
        print(json.dumps(dict(owned_child=child, surviving_group=group,
            publisher_exit=result.returncode, recorded_exit=receipt["child_exit"], verdict=receipt["verdict"])))
        assert receipt["child_exit"] == 0 and receipt["source_stable"] is True
        assert result.returncode != 0, "ACTUAL_ORPHAN_FALSE_GREEN: " + result.stdout + result.stderr
        assert group is None, "OWNED_CHILD_STILL_ALIVE"
        cleanup = receipt["process_cleanup"]
        assert cleanup["survivors_detected"] is True and cleanup["group_absent"] is True
    finally:
        if group is not None:
            assert group != os.getpgrp(), "Refuse cleanup of the test runner group"
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    os.killpg(group, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.05)
            else:
                pytest.fail("Owned toy child group cleanup did not read back absent")


@pytest.mark.parametrize("optimized", [False, True])
def test_actual_deadline_records_owned_group_absence(recorded, tmp_path, optimized):
    source, _, env = recorded
    test = source / "backend/tests/test_actual_deadline.py"
    test.write_text("import time\ndef test_actual_deadline():\n    time.sleep(30)\n")
    subprocess.run(["git", "add", "."], cwd=source, env=env, check=True, capture_output=True, timeout=10)
    subprocess.run(["git", "-c", "user.name=Owned Fixture", "-c", "user.email=owned@example.invalid",
                    "commit", "--allow-empty", "-qm", "actual command deadline fixture"],
                   cwd=source, env=env, check=True, capture_output=True, timeout=10)
    packet = tmp_path / "deadline-packet"
    result = subprocess.run([sys.executable, *(["-O"] if optimized else []), str(source / LANE / "publish.py"),
        "--root", str(source), "--out", str(packet), "--timeout", "1", "tests/test_actual_deadline.py"],
        env=env, capture_output=True, text=True, timeout=25)
    assert (packet / "receipt.json").is_file(), result.stdout + result.stderr
    receipt = json.loads((packet / "receipt.json").read_text())
    assert result.returncode != 0 and receipt["verdict"] == "FAIL" and receipt["timed_out"] is True
    assert receipt["source_stable"] is True and receipt["child_exit"] != 0
    cleanup = receipt["process_cleanup"]
    assert cleanup["survivors_detected"] is True and cleanup["group_absent"] is True
    assert cleanup["signals"] == ["SIGTERM"]
    with pytest.raises(ProcessLookupError):
        os.killpg(cleanup["group"], 0)


@pytest.mark.parametrize("optimized", [False, True])
@pytest.mark.parametrize("fault", ["source_leaf_link", "source_parent_link", "dotenv", "output_parent_link", "output_internal", "output_inherited"])
def test_current_recorder_refuses_source_or_output_escape(recorded, tmp_path, optimized, fault):
    source, _, env = recorded
    marker = tmp_path / "forbidden-child-start"
    consumed = tmp_path / "external-toy-source.py"
    consumed.write_text("OWNED_TOY_SECRET = 'not-a-real-secret'\n")
    raw = tmp_path / "record.json"
    link = None
    if fault == "source_leaf_link":
        link = source / "source-escape.py"
        link.symlink_to(consumed)
    elif fault == "source_parent_link":
        link = source / "source-parent"
        link.symlink_to(tmp_path, target_is_directory=True)
    elif fault == "dotenv":
        link = source / ".env.runtime-owned"
        link.write_text("OWNED_TOY_SECRET=not-a-real-secret\n")
    elif fault == "output_parent_link":
        link = tmp_path / "output-parent"
        link.symlink_to(tmp_path, target_is_directory=True)
        raw = link / "record.json"
    elif fault == "output_internal":
        raw = source / "forbidden-record.json"
    elif fault == "output_inherited":
        raw.write_text("original-owned-output")
    before = consumed.read_bytes()
    try:
        result = subprocess.run([sys.executable, *(["-O"] if optimized else []), str(source / RECORDER),
            "--root", str(source), "--output", str(raw), "--", sys.executable, "-c",
            f"from pathlib import Path; Path({str(marker)!r}).write_text('started')"],
            env=env, capture_output=True, text=True, timeout=15)
        assert result.returncode != 0 and not marker.exists(), result.stdout + result.stderr
        assert consumed.read_bytes() == before and not raw.with_suffix(".txt").exists()
        assert "not-a-real-secret" not in result.stdout + result.stderr
        if fault == "output_inherited":
            assert raw.read_text() == "original-owned-output"
        else:
            assert not raw.exists()
    finally:
        if link is not None:
            link.unlink()


@pytest.mark.parametrize("optimized", [False, True])
def test_actual_child_uses_explicit_minimal_environment(recorded, tmp_path, optimized):
    source, _, env = recorded
    test = source / "backend/tests/test_actual_environment.py"
    test.write_text(
        "import os\ndef test_actual_environment():\n"
        "    assert os.environ['PYTHON_DOTENV_DISABLED'] == '1'\n"
        "    assert os.environ['PYTHONDONTWRITEBYTECODE'] == '1'\n"
        "    for name in ('AUTO_SEEDER_ENABLED', 'AUTO_WARMUP_ENABLED', 'ENABLE_ETL_SCHEDULER'):\n"
        "        assert os.environ[name] == 'false'\n"
        "    for name in ('OWNED_AMBIENT_CANARY', 'SUPABASE_SERVICE_ROLE_KEY', 'HOME'):\n"
        "        assert name not in os.environ\n")
    subprocess.run(["git", "add", "."], cwd=source, env=env, check=True, capture_output=True, timeout=10)
    subprocess.run(["git", "-c", "user.name=Owned Fixture", "-c", "user.email=owned@example.invalid",
                    "commit", "--allow-empty", "-qm", "actual minimal environment fixture"],
                   cwd=source, env=env, check=True, capture_output=True, timeout=10)
    packet = tmp_path / "environment-packet"
    inherited = {**env, "OWNED_AMBIENT_CANARY": "inert-owned-canary", "SUPABASE_SERVICE_ROLE_KEY": "inert-owned-key",
        "AUTO_SEEDER_ENABLED": "true", "AUTO_WARMUP_ENABLED": "true", "ENABLE_ETL_SCHEDULER": "true"}
    result = subprocess.run([sys.executable, *(["-O"] if optimized else []), str(source / LANE / "publish.py"),
        "--root", str(source), "--out", str(packet), "tests/test_actual_environment.py"],
        env=inherited, capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.splitlines()[-1])["counts"]["passed"] == 1
    assert "inert-owned-canary" not in (packet / "receipt.json").read_text()
