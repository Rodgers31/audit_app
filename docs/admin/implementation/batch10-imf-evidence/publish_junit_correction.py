"""Append JUnit admission correction, retaining every prior publication byte."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
PACKET = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    prior = PACKET / "COPILOT_CORRECTION_2026_10_10.json"
    retained = json.loads(
        (PACKET / "history/junit-2026-10-10/provenance.json").read_text()
    )
    original = subprocess.check_output(
        [
            "git",
            "-C",
            str(ROOT),
            "show",
            retained["source_head"] + ":" + retained["original_path"],
        ]
    )
    if original != (ROOT / retained["retained_path"]).read_bytes():
        raise RuntimeError("Historical verifier snapshot differs")
    record = {
        "schema": 1,
        "generated_by": str(Path(__file__).relative_to(ROOT)),
        "generator_sha256": sha(Path(__file__)),
        "generated_at": "2026-10-10",
        "issue": 608,
        "classification": "current_junit_admission_correction",
        "superseded_publication": {
            "path": str(prior.relative_to(ROOT)),
            "sha256": sha(prior),
            "current_checkout_acceptance": False,
        },
        "original_tool": retained,
        "replacement_tool": {
            "path": str((PACKET / "verify_evidence.py").relative_to(ROOT)),
            "sha256": sha(PACKET / "verify_evidence.py"),
        },
        "change": "Current acceptance requires unique nonempty classname/name pairs. Historical recorded selections retain honest counts without being relabelled current.",
        "historical_duplicate_selection_limitations": [
            "full-cohort/receipt.json",
            "spec-repaired-1/receipt.json",
        ],
        "current_acceptance": "A separate external final source-bound execution and real producer/verifier check is required; prior b50 runs retain their original HEAD/tree/corpus.",
        "original_manifest_sha256": sha(PACKET / "manifest.json"),
    }
    destination = PACKET / "JUNIT_CORRECTION_2026_10_10.json"
    with destination.open("x") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    if (
        json.loads(destination.read_text()) != record
        or sha(Path(__file__)) != record["generator_sha256"]
    ):
        raise RuntimeError("Publication readback differs")
    print(destination.relative_to(ROOT))


if __name__ == "__main__":
    main()
