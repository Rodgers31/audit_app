"""Guard the owned lane receipts against silent generator drift."""
import hashlib
import json
from pathlib import Path


def test_owned_producer_receipts_have_live_or_superseded_generators():
    repo = Path(__file__).resolve().parents[2]
    evidence = repo / "docs/admin/implementation/batch8-producer-evidence"
    receipts = list(evidence.glob("*.json"))
    assert receipts, "No producer lane receipts were examined"
    superseded = (evidence / "SUPERSEDED_RUNNER.md").read_text()
    for path in receipts:
        receipt = json.loads(path.read_text())
        generator = repo / receipt["generated_by"]
        assert generator.is_file(), path
        actual = hashlib.sha256(generator.read_bytes()).hexdigest()
        if receipt["generator_sha256"] != actual:
            assert path.name in superseded, path
            assert receipt["generator_sha256"] in superseded, path
        assert receipt["verdict"] == ("PASS" if receipt["exit_status"] == 0 else "FAILED"), path
