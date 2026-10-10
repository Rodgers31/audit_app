"""Preserve original execution bytes; the manifest claims historical integrity only."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import xml.etree.ElementTree as ET


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    home = args.artifacts.resolve()
    if args.archive.exists() or args.manifest.exists():
        raise ValueError("Fresh historical outputs required")
    directories = {"review-adversarial", "review-spec", "review-standards", "metadata-green",
        "full-backend-current", "full-legacy-current", "linux-current", "linux-minimum"}
    exclusions = {"tmp", "cache", "pytest-cache", "__pycache__", "generated-seeding", ".git"}
    candidates = list(home.iterdir())
    for directory in sorted(directories):
        for parent, children, names in os.walk(home / directory):
            children[:] = sorted(n for n in children if n not in exclusions and not (Path(parent) / n).is_symlink())
            candidates.extend(Path(parent) / n for n in names)
    paths = sorted(p for p in candidates if p.is_file() and not p.is_symlink()
        and p.suffix in {".json", ".txt", ".xml", ".log", ".md", ".py"}
        and (len(p.relative_to(home).parts) == 1 or p.relative_to(home).parts[0] in directories)
        and not exclusions.intersection(p.relative_to(home).parts)
        and p.name not in {"handoff-draft.md", "lessons-draft.md", "append-coordination.py"})
    files = {}
    inventories = {}
    with args.archive.open("xb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as zipped:
        with tarfile.open(fileobj=zipped, mode="w|") as archive:
            for path in paths:
                name = path.relative_to(home).as_posix()
                data = path.read_bytes()
                info = tarfile.TarInfo(name)
                info.size, info.mode, info.mtime = len(data), 0o644, 0
                archive.addfile(info, io.BytesIO(data))
                files[name] = dict(bytes=len(data), sha256=sha(data))
                if path.suffix == ".xml":
                    cases = list(ET.fromstring(data).iter("testcase"))
                    ids = [t.attrib.get("classname", "") + "::" + t.attrib.get("name", "") for t in cases]
                    counts = dict(passed=0, failed=0, errors=0, skipped=0, xfailed=0)
                    skips = []
                    for identity, case in zip(ids, cases):
                        skipped = case.find("skipped")
                        key = ("failed" if case.find("failure") is not None else "errors" if case.find("error") is not None else
                            "xfailed" if skipped is not None and skipped.get("type") == "pytest.xfail" else
                            "skipped" if skipped is not None else "passed")
                        counts[key] += 1
                        if skipped is not None:
                            skips.append(dict(identity=identity, reason=skipped.get("message", "")))
                    inventories[name] = dict(identities=ids, counts=counts, skips=skips,
                        nonempty_unique=bool(ids) and len(ids) == len(set(ids)),
                        classification="historical_execution_inventory" if ids else "historical_setup_without_testcases")
    # Read back archive bytes without extracting or rebinding any execution.
    with tarfile.open(args.archive, "r:gz") as archive:
        observed = {member.name: dict(bytes=member.size, sha256=sha(archive.extractfile(member).read())) for member in archive}
    if observed != files:
        raise RuntimeError("Historical archive readback mismatch")
    packet = dict(classification="historical_integrity_only", generated_by=Path(__file__).name,
        generator_sha256=sha(Path(__file__).read_bytes()), archive_sha256=sha(args.archive.read_bytes()),
        files=files, junit=inventories,
        note="Original histories include failed/setup/interrupted/negative runs; this manifest cannot certify the final source.")
    with args.manifest.open("x") as stream:
        json.dump(packet, stream, indent=2)
    if json.loads(args.manifest.read_text()) != packet:
        raise RuntimeError("Historical manifest readback mismatch")
    print(json.dumps(dict(files=len(files), junit=len(inventories), archive_sha256=packet["archive_sha256"])))


if __name__ == "__main__":
    main()
