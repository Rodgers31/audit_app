"""Exercise the evidence CLI with real pytest output and disposable Git inputs."""

import hashlib
import json
import os
import subprocess
import sys
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
    (checkout / "generator.py").write_text("# synthetic generator identity\n")
    test = checkout / "test_control.py"
    test.write_text("def test_control():\n    assert 1 + 1 == 2\n")
    env = {"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"}
    command = [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        "-q",
        str(test),
        "--junitxml=" + str(replay / "cases.xml"),
    ]
    child = subprocess.run(
        command, cwd=checkout, env=env, capture_output=True, text=True, timeout=30
    )
    assert child.returncode == 0, child.stdout + child.stderr
    (replay / "raw.log").write_text(child.stdout + child.stderr)
    (artifacts / "control.log").write_text(child.stdout + child.stderr)
    manifest = checkout / "docs/admin/implementation/batch10-imf-evidence/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
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
    git("add", "generator.py", "test_control.py", str(manifest.relative_to(checkout)))
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
        "generated_by": "generator.py",
        "generator_sha256": digest(checkout / "generator.py"),
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
