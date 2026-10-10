"""Run a #602 test suite with the hosted CI's PostgreSQL prerequisites, owned locally.

Replaces the draft run_cohort.py, whose full-core mode pointed DATABASE_URL at an
inert port (the PostgreSQL citation test then errored on connection refusal),
built the reconciliation template with its own autovacuum-enabled container
instead of the CI preparer, and asked for a JUnit path it never produced.

Prerequisites, mirroring .github/workflows/ci.yml test-backend:
  * an owned, empty "service" PostgreSQL (CI's pinned service image) for
    DATABASE_URL, and an owned Redis (CI's pinned image) for REDIS_URL;
  * the real .github/scripts/prepare_reconciliation_test_fixture.py prepare /
    cleanup for BATCH9_RECONCILIATION_DATABASE_URL (autovacuum off, single
    repository head readback);
  * owned fixtures inside tests start their own labelled containers.
Every container/network/volume created here is named with a fresh nonce, removed
afterwards, and its absence read back. Ports exclude sibling lane reservations.
The suite itself is executed and measured by record_v4.py.
"""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import time
from uuid import uuid4

SERVICE_IMAGE = "public.ecr.aws/docker/library/postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3"
REDIS_IMAGE = "public.ecr.aws/docker/library/redis@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499"
RESERVED = {55530, 55532, 55534, 18030, 18032, 18033, 18034, 13032, 13033, 13034}
PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def free(port):
    if port in RESERVED:
        raise SystemExit(f"Port {port} is reserved by a sibling lane")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def docker(*args, timeout=60):
    return subprocess.check_output(["docker", *args], text=True, timeout=timeout, env={"PATH": PATH}).strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--python", type=Path, required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--suite", choices=("full", "complete", "tests"), required=True)
    p.add_argument("--service-port", type=int, default=55531)
    p.add_argument("--fixture-port", type=int, default=55536)
    p.add_argument("--native-port", type=int, default=55535)
    p.add_argument("--redis-port", type=int, default=55539)
    p.add_argument("--api-port", type=int, default=18031)
    p.add_argument("--timeout", type=int, default=3600)
    p.add_argument("--ci-parity", action="store_true", help="pass --ci-parity to record_v3")
    p.add_argument("tests", nargs="*")
    a = p.parse_args()
    repo, out = a.repo.resolve(strict=True), a.out.absolute()
    if out.exists() or repo in out.parents:
        raise SystemExit("Fresh external output directory required")
    for port in (a.service_port, a.fixture_port, a.native_port, a.redis_port, a.api_port):
        free(port)
    out.mkdir()
    nonce = uuid4().hex[:12]
    service, redis = f"batch11-issue602-service-{nonce}", f"batch11-issue602-redis-{nonce}"
    log = {"nonce": nonce, "service": service, "redis": redis, "steps": []}
    created, prepared = [], False
    state, exported = out / "fixture-state.json", out / "fixture-github-env"
    rc = 1
    try:
        docker("run", "-d", "--name", service, "--label", "audit.batch11.issue602.suite=" + nonce,
               "-p", f"127.0.0.1:{a.service_port}:5432", "-e", "POSTGRES_PASSWORD=inert-owned-602",
               "-e", "POSTGRES_DB=audit_app_test", SERVICE_IMAGE)
        created.append(service)
        docker("run", "-d", "--name", redis, "--label", "audit.batch11.issue602.suite=" + nonce,
               "-p", f"127.0.0.1:{a.redis_port}:6379", REDIS_IMAGE)
        created.append(redis)
        deadline = time.monotonic() + 60
        while subprocess.run(["docker", "exec", service, "pg_isready", "-U", "postgres", "-d", "audit_app_test"],
                             env={"PATH": PATH}, capture_output=True, timeout=20).returncode:
            if time.monotonic() > deadline:
                raise SystemExit("Owned service PostgreSQL not ready")
            time.sleep(.5)
        prepare = subprocess.run([str(a.python), str(repo / ".github/scripts/prepare_reconciliation_test_fixture.py"),
                                  "prepare", "--state", str(state), "--port", str(a.fixture_port), "--github-env", str(exported)],
                                 cwd=repo, env={"PATH": PATH, "PYTHON_DOTENV_DISABLED": "1", "PYTHONDONTWRITEBYTECODE": "1"},
                                 capture_output=True, text=True, timeout=300)
        (out / "fixture-prepare.log").write_text(prepare.stdout + prepare.stderr)
        log["steps"].append({"prepare_exit": prepare.returncode})
        if prepare.returncode:
            raise SystemExit("Reconciliation fixture preparation refused; see fixture-prepare.log")
        prepared = True
        fixture_url = [line.split("=", 1)[1] for line in exported.read_text().splitlines()
                       if line.startswith("BATCH9_RECONCILIATION_DATABASE_URL=")]
        if len(fixture_url) != 1:
            raise SystemExit("Fixture export readback failed")
        env = ["DATABASE_URL=postgresql://postgres:inert-owned-602@127.0.0.1:%d/audit_app_test" % a.service_port,
               "REDIS_URL=redis://127.0.0.1:%d" % a.redis_port, "TESTING=true",
               "BATCH9_RECONCILIATION_DATABASE_URL=" + fixture_url[0],
               "BATCH11_602_PG_PORT=%d" % a.native_port, "BATCH11_602_API_PORT=%d" % a.api_port]
        def record(run, mode, command, label, extra_env=()):
            argv = [str(a.python), "-I", str(Path(__file__).resolve().parent / "record_v4.py"), "--repo", str(repo),
                    "--out", str(out / run), "--label", label, "--timeout", str(a.timeout), "--mode", mode]
            if a.ci_parity:
                argv.append("--ci-parity")
            for item in (*env, *extra_env):
                argv += ["--env", item]
            return subprocess.run([*argv, "--", *command], cwd=repo, timeout=a.timeout + 120, env={"PATH": PATH}).returncode
        if a.suite == "full":
            rc = record("run", "launcher", [str(a.python), str(repo / ".github/scripts/run_backend_tests.py")], a.label)
        elif a.suite == "complete":
            runner = str(Path(__file__).resolve().parent / "run_launcher_cohorts_complete.py")
            rc = 0
            for cohort in ("backend", "legacy"):
                rc |= record("run-" + cohort, "pytest",
                             [str(a.python), runner, "--cohort", cohort, "--output-dir", str(out / ("launcher-" + cohort))],
                             a.label + " [" + cohort + " cohort]", ("PYTHONPATH=%s" % (repo / "backend"),))
        else:
            rc = record("run", "pytest", [str(a.python), "-m", "pytest", *a.tests, "-q", "-o", "addopts="], a.label,
                        ("PYTHONPATH=%s:%s" % (repo / "backend", repo / "backend/tests"),))
    finally:
        if prepared or state.exists():
            cleanup = subprocess.run([str(a.python), str(repo / ".github/scripts/prepare_reconciliation_test_fixture.py"),
                                      "cleanup", "--state", str(state)], cwd=repo,
                                     env={"PATH": PATH, "PYTHON_DOTENV_DISABLED": "1"}, capture_output=True, text=True, timeout=120)
            (out / "fixture-cleanup.log").write_text(cleanup.stdout + cleanup.stderr)
            log["steps"].append({"fixture_cleanup_exit": cleanup.returncode})
        for name in created:
            docker("rm", "-f", "--volumes", name)
        leftovers = docker("ps", "-aq", "--filter", "label=audit.batch11.issue602.suite=" + nonce)
        fixture_left = ""
        if state.exists():
            nonce_592 = json.loads(state.read_text())["nonce"]
            fixture_left = docker("ps", "-aq", "--filter", "label=audit.fixture.nonce=" + nonce_592)
        for port in (a.service_port, a.fixture_port, a.native_port, a.redis_port, a.api_port):
            free(port)
        log.update(cleanup_leftover_suite_containers=leftovers, cleanup_leftover_fixture_containers=fixture_left,
                   ports_free_after=True, suite_exit=rc)
        (out / "suite.json").write_text(json.dumps(log, indent=2))
        if leftovers or fixture_left:
            raise SystemExit("Owned resource cleanup readback failed")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
