"""Preparation-only packet controls; no database/provider transport."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
ENTRY = ROOT / "backend/scripts/batch13_baseline_release.py"
spec = importlib.util.spec_from_file_location("release", ENTRY)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def inputs():
    now = datetime.now(timezone.utc).isoformat()
    return {"version": 1, "observed_at": now, "accepted_base": release.BASE, "accepted_tree": release.BASE_TREE,
        "github": {"enabled": False, "workflow_total": 5, "workflows": [
            {"id": i, "path": ".github/workflows/" + name, "state": "disabled_manually"}
            for i, name in enumerate(("ci.yml", "seed.yml", "docker-build-deploy.yml", "verification.yml", "r2-acceptance.yml"), 1)],
            "runs": [], "secret_names": ["DATABASE_POOLER_URL", "DATABASE_URL"]},
        "providers": {"render": {"resource_id": release.RENDER, "observed_at": now, "state": "authentication_required"},
            "supabase": {"resource_id": release.SUPABASE, "observed_at": now, "state": "authentication_required"}}}


def test_valid_packet_enumerates_every_category_and_stays_blocked():
    value = inputs()
    packet = release.build_packet(value)
    release.verify_packet(packet, value)
    assert packet["target"] == "e602b11a0001"
    assert packet["migration_chain"][-1]["revision"] == packet["target"]
    assert packet["audit_release"]["included"] is False
    assert packet["migration_from_revision"] is None
    assert packet["production_ready"] is packet["production_execution_authorized"] is False
    assert packet["status"] == "blocked_production_prerequisites" and len(packet["blockers"]) >= 8
    categories = {r["category"] for r in packet["writer_controls"]}
    assert categories == {"native_scheduled", "native_manual", "dedicated_supervisor", "dedicated_adapter_orphans", "legacy_etl", "bootstrap", "application_auto_seeder", "application_sessions", "parliament", "migrations_manual_scripts"}
    assert {r["id"] for r in packet["writer_controls"]} >= {"render_independent_jobs", "supabase_admission", "startup_bootstrap", "request_sessions"}
    assert all(r["deployed_disposition"] == "unverified" for r in packet["writer_controls"])


@pytest.mark.parametrize("provider", ["render", "supabase", "both"])
def test_authenticated_observations_do_not_certify_fences(provider):
    value = inputs()
    for name, row in value["providers"].items():
        if provider in (name, "both"):
            row["state"] = "authenticated_read_only"
    packet = release.build_packet(value)
    release.verify_packet(packet, value)
    assert packet["providers"] == value["providers"]
    assert packet["production_ready"] is packet["production_execution_authorized"] is False
    assert packet["status"] == "blocked_production_prerequisites"
    assert all(row["deployed_disposition"] == "unverified" for row in packet["writer_controls"])
    lifecycle = next(row for row in packet["writer_controls"] if row["id"] == "render_lifecycle")
    assert "backend/Dockerfile.prod" in lifecycle["source_paths"]
    assert "Gunicorn request recycling" in lifecycle["required_readback_and_fence"]


@pytest.mark.parametrize("bad", [None, {}, [], "bad", 0, True], ids=["null", "empty-object", "empty-list", "text", "zero", "bool"])
def test_unknown_root_refuses(bad):
    with pytest.raises(release.Refused, match="readback_shape"):
        release.build_packet(bad)


@pytest.mark.parametrize("bad", [True, 1.0, "1", None, 0, -1, float("nan"), float("inf")], ids=["bool", "float", "text", "null", "zero", "negative", "nan", "inf"])
def test_version_requires_exact_integer(bad):
    value = inputs(); value["version"] = bad
    with pytest.raises(release.Refused, match="readback_version"):
        release.build_packet(value)


@pytest.mark.parametrize("field", ["observed_at", "render", "supabase"])
@pytest.mark.parametrize("offset", [-301, 31], ids=["stale", "future"])
def test_every_readback_clock_is_bounded(field, offset):
    value = inputs(); stamp = (datetime.now(timezone.utc) + timedelta(seconds=offset)).isoformat()
    if field == "observed_at": value[field] = stamp
    else: value["providers"][field]["observed_at"] = stamp
    with pytest.raises(release.Refused, match="readback_stale"):
        release.build_packet(value)


@pytest.mark.parametrize("mutation", ["missing-workflow", "duplicate-workflow", "bool-total", "extra-key", "bad-state", "duplicate-secret", "no-secrets", "wrong-provider", "claimed-fence", "unknown-run-workflow"], ids=str)
def test_incomplete_or_ambiguous_census_refuses(mutation):
    value = inputs(); gh = value["github"]
    if mutation == "missing-workflow": gh["workflows"].pop(); gh["workflow_total"] -= 1
    if mutation == "duplicate-workflow": gh["workflows"][1] = deepcopy(gh["workflows"][0])
    if mutation == "bool-total": gh["workflow_total"] = True
    if mutation == "extra-key": value["production_ready"] = True
    if mutation == "bad-state": gh["workflows"][0]["state"] = "OFF"
    if mutation == "duplicate-secret": gh["secret_names"].append("DATABASE_URL")
    if mutation == "no-secrets": gh["secret_names"] = []
    if mutation == "wrong-provider": value["providers"]["render"]["resource_id"] = "srv-foreign"
    if mutation == "claimed-fence": value["providers"]["supabase"]["state"] = "fenced"
    if mutation == "unknown-run-workflow": gh["runs"] = [{"id": 1, "workflow_id": 999, "head_sha": "1" * 40, "status": "queued", "run_attempt": 1}]
    with pytest.raises(release.Refused): release.build_packet(value)


def test_repository_off_does_not_hide_active_workflows_or_pending_runs():
    value = inputs(); gh = value["github"]
    gh["workflows"].append({"id": 99, "path": "dynamic/agents/unknown-writer", "state": "active"}); gh["workflow_total"] += 1
    gh["runs"] = [{"id": 2, "workflow_id": 99, "head_sha": "1" * 40, "status": "queued", "run_attempt": 1}]
    packet = release.build_packet(value)
    assert packet["github_off_snapshot"] is True
    assert packet["nonterminal_runs"] == gh["runs"]
    assert packet["production_ready"] is False and packet["blockers"]
    gh["enabled"] = True
    packet = release.build_packet(value)
    assert packet["github_off_snapshot"] is False
    assert packet["blockers"][-1].startswith("GitHub repository")


@pytest.mark.parametrize("mutation", ["authority", "version-bool", "version-float", "source", "input", "writer", "audit", "revision", "generator"])
def test_published_packet_tampering_refuses(mutation):
    value = inputs(); packet = release.build_packet(value)
    if mutation == "authority": packet["production_execution_authorized"] = True
    if mutation == "version-bool": packet["version"] = True
    if mutation == "version-float": packet["version"] = 1.0
    if mutation == "source": packet["source_sha256"][release.ENTRY] = "0" * 64
    if mutation == "input": packet["input_sha256"] = "0" * 64
    if mutation == "writer": packet["writer_controls"].pop()
    if mutation == "audit": packet["target"] = "a611b12a0001"
    if mutation == "revision": packet["migration_from_revision"] = "ea1645a4c0b5"
    if mutation == "generator": packet["generator_sha256"] = "0" * 64
    with pytest.raises(release.Refused, match="packet_source_or_input_changed"):
        release.verify_packet(packet, value)


def test_source_links_and_missing_source_refuse(tmp_path):
    for name in release.source_hashes(ROOT):
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("inert source control\n")
    target = tmp_path / release.ENTRY
    target.unlink(); target.symlink_to(ENTRY)
    with pytest.raises(release.Refused, match="source_unavailable"): release.source_hashes(tmp_path)
    target.unlink()
    with pytest.raises(release.Refused, match="source_unavailable"): release.source_hashes(tmp_path)


@pytest.mark.parametrize("destination", ["source", "relative", "wrong-fd", "generator", "parent-link"])
def test_direct_publication_refuses_before_creation(tmp_path, destination):
    value = inputs()
    packet = release.build_packet(value)
    target = ROOT / "batch13-do-not-create.json" if destination == "source" else Path("relative-do-not-create.json") if destination == "relative" else tmp_path / "new.json"
    if destination == "generator":
        target = ENTRY
    if destination == "parent-link":
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path, target_is_directory=True)
        target = alias / "new.json"
    fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY)
    before = release.source_hashes(ROOT)
    try:
        with pytest.raises(release.Refused):
            release.publish(target, packet, value, fd)
    finally:
        os.close(fd)
    if destination != "generator":
        assert not target.exists()
    assert release.source_hashes(ROOT) == before


def invoke(argv, optimized=False):
    return subprocess.run([sys.executable, *(["-O"] if optimized else []), str(ENTRY), *argv],
        env={"PATH": "/usr/bin:/bin", "PYTHON_DOTENV_DISABLED": "1"}, text=True, capture_output=True, timeout=10)


@pytest.mark.parametrize("optimized", [False, True], ids=["normal", "optimized"])
def test_actual_cli_publish_verify_and_fresh_output_guard(tmp_path, optimized):
    value = inputs(); input_path = tmp_path / "inputs.json"; packet = tmp_path / "packet.json"
    input_path.write_text(json.dumps(value))
    before = release.source_hashes(ROOT)
    result = invoke(["prepare", "--inputs", str(input_path), "--out", str(packet)], optimized)
    assert result.returncode == 0 and json.loads(result.stdout)["status"] == "verified_preparation_only", result.stderr
    assert packet.stat().st_mode & 0o777 == 0o600
    raw = packet.read_bytes()
    result = invoke(["verify", "--inputs", str(input_path), "--packet", str(packet)], optimized)
    assert result.returncode == 0 and json.loads(result.stdout)["production_ready"] is False
    result = invoke(["prepare", "--inputs", str(input_path), "--out", str(packet)], optimized)
    assert result.returncode == 1 and json.loads(result.stdout)["status"] == "refused"
    assert packet.read_bytes() == raw and release.source_hashes(ROOT) == before


@pytest.mark.parametrize("optimized", [False, True], ids=["normal", "optimized"])
@pytest.mark.parametrize("bad", ["absent", "empty", "malformed", "duplicate", "nonfinite", "stale", "tampered", "deep"], ids=str)
def test_actual_reader_refuses_without_new_output(tmp_path, optimized, bad):
    value = inputs(); path = tmp_path / "inputs.json"; packet = tmp_path / "packet.json"
    raw = json.dumps(value)
    if bad == "empty": raw = ""
    if bad == "malformed": raw = "{"
    if bad == "duplicate": raw = raw[:-1] + ', "version": 1}'
    if bad == "nonfinite": raw = raw.replace('"version": 1', '"version": NaN')
    if bad == "deep": raw = "[" * 16000 + "]" * 16000
    if bad == "stale": value["observed_at"] = "2020-01-01T00:00:00Z"; raw = json.dumps(value)
    if bad == "tampered": value["accepted_base"] = "0" * 40; raw = json.dumps(value)
    if bad != "absent": path.write_text(raw)
    result = invoke(["prepare", "--inputs", str(path), "--out", str(packet)], optimized)
    assert result.returncode == 1 and json.loads(result.stdout)["status"] == "refused", result.stderr
    assert not packet.exists()


@pytest.mark.parametrize("optimized", [False, True], ids=["normal", "optimized"])
def test_absent_stale_and_malformed_packet_reader(tmp_path, optimized):
    value = inputs(); path = tmp_path / "inputs.json"; packet = tmp_path / "packet.json"
    path.write_text(json.dumps(value))
    result = invoke(["verify", "--inputs", str(path), "--packet", str(packet)], optimized)
    assert result.returncode == 1 and json.loads(result.stdout)["status"] == "refused"
    packet.write_text("{}")
    original = packet.read_bytes()
    result = invoke(["verify", "--inputs", str(path), "--packet", str(packet)], optimized)
    assert result.returncode == 1 and packet.read_bytes() == original
    packet.write_text(json.dumps(release.build_packet(value)))
    value["observed_at"] = "2020-01-01T00:00:00Z"; path.write_text(json.dumps(value))
    original = packet.read_bytes()
    result = invoke(["verify", "--inputs", str(path), "--packet", str(packet)], optimized)
    assert result.returncode == 1 and packet.read_bytes() == original
