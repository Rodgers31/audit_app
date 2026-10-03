"""Offline image attacks; real PostgreSQL capture is a separate bounded control."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/verification"))
import oag_acceptance_images as images
from seeding.extractors.oag_blue_book import source_hash_of


def image(stage="catchup"):
    sources = {url: {"id": i + 1, "url": url, "country_id": 1, "publisher": "Office of the Auditor-General", "doc_type": "AUDIT"}
               for i, url in enumerate(images.accepted_editions())}
    selected = {e["source_url"] for e in images.parse_manifest(images.read_manifest(ROOT / images.PINS[1]))}
    rows = json.loads((ROOT / "backend/tests/fixtures/oag_boundary_correction_before.json").read_bytes())["rows"]
    return {"schema": "oag_acceptance_image/v1", "stage": stage, "operation": "synthetic-independent-comparison",
            "captured_at": "2026-10-03T00:00:00+00:00", "generator_sha256": images.file_sha(images.__file__),
            "pins": {p: images.file_sha(ROOT / p) for p in images.PINS},
            "database_identity_sha256": "0" * 64, "transaction": {"read_only": "on", "isolation": "repeatable read"},
            "source_country": {"id": 1, "iso_code": "KEN"},
            "county_identities": {str(c): f"Synthetic county {c}" for c in range(1, 48)},
            "sources": sources, "selected_ids": sorted(sources[u]["id"] for u in selected),
            "protected": {t: {"columns": [[c, "text", "pg_catalog", "text", "YES"] for c in sorted(images.model_columns()[t])], "count": 8, "sha256": "1" * 64} for t in images.TABLES},
            "trim_rows": {t: [r[k] for r in rows] for t, k in (("audits", "audit"), ("extractions", "extraction"))}}


def covered(after):
    editions = images.accepted_editions()
    cells = [{"county_id": c, "county": f"Synthetic county {c}", "fiscal_year": fy, "institution": role, "findings": 1}
             for c in range(1, 48) for fy in sorted({e["fiscal_year"] for e in editions.values()}) for role in ("executives", "assemblies")]
    receipt = {"listing_job_id": 1, "listing_read_at": after["captured_at"], "required_years": sorted({e["fiscal_year"] for e in editions.values()}),
               "counties_by_year": {str(int(fy[5:])): 47 for fy in {e["fiscal_year"] for e in editions.values()}},
               "county_count": 47, "expected_county_count": 47, "cells": cells, "run_gaps": []}
    after["coverage"] = {"receipt": receipt, "level": "OK", "message": "synthetic"}
    after["edition_proofs"] = [{"url": url, "source_document_id": after["sources"][url]["id"], "fiscal_year": e["fiscal_year"], "institution": e["institution"],
                                "md5": e["md5"], "sha256": e["sha256"], "findings": 47, "chapters": 47, "size_bytes": 10,
                                "state_sha256": "2" * 64, "binding": "legacy_extracted_md5_complete_parser"} for url, e in editions.items()]
    return after


def trim_pair():
    before = image("trim"); after = copy.deepcopy(before)
    manifest = json.loads((ROOT / images.PINS[0]).read_bytes())
    fixture = json.loads((ROOT / "backend/tests/fixtures/oag_boundary_correction_before.json").read_bytes())["rows"]
    plan = {"schema": "oag_boundary_correction/v1", "manifest_sha256": images.file_sha(ROOT / images.PINS[0]),
            "source_sha256": manifest["source_sha256"], "before": fixture, "after": copy.deepcopy(fixture)}
    for mr, a, x, row in zip(manifest["changed_rows"], after["trim_rows"]["audits"], after["trim_rows"]["extractions"], plan["after"], strict=True):
        a["finding_text"] = x["extracted_json"]["finding_text"] = mr["after"]["text"]
        a["source_hash"] = source_hash_of(x["extracted_json"])
        row["audit"] = copy.deepcopy(a); row["extraction"] = copy.deepcopy(x)
    return before, after, plan


def test_exact_catchup_preservation_and_376_distinct_cells():
    before = image(); after = covered(copy.deepcopy(before))
    assert images.compare(before, after, require_coverage=True)["preservation_passed"]


def test_exact_reviewed_trim_changes_only_text_and_json_hash():
    before, after, plan = trim_pair()
    assert images.compare(before, after, plan=plan, expected_plan_sha256=images.boundary.digest(plan))["preservation_passed"]


@pytest.mark.parametrize("table", images.TABLES)
@pytest.mark.parametrize("field,value", [("count", 9), ("sha256", "3" * 64), ("columns", [["new", "text"]])])
def test_every_protected_table_and_full_schema_change_is_visible(table, field, value):
    before = image(); after = copy.deepcopy(before)
    after["protected"][table][field] = after["protected"][table][field] + [["extra", "text", "pg_catalog", "text", "YES"]] if field == "columns" else value
    assert not images.compare(before, after)["preservation_passed"]


@pytest.mark.parametrize("attack", ["missing_table", "zero_count", "boolean_count", "bad_hash", "missing_source", "duplicate_source", "boolean_id", "bad_selected", "lost_trim", "producer", "pin", "transaction", "empty_operation"])
def test_malformed_images_refuse_even_when_both_match(attack):
    before = image()
    if attack == "missing_table": before["protected"].pop("audits")
    elif attack == "zero_count": before["protected"]["audits"]["count"] = 0
    elif attack == "boolean_count": before["protected"]["audits"]["count"] = True
    elif attack == "bad_hash": before["protected"]["audits"]["sha256"] = "bad"
    elif attack == "missing_source": before["sources"].pop(next(iter(before["sources"])))
    elif attack == "duplicate_source": list(before["sources"].values())[1]["id"] = list(before["sources"].values())[0]["id"]
    elif attack == "boolean_id": next(iter(before["sources"].values()))["id"] = True
    elif attack == "bad_selected": before["selected_ids"] = []
    elif attack == "lost_trim": before["trim_rows"]["extractions"] = []
    elif attack == "producer": before["generator_sha256"] = "0" * 64
    elif attack == "pin": before["pins"] = {}
    elif attack == "transaction": before["transaction"]["read_only"] = "off"
    else: before["operation"] = ""
    with pytest.raises(ValueError): images.compare(before, copy.deepcopy(before))


@pytest.mark.parametrize("attack", ["missing", "duplicate_cells", "zero_findings", "bool_findings", "missing_year", "wrong_role", "missing_proof", "fake_proof", "wrong_proof_source", "wrong_proof_hash", "bool_chapters", "bool_coverage", "run_gap"])
def test_claimed_coverage_without_full_distinct_qualified_authority_refuses(attack):
    before = image(); after = covered(copy.deepcopy(before)); c = after["coverage"]["receipt"]
    if attack == "missing": after.pop("coverage")
    elif attack == "duplicate_cells": c["cells"] = [c["cells"][0]] * 376
    elif attack == "zero_findings": c["cells"][0]["findings"] = 0
    elif attack == "bool_findings": c["cells"][0]["findings"] = True
    elif attack == "missing_year": c["required_years"].pop()
    elif attack == "wrong_role": c["cells"][0]["institution"] = "national"
    elif attack == "missing_proof": after["edition_proofs"].pop()
    elif attack == "fake_proof": after["edition_proofs"] = [{"url": p["url"]} for p in after["edition_proofs"]]
    elif attack == "wrong_proof_source": after["edition_proofs"][0]["source_document_id"] += 1
    elif attack == "wrong_proof_hash": after["edition_proofs"][0]["sha256"] = "0" * 64
    elif attack == "bool_chapters": after["edition_proofs"][0]["chapters"] = True
    elif attack == "bool_coverage": after["coverage"]["level"] = True
    else: c["run_gaps"] = ["observation refused"]
    assert not images.compare(before, after, require_coverage=True)["preservation_passed"]


@pytest.mark.parametrize("field,value", [("recommended_action", "unreviewed"), ("amount", "1.00"), ("page_ref", "p.1"), ("source_hash", "0" * 64)])
def test_rehashed_plan_cannot_authorize_other_audit_fields(field, value):
    before, after, plan = trim_pair()
    after["trim_rows"]["audits"][0][field] = value; plan["after"][0]["audit"][field] = value
    assert not images.compare(before, after, plan=plan, expected_plan_sha256=images.boundary.digest(plan))["preservation_passed"]


def test_source_identity_and_trim_rows_remain_protected_in_catchup():
    before = image(); after = copy.deepcopy(before)
    next(iter(after["sources"].values()))["publisher"] = "unreviewed"
    after["trim_rows"]["audits"][0]["finding_text"] = "unreviewed"
    with pytest.raises(ValueError): images.compare(before, after)
    next(iter(after["sources"].values()))["publisher"] = "Office of the Auditor-General"
    assert images.compare(before, after)["gaps"] == ["catch-up changed protected corrected text rows"]


def test_incomplete_schema_image_and_reversed_time_and_wrong_stage_refuse():
    before = image(); after = copy.deepcopy(before)
    after["captured_at"] = "2026-10-02T00:00:00+00:00"
    with pytest.raises(ValueError): images.compare(before, after)
    before["protected"]["audits"]["columns"] = [["id", "integer", "pg_catalog", "int4", "NO"]]
    with pytest.raises(ValueError): images.compare(before, copy.deepcopy(before))
    before, after, plan = trim_pair()
    with pytest.raises(ValueError): images.compare(before, after, plan=plan, expected_plan_sha256=images.boundary.digest(plan), require_coverage=True)
