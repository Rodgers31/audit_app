"""Check byte-preserving archival packaging for issue #629.

This validates historical input bytes and their original identities. It never
replays an archived producer or certifies any recorded behavioral acceptance.
"""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import subprocess


PACKET_PATH = "docs/admin/implementation/batch11-issue-607-evidence"
ORIGINAL_COMMIT = "26a328ad5b69f0df2efbdefad7de1c0209744ffd"
ORIGINAL_PATH = "archive-generators/record_v2.py"
ARTIFACT_PATH = ORIGINAL_PATH + ".txt"
ORIGINAL_SHA256 = "d7e6fb4d511827690d103d6b78946a5e6eecd44c15d0e907519fd90b0c234dfd"
MANIFEST_HASHES = {
    "packet-v1.json": "5c0f77c0411fc8349e3a06fa86df1b11d02de55032fd0fd82fcb3b1b5e1b359d",
    "packet-v2.json": "a1c571feda16b95f24e2230c74dadac2a523df35b34cac66680cbd3db65a6bec",
}
LAYOUT_NAME = "historical-byte-layout.json"
EXPECTED_LAYOUT = {
    "schema": 1,
    "issue": 629,
    "scope": "historical-byte-layout-only",
    "original_commit": ORIGINAL_COMMIT,
    "original_packet_path": PACKET_PATH,
    "manifests": MANIFEST_HASHES,
    "moves": [{
        "original_path": ORIGINAL_PATH,
        "artifact_path": ARTIFACT_PATH,
        "sha256": ORIGINAL_SHA256,
    }],
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_directory(path):
    path = Path(path).absolute()
    require(not any(part.is_symlink() for part in [path, *path.parents]), "Symlinked directory")
    require(path.is_dir(), "Missing directory")
    return path


def safe_file(root, name):
    require(type(name) is str and bool(name), "Invalid path type")
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and ".." not in relative.parts
            and str(relative) == name, "Unsafe path")
    path = root / name
    require(not any(part.is_symlink() for part in [path, *path.parents]), "Symlinked input")
    require(path.is_file(), "Missing input: " + name)
    return path


def load_json(raw):
    def unique(pairs):
        result = {}
        for name, value in pairs:
            require(name not in result, "Duplicate JSON key")
            result[name] = value
        return result

    def nonfinite(value):
        raise ValueError("Nonfinite JSON: " + value)

    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


def original_bytes(checkout, relative):
    environment = {
        "PATH": "/usr/bin:/bin", "HOME": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "",
    }
    command = ["/usr/bin/git", "-c", "core.hooksPath=/dev/null",
               "-c", "core.fsmonitor=false", "show",
               ORIGINAL_COMMIT + ":" + PACKET_PATH + "/" + relative]
    try:
        result = subprocess.run(command, cwd=checkout, env=environment,
                                capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("Original Git bytes unavailable: " + relative) from error
    require(result.returncode == 0, "Original Git bytes unavailable: " + relative)
    return result.stdout


def verify_layout(checkout, packet=None, require_original_git_bytes=False):
    require(type(require_original_git_bytes) is bool, "Invalid Git verification mode")
    checkout = safe_directory(checkout)
    packet = safe_directory(packet if packet is not None else checkout / PACKET_PATH)
    layout = load_json(safe_file(packet, LAYOUT_NAME).read_bytes())
    require(layout == EXPECTED_LAYOUT, "Unexpected historical layout correspondence")
    require(type(layout["schema"]) is int and type(layout["issue"]) is int,
            "Invalid layout integer type")

    archived = {}
    counts = {}
    for name, expected in MANIFEST_HASHES.items():
        raw = safe_file(packet, name).read_bytes()
        require(digest(raw) == expected, "Original manifest hash mismatch: " + name)
        if require_original_git_bytes:
            require(raw == original_bytes(checkout, name), "Original Git manifest mismatch: " + name)
        manifest = load_json(raw)
        require(type(manifest) is dict and type(manifest.get("files")) is dict,
                "Invalid original manifest")
        entries = {path: value for path, value in manifest["files"].items()
                   if path.startswith("archive-generators/")}
        counts[name] = len(entries)
        for path, value in entries.items():
            require(path not in archived or archived[path] == value,
                    "Conflicting historical archive identities")
            archived[path] = value
    require(counts == {"packet-v1.json": 64, "packet-v2.json": 65}
            and len(archived) == 65 and archived.get(ORIGINAL_PATH) == ORIGINAL_SHA256,
            "Incomplete original archive catalogue")
    original = packet / ORIGINAL_PATH
    require(not original.exists() and not original.is_symlink(),
            "Historical malformed producer remains at executable path")
    physical = {ARTIFACT_PATH if path == ORIGINAL_PATH else path for path in archived}
    required_directories = set()
    for name in physical:
        for parent in PurePosixPath(name).parents:
            if str(parent) == "archive-generators":
                break
            required_directories.add(str(parent))
    directory = safe_directory(packet / "archive-generators")
    actual = set()
    actual_directories = set()
    for path in directory.rglob("*"):
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            actual_directories.add(path.relative_to(packet).as_posix())
            continue
        require(stat.S_ISREG(mode), "Nonordinary historical archive object: "
                + path.relative_to(packet).as_posix())
        actual.add(path.relative_to(packet).as_posix())
    require(actual == physical, "Uncatalogued/missing historical archive input")
    require(actual_directories == required_directories,
            "Uncatalogued/missing historical archive directory")
    for path, expected in archived.items():
        artifact = ARTIFACT_PATH if path == ORIGINAL_PATH else path
        raw = safe_file(packet, artifact).read_bytes()
        require(digest(raw) == expected, "Original archived byte hash mismatch: " + path)
        if require_original_git_bytes:
            require(raw == original_bytes(checkout, path), "Original Git archive mismatch: " + path)
    return {
        "verification_scope": "historical-byte-layout-only",
        "original_commit": ORIGINAL_COMMIT,
        "packet": str(packet),
        "manifest_archive_counts": counts,
        "original_archives_verified": len(archived),
        "mapped_byte_artifacts": 1,
        "original_git_bytes_verified": require_original_git_bytes,
        "original_git_bytes_status": "verified" if require_original_git_bytes else "not-requested",
        "fresh_execution": False,
        "recorded_acceptance": False,
        "hosted_acceptance": False,
        "production_acceptance": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--packet", type=Path, help="Optional separately packaged historical input directory")
    parser.add_argument("--require-original-git-bytes", action="store_true",
                        help="Also compare literal original Git bytes; refuse unavailable historical objects")
    args = parser.parse_args()
    result = verify_layout(args.checkout, args.packet, args.require_original_git_bytes)
    result["verifier_sha256"] = digest(Path(__file__).read_bytes())
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
