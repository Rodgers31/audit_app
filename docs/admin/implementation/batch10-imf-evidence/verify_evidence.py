"""Verify the published manifest and optionally a final checkout replay.

Usage: python verify_evidence.py CHECKOUT ARTIFACT_ROOT [CURRENT_RECEIPT]
The artifact root can be relocated. Historical records remain bound to their
original inputs; only the optional current replay certifies checkout identity.
All acceptance checks use explicit exceptions, including under python -O.
"""

import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from run_evidence import source_names, source_state

PACKET = "docs/admin/implementation/batch10-imf-evidence/"
GENERATOR = PACKET + "run_evidence.py"
ENTRY = PACKET + "pytest_entry.py"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def owned_file(root, name):
    require(isinstance(name, str) and bool(name), "Malformed artifact path")
    path = root / name
    require(not Path(name).is_absolute(), "Absolute artifact path")
    require(path.resolve().is_relative_to(root), "Artifact escapes package")
    require(path.is_file() and not path.is_symlink(), "Missing or symlink artifact")
    return path


def execution_provenance(receipt):
    """Validate shared execution fields without rebinding historical identities."""
    require(isinstance(receipt, dict), "Malformed receipt")
    require(type(receipt["child_exit"]) is int, "Malformed child exit")
    require(type(receipt["verification_exit"]) is int, "Malformed verification exit")
    require(receipt["source_stable"] is True, "Source stability is not true")
    require(receipt["start"] == receipt["end"], "Source changed during run")
    require(receipt["generated_by"] == GENERATOR, "Unexpected recorder path")
    for key in ("generator_sha256", "entry_sha256"):
        value = receipt[key]
        require(
            isinstance(value, str)
            and len(value) == 64
            and all(c in "0123456789abcdef" for c in value),
            "Malformed " + key,
        )
    command = receipt["command"]
    require(
        isinstance(command, list)
        and len(command) >= 3
        and all(isinstance(v, str) and v.strip() for v in command),
        "Malformed command",
    )
    for key in ("runtime", "platform", "checkout"):
        require(
            isinstance(receipt[key], str) and bool(receipt[key].strip()),
            "Malformed " + key,
        )
    env = receipt["environment"]
    require(
        isinstance(env, dict)
        and bool(env)
        and all(isinstance(k, str) and isinstance(v, str) for k, v in env.items())
        and env.get("PYTHON_DOTENV_DISABLED") == "1",
        "Malformed environment",
    )
    started, ended = (
        datetime.fromisoformat(receipt[k]) for k in ("started_at", "ended_at")
    )
    require(
        started.tzinfo is not None and ended.tzinfo is not None and ended >= started,
        "Invalid execution timestamps",
    )


def cases(path):
    suites = ElementTree.parse(path).getroot().findall("testsuite")
    require(bool(suites), "No test suites")
    counts = {
        key: sum(int(s.get(key, "0")) for s in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    executed = [case for suite in suites for case in suite.findall("testcase")]
    actual = {"tests": len(executed)}
    actual.update(
        {
            key: sum(case.find(tag) is not None for case in executed)
            for key, tag in (
                ("failures", "failure"),
                ("errors", "error"),
                ("skipped", "skipped"),
            )
        }
    )
    require(counts == actual, "Declared counts differ from executed cases")
    require(counts["tests"] > 0, "Empty case inventory")
    return counts


def verify(checkout, artifacts, current=None):
    manifest = json.loads(
        (
            checkout / "docs/admin/implementation/batch10-imf-evidence/manifest.json"
        ).read_text()
    )
    require(
        type(manifest["schema"]) is int and manifest["schema"] == 1,
        "Unsupported manifest schema",
    )
    require(
        type(manifest["issue"]) is int and manifest["issue"] == 595,
        "Wrong issue identity",
    )
    require(bool(manifest["artifacts"]), "Empty artifact inventory")
    for item in manifest["artifacts"]:
        require(
            digest(owned_file(artifacts, item["path"])) == item["sha256"],
            "Artifact hash mismatch: " + item["path"],
        )
    for item in manifest["runs"]:
        receipt_path = owned_file(artifacts, item["receipt"])
        receipt = json.loads(receipt_path.read_text())
        execution_provenance(receipt)
        require(
            receipt["source_stable"] and receipt["start"] == receipt["end"],
            "Source changed during run",
        )
        require(
            type(item["child_exit"]) is int
            and receipt["child_exit"] == item["child_exit"],
            "Wrong child exit",
        )
        for name, expected in receipt["outputs"].items():
            require(
                digest(owned_file(artifacts, str(Path(item["receipt"]).parent / name)))
                == expected,
                "Recorded output differs",
            )
        require(
            cases(receipt_path.parent / "cases.xml") == item["cases"],
            "Case inventory differs",
        )
    if current is not None:
        receipt = json.loads(current.read_text())
        execution_provenance(receipt)
        require(
            receipt["child_exit"] == 0 and receipt["verification_exit"] == 0,
            "Current replay did not pass",
        )
        require(
            receipt["source_stable"] and receipt["start"] == receipt["end"],
            "Current source drift",
        )
        require(
            digest(owned_file(checkout, receipt["generated_by"]))
            == receipt["generator_sha256"],
            "Current generator drift",
        )
        require(
            digest(owned_file(checkout, ENTRY)) == receipt["entry_sha256"],
            "Current entry drift",
        )
        require(receipt["checkout"] == str(checkout), "Current checkout differs")
        command = receipt["command"]
        require(
            command[1:3] == ["-B", str(checkout / ENTRY)],
            "Unexpected current entry command",
        )
        require(
            command.count("--junitxml=" + str(current.parent / "cases.xml")) == 1
            and sum(v.startswith("--junitxml") for v in command) == 1,
            "Current JUnit destination differs",
        )
        require(
            receipt["environment"].get("DATABASE_URL")
            == "sqlite:///" + str(current.parent / "batch10-imf-import.sqlite"),
            "Current database fixture differs",
        )
        require(
            source_state(checkout, source_names(checkout)) == receipt["start"],
            "Current measured source inventory or Git state differs",
        )
        require(
            {"raw.log", "cases.xml"}.issubset(receipt["outputs"]),
            "Current output inventory is incomplete",
        )
        for name, expected in receipt["outputs"].items():
            require(
                digest(owned_file(current.parent.resolve(), name)) == expected,
                "Current output drift",
            )
        for ref, key in (("HEAD", "head"), ("HEAD^{tree}", "tree")):
            actual = subprocess.check_output(
                ["git", "-C", str(checkout), "rev-parse", ref], text=True
            ).strip()
            require(actual == receipt["start"][key], "Current Git identity differs")
        counts = cases(current.parent / "cases.xml")
        require(
            counts["failures"] == 0 and counts["errors"] == 0, "Current cases failed"
        )
        require(
            counts["tests"] > counts["skipped"],
            "Current replay executed no passing cases",
        )
    return {
        "verified_artifacts": len(manifest["artifacts"]),
        "historical_runs": len(manifest["runs"]),
        "current_checked": current is not None,
    }


if __name__ == "__main__":
    print(
        json.dumps(
            verify(
                Path(sys.argv[1]).resolve(),
                Path(sys.argv[2]).resolve(),
                Path(sys.argv[3]).resolve() if len(sys.argv) == 4 else None,
            )
        )
    )
