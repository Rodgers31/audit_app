"""The review-only SQL renderer must enforce its guards even under python -O."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/prepare_legacy_evidence_cleanup.py"
MANIFEST = ROOT / "docs/operations/2026-09-27-public-evidence/cleanup-manifest.json"


def _renderer():
    spec = importlib.util.spec_from_file_location("review_cleanup_renderer", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.render


def _manifest():
    return json.loads(MANIFEST.read_text())


def _malformed(kind):
    manifest = _manifest()
    if kind == "after_image_changes_retained_value":
        manifest["entities"][0]["after"]["governor"] = "Unreviewed replacement"
    elif kind == "after_image_drops_unselected_key":
        del manifest["entities"][0]["after"]["governor"]
    elif kind == "wrong_document":
        manifest["delete_audits"][0]["source_document_id"] = 1837
    elif kind == "new_extraction_link":
        manifest["delete_audits"][0]["extraction_id"] = 777
    elif kind == "new_page_link":
        manifest["delete_audits"][0]["page_ref"] = "p.2"
    elif kind == "retained_nested_number_becomes_boolean":
        entity = manifest["entities"][0]
        entity["before"]["source_projects"] = [{"paid": 1, "verified": False}]
        entity["after"]["source_projects"] = [{"paid": True, "verified": False}]
    elif kind == "retained_nested_boolean_becomes_number":
        entity = manifest["entities"][0]
        entity["before"]["source_projects"] = [{"paid": 0, "verified": False}]
        entity["after"]["source_projects"] = [{"paid": 0, "verified": 0}]
    elif kind == "retained_nested_integer_becomes_float":
        entity = manifest["entities"][0]
        entity["before"]["source_projects"] = [{"paid": 1}]
        entity["after"]["source_projects"] = [{"paid": 1.0}]
    else:
        raise ValueError(kind)
    return manifest


INVALID = [
    "after_image_changes_retained_value",
    "after_image_drops_unselected_key",
    "wrong_document",
    "new_extraction_link",
    "new_page_link",
    "retained_nested_number_becomes_boolean",
    "retained_nested_boolean_becomes_number",
    "retained_nested_integer_becomes_float",
]


@pytest.mark.parametrize("kind", INVALID)
def test_cleanup_direct_rejects_invalid_review_snapshot(kind):
    with pytest.raises(ValueError):
        _renderer()(_malformed(kind))


@pytest.mark.parametrize("kind", INVALID)
def test_cleanup_optimized_python_rejects_before_writing_sql(kind, tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_malformed(kind)))
    output = tmp_path / "rendered"
    result = subprocess.run(
        [sys.executable, "-O", str(SCRIPT), str(manifest), str(output)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0, "optimized Python rendered an unsafe snapshot"
    assert not (output / "cleanup.sql").exists()
    assert not (output / "recover.sql").exists()


def test_cleanup_valid_fixture_renders_guarded_forward_and_recovery():
    forward, recovery = _renderer()(_manifest())
    assert "DELETE FROM audits" in forward
    assert "INSERT INTO audits" in recovery
    assert forward.rstrip().endswith("ROLLBACK;")
    assert recovery.rstrip().endswith("ROLLBACK;")


def test_cleanup_valid_fixture_renders_identically_in_optimized_python(tmp_path):
    output = tmp_path / "rendered"
    result = subprocess.run(
        [sys.executable, "-O", str(SCRIPT), str(MANIFEST), str(output)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    forward, recovery = _renderer()(_manifest())
    assert (output / "cleanup.sql").read_text() == forward
    assert (output / "recover.sql").read_text() == recovery
