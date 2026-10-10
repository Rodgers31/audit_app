"""Actual CLI receipt refusal and published-source verification, including -O."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/admin/implementation/batch10-readiness-evidence"


@pytest.fixture
def package(tmp_path):
    root = tmp_path / "package"
    (root / "backend").mkdir(parents=True)
    for filename in ("record.py", "verify_package.py"):
        shutil.copyfile(EVIDENCE / filename, root / filename)
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    (root / "backend/input.py").write_text("value = 1\n")
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "add",
            "record.py",
            "verify_package.py",
            "backend/input.py",
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Inert fixture",
            "-c",
            "user.email=inert@local",
            "commit",
            "-m",
            "fixture",
        ],
        check=True,
        capture_output=True,
    )
    return root, tmp_path


def run(root, output, payload, *, optimize=False, negative=None):
    command = [
        sys.executable,
        *(["-O"] if optimize else []),
        str(root / "record.py"),
        "--root",
        str(root),
        "--output",
        str(output),
    ]
    if negative:
        command += ["--negative-diagnostic", negative]
    return subprocess.run(
        command + ["--", sys.executable, "-c", payload],
        env={"PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        timeout=15,
    )


@pytest.mark.parametrize("optimize", [False, True])
@pytest.mark.parametrize("destination", ["inherited", "source", "generator", "symlink"])
def test_recorder_refuses_overwrite_before_child(package, destination, optimize):
    root, tmp = package
    sentinel = tmp / "child-ran"
    output = tmp / "receipt.json"
    if destination == "inherited":
        output.write_text("historical bytes")
    elif destination in {"source", "generator"}:
        output = root / ("backend/input.py" if destination == "source" else "record.py")
    else:
        output.symlink_to(root / "backend/input.py")
    before = output.read_bytes()
    result = run(
        root,
        output,
        f"from pathlib import Path; Path({str(sentinel)!r}).touch()",
        optimize=optimize,
    )
    assert result.returncode == 1
    assert "Refuse" in result.stderr or "external" in result.stderr
    assert output.read_bytes() == before and not sentinel.exists()


@pytest.mark.parametrize("optimize", [False, True])
@pytest.mark.parametrize(
    "tamper",
    [
        "source",
        "output",
        "verdict",
        "empty_inventory",
        "generator",
        "wrong_generator",
        "boolean_child_exit",
        "string_stability",
        "missing_command",
        "missing_runtime",
        "missing_started_at",
        "missing_ended_at",
        "missing_environment",
    ],
)
def test_package_verifier_rejects_tampering(package, optimize, tamper):
    root, tmp = package
    output = tmp / "receipt.json"
    assert run(root, output, "print('actual child')").returncode == 0

    def check():
        return subprocess.run(
            [
                sys.executable,
                *(["-O"] if optimize else []),
                str(root / "verify_package.py"),
                "--root",
                str(root),
                "--receipt",
                str(output),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )

    assert check().returncode == 0
    if tamper == "source":
        (root / "backend/input.py").write_text("value = 2\n")
    elif tamper == "output":
        output.with_suffix(".txt").write_text("tampered")
    elif tamper == "generator":
        with (root / "record.py").open("a") as stream:
            stream.write("\n# changed\n")
    else:
        data = json.loads(output.read_text())
        if tamper.startswith("missing_"):
            del data[tamper.removeprefix("missing_")]
        elif tamper == "wrong_generator":
            import hashlib

            data["generated_by"] = "backend/input.py"
            data["generator_sha256"] = hashlib.sha256(
                (root / "backend/input.py").read_bytes()
            ).hexdigest()
        elif tamper == "boolean_child_exit":
            data["child_exit"] = False
        elif tamper == "string_stability":
            data["source_stable"] = "false"
        elif tamper == "verdict":
            data["verdict"] = "FAIL"
        else:
            data["before"]["sources"] = data["after"]["sources"] = {}
        output.write_text(json.dumps(data))
    assert check().returncode == 1, "VERIFIER_ACCEPTED_TAMPERED_RECEIPT"


def test_source_mutation_and_missing_child_cannot_certify_success(package):
    root, tmp = package
    output = tmp / "changed.json"
    result = run(
        root, output, "from pathlib import Path; Path('input.py').write_text('changed')"
    )
    assert result.returncode == 1
    data = json.loads(output.read_text())
    assert (
        data["child_exit"] == 0
        and data["source_stable"] is False
        and data["verdict"] == "FAIL"
    )
    missing = tmp / "missing.json"
    result = run(
        root, missing, "raise RuntimeError('FALSE_READY')", negative="FALSE_READY"
    )
    assert result.returncode == 1
    assert json.loads(missing.read_text())["verdict"] == "FAIL"
    # Fresh command failures, including an absent actual script, are never behavioral red.
    absent = tmp / "absent.json"
    result = subprocess.run(
        [
            sys.executable,
            str(root / "record.py"),
            "--root",
            str(root),
            "--output",
            str(absent),
            "--negative-diagnostic",
            "FALSE_READY",
            "--",
            sys.executable,
            str(tmp / "absent-child.py"),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 1 and json.loads(absent.read_text())["child_exit"] == 2
