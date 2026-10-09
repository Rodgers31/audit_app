"""Retire original publication evidence without rewriting any receipt bytes.

The published author commit retains every original generator. Git blob/hash
readback distinguishes immutable history from the repaired current generators.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = "950a0d54ace562acdf1ade46d66dc7fa18d50cb5"
DIRECTORY = ROOT / "batch9-reconciliation-evidence"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def original(path):
    return subprocess.check_output(["git", "show", ORIGINAL + ":" + path], cwd=ROOT)


def main():
    names = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", ORIGINAL,
                                      "--", "batch9-reconciliation-evidence"], cwd=ROOT, text=True).splitlines()
    retired = []
    for name in names:
        if not name.endswith(".json") and name not in {
                "batch9-reconciliation-evidence/spec-review.md", "batch9-reconciliation-evidence/standards-review.md",
                "batch9-reconciliation-evidence/behavior/REPORT.md"}:
            continue
        raw = original(name)
        assert (ROOT / name).read_bytes() == raw, "Historical receipt bytes changed: " + name
        item = {"path": name, "sha256": sha(raw), "status": "SUPERSEDED_FOR_CURRENT_ACCEPTANCE",
                "why": "Original source attribution and credential-bearing publication retired; preserve as historical author evidence only. Use review-repairs.md and the new review packet for current results."}
        if name.endswith(".json"):
            value = json.loads(raw)
            if type(value) is dict and "generated_by" in value:
                generator = value["generated_by"]
                blob = original(generator)
                assert sha(blob) == value["generator_sha256"], name
                item.update(original_generator=generator, original_generator_sha256=sha(blob),
                            original_generator_git_blob=ORIGINAL + ":" + generator)
        retired.append(item)
    assert len(retired) >= 40
    output = DIRECTORY / "publication-supersessions.json"
    assert not output.exists(), "Append-only retirement declaration"
    receipt = {"generated_by": str(Path(__file__).relative_to(ROOT)), "generator_sha256": sha(Path(__file__).read_bytes()),
               "generated_at": datetime.now(timezone.utc).isoformat(), "original_author_commit": ORIGINAL,
               "target_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "superseded_at": datetime.now(timezone.utc).date().isoformat(),
               "untrustworthy_fields": ["unredacted environment/command/output publication", "whole-repository writer coverage", "current-source acceptance attribution"],
               "corrected_answer": "Current active generators use owned untracked fixture inputs and a shared redaction boundary; source census is an explicitly incomplete subset with all tracked omissions listed. Production/operator acceptance remains pending.",
               "historical_artifacts": retired}
    output.write_text(json.dumps(receipt, indent=2) + "\n")
    assert json.loads(output.read_text()) == receipt
    print(f"{len(retired)} immutable historical artifacts explicitly retired; original generator Git blobs verified")


if __name__ == "__main__":
    main()
