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
