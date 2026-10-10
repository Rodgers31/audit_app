"""Append-only execution record for #602 test runs (supersedes the draft record_v2).

Measures, rather than asserts, what ran:
  * a fresh external output directory (never inside the checkout, never a symlink);
  * the child environment is an explicit allowlist with inert values;
  * every tracked/untracked source byte is hashed before and after the run, and
    any drift is reported, not hidden;
  * ``pytest`` mode always writes its own JUnit file inside the output directory
    and derives a unique nonempty testcase inventory with per-state counts;
  * ``launcher`` mode runs .github/scripts/run_backend_tests.py unchanged with its
    output directory inside ours, then reconciles every collected node id from the
    launcher's own collection receipts against the verbose outcome lines. A run is
    "complete" only when each collected node has exactly one final outcome, so a
    maxfail-truncated launcher run can never be reported as complete;
  * a wall-clock deadline kills the whole process group;
  * owned containers carrying the #602 label must be absent afterwards.

Historical receipts (record.py/record_v2.py) keep their original identity; this
generator never rewrites them. V4 refuses linked or missing source inputs before hashing.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ALLOWED_PREFIXES = ("BATCH11_", "BATCH9_", "BATCH10_", "SEED_", "ADMIN_ETL_")
ALLOWED_KEYS = ("PYTHONPATH", "DATABASE_URL", "REDIS_URL", "TESTING")
OUTCOME = re.compile(r"^(?P<node>\S+::\S.*?) (?P<state>PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)(?: \[\s*\d+%\])?$")
PRECEDENCE = {"error": 5, "failed": 4, "xpass": 3, "passed": 2, "xfail": 1, "skipped": 0}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(repo, *args):
    env = {"PATH": os.environ.get("PATH", os.defpath), "DEVELOPER_DIR": "/Library/Developer/CommandLineTools"}
    return subprocess.check_output(["git", *args], cwd=repo, text=True, env=env, timeout=60)


def source(repo):
    names = git(repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0")
    result = {}
    for name in sorted(set(names) - {""}):
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Source path escape refused")
        path = repo / relative
        if path.resolve() != path or path.is_symlink() or not path.is_file():
            raise ValueError("Linked or missing source input refused: " + name)
        result[name] = sha(path)
    if not result:
        raise ValueError("Empty source inventory refused")
    return result


def owned_containers():
    try:
        out = subprocess.check_output(["docker", "ps", "-aq", "--filter", "label=audit.batch11.issue=602"],
                                      text=True, timeout=30)
        return sorted(out.split())
    except (OSError, subprocess.SubprocessError):
        return None


def junit_cases(path, log=""):
    cases = []
    for case in ET.parse(path).getroot().iter("testcase"):
        if case.find("failure") is not None:
            state = "failed"
        elif case.find("error") is not None:
            state = "error"
        elif case.find("skipped") is not None:
            skipped = case.find("skipped")
            state = "xfail" if skipped.get("type") == "pytest.xfail" else "skipped"
        else:
            state = "passed"
        cases.append({"id": case.get("classname", "") + "::" + case.get("name", ""), "state": state})
    # Non-strict XPASS has no XML marker. The actual -rA output supplies its
    # identity; refuse an ambiguous/missing identity instead of calling it PASS.
    clean = re.sub(r"\x1b\[[0-9;]*m", "", log)
    unexpected = re.findall(r"(?m)^XPASS(?:\[[^\]]*\])?\s+(.+?)(?:\s+-\s+.*)?$", clean)
    totals = re.findall(r"\b(\d+) xpassed\b", clean)
    if totals and int(totals[-1]) != len(unexpected):
        raise ValueError("XPASS summary lacks a complete outcome identity")
    for node in unexpected:
        pieces = node.strip().split("::")
        module = pieces[0].removesuffix(".py").replace("/", ".")
        classname = ".".join([module, *pieces[1:-1]])
        candidates = [case for case in cases if case["id"].split("::", 1)[-1] == pieces[-1]
                      and (case["id"].split("::", 1)[0] == classname
                           or classname.endswith("." + case["id"].split("::", 1)[0])
                           or case["id"].split("::", 1)[0].endswith("." + classname))]
        if len(candidates) != 1 or candidates[0]["state"] != "passed":
            raise ValueError("XPASS identity is ambiguous or differs from JUnit")
        candidates[0]["state"] = "xpass"
    return cases


def group_present(identity):
    try:
        os.killpg(identity, 0)
        return True
    except ProcessLookupError:
        return False


def cleanup_group(identity):
    """Clean only the new session created for this exact command."""
    if group_present(identity):
        try:
            os.killpg(identity, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + 1
        while group_present(identity) and time.monotonic() < deadline:
            time.sleep(.05)
        if group_present(identity):
            try:
                os.killpg(identity, signal.SIGKILL)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 2
    while group_present(identity) and time.monotonic() < deadline:
        time.sleep(.05)
    return not group_present(identity)


def verbose_cases(log):
    final = {}
    for line in log.splitlines():
        match = OUTCOME.match(line.strip())
        if match:
            node, state = match["node"], match["state"].lower()
            if node not in final or PRECEDENCE[state] > PRECEDENCE[final[node]]:
                final[node] = state
    return [{"id": k, "state": v} for k, v in sorted(final.items())]


def counts(cases):
    result = dict.fromkeys(PRECEDENCE, 0)
    for case in cases:
        result[case["state"]] += 1
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--mode", choices=("pytest", "launcher", "command"), required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--env", action="append", default=[])
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--cwd", choices=("backend", "repo"), default="backend")
    p.add_argument("--ci-parity", action="store_true",
                   help="child env mirrors ci.yml test-backend: only PATH, dotenv off and explicit --env values")
    p.add_argument("command", nargs=argparse.REMAINDER)
    a = p.parse_args()
    repo = a.repo.resolve(strict=True)
    out = a.out.absolute()
    if (out.exists() or out.is_symlink() or out.parent.resolve() != out.parent
            or repo == out or repo in out.parents or out in repo.parents):
        raise SystemExit("Fresh external non-symlink output directory required")
    command = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not command:
        raise SystemExit("Command required")
    out.mkdir()
    env = {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
           "PYTHON_DOTENV_DISABLED": "1", "PYTHONDONTWRITEBYTECODE": "1",
           "DATABASE_URL": "postgresql+psycopg2://inert:inert@127.0.0.1:9/inert",
           "SUPABASE_URL": "https://owned.invalid", "SUPABASE_KEY": "inert",
           "SUPABASE_SERVICE_ROLE_KEY": "inert", "SUPABASE_JWT_SECRET": "inert-only",
           "ADMIN_ETL_DISPATCH_ENABLED": "false", "SEED_CRA_INGESTION_ENABLED": "false",
           "SEED_LIVE_PDF_FETCH_ENABLED": "false", "SEED_ENRICH_WITH_WORLDBANK": "false",
           "SEED_STORAGE_PATH": str(out / "storage"), "SEED_CACHE_PATH": str(out / "cache"),
           "SEED_LOG_PATH": str(out / "seed.jsonl")}
    if a.ci_parity:
        # ci.yml sets DATABASE_URL, REDIS_URL, TESTING and PYTHON_DOTENV_DISABLED only;
        # the inert SEED_/ADMIN_/SUPABASE_ defaults above would change tested defaults.
        env = {"PATH": env["PATH"], "PYTHON_DOTENV_DISABLED": "1", "PYTHONDONTWRITEBYTECODE": "1",
               "HOME": str(out / "home")}
        (out / "home").mkdir()
    for item in a.env:
        key, value = item.split("=", 1)
        if not key.startswith(ALLOWED_PREFIXES) and key not in ALLOWED_KEYS:
            raise SystemExit("Unapproved child environment field: " + key)
        env[key] = value
    if a.mode == "pytest":
        command = [*command, "--junitxml=" + str(out / "junit.xml"), "--basetemp=" + str(out / "tmp"),
                   "-p", "no:cacheprovider", "-rA"]
    elif a.mode == "launcher":
        command = [*command, "--output-dir", str(out / "core")]
    before_status = git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    before = source(repo)
    head, tree = git(repo, "rev-parse", "HEAD", "HEAD^{tree}").split()
    containers_before = owned_containers()
    started, t0 = datetime.now(timezone.utc).isoformat(), time.monotonic()
    timed_out = False
    with (out / "output.log").open("xb") as log:
        child = subprocess.Popen(command, cwd=repo / "backend" if a.cwd == "backend" else repo, env=env,
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = child.wait(timeout=a.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            cleanup_group(child.pid)
            code = child.wait(timeout=20)
    leftover_group = group_present(child.pid)
    group_absent = cleanup_group(child.pid)
    duration = round(time.monotonic() - t0, 3)
    after = source(repo)
    after_status = git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    log_text = (out / "output.log").read_text(errors="replace")
    inventory = {}
    inventory_error = None
    if a.mode == "pytest":
        try:
            cases = junit_cases(out / "junit.xml", log_text) if (out / "junit.xml").is_file() else []
        except ValueError as exc:
            cases, inventory_error = [], str(exc)
        ids = [c["id"] for c in cases]
        inventory = {"source": "junit", "unique": len(ids) == len(set(ids)), "nonempty": bool(ids)}
        complete = bool(ids) and len(ids) == len(set(ids)) and not timed_out
    elif a.mode == "launcher":
        cases = verbose_cases(log_text)
        collected = {}
        for cohort in ("backend", "legacy"):
            path = out / "core" / f"collection-{cohort}.json"
            collected[cohort] = json.loads(path.read_text())["nodeids"] if path.is_file() else None
        all_nodes = [n for nodes in collected.values() if nodes for n in nodes]
        seen = {c["id"] for c in cases}
        missing = sorted(set(all_nodes) - seen)
        unexpected = sorted(seen - set(all_nodes))
        inventory = {"source": "launcher collection receipts + verbose outcomes",
                     "collected": {k: (len(v) if v is not None else None) for k, v in collected.items()},
                     "collected_unique": len(all_nodes) == len(set(all_nodes)),
                     "missing_outcome_count": len(missing), "missing_outcome_sample": missing[:50],
                     "unexpected_outcome_count": len(unexpected), "unexpected_outcome_sample": unexpected[:20]}
        complete = (all(v for v in collected.values()) and not missing and not unexpected
                    and len(all_nodes) == len(set(all_nodes)) and not timed_out)
        summary = out / "core" / "summary.json"
        inventory["launcher_summary"] = json.loads(summary.read_text()) if summary.is_file() else None
    else:
        cases, complete = [], not timed_out
    drift = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    outputs = [out / "output.log"]
    if a.mode == "pytest" and (out / "junit.xml").is_file():
        outputs.append(out / "junit.xml")
    elif a.mode == "launcher":
        outputs.extend(p for p in sorted((out / "core").glob("*.json")) if p.is_file())
    record = {
        "generated_by": "docs/admin/implementation/batch11-issue-602-evidence/tools/record_v4.py",
        "generator_sha256": sha(Path(__file__)),
        "label": a.label, "mode": a.mode, "ci_parity_environment": a.ci_parity, "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(), "duration_seconds": duration,
        "deadline_seconds": a.timeout, "timed_out": timed_out, "exit_code": code,
        "leftover_process_group": leftover_group,
        "owned_process_group": child.pid, "process_group_absent_after_cleanup": group_absent,
        "command": [c.replace(str(repo), "<repo>").replace(str(out), "<out>") for c in command],
        "child_environment": {k: (v.replace(str(out), "<out>").replace(str(repo), "<repo>")) for k, v in sorted(env.items())},
        "runtime": {"python": sys.version, "executable_name": Path(command[0]).name, "platform": platform.platform()},
        "head": head, "tree": tree, "status_before": before_status, "status_after": after_status,
        "source_before_sha256": hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
        "source_after_sha256": hashlib.sha256(json.dumps(after, sort_keys=True).encode()).hexdigest(),
        "source_drift": drift, "source_files": before,
        "owned_containers_before": containers_before, "owned_containers_after": owned_containers(),
        "inventory": inventory, "inventory_error": inventory_error, "complete_inventory": complete,
        "counts": counts(cases), "testcases": cases,
        "output_files": {str(path.relative_to(out)): sha(path) for path in outputs},
    }
    with (out / "receipt.json").open("x") as f:
        json.dump(record, f, indent=2)
    readback = json.loads((out / "receipt.json").read_text())
    if readback.get("generator_sha256") != record["generator_sha256"] or readback.get("counts") != record["counts"]:
        raise SystemExit("Receipt provenance readback failed")
    print(json.dumps({"label": a.label, "exit": code, "complete": complete, "counts": record["counts"],
                      "drift": drift, "timed_out": timed_out, "duration": duration,
                      "containers_after": record["owned_containers_after"]}))
    # Green only when the child passed, the inventory is complete and nothing drifted.
    return 0 if (code == 0 and complete and not drift and not timed_out
                 and not leftover_group and group_absent
                 and record["owned_containers_before"] == record["owned_containers_after"] == []
                 and not any(record["counts"][s] for s in ("failed", "error", "xpass"))) else 1


if __name__ == "__main__":
    raise SystemExit(main())
