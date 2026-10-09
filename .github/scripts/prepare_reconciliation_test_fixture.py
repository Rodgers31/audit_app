#!/usr/bin/env python3
"""Owned loopback CI template for the mandatory reconciliation test cohort.

Use the already prepared immutable image. No pull, shared-service reuse,
production connection, background retry, or prerequisite skip is available.
Connection input is exported only after a fresh whole migration and readback.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "public.ecr.aws/docker/library/postgres@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675"
REVISION = "e583b9c9a001"
PREFIX = "batch9-review-592-"
MAX_SECONDS = 240
LIBPQ = frozenset({"PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGPASSFILE",
                   "PGSERVICE", "PGSERVICEFILE", "PGSSLMODE", "PGSSLROOTCERT", "PGSSLCERT", "PGSSLKEY",
                   "PGOPTIONS", "PGTARGETSESSIONATTRS"})
IDENTITY = re.compile(r"[0-9a-f]{64}")


class Refused(RuntimeError):
    """Fixed diagnostics must not publish child output or ambient secrets."""


def guard_environment():
    if any(os.environ.get(name) for name in LIBPQ):
        raise Refused("ambient_libpq_configuration")


def validate_port(port):
    if type(port) is not int or not 1024 <= port <= 65535:
        raise Refused("invalid_owned_loopback_port")


def private_path(path, *, exists=False):
    if path.is_symlink():
        raise Refused("state_or_export_symlink")
    if path.exists():
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise Refused("state_or_export_not_owned")
    elif exists:
        raise Refused("state_missing")


def state_write(path, value):
    private_path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
    os.chmod(path, 0o600)
    if json.loads(path.read_text()) != value:
        raise Refused("state_readback_mismatch")


def state_read(path):
    private_path(path, exists=True)
    if path.stat().st_mode & 0o077:
        raise Refused("state_permissions")
    try:
        value = json.loads(path.read_text())
        if type(value) is not dict or set(value) != {"version", "nonce", "container_name", "network_name", "database",
                "port", "image", "container_id", "network_id", "ready", "cleaned"}:
            raise Refused("state_shape")
        if (type(value["version"]) is not int or value["version"] != 1 or
                type(value["nonce"]) is not str or not re.fullmatch(r"[0-9a-f]{32}", value["nonce"]) or
                value["container_name"] != PREFIX + value["nonce"] + "-db" or
                value["network_name"] != PREFIX + value["nonce"] + "-net" or
                value["database"] != PREFIX + value["nonce"] or value["image"] != IMAGE or
                type(value["ready"]) is not bool or type(value["cleaned"]) is not bool):
            raise Refused("state_identity")
        validate_port(value["port"])
        for field in ("container_id", "network_id"):
            if value[field] is not None and (type(value[field]) is not str or not IDENTITY.fullmatch(value[field])):
                raise Refused("state_resource_identity")
        return value
    except (ValueError, TypeError, KeyError):
        raise Refused("state_malformed") from None


def run(command, deadline, *, env=None, cwd=None):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise Refused("fixture_deadline")
    try:
        result = subprocess.run(command, env=env or {"PATH": os.environ.get("PATH", os.defpath)}, cwd=cwd,
                                text=True, capture_output=True, timeout=min(60, remaining), check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Refused("fixture_command_unavailable_or_timeout") from None
    if result.returncode:
        raise Refused("fixture_command_failed")
    return result.stdout.strip()


def inspect(kind, identity, deadline):
    try:
        result = json.loads(run(["docker", kind, "inspect", identity], deadline))
    except (ValueError, TypeError):
        raise Refused("docker_inspection_malformed") from None
    if type(result) is not list or len(result) != 1 or type(result[0]) is not dict:
        raise Refused("docker_inspection_shape")
    return result[0]


def verify_resources(value, deadline):
    expected = {"audit.review": "592", "audit.fixture.nonce": value["nonce"]}
    if value["container_id"]:
        container = inspect("container", value["container_id"], deadline)
        if (container.get("Id") != value["container_id"] or container.get("Name") != "/" + value["container_name"] or
                container.get("Config", {}).get("Labels") != expected or
                container.get("Config", {}).get("Image") != IMAGE or
                container.get("HostConfig", {}).get("PortBindings") != {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(value["port"])}]} or
                set(container.get("NetworkSettings", {}).get("Networks", {})) != {value["network_name"]}):
            raise Refused("container_ownership_mismatch")
    if value["network_id"]:
        network = inspect("network", value["network_id"], deadline)
        if (network.get("Id") != value["network_id"] or network.get("Name") != value["network_name"] or
                network.get("Labels") != expected or
                set(network.get("Containers", {})) - {value["container_id"]}):
            raise Refused("network_ownership_mismatch")


def prepare(path, port, github_env, deadline):
    guard_environment()
    validate_port(port)
    if path.exists() or path.is_symlink():
        raise Refused("existing_state_refused")
    private_path(github_env)
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            raise Refused("owned_loopback_port_unavailable") from None
    image = inspect("image", IMAGE, deadline)
    server = json.loads(run(["docker", "version", "--format", "{{json .Server}}"], deadline))
    if (type(server) is not dict or server.get("Os") != "linux" or
            image.get("Os") != "linux" or image.get("Architecture") != server.get("Arch") or
            type(image.get("Id")) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", image["Id"]) or
            type(image.get("RepoDigests")) is not list or IMAGE not in image["RepoDigests"] or
            any(type(d) is not str or not re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", d) for d in image["RepoDigests"])):
        raise Refused("cached_immutable_native_image_unverified")
    nonce = uuid4().hex
    value = {"version": 1, "nonce": nonce, "container_name": PREFIX + nonce + "-db",
             "network_name": PREFIX + nonce + "-net", "database": PREFIX + nonce, "port": port,
             "image": IMAGE, "container_id": None, "network_id": None, "ready": False, "cleaned": False}
    state_write(path, value)
    labels = ["--label", "audit.review=592", "--label", "audit.fixture.nonce=" + nonce]
    value["network_id"] = run(["docker", "network", "create", *labels, value["network_name"]], deadline)
    if not IDENTITY.fullmatch(value["network_id"]):
        raise Refused("created_network_identity_unverified")
    state_write(path, value)
    value["container_id"] = run(["docker", "run", "-d", "--name", value["container_name"], "--network", value["network_name"],
                                 *labels, "-p", f"127.0.0.1:{port}:5432", "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
                                 "-e", "POSTGRES_DB=" + value["database"], IMAGE, "postgres", "-c", "autovacuum=off"], deadline)
    if not IDENTITY.fullmatch(value["container_id"]):
        raise Refused("created_container_identity_unverified")
    state_write(path, value)
    verify_resources(value, deadline)
    for _ in range(60):
        try:
            run(["docker", "exec", value["container_id"], "pg_isready", "-U", "postgres"], deadline)
            break
        except Refused as exc:
            if str(exc) != "fixture_command_failed":
                raise
            time.sleep(0.5)
    else:
        raise Refused("postgres_readiness_unverified")
    # Trust auth is restricted to this isolated, ephemeral fixture; no credential
    # appears in the URL, the receipt, or the GitHub environment export.
    url = f"postgresql+psycopg2://postgres@127.0.0.1:{port}/{value['database']}"
    env = {"PATH": os.environ.get("PATH", os.defpath), "PYTHONDONTWRITEBYTECODE": "1", "PYTHON_DOTENV_DISABLED": "1",
           "PYTHONPATH": str(ROOT / "backend"), "DATABASE_URL": url}
    run([sys.executable, "-m", "alembic", "upgrade", "head"], deadline, env=env, cwd=ROOT / "backend")
    proof = run(["docker", "exec", value["container_id"], "psql", "-U", "postgres", "-d", value["database"], "-Atc",
                 "SELECT json_build_object('database',current_database(),'autovacuum',current_setting('autovacuum'),'revision',(SELECT version_num FROM public.alembic_version),"
                 "'claim',to_regclass('public.seeding_domain_claims') IS NOT NULL,'jobs',to_regclass('public.ingestion_jobs') IS NOT NULL,"
                 "'audit',to_regclass('public.admin_audit_log') IS NOT NULL,'rls',(SELECT relrowsecurity FROM pg_class WHERE oid='public.seeding_domain_claims'::regclass),"
                 "'active_index',(SELECT indisvalid AND indisready AND indisunique FROM pg_index WHERE indexrelid='public.uq_seeding_active_domain'::regclass))"], deadline)
    try:
        expected = {"database": value["database"], "autovacuum": "off", "revision": REVISION, "claim": True, "jobs": True, "audit": True, "rls": True, "active_index": True}
        if json.loads(proof) != expected:
            raise Refused("migrated_template_readback_mismatch")
    except (ValueError, TypeError):
        raise Refused("migrated_template_readback_malformed") from None
    verify_resources(value, deadline)
    private_path(github_env)
    fd = os.open(github_env, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "a") as output:
        output.write("BATCH9_RECONCILIATION_DATABASE_URL=" + url + "\n")
    if ("BATCH9_RECONCILIATION_DATABASE_URL=" + url) not in github_env.read_text().splitlines():
        raise Refused("environment_export_readback_mismatch")
    value["ready"] = True
    state_write(path, value)
    return {"status": "ready", "revision": REVISION, "loopback_port": port,
            "container_id": value["container_id"], "network_id": value["network_id"], "state_file": str(path)}


def cleanup(path, deadline):
    guard_environment()
    value = state_read(path)
    if value["cleaned"]:
        return {"status": "already_cleaned"}
    verify_resources(value, deadline)
    if value["container_id"]:
        run(["docker", "rm", "-f", value["container_id"]], deadline)
    if value["network_id"]:
        run(["docker", "network", "rm", value["network_id"]], deadline)
    value.update(ready=False, cleaned=True)
    state_write(path, value)
    return {"status": "cleaned", "container_id": value["container_id"], "network_id": value["network_id"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "cleanup"))
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--port", type=int, default=55496)
    parser.add_argument("--github-env", type=Path)
    args = parser.parse_args()
    deadline = time.monotonic() + MAX_SECONDS
    try:
        if args.action == "prepare":
            target = args.github_env or (Path(os.environ["GITHUB_ENV"]) if os.environ.get("GITHUB_ENV") else None)
            if target is None:
                raise Refused("explicit_environment_export_required")
            result = prepare(args.state, args.port, target, deadline)
        else:
            result = cleanup(args.state, deadline)
        result.update(generated_by=str(Path(__file__).relative_to(ROOT)),
                      generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      generated_at=datetime.now(timezone.utc).isoformat())
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Refused, ValueError, TypeError, KeyError, OSError) as exc:
        reason = str(exc) if isinstance(exc, Refused) else "fixture_configuration_or_io_failure"
        print(json.dumps({"status": "refused", "reason": reason}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
