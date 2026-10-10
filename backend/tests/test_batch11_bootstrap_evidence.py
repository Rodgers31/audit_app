"""Current packet acceptance executes real pytest and refuses malformed proof."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
LANE = Path("docs/admin/implementation/batch11-issue-603-evidence")
RECORDER = Path("docs/admin/implementation/batch10-readiness-evidence/record.py")


@pytest.fixture(scope="module")
def recorded(tmp_path_factory):
    home = tmp_path_factory.mktemp("batch11-packet")
    source = home / "source"
    (source / LANE).mkdir(parents=True)
    (source / RECORDER.parent).mkdir(parents=True)
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
    "null_timestamp", "unordered_time", "naive_timestamp", "invalid_environment", "enabled_dispatch", "secret_presence", "unredacted_input", "wrong_portable_entrypoint"])
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
