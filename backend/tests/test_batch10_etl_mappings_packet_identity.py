"""Actual #610 malformed metadata/XML and sibling-source regression controls."""
import json
import xml.etree.ElementTree as ET

import pytest

from batch10_packet_fixture import PACKET, copy_packet, invoke, save_manifest, sha, snapshot, write_receipt

ATTACKS = (
    "duplicate_identity", "blank_name", "blank_classname",
    "publication_hash", "publication_path", "recorder_alias",
    "receipt_publication_hash", "receipt_publication_path",
    "missing_environment", "changed_environment", "changed_command",
    "changed_cwd", "changed_runtime", "changed_start", "changed_end",
    "changed_head", "changed_tree", "boolean_verification_exit",
    "boolean_count", "pruned_source_identity",
)


@pytest.mark.parametrize("optimized", [False, True])
@pytest.mark.parametrize("attack", ATTACKS)
def test_historical_packet_refuses_inconsistent_identity(tmp_path, optimized, attack):
    root = tmp_path / "copy"
    packet, manifest = copy_packet(root)
    name = manifest["checks"][0]["receipt"]
    receipt = json.loads((packet / name).read_text())
    if attack in ("duplicate_identity", "blank_name", "blank_classname"):
        xml = packet / receipt["junit"]
        tree = ET.parse(xml)
        cases = list(tree.getroot().iter("testcase"))
        assert len(cases) == 519
        if attack == "duplicate_identity":
            cases[1].set("name", cases[0].attrib["name"])
            cases[1].set("classname", cases[0].attrib["classname"])
            assert len({(c.attrib["classname"], c.attrib["name"]) for c in cases}) == 518
        else:
            cases[0].set("name" if attack == "blank_name" else "classname", "   ")
        tree.write(xml, encoding="utf-8", xml_declaration=True)
        receipt["junit_sha256"] = sha(xml)
        manifest["assets_sha256"][receipt["junit"]] = sha(xml)
    elif attack.startswith("publication_"):
        manifest["generator_sha256" if attack == "publication_hash" else "generated_by"] = "0" * 64 if attack == "publication_hash" else "build_package.py"
    elif attack == "recorder_alias":
        receipt["generated_by"] = "generators/run_legacy.py"
    elif attack.startswith("receipt_publication_"):
        receipt["publication_generator_sha256" if attack.endswith("hash") else "publication_generator"] = "0" * 64 if attack.endswith("hash") else "revise_package.py"
    elif attack == "missing_environment":
        receipt.pop("environment")
    elif attack == "changed_environment":
        receipt["environment"]["JWT_SECRET"] = "different-inert-secret"
    elif attack == "changed_command":
        receipt["command"] = ["python", "-c", "print('different run')"]
    elif attack in ("changed_cwd", "changed_runtime", "changed_head", "changed_tree"):
        field = {"changed_cwd": "cwd", "changed_runtime": "runtime", "changed_head": "source_head", "changed_tree": "source_tree"}[attack]
        receipt[field] = "changed-inert-value"
    elif attack == "changed_start":
        receipt["started_at"] -= 1
    elif attack == "changed_end":
        receipt["ended_at"] += 1
    elif attack == "boolean_verification_exit":
        receipt["verification_exit"] = False
    elif attack == "boolean_count":
        receipt["counts"]["failures"] = False
    elif attack == "pruned_source_identity":
        key = next(iter(receipt["source_before"]))
        receipt["source_before"].pop(key)
        receipt["source_after"].pop(key)
    write_receipt(packet, manifest, name, receipt)
    save_manifest(packet, manifest)
    inherited = packet / "inherited-verdict.json"
    inherited.write_bytes(b'{"historical":true,"verdict":"old"}\n')
    before = snapshot(root)
    result = invoke(packet, root, optimized)
    assert result.returncode != 0 and "PASSED" not in result.stdout, (attack, result.stdout, result.stderr)
    assert "ValueError:" in result.stderr, result.stderr
    assert snapshot(root) == before


@pytest.mark.parametrize("optimized", [False, True])
def test_valid_sibling_source_does_not_rebind_historical_execution(tmp_path, optimized):
    root = tmp_path / "candidate"
    packet, _ = copy_packet(root)
    # A later checkout can legitimately have different startup source. Only the
    # historical archive certifies the historical execution; live bytes cannot
    # overwrite that identity or cause the positive fixture to fail integration.
    for name in ("backend/main.py", "backend/bootstrap.py"):
        source = root / "retained-source" / name
        current = root / name
        current.parent.mkdir(parents=True, exist_ok=True)
        current.write_bytes(source.read_bytes() + b"\n# Independently changed sibling source.\n")
    (packet / "inherited-verdict.json").write_bytes(b'{"historical":true}\n')
    before = snapshot(root)
    result = invoke(packet, root, optimized)
    assert result.returncode == 0, result.stderr
    actual = json.loads(result.stdout)
    assert actual["verdict"] == "PASSED"
    assert actual["classification"] == "HISTORICAL_EXECUTION_PACKET"
    assert actual["current_checkout_acceptance"] is False
    assert actual["source_files"] == 1160 and actual["executed_source_files"] == 1158
    assert snapshot(root) == before
