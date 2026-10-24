import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from conftest import ROOT, tool
import ingestion_preflight_readiness as readiness


def workflow():
    return yaml.load(
        (ROOT / ".github/workflows/ingestion-preflight.yml").read_text(),
        Loader=yaml.BaseLoader,
    )


def test_manual_only_workflow_has_no_input_execution_or_upload():
    value = workflow()
    assert set(value["on"]) == {"workflow_dispatch"}
    assert value["permissions"] == {"contents": "read"}
    assert value["concurrency"]["cancel-in-progress"] == "false"
    assert len(value["jobs"]) == 1
    job = value["jobs"]["inspect"]
    assert job["runs-on"] == "ubuntu-latest" and job["timeout-minutes"] == "5"
    assert "if" not in job  # Mismatched identity must REFUSE, not skip green.
    steps = job["steps"]
    actions = [s["uses"] for s in steps if "uses" in s]
    assert all(len(a.rsplit("@", 1)[1]) == 40 for a in actions)
    checkout = next(s for s in steps if "uses" in s)
    assert len(checkout["with"]["ref"]) == 40
    assert checkout["with"]["persist-credentials"] == "false"
    secret_steps = [s for s in steps if "secrets." in json.dumps(s)]
    assert len(secret_steps) == 1
    assert "--execute-read-only" in secret_steps[0]["run"]
    assert steps.index(secret_steps[0]) > next(
        i for i, s in enumerate(steps) if "--admit-only" in s.get("run", "")
    )
    assert not any("upload-artifact" in a for a in actions)
    assert not any("inputs." in json.dumps(s) for s in steps)


@pytest.mark.parametrize(
    "ref,sha,definition",
    [
        (
            "refs/heads/main",
            "924f1a4f27e1952f97d2291d8878d88603132237",
            "Rodgers31/audit_app/.github/workflows/ingestion-preflight.yml@refs/heads/main",
        ),
        (
            "refs/heads/attacker",
            "a" * 40,
            "Rodgers31/audit_app/.github/workflows/ingestion-preflight.yml@refs/heads/attacker",
        ),
        ("refs/tags/main", "a" * 40, "wrong"),
    ],
)
def test_actual_workflow_admission_shell_refuses_all_author_dispatches(
    ref, sha, definition
):
    command = workflow()["jobs"]["inspect"]["steps"][0]["run"]
    r = subprocess.run(
        ["sh", "-ec", command],
        env={
            "DISPATCH_REPOSITORY": "Rodgers31/audit_app",
            "DISPATCH_REF": ref,
            "DISPATCH_SHA": sha,
            "DEFINITION_REF": definition,
            "APPROVED_DISPATCH_SHA": "",
        },
        capture_output=True,
        timeout=2,
    )
    assert r.returncode != 0


@pytest.mark.parametrize(
    "expected", ["", "true", "failed", "0" * 39, "z" * 40, "a" * 39 + "\n", "b" * 40]
)
def test_workflow_dispatch_identity_requires_exact_reviewed_external_pin(expected):
    command = workflow()["jobs"]["inspect"]["steps"][0]["run"]
    r = subprocess.run(
        ["sh", "-ec", command],
        env={
            "DISPATCH_REPOSITORY": "Rodgers31/audit_app",
            "DISPATCH_REF": "refs/heads/main",
            "DISPATCH_SHA": "a" * 40,
            "DEFINITION_REF": "Rodgers31/audit_app/.github/workflows/ingestion-preflight.yml@refs/heads/main",
            "APPROVED_DISPATCH_SHA": expected,
        },
        capture_output=True,
        timeout=2,
    )
    assert r.returncode != 0


def test_workflow_dispatch_pin_can_be_provisioned_after_reviewed_commit_exists():
    command = workflow()["jobs"]["inspect"]["steps"][0]["run"]
    env = {
        "DISPATCH_REPOSITORY": "Rodgers31/audit_app",
        "DISPATCH_REF": "refs/heads/main",
        "DISPATCH_SHA": "a" * 40,
        "DEFINITION_REF": "Rodgers31/audit_app/.github/workflows/ingestion-preflight.yml@refs/heads/main",
        "APPROVED_DISPATCH_SHA": "a" * 40,
    }
    assert (
        subprocess.run(
            ["sh", "-ec", command], env=env, capture_output=True, timeout=2
        ).returncode
        == 0
    )
    # This admits ONLY the shell identity; disabled policy still refuses the CLI.
    env["DISPATCH_REF"] = "refs/heads/unreviewed"
    assert (
        subprocess.run(
            ["sh", "-ec", command], env=env, capture_output=True, timeout=2
        ).returncode
        != 0
    )


def test_actual_workflow_cli_refuses_disabled_admission_without_secrets():
    r = subprocess.run(
        [
            sys.executable,
            "-B",
            str(ROOT / "scripts/verification/ingestion_preflight.py"),
            "--admit-only",
        ],
        env={},
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert r.returncode == 2 and json.loads(r.stdout)["status"] == "REFUSED"


def test_retained_facts_are_not_a_daily_forecast_or_free_acceptance():
    result = readiness.readiness()
    assert result["status"] == "BLOCKED" and result["free_ready"] is False
    assert result["retained"]["optimized_daily_rate_bytes"] is None
    assert result["historical_uncached_allowance_multiple"] == "8.6252"
    assert (
        result["current_database_headroom_bytes_before_growth_and_reserve"]
        == 409_900_000
    )
    assert result["official_free_limits"]["cached_bytes_separate"] == 5_000_000_000
    assert "RECURRING_OWNER_MANAGED_OFFSITE_BACKUP_POLICY" in result["unmet_gates"]


@pytest.mark.parametrize(
    "packet",
    [
        True,
        False,
        None,
        1,
        {},
        [],
        "",
        float("nan"),
        float("inf"),
        -1,
        {"status": "passed"},
    ],
)
def test_absent_malformed_truthy_failed_and_synthetic_evidence_never_accepts_free(
    packet,
):
    from datetime import datetime, timezone

    result = readiness.readiness(
        packet, expected_identity={}, as_of=datetime.now(timezone.utc)
    )
    assert result["status"] == "BLOCKED" and result["free_ready"] is False
    assert result["production_authorized"] is False


def test_existing_operating_evaluator_is_invoked_for_real_packet_shape(monkeypatch):
    calls = []

    def existing(packet, **kwargs):
        calls.append((packet, kwargs))
        return {"status": "CANDIDATE_FOR_OWNER_REVIEW", "production_authorized": False}

    from datetime import datetime, timezone

    monkeypatch.setattr(readiness.budget, "evaluate", existing)
    result = readiness.readiness(
        {"input": "toy"},
        expected_identity={"id": "toy"},
        as_of=datetime.now(timezone.utc),
    )
    assert len(calls) == 1
    assert (
        result["existing_operating_evaluation"]["status"]
        == "CANDIDATE_FOR_OWNER_REVIEW"
    )
    assert result["free_ready"] is False and result["status"] == "BLOCKED"


def test_existing_synthetic_operating_packet_stays_blocked():
    packet = tool.budget.load_json(
        ROOT
        / "docs/infrastructure/supabase-egress/fixtures/social-operating-synthetic.json"
    )
    # Use retained fixture's declared identity/time; do not relabel as production.
    from datetime import datetime, timezone

    result = readiness.readiness(
        packet,
        expected_identity=packet["identity"],
        as_of=datetime(2026, 10, 20, tzinfo=timezone.utc),
    )
    assert result["free_ready"] is False
    assert result["existing_operating_evaluation"]["status"] == "BLOCKED"


def test_readiness_cli_exit_is_blocked():
    r = subprocess.run(
        [
            sys.executable,
            "-B",
            str(ROOT / "scripts/verification/ingestion_preflight_readiness.py"),
        ],
        env={},
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1 and json.loads(r.stdout)["status"] == "BLOCKED"


@pytest.mark.parametrize("hash_value", [None, "", True, "a" * 64, "NOT_ADMITTED"])
def test_reviewed_admission_requires_exact_nonsecret_file_hash(
    tmp_path, capsys, hash_value
):
    path = tmp_path / "admission.json"
    path.write_text((ROOT / "docs/admin/batch66/preflight-admission.json").read_text())
    args = ["--reviewed-admission", str(path), "--admit-only"]
    if hash_value is not None:
        args += ["--expected-admission-sha256", str(hash_value)]
    assert tool.main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "REFUSED"


def test_pinned_policy_can_refer_to_preexisting_implementation(
    config, tmp_path, monkeypatch, capsys
):
    # Admission file exists OUTSIDE the immutable source checkout. It can be
    # committed later without changing the implementation's expected HEAD.
    config["mode"] = "hosted"
    config["database"].update(
        host="db." + "a" * 20 + ".supabase.co", port=5432, tls="verify-full"
    )
    path = tmp_path / "admission.json"
    path.write_text(json.dumps(config))
    import hashlib

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert (
        tool.main(
            [
                "--reviewed-admission",
                str(path),
                "--expected-admission-sha256",
                digest,
                "--admit-only",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["safe_to_write"] is False
    path.write_text("{}")
    assert (
        tool.main(
            [
                "--reviewed-admission",
                str(path),
                "--expected-admission-sha256",
                digest,
                "--admit-only",
            ]
        )
        == 2
    )


def test_policy_is_parsed_from_exact_hashed_bytes_once(tmp_path, monkeypatch, capsys):
    import hashlib

    path = tmp_path / "admission.json"
    original = (ROOT / "docs/admin/batch66/preflight-admission.json").read_bytes()
    path.write_bytes(original)
    calls = []
    real = tool.raw_file

    def replace_after_read(target, *args):
        value = real(target, *args)
        if target == path:
            calls.append(target)
            path.write_text('{"accepted":true}')
        return value

    monkeypatch.setattr(tool, "raw_file", replace_after_read)
    assert (
        tool.main(
            [
                "--reviewed-admission",
                str(path),
                "--expected-admission-sha256",
                hashlib.sha256(original).hexdigest(),
                "--admit-only",
            ]
        )
        == 2
    )
    assert calls == [path]
    assert json.loads(capsys.readouterr().out)["status"] == "REFUSED"


def test_cli_whole_deadline_includes_admission(tmp_path, monkeypatch, capsys):
    import time

    # Bypass the unrelated config guard only in this timeout unit control.
    path = tmp_path / "admission.json"
    path.write_text('{"mode":"hosted"}')
    monkeypatch.setattr(tool, "CONFIG", path)
    monkeypatch.setattr(tool, "check_config", lambda _: None)
    monkeypatch.setattr(tool, "source_identity", lambda *_: time.sleep(0.2))
    monkeypatch.setattr(tool, "RUN_SECONDS", 0.02)
    start = time.monotonic()
    assert tool.main(["--admit-only"]) == 2
    assert time.monotonic() - start < 0.15
    assert json.loads(capsys.readouterr().out)["status"] == "REFUSED"
