"""Guarded acceptance helper execution against local simulation, never Supabase."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

from seeding.config import SeedingSettings
from test_supabase_receipt_store import Boundary, BODY, BUCKET, URL

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts/verification/verify_durable_receipt.py"
)
SPEC = importlib.util.spec_from_file_location("receipt_acceptance", SCRIPT)
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


def settings(tmp_path):
    return SeedingSettings(
        storage_path=tmp_path,
        receipt_storage_backend="supabase",
        receipt_supabase_url=URL,
        receipt_supabase_bucket=BUCKET,
        receipt_max_bytes=1024,
    )


def arguments(tmp_path, **changes):
    values = dict(
        operation="put",
        expected_project_ref="abcdefghijklmnopqrst",
        expected_bucket=BUCKET,
        file=tmp_path / "input",
        allow_supabase_write=True,
    )
    values.update(changes)
    return argparse.Namespace(**values)


@pytest.mark.parametrize(
    "change",
    [
        {"expected_project_ref": "other"},
        {"expected_bucket": "other"},
        {"allow_supabase_write": False},
        {"operation": "unknown"},
    ],
)
def test_cli_target_and_write_guards_before_storage(tmp_path, monkeypatch, change):
    monkeypatch.setattr(
        CLI,
        "configured_receipt_store",
        lambda settings: pytest.fail("must refuse before accessing storage"),
    )
    (tmp_path / "input").write_bytes(BODY)
    with pytest.raises(ValueError):
        CLI.verify(arguments(tmp_path, **change), settings(tmp_path))


def test_cli_local_put_then_fresh_adapter_read(tmp_path, monkeypatch):
    objects = tmp_path / "objects"
    objects.mkdir()
    (tmp_path / "input").write_bytes(BODY)
    monkeypatch.setattr(
        CLI, "configured_receipt_store", lambda settings: Boundary(objects).store()
    )
    put = CLI.verify(arguments(tmp_path), settings(tmp_path))
    assert put["status"] == "authenticated_readback_matched"
    read = CLI.verify(
        arguments(
            tmp_path,
            operation="read",
            digest=put["digest"],
            expected_size=put["byte_size"],
        ),
        settings(tmp_path),
    )
    assert read["digest"] == put["digest"]
    assert read["byte_size"] == len(BODY)
    with pytest.raises(RuntimeError, match="size mismatch"):
        CLI.verify(
            arguments(
                tmp_path,
                operation="read",
                digest=put["digest"],
                expected_size=len(BODY) + 1,
            ),
            settings(tmp_path),
        )


@pytest.mark.parametrize("body", [b"", b"x" * 1025])
def test_cli_bounded_file_before_storage(tmp_path, monkeypatch, body):
    (tmp_path / "input").write_bytes(body)
    monkeypatch.setattr(
        CLI,
        "configured_receipt_store",
        lambda settings: pytest.fail("must refuse before storage"),
    )
    with pytest.raises(ValueError):
        CLI.verify(arguments(tmp_path), settings(tmp_path))


def test_actual_cli_process_exits_nonzero_for_unconfigured_backend():
    # Deliberately provide no inherited provider credentials or database settings.
    process = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--expected-project-ref",
            "abcdefghijklmnopqrst",
            "--expected-bucket",
            BUCKET,
            "read",
            "--digest",
            "a" * 64,
            "--expected-size",
            "1",
        ],
        env={"SEED_RECEIPT_STORAGE_BACKEND": "local"},
        capture_output=True,
        text=True,
    )
    assert process.returncode == 1
    assert '"status": "refused"' in process.stderr
    assert not process.stdout


def r2_settings(tmp_path):
    from test_r2_receipt_store import ACCOUNT, R2_BUCKET
    return SeedingSettings(storage_path=tmp_path, receipt_storage_backend="r2", receipt_r2_account_id=ACCOUNT, receipt_r2_bucket=R2_BUCKET, receipt_max_bytes=1024)


def r2_args(tmp_path, **changes):
    from test_r2_receipt_store import ACCOUNT, R2_BUCKET
    return arguments(tmp_path, expected_backend="r2", expected_account_id=ACCOUNT, expected_bucket=R2_BUCKET, expected_jurisdiction="default", allow_r2_write=True, **changes)


@pytest.mark.parametrize("field,value", [("expected_account_id", "b" * 32), ("expected_bucket", "other"), ("expected_jurisdiction", "eu"), ("allow_r2_write", False)])
def test_r2_cli_guards_before_store(tmp_path, monkeypatch, field, value):
    args = r2_args(tmp_path)
    setattr(args, field, value)
    monkeypatch.setattr(CLI, "configured_receipt_store", lambda settings: pytest.fail("must refuse before storage"))
    with pytest.raises(ValueError): CLI.verify(args, r2_settings(tmp_path))


def test_r2_actual_cli_parsing_and_fresh_boundary_read(tmp_path, monkeypatch):
    from test_r2_receipt_store import ACCOUNT, R2_BUCKET, Boundary as R2Boundary
    (tmp_path / "input").write_bytes(BODY)
    args = CLI.parser().parse_args(["--expected-backend", "r2", "--expected-account-id", ACCOUNT, "--expected-bucket", R2_BUCKET, "--expected-jurisdiction", "default", "put", "--file", str(tmp_path / "input"), "--allow-r2-write"])
    monkeypatch.setattr(CLI, "configured_receipt_store", lambda settings: R2Boundary(tmp_path / "objects").store())
    put = CLI.verify(args, r2_settings(tmp_path))
    assert put["backend"] == "r2" and put["account_id"] == ACCOUNT
    read = CLI.verify(r2_args(tmp_path, operation="read", digest=put["digest"], expected_size=put["byte_size"]), r2_settings(tmp_path))
    assert read["digest"] == put["digest"]
