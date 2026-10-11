"""The committed #602 packet verifier refuses tampered, rebound and internal outputs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKET = ROOT / "docs/admin/implementation/batch11-issue-602-evidence"
SPEC = importlib.util.spec_from_file_location("batch11_602_verify_packet", PACKET / "tools/verify_packet_v2.py")
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def synthetic_receipt(label, exit_code, owned_hashes):
    cases = [{"id": "tests/test_x.py::test_a", "state": "passed" if exit_code == 0 else "failed"},
             {"id": "tests/test_x.py::test_b", "state": "passed"}]
    counts = dict.fromkeys(verifier.STATES, 0)
    for case in cases:
        counts[case["state"]] += 1
    return {"generated_by": "docs/admin/implementation/batch11-issue-602-evidence/tools/record_v3.py",
            "label": label, "mode": "pytest", "exit_code": exit_code, "complete_inventory": True,
            "timed_out": False, "source_drift": [], "source_files": owned_hashes,
            "testcases": cases, "counts": counts}


@pytest.fixture
def copy(tmp_path):
    """A packet built from synthetic receipts bound to this checkout's real bytes.

    Independent of which receipts are committed, so the verifier's own tests do
    not depend on a final receipt that must itself include these tests.
    """
    target = tmp_path / "packet"
    owned = {p: sha(ROOT / p) for p in ("backend/seeding/domains/cra/parser.py",
                                        "backend/seeding/domains/cra/writer.py", "etl/writer_ownership.py")}
    for label, code in (("red-example", 1), ("final-example", 0)):
        folder = target / "receipts" / label
        folder.mkdir(parents=True)
        (folder / "receipt.json").write_text(json.dumps(synthetic_receipt(label, code, owned)))
    (target / "MANIFEST.json").write_text(json.dumps({"schema": 2, "files": {}}))
    remanifest(target)
    return target


def remanifest(packet):
    manifest = json.loads((packet / "MANIFEST.json").read_text())
    manifest["files"] = {str(p.relative_to(packet)): sha(p) for p in sorted((packet / "receipts").rglob("*")) if p.is_file()}
    (packet / "MANIFEST.json").write_text(json.dumps(manifest))


def final_receipt(packet):
    return next(p for p in sorted((packet / "receipts").glob("final-*/receipt.json")))


def test_committed_packet_has_historical_integrity():
    result = verifier.verify(PACKET, ROOT)
    assert result["historical_integrity"] is True and result["receipts"]


def test_synthetic_packet_bound_to_this_checkout_is_accepted(copy):
    result = verifier.verify(copy, ROOT)
    assert result["historical_integrity"] is True and result["current_checkout_acceptance"] is True
    assert [r["green"] for r in result["receipts"].values()] == [True, False]  # final, red (sorted)


def test_tampered_byte_refuses(copy):
    path = final_receipt(copy)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(verifier.Refused, match="hash mismatch"):
        verifier.verify(copy, ROOT)


@pytest.mark.parametrize("name", ["extra.json", "coverage.xml", ".coverage.backend", "__pycache__/x.pyc"])
def test_unlisted_or_internal_output_refuses(copy, name):
    target = final_receipt(copy).parent / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{}")
    with pytest.raises(verifier.Refused):
        verifier.verify(copy, ROOT)
    remanifest(copy)  # even when listed, an internal output is refused
    if name != "extra.json":
        with pytest.raises(verifier.Refused, match="internal output"):
            verifier.verify(copy, ROOT)


def test_symlinked_receipt_refuses(copy, tmp_path):
    path = final_receipt(copy)
    outside = tmp_path / "outside.json"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(verifier.Refused, match="symlink"):
        verifier.verify(copy, ROOT)


def test_manifest_path_escape_refuses(copy):
    manifest = json.loads((copy / "MANIFEST.json").read_text())
    manifest["files"]["../outside.json"] = "0" * 64
    (copy / "MANIFEST.json").write_text(json.dumps(manifest))
    with pytest.raises(verifier.Refused, match="escapes"):
        verifier.verify(copy, ROOT)


@pytest.mark.parametrize("mutation", ["counts", "duplicate_id", "bool_exit", "empty_complete", "absolute_source"])
def test_malformed_receipt_refuses_even_with_a_matching_manifest(copy, mutation):
    path = final_receipt(copy)
    record = json.loads(path.read_text())
    if mutation == "counts":
        record["counts"]["passed"] += 1
    elif mutation == "duplicate_id":
        record["testcases"].append(dict(record["testcases"][0]))
        record["counts"][record["testcases"][0]["state"]] += 1
    elif mutation == "bool_exit":
        record["exit_code"] = False
    elif mutation == "empty_complete":
        record["testcases"], record["counts"] = [], dict.fromkeys(record["counts"], 0)
    else:
        record["source_files"]["/etc/passwd"] = "0" * 64
    path.write_text(json.dumps(record))
    remanifest(copy)
    with pytest.raises(verifier.Refused):
        verifier.verify(copy, ROOT)


def test_rebound_source_keeps_integrity_but_not_current_acceptance(copy):
    path = final_receipt(copy)
    record = json.loads(path.read_text())
    owned = next(k for k in record["source_files"] if k.startswith("backend/seeding/domains/cra/"))
    record["source_files"][owned] = "0" * 64
    path.write_text(json.dumps(record))
    remanifest(copy)
    result = verifier.verify(copy, ROOT)
    assert result["historical_integrity"] is True and result["current_checkout_acceptance"] is False
    assert owned in result["source_mismatch_sample"]


def test_red_final_receipt_is_not_acceptance(copy):
    path = final_receipt(copy)
    record = json.loads(path.read_text())
    record["exit_code"] = 1
    path.write_text(json.dumps(record))
    remanifest(copy)
    assert verifier.verify(copy, ROOT)["current_checkout_acceptance"] is False
