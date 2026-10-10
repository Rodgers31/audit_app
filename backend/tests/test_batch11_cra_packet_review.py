"""Current receipts must cover the complete source graph and executed states."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = "docs/admin/implementation/batch11-issue-602-evidence/tools/record_v4.py"

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

verifier = load(ROOT / "docs/admin/implementation/batch11-issue-602-evidence/tools/verify_packet_v3.py", "cra_review_verifier")
recorder = load(ROOT / IDENTITY, "cra_review_recorder")

@pytest.fixture
def current(tmp_path):
    repo = tmp_path / "repo"
    target = repo / IDENTITY
    target.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / IDENTITY, target)
    for name in ("backend/admin_etl_dispatch.py", "backend/seeding/config.py", ".github/workflows/verification.yml"):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("owned source\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Owned fixture", "-c", "user.email=owned@example.invalid", "commit", "-qm", "fixture"], check=True)
    sources = recorder.source(repo)
    digest = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()
    record = {"generated_by": IDENTITY, "generator_sha256": sources[IDENTITY], "mode": "pytest", "label": "review-control",
              "exit_code": 0, "complete_inventory": True, "timed_out": False, "source_drift": [], "source_files": sources,
              "testcases": [{"id": "owned::case", "state": "passed"}], "counts": dict.fromkeys(verifier.STATES, 0),
              "leftover_process_group": False, "ci_parity_environment": False,
              "process_group_absent_after_cleanup": True,
              "owned_containers_before": [], "owned_containers_after": [],
              "source_before_sha256": digest, "source_after_sha256": digest,
              "started_at": "2026-10-10T20:00:00+00:00", "finished_at": "2026-10-10T20:00:01+00:00"}
    record["counts"]["passed"] = 1
    record["head"], record["tree"] = recorder.git(repo, "rev-parse", "HEAD", "HEAD^{tree}").split()
    record["status_before"] = record["status_after"] = ""
    for name, content in (("output.log", "owned case passed"),
                          ("junit.xml", '<testsuites><testsuite><testcase classname="owned" name="case"/></testsuite></testsuites>')):
        (tmp_path / name).write_text(content)
    record["output_files"] = {name: recorder.sha(tmp_path / name) for name in ("output.log", "junit.xml")}
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(record))
    return repo, path, record

def test_complete_graph_is_accepted(current):
    repo, path, _ = current
    assert verifier.current_execution(path, repo)["current_checkout_acceptance"] is True

@pytest.mark.parametrize("source", ["backend/admin_etl_dispatch.py", "backend/seeding/config.py", ".github/workflows/verification.yml"])
def test_changed_source_outside_old_filter_is_rejected(current, source):
    repo, path, _ = current
    (repo / source).write_text("changed source\n")
    assert verifier.current_execution(path, repo)["current_checkout_acceptance"] is False

@pytest.mark.parametrize("mutation", ["missing_source", "empty_source", "failed", "error", "xpass", "leftover", "cleanup", "container", "digest", "head", "tree"])
def test_well_typed_false_green_is_rejected(current, mutation):
    repo, path, record = current
    if mutation == "missing_source":
        record["source_files"].pop("backend/admin_etl_dispatch.py")
    elif mutation == "empty_source":
        record["source_files"] = {}
    elif mutation in ("failed", "error", "xpass"):
        record["testcases"][0]["state"] = mutation
        record["counts"]["passed"], record["counts"][mutation] = 0, 1
    elif mutation == "leftover":
        record["leftover_process_group"] = True
    elif mutation == "cleanup":
        record["process_group_absent_after_cleanup"] = False
    elif mutation == "container":
        record["owned_containers_after"] = ["owned-residue"]
    elif mutation == "digest":
        record["source_after_sha256"] = "0" * 64
    else:
        record[mutation] = "0" * 40
    path.write_text(json.dumps(record))
    assert verifier.current_execution(path, repo)["current_checkout_acceptance"] is False

@pytest.mark.parametrize("linked", ["file", "ancestor"])
def test_source_links_are_refused_before_reading(current, tmp_path, linked):
    repo, _, _ = current
    external = tmp_path / "outside"
    external.mkdir()
    (external / "admin_etl_dispatch.py").write_text("external input")
    if linked == "file":
        path = repo / "backend/admin_etl_dispatch.py"
        path.unlink()
        path.symlink_to(external / path.name)
    else:
        shutil.rmtree(repo / "backend")
        (repo / "backend").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="Linked or missing source input"):
        recorder.source(repo)


@pytest.mark.parametrize("name", ["output.log", "junit.xml"])
def test_edited_execution_output_refuses(current, name):
    repo, path, _ = current
    (path.parent / name).write_text("tampered output")
    with pytest.raises(verifier.Refused, match="Raw execution output changed"):
        verifier.current_execution(path, repo)


@pytest.mark.parametrize("mutation", [None, "empty", "missing", "duplicate"])
def test_launcher_recomputes_collection_outcomes(current, mutation):
    repo, path, record = current
    record["mode"] = "launcher"
    record["testcases"] = [{"id": "tests/backend.py::case", "state": "passed"},
                           {"id": "tests/legacy.py::case", "state": "passed"}]
    record["counts"]["passed"] = 2
    (path.parent / "output.log").write_text("tests/backend.py::case PASSED\ntests/legacy.py::case PASSED\n")
    record["output_files"] = {"output.log": recorder.sha(path.parent / "output.log")}
    for cohort in ("backend", "legacy"):
        nodes = [f"tests/{cohort}.py::case"]
        if cohort == "legacy" and mutation == "empty":
            nodes = []
        elif cohort == "legacy" and mutation == "missing":
            nodes = ["tests/legacy.py::unexecuted"]
        elif cohort == "legacy" and mutation == "duplicate":
            nodes = ["tests/backend.py::case"]
        member = path.parent / "core" / f"collection-{cohort}.json"
        member.parent.mkdir(exist_ok=True)
        member.write_text(json.dumps({"nodeids": nodes}))
        record["output_files"][str(member.relative_to(path.parent))] = recorder.sha(member)
    path.write_text(json.dumps(record))
    if mutation is None:
        assert verifier.current_execution(path, repo)["current_checkout_acceptance"] is True
    else:
        with pytest.raises(verifier.Refused, match="Current launcher"):
            verifier.current_execution(path, repo)


def test_actual_non_strict_xpass_is_not_passed(tmp_path):
    test = tmp_path / "owned_xpass.py"
    test.write_text("import pytest\n@pytest.mark.xfail(reason='owned outcome control', strict=False)\ndef test_unexpected():\n    assert True\n")
    xml = tmp_path / "actual.xml"
    result = subprocess.run([sys.executable, "-m", "pytest", str(test), "-q", "-rA",
                             "--junitxml=" + str(xml), "-p", "no:cacheprovider", "-o", "addopts="],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0 and "XPASS" in result.stdout
    assert recorder.junit_cases(xml, result.stdout)[0]["state"] == "xpass"


def test_xpass_without_case_identity_refuses(current):
    _, path, _ = current
    with pytest.raises(ValueError, match="XPASS summary lacks"):
        recorder.junit_cases(path.parent / "junit.xml", "1 xpassed in 0.01s")


def test_successful_parent_survivor_is_physically_cleaned(tmp_path):
    marker = tmp_path / "late-marker"
    worker = "import time; from pathlib import Path; time.sleep(30); Path(" + repr(str(marker)) + ").write_text('late')"
    parent = "import subprocess,sys; subprocess.Popen([sys.executable,'-c'," + repr(worker) + "], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)"
    process = subprocess.Popen([sys.executable, "-c", parent], start_new_session=True)
    try:
        assert process.wait(timeout=10) == 0 and recorder.group_present(process.pid)
        assert recorder.cleanup_group(process.pid) is True
        assert not recorder.group_present(process.pid) and not marker.exists()
    finally:
        recorder.cleanup_group(process.pid)
