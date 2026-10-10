"""Read back final refusal/storage/session controls against their exact source."""
import hashlib
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "batch9-legacy-etl-evidence"
generator = hashlib.sha256((EVIDENCE / "run_receipt.py").read_bytes()).hexdigest()
source = hashlib.sha256((ROOT / "etl/writer_ownership.py").read_bytes()).hexdigest()
results = []
for kind in ("session", "readiness", "refusal"):
    for runtime in ("", "minimum-"):
        name = f"standards-{kind}-final2-{runtime}independent.json"
        receipt = json.loads((EVIDENCE / name).read_text())
        valid = (receipt["exit_code"] == 0 and receipt["verdict"] == "PASSED"
            and receipt["generator_sha256"] == generator
            and receipt["source_sha256"]["etl/writer_ownership.py"] == source)
        if kind == "refusal":
            control_hash = hashlib.sha256((EVIDENCE / "refusal_storage_control.py").read_bytes()).hexdigest()
            valid &= (f"control_sha256={control_hash}" in receipt["output"]
                and "refusal_exception=DomainOwnershipError" in receipt["output"]
                and "effects=0; retained=1" in receipt["output"])
        else:
            probe_hash = hashlib.sha256((EVIDENCE / f"standards-{kind}-probe.py").read_bytes()).hexdigest()
            valid &= probe_hash in receipt["output"] and '"verdict": "PASSED"' in receipt["output"]
        results.append({"receipt": name, "python": receipt["python"], "verified": bool(valid)})
verified = all(result["verified"] for result in results)
output = {"generated_by": str(Path(__file__).relative_to(ROOT)),
    "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "command": [sys.executable, str(Path(__file__).resolve())],
    "python": platform.python_version(), "replay_generator_sha256": generator,
    "writer_source_sha256": source, "results": results,
    "verdict": "PASSED" if verified else "FAILED"}
path = EVIDENCE / "standards-final-replay-readback.json"
path.write_text(json.dumps(output, indent=2) + "\n")
assert json.loads(path.read_text()) == output
print(json.dumps(output, indent=2))
sys.exit(0 if verified else 1)
