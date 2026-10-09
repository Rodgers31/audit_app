"""Copy immutable run receipts and bind the final readiness acceptance packet."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "batch9-native-readiness-evidence"
RAW = Path("/Users/roger/.codex/visualizations/2026/10/03/01a1034a-4799-7f72-a9d1-28c8cfbea53f/BATCH_9_SESSIONS/NATIVE_SCHEMA_READINESS")
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
generators = {digest(path): str(path.relative_to(ROOT)) for path in OUT.glob("run_receipt*.py")}
sources = {str(path.relative_to(ROOT)): digest(path) for path in (
    ROOT / "backend/seeding/exclusion.py", ROOT / "backend/tests/test_batch9_native_schema_readiness.py",
    ROOT / "backend/tests/batch9_native_readiness_fixture/sitecustomize.py")}
current = "green-current-scope-final.json"
minimum = "green-minimum-scope-final.json"
red = "red-final-scope-original.json"
min_red = "red-minimum-scope-original-entry.json"
final_names = {current, minimum, red, min_red, "versions-current.json", "versions-minimum.json"}
for name in (current, minimum):
    receipt = json.loads((RAW / name).read_text())
    assert receipt["source_hashes"] == sources and receipt["exit_code"] == 0
    assert "67 passed" in receipt["output"] and "skipped" not in receipt["output"]
baseline_bytes = subprocess.check_output(["git", "show", "5c68fb1b4454bad60db9bf12f9b7c68ce4549168:backend/seeding/exclusion.py"], cwd=ROOT)
for name in (red, min_red):
    receipt = json.loads((RAW / name).read_text())
    assert receipt["source_hashes"]["backend/seeding/exclusion.py"] == hashlib.sha256(baseline_bytes).hexdigest()
    assert receipt["source_hashes"]["backend/tests/test_batch9_native_schema_readiness.py"] == sources["backend/tests/test_batch9_native_schema_readiness.py"]
    assert receipt["exit_code"] == 1
assert "45 failed, 19 passed" in json.loads((RAW / red).read_text())["output"]
assert "4 failed" in json.loads((RAW / min_red).read_text())["output"]
receipts = {}
(OUT / "receipts").mkdir(exist_ok=True)
for path in RAW.glob("*.json"):
    if path.name.startswith("coordinator-"):
        continue  # coordinator evidence remains independently owned
    receipt = json.loads(path.read_text())
    if "generated_by" not in receipt:
        continue
    assert receipt["generator_sha256"] in generators, path
    copy = OUT / "receipts" / path.name
    shutil.copyfile(path, copy)
    check = json.loads(copy.read_text())
    assert check["generator_sha256"] == receipt["generator_sha256"] and copy.read_bytes() == path.read_bytes()
    receipts[str(copy.relative_to(ROOT))] = {"sha256": digest(copy),
        "retained_generator": generators[receipt["generator_sha256"]],
        "status": "FINAL" if path.name in final_names else "SUPERSEDED",
        "superseded_by": None if path.name in final_names else [current, minimum, red, min_red],
        "reason": None if path.name in final_names else "Historical setup or narrower fixture/generator version; raw receipt is immutable. Final fixtures and generator were replayed against the pinned original source."}
manifest = {"generated_by": str(Path(__file__).relative_to(ROOT)), "generator_sha256": digest(Path(__file__)),
    "generated_at": datetime.now(timezone.utc).isoformat(), "base_commit": "5c68fb1b4454bad60db9bf12f9b7c68ce4549168",
    "source_hashes": sources, "receipts": receipts,
    "results": {"current": "67 passed, 0 skipped", "minimum": "67 passed, 0 skipped",
        "original_current": "45 behavioral failures, 19 positive passes", "original_minimum_selected": "4 behavioral failures"},
    "scope": "Local readiness repair only; overlapping test counts are not additive. No production operation, migration, activation, reconciliation or merge is certified."}
path = OUT / "manifest.json"
path.write_text(json.dumps(manifest, indent=2) + "\n")
check = json.loads(path.read_text())
assert check["generator_sha256"] == digest(Path(__file__)) and check["source_hashes"] == sources
print(json.dumps({"manifest": str(path), "receipts": len(receipts), "source_hashes": sources}, indent=2))
