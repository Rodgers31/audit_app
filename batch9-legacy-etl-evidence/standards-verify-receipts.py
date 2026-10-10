"""Read back independently replayed results and bind them to the current source."""
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
for kind in ("session", "readiness"):
    for runtime in ("", "minimum-"):
        name = f"standards-{kind}-final-{runtime}independent.json"
        receipt = json.loads((EVIDENCE / name).read_text())
        valid = (receipt["exit_code"] == 0 and receipt["verdict"] == "PASSED"
            and receipt["generator_sha256"] == generator
            and receipt["source_sha256"]["etl/writer_ownership.py"] == source
            and '"verdict": "PASSED"' in receipt["output"])
        results.append({"receipt": name, "python": receipt["python"], "verified": valid})
    probe = json.loads((EVIDENCE / f"standards-{kind}-probe.json").read_text())
    assert probe["generator_sha256"] == hashlib.sha256((EVIDENCE / f"standards-{kind}-probe.py").read_bytes()).hexdigest()
    assert probe["verdict"] == "PASSED"
verified = all(result["verified"] for result in results)
output = {"generated_by": str(Path(__file__).relative_to(ROOT)),
    "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "command": [sys.executable, str(Path(__file__).resolve())],
    "python": platform.python_version(), "replay_generator_sha256": generator,
    "writer_source_sha256": source, "results": results,
    "verdict": "PASSED" if verified else "FAILED"}
path = EVIDENCE / "standards-replay-readback.json"
path.write_text(json.dumps(output, indent=2) + "\n")
assert json.loads(path.read_text()) == output
print(json.dumps(output, indent=2))
sys.exit(0 if verified else 1)
