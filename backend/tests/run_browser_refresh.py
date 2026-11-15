"""Run the real seed workflow refresh steps over test-owned loopback TLS."""

import http.client
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from tests.refresh_eligibility_fixture import SHA, needs_fixture


class RefreshProxy(BaseHTTPRequestHandler):
    # Forward only the three signed routes to the fixed Playwright fixtures.
    ports = {
        "/api/v1/system/cache/invalidate": 8125,
        "/api/v1/system/cache/status": 8125,
        "/api/revalidate": 3125,
    }

    def do_POST(self):
        size = int(self.headers.get("content-length", "0"))
        if self.path not in self.ports or not 0 < size <= 8192:
            self.send_error(400)
            return
        data = self.rfile.read(size)
        upstream = http.client.HTTPConnection("127.0.0.1", self.ports[self.path], timeout=5)
        try:
            upstream.request("POST", self.path, data, {
                name: self.headers[name]
                for name in ("content-type", "x-revalidate-signature", "accept-encoding")
            })
            response = upstream.getresponse()
            body = response.read(65537)
            if len(body) > 65536:
                self.send_error(502)
                return
            self.send_response(response.status)
            for name in ("content-type", "content-encoding", "x-revalidate-response-signature"):
                if value := response.getheader(name):
                    self.send_header(name, value)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        finally:
            upstream.close()


def run_refresh(directory):
    cert, key = directory / "cert.pem", directory / "key.pem"
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
        "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1",
        "-out", str(cert), "-keyout", str(key),
    ], check=True, capture_output=True, timeout=10)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    with HTTPServer(("127.0.0.1", 0), RefreshProxy) as server:
        server.socket = context.wrap_socket(server.socket, server_side=True)
        base = f"https://127.0.0.1:{server.server_port}"
        needs = needs_fixture()
        report = json.loads(needs["seed"]["outputs"]["report"])
        env = {
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
            "REVALIDATE_SECRET": os.environ.get("REVALIDATE_SECRET", ""),
            "SSL_CERT_FILE": str(cert),
            "API_BASE_URL": base,
            "REVALIDATE_URL": base + "/api/revalidate",
            "GITHUB_SHA": SHA,
            "GITHUB_RUN_ID": report["run_id"],
            "GITHUB_RUN_ATTEMPT": report["run_attempt"],
            "REFRESH_NEEDS": json.dumps(needs),
            "RUNNER_TEMP": str(directory),
            "GITHUB_OUTPUT": str(directory / "outputs"),
        }
        workflow = yaml.safe_load((ROOT / ".github/workflows/seed.yml").read_text())
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for step in workflow["jobs"]["revalidate"]["steps"]:
                if "run" not in step:
                    continue
                script = step["run"]
                if "${{" in script:
                    raise SystemExit("Unexpected workflow expression in refresh step")
                print(step["name"], flush=True)
                result = subprocess.run(
                    ["bash", "-eo", "pipefail", "-c", script],
                    cwd=ROOT, env=env, timeout=15,
                )
                if result.returncode:
                    return result.returncode
        finally:
            server.shutdown()
            thread.join()
    return 0


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="browser-refresh-") as runtime:
        raise SystemExit(run_refresh(Path(runtime).resolve()))
