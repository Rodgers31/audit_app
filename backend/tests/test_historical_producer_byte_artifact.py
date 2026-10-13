"""Historical failed producer bytes remain evidence, outside live Python source.

Issue #629: the route source registry tried to parse an archived producer's
known syntax failure during collection. Preserve that failure as byte input;
the whole-tree source scanner and its fail-closed parser remain unchanged.
"""

import ast
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess

import pytest

from tests._repo_tree import REPO_ROOT, python_modules


PACKET = REPO_ROOT / "docs/admin/implementation/batch11-issue-607-evidence"
ORIGINAL = PACKET / "archive-generators/record_v2.py"
ARTIFACT = ORIGINAL.with_suffix(".py.txt")
ORIGINAL_SHA256 = "d7e6fb4d511827690d103d6b78946a5e6eecd44c15d0e907519fd90b0c234dfd"


def test_failed_historical_producer_is_preserved_but_not_live_source():
    # Selecting these same malformed bytes as live source was the collection
    # failure. Do not make the historical attempt parse to obtain a green run.
    source = ORIGINAL if ORIGINAL.is_file() else ARTIFACT
    assert hashlib.sha256(source.read_bytes()).hexdigest() == ORIGINAL_SHA256
    with pytest.raises(SyntaxError) as error:
        ast.parse(source.read_bytes(), filename=str(ORIGINAL))
    assert error.value.lineno == 32
    assert ORIGINAL not in python_modules(), "historical failed producer selected as live Python"
    assert ARTIFACT.is_file()
    assert not ORIGINAL.exists()


def test_malformed_live_python_is_still_selected_and_fails_closed(tmp_path):
    from tests.test_advertised_endpoints_are_served import find_registered_routes

    live = tmp_path / "brand_new_package/live.py"
    live.parent.mkdir()
    live.write_text("sys.exit(0 if result['helper_hashes']=helpers\n")
    assert python_modules(tmp_path) == [live]
    with pytest.raises(SyntaxError):
        find_registered_routes(live.read_text(), str(live))


def layout_verifier():
    path = PACKET / "tools/verify_archive_layout.py"
    spec = importlib.util.spec_from_file_location("archive_layout_boundary", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def packet_fixture(tmp_path):
    packet = tmp_path / "packet"
    packet.mkdir()
    for name in ("historical-byte-layout.json", "packet-v1.json", "packet-v2.json"):
        shutil.copyfile(PACKET / name, packet / name)
    shutil.copytree(PACKET / "archive-generators", packet / "archive-generators")
    return packet


def test_layout_preserves_all_archived_bytes_and_both_manifest_identities():
    result = layout_verifier().verify_layout(REPO_ROOT)
    assert result["original_archives_verified"] == 65
    assert result["manifest_archive_counts"] == {"packet-v1.json": 64, "packet-v2.json": 65}
    assert result["mapped_byte_artifacts"] == 1
    assert result["fresh_execution"] is False
    assert result["recorded_acceptance"] is False
    assert result["original_git_bytes_verified"] is False
    assert result["original_git_bytes_status"] == "not-requested"


def test_portable_layout_accepts_shallow_checkout_and_strict_requires_history(tmp_path):
    module = layout_verifier()
    seed = tmp_path / "seed"
    seed.mkdir()
    packet_fixture(seed)
    environment = {"PATH": "/usr/bin:/bin", "HOME": "/dev/null",
                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
                   "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_NO_REPLACE_OBJECTS": "1"}

    def git(*arguments, cwd=seed):
        return subprocess.run(["/usr/bin/git", *arguments], cwd=cwd, env=environment,
                              check=True, capture_output=True, text=True, timeout=20).stdout

    git("init", "-q")
    git("add", "--", "packet")
    git("-c", "user.name=Owned fixture", "-c", "user.email=owned@example.invalid",
        "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
        "commit", "-qm", "Owned archive fixture")
    shallow = tmp_path / "shallow"
    git("clone", "-q", "--depth=1", seed.as_uri(), str(shallow))
    assert git("rev-parse", "--is-shallow-repository", cwd=shallow).strip() == "true"
    result = module.verify_layout(shallow, shallow / "packet")
    assert result["original_archives_verified"] == 65
    assert result["original_git_bytes_verified"] is False
    with pytest.raises(ValueError, match="Original Git bytes unavailable"):
        module.verify_layout(shallow, shallow / "packet", require_original_git_bytes=True)


@pytest.mark.parametrize("mutation", [
    "restored_executable", "missing_artifact", "changed_artifact", "extra_archive",
    "missing_archive", "changed_manifest", "changed_correspondence",
    "duplicate_metadata_key", "artifact_symlink", "archive_ancestor_symlink", "extra_fifo",
    "extra_empty_directory",
])
def test_layout_refuses_changed_or_ambiguous_historical_inputs(tmp_path, mutation):
    module = layout_verifier()
    packet = packet_fixture(tmp_path)
    artifact = packet / "archive-generators/record_v2.py.txt"
    if mutation == "restored_executable":
        shutil.copyfile(artifact, artifact.with_suffix(""))
    elif mutation == "missing_artifact":
        artifact.unlink()
    elif mutation == "changed_artifact":
        artifact.write_bytes(artifact.read_bytes() + b"\n# altered\n")
    elif mutation == "extra_archive":
        (packet / "archive-generators/extra.py.txt").write_text("x=1\n")
    elif mutation == "missing_archive":
        next(path for path in (packet / "archive-generators").iterdir()
             if path.is_file() and path != artifact).unlink()
    elif mutation == "changed_manifest":
        path = packet / "packet-v2.json"
        path.write_bytes(path.read_bytes() + b"\n")
    elif mutation == "changed_correspondence":
        path = packet / "historical-byte-layout.json"
        layout = json.loads(path.read_bytes())
        layout["moves"][0]["artifact_path"] = "archive-generators/borrowed.py.txt"
        path.write_text(json.dumps(layout))
    elif mutation == "duplicate_metadata_key":
        path = packet / "historical-byte-layout.json"
        path.write_text(path.read_text().replace('"schema": 1,', '"schema": 1, "schema": 1,'))
    elif mutation == "artifact_symlink":
        artifact.unlink()
        artifact.symlink_to(ARTIFACT)
    elif mutation == "archive_ancestor_symlink":
        directory = packet / "archive-generators"
        directory.rename(tmp_path / "borrowed-archive")
        directory.symlink_to(tmp_path / "borrowed-archive", target_is_directory=True)
    elif mutation == "extra_fifo":
        os.mkfifo(packet / "archive-generators/uncatalogued.fifo")
    elif mutation == "extra_empty_directory":
        (packet / "archive-generators/uncatalogued-empty").mkdir()
    with pytest.raises(ValueError):
        module.verify_layout(REPO_ROOT, packet)
