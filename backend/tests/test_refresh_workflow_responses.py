"""Execute the deployed workflow scripts against malformed HTTP success bodies."""

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/seed.yml").read_text())
PATHS = json.loads((ROOT / "frontend/lib/revalidation/paths.json").read_text())["paths"]


def run_refresh(tmp_path, invalidated, revalidated):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            calls.append(self.path)
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            body = invalidated if self.path.endswith("/invalidate") else revalidated
            payload = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    env = {
        **os.environ,
        "REVALIDATE_SECRET": "test-only-key",
        "API_BASE_URL": url,
        "REVALIDATE_URL": url + "/revalidate",
    }
    try:
        for step in WORKFLOW["jobs"]["revalidate"]["steps"]:
            if "run" not in step:
                continue
            script = (
                step["run"]
                .replace("${{ github.run_id }}", "regression")
                .replace("/tmp/", str(tmp_path) + "/")
            )
            result = subprocess.run(
                ["bash", "-eo", "pipefail", "-c", script],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode:
                break
        return result.returncode, calls
    finally:
        server.shutdown()
        server.server_close()


def test_valid_responses_refresh_in_order(tmp_path):
    code, calls = run_refresh(
        tmp_path, {"invalidated": True}, {"revalidated": PATHS, "rejected": []}
    )
    assert code == 0
    assert calls == ["/api/v1/system/cache/invalidate", "/revalidate"]


@pytest.mark.parametrize("value", ["true", False, None, 1])
def test_invalidation_requires_boolean_true(tmp_path, value):
    code, calls = run_refresh(
        tmp_path, {"invalidated": value}, {"revalidated": PATHS, "rejected": []}
    )
    assert code != 0
    assert calls == ["/api/v1/system/cache/invalidate"]


@pytest.mark.parametrize(
    "value",
    [
        "x" * len(PATHS),
        ["/"] * len(PATHS),
        ["/wrong" + str(i) for i in range(len(PATHS))],
        {},
        None,
    ],
)
def test_frontend_must_confirm_exact_requested_paths(tmp_path, value):
    code, _ = run_refresh(
        tmp_path, {"invalidated": True}, {"revalidated": value, "rejected": []}
    )
    assert code != 0


def test_invalidation_rejects_a_stream_of_conflicting_json_documents(tmp_path):
    code, calls = run_refresh(
        tmp_path,
        b'{"invalidated":false}\n{"invalidated":true}',
        {"revalidated": PATHS, "rejected": []},
    )
    assert code != 0
    assert calls == ["/api/v1/system/cache/invalidate"]


def test_revalidation_rejects_a_stream_of_conflicting_json_documents(tmp_path):
    receipts = (
        json.dumps({"revalidated": [], "rejected": []})
        + "\n"
        + json.dumps({"revalidated": PATHS, "rejected": []})
    )
    code, _ = run_refresh(tmp_path, {"invalidated": True}, receipts.encode())
    assert code != 0
