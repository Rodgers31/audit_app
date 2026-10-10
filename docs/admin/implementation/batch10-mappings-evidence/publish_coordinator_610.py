"""Append #610 history and retain frozen source bytes; never rewrite old runs.

Run ``prepare`` before changing the verifier, then ``publish`` after all packet
edits. Only manifest.json is a replaceable publication index. All other writes
use exclusive creation and verify disk bytes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import time
import zipfile

FROZEN = "86aa4c3a7a29383ed256273bd0097cfc81b3336d"
TREE = "051cd539ef2219e9659dd339c720b3ba9e2596c7"
PACKET = Path(__file__).resolve().parent
ROOT = PACKET.parents[3]
HISTORY = PACKET / "history/coordinator-610"
ARCHIVE = PACKET / "retained-source-86aa4c3.zip"


def sha(body):
    return hashlib.sha256(body).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def write_new(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(body)
    if path.read_bytes() != body:
        raise RuntimeError("Publication readback mismatch: " + str(path))


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def prepare():
    if git("rev-parse", FROZEN + "^{tree}").decode().strip() != TREE:
        raise RuntimeError("Frozen tree mismatch")
    manifest_bytes = git("show", FROZEN + ":" + str(PACKET.relative_to(ROOT) / "manifest.json"))
    manifest = json.loads(manifest_bytes)
    if (PACKET / "manifest.json").read_bytes() != manifest_bytes:
        raise RuntimeError("Expected original current publication")
    for name in ("manifest.json", "verify_package.py", "README.md"):
        original = git("show", FROZEN + ":" + str(PACKET.relative_to(ROOT) / name))
        if (PACKET / name).read_bytes() != original:
            raise RuntimeError("Original publication already changed: " + name)
        write_new(HISTORY / ("previous-" + name), original)
    # The archive is deliberately built from committed frozen blobs, not the
    # candidate checkout. The manifest includes 1,158 executed source files and
    # two subsequent publication-only files; those roles remain distinct.
    with ARCHIVE.open("xb") as stream:
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, expected in sorted(manifest["source_sha256"].items()):
                body = git("show", FROZEN + ":" + name)
                if sha(body) != expected:
                    raise RuntimeError("Frozen source mismatch: " + name)
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, body, compresslevel=9)
    with zipfile.ZipFile(ARCHIVE) as archive:
        actual = {info.filename: sha(archive.read(info)) for info in archive.infolist()}
        if actual != manifest["source_sha256"] or len(archive.infolist()) != 1160:
            raise RuntimeError("Archive readback mismatch")
    preservation = {
        "generated_by": "publish_coordinator_610.py",
        "generator_sha256": sha(Path(__file__).read_bytes()),
        "generated_at": time.time(),
        "frozen_commit": FROZEN,
        "frozen_tree": TREE,
        "previous_manifest_sha256": sha(manifest_bytes),
        "original_assets_sha256": manifest["assets_sha256"],
        "source_archive_sha256": sha(ARCHIVE.read_bytes()),
        "source_files": 1160,
        "executed_source_files": 1158,
        "classification": "HISTORICAL_EXECUTION_PACKET",
        "current_checkout_acceptance": False,
    }
    write_new(HISTORY / "preservation.json", encode(preservation))
    print(json.dumps({"stage": "prepare", "source_files": len(actual), "archive_sha256": preservation["source_archive_sha256"]}))


def publish():
    old_bytes = (HISTORY / "previous-manifest.json").read_bytes()
    old = json.loads(old_bytes)
    if (PACKET / "manifest.json").read_bytes() != old_bytes:
        raise RuntimeError("Publication index has changed since prepare")
    replacements = {name: "history/coordinator-610/previous-" + name for name in ("README.md", "verify_package.py")}
    for name, expected in old["assets_sha256"].items():
        path = PACKET / replacements.get(name, name)
        if sha(path.read_bytes()) != expected:
            raise RuntimeError("Historical asset changed: " + name)
    publication_only = sorted(set(old["source_sha256"]) - set(json.loads((PACKET / old["checks"][0]["receipt"]).read_text())["source_before"]))
    if len(publication_only) != 2:
        raise RuntimeError("Historical source roles mismatch")
    history = {
        "generated_by": "publish_coordinator_610.py",
        "generator_sha256": sha(Path(__file__).read_bytes()),
        "generated_at": time.time(),
        "issue": 610,
        "previous_manifest_sha256": sha(old_bytes),
        "previous_verifier_sha256": sha((HISTORY / "previous-verify_package.py").read_bytes()),
        "previous_publication_status": "HISTORICAL_SUPERSEDED_VALIDATOR",
        "original_execution_status": "HISTORICAL_EXECUTION_PACKET",
        "current_checkout_acceptance": False,
        "reason": "Strict metadata/JUnit guards and retained-source archive repair; old source identities, receipts, generators and outputs are unchanged. Fresh candidate execution is recorded externally.",
    }
    write_new(HISTORY / "publication.json", encode(history))
    manifest = {
        **old,
        "schema": 2,
        "generated_by": "publish_coordinator_610.py",
        "generator_sha256": sha(Path(__file__).read_bytes()),
        "generated_at": time.time(),
        "classification": "HISTORICAL_EXECUTION_PACKET",
        "current_checkout_acceptance": False,
        "previous_publication_sha256": sha(old_bytes),
        "publication_history": "history/coordinator-610/publication.json",
        "original_publication": "history/coordinator-610/previous-manifest.json",
        "historical_asset_replacements": replacements,
        "retained_source": {
            "archive": ARCHIVE.name,
            "sha256": sha(ARCHIVE.read_bytes()),
            "commit": FROZEN,
            "tree": TREE,
            "source_files": 1160,
            "executed_source_files": 1158,
            "publication_only_sources": publication_only,
        },
    }
    manifest["assets_sha256"] = {str(p.relative_to(PACKET)): sha(p.read_bytes()) for p in sorted(PACKET.rglob("*")) if p.is_file() and p.name != "manifest.json"}
    body = encode(manifest)
    (PACKET / "manifest.json").write_bytes(body)
    if (PACKET / "manifest.json").read_bytes() != body:
        raise RuntimeError("Current publication readback mismatch")
    print(json.dumps({"stage": "publish", "source_files": 1160, "assets": len(manifest["assets_sha256"]), "classification": manifest["classification"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "publish"))
    args = parser.parse_args()
    {"prepare": prepare, "publish": publish}[args.stage]()
