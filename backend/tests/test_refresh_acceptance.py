"""Malformed or partial worker acknowledgements must stop frontend refresh."""

import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("refresh_acceptance", ROOT / "tools/verify_refresh_acceptance.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

MARKER = [123, 456, 32]
STATUS = {"pid": 7, "commit": "a" * 40, "marker_path": "/tmp/generation",
          "synchronised": True, "observed_identity": MARKER, "adopted_identity": MARKER}


def run(statuses, frontend=None, ack=None):
    calls = []
    def post(url, body):
        calls.append((url, body))
        if url.endswith("/invalidate"):
            return ack if ack is not None else {"invalidated": True, "marker_identity": MARKER,
                                               "generation": "a" * 32, "pid": 7}
        if url.endswith("/status"):
            return statuses.pop(0) if len(statuses) > 1 else statuses[0]
        return frontend if frontend is not None else {"revalidated": ["/", "/counties/[id]"], "rejected": []}
    return calls, lambda: module.refresh(
        post, api_url="https://backend.test", frontend_url="https://frontend.test/api/revalidate",
        pids=[7, 8], commit="a" * 40, marker_path="/tmp/generation",
        paths=["/", "/counties/[id]"], reason="test", attempts=3)


def test_acceptance_requires_each_worker_before_exact_frontend_paths():
    second = {**STATUS, "pid": 8}
    calls, execute = run([STATUS, second])
    receipt = execute()
    assert [worker["pid"] for worker in receipt["workers"]] == [7, 8]
    assert calls[-1][0] == "https://frontend.test/api/revalidate"
    assert calls[-1][1] == {"paths": ["/", "/counties/[id]"]}


@pytest.mark.parametrize("key,value", [
    ("pid", True), ("pid", 9), ("commit", "b" * 40), ("marker_path", "/other"),
    ("synchronised", "true"), ("observed_identity", None), ("adopted_identity", [123, 999, 32]),
    ("observed_identity", [True, 456, 32]), ("observed_identity", [123, 456, 0]),
])
def test_bad_worker_receipt_stops_before_frontend(key, value):
    status = copy.deepcopy(STATUS)
    status[key] = value
    calls, execute = run([status])
    with pytest.raises(ValueError):
        execute()
    assert all(not url.startswith("https://frontend.test") for url, _ in calls)


def test_repeated_one_worker_does_not_certify_sibling():
    calls, execute = run([STATUS])
    with pytest.raises(ValueError, match="not every"):
        execute()
    assert len(calls) == 4


@pytest.mark.parametrize("frontend", [
    {"revalidated": ["/", "/"], "rejected": []},
    {"revalidated": ["/", "/counties/[id]"], "rejected": ["/wrong"]},
    {"revalidated": "xx", "rejected": []}, None,
])
def test_frontend_must_acknowledge_exact_paths(frontend):
    calls, execute = run([STATUS, {**STATUS, "pid": 8}], frontend=frontend or {})
    with pytest.raises(ValueError, match="frontend"):
        execute()


def test_cli_writes_private_hash_bound_failure_receipt(tmp_path, monkeypatch):
    import json
    import sys
    tmp_path.chmod(0o700)
    output = tmp_path / "receipt.json"
    monkeypatch.setenv("REVALIDATE_SECRET", "local-test")
    monkeypatch.setattr(sys, "argv", ["verify_refresh_acceptance.py", "--execute",
        "--worker-pid", "7", "--backend-commit", "a" * 40, "--marker-path", "/tmp/generation",
        "--reason", "local-test", "--output", str(output)])
    def fail(*args, **kwargs):
        raise ValueError("bad acknowledgement")
    monkeypatch.setattr(module, "refresh", fail)
    assert module.main() == 1
    receipt = json.loads(output.read_text())
    assert receipt["status"] == "failed"
    assert receipt["error_class"] == "ValueError"
    assert receipt["generator_sha256"]
    assert output.stat().st_mode & 0o777 == 0o600
