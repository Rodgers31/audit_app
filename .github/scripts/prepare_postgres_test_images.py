#!/usr/bin/env python3
"""Bounded public image preparation for owned, offline PostgreSQL test fixtures."""
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
MAX_SECONDS = 240
DIAGNOSTIC_SAMPLE_BYTES = 8192
PIN = re.compile(r"(?:postgres|public\.ecr\.aws/supabase/postgres)@sha256:[0-9a-f]{64}")


class Refusal(RuntimeError):
    def __init__(self, reason, context=None):
        super().__init__(reason)
        self.receipt = {"status": "refused", "reason": reason, "phase": "configuration",
                        "image": None, "platform": None, "exit_code": None,
                        "diagnostic_category": "not_available", "stderr_bytes": 0,
                        "diagnostic_sample_truncated": False, **(context or {})}


def diagnostic(stderr):
    """Emit fixed categories, never child text, URLs, tokens or credentials."""
    stderr = stderr or b""
    sample = stderr[:DIAGNOSTIC_SAMPLE_BYTES].decode("utf8", errors="replace").lower()
    categories = (
        ("docker_daemon_unavailable", ("cannot connect to the docker daemon", "is the docker daemon running", "error during connect", "docker.sock: connect: permission denied")),
        ("registry_authorization_refused", ("unauthorized", "authentication required", "pull access denied", "no basic auth credentials")),
        ("registry_rate_limited", ("toomanyrequests", "too many requests", "429 too many")),
        ("registry_manifest_unavailable", ("manifest unknown", "manifest not found", "no matching manifest")),
        ("transport_tls_error", ("x509:", "tls handshake", "certificate verify")),
        ("transport_dns_error", ("no such host", "temporary failure in name resolution")),
        ("transport_timeout", ("context deadline exceeded", "i/o timeout", "timed out")),
        ("transport_connection_error", ("connection reset", "connection refused", "unexpected eof")),
        ("local_storage_exhausted", ("no space left on device",)),
    )
    category = next((name for name, patterns in categories if any(p in sample for p in patterns)),
                    "unclassified" if stderr else "no_stderr")
    return {"diagnostic_category": category, "stderr_bytes": len(stderr),
            "diagnostic_sample_truncated": len(stderr) > DIAGNOSTIC_SAMPLE_BYTES}


def missing_image(result, ref):
    # Exit 1 also covers unavailable/denied daemons. Only this exact image-bound
    # diagnostic authorizes a pull; ambiguous failures remain failures.
    expected = ("Error response from daemon: No such image: " + ref).encode()
    return (result.returncode == 1 and result.stdout.strip() in (b"", b"[]")
            and result.stderr.strip() == expected)


def required_images():
    # Read the tool's literal pins without executing backup/acquisition code.
    tree = ast.parse((ROOT / "tools/bounded_pg_backup.py").read_text())
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"IMAGE", "SUPABASE_IMAGE"}:
                    if target.id in values or not isinstance(node.value, ast.Constant):
                        raise Refusal("invalid_fixture_image_pin")
                    values[target.id] = node.value.value
    if set(values) != {"IMAGE", "SUPABASE_IMAGE"}:
        raise Refusal("missing_fixture_image_pin")
    images = [values[name] for name in ("IMAGE", "SUPABASE_IMAGE")]
    if any(not isinstance(ref, str) or PIN.fullmatch(ref) is None for ref in images):
        raise Refusal("mutable_or_invalid_fixture_image_pin")
    return images


def prepare():
    deadline = time.monotonic() + MAX_SECONDS
    context = {"phase": "docker_server", "image": None, "platform": None, "exit_code": None}

    def refuse(reason):
        raise Refusal(reason, context)

    def run(args, *, phase, image=None, missing=False, timeout=15):
        context.update(phase=phase, image=image, exit_code=None,
                       diagnostic_category="not_available", stderr_bytes=0,
                       diagnostic_sample_truncated=False)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            refuse("image_preparation_deadline")
        try:
            result = subprocess.run(
                ["docker", *args], capture_output=True,
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                timeout=min(timeout, remaining), check=False,
            )
        except subprocess.TimeoutExpired as exc:
            context.update(diagnostic(exc.stderr))
            context["diagnostic_category"] = "command_timeout"
            refuse("image_preparation_unavailable_or_timed_out")
        except OSError:
            context["diagnostic_category"] = "docker_client_unavailable"
            refuse("image_preparation_unavailable_or_timed_out")
        context.update(exit_code=result.returncode, **diagnostic(result.stderr))
        if result.returncode:
            if missing and missing_image(result, image):
                return None
            refuse("image_preparation_command_failed")
        return result.stdout

    def decode(raw):
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            refuse("invalid_docker_image_metadata")

    server = decode(run(["version", "--format", "{{json .Server}}"], phase="docker_server"))
    if not isinstance(server, dict) or server.get("Os") != "linux" or server.get("Arch") not in {"amd64", "arm64"}:
        refuse("unsupported_native_docker_platform")
    platform = "linux/" + server["Arch"]
    context["platform"] = platform
    for ref in required_images():
        raw = run(["image", "inspect", ref], phase="inspect_cached", image=ref, missing=True)
        if raw is None:
            run(["pull", "--platform", platform, ref], phase="pull", image=ref, timeout=MAX_SECONDS)
            raw = run(["image", "inspect", ref], phase="inspect_pulled", image=ref)
        records = decode(raw)
        if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
            refuse("invalid_docker_image_metadata")
        image = records[0]
        if (not isinstance(image.get("RepoDigests"), list) or ref not in image["RepoDigests"]
                or not isinstance(image.get("Id"), str) or re.fullmatch(r"sha256:[0-9a-f]{64}", image["Id"]) is None
                or image.get("Os") != "linux" or image.get("Architecture") != server["Arch"]):
            refuse("fixture_image_identity_or_platform_mismatch")
        print(f"Prepared {ref} ({platform}; {image['Id']})", flush=True)


if __name__ == "__main__":
    try:
        prepare()
    except Refusal as exc:
        print(json.dumps(exc.receipt, sort_keys=True), file=sys.stderr, flush=True)
        sys.exit(1)
