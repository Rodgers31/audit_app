"""Execute the manual acceptance guards offline, stopping before producer IO."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github/workflows/r2-acceptance.yml"
PRODUCER = REPO / "backend/scripts/r2_producer_acceptance.py"
APP_HEAD = "420cdc1887502940db32403fe26c6158789f9bc3"
APP_TREE = "093b3c321197943c0a647f1e763212982ee7cef4"
PRODUCER_SHA = "9124c3c8abad7b48c8ed78d580c01012662174fd1ca4b5bdd148cc0250a1478f"

# Only the final live run boundary is replaced. The real module's argument
# parser, main, guards and actual git subprocesses execute in each child.
# Frozen HEAD/tree use a real, self-contained owned Git fixture; the original
# deployment pins are checked separately. Linux/Python 3.12 are simulated;
# this is not intended-host/runtime parity or full producer acceptance.
OBSERVER = r'''
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
from unittest.mock import patch

def deny(*args, **kwargs):
    raise AssertionError("offline guard attempted socket IO")

socket.socket.connect = deny
socket.socket.connect_ex = deny
socket.create_connection = deny
script = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("offline_producer", script)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

def observed(args, repo, output):
    event = {"marker": "BATCH9_PDF_PIN_LIVE_BOUNDARY_STOPPED",
             "stage": args.stage, "arguments": sys.argv[2:]}
    with open(os.environ["OFFLINE_CALL_LOG"], "a") as stream:
        stream.write(json.dumps(event) + "\n")
    return {"status": "OFFLINE_GUARD_ACCEPTED", "stage": args.stage}

assert module.HEAD == os.environ["OFFLINE_SOURCE_HEAD"]
assert module.TREE == os.environ["OFFLINE_SOURCE_TREE"]
with patch.object(module, "HEAD", os.environ["OFFLINE_FIXTURE_HEAD"]), \
     patch.object(module, "TREE", os.environ["OFFLINE_FIXTURE_TREE"]), \
     patch.object(module, "run", observed), \
     patch.object(module.platform, "system", return_value="Linux"), \
     patch.object(module.sys, "version_info", (3, 12)):
    sys.exit(module.main(sys.argv[2:]))
'''


def workflow():
    return yaml.safe_load(WORKFLOW.read_text())


def live_step():
    return next(step for step in workflow()["jobs"]["verify"]["steps"]
                if step.get("name") == "Single official source pilot then complete retained PDF")


@pytest.fixture
def owned(tmp_path):
    app = tmp_path / "app"
    # No historical objects or network are required, including on depth-one CI.
    app.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=app, check=True)
    (app / "README.md").write_text("owned offline Git fixture\n")
    subprocess.run(["git", "add", "README.md"], cwd=app, check=True)
    for message in ("owned tree", "owned frozen head"):
        subprocess.run(["git", "-c", "user.name=Offline fixture", "-c",
                        "user.email=fixture@example.invalid", "commit", "--quiet",
                        "--allow-empty", "-m", message], cwd=app, check=True)
    fixture_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=app, text=True).strip()
    fixture_tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=app, text=True).strip()
    script = tmp_path / "acceptance-tools/backend/scripts/r2_producer_acceptance.py"
    script.parent.mkdir(parents=True)
    script.write_bytes(PRODUCER.read_bytes())
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    observer = bin_dir / "python"
    observer.write_text(f"#!{sys.executable}\n" + OBSERVER)
    observer.chmod(0o700)
    calls = tmp_path / "calls.jsonl"
    # Do not inherit provider credentials, application config or dotenv paths.
    env = {
        "PATH": str(bin_dir) + os.pathsep + os.defpath + ":/sbin",
        "GITHUB_WORKSPACE": str(tmp_path),
        "RUNNER_TEMP": str(tmp_path / "runner"),
        "OFFLINE_CALL_LOG": str(calls),
        "OFFLINE_SOURCE_HEAD": APP_HEAD,
        "OFFLINE_SOURCE_TREE": APP_TREE,
        "OFFLINE_FIXTURE_HEAD": fixture_head,
        "OFFLINE_FIXTURE_TREE": fixture_tree,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHON_DOTENV_DISABLED": "1",
    }
    return app, script, calls, env


def execute(owned, body=None):
    _, _, calls, env = owned
    shell = (live_step()["run"] if body is None else body).replace(APP_HEAD, env["OFFLINE_FIXTURE_HEAD"])
    result = subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", shell],
                            env=env, text=True, capture_output=True, timeout=30)
    events = [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
    return result, events


def test_current_reviewed_bytes_reach_both_offline_boundaries(owned):
    assert hashlib.sha256(PRODUCER.read_bytes()).hexdigest() == PRODUCER_SHA
    result, events = execute(owned)
    assert result.returncode == 0, result.stdout + result.stderr
    assert [event["stage"] for event in events] == ["pilot", "pdf"]
    assert all(event["marker"] == "BATCH9_PDF_PIN_LIVE_BOUNDARY_STOPPED" for event in events)
    assert result.stdout.count('"status": "OFFLINE_GUARD_ACCEPTED"') == 2


@pytest.mark.parametrize("mutation", ["changed", "empty", "absent"])
def test_unreviewed_or_missing_bytes_never_reach_producer(owned, mutation):
    _, script, _, _ = owned
    if mutation == "changed":
        script.write_bytes(script.read_bytes() + b"\n# unreviewed mutation\n")
    elif mutation == "empty":
        script.write_bytes(b"")
    else:
        script.unlink()
    result, events = execute(owned)
    assert result.returncode != 0
    assert events == []
    assert "OFFLINE_GUARD_ACCEPTED" not in result.stdout


def test_wrong_actual_checkout_never_reaches_live_boundary(owned):
    app, _, _, _ = owned
    subprocess.run(["git", "checkout", "--quiet", "--detach", "HEAD^"], cwd=app, check=True)
    result, events = execute(owned)
    assert result.returncode == 1
    assert json.loads(result.stdout) == {"status": "FAILED", "reason": "checkout_mismatch"}
    assert events == []


def test_dirty_frozen_checkout_never_reaches_live_boundary(owned):
    app, _, _, _ = owned
    with (app / "README.md").open("a") as stream:
        stream.write("\nowned dirty fixture\n")
    result, events = execute(owned)
    assert result.returncode == 1
    assert json.loads(result.stdout)["reason"] == "checkout_dirty"
    assert events == []


@pytest.mark.parametrize("old,new,reason", [
    (APP_HEAD, "main", "source_or_head_mismatch"),
    (APP_HEAD, "0" * 40, "source_or_head_mismatch"),
    ("--stage pilot", "--stage unsupported", "arguments_invalid"),
    ("--stage pilot", "--stage pilot --attempt 2", "arguments_invalid"),
    ("--allow-live-r2", "", "live_not_authorized"),
    ("--allow-official-worldbank", "", "publisher_fetch_not_authorized"),
    ("--expected-bucket audit-source-evidence-v1", "--expected-bucket other", "destination_mismatch"),
    ("--expected-account 6929fa03fad58c2f93c70196ec498c69", "--expected-account other", "destination_mismatch"),
    ("--expected-jurisdiction default", "--expected-jurisdiction eu", "destination_mismatch"),
    ("--expected-source-sha256 5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3",
     "--expected-source-sha256 " + "0" * 64, "source_or_head_mismatch"),
    ("--memory-budget-bytes 8589934592", "--memory-budget-bytes 0", "budget_mismatch"),
    ("--timeout-seconds 720", "--timeout-seconds NaN", "budget_mismatch"),
])
def test_unsupported_input_cannot_activate_live_calls(owned, old, new, reason):
    body = live_step()["run"]
    assert old in body
    result, events = execute(owned, body.replace(old, new))
    assert result.returncode == 1
    assert json.loads(result.stdout) == {"status": "FAILED", "reason": reason}
    assert events == []


@pytest.mark.parametrize("approval", ["", "NO", "RUN_BOUNDED_R2_ACCEPTANCE ", "RUN_BOUNDED_R2_ACCEPTANCE"])
def test_actual_confirmation_guard(owned, approval):
    steps = workflow()["jobs"]["verify"]["steps"]
    body = next(step["run"] for step in steps if step.get("name") == "Refuse unapproved manual invocation")
    owned[3]["APPROVAL_TEXT"] = approval
    result, events = execute(owned, body=body)
    assert (result.returncode == 0) == (approval == "RUN_BOUNDED_R2_ACCEPTANCE")
    assert events == []


def test_workflow_retains_dispatch_and_credential_boundaries():
    doc = workflow()
    # PyYAML's YAML 1.1 resolver reads unquoted `on` as True.
    assert set(doc.get("on", doc.get(True))) == {"workflow_dispatch"}
    assert doc["permissions"] == {"contents": "read"}
    assert doc["concurrency"]["cancel-in-progress"] is False
    job = doc["jobs"]["verify"]
    assert job["timeout-minutes"] == 15
    checkouts = [step["with"] for step in job["steps"] if step.get("uses") == "actions/checkout@v5"]
    assert checkouts == [{"ref": APP_HEAD, "path": "app"},
                         {"ref": "${{ github.sha }}", "path": "acceptance-tools"}]
    assert live_step()["timeout-minutes"] == 12
    secret_steps = [step for step in job["steps"] if "secrets." in json.dumps(step)]
    assert secret_steps == [live_step()]
    assert set(live_step()["env"]) == {"RECEIPT_R2_ACCESS_KEY_ID", "RECEIPT_R2_SECRET_ACCESS_KEY",
                                       "RECEIPT_R2_CONTROL_TOKEN"}


def test_pdf_pin_receipts_have_current_generators():
    receipts = list((REPO / "docs/admin/implementation/batch9-pdf-pin-evidence").glob("*.json"))
    assert receipts, "No PDF pin receipts examined"
    for path in receipts:
        receipt = json.loads(path.read_text())
        generator = REPO / receipt["generated_by"]
        if hashlib.sha256(generator.read_bytes()).hexdigest() != receipt["generator_sha256"]:
            generator = path.parent / "historical-generators" / ("record_check_" + receipt["generator_sha256"] + ".py")
        assert hashlib.sha256(generator.read_bytes()).hexdigest() == receipt["generator_sha256"], path
        status = receipt.get("verification_exit_status", receipt["exit_status"])
        assert receipt["verdict"] == ("PASS" if status == 0 else "FAILED"), path
