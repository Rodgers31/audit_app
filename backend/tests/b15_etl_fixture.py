"""Ephemeral owned PostgreSQL for the B15 ETL native and evidence controls."""
from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

URL = "postgresql+psycopg2://b15_etl:b15-inert-local@127.0.0.1:55396/b15_etl"
IMAGE = "sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3"


@contextmanager
def postgres():
    if any(name.startswith("PG") for name in os.environ):
        raise RuntimeError("Ambient PostgreSQL redirects refused")
    name = "b15-etl-" + uuid4().hex
    def docker(*args):
        return subprocess.check_output(["docker", *args], text=True, timeout=45).strip()
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", 55396))
    docker("image", "inspect", IMAGE)  # cached image only; no pull
    created = False
    engine = None
    try:
        docker("run", "--pull=never", "-d", "--name", name,
               "-p", "127.0.0.1:55396:5432", "--tmpfs", "/var/lib/postgresql/data",
               "-e", "POSTGRES_USER=b15_etl", "-e", "POSTGRES_PASSWORD=b15-inert-local",
               "-e", "POSTGRES_DB=b15_etl", IMAGE)
        created = True
        engine = create_engine(URL, connect_args={"connect_timeout": 2})
        deadline = time.monotonic() + 25
        while True:
            try:
                with engine.connect() as db:
                    actual = tuple(db.execute(text("SELECT current_database(),current_user,version()")).one())
                    if actual[:2] != ("b15_etl", "b15_etl"):
                        raise RuntimeError("Wrong owned fixture identity")
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.1)
        backend = Path(__file__).resolve().parents[1]
        env = {"PATH": os.environ["PATH"], "PYTHONPATH": str(backend),
               "PYTHON_DOTENV_DISABLED": "1", "DATABASE_URL": URL}
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "a545b14a0001"],
                       cwd=backend, env=env, check=True, timeout=90)
        with engine.connect() as db:
            if db.scalar(text("SELECT version_num FROM alembic_version")) != "a545b14a0001":
                raise RuntimeError("Frozen accepted ETL schema required")
        yield sessionmaker(bind=engine), engine
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            docker("rm", "-f", name)
            if docker("ps", "-aq", "--filter", "name=^/" + name + "$"):
                raise RuntimeError("Owned fixture cleanup incomplete")
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(("127.0.0.1", 55396))
