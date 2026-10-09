"""Bind final local receipts to committed implementation bytes; no test rerun."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "batch9-reconciliation-evidence"
BASE = "9e97ca3f1ca43f103a8655447a86d889456a218a"
IMPLEMENTATION = "b7329bf1b25ef1ffdeebd42184fa77d597b373fb"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def main():
    path = EVIDENCE / "delivery-manifest.json"
    assert not path.exists(), "append-only manifest"
    assert git("rev-parse", "HEAD").decode().strip() == IMPLEMENTATION
    assert git("rev-parse", IMPLEMENTATION + "^").decode().strip() == BASE
    checked = []
    for source in sorted(EVIDENCE.rglob("*.json")):
        if source.name == "issue-inventory-initial.json":
            continue
        receipt = json.loads(source.read_text())
        generator = ROOT / receipt["generated_by"]
        assert sha(generator) == receipt["generator_sha256"], source
        checked.append({"path": str(source.relative_to(ROOT)), "sha256": sha(source),
                        "generator": str(generator.relative_to(ROOT)), "generator_sha256": sha(generator)})
    assert len(checked) >= 39
    accepted = []
    sources = None
    for name in ("final-current.json", "final-minimum.json", "scoped-critical-lint.json",
                 "app-import-current.json", "app-import-minimum.json"):
        receipt = json.loads((EVIDENCE / name).read_text())
        assert receipt["exit_code"] == 0, name
        if name.startswith("final-"):
            assert "102 passed" in receipt["stdout"] and "skipped" not in receipt["stdout"]
        if sources is None:
            sources = receipt["source_sha256"]
        assert sources == receipt["source_sha256"], name
        for source, expected in sources.items():
            committed = hashlib.sha256(git("show", IMPLEMENTATION + ":" + source)).hexdigest()
            assert committed == expected == sha(ROOT / source), (name, source)
        accepted.append({"path": "batch9-reconciliation-evidence/" + name,
                         "sha256": sha(EVIDENCE / name), "exit_code": 0,
                         "runtime": receipt["runtime"], "command": receipt["command"]})
    for name in ("current-final-stable.json", "min-final-stable.json"):
        receipt = json.loads((EVIDENCE / "behavior" / name).read_text())
        assert len(receipt["checks"]) == 91 and receipt["source_changed_during_run"] is False
        assert receipt["source_sha256_before"] == receipt["source_sha256_after"]
        for source, expected in receipt["source_sha256_after"].items():
            assert sources[source] == expected
    census = json.loads((EVIDENCE / "writer-census.json").read_text())
    # This field's actual format is inspected, not inferred from a passing count.
    for source, expected in census["source_sha256"].items():
        assert sha(ROOT / source) == expected, source
    changed = git("diff", "--name-only", BASE, IMPLEMENTATION).decode().splitlines()
    assert all(source in sources or source.startswith("batch9-reconciliation-evidence/") for source in changed)
    reviews = ("spec-review.md", "standards-review.md", "behavior/REPORT.md", "operator-procedure.md")
    result = {"generated_by": str(Path(__file__).relative_to(ROOT)), "generator_sha256": sha(Path(__file__)),
              "generated_at": datetime.now(timezone.utc).isoformat(), "runtime": sys.version,
              "implementation_commit": IMPLEMENTATION, "pinned_dependent_base": BASE,
              "source_sha256": sources, "changed_implementation_paths": changed,
              "accepted_author_receipts": accepted, "machine_receipts_checked": checked,
              "review_and_procedure_sha256": {name: sha(EVIDENCE / name) for name in reviews},
              "writer_census_sources_checked": len(census["source_sha256"]),
              "raw_issue_census_sha256": sha(EVIDENCE / "issue-inventory-initial.json"),
              "verdict": "PASSED",
              "meaning": "Final accepted source hashes equal committed implementation bytes. Original receipt target_commit remains the precommit base; this manifest records the subsequent commit mapping, without relabeling tests as rerun.",
              "delivery_head": "Published in the dependent draft PR and coordinator/final report; this manifest and handoff are a following documentation-only commit.",
              "scope_limit": "Owned inert local PostgreSQL16 and SQLite controls only. Production/provider/operator acceptance remains pending."}
    path.write_text(json.dumps(result, indent=2) + "\n")
    assert json.loads(path.read_text()) == result
    print(f"{len(checked)} machine receipt generators verified; {len(sources)} tested files match {IMPLEMENTATION}; {len(census['source_sha256'])} census hashes verified")


if __name__ == "__main__":
    main()
