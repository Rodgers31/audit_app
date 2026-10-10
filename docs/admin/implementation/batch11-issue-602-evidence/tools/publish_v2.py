"""Publish selected external #602 run receipts into the committed portable packet.

One-way and append-only: a label that already exists in the packet refuses, and
nothing outside ``receipts/`` or ``MANIFEST.json`` is written. Inputs are
record_v3 output directories (outside the checkout); only ``receipt.json`` is
copied, after machine paths are replaced by placeholders and any testcase id
longer than 512 characters is compacted to its first 200 characters plus its
SHA-256 and length (counted in ``published_testcase_ids_compacted``). Historical receipts produced by record.py/record_v2.py are not
republished or rebound here; they stay in the recovery bundle with their original
generator identity.

    python publish_v2.py --packet <evidence dir> --label <name> --run <record_v3 out dir>
"""
import argparse
import hashlib
import json
from pathlib import Path
import os
import re
import subprocess

MAX_ID = 512
BASE = "bcb5ff99854de595bbe3f7d60cc8796b7ada5a20"  # accepted predecessor main


def changed_paths(repo):
    """Paths the #602 lane changed from the accepted base, tracked or untracked."""
    env = {"PATH": os.environ.get("PATH", os.defpath), "DEVELOPER_DIR": "/Library/Developer/CommandLineTools"}
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=repo, text=True, env=env).split("\0")
    names = git("diff", "--name-only", "-z", BASE) + git("ls-files", "--others", "--exclude-standard", "-z")
    return {n for n in names if n}
SAFE_LABEL = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable(text, run):
    text = text.replace(str(run), "<out>")
    # Any remaining absolute home path is author-machine-only; refuse to publish it.
    if re.search(r"/Users/[^/\s\"]+/", text):
        text = re.sub(r"/Users/[^\s\"<>]+", "<machine-path>", text)
    return text


def manifest(packet):
    files = {}
    for path in sorted((packet / "receipts").rglob("*")):
        if path.is_symlink():
            raise SystemExit("Symlink inside packet refused: " + str(path))
        if path.is_file():
            files[str(path.relative_to(packet))] = sha(path)
    return {"schema": 2, "generated_by": "tools/publish_v2.py", "generator_sha256": sha(Path(__file__)), "files": files}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--packet", type=Path, required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--run", type=Path, required=True)
    a = p.parse_args()
    packet, run = a.packet.resolve(strict=True), a.run.resolve(strict=True)
    if not SAFE_LABEL.fullmatch(a.label):
        raise SystemExit("Unsafe label")
    if packet in run.parents or run == packet:
        raise SystemExit("Run outputs must be external to the packet")
    receipt = run / "receipt.json"
    if receipt.is_symlink() or not receipt.is_file():
        raise SystemExit("record_v3 receipt.json required")
    record = json.loads(receipt.read_text())
    if not str(record.get("generated_by", "")).endswith("tools/record_v3.py"):
        raise SystemExit("Only record_v3 receipts are published by this generator")
    target = packet / "receipts" / a.label
    if target.exists():
        raise SystemExit("Append-only: label already published")
    target.mkdir(parents=True)
    record = json.loads(portable(receipt.read_text(), run))
    compacted = 0
    for case in record.get("testcases", []):
        # A parametrized id can embed megabytes of input; keep it unique and
        # identifiable without committing the payload.
        if type(case.get("id")) is str and len(case["id"]) > MAX_ID:
            raw = case["id"].encode()
            case["id"] = case["id"][:200] + f"...[sha256={hashlib.sha256(raw).hexdigest()},len={len(raw)}]"
            compacted += 1
    record["published_testcase_ids_compacted"] = compacted
    scope = changed_paths(packet.parents[3])
    record["source_files"] = {k: v for k, v in record.get("source_files", {}).items() if k in scope}
    record["published_source_files_scope"] = ("paths changed from accepted base " + BASE
                                              + "; the full-set digest is source_before_sha256")
    (target / "receipt.json").write_text(json.dumps(record, indent=1))
    # junit.xml stays in the external output; the receipt carries the parsed
    # inventory, and the external path is recorded in the postcommit binder.
    (packet / "MANIFEST.json").write_text(json.dumps(manifest(packet), indent=2) + "\n")
    print(json.dumps({"published": a.label, "files": sorted(p.name for p in target.iterdir())}))


if __name__ == "__main__":
    main()
