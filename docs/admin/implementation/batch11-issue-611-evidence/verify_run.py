"""Verify fresh local current-source evidence; historical records are not acceptance."""

import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

# Normal and optimized invocations must not create caches beside source files.
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("issue611_recorder", HERE / "record.py")
recorder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recorder)


def verify(path):
    absolute = recorder.output_path(path)
    record = json.loads(absolute.read_text())
    if type(record) is not dict:
        raise ValueError("Object receipt required")
    expected = str((HERE / "record.py").relative_to(recorder.ROOT))
    if record.get("generated_by") != expected or record.get(
        "generator_sha256"
    ) != recorder.digest(HERE / "record.py"):
        raise ValueError("Expected live recorder identity required")
    outputs = record.get("outputs_sha256")
    names = {
        "stdout.txt",
        "stderr.txt",
        "tests.xml",
        "runtime.stdout.txt",
        "runtime.stderr.txt",
        "execution.json",
    }
    if type(outputs) is not dict or set(outputs) != names:
        raise ValueError("Complete raw execution outputs required")
    for name, sha in outputs.items():
        output = recorder.output_path(absolute.parent / name)
        if (
            not output.is_file()
            or type(sha) is not str
            or recorder.digest(output) != sha
        ):
            raise ValueError("Execution output identity mismatch")
    execution = json.loads((absolute.parent / "execution.json").read_text())
    required = {
        "generated_by",
        "generator_sha256",
        "generated_at",
        "target_commit",
        "target_tree",
        "source_inventory_sha256",
        "status_before",
        "status_after",
        "runtime",
        "runtime_probe_command",
        "runtime_probe_exit",
        "platform",
        "command",
        "env",
        "child_exit",
        "source_unchanged",
    }
    if (
        type(execution) is not dict
        or set(execution) != required
        or any(record.get(k) != execution[k] for k in required)
    ):
        raise ValueError(
            "Receipt must match complete retained producer execution metadata"
        )
    for field in ("child_exit", "verification_exit", "runtime_probe_exit"):
        if type(record.get(field)) is not int or record[field] != 0:
            raise ValueError("Actual successful integer exits required")
    if record.get("verdict") != "PASS" or record.get("source_unchanged") is not True:
        raise ValueError("Accepted unchanged execution required")
    runtime = record.get("runtime")
    if (
        type(runtime) is not dict
        or set(runtime) != {"python", "sqlalchemy", "fastapi"}
        or any(type(v) is not str or not v for v in runtime.values())
    ):
        raise ValueError("Complete runtime identity required")
    if runtime != json.loads(
        (absolute.parent / "runtime.stdout.txt").read_text()
    ) or record["runtime_probe_command"] != ["<owned-python>", "-c", recorder.PROBE]:
        raise ValueError("Runtime identity must match actual captured probe output")
    if record["target_commit"] != recorder.git("rev-parse", "HEAD") or record[
        "target_tree"
    ] != recorder.git("rev-parse", "HEAD^{tree}"):
        raise ValueError("Fresh current Git identity required")
    if record["status_before"] != record["status_after"] or record[
        "status_after"
    ] != recorder.git("status", "--porcelain=v1"):
        raise ValueError("Unchanged current source status required")
    if (
        type(record["generated_at"]) is not str
        or datetime.fromisoformat(record["generated_at"]).utcoffset() is None
        or type(record["platform"]) is not str
        or not record["platform"]
    ):
        raise ValueError("Complete dated platform identity required")
    command = record["command"]
    if (
        type(command) is not list
        or len(command) < 10
        or command[:6]
        != [
            "<owned-python>",
            "-m",
            "pytest",
            "--confcutdir=tests",
            "-p",
            "no:cacheprovider",
        ]
        or command[-3:] != ["-v", "-s", "--junitxml=<external>/tests.xml"]
        or any(
            type(t) is not str or not t.startswith("tests/") or ".." in Path(t).parts
            for t in command[6:-3]
        )
        or record["env"] != recorder.ENV
    ):
        raise ValueError("Owned executable cohort and explicit environment required")
    cases = record.get("cases")
    actual = recorder.junit_cases(absolute.parent / "tests.xml")
    if type(cases) is not list or not cases or cases != actual:
        raise ValueError("Testcase identities must match actual retained JUnit")
    ids = []
    for case in cases:
        if (
            type(case) is not dict
            or set(case) != {"id", "state"}
            or type(case["id"]) is not str
            or not case["id"]
            or case["state"] != "passed"
        ):
            raise ValueError("Complete passing testcase identities required")
        ids.append(case["id"])
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate testcase identity")
    counts = record.get("counts")
    if (
        type(counts) is not dict
        or set(counts) != set(recorder.STATES)
        or any(type(n) is not int for n in counts.values())
        or counts != recorder.counts(actual)
    ):
        raise ValueError("Exact executed outcome counts required")
    source = recorder.inventory()
    if (
        record.get("source_sha256") != source
        or record["source_inventory_sha256"]
        != hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
    ):
        raise ValueError("Historical source identity; fresh current replay required")
    recorder.output_path(absolute)
    print(
        json.dumps(
            {
                "scope": "current local backend replay",
                "verdict": "PASS",
                "cases": len(ids),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    try:
        verify(args.receipt)
    except (ValueError, KeyError, OSError, TypeError, ET.ParseError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
