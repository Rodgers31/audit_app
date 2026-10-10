"""Retain the pre-hosted tools/context and append a one-time correction label."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
ORIGINAL_HEAD = "6db43b4a806f7006f7b14631f6f01bff7f5b3db7"
FOLDER = ROOT / "docs/admin/implementation/batch10-readiness-evidence"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    generator = Path(__file__).resolve()
    generator_hash = sha(generator.read_bytes())
    history = FOLDER / "history/hosted-2026-10-10"
    history.mkdir()
    retained = []
    for path, filename in (
        ("docs/admin/implementation/batch10-readiness-evidence/verify_package.py", "verify_package.py.txt"),
        ("backend/tests/test_batch10_startup_readiness_receipts.py", "test_batch10_startup_readiness_receipts.py.txt"),
        ("backend/tests/financial_literal_reviewed_inventory.json", "financial_literal_reviewed_inventory.json.txt"),
    ):
        original = subprocess.check_output(["git", "-C", str(ROOT), "show", ORIGINAL_HEAD + ":" + path])
        destination = history / filename
        with destination.open("xb") as stream:
            stream.write(original)
        if destination.read_bytes() != original:
            raise RuntimeError("Historical snapshot readback mismatch")
        retained.append({"source_head": ORIGINAL_HEAD, "original_path": path,
                         "retained_path": str(destination.relative_to(ROOT)),
                         "sha256": sha(original), "bytes": len(original)})
    replacement = [
        {"path": row["original_path"], "sha256": sha((ROOT / row["original_path"]).read_bytes())}
        for row in retained
    ]
    record = {
        "schema": 1, "generated_by": str(generator.relative_to(ROOT)),
        "generator_sha256": generator_hash, "generated_at": "2026-10-10",
        "classification": "hosted_verifier_and_context_correction_publication",
        "issues": [591, 616], "original_head": ORIGINAL_HEAD,
        "original_tool_and_context": retained, "replacement_files": replacement,
        "historical_current_checkout_acceptance": False,
        "historical_disposition": "Original receipts retain their source, generator, counts, verdicts and bytes; they do not certify this changed candidate. The f75 full hosted run failed five backend and ten browser cases and is diagnostic, not acceptance.",
        "mechanism": "Verifier import wrote a new measured __pycache__ file when bytecode was enabled. Prevent the import write and restore the caller flag; retain every measured file and all tamper refusals. This is not historical sibling-source copying.",
        "context_review": "docs/verification/2026-10-10-batch10-finance-context-review.md",
        "current_acceptance": "Separate external executions must bind the final full consumed source HEAD/tree/corpus. Frozen full hosted acceptance remains a coordinator gate.",
        "unchanged_historical_packets": {
            path: sha((ROOT / path).read_bytes()) for path in (
                "docs/admin/implementation/batch10-readiness-evidence/MANIFEST.json",
                "docs/admin/implementation/batch10-readiness-evidence/COPILOT_CORRECTION_2026_10_10.json",
                "docs/verification/2026-10-09-batch9-finance-context-review.md",
            )
        },
    }
    destination = FOLDER / "HOSTED_CORRECTION_2026_10_10.json"
    with destination.open("x") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    if json.loads(destination.read_text()) != record or sha(generator.read_bytes()) != generator_hash:
        raise RuntimeError("Correction publication readback mismatch")
    print(destination.relative_to(ROOT))


if __name__ == "__main__":
    main()
