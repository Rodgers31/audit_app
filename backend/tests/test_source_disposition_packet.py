"""Execute the offline packet and drift guards using owned local PostgreSQL."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "source_disposition", ROOT / "tools/prepare_source_disposition.py"
)
disposition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(disposition)
CAPTURE = (
    ROOT
    / "docs/operations/2026-10-03-round21-source-disposition/synthetic-test-capture.json"
)


def capture():
    return json.loads(CAPTURE.read_text())


@pytest.mark.parametrize(
    "change",
    [
        "old_packet",
        "missing_image",
        "bool_id",
        "float_id",
        "foreign_country",
        "publisher",
        "origin",
        "metadata_list",
        "missing_refs",
        "new_ref",
        "missing_fk",
        "duplicate_fk",
        "logical_ref",
        "nonfinite",
        "sql_delimiter",
    ],
)
def test_renderer_refuses_incomplete_or_unreviewed_input(change):
    value = capture()
    if change == "old_packet":
        value["schema"] = "round21_source_disposition_packet/v1"
    elif change == "missing_image":
        del value["sources"][0]["created_at"]
    elif change == "bool_id":
        value["sources"][0]["id"] = True
    elif change == "float_id":
        value["sources"][0]["id"] = 1707.0
    elif change == "foreign_country":
        value["sources"][0]["country_id"] = 2
    elif change == "publisher":
        value["sources"][0]["publisher"] = "CRA"
    elif change == "origin":
        value["sources"][0]["metadata"]["dataset_id"] = "official"
    elif change == "metadata_list":
        value["sources"][0]["metadata"] = []
    elif change == "missing_refs":
        value["source_references"].pop()
    elif change == "new_ref":
        value["source_references"][0]["rows"] = [
            {"id": 100, "source_document_id": 1707}
        ]
    elif change == "missing_fk":
        value["foreign_keys"].pop()
    elif change == "duplicate_fk":
        value["foreign_keys"][0]["conname"] = value["foreign_keys"][1]["conname"]
    elif change == "logical_ref":
        value["logical_matches"] = [{"source_document_id": 1718}]
    elif change == "nonfinite":
        value["sources"][0]["metadata"]["unknown"] = float("nan")
    elif change == "sql_delimiter":
        value["sources"][0]["metadata"]["unknown"] = "$source_disposition_319$"
    with pytest.raises(ValueError):
        disposition.render(value)


def test_proposal_preserves_source_identity_and_all_original_metadata():
    value = capture()
    for s in value["sources"]:
        s["metadata"]["retained"] = {
            "flag": True,
            "amount": 1,
            "float": 1.0,
            "projects": [],
        }
    before = copy.deepcopy(value)
    plan, forward, inverse = disposition.render(value)
    assert value == before
    for change in plan["changes"]:
        old, new = change["before"], change["after"]
        assert {
            k: v for k, v in new.items() if k not in ("publisher", "status", "metadata")
        } == {
            k: v for k, v in old.items() if k not in ("publisher", "status", "metadata")
        }
        assert new["status"] == "ARCHIVED"
        assert new["publisher"].startswith("AuditGava (")
        assert {k: new["metadata"][k] for k in old["metadata"]} == old["metadata"]
    assert forward.rstrip().endswith("ROLLBACK;")
    assert inverse.rstrip().endswith("ROLLBACK;")


@pytest.mark.parametrize(
    "field,value",
    [
        ("file_path", {}),
        ("fetch_date", False),
        ("md5", []),
        ("content_type", {}),
        ("http_status", True),
        ("last_verified_at", 123),
        ("last_seen_at", 123),
        ("created_at", 123),
        ("fetch_date", "2026-02-31T12:00:00"),
        ("fetch_date", "2026-10-03"),
        ("md5", "z" * 32),
        ("http_status", 200.0),
        ("http_status", 0),
    ],
)
def test_complete_field_names_do_not_certify_malformed_source_values(field, value):
    value_capture = capture()
    value_capture["sources"][0][field] = value
    with pytest.raises(ValueError):
        disposition.render(value_capture)


@pytest.mark.parametrize(
    "kind", ["missing", "empty", "duplicate", "partial", "unknown", "malformed"]
)
def test_renderer_requires_exact_complete_logical_column_catalogue(kind):
    value = capture()
    if kind == "missing":
        del value["logical_scan_columns"]
    elif kind == "empty":
        value["logical_scan_columns"] = []
    elif kind == "duplicate":
        value["logical_scan_columns"][0] = value["logical_scan_columns"][1]
    elif kind == "partial":
        value["logical_scan_columns"].pop()
    elif kind == "unknown":
        value["logical_scan_columns"][0]["table"] = "unreviewed_table"
    elif kind == "malformed":
        value["logical_scan_columns"][0]["column"] = True
    with pytest.raises(ValueError):
        disposition.render(value)
