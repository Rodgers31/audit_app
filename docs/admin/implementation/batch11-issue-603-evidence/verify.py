"""Validate recorded current execution; historical integrity is a separate claim."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

RECORDER = "docs/admin/implementation/batch10-readiness-evidence/record.py"


def require(value, message):
    if not value:
        raise ValueError(message)


def external(path, root):
    path = Path(path).absolute()
    require(".." not in path.parts and path.resolve() == path, "Symlink/traversal output refused")
    require(root != path and root not in path.parents, "Internal output refused")
    require(path.is_file(), "Missing recorded output")
    return path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(path):
    cases = list(ET.parse(path).iter("testcase"))
    identities = [t.attrib.get("classname", "") + "::" + t.attrib.get("name", "") for t in cases]
    require(bool(identities) and len(set(identities)) == len(identities)
        and all(t.attrib.get("classname") and t.attrib.get("name") for t in cases), "Empty/duplicate testcase inventory")
    counts = dict(passed=0, failed=0, errors=0, skipped=0, xfailed=0)
    skips = []
    for identity, case in zip(identities, cases):
        if case.find("failure") is not None:
            counts["failed"] += 1
        elif case.find("error") is not None:
            counts["errors"] += 1
        elif case.find("skipped") is not None:
            node = case.find("skipped")
            counts["xfailed" if node.attrib.get("type") == "pytest.xfail" else "skipped"] += 1
            skips.append(dict(identity=identity, reason=node.attrib.get("message", "")))
        else:
            counts["passed"] += 1
    require(counts["passed"] > 0, "No passing executed testcases")
    suites = list(ET.parse(path).iter("testsuite"))
    for key, actual in (("tests", len(cases)), ("failures", counts["failed"]),
            ("errors", counts["errors"]), ("skipped", counts["skipped"] + counts["xfailed"])):
        require(sum(int(s.attrib[key]) for s in suites) == actual, "JUnit summary mismatch")
    return dict(identities=identities, counts=counts, skips=skips)


def validate(root, index_path, *, current=True):
    root = Path(root).resolve()
    index_path = external(index_path, root)
    packet = json.loads(index_path.read_text())
    require(type(packet) is dict and packet.get("schema") == "batch11-603-v1", "Unknown packet schema")
    require(packet.get("generated_by") == "docs/admin/implementation/batch11-issue-603-evidence/publish.py", "Wrong publisher")
    require(type(packet.get("files")) is dict and set(packet["files"]) == {"receipt.json", "receipt.txt", "results.xml"}, "Missing packet members")
    for name, digest in packet["files"].items():
        path = external(index_path.parent / name, root)
        require(type(digest) is str and re.fullmatch("[0-9a-f]{64}", digest) and sha(path) == digest, "Output hash mismatch")
    receipt = json.loads((index_path.parent / "receipt.json").read_text())
    require(type(receipt) is dict and receipt.get("generated_by") == RECORDER, "Wrong execution recorder")
    require(type(receipt.get("child_exit")) is int and receipt["child_exit"] == 0, "Invalid child exit")
    require(type(receipt.get("timed_out")) is bool and receipt["timed_out"] is False, "Timeout metadata invalid")
    require(type(receipt.get("source_stable")) is bool and receipt["source_stable"] is True, "Source stability invalid")
    require(receipt.get("verdict") == "PASS" and receipt.get("negative_diagnostic") is None, "Behavioral acceptance invalid")
    require(type(receipt.get("command")) is list and len(receipt["command"]) > 3
        and all(type(v) is str and v for v in receipt["command"]), "Missing executed command")
    require(receipt["command"][1:3] == ["-m", "pytest"], "Wrong executed entrypoint")
    for key in ("started_at", "ended_at", "runtime", "environment", "secret_environment_present", "before", "after"):
        require(key in receipt, "Missing execution metadata: " + key)
    require(type(receipt["runtime"]) is dict and all(type(receipt["runtime"].get(k)) is str and receipt["runtime"][k]
        for k in ("executable", "python", "platform")), "Runtime metadata invalid")
    require(receipt["runtime"]["executable"] == receipt["command"][0], "Wrong executed runtime")
    require(type(receipt["secret_environment_present"]) is dict and
        set(receipt["secret_environment_present"]) == {"DATABASE_URL", "JWT_SECRET_KEY", "BATCH9_BOOTSTRAP_POSTGRES_URL"}
        and all(type(v) is bool for v in receipt["secret_environment_present"].values()), "Presence metadata invalid")
    require(receipt["before"] == receipt["after"] and type(receipt["before"]) is dict, "Source changed during execution")
    source = receipt["before"]
    require(type(source.get("sources")) is dict and bool(source["sources"]), "Missing source inventory")
    for path, digest in source["sources"].items():
        require(type(path) is str and not Path(path).is_absolute() and ".." not in Path(path).parts, "Invalid source identity")
        require(type(digest) is str and re.fullmatch("[0-9a-f]{64}", digest), "Malformed source hash")
    require(receipt.get("generator_sha256") == source["sources"].get(RECORDER), "Recorder identity mismatch")
    require(packet.get("generator_sha256") == source["sources"].get(packet["generated_by"]), "Publisher identity mismatch")
    require(receipt.get("log_sha256") == packet["files"]["receipt.txt"], "Raw execution output mismatch")
    observed = inventory(index_path.parent / "results.xml")
    declared = packet.get("testcases")
    require(type(declared) is dict and set(declared) == {"identities", "counts", "skips"}
        and type(declared["counts"]) is dict and set(declared["counts"]) == set(observed["counts"])
        and all(type(v) is int and v >= 0 for v in declared["counts"].values()), "Malformed testcase counts")
    require(observed == packet.get("testcases"), "Testcase metadata mismatch")
    require(observed["counts"]["failed"] == observed["counts"]["errors"] == observed["counts"]["xfailed"] == 0,
        "Failed/error/xfail execution cannot certify repair")
    if current:
        spec = importlib.util.spec_from_file_location("batch11_record_readonly", root / RECORDER)
        module = importlib.util.module_from_spec(spec)
        prior = sys.dont_write_bytecode
        try:
            sys.dont_write_bytecode = True
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = prior
        require(module.identity(root) == source, "Historical source is not current acceptance")
        require(sha(root / RECORDER) == receipt["generator_sha256"], "Current recorder changed")
    return dict(classification="current_behavioral_acceptance" if current else "historical_packet_integrity",
        head=source["head"], tree=source["tree"], counts=observed["counts"], skips=observed["skips"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--history-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(validate(args.root, args.index, current=not args.history_only)))
