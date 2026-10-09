"""Read back every lane receipt and bind it to its unchanged generator/output."""
import hashlib
import json
from pathlib import Path

here = Path(__file__).resolve().parent
root = here.parents[3]
receipts = sorted(here.rglob("*.json"))
assert receipts, "No receipts were examined"
for path in receipts:
    data = json.loads(path.read_text())
    generator = root / data["generated_by"]
    assert hashlib.sha256(generator.read_bytes()).hexdigest() == data["generator_sha256"], path
    assert hashlib.sha256(path.with_suffix(".txt").read_bytes()).hexdigest() == data["output_sha256"], path
    assert (data["exit_code"] == 0) == (data["verdict"] == "PASSED"), path
spec_generator = hashlib.sha256((here / "spec-readiness-control.py").read_bytes()).hexdigest()
for name in ("spec-readiness-red", "spec-readiness-green", "spec-readiness-green-minimum"):
    data, _ = json.JSONDecoder().raw_decode((here / (name + ".txt")).read_text())
    assert data["control_sha256"] == spec_generator, name
print(f"Verified {len(receipts)} JSON receipts and 3 independent Spec raw receipts")
print("generator_sha256", hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
