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
        "REDIS_URL": "redis://127.0.0.1:55521/15",
        "ENVIRONMENT": "test",
        "SECRET_BACKEND": "env",
        "AUTO_SEEDER_ENABLED": "false",
        "AUTO_WARMUP_ENABLED": "false",
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
        (checkout / receipt["generated_by"]).write_text("# changed\n")
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
        "missing_env_REDIS_URL",
        "missing_env_ENVIRONMENT",
        "missing_env_SECRET_BACKEND",
        "missing_env_AUTO_SEEDER_ENABLED",
        "missing_env_AUTO_WARMUP_ENABLED",
    ],
)
def test_evidence_rejects_malformed_execution_provenance(
    evidence_package, optimized, mutation
):
    checkout, _, _, receipt = evidence_package
    if mutation.startswith("missing_env_"):
        receipt["environment"].pop(mutation[len("missing_env_") :])
    elif mutation.startswith("missing_"):
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


@pytest.mark.parametrize("optimized", [False, True])
@pytest.mark.parametrize("destination", ["git", "ignored", "symlink"])
def test_evidence_refuses_current_outputs_hidden_inside_checkout(
    evidence_package, optimized, destination
):
    checkout, artifacts, replay, receipt = evidence_package
    if destination == "symlink":
        alias = replay.parent / "replay-alias"
        alias.symlink_to(replay, target_is_directory=True)
        receipt_path = alias / "receipt.json"
    else:
        hidden = checkout / (
            ".git/current-replay" if destination == "git" else "ignored-output"
        )
        hidden.mkdir()
        if destination == "ignored":
            (checkout / ".gitignore").write_text("ignored-output/\n")
            subprocess.run(
                ["git", "-C", str(checkout), "add", ".gitignore"], check=True
            )
        receipt["command"][-1] = "--junitxml=" + str(hidden / "cases.xml")
        receipt["environment"]["DATABASE_URL"] = "sqlite:///" + str(
            hidden / "batch10-imf-import.sqlite"
        )
        receipt["started_at"] = datetime.now(timezone.utc).isoformat()
        child = subprocess.run(
            receipt["command"],
            cwd=checkout,
            env=receipt["environment"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert child.returncode == 0, child.stdout + child.stderr
        (hidden / "raw.log").write_text(child.stdout + child.stderr)
        receipt["ended_at"] = datetime.now(timezone.utc).isoformat()
        receipt["outputs"] = {
            name: digest(hidden / name) for name in ("raw.log", "cases.xml")
        }
        # Measure the actual post-fixture source, including the added ignore rule.
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "imf_review_recorder", VERIFIER.with_name("run_evidence.py")
        )
        recorder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(recorder)
        state = recorder.source_state(checkout, recorder.source_names(checkout))
        receipt["start"] = state
        receipt["end"] = json.loads(json.dumps(state))
        receipt_path = hidden / "receipt.json"
    receipt_path.write_text(json.dumps(receipt))
    retained = {
        name: digest(receipt_path.parent / name)
        for name in ("receipt.json", "cases.xml", "raw.log")
    }
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            *(["-O"] if optimized else []),
            str(VERIFIER),
            str(checkout),
            str(artifacts),
            str(receipt_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0, "CURRENT_REPLAY_INSIDE_CHECKOUT_ACCEPTED"
    assert "external" in result.stderr or "symlink" in result.stderr, result.stderr
    assert retained == {
        name: digest(receipt_path.parent / name) for name in retained
    }, "Verifier changed inherited output bytes"


@pytest.mark.parametrize("optimized", [False, True])
def test_evidence_refuses_fixture_database_symlink_into_checkout(
    evidence_package, optimized
):
    checkout, _, replay, receipt = evidence_package
    hidden = checkout / ".git/hidden-fixture.sqlite"
    fixture = replay / "batch10-imf-import.sqlite"
    fixture.symlink_to(hidden)
    test = checkout / "test_control.py"
    test.write_text(
        "import os,sqlite3\ndef test_control():\n    with sqlite3.connect(os.environ['DATABASE_URL'].removeprefix('sqlite:///')) as db:\n        assert db.execute('SELECT 1').fetchone() == (1,)\n"
    )
    receipt["started_at"] = datetime.now(timezone.utc).isoformat()
    child = subprocess.run(
        receipt["command"],
        cwd=checkout,
        env=receipt["environment"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert child.returncode == 0, child.stdout + child.stderr
    assert hidden.is_file(), "Actual child did not open the hidden database"
    (replay / "raw.log").write_text(child.stdout + child.stderr)
    receipt["ended_at"] = datetime.now(timezone.utc).isoformat()
    receipt["outputs"] = {
        name: digest(replay / name) for name in ("raw.log", "cases.xml")
    }
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "imf_db_boundary_recorder", VERIFIER.with_name("run_evidence.py")
    )
    recorder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recorder)
    state = recorder.source_state(checkout, recorder.source_names(checkout))
    receipt["start"] = state
    receipt["end"] = json.loads(json.dumps(state))
    before = hidden.read_bytes()
    result = verify(evidence_package, optimized)
    assert result.returncode != 0, "CURRENT_DATABASE_RESOLVES_INTO_CHECKOUT_ACCEPTED"
    assert "symlink" in result.stderr or "external" in result.stderr, result.stderr
    assert hidden.read_bytes() == before


@pytest.mark.parametrize("optimized", [False, True])
@pytest.mark.parametrize(
    "identity",
    [
        "valid",
        "blank_name",
        "blank_classname",
        "missing_name",
        "missing_classname",
        "duplicate",
    ],
)
def test_evidence_requires_unique_nonempty_executed_case_identities(
    evidence_package, optimized, identity
):
    checkout, _, replay, receipt = evidence_package
    test = checkout / "test_control.py"
    test.write_text(
        "def test_control():\n    assert 1+1==2\ndef test_second():\n    assert 2+2==4\n"
    )
    receipt["started_at"] = datetime.now(timezone.utc).isoformat()
    child = subprocess.run(
        receipt["command"],
        cwd=checkout,
        env=receipt["environment"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert child.returncode == 0, child.stdout + child.stderr
    (replay / "raw.log").write_text(child.stdout + child.stderr)
    receipt["ended_at"] = datetime.now(timezone.utc).isoformat()
    import importlib.util
    from xml.etree import ElementTree

    spec = importlib.util.spec_from_file_location(
        "imf_identity_recorder", VERIFIER.with_name("run_evidence.py")
    )
    recorder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recorder)
    state = recorder.source_state(checkout, recorder.source_names(checkout))
    receipt["start"] = state
    receipt["end"] = json.loads(json.dumps(state))
    xml = replay / "cases.xml"
    tree = ElementTree.parse(xml)
    cases = list(tree.getroot().iter("testcase"))
    assert len(cases) == 2, "Two real cases were not executed"
    if identity == "duplicate":
        for key in ("name", "classname"):
            cases[1].set(key, cases[0].get(key))
    elif identity.startswith("blank_"):
        cases[0].set(identity.removeprefix("blank_"), "   ")
    elif identity.startswith("missing_"):
        cases[0].attrib.pop(identity.removeprefix("missing_"))
    tree.write(xml, encoding="utf-8", xml_declaration=True)
    receipt["outputs"] = {
        name: digest(replay / name) for name in ("raw.log", "cases.xml")
    }
    (replay / "receipt.json").write_text(json.dumps(receipt))
    before = {
        name: digest(replay / name) for name in ("raw.log", "cases.xml", "receipt.json")
    }
    result = verify(evidence_package, optimized)
    if identity == "valid":
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["current_checked"] is True
    else:
        assert result.returncode != 0, "MALFORMED_JUNIT_IDENTITY_ACCEPTED"
        assert "testcase identity" in result.stderr, result.stderr
    assert before == {
        name: digest(replay / name) for name in before
    }, "Verifier rewrote inherited record bytes"
