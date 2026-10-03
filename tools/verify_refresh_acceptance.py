"""Run the approved refresh step; seed/full validation and browser proof are separate.

No requests run without --execute. REVALIDATE_SECRET comes only from the private
process environment. A current worker census is required: sampling one worker
cannot certify its siblings. This utility does not activate GitHub Actions.
"""

import argparse
import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import time
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def identity(value):
    if (not isinstance(value, list) or len(value) != 3
            or any(type(v) is not int or v < 0 for v in value)
            or value[0] == 0 or value[2] != 32):
        raise ValueError("invalid marker identity")
    return value


def require_worker(body, marker, pids, commit, marker_path):
    identity(marker)
    if (not pids or any(type(pid) is not int or pid <= 0 for pid in pids)
            or len(set(pids)) != len(pids)):
        raise ValueError("nonempty unique worker census required")
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or not marker_path.startswith("/"):
        raise ValueError("full backend commit and absolute loaded marker path required")
    if not isinstance(body, dict):
        raise ValueError("worker status must be an object")
    pid = body.get("pid")
    if type(pid) is not int or pid not in pids:
        raise ValueError("worker outside approved census")
    if body.get("commit") != commit or body.get("marker_path") != marker_path:
        raise ValueError("loaded commit/path differ from approved target")
    if (body.get("synchronised") is not True
            or identity(body.get("observed_identity")) != marker
            or identity(body.get("adopted_identity")) != marker):
        raise ValueError("worker did not adopt invalidation identity")
    return pid


def refresh(post, *, api_url, frontend_url, pids, commit, marker_path, paths,
            reason, attempts=30):
    if (not pids or any(type(pid) is not int or pid <= 0 for pid in pids)
            or len(set(pids)) != len(pids)):
        raise ValueError("nonempty unique worker census required")
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or not marker_path.startswith("/"):
        raise ValueError("full backend commit and absolute loaded marker path required")
    if (not paths or any(not isinstance(path, str) for path in paths)
            or len(set(paths)) != len(paths)):
        raise ValueError("nonempty unique path manifest required")
    ack = post(api_url + "/api/v1/system/cache/invalidate", {
        "ts": int(time.time()), "reason": reason
    })
    if not isinstance(ack, dict) or ack.get("invalidated") is not True:
        raise ValueError("backend did not acknowledge invalidation")
    marker = identity(ack.get("marker_identity"))
    if not isinstance(ack.get("generation"), str) or not re.fullmatch(
        r"[0-9a-f]{32}", ack["generation"]
    ):
        raise ValueError("invalid generation token")
    if type(ack.get("pid")) is not int or ack["pid"] not in pids:
        raise ValueError("invalidation worker outside approved census")
    workers = {}
    for _ in range(attempts):
        status = post(api_url + "/api/v1/system/cache/status", {"ts": int(time.time())})
        pid = require_worker(status, marker, pids, commit, marker_path)
        workers[pid] = status
        if set(workers) == set(pids):
            break
    if set(workers) != set(pids):
        raise ValueError("not every approved worker acknowledged; frontend not refreshed")
    frontend = post(frontend_url, {"paths": paths})
    if (not isinstance(frontend, dict) or frontend.get("rejected") != []
            or not isinstance(frontend.get("revalidated"), list)
            or any(not isinstance(v, str) for v in frontend["revalidated"])
            or sorted(frontend["revalidated"]) != sorted(paths)):
        raise ValueError("frontend did not acknowledge exact allowed paths")
    return {"invalidation": ack, "workers": list(workers.values()), "frontend": frontend,
            "scope": "Signed refresh acknowledgements only; source/full-validation/API/browser acceptance separate"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="perform the separately approved cache operation")
    parser.add_argument("--api-url", default="https://audit-app-4pwa.onrender.com")
    parser.add_argument("--frontend-url", default="https://www.auditgava.com/api/revalidate")
    parser.add_argument("--worker-pid", type=int, action="append", required=True)
    parser.add_argument("--backend-commit", required=True)
    parser.add_argument("--marker-path", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required after coordinator approval; no requests sent")
    if args.output.exists() or args.output.parent.stat().st_mode & 0o077:
        parser.error("output must be new in a private directory (0700)")
    secret = os.environ.get("REVALIDATE_SECRET")
    if not secret:
        parser.error("REVALIDATE_SECRET missing; no requests sent")
    for url in (args.api_url, args.frontend_url):
        target = urlsplit(url)
        if (not target.hostname or target.username or target.password or target.query
                or target.fragment or (target.scheme != "https" and not (
                    target.scheme == "http" and target.hostname in ("localhost", "127.0.0.1", "::1")))):
            parser.error("HTTPS target required (HTTP allowed only on loopback); no credentials/query/fragment")
    # Redirects cannot forward a signed cache operation to another target.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *unused, **kw):
            return None
    opener = urllib.request.build_opener(NoRedirect())
    started = time.monotonic()
    def post(url, body):
        remaining = 120 - (time.monotonic() - started)
        if remaining <= 0:
            raise ValueError("refresh wall limit reached")
        raw = json.dumps(body, separators=(",", ":")).encode()
        request = urllib.request.Request(url, data=raw, method="POST", headers={
            "Content-Type": "application/json",
            "x-revalidate-signature": hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest(),
        })
        with opener.open(request, timeout=min(15, remaining)) as response:
            raw_response = response.read(65537)
            if response.status != 200 or len(raw_response) > 65536:
                raise ValueError("unexpected HTTP response or byte ceiling")
            return json.loads(raw_response)
    paths = json.loads((ROOT / "frontend/lib/revalidation/paths.json").read_text())["paths"]
    receipt = {"generated_by": str(Path(__file__).resolve()),
               "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "target_commit": args.backend_commit, "api_url": args.api_url,
               "frontend_url": args.frontend_url, "expected_worker_pids": args.worker_pid,
               "manifest_sha256": hashlib.sha256((ROOT / "frontend/lib/revalidation/paths.json").read_bytes()).hexdigest()}
    try:
        receipt.update(refresh(post, api_url=args.api_url.rstrip("/"), frontend_url=args.frontend_url,
                               pids=args.worker_pid, commit=args.backend_commit,
                               marker_path=args.marker_path, paths=paths, reason=args.reason))
        receipt["status"] = "acknowledged"
    except Exception as exc:
        receipt.update(status="failed", error_class=type(exc).__name__,
                       scope="Refresh incomplete; may have cleared backend or partially refreshed frontend")
    with open(args.output, "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as output:
        json.dump(receipt, output, indent=2)
    reread = json.loads(args.output.read_text())
    assert reread["generator_sha256"] == receipt["generator_sha256"]
    print(json.dumps({"status": receipt["status"], "receipt": str(args.output)}))
    return 0 if receipt["status"] == "acknowledged" else 1


if __name__ == "__main__":
    raise SystemExit(main())
