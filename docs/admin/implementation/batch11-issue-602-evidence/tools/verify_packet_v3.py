"""Read-only verifier for the committed #602 evidence packet (supersedes draft v1).

Two separate verdicts, never merged:
  * ``historical_integrity``: MANIFEST.json lists exactly the files under
    receipts/, every hash matches, no symlink, no path escape, no unlisted or
    internal output (coverage, caches), and every receipt is well-typed with
    counts that recompute from its unique, nonempty testcase inventory;
  * ``current_checkout_acceptance``: a fresh external execution is green,
    its raw inventory recomputes, and its complete source map and clean
    HEAD/tree match this checkout. Archived receipts never grant acceptance.
Archived receipts certify history only. Current acceptance additionally requires a fresh external
record_v4 receipt with a complete current source map; old receipts are never rebound.
Exit status is 0 only when integrity holds; acceptance is reported, not implied.

    python -B docs/admin/implementation/batch11-issue-602-evidence/tools/verify_packet_v3.py
"""
import hashlib
import json
from pathlib import Path
import re
import sys

PACKET = Path(__file__).resolve().parents[1]
REPO = PACKET.parents[3]
STATES = ("error", "failed", "xpass", "passed", "xfail", "skipped")
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


def verify(packet=PACKET, repo=REPO, current_receipt=None):
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
            and not record["timed_out"] and bool(record["source_files"]) \
            and all(record["counts"][state] == 0 for state in ("error", "failed", "xpass"))
        final = rel.split("/")[1].startswith("final-")
        receipts[rel] = {"label": record["label"], "green": green, "final": final, "counts": record["counts"]}
        if final and not green:
            acceptance = False
        if final:
            for path, digest in record["source_files"].items():
                current = repo / path
                if current.resolve() != current or not current.is_file() or current.is_symlink() or sha(current) != digest:
                    acceptance = False
                    mismatched.append(path)
    result = {"historical_integrity": True, "current_checkout_acceptance": False,
              "archived_source_mismatch_sample": sorted(set(mismatched))[:20], "receipts": receipts,
              "current_receipt": None,
              "acceptance_requirement": "Fresh external record_v4 receipt binding the complete current source inventory"}
    if current_receipt is not None:
        result.update(current_execution(Path(current_receipt), repo))
    return result


def current_execution(path, repo):
    import importlib.util
    from datetime import datetime, timezone
    path = path.absolute()
    if path.resolve() != path or path.is_symlink() or not path.is_file() or repo == path or repo in path.parents:
        raise Refused("Fresh current receipt must be an external regular file")
    record = check_receipt(str(path), json.loads(path.read_text()))
    identity = "docs/admin/implementation/batch11-issue-602-evidence/tools/record_v4.py"
    if record.get("generated_by") != identity or record.get("mode") not in ("pytest", "launcher"):
        raise Refused("Current acceptance requires an executed record_v4 test inventory")
    for field in ("leftover_process_group", "ci_parity_environment"):
        if type(record.get(field)) is not bool:
            raise Refused("Malformed current execution flag: " + field)
    for field in ("owned_containers_before", "owned_containers_after"):
        if type(record.get(field)) is not list:
            raise Refused("Missing physical resource readback: " + field)
    timestamps = [datetime.fromisoformat(record[k]) for k in ("started_at", "finished_at")]
    if any(t.tzinfo is None or t.utcoffset() != timezone.utc.utcoffset(t) for t in timestamps) or timestamps[0] > timestamps[1]:
        raise Refused("Current execution requires ordered UTC timestamps")
    producer = repo / identity
    if producer.resolve() != producer or producer.is_symlink() or not producer.is_file():
        raise Refused("Current recorder must be a checkout-local regular file")
    spec = importlib.util.spec_from_file_location("batch11_current_recorder_readonly", producer)
    recorder = importlib.util.module_from_spec(spec)
    old = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(recorder)
    finally:
        sys.dont_write_bytecode = old
    expected = recorder.source(repo)
    outputs = record.get("output_files")
    if type(outputs) is not dict or not outputs or "output.log" not in outputs:
        raise Refused("Current execution requires raw output identities")
    for name, recorded in outputs.items():
        if type(name) is not str or not name or Path(name).is_absolute() or ".." in Path(name).parts:
            raise Refused("Raw output path escapes its execution")
        member = path.parent / name
        if member.resolve() != member or not member.is_file() or member.is_symlink() or sha(member) != recorded:
            raise Refused("Raw execution output changed: " + name)
    if record["mode"] == "pytest":
        if set(outputs) != {"output.log", "junit.xml"}:
            raise Refused("Current pytest requires its actual JUnit and raw log")
        observed = recorder.junit_cases(path.parent / "junit.xml")
    else:
        required = {"core/collection-backend.json", "core/collection-legacy.json"}
        if not required <= set(outputs):
            raise Refused("Current launcher requires both collection receipts")
        observed = recorder.verbose_cases((path.parent / "output.log").read_text())
        collected = []
        for name in sorted(required):
            nodes = json.loads((path.parent / name).read_text()).get("nodeids")
            if type(nodes) is not list or not nodes or any(type(n) is not str or not n for n in nodes):
                raise Refused("Current launcher collection must be nonempty typed identities")
            collected.extend(nodes)
        if len(collected) != len(set(collected)) or set(collected) != {c["id"] for c in observed}:
            raise Refused("Current launcher outcomes must cover both unique collection inventories")
    output_inventory_matches = observed == record["testcases"]
    head, tree = recorder.git(repo, "rev-parse", "HEAD", "HEAD^{tree}").split()
    checkout_matches = (record.get("head") == head and record.get("tree") == tree
                        and record.get("status_before") == record.get("status_after") == ""
                        and recorder.git(repo, "status", "--porcelain=v1", "--untracked-files=all") == "")
    digest = hashlib.sha256(json.dumps(record["source_files"], sort_keys=True).encode()).hexdigest()
    stable = record.get("source_before_sha256") == record.get("source_after_sha256") == digest
    green = (record["exit_code"] == 0 and record["complete_inventory"] is True
             and record["timed_out"] is False and record["source_drift"] == []
             and record["leftover_process_group"] is False
             and record["owned_containers_before"] == record["owned_containers_after"] == []
             and record["counts"]["passed"] > 0
             and all(record["counts"][state] == 0 for state in ("error", "failed", "xpass")))
    complete = expected == record["source_files"] and record.get("generator_sha256") == expected.get(identity)
    return {"current_checkout_acceptance": bool(green and complete and stable and output_inventory_matches and checkout_matches),
            "current_receipt": {"sha256": sha(path), "source_complete": complete, "source_stable": stable,
                                "output_inventory_matches": output_inventory_matches, "checkout_matches": checkout_matches,
                                "green": green, "counts": record["counts"], "head": record.get("head"), "tree": record.get("tree")}}


def main():
    try:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--current-receipt", type=Path)
        args = parser.parse_args()
        result = verify(current_receipt=args.current_receipt)
    except (Refused, ValueError, OSError) as exc:
        print(json.dumps({"historical_integrity": False, "current_checkout_acceptance": False, "refused": str(exc)}))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
