"""Exercise the evidence CLI with real pytest output and disposable Git inputs."""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

VERIFIER = (
    Path(__file__).resolve().parents[2]
    / "docs/admin/implementation/batch10-imf-evidence/verify_evidence.py"
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def evidence_package(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    replay = tmp_path / "replay"
    replay.mkdir()
    packet = checkout / "docs/admin/implementation/batch10-imf-evidence"
    packet.mkdir(parents=True)
    generator = packet / "run_evidence.py"
    generator.write_text("# synthetic generator identity\n")
    entry = packet / "pytest_entry.py"
    entry.write_text(
        "import sys, pytest\nraise SystemExit(pytest.main(sys.argv[1:]))\n"
    )
    test = checkout / "test_control.py"
    test.write_text("def test_control():\n    assert 1 + 1 == 2\n")
    env = {
        "PATH": os.defpath,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHON_DOTENV_DISABLED": "1",
        "DATABASE_URL": "sqlite:///" + str(replay / "batch10-imf-import.sqlite"),
    }
    command = [
        sys.executable,
        "-B",
        str(entry),
        "-p",
        "no:cacheprovider",
        "-q",
        str(test),
        "--junitxml=" + str(replay / "cases.xml"),
    ]
    began = datetime.now(timezone.utc).isoformat()
    child = subprocess.run(
        command, cwd=checkout, env=env, capture_output=True, text=True, timeout=30
    )
    assert child.returncode == 0, child.stdout + child.stderr
    (replay / "raw.log").write_text(child.stdout + child.stderr)
    (artifacts / "control.log").write_text(child.stdout + child.stderr)
    manifest = checkout / "docs/admin/implementation/batch10-imf-evidence/manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "schema": 1,
                "issue": 595,
                "artifacts": [
                    {"path": "control.log", "sha256": digest(artifacts / "control.log")}
                ],
                "runs": [],
            }
        )
    )

    def git(*args):
        return subprocess.check_output(
            ["git", "-c", "core.hooksPath=/dev/null", "-C", str(checkout), *args],
            text=True,
        ).strip()

    git("init", "-q")
    git("add", ".")
    git(
        "-c",
        "user.name=Batch10 fixture",
        "-c",
        "user.email=batch10@example.invalid",
        "commit",
        "-qm",
        "synthetic evidence inputs",
    )
    state = {
        "head": git("rev-parse", "HEAD"),
        "tree": git("rev-parse", "HEAD^{tree}"),
        "status": git("status", "--porcelain", "--untracked-files=all"),
        "sha256": {
            name: digest(checkout / name) for name in git("ls-files").splitlines()
        },
    }
    receipt = {
        "generated_by": str(generator.relative_to(checkout)),
        "generator_sha256": digest(generator),
        "entry_sha256": digest(entry),
        "command": command,
        "environment": env,
        "runtime": sys.version,
        "platform": sys.platform,
        "checkout": str(checkout),
        "started_at": began,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "start": state,
        "end": json.loads(json.dumps(state)),
        "source_stable": True,
        "child_exit": 0,
        "verification_exit": 0,
        "outputs": {name: digest(replay / name) for name in ("raw.log", "cases.xml")},
    }
    return checkout, artifacts, replay, receipt


def verify(package, optimized):
    checkout, artifacts, replay, receipt = package
    path = replay / "receipt.json"
    path.write_text(json.dumps(receipt))
    return subprocess.run(
        [sys.executable, "-B"]
        + (["-O"] if optimized else [])
        + [str(VERIFIER), str(checkout), str(artifacts), str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize("optimized", [False, True])
def test_evidence_accepts_real_executed_control(evidence_package, optimized):
    result = verify(evidence_package, optimized)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["current_checked"] is True


@pytest.mark.parametrize("optimized", [False, True])
def test_evidence_rejects_real_all_skipped_execution(evidence_package, optimized):
    checkout, _, replay, receipt = evidence_package
    test = checkout / "test_control.py"
    test.write_text(
        'import pytest\n@pytest.mark.skip(reason="synthetic prerequisite absent")\n'
        'def test_control():\n    raise RuntimeError("body must not execute")\n'
    )
    child = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-q",
            str(test),
            "--junitxml=" + str(replay / "cases.xml"),
        ],
        cwd=checkout,
        env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert child.returncode == 0, child.stdout + child.stderr
    assert "1 skipped" in child.stdout
    (replay / "raw.log").write_text(child.stdout + child.stderr)
    state = receipt["start"]
    state["sha256"]["test_control.py"] = digest(test)
    state["status"] = subprocess.check_output(
        ["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=all"],
        text=True,
    ).strip()
    receipt["end"] = json.loads(json.dumps(state))
    receipt["outputs"] = {
        name: digest(replay / name) for name in ("raw.log", "cases.xml")
    }
    result = verify(evidence_package, optimized)
    assert result.returncode != 0, result.stdout


@pytest.mark.parametrize("optimized", [False, True])
@pytest.mark.parametrize(
    "mutation",
    [
        "missing_inputs",
        "missing_outputs",
        "fake_counts",
        "wrong_status",
        "source_drift",
        "output_drift",
        "empty_case_inventory",
        "failed_cases",
    ],
)
def test_evidence_rejects_incomplete_or_changed_execution(
    evidence_package, optimized, mutation
):
    checkout, _, replay, receipt = evidence_package
    if mutation == "missing_inputs":
        receipt["start"]["sha256"] = {}
        receipt["end"]["sha256"] = {}
    elif mutation == "missing_outputs":
        receipt["outputs"] = {}
    elif mutation == "wrong_status":
        receipt["start"]["status"] = "synthetic changed state"
        receipt["end"]["status"] = "synthetic changed state"
    elif mutation == "source_drift":
        (checkout / "generator.py").write_text("# changed\n")
    elif mutation == "output_drift":
        (replay / "raw.log").write_text("changed\n")
    else:
        body = {
            "fake_counts": '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0" /></testsuites>',
            "empty_case_inventory": '<testsuites><testsuite tests="0" failures="0" errors="0" skipped="0" /></testsuites>',
            "failed_cases": '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="failed"><failure>failed</failure></testcase></testsuite></testsuites>',
        }[mutation]
        (replay / "cases.xml").write_text(body)
        receipt["outputs"]["cases.xml"] = digest(replay / "cases.xml")
    result = verify(evidence_package, optimized)
    assert result.returncode != 0, result.stdout


@pytest.mark.parametrize("optimized", [False, True])
@pytest.mark.parametrize(
    "mutation",
    [
        "child_bool",
        "verification_bool",
        "stability_string",
        "wrong_generator",
        "wrong_entry",
        "missing_command",
        "missing_runtime",
        "missing_environment",
        "missing_started_at",
        "missing_ended_at",
        "missing_entry",
        "empty_command",
        "runtime_bool",
        "environment_bool",
        "reversed_time",
        "naive_time",
        "wrong_command_entry",
        "wrong_junit_destination",
        "manifest_schema_bool",
    ],
)
def test_evidence_rejects_malformed_execution_provenance(
    evidence_package, optimized, mutation
):
    checkout, _, _, receipt = evidence_package
    if mutation.startswith("missing_"):
        receipt.pop({"missing_entry": "entry_sha256"}.get(mutation, mutation[8:]))
    elif mutation == "child_bool":
        receipt["child_exit"] = False
    elif mutation == "verification_bool":
        receipt["verification_exit"] = False
    elif mutation == "stability_string":
        receipt["source_stable"] = "false"
    elif mutation == "wrong_generator":
        receipt["generated_by"] = "test_control.py"
        receipt["generator_sha256"] = digest(checkout / "test_control.py")
    elif mutation == "wrong_entry":
        receipt["entry_sha256"] = digest(checkout / "test_control.py")
    elif mutation == "empty_command":
        receipt["command"] = []
    elif mutation == "runtime_bool":
        receipt["runtime"] = True
    elif mutation == "environment_bool":
        receipt["environment"] = False
    elif mutation == "reversed_time":
        receipt["ended_at"] = "2000-01-01T00:00:00+00:00"
    elif mutation == "naive_time":
        receipt["started_at"] = "2000-01-01T00:00:00"
    elif mutation == "wrong_command_entry":
        receipt["command"][2] = str(checkout / "test_control.py")
    elif mutation == "wrong_junit_destination":
        receipt["command"][-1] = "--junitxml=/unowned/cases.xml"
    else:
        path = checkout / "docs/admin/implementation/batch10-imf-evidence/manifest.json"
        manifest = json.loads(path.read_text())
        manifest["schema"] = True
        path.write_text(json.dumps(manifest))
        for state in (receipt["start"], receipt["end"]):
            state["sha256"][str(path.relative_to(checkout))] = digest(path)
            state["status"] = subprocess.check_output(
                [
                    "git",
                    "-C",
                    str(checkout),
                    "status",
                    "--porcelain",
                    "--untracked-files=all",
                ],
                text=True,
            ).strip()
    result = verify(evidence_package, optimized)
    assert result.returncode != 0, result.stdout
    assert "current_checked" not in result.stdout
