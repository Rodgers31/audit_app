"""Check the published historical bundle; never promote it to current acceptance."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile

HERE = Path(__file__).resolve().parent


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def verify():
    index_path = HERE / "history-index.json"
    archive = HERE / "history-v1.tar.gz"
    if index_path.is_symlink() or archive.is_symlink():
        raise ValueError("Published packet files must be ordinary files")
    index = json.loads(index_path.read_text())
    if (
        type(index) is not dict
        or type(index.get("schema")) is not int
        or index["schema"] != 1
        or index.get("scope") != "historical diagnostic evidence only"
        or index.get("archive") != archive.name
        or index.get("archive_sha256") != checksum(archive.read_bytes())
    ):
        raise ValueError("Expected historical bundle identity required")
    entries = index.get("entries")
    if type(entries) is not list or not entries:
        raise ValueError("Nonempty retained artifact inventory required")
    expected = {}
    for entry in entries:
        if type(entry) is not dict or set(entry) != {"path", "sha256"}:
            raise ValueError("Exact artifact identity fields required")
        name, sha = entry["path"], entry["sha256"]
        if type(name) is not str or type(sha) is not str:
            raise ValueError("String artifact identity required")
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or str(path) != name
            or any(p in {"..", ".git"} for p in path.parts)
            or not re.fullmatch(r"[0-9a-f]{64}", sha)
            or name in expected
        ):
            raise ValueError("Unique ordinary relative artifact paths required")
        expected[name] = sha
    producer = index.get("producer")
    if (
        type(producer) is not dict
        or set(producer) != {"path", "sha256"}
        or producer.get("path") != "archive_producer.py"
        or expected.get(producer["path"]) != producer["sha256"]
    ):
        raise ValueError("Retained actual archive producer identity required")
    actual = {}
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            if not member.isfile() or member.name in actual or member.size > 20_000_000:
                raise ValueError("Ordinary unique bounded bundle members required")
            data = bundle.extractfile(member).read()
            actual[member.name] = checksum(data)
    if actual != expected:
        raise ValueError("Archive member identities differ from retained inventory")
    print(
        json.dumps(
            {
                "scope": index["scope"],
                "bundle_integrity": "PASS",
                "artifacts": len(actual),
                "current_acceptance": False,
            }
        )
    )


if __name__ == "__main__":
    try:
        verify()
    except (ValueError, KeyError, OSError, TypeError, tarfile.TarError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
