"""Exclusive loopback fixture; default execution never skips PostgreSQL controls."""
from contextlib import contextmanager
import json
import hashlib
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4

URL = "postgresql+psycopg2://batch10_mappings:batch10-inert-local@127.0.0.1:55522/batch10_mappings"
IMAGE = "public.ecr.aws/docker/library/postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3"


@contextmanager
def postgres(output):
    override = os.getenv("BATCH10_MAPPINGS_DATABASE_URL")
    if override and override != URL:
        raise ValueError("Refusing unowned database target")
    if any(k.startswith("PG") for k in os.environ):
        raise ValueError("Refusing ambient PostgreSQL redirects")
    name = "batch10-mappings-" + str(uuid4())
    volume = name + "-data"
    owned = not override
    volume_created = container_created = False
    identity = None
    def docker(*args):
        return subprocess.check_output(["docker", *args], text=True, timeout=45).strip()
    if owned:
        with socket.socket() as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 55522))
        docker("image", "inspect", IMAGE)
        docker("volume", "create", volume)
        volume_created = True
    try:
        if owned:
            docker("run", "-d", "--name", name, "-p", "127.0.0.1:55522:5432", "-v", volume + ":/var/lib/postgresql/data",
                "-e", "POSTGRES_USER=batch10_mappings", "-e", "POSTGRES_PASSWORD=batch10-inert-local", "-e", "POSTGRES_DB=batch10_mappings", IMAGE)
            container_created = True
        from sqlalchemy import create_engine, text
        engine = create_engine(URL)
        deadline = time.monotonic() + 30
        while True:
            try:
                with engine.connect() as c:
                    identity = c.execute(text("SELECT current_database(),current_user,version()")).one()
                    if identity[:2] != ("batch10_mappings", "batch10_mappings"):
                        raise ValueError("Wrong fixture identity")
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.1)
        engine.dispose()
        if owned:
            backend = Path(__file__).resolve().parents[2]
            env = {"PATH": os.environ["PATH"], "PYTHONPATH": str(backend), "PYTHONDONTWRITEBYTECODE": "1", "PYTHON_DOTENV_DISABLED": "1", "DATABASE_URL": URL}
            subprocess.run([sys.executable, "-c", "from alembic.config import Config; from alembic import command; command.upgrade(Config('alembic.ini'),'head')"], cwd=backend, env=env, check=True, timeout=90)
        yield URL
    finally:
        if owned:
            if container_created:
                docker("rm", "-f", name)
            if volume_created:
                docker("volume", "rm", volume)
            if docker("ps", "-aq", "--filter", "name=^/" + name + "$") or docker("volume", "ls", "-q", "--filter", "name=^" + volume + "$"):
                raise RuntimeError("Owned fixture cleanup incomplete")
            with socket.socket() as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", 55522))
        record = {"generated_by": str(Path(__file__).resolve()), "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "image": IMAGE,
            "container": name if owned else "author-override", "volume": volume if owned else None, "identity": list(identity) if identity else None, "owned": owned, "cleanup": owned}
        destination = Path(output, "resources.json")
        with destination.open('x') as f:
            json.dump(record, f, indent=2)
        if json.loads(destination.read_text()) != record:
            raise RuntimeError("Resource receipt readback mismatch")
