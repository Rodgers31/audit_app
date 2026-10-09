"""Verify immutable historical evidence and independently bind new source receipts."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(here=HERE, root=ROOT):
    history = json.loads((here / "historical-provenance.json").read_text())
    receipts = sorted(p for p in here.rglob("*.json") if p.name != "historical-provenance.json")
    assert receipts, "No receipts examined"
    seen, current = set(), 0
    for path in receipts:
        data = json.loads(path.read_text())
        name = str(path.relative_to(here))
        historical = history["receipts"].get(name)
        if historical:
            assert historical["status"] == "HISTORICAL_ONLY"
            assert sha(path) == historical["receipt_sha256"], path
            assert historical["source_sha256"] == data["source_sha256"], path
            seen.add(name)
        generator = root / data["generated_by"]
        if historical and sha(generator) != data["generator_sha256"]:
            generator = here / "historical-generators" / (data["generator_sha256"] + ".py")
        assert sha(generator) == data["generator_sha256"], path
        assert sha(path.with_suffix(".txt")) == data["output_sha256"], path
        assert (data["exit_code"] == 0) == (data["verdict"] == "PASSED"), path
        if not historical:
            assert data["source_sha256"], path
            for source, expected in data["source_sha256"].items():
                assert sha(root / source) == expected, f"Current source mismatch: {source} ({path})"
            current += 1
    assert seen == set(history["receipts"]), "Historical receipts removed"
    for name in history["spec_raw"]:
        data, _ = json.JSONDecoder().raw_decode((here / (name + ".txt")).read_text())
        archived = here / "historical-generators" / (data["control_sha256"] + ".py")
        assert sha(archived) == data["control_sha256"], name
    return {"historical_receipts": len(seen), "current_source_bound_receipts": current,
            "historical_spec_raw": len(history["spec_raw"]),
            "limitation": "Historical hashes describe their original working tree; they do not certify current sources or deployment."}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
    print("generator_sha256", sha(Path(__file__)))
