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
            r"\$\{\{ (vars|secrets)\.([A-Z_]+)(?: \|\| '([^']*)')? \}\}", expression
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
    apply_environment(monkeypatch, environment)
    settings = SeedingSettings(storage_path=tmp_path)
    assert settings.receipt_max_bytes is None
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
        "SEED_RECEIPT_STORAGE_TIMEOUT_SECONDS": "12",
    }
    _, environment = job_environment(variables, {"RECEIPT_SUPABASE_SECRET_KEY": KEY})
    apply_environment(monkeypatch, environment)
    monkeypatch.setattr(secrets, "get_secret", lambda name: environment[name])
    settings = SeedingSettings(storage_path=tmp_path)
    assert settings.receipt_supabase_url == URL
    assert settings.receipt_supabase_bucket == BUCKET
    assert settings.receipt_max_bytes == 1024
    assert settings.receipt_storage_timeout_seconds == 12
    store = configured_receipt_store(settings)
    assert isinstance(store, SupabaseReceiptStore)
    assert (
        store.project_url == URL and store.bucket == BUCKET and store.max_bytes == 1024
    )


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
