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
PIN = re.compile(r"(?:postgres|public\.ecr\.aws/supabase/postgres)@sha256:[0-9a-f]{64}")


class Refusal(RuntimeError):
    pass


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

    def run(args, *, missing=False, timeout=15):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Refusal("image_preparation_deadline")
        try:
            result = subprocess.run(
                ["docker", *args], capture_output=True,
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                timeout=min(timeout, remaining), check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise Refusal("image_preparation_unavailable_or_timed_out") from None
        if result.returncode:
            if missing and result.returncode == 1:
                return None
            raise Refusal("image_preparation_command_failed")
        return result.stdout

    def decode(raw):
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            raise Refusal("invalid_docker_image_metadata") from None

    server = decode(run(["version", "--format", "{{json .Server}}"]))
    if not isinstance(server, dict) or server.get("Os") != "linux" or server.get("Arch") not in {"amd64", "arm64"}:
        raise Refusal("unsupported_native_docker_platform")
    platform = "linux/" + server["Arch"]
    for ref in required_images():
        raw = run(["image", "inspect", ref], missing=True)
        if raw is None:
            run(["pull", "--platform", platform, ref], timeout=MAX_SECONDS)
            raw = run(["image", "inspect", ref])
        records = decode(raw)
        if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
            raise Refusal("invalid_docker_image_metadata")
        image = records[0]
        if (not isinstance(image.get("RepoDigests"), list) or ref not in image["RepoDigests"]
                or not isinstance(image.get("Id"), str) or re.fullmatch(r"sha256:[0-9a-f]{64}", image["Id"]) is None
                or image.get("Os") != "linux" or image.get("Architecture") != server["Arch"]):
            raise Refusal("fixture_image_identity_or_platform_mismatch")
        print(f"Prepared {ref} ({platform}; {image['Id']})")


if __name__ == "__main__":
    try:
        prepare()
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
