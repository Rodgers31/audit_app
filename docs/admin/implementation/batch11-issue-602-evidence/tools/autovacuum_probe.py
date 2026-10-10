"""A/B probe: does autovacuum alone reproduce "Other database sessions remain"?

Same image, same migrated template, same test selection; only the server's
autovacuum setting differs (on with a 1 s naptime to amplify, vs off as the CI
preparer configures). Owned containers are nonce-named and removed with readback.
"""
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4

IMAGE = "public.ecr.aws/docker/library/postgres@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675"
PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
repo, out, python, port = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], int(sys.argv[4])
selection = sys.argv[5:]
out.mkdir()
summary = {}
for arm, flags in (("autovacuum_on_naptime_1s", ["-c", "autovacuum=on", "-c", "autovacuum_naptime=1"]),
                   ("autovacuum_off", ["-c", "autovacuum=off"])):
    deadline = time.monotonic() + 60
    while True:  # docker-proxy releases a published port shortly after rm
        try:
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(("127.0.0.1", port))
            break
        except OSError:
            if time.monotonic() > deadline:
                raise
            time.sleep(1)
    name = "batch11-issue602-avprobe-" + uuid4().hex[:10]
    database = "batch9-reconciliation-602probe"
    subprocess.check_call(["docker", "run", "-d", "--name", name, "--label", "audit.batch11.issue=602",
        "-p", f"127.0.0.1:{port}:5432", "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "-e", "POSTGRES_DB=" + database,
        IMAGE, "postgres", *flags], env={"PATH": PATH}, stdout=subprocess.DEVNULL)
    try:
        for _ in range(120):
            if subprocess.run(["docker", "exec", name, "pg_isready", "-U", "postgres"], env={"PATH": PATH},
                              capture_output=True).returncode == 0:
                break
            time.sleep(.5)
        time.sleep(2)
        url = f"postgresql+psycopg2://postgres@127.0.0.1:{port}/{database}"
        env = {"PATH": PATH, "PYTHON_DOTENV_DISABLED": "1", "PYTHONDONTWRITEBYTECODE": "1", "DATABASE_URL": url}
        subprocess.check_call([python, "-m", "alembic", "upgrade", "head"], cwd=repo / "backend", env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        setting = subprocess.check_output(["docker", "exec", name, "psql", "-U", "postgres", "-Atc",
            "SELECT current_setting('autovacuum')||','||current_setting('autovacuum_naptime')"], env={"PATH": PATH}, text=True).strip()
        log = out / (arm + ".log")
        test_env = {**env, "DATABASE_URL": "postgresql+psycopg2://inert:inert@127.0.0.1:9/inert",
                    "BATCH9_RECONCILIATION_DATABASE_URL": url, "SUPABASE_URL": "https://owned.invalid",
                    "SUPABASE_KEY": "inert", "SUPABASE_JWT_SECRET": "inert-only",
                    "PYTHONPATH": f"{repo / 'backend'}:{repo / 'backend/tests'}"}
        with log.open("x") as handle:
            code = subprocess.run([python, "-m", "pytest", *selection, "-q", "-p", "no:cacheprovider", "-o", "addopts=",
                                   "--junitxml=" + str(out / (arm + ".xml"))], cwd=repo / "backend", env=test_env,
                                  stdout=handle, stderr=subprocess.STDOUT, timeout=1800).returncode
        text = log.read_text()
        summary[arm] = {"server_setting": setting, "exit": code,
                        "other_sessions_refusals": text.count("Other database sessions or background writers remain"),
                        "summary_line": [l for l in text.splitlines() if " passed" in l or " failed" in l][-1:]}
    finally:
        subprocess.call(["docker", "rm", "-f", "--volumes", name], env={"PATH": PATH}, stdout=subprocess.DEVNULL)
        left = subprocess.check_output(["docker", "ps", "-aq", "--filter", "name=^/" + name + "$"], env={"PATH": PATH}, text=True).strip()
        summary.setdefault(arm, {})["cleanup_leftover"] = left
(out / "summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
