"""Append correction labels while preserving original tool/receipt identities."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
PACKETS = ROOT / "docs/admin/implementation"
ORIGINAL_HEAD = "ad4a9f76f944514c414465643a72f2cee0b1bc19"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    generator = Path(__file__).resolve()
    generator_hash = sha(generator)
    for packet, tool, thread, change in (
        (
            "batch10-readiness-evidence",
            "record.py",
            "4237305236",
            "Child credential inputs remain unchanged; portable environment values are redacted with boolean presence metadata.",
        ),
        (
            "batch10-imf-evidence",
            "verify_evidence.py",
            "4237305222",
            "Current receipts, outputs and fixture database must be external to consumed source and have no symlink/escape components.",
        ),
    ):
        folder = PACKETS / packet
        historical = folder / "history/copilot-2026-10-10/provenance.json"
        retained = json.loads(historical.read_text())
        snapshot = ROOT / retained["retained_path"]
        original = subprocess.check_output(
            [
                "git",
                "-C",
                str(ROOT),
                "show",
                ORIGINAL_HEAD + ":" + retained["original_path"],
            ]
        )
        if snapshot.read_bytes() != original or sha(snapshot) != retained["sha256"]:
            raise RuntimeError("Historical tool snapshot differs")
        correction = {
            "schema": 1,
            "generated_by": str(generator.relative_to(ROOT)),
            "generator_sha256": generator_hash,
            "generated_at": "2026-10-10",
            "review_comment": thread,
            "classification": "tool_correction_publication",
            "historical_current_checkout_acceptance": False,
            "historical_disposition": "Superseded for current checkout acceptance; retained as records of their original executions, with no source/generator/count rebinding.",
            "original_tool": retained,
            "replacement_tool": {
                "path": str((folder / tool).relative_to(ROOT)),
                "sha256": sha(folder / tool),
            },
            "change": change,
            "current_acceptance": "Requires a separate external execution receipt whose complete source HEAD/tree/corpus matches the final committed checkout.",
            "original_manifest": {
                "path": str(
                    (
                        folder
                        / (
                            "MANIFEST.json"
                            if packet == "batch10-readiness-evidence"
                            else "manifest.json"
                        )
                    ).relative_to(ROOT)
                )
            },
        }
        correction["original_manifest"]["sha256"] = sha(
            ROOT / correction["original_manifest"]["path"]
        )
        destination = folder / "COPILOT_CORRECTION_2026_10_10.json"
        with destination.open("x") as stream:
            json.dump(correction, stream, indent=2)
            stream.write("\n")
        if (
            json.loads(destination.read_text()) != correction
            or sha(generator) != generator_hash
        ):
            raise RuntimeError("Correction provenance readback mismatch")
        print(destination.relative_to(ROOT))


if __name__ == "__main__":
    main()
