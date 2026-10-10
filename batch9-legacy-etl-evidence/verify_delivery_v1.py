"""Read back final delivery receipts, immutable generators and archived output."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

root = Path(__file__).resolve().parents[1]
evidence = root / "batch9-legacy-etl-evidence"
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def read(name):
    return json.loads((evidence / name).read_text())

writer = digest(root / "etl/writer_ownership.py")
wrapper = digest(evidence / "run_receipt.py")
assert wrapper == "519b548f3760f324c3a44fa2616a2e56ff4819d6fa9f5909a94e0d14868011bd"
finals = ["process-final-minimum.json", "process-final-current.json", "critical-lint-final.json",
          "refusal-storage-green-current.json", "refusal-storage-green-minimum.json",
          "refusal-storage-final-spec-independent.json", "spec-refusal-final-independent-green.json",
          "spec-session-final-independent-green.json", "spec-scheduler-final-independent-green.json"]
finals += [f"standards-{kind}-final2-{runtime}independent.json"
           for kind in ("session", "readiness", "refusal-storage") for runtime in ("", "minimum-")]
checked = []
for name in finals:
    receipt = read(name)
    assert receipt["exit_code"] == 0 and receipt["verdict"] == "PASSED", name
    assert receipt["generator_sha256"] == wrapper, name
    assert receipt["source_sha256"]["etl/writer_ownership.py"] == writer, name
    for path, expected in receipt["source_sha256"].items():
        assert digest(root / path) == expected, (name, path)
    if name.startswith("process-final"):
        assert "77 passed" in receipt["output"] and "skipped" not in receipt["output"] and "xfailed" not in receipt["output"]
    checked.append(name)
for name in ("behavior-review-recheck-acceptance.json", "standards-final-replay-readback.json"):
    assessment = read(name)
    assert assessment["verdict"] == "PASSED", name
    assert digest(root / assessment["generated_by"]) == assessment["generator_sha256"], name
    checked.append(name)
for runtime in ("minimum", "current"):
    for kind in ("", "cancellation-", "dynamic-binds-", "refusal-storage-"):
        name = f"behavior-review-recheck-{kind}{runtime}.json"
        receipt = read(name)
        assert receipt["source_sha256"]["etl/writer_ownership.py"] == writer, name
        assert receipt["start_source_sha256"] == receipt["source_sha256"], name
        assert digest(root / receipt["generated_by"]) == receipt["generator_sha256"], name
        for path, expected in receipt["source_sha256"].items():
            assert digest(root / path) == expected, (name, path)
        checked.append(name)
red = read("baseline-final-red.json")
assert red["exit_code"] == 1 and "3 failed, 57 deselected" in red["output"]
assert "etl/writer_ownership.py" not in red["source_sha256"]
base = "9e97ca3f1ca43f103a8655447a86d889456a218a"
for path in ("etl/backfill.py", "etl/database_loader.py", "etl/kenya_pipeline.py", "etl/monitored_runner.py", "etl/scheduler.py", "etl/worker.py"):
    actual = subprocess.check_output(["git", "show", base + ":" + path], cwd=root)
    assert hashlib.sha256(actual).hexdigest() == red["source_sha256"][path], path
for path in ("backend/tests/test_batch9_legacy_etl_ownership.py", "backend/tests/batch9_legacy_fixture/sitecustomize.py", "backend/tests/batch9_legacy_fixture/entry.py"):
    assert red["source_sha256"][path] == read("process-final-current.json")["source_sha256"][path] == digest(root / path), path
assert read("baseline-replay-execution.json")["exit_code"] == 0
assert "owned_candidate_bytes_restored=true" in read("baseline-replay-execution.json")["output"]
manifest = json.loads((evidence / "process-logs/manifest.json").read_text())
assert digest(root / manifest["generated_by"]) == manifest["generator_sha256"]
for record in manifest["records"]:
    assert digest(root / record["archive"]) == record["archive_sha256"]
    with tarfile.open(root / record["archive"], "r:gz") as archive:
        for member, expected in record["files"].items():
            assert hashlib.sha256(archive.extractfile(member).read()).hexdigest() == expected
artifacts = {str(path.relative_to(root)): digest(path) for path in sorted(evidence.rglob("*"))
             if path.is_file() and path.name != "delivery-provenance.json"}
output = {"generated_by": str(Path(__file__).relative_to(root)), "generator_sha256": digest(Path(__file__)),
          "command": ["python", str(Path(__file__).relative_to(root))], "base": base,
          "implementation_source_sha256": {path: digest(root / path) for path in read("process-final-current.json")["source_sha256"]},
          "checked_receipts": checked, "unchanged_red_green_measurements": True,
          "expected_baseline_failures": 3, "final_passes_each_runtime": 77,
          "artifact_sha256": artifacts, "verdict": "PASSED"}
path = evidence / "delivery-provenance.json"
path.write_text(json.dumps(output, indent=2) + "\n")
assert json.loads(path.read_text()) == output
print(f"PASSED: {len(checked)} final receipts/assessments, {len(artifacts)} artifact hashes, unchanged red/green measurements")
