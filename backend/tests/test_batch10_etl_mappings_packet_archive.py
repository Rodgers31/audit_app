"""Retained historical corpus and append-only identity rejection, normal/-O."""
import gzip
import json
import stat
import zipfile

import pytest

from batch10_packet_fixture import copy_packet, invoke, save_manifest, sha, snapshot, write_receipt

ATTACKS = (
    "duplicate_member", "missing_member", "extra_member", "traversal_member",
    "absolute_member", "backslash_member", "symlink_member", "changed_source",
    "pruned_source_inventory", "boolean_source_count", "changed_classification",
    "current_acceptance", "unindexed_asset", "unindexed_manifest", "symlink_asset", "extracted_extra",
    "extracted_missing", "extracted_symlink", "coordinated_execution_rebind",
)


@pytest.mark.parametrize("optimized", [False, True])
@pytest.mark.parametrize("attack", ATTACKS)
def test_retained_corpus_refuses_unsafe_or_rebound_evidence(tmp_path, optimized, attack):
    root = tmp_path / "copy"
    packet, manifest = copy_packet(root)
    archive_name = manifest["retained_source"]["archive"]
    archive_path = packet / archive_name
    if attack.endswith("member") or attack == "changed_source":
        with zipfile.ZipFile(archive_path) as archive:
            members = [(info, archive.read(info)) for info in archive.infolist()]
        if attack == "duplicate_member":
            members.append(members[0])
        elif attack == "missing_member":
            members.pop()
        elif attack == "extra_member":
            info = zipfile.ZipInfo("unexpected.py")
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            members.append((info, b"# unexpected source\n"))
        elif attack in ("traversal_member", "absolute_member", "backslash_member"):
            info, body = members[0]
            info.filename = {"traversal_member": "../outside.py", "absolute_member": "/outside.py", "backslash_member": "backend\\outside.py"}[attack]
            members[0] = info, body
        elif attack == "symlink_member":
            members[0][0].external_attr = (stat.S_IFLNK | 0o777) << 16
        elif attack == "changed_source":
            info, body = members[0]
            members[0] = info, body + b"\n# mutated recorded source\n"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for info, body in members:
                archive.writestr(info, body)
        manifest["retained_source"]["sha256"] = sha(archive_path)
        manifest["assets_sha256"][archive_name] = sha(archive_path)
    elif attack == "pruned_source_inventory":
        manifest["source_sha256"].pop(next(iter(manifest["source_sha256"])))
    elif attack == "boolean_source_count":
        manifest["retained_source"]["source_files"] = True
    elif attack == "changed_classification":
        manifest["classification"] = "CURRENT_ACCEPTANCE"
    elif attack == "current_acceptance":
        manifest["current_checkout_acceptance"] = True
    elif attack == "unindexed_asset":
        (packet / "unindexed.txt").write_text("unrecorded")
    elif attack == "unindexed_manifest":
        (packet / "unindexed").mkdir()
        (packet / "unindexed/manifest.json").write_text('{"unrecorded":true}')
    elif attack == "symlink_asset":
        victim = packet / "README.md"
        body = victim.read_bytes()
        victim.unlink()
        outside = tmp_path / "outside.md"
        outside.write_bytes(body)
        victim.symlink_to(outside)
    elif attack in ("extracted_extra", "extracted_missing", "extracted_symlink"):
        fixture = root / "retained-source"
        victim = fixture / next(iter(manifest["source_sha256"]))
        if attack == "extracted_extra":
            (fixture / "extra.py").write_text("extra")
        elif attack == "extracted_missing":
            victim.unlink()
        else:
            body = victim.read_bytes()
            victim.unlink()
            outside = tmp_path / "outside.py"
            outside.write_bytes(body)
            victim.symlink_to(outside)
    elif attack == "coordinated_execution_rebind":
        name = manifest["checks"][0]["receipt"]
        receipt = json.loads((packet / name).read_text())
        original_path = packet / receipt["original_receipt"]
        original = json.loads(gzip.decompress(original_path.read_bytes()))
        receipt["environment"]["JWT_SECRET"] = "rebound-inert"
        original["environment"] = dict(receipt["environment"])
        original_path.write_bytes(gzip.compress(json.dumps(original).encode(), mtime=0))
        manifest["assets_sha256"][receipt["original_receipt"]] = sha(original_path)
        write_receipt(packet, manifest, name, receipt)
    save_manifest(packet, manifest)
    inherited = packet / "inherited-verdict.json"
    inherited.write_bytes(b'{"historical":true,"verdict":"original"}\n')
    before = snapshot(root)
    result = invoke(packet, root, optimized, retained_source=True)
    assert result.returncode != 0 and "PASSED" not in result.stdout, (attack, result.stdout, result.stderr)
    assert "ValueError:" in result.stderr, result.stderr
    assert snapshot(root) == before
