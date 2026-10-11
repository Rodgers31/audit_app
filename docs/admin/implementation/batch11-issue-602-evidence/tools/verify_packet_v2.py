"""Read-only verifier for the committed #602 evidence packet (supersedes draft v1).

Two separate verdicts, never merged:
  * ``historical_integrity``: MANIFEST.json lists exactly the files under
    receipts/, every hash matches, no symlink, no path escape, no unlisted or
    internal output (coverage, caches), and every receipt is well-typed with
    counts that recompute from its unique, nonempty testcase inventory;
  * ``current_checkout_acceptance``: additionally, every ``receipts/final-*``
    receipt is green (exit 0, complete, no drift, no timeout) and its recorded
    source hashes for the #602-owned files equal the bytes in this checkout.
    Red and intermediate receipts are history and never count toward it. A clone at another commit reports
    false here while integrity can still be true.
Exit status is 0 only when integrity holds; acceptance is reported, not implied.

    python -B docs/admin/implementation/batch11-issue-602-evidence/tools/verify_packet_v2.py
"""
import hashlib
import json
from pathlib import Path
import re
import sys

PACKET = Path(__file__).resolve().parents[1]
REPO = PACKET.parents[3]
STATES = ("error", "failed", "xpass", "passed", "xfail", "skipped")
OWNED = re.compile(r"^(backend/seeding/domains/cra/|backend/alembic/versions/e602b11a0001_|backend/tests/test_batch11_|"
                   r"backend/tests/batch11_native_sources_fixture/|etl/writer_ownership\.py$|"
                   r"\.github/scripts/prepare_reconciliation_test_fixture\.py$)")
FORBIDDEN = re.compile(r"(^|/)(\.coverage[^/]*|coverage\.xml|htmlcov|__pycache__|\.pytest_cache)(/|$)")


class Refused(Exception):
    pass


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_receipt(name, record):
    if type(record) is not dict:
        raise Refused(name + ": receipt is not an object")
    for key, kind in (("exit_code", int), ("complete_inventory", bool), ("timed_out", bool), ("label", str),
                      ("source_files", dict), ("source_drift", list), ("testcases", list), ("counts", dict)):
        if type(record.get(key)) is not kind:
            raise Refused(f"{name}: {key} must be {kind.__name__}")
    cases = record["testcases"]
    ids = [c.get("id") if type(c) is dict else None for c in cases]
    if any(type(i) is not str or not i for i in ids) or len(ids) != len(set(ids)):
        raise Refused(name + ": testcase identities must be unique nonempty strings")
    if any(type(c) is not dict or c.get("state") not in STATES for c in cases):
        raise Refused(name + ": unknown testcase state")
    recomputed = {s: sum(c["state"] == s for c in cases) for s in STATES}
    if set(record["counts"]) != set(STATES) or any(type(v) is not int for v in record["counts"].values()) \
            or record["counts"] != recomputed:
        raise Refused(name + ": counts do not recompute from the testcase inventory")
    if record["complete_inventory"] and not cases and record.get("mode") != "command":
        raise Refused(name + ": a complete inventory cannot be empty")
    for path, digest in record["source_files"].items():
        if type(path) is not str or path.startswith("/") or ".." in Path(path).parts \
                or type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise Refused(name + ": malformed source identity")
    return record


def verify(packet=PACKET, repo=REPO):
    manifest_path = packet / "MANIFEST.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise Refused("MANIFEST.json missing or symlinked")
    manifest = json.loads(manifest_path.read_text())
    if type(manifest) is not dict or manifest.get("schema") != 2 or type(manifest.get("files")) is not dict:
        raise Refused("MANIFEST.json schema")
    receipts_root = packet / "receipts"
    if receipts_root.is_symlink():
        raise Refused("receipts directory is a symlink")
    actual = {}
    for path in sorted(receipts_root.rglob("*")):
        rel = str(path.relative_to(packet))
        if path.is_symlink():
            raise Refused("symlink refused: " + rel)
        if FORBIDDEN.search(rel):
            raise Refused("internal output inside packet: " + rel)
        if path.is_file():
            actual[rel] = sha(path)
    listed = manifest["files"]
    for rel in listed:
        if type(rel) is not str or rel.startswith("/") or ".." in Path(rel).parts or not rel.startswith("receipts/"):
            raise Refused("manifest path escapes the packet: " + str(rel))
    if set(listed) != set(actual):
        raise Refused("manifest and packet files differ: " + json.dumps(sorted(set(listed) ^ set(actual))))
    for rel, digest in listed.items():
        if actual[rel] != digest:
            raise Refused("hash mismatch: " + rel)
    receipts, acceptance, mismatched = {}, True, []
    for rel in sorted(r for r in listed if r.endswith("/receipt.json")):
        record = check_receipt(rel, json.loads((packet / rel).read_text()))
        green = record["exit_code"] == 0 and record["complete_inventory"] and not record["source_drift"] \
            and not record["timed_out"]
        final = rel.split("/")[1].startswith("final-")
        receipts[rel] = {"label": record["label"], "green": green, "final": final, "counts": record["counts"]}
        if final and not green:
            acceptance = False
        if final:
            for path, digest in record["source_files"].items():
                if OWNED.match(path):
                    current = repo / path
                    if not current.is_file() or current.is_symlink() or sha(current) != digest:
                        acceptance = False
                        mismatched.append(path)
    return {"historical_integrity": True, "current_checkout_acceptance": acceptance and any(r["final"] for r in receipts.values()),
            "source_mismatch_sample": sorted(set(mismatched))[:20], "receipts": receipts}


def main():
    try:
        result = verify()
    except (Refused, ValueError, OSError) as exc:
        print(json.dumps({"historical_integrity": False, "current_checkout_acceptance": False, "refused": str(exc)}))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
