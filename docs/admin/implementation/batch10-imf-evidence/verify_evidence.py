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
from pathlib import Path
from xml.etree import ElementTree

from run_evidence import source_names, source_state


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def owned_file(root, name):
    path = root / name
    require(not Path(name).is_absolute(), "Absolute artifact path")
    require(path.resolve().is_relative_to(root), "Artifact escapes package")
    require(path.is_file() and not path.is_symlink(), "Missing or symlink artifact")
    return path


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
    require(bool(manifest["artifacts"]), "Empty artifact inventory")
    for item in manifest["artifacts"]:
        require(
            digest(owned_file(artifacts, item["path"])) == item["sha256"],
            "Artifact hash mismatch: " + item["path"],
        )
    for item in manifest["runs"]:
        receipt_path = owned_file(artifacts, item["receipt"])
        receipt = json.loads(receipt_path.read_text())
        require(
            receipt["source_stable"] and receipt["start"] == receipt["end"],
            "Source changed during run",
        )
        require(receipt["child_exit"] == item["child_exit"], "Wrong child exit")
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
