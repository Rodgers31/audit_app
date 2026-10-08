"""Actual YAML job scope and resolved env -> Settings -> adapter behavior."""
from pathlib import Path
import re

import pytest
import yaml

from seeding.config import SeedingSettings
from services.receipt_store import LocalReceiptStore, configured_receipt_store
from services.supabase_receipt_store import SupabaseReceiptStore
from test_supabase_receipt_store import BUCKET, KEY, URL

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/seed.yml"


def job_environment(variables, secrets):
    workflow = yaml.safe_load(WORKFLOW.read_text())
    environment = workflow["jobs"]["seed"]["env"]
    resolved = {}
    for name, expression in environment.items():
        match = re.fullmatch(
            r"\$\{\{ (vars|secrets)\.([A-Z0-9_]+)(?: \|\| '([^']*)')? \}\}", expression
        )
        assert match, (name, expression)
        source, key, fallback = match.groups()
        resolved[name] = (
            (variables if source == "vars" else secrets).get(key, "") or fallback or ""
        )
    return workflow, resolved


def apply_environment(monkeypatch, environment):
    for name in environment:
        monkeypatch.setenv(name, environment[name])


def test_unset_workflow_config_retains_local_mode_without_secret_lookup(
    tmp_path, monkeypatch
):
    from config import secrets

    workflow, environment = job_environment({}, {})
    assert environment["SEED_RECEIPT_STORAGE_BACKEND"] == "local"
    assert environment["SEED_RECEIPT_MAX_BYTES"] == ""
    assert environment["SEED_RECEIPT_PART_MAX_BYTES"] == ""
    apply_environment(monkeypatch, environment)
    settings = SeedingSettings(storage_path=tmp_path)
    assert settings.receipt_max_bytes is None
    assert settings.receipt_part_max_bytes is None
    monkeypatch.setattr(
        secrets,
        "get_secret",
        lambda name: pytest.fail("local mode must not request the server key"),
    )
    assert isinstance(configured_receipt_store(settings), LocalReceiptStore)
    assert "RECEIPT_SUPABASE_SECRET_KEY" not in workflow.get("env", {})
    for job_name, job in workflow["jobs"].items():
        if job_name != "seed":
            assert "RECEIPT_SUPABASE_SECRET_KEY" not in str(job)


def test_supabase_workflow_variables_reach_actual_settings_and_adapter(
    tmp_path, monkeypatch
):
    from config import secrets

    variables = {
        "SEED_RECEIPT_STORAGE_BACKEND": "supabase",
        "SEED_RECEIPT_SUPABASE_URL": URL,
        "SEED_RECEIPT_SUPABASE_BUCKET": BUCKET,
        "SEED_RECEIPT_MAX_BYTES": "1024",
        "SEED_RECEIPT_PART_MAX_BYTES": "512",
        "SEED_RECEIPT_STORAGE_TIMEOUT_SECONDS": "12",
    }
    _, environment = job_environment(variables, {"RECEIPT_SUPABASE_SECRET_KEY": KEY})
    apply_environment(monkeypatch, environment)
    monkeypatch.setattr(secrets, "get_secret", lambda name: environment[name])
    settings = SeedingSettings(storage_path=tmp_path)
    assert settings.receipt_supabase_url == URL
    assert settings.receipt_supabase_bucket == BUCKET
    assert settings.receipt_max_bytes == 1024
    assert settings.receipt_part_max_bytes == 512
    assert settings.receipt_storage_timeout_seconds == 12
    store = configured_receipt_store(settings)
    assert isinstance(store, SupabaseReceiptStore)
    assert (
        store.project_url == URL and store.bucket == BUCKET and store.max_bytes == 1024
    )
    assert store.part_max_bytes == 512


@pytest.mark.parametrize("cap", ["true", "0", "-1", "1.0", "1e3", "NaN", "33554433"])
def test_workflow_hostile_part_caps_refuse_settings(monkeypatch, cap):
    _, environment = job_environment({"SEED_RECEIPT_PART_MAX_BYTES": cap}, {})
    apply_environment(monkeypatch, environment)
    with pytest.raises(ValueError):
        SeedingSettings()


def test_selected_supabase_without_workflow_cap_refuses_before_secret_lookup(
    tmp_path, monkeypatch
):
    from config import secrets

    _, environment = job_environment(
        {
            "SEED_RECEIPT_STORAGE_BACKEND": "supabase",
            "SEED_RECEIPT_SUPABASE_URL": URL,
            "SEED_RECEIPT_SUPABASE_BUCKET": BUCKET,
        },
        {},
    )
    apply_environment(monkeypatch, environment)
    settings = SeedingSettings(storage_path=tmp_path)
    monkeypatch.setattr(
        secrets,
        "get_secret",
        lambda name: pytest.fail("missing-cap refusal must precede secret lookup"),
    )
    with pytest.raises(ValueError, match="explicitly configured"):
        configured_receipt_store(settings)
    assert not (tmp_path / "response-receipts").exists()


def test_r2_workflow_binding_and_job_only_secrets(tmp_path, monkeypatch):
    from config import secrets
    from services.r2_receipt_store import R2ReceiptStore
    from test_r2_receipt_store import ACCOUNT, R2_BUCKET, ACCESS, SECRET, CONTROL
    variables = {"SEED_RECEIPT_STORAGE_BACKEND": "r2", "SEED_RECEIPT_R2_ACCOUNT_ID": ACCOUNT, "SEED_RECEIPT_R2_BUCKET": R2_BUCKET, "SEED_RECEIPT_R2_JURISDICTION": "default", "SEED_RECEIPT_MAX_BYTES": "1024", "SEED_RECEIPT_PART_MAX_BYTES": "512", "SEED_RECEIPT_STORAGE_TIMEOUT_SECONDS": "12"}
    credentials = {"RECEIPT_R2_ACCESS_KEY_ID": ACCESS, "RECEIPT_R2_SECRET_ACCESS_KEY": SECRET, "RECEIPT_R2_CONTROL_TOKEN": CONTROL}
    workflow, environment = job_environment(variables, credentials)
    apply_environment(monkeypatch, environment)
    monkeypatch.setattr(secrets, "get_secret", lambda name: environment[name])
    settings = SeedingSettings(storage_path=tmp_path)
    store = configured_receipt_store(settings)
    assert isinstance(store, R2ReceiptStore)
    assert (store.account_id, store.bucket, store.jurisdiction) == (ACCOUNT, R2_BUCKET, "default")
    assert (store.max_bytes, store.part_max_bytes, store._timeout) == (1024, 512, 12)
    for name in credentials:
        assert name not in workflow.get("env", {})
        for job_name, job in workflow["jobs"].items():
            if job_name != "seed": assert name not in str(job)


@pytest.mark.parametrize("changes", [{"receipt_max_bytes": None}, {"receipt_r2_account_id": "evil.example"}, {"receipt_r2_bucket": "../other"}])
def test_r2_invalid_target_or_missing_cap_before_secret_lookup(tmp_path, monkeypatch, changes):
    from config import secrets
    from test_r2_receipt_store import ACCOUNT, R2_BUCKET
    values = dict(storage_path=tmp_path, receipt_storage_backend="r2", receipt_r2_account_id=ACCOUNT, receipt_r2_bucket=R2_BUCKET, receipt_max_bytes=1024)
    values.update(changes)
    monkeypatch.setattr(secrets, "get_secret", lambda name: pytest.fail("invalid target must refuse before secret lookup"))
    with pytest.raises(ValueError): configured_receipt_store(SeedingSettings(**values))
    assert not (tmp_path / "response-receipts").exists()
