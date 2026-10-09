"""Read back every machine JSON receipt in this lane; raw issue output is indexed."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = Path(__file__).resolve().parent


def main():
    findings = []
    for path in sorted(EVIDENCE.rglob("*.json")):
        if path.name == "issue-inventory-initial.json":
            # Raw gh source output, preserved as supporting data. It is not a
            # verdict; independently hashed below instead of inventing a generator.
            continue
        value = json.loads(path.read_text())
        if type(value) is not dict or "generated_by" not in value:
            raise AssertionError(f"Unindexed receipt: {path}")
        generator = Path(value["generated_by"])
        if not generator.is_absolute():
            generator = ROOT / generator
        actual = hashlib.sha256(generator.read_bytes()).hexdigest()
        assert actual == value["generator_sha256"], path
        findings.append({"path": str(path.relative_to(ROOT)), "generator": str(generator.relative_to(ROOT)),
                         "generator_sha256": actual, "receipt_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    assert len(findings) >= 20, "A no-receipt scan cannot certify provenance"
    raw = EVIDENCE / "issue-inventory-initial.json"
    receipt = {"generated_by": str(Path(__file__).relative_to(ROOT)),
               "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "generated_at": datetime.now(timezone.utc).isoformat(),
               "target_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "checked": findings,
               "raw_sources": [{"path": str(raw.relative_to(ROOT)), "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
                                "source_command": "gh issue list --repo Rodgers31/audit_app --state all --limit 200 --json number,title,state",
                                "meaning": "raw initial open/closed tracking census; no follow-up issue was created"}]}
    path = EVIDENCE / "receipt-provenance.json"
    assert not path.exists(), "append-only evidence"
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    check = json.loads(path.read_text())
    assert check["generator_sha256"] == receipt["generator_sha256"] and check["checked"] == findings
    print(f"{len(findings)} receipt generators verified and read back; one raw issue census indexed")


if __name__ == "__main__":
    main()
