"""Append acceptance for the reviewed SQLite identifier-case correction."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "batch9-native-readiness-evidence"
RAW = Path("/Users/roger/.codex/visualizations/2026/10/03/01a1034a-4799-7f72-a9d1-28c8cfbea53f/BATCH_9_SESSIONS/NATIVE_SCHEMA_READINESS")
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
sources = {str(path.relative_to(ROOT)): digest(path) for path in (
    ROOT / "backend/seeding/exclusion.py", ROOT / "backend/tests/test_batch9_native_schema_readiness.py",
    ROOT / "backend/tests/batch9_native_readiness_fixture/sitecustomize.py")}
names = ("green-current-case-final.json", "green-minimum-case-final.json",
    "red-sqlite-case-v1-current.json", "red-sqlite-case-v1-minimum.json", "lint-case-final.json")
reviewed_source = "5b8963f6d82397bf6bdec43c10de3b487c18f922017ce121dd47f40613920e6f"
receipts = {}
for name in names:
    original = RAW / name
    receipt = json.loads(original.read_text())
    assert receipt["generator_sha256"] == digest(OUT / "run_receipt.py")
    if name.startswith("red-"):
        assert receipt["source_hashes"]["backend/seeding/exclusion.py"] == reviewed_source
        assert receipt["source_hashes"]["backend/tests/test_batch9_native_schema_readiness.py"] == sources["backend/tests/test_batch9_native_schema_readiness.py"]
        assert receipt["exit_code"] == 1 and "6 failed" in receipt["output"]
    else:
        assert receipt["source_hashes"] == sources and receipt["exit_code"] == 0
        if name.startswith("green-"):
            assert "73 passed" in receipt["output"] and "skipped" not in receipt["output"]
    copy = OUT / "receipts" / name
    if copy.exists():
        assert copy.read_bytes() == original.read_bytes(), "Receipts are immutable"
    else:
        shutil.copyfile(original, copy)
    assert json.loads(copy.read_text())["generator_sha256"] == digest(OUT / "run_receipt.py")
    receipts[str(copy.relative_to(ROOT))] = {"sha256": digest(copy), "retained_generator": "batch9-native-readiness-evidence/run_receipt.py", "status": "FINAL"}
previous_path = OUT / "manifest.json"
previous = json.loads(previous_path.read_text())
assert previous["generator_sha256"] == digest(OUT / "finalize_evidence.py")
for name, old in previous["receipts"].items():
    assert digest(ROOT / name) == old["sha256"]
    receipts[name] = {**old, "status": "SUPERSEDED", "superseded_by": list(names),
        "reason": "Historical initial readiness acceptance; independent Standards review later reproduced SQLite ASCII-case TEMP shadow admission. Its exact raw observations and retained generators remain unchanged. This manifest certifies the corrected source."}
manifest = {"generated_by": str(Path(__file__).relative_to(ROOT)), "generator_sha256": digest(Path(__file__)),
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "base_commit": "5c68fb1b4454bad60db9bf12f9b7c68ce4549168", "source_hashes": sources,
    "supersedes_manifest": {"path": str(previous_path.relative_to(ROOT)), "sha256": digest(previous_path),
        "reason": "SQLite metadata names require the same ASCII case identity as SQLite SQL resolution. Previous67-test acceptance did not cover uppercase/mixed-case TEMP shadows."},
    "receipts": receipts, "results": {"current": "73 passed, 0 skipped", "minimum": "73 passed, 0 skipped",
        "reviewed_v1_current": "6 behavioral failures", "reviewed_v1_minimum": "6 behavioral failures"},
    "historical_original_acceptance": "Previous64 new tests:45 behavioral failures/19 positive passes on original source; prior minimum four entry reds. Counts are historical and overlap final selections.",
    "scope": "Local admission repair only; no production, deployment, release, activation or merge certification."}
path = OUT / "manifest-case-final.json"
assert not path.exists(), "Append a new named manifest rather than overwrite a receipt"
path.write_text(json.dumps(manifest, indent=2) + "\n")
check = json.loads(path.read_text())
assert check["generator_sha256"] == digest(Path(__file__)) and check["source_hashes"] == sources
print(json.dumps({"manifest": str(path), "source_hashes": sources, "receipts": len(receipts)}, indent=2))
