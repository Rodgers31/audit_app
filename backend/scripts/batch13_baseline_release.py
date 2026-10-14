"""Source-bound baseline release preparation. No production operation or authority.

GitHub and authenticated or refused provider readbacks are observations, never maintenance
certificates. This packet enumerates obligations; a coordinator must separately
review and authorize each concrete production step.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
ENTRY = "backend/scripts/batch13_baseline_release.py"
BASE = "c8970e3953717fc0f0ca3a54e22f7e3e509eec0f"
BASE_TREE = "1f5a2ccdec2627b320ccedcb9f1fd9db975f3dc8"
TARGET = "e602b11a0001"
RENDER = "srv-d6hr3t5m5p6s73bomqu0"
SUPABASE = "xznjxwrkbkahwtnbstbj"
MAX_BYTES = 262144

# Loading a sibling inspector must not mutate the measured checkout, including
# when the caller leaves normal interpreter bytecode caching enabled.
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("baseline_rollout", Path(__file__).with_name("batch12_rollout.py"))
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
Refused = baseline.Refused

# Source obligations are not a deployed census. Unknown deployed channels must
# be added to the independently reviewed operational census before fencing.
CONTROLS = (
    ("github_seed", "native_scheduled", (".github/workflows/seed.yml", "backend/seeding/cli.py"),
     "Repository/workflow admission, schedules, dispatch/rerun, queued and running jobs, runner descendants; secret target and receipt transports."),
    ("github_deploy", "migrations_manual_scripts", (".github/workflows/docker-build-deploy.yml", ".github/workflows/ci.yml", ".github/workflows/verification.yml", ".github/workflows/r2-acceptance.yml"),
     "Keep all writers fenced; head upgrades, SSH compose deploy, images, revalidation and R2 publication need separate disposition."),
    ("render_lifecycle", "application_sessions", ("backend/main.py", "backend/Dockerfile", "backend/Dockerfile.prod", "docker-compose.prod.yml"),
     "Exact service/replica/deploy/image/start command; manual/API/hook/rollback/resume, Gunicorn request recycling, Docker/provider health replacement, provider maintenance and credential holders."),
    ("render_independent_jobs", "migrations_manual_scripts", ("backend/alembic/env.py",),
     "Inventory every Render workspace service, cron and one-off job by ID. Suspending/redeploying the base service does not terminate a one-off job."),
    ("startup_bootstrap", "bootstrap", ("backend/main.py", "backend/bootstrap.py"),
     "Stop process/thread and fence every restart; AutoSeeder=false does not fence reference initialization or national_budget."),
    ("auto_seeder", "application_auto_seeder", ("backend/services/auto_seeder.py", "backend/main.py"),
     "Account for initial/hourly/weekly tasks and reference commits; read actual runtime flags and stopped task identities."),
    ("legacy_etl", "legacy_etl", ("backend/main.py", "docker-compose.prod.yml", "etl/database_loader.py"),
     "Fence manual/light/deep discovery, APScheduler and legacy compose workers/cron; light mode still has external effects."),
    ("native_manual", "native_manual", ("backend/seeding/cli.py", "backend/bootstrap.py"),
     "Inventory every host, CLI, force/dry-run/manual script and credential; dry run still writes claims and observations."),
    ("dedicated_worker", "dedicated_supervisor", ("backend/admin_etl_dispatch_worker.py", "backend/admin_etl_dispatch.py"),
     "Exact supervisor PID/birth/generation and launch/restart channel stopped; default-off flag alone is insufficient."),
    ("adapter_orphans", "dedicated_adapter_orphans", ("backend/admin_etl_dispatch_adapter.py",),
     "Census exact child/orphan host/PID/birth/group and native descendants; do not infer exit from lease age."),
    ("parliament_digest", "parliament", ("backend/main.py",),
     "Stop ingest/reconcile/digest schedules, children and email/provider transports; fence independent callers."),
    ("request_sessions", "application_sessions", ("backend/routers/etl_admin.py", "backend/admin_etl_dispatch.py", "backend/database.py"),
     "Fence API sessions and credentials. Dispatch/command GETs can commit receipt retirement; never use them as read-only preflight."),
    ("supabase_admission", "migrations_manual_scripts", ("backend/seeding/reconciliation.py", "backend/seeding/reconcile_operator.py"),
     "Direct/session/transaction poolers; PostgREST/Auth/Storage/Realtime/Edge/cron/replication, dashboard SQL, prepared work, background maintenance and all role/secret holders."),
    ("vercel_and_external", "application_sessions", ("frontend/lib/api/base.ts", "frontend/lib/api/axios.ts"),
     "Exact Vercel project/deployment and server/browser credentials, API destinations, hooks, email/storage/receipt publishers; no claim of a direct DB writer without readback."),
)

BLOCKERS = (
    "Render metadata/runtime observations do not certify every service/job/restart/credential fence.",
    "Supabase metadata/catalog observations do not certify every provider/session/admission fence.",
    "GitHub secret metadata cannot prove any secret value's database or external-effect target.",
    "Every writer/restart/reconnect/background channel requires an exact independently trusted fence.",
    "Accepted reconciliation requires actual rolsuper=true, datallowconn=false, zero other target sessions and zero prepared transactions; provider equivalent is not reviewed.",
    "Complete installed source/image/runtime qualification, direct-connection feasibility and production restore/external effects remain unverified.",
    "Retained effects/claims/dispatch/RUNNING rows require exact investigation and signed same-backend reconciliation; never age-based reclaim.",
    "Authenticated deployed UI/API/worker/operator acceptance and coordinator authorization remain pending.",
)


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise Refused("json_shape") from None


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def exact(value, keys, reason):
    require(type(value) is dict and set(value) == set(keys.split()), reason)


def label(value):
    return type(value) is str and 0 < len(value) <= 512 and value == value.strip() and not any(ord(c) < 32 for c in value)


def integer(value, minimum=0):
    return type(value) is int and minimum <= value <= 2**63 - 1


def fresh(value, now):
    require(type(value) is str, "readback_time")
    try:
        observed = datetime.fromisoformat(value)
        age = (now - observed).total_seconds()
    except (ValueError, TypeError):
        raise Refused("readback_time") from None
    require(observed.utcoffset() is not None and observed.utcoffset().total_seconds() == 0 and -30 <= age <= 300, "readback_stale")


def validate_inputs(value, now):
    exact(value, "version observed_at accepted_base accepted_tree github providers", "readback_shape")
    require(type(value["version"]) is int and value["version"] == 1, "readback_version")
    require(value["accepted_base"] == BASE and value["accepted_tree"] == BASE_TREE, "accepted_source")
    fresh(value["observed_at"], now)
    github = value["github"]
    exact(github, "enabled workflow_total workflows runs secret_names", "github_shape")
    require(type(github["enabled"]) is bool and integer(github["workflow_total"], 1), "github_state")
    workflows = github["workflows"]
    require(type(workflows) is list and len(workflows) == github["workflow_total"] <= 1000, "workflow_census")
    ids, paths = set(), set()
    for row in workflows:
        exact(row, "id path state", "workflow_shape")
        require(integer(row["id"], 1) and label(row["path"]) and row["state"] in ("active", "disabled_manually", "disabled_inactivity", "disabled_fork", "deleted"), "workflow_state")
        require(row["id"] not in ids and row["path"] not in paths, "workflow_duplicate")
        ids.add(row["id"]); paths.add(row["path"])
    required = {".github/workflows/" + name for name in ("ci.yml", "seed.yml", "docker-build-deploy.yml", "verification.yml", "r2-acceptance.yml")}
    require(required <= paths, "static_workflow_missing")
    runs = github["runs"]
    require(type(runs) is list and len(runs) <= 1000, "run_census")
    seen = set()
    for row in runs:
        exact(row, "id workflow_id head_sha status run_attempt", "run_shape")
        require(integer(row["id"], 1) and integer(row["workflow_id"], 1) and integer(row["run_attempt"], 1) and
                type(row["head_sha"]) is str and re.fullmatch(r"[0-9a-f]{40}", row["head_sha"]) and
                row["status"] in ("queued", "in_progress", "waiting", "requested", "pending"), "run_state")
        require(row["id"] not in seen and row["workflow_id"] in ids, "run_identity")
        seen.add(row["id"])
    secrets = github["secret_names"]
    require(type(secrets) is list and 0 < len(secrets) <= 1000 and all(label(x) for x in secrets) and len(set(secrets)) == len(secrets), "secret_metadata")
    exact(value["providers"], "render supabase", "provider_census")
    for name, identity in (("render", RENDER), ("supabase", SUPABASE)):
        row = value["providers"][name]
        exact(row, "resource_id observed_at state", "provider_shape")
        require(row["resource_id"] == identity and row["state"] in ("authentication_required", "not_supplied", "authenticated_read_only"), "provider_identity")
        fresh(row["observed_at"], now)
    canonical(value)


def source_hashes(root):
    paths = {ENTRY, "backend/scripts/batch12_rollout.py"}
    paths.update(path for _, _, refs, _ in CONTROLS for path in refs)
    result = {}
    for name in sorted(paths):
        path = root / name
        require(path.resolve() == path and path.is_file() and not path.is_symlink(), "source_unavailable")
        result[name] = sha(path.read_bytes())
    return result


def build_packet(value, root=ROOT, now=None):
    now = now or datetime.now(timezone.utc)
    validate_inputs(value, now)
    chain = baseline.migration_chain(root)
    github = value["github"]
    # OFF is only a GitHub snapshot. It does not fence providers, restart paths,
    # existing jobs, database admission or credentials held outside GitHub.
    github_off = github["enabled"] is False and all(row["state"] == "disabled_manually" for row in github["workflows"] if row["path"].startswith(".github/workflows/"))
    return {"version": 1, "kind": "baseline_release_preparation_only",
        "accepted_base": BASE, "accepted_tree": BASE_TREE, "target": TARGET,
        "input_sha256": sha(canonical(value).encode()), "observed_at": value["observed_at"],
        "generated_by": ENTRY, "generator_sha256": sha(Path(__file__).read_bytes()),
        "source_sha256": source_hashes(root), "migration_chain": chain,
        "github_off_snapshot": github_off, "nonterminal_runs": github["runs"],
        "secret_names_only": github["secret_names"], "providers": value["providers"],
        "writer_controls": [{"id": name, "category": category, "source_paths": list(refs),
            "required_readback_and_fence": obligation, "deployed_disposition": "unverified"} for name, category, refs, obligation in CONTROLS],
        "blockers": list(BLOCKERS) + ([] if github_off else ["GitHub repository/static workflows are not all observed OFF."]),
        "migration_from_revision": None,
        "migration_command_after_fresh_database_plan": ["<reviewed-python>", "-m", "alembic", "upgrade", TARGET],
        "audit_release": {"target": "a611b12a0001", "included": False, "contract": "separate frozen reviewed contract required"},
        "status": "blocked_production_prerequisites", "production_ready": False,
        "production_execution_authorized": False}


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def read_json(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path, "input_path")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= MAX_BYTES, "input_file")
        raw = stream.read(MAX_BYTES + 1)
    require(0 < len(raw) <= MAX_BYTES, "input_size")
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(Refused("nonfinite_json")))
    except RecursionError:
        raise Refused("json_depth") from None


def verify_packet(packet, inputs, root=ROOT, now=None):
    expected = build_packet(inputs, root, now)
    require(canonical(packet) == canonical(expected), "packet_source_or_input_changed")


def publish(path, packet, inputs, directory_fd):
    # Direct callers must receive the same destination protection as the CLI.
    # Bind their fd to an independently traversed fresh external parent before
    # any create; a valid packet never authorizes writing into measured source.
    with baseline.output_directory(path) as checked_fd:
        expected = os.fstat(checked_fd)
        supplied = os.fstat(directory_fd)
        require((supplied.st_dev, supplied.st_ino) == (expected.st_dev, expected.st_ino), "packet_directory_changed")
        _publish_anchored(path, packet, inputs, directory_fd)


def _publish_anchored(path, packet, inputs, directory_fd):
    verify_packet(packet, inputs)
    path = Path(path)
    raw = json.dumps(packet, sort_keys=True, indent=2, allow_nan=False) + "\n"
    fd = os.open(path.name, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
    with os.fdopen(fd, "w+") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno()); stream.seek(0)
        require(stream.read() == raw, "packet_readback")
        require(os.fstat(stream.fileno()).st_ino == os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False).st_ino, "packet_replaced")
        require(path.parent.resolve() == path.parent and os.stat(path.parent).st_ino == os.fstat(directory_fd).st_ino, "packet_parent_changed")
    os.fsync(directory_fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--inputs", type=Path, required=True)
    prepare.add_argument("--out", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--inputs", type=Path, required=True)
    verify.add_argument("--packet", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "prepare":
            # Validate destination before reading or doing source work.
            with baseline.output_directory(args.out) as directory_fd:
                inputs = read_json(args.inputs)
                publish(args.out, build_packet(inputs), inputs, directory_fd)
        else:
            verify_packet(read_json(args.packet), read_json(args.inputs))
        print(json.dumps({"status": "verified_preparation_only", "production_ready": False, "production_execution_authorized": False, "target": TARGET}))
        return 0
    except (Refused, OSError, ValueError, TypeError, KeyError, UnicodeError):
        print(json.dumps({"status": "refused", "production_ready": False, "production_execution_authorized": False, "reason": "release_packet_unverified"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
