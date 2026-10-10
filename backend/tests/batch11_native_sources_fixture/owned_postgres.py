"""Exclusive PostgreSQL fixture with named volume and cleanup readback."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4

IMAGE = "public.ecr.aws/docker/library/postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3"
DATABASE = "batch9-reconciliation-batch11-602-template"


def command_environment(url=None):
    env = {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
           "PYTHON_DOTENV_DISABLED": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    if url:
        env["DATABASE_URL"] = url
    return env


@contextmanager
def postgres(output):
    from sqlalchemy import create_engine, text
    port = int(os.environ.get("BATCH11_602_PG_PORT", "55531"))
    if not 1024 <= port <= 65535 or port in (55530, 55532, 55534, 18030, 18031, 18032, 18033, 18034, 13032, 13033, 13034):
        raise ValueError("Port is reserved by another service/lane")
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", port))
    url = f"postgresql+psycopg2://batch11_602:inert-owned-602@127.0.0.1:{port}/{DATABASE}"
    name = "batch11-issue602-" + uuid4().hex
    volume = name + "-data"
    owned_volume = owned_container = False
    identity = None
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "resources-start.json").open("x") as f:
        json.dump({"generated_by": "backend/tests/batch11_native_sources_fixture/owned_postgres.py",
            "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "container": name, "volume": volume, "port": port, "image": IMAGE}, f, indent=2)
    def docker(*args):
        return subprocess.check_output(["docker", *args], text=True, env=command_environment(), timeout=45).strip()
    try:
        docker("image", "inspect", IMAGE)
        docker("volume", "create", "--label", "audit.batch11.issue=602", volume)
        owned_volume = True
        docker("run", "-d", "--name", name, "--label", "audit.batch11.issue=602", "-p", f"127.0.0.1:{port}:5432",
               "-v", volume + ":/var/lib/postgresql/data", "-e", "POSTGRES_USER=batch11_602",
               "-e", "POSTGRES_PASSWORD=inert-owned-602", "-e", "POSTGRES_DB=" + DATABASE, IMAGE)
        owned_container = True
        engine = create_engine(url)
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    with engine.connect() as c:
                        identity = tuple(c.execute(text("SELECT current_database(),current_user,version()")).one())
                    break
                except Exception:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(.1)
            if identity[:2] != (DATABASE, "batch11_602"):
                raise ValueError("Owned fixture database identity mismatch")
        finally:
            engine.dispose()
        backend = Path(__file__).resolve().parents[2]
        result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend,
            env=command_environment(url), capture_output=True, text=True, timeout=90)
        (output / "migration.log").write_text(result.stdout + result.stderr)
        if result.returncode != 0:
            raise RuntimeError("Owned fixture migration failed: " + result.stderr)
        yield url
    finally:
        if owned_container:
            docker("rm", "-f", name)
        if owned_volume:
            docker("volume", "rm", volume)
        if docker("ps", "-aq", "--filter", "name=^/" + name + "$") or docker("volume", "ls", "-q", "--filter", "name=^" + volume + "$"):
            raise RuntimeError("Owned fixture resource cleanup failed")
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", port))
        record = {"generated_by": "backend/tests/batch11_native_sources_fixture/owned_postgres.py",
            "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "generated_at": datetime.now(timezone.utc).isoformat(), "image": IMAGE, "container": name,
            "volume": volume, "port": port, "identity": identity, "cleanup_verified": True}
        with (output / "resources.json").open("x") as f:
            json.dump(record, f, indent=2)
        check = json.loads((output / "resources.json").read_text())
        if check["generator_sha256"] != record["generator_sha256"] or check["cleanup_verified"] is not True:
            raise RuntimeError("Resource receipt readback failed")
