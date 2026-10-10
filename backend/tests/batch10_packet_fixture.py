"""Owned packet fixtures copy retained historical bytes, never live source."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PACKET = Path("docs/admin/implementation/batch10-mappings-evidence")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_packet(path):
    shutil.copytree(ROOT / PACKET, path / PACKET)
    packet = path / PACKET
    manifest = json.loads((packet / "manifest.json").read_text())
    archive_name = manifest.get("retained_source", {}).get("archive", "retained-source-86aa4c3.zip")
    with zipfile.ZipFile(packet / archive_name) as archive:
        for info in archive.infolist():
            # The positive fixture's published archive is validated separately;
            # extraction is bounded to the fixture even when a later mutation
            # intentionally gives the verifier an unsafe archive member.
            target = path / "retained-source" / info.filename
            if not target.resolve().is_relative_to((path / "retained-source").resolve()):
                raise ValueError("Unsafe fixture source path")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))
            # Preserve reproducibility against the retained pre-repair verifier.
            # That historical verifier expects source at root; schema2 does not.
            if manifest["schema"] == 1 and not str(info.filename).startswith(str(PACKET)):
                legacy = path / info.filename
                legacy.parent.mkdir(parents=True, exist_ok=True)
                legacy.write_bytes(archive.read(info))
    return packet, manifest


def invoke(packet, root, optimized, retained_source=False):
    command = [sys.executable, "-B", *(["-O"] if optimized else []), str(packet / "verify_package.py"), str(root)]
    if retained_source:
        command += ["--retained-source-root", str(root / "retained-source")]
    return subprocess.run(command, capture_output=True, text=True, timeout=30)


def snapshot(root):
    return {str(p.relative_to(root)): sha(p) for p in root.rglob("*") if p.is_file()}


def write_receipt(packet, manifest, name, receipt):
    path = packet / name
    path.write_text(json.dumps(receipt))
    manifest["assets_sha256"][name] = sha(path)


def save_manifest(packet, manifest):
    (packet / "manifest.json").write_text(json.dumps(manifest))
