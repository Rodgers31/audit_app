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
@pytest.mark.parametrize("bytecode_setting", [None, "0", "1"])
@pytest.mark.parametrize("existing_cache", [False, True])
def test_valid_verification_preserves_complete_source_with_bytecode_enabled(
    package, optimize, bytecode_setting, existing_cache
):
    root, tmp = package
    if existing_cache:
        cache = root / "__pycache__/retained-input.pyc"
        cache.parent.mkdir()
        cache.write_bytes(b"retained measured input")
    output = tmp / "valid.json"
    recorded = run(root, output, "print('actual child')")
    assert recorded.returncode == 0, recorded.stderr
    receipt_bytes = output.read_bytes()
    log_bytes = output.with_suffix(".txt").read_bytes()
    before = json.loads(receipt_bytes)["after"]
    source_bytes = {path: (root / path).read_bytes() for path in before["sources"]}
    environment = {"PATH": os.defpath}
    if bytecode_setting is not None:
        environment["PYTHONDONTWRITEBYTECODE"] = bytecode_setting
    # Execute the actual CLI with an explicit ordinary/optimized interpreter.
    # Record its flags and require the imported helper to restore ambient state.
    payload = (
        "import json,runpy,sys; "
        "initial=sys.dont_write_bytecode; "
        "print(json.dumps({'optimize':sys.flags.optimize,'dont_write_bytecode':initial})); "
        f"sys.argv={[str(root / 'verify_package.py'), '--root', str(root), '--receipt', str(output)]!r}; "
        f"runpy.run_path({str(root / 'verify_package.py')!r},run_name='__main__'); "
        "print(json.dumps({'restored':sys.dont_write_bytecode is initial}))"
    )
    checked = subprocess.run(
        [sys.executable, *(["-O"] if optimize else []), "-c", payload],
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert checked.returncode == 0, checked.stderr
    flags, verdict, restored = [json.loads(line) for line in checked.stdout.splitlines()]
    assert flags == {
        "optimize": int(optimize),
        "dont_write_bytecode": bytecode_setting not in (None, "0"),
    }
    assert restored == {"restored": True}
    assert verdict["verdict"] == "PASS"
    paths = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "-c", "--others", "--exclude-standard"],
        env={"PATH": os.defpath},
        text=True,
    ).splitlines()
    assert set(paths) == set(source_bytes)
    assert all((root / path).read_bytes() == value for path, value in source_bytes.items())
    status = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain"],
        env={"PATH": os.defpath},
        text=True,
    ).strip()
    assert status == before["status"]
    assert output.read_bytes() == receipt_bytes
    assert output.with_suffix(".txt").read_bytes() == log_bytes


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
            env={"PATH": os.defpath},
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
        env={"PATH": os.defpath},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 1 and json.loads(absent.read_text())["child_exit"] == 2


@pytest.mark.parametrize("optimize", [False, True])
@pytest.mark.parametrize("present", [False, True])
def test_recorder_preserves_child_secret_inputs_without_publishing_values(
    package, optimize, present
):
    import hashlib

    root, tmp = package
    output = tmp / "portable.json"
    # These values are synthetic. Hashes in the command prove unchanged child
    # inputs without placing credentials in the recorded command or child log.
    secrets = {
        "DATABASE_URL": "postgresql://toy-user:toy-password-604@127.0.0.1:9/toy-db",
        "JWT_SECRET_KEY": "toy-jwt-secret-604-portable-control",
        "BATCH9_BOOTSTRAP_POSTGRES_URL": "postgresql://toy-user:toy-worker-604@127.0.0.1:9/toy-db",
    }
    expected = {
        key: hashlib.sha256(value.encode()).hexdigest()
        for key, value in secrets.items()
    }
    payload = (
        "import hashlib,os; expected="
        + repr(expected)
        + "; "
        + (
            "assert all(hashlib.sha256(os.environ[k].encode()).hexdigest()==v for k,v in expected.items()); "
            if present
            else "assert all(k not in os.environ for k in expected); "
        )
        + "print('CHILD_SECRET_INPUTS_PRESERVED')"
    )
    result = subprocess.run(
        [
            sys.executable,
            *(["-O"] if optimize else []),
            str(root / "record.py"),
            "--root",
            str(root),
            "--output",
            str(output),
            "--",
            sys.executable,
            "-c",
            payload,
        ],
        env={"PATH": os.defpath, **(secrets if present else {})},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads(output.read_text())
    assert receipt["child_exit"] == 0 and receipt["verdict"] == "PASS"
    assert "CHILD_SECRET_INPUTS_PRESERVED" in output.with_suffix(".txt").read_text()
    portable = output.read_bytes() + output.with_suffix(".txt").read_bytes()
    assert not any(
        value.encode() in portable for value in secrets.values()
    ), "PORTABLE_RECEIPT_LEAKS_SECRET"
    assert receipt.get(
        "secret_environment_present", {key: False for key in secrets}
    ) == {key: present for key in secrets}
    assert all(
        receipt["environment"].get(key) == ("<redacted>" if present else None)
        for key in secrets
    )
    verified = subprocess.run(
        [
            sys.executable,
            *(["-O"] if optimize else []),
            str(root / "verify_package.py"),
            "--root",
            str(root),
            "--receipt",
            str(output),
        ],
        env={"PATH": os.defpath},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert verified.returncode == 0, verified.stderr
