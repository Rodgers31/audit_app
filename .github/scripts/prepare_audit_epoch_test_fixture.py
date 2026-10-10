#!/usr/bin/env python3
"""Fresh, owned epoch-one PostgreSQL for the unchanged issue611 prototype tests.

The reconciliation helper owns a *second* container/network. Its export stays
private; the workflow receives only the prototype opt-in and explicit port.
Only the verified stopped container's anonymous volume is reset, without force.
This test prerequisite does not activate the production audit capability.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "audit_epoch_reconciliation_fixture", Path(__file__).with_name("prepare_reconciliation_test_fixture.py"))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
Refused = base.Refused
PGDATA = "/var/lib/postgresql/data"
RESET = 'test ! -e "$PGDATA/postmaster.pid"; pg_resetwal -e 1 -x 1000 "$PGDATA"'
KEYS = frozenset({"ISSUE611_OWNED_POSTGRES", "ISSUE611_PG_PORT"})


def path_guard(path, *, exists=False, fresh=False):
    if not path.is_absolute() or ".." in path.parts or path.is_relative_to(ROOT):
        raise Refused("explicit_external_owned_path_required")
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise Refused("state_or_export_symlink")
    if fresh and path.exists():
        raise Refused("existing_state_or_private_export_refused")
    base.private_path(path, exists=exists)
    if not path.parent.is_dir() or path.parent.stat().st_uid != os.getuid():
        raise Refused("state_or_export_parent_not_owned")


def paths(path):
    return path.with_name(path.name + ".base.json"), path.with_name(path.name + ".private-env")


def validate_port(port):
    if type(port) is not int or port not in (55534, 55545):
        raise Refused("explicit_issue611_owned_port_required")


def state_read(path):
    path_guard(path, exists=True)
    if path.stat().st_mode & 0o077:
        raise Refused("state_permissions")
    try:
        value = json.loads(path.read_text())
    except (ValueError, TypeError):
        raise Refused("epoch_state_malformed") from None
    if (type(value) is not dict or set(value) != {"version", "reset_id", "reset_removed", "ready", "cleaned"}
            or type(value["version"]) is not int or value["version"] != 1
            or any(type(value[k]) is not bool for k in ("reset_removed", "ready", "cleaned"))
            or (value["reset_id"] is not None and (type(value["reset_id"]) is not str
                or not base.IDENTITY.fullmatch(value["reset_id"])))
            or (value["reset_removed"] and value["reset_id"] is None)
            or (value["ready"] and (not value["reset_removed"] or value["cleaned"]))):
        raise Refused("epoch_state_identity")
    return value


def state_write(path, value):
    path_guard(path)
    base.state_write(path, value)
    if state_read(path) != value:
        raise Refused("epoch_state_readback_mismatch")


def absence(kind, identity, deadline):
    """Only exact literal not-found is absence; daemon/permission failures refuse."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise Refused("fixture_deadline")
    try:
        result = subprocess.run(["docker", kind, "inspect", identity],
            env={"PATH": os.environ.get("PATH", os.defpath)}, text=True,
            capture_output=True, timeout=min(20, remaining), check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Refused("resource_absence_unverified") from None
    error = re.escape(identity)
    pattern = (rf"(?:Error response from daemon: |Error: )?No such container: {error}"
               if kind == "container" else rf"(?:Error response from daemon: )?network {error} not found")
    if not (result.returncode == 1 and result.stdout.strip() == "[]"
            and re.fullmatch(pattern, result.stderr.strip())):
        raise Refused("resource_absence_unverified")


def container(value, deadline, *, running):
    base.verify_resources(value, deadline)
    result = base.inspect("container", value["container_id"], deadline)
    state = result.get("State", {})
    if (type(state.get("Running")) is not bool or state["Running"] is not running
            or state.get("Error") != "" or state.get("Status") != ("running" if running else "exited")
            or (not running and (type(state.get("ExitCode")) is not int or state["ExitCode"] != 0))):
        raise Refused("owned_postgres_running_state_unverified")
    mounts = result.get("Mounts")
    if (type(mounts) is not list or len(mounts) != 1 or type(mounts[0]) is not dict
            or mounts[0].get("Type") != "volume" or mounts[0].get("Destination") != PGDATA
            or mounts[0].get("Driver") != "local" or mounts[0].get("RW") is not True
            or type(mounts[0].get("Name")) is not str or not base.IDENTITY.fullmatch(mounts[0]["Name"])
            or result.get("HostConfig", {}).get("Binds")
            or result.get("HostConfig", {}).get("VolumesFrom")
            or result.get("HostConfig", {}).get("Mounts")
            or result.get("Config", {}).get("Env", []).count("PGDATA=" + PGDATA) != 1):
        raise Refused("owned_anonymous_postgres_volume_unverified")
    return mounts[0]


def reset_name(value):
    return base.PREFIX + value["nonce"] + "-epoch"


def verify_reset(value, identity, mount, deadline):
    result = base.inspect("container", identity, deadline)
    host = result.get("HostConfig", {})
    config = result.get("Config", {})
    actual = result.get("Mounts")
    if (result.get("Id") != identity or result.get("Name") != "/" + reset_name(value)
            or config.get("Image") != base.IMAGE or config.get("User") != "postgres"
            or config.get("Entrypoint") != ["/bin/sh"] or config.get("Cmd") != ["-ceu", RESET]
            or config.get("Labels") != {"audit.review": "592", "audit.fixture.nonce": value["nonce"],
                                       "audit.fixture.purpose": "epoch-reset"}
            or host.get("NetworkMode") != "none" or host.get("PortBindings") or host.get("Binds")
            or host.get("Privileged") is not False or host.get("ReadonlyRootfs") is not True
            or host.get("VolumesFrom") != [value["container_id"] + ":rw"]
            or config.get("Env", []).count("PGDATA=" + PGDATA) != 1
            or type(actual) is not list or len(actual) != 1 or type(actual[0]) is not dict
            or any(actual[0].get(k) != mount.get(k) for k in ("Type", "Name", "Source", "Destination", "Driver", "RW"))):
        raise Refused("epoch_utility_ownership_mismatch")
    return result


def psql(value, query, deadline, *, issue=False):
    return base.run(["docker", "exec", value["container_id"], "psql", "-v", "ON_ERROR_STOP=1",
                     "-U", "inert" if issue else "postgres", "-d", "issue611" if issue else "postgres",
                     "-Atc", query], deadline)


def proof(value, deadline):
    try:
        actual = json.loads(psql(value, "SELECT json_build_object('database',current_database(),"
            "'user',current_user,'owner',(SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()),"
            "'root',pg_current_xact_id()::text,'autovacuum',current_setting('autovacuum'),"
            "'tables',(SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p')),"
            "'roles',(SELECT count(*) FROM pg_roles WHERE rolname IN ('issue611_reader','issue611_writer','issue611_untrusted')))" , deadline, issue=True))
    except (ValueError, TypeError):
        raise Refused("epoch_database_readback_malformed") from None
    expected = {"database": "issue611", "user": "inert", "owner": "inert", "autovacuum": "off", "tables": 0, "roles": 0}
    if (type(actual) is not dict or set(actual) != set(expected) | {"root"}
            or any(actual[k] != v or type(actual[k]) is not type(v) for k, v in expected.items())
            or type(actual["root"]) is not str or not re.fullmatch(r"[0-9]{1,20}", actual["root"])
            or not 2 ** 32 < int(actual["root"]) < 2 ** 33):
        raise Refused("epoch_database_readback_mismatch")
    return actual


def environment_bytes(target):
    path_guard(target)
    contents = target.read_bytes() if target.exists() else b""
    if contents and not contents.endswith(b"\n"):
        raise Refused("environment_export_incomplete_line")
    if any(line.split(b"=", 1)[0].decode("utf-8", errors="replace") in KEYS for line in contents.splitlines()):
        raise Refused("existing_epoch_environment_export_refused")
    return contents


def export(target, port, original):
    path_guard(target)
    if environment_bytes(target) != original:
        raise Refused("environment_export_changed")
    addition = f"ISSUE611_OWNED_POSTGRES=1\nISSUE611_PG_PORT={port}\n".encode()
    fd = os.open(target, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(addition)
    if target.read_bytes() != original + addition:
        raise Refused("environment_export_readback_mismatch")


def prepare(path, port, target, deadline):
    base.guard_environment()
    validate_port(port)
    if any(os.environ.get(key) for key in KEYS):
        raise Refused("ambient_epoch_configuration")
    base_path, private_env = paths(path)
    for item in (path, base_path, private_env):
        path_guard(item, fresh=True)
    if target in (path, base_path, private_env):
        raise Refused("aliased_fixture_state_or_export")
    original = environment_bytes(target)
    state = {"version": 1, "reset_id": None, "reset_removed": False, "ready": False, "cleaned": False}
    state_write(path, state)
    base.prepare(base_path, port, private_env, deadline)
    value = base.state_read(base_path)
    if not value["ready"] or value["cleaned"] or value["port"] != port:
        raise Refused("secondary_fixture_readiness_unverified")
    container(value, deadline, running=True)
    if psql(value, "SELECT (NOT EXISTS(SELECT FROM pg_roles WHERE rolname='inert') AND NOT EXISTS(SELECT FROM pg_database WHERE datname='issue611'))::text", deadline) != "true":
        raise Refused("preexisting_prototype_database_or_owner")
    psql(value, "CREATE ROLE inert LOGIN SUPERUSER PASSWORD 'inert'", deadline)
    psql(value, "CREATE DATABASE issue611 OWNER inert", deadline)
    base.run(["docker", "stop", "--time", "30", value["container_id"]], deadline)
    mount = container(value, deadline, running=False)
    absence("container", reset_name(value), deadline)
    identity = base.run(["docker", "create", "--name", reset_name(value), "--network", "none", "--read-only",
        "--user", "postgres", "--volumes-from", value["container_id"] + ":rw",
        "--label", "audit.review=592", "--label", "audit.fixture.nonce=" + value["nonce"],
        "--label", "audit.fixture.purpose=epoch-reset", "--entrypoint", "/bin/sh", base.IMAGE, "-ceu", RESET], deadline)
    if not base.IDENTITY.fullmatch(identity):
        raise Refused("created_epoch_utility_identity_unverified")
    state["reset_id"] = identity
    state_write(path, state)
    utility = verify_reset(value, identity, mount, deadline)
    if utility.get("State", {}).get("Running") is not False or utility.get("State", {}).get("Status") != "created":
        raise Refused("epoch_utility_not_freshly_created")
    container(value, deadline, running=False)
    base.run(["docker", "start", "-a", identity], deadline)
    utility = verify_reset(value, identity, mount, deadline)
    status = utility.get("State", {})
    if (status.get("Running") is not False or status.get("Status") != "exited"
            or type(status.get("ExitCode")) is not int or status["ExitCode"] != 0 or status.get("Error") != ""):
        raise Refused("offline_epoch_reset_unverified")
    container(value, deadline, running=False)
    base.run(["docker", "rm", identity], deadline)
    absence("container", identity, deadline)
    state["reset_removed"] = True
    state_write(path, state)
    base.run(["docker", "start", value["container_id"]], deadline)
    for _ in range(60):
        try:
            base.run(["docker", "exec", value["container_id"], "pg_isready", "-U", "inert", "-d", "issue611"], deadline)
            break
        except Refused as exc:
            if str(exc) != "fixture_command_failed":
                raise
            time.sleep(0.5)
    else:
        raise Refused("epoch_postgres_readiness_unverified")
    container(value, deadline, running=True)
    actual = proof(value, deadline)
    export(target, port, original)
    state["ready"] = True
    state_write(path, state)
    return {"status": "ready", "loopback_port": port, "database": "issue611", "root_xid": actual["root"],
            "container_id": value["container_id"], "network_id": value["network_id"],
            "reset_container_id": identity, "reset_container_absent": True,
            "original_environment_sha256": hashlib.sha256(original).hexdigest()}


def cleanup(path, deadline):
    base.guard_environment()
    state = state_read(path)
    base_path, private_env = paths(path)
    for item in (base_path, private_env):
        path_guard(item)
    if not base_path.exists():
        if state["reset_id"] is not None or state["ready"]:
            raise Refused("missing_secondary_fixture_state")
        state["cleaned"] = True
        state_write(path, state)
        return {"status": "cleaned_before_creation"}
    value = base.state_read(base_path)
    validate_port(value["port"])
    if not value["cleaned"]:
        base.verify_resources(value, deadline)
        if state["reset_id"] is not None and not state["reset_removed"]:
            # Ownership is checked before either resource can be deleted.
            result = base.inspect("container", value["container_id"], deadline)
            running = result.get("State", {}).get("Running")
            if type(running) is not bool:
                raise Refused("owned_postgres_running_state_unverified")
            mount = container(value, deadline, running=running)
            verify_reset(value, state["reset_id"], mount, deadline)
            base.run(["docker", "rm", "-f", state["reset_id"]], deadline)
            absence("container", state["reset_id"], deadline)
            state["reset_removed"] = True
            state_write(path, state)
        else:
            absence("container", state["reset_id"] or reset_name(value), deadline)
        for kind, field, name in (("container", "container_id", "container_name"), ("network", "network_id", "network_name")):
            if value[field] is None:
                absence(kind, value[name], deadline)
        base.cleanup(base_path, deadline)
    for kind, field, name in (("container", "container_id", "container_name"), ("network", "network_id", "network_name")):
        absence(kind, value[field] or value[name], deadline)
    absence("container", state["reset_id"] or reset_name(value), deadline)
    state.update(ready=False, cleaned=True)
    state_write(path, state)
    return {"status": "cleaned", "container_id": value["container_id"], "network_id": value["network_id"],
            "reset_container_id": state["reset_id"], "physical_resource_absence_verified": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "cleanup"))
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--port", type=int, choices=(55534, 55545), default=55534)
    parser.add_argument("--github-env", type=Path)
    args = parser.parse_args()
    deadline = time.monotonic() + base.MAX_SECONDS
    try:
        if args.action == "prepare":
            target = args.github_env or (Path(os.environ["GITHUB_ENV"]) if os.environ.get("GITHUB_ENV") else None)
            if target is None:
                raise Refused("explicit_environment_export_required")
            result = prepare(args.state, args.port, target, deadline)
        else:
            result = cleanup(args.state, deadline)
        result.update(generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Refused, ValueError, TypeError, KeyError, OSError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc) if isinstance(exc, Refused)
                          else "epoch_fixture_configuration_or_io_failure"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
