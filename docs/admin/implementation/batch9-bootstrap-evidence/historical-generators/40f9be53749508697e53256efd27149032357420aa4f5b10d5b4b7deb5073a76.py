"""Owned reproduction of the unchanged non-budget startup deferral gap."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from models import Base

root = Path(__file__).resolve().parents[4]
url = os.environ["DATABASE_URL"]
assert "@127.0.0.1:55492/batch9-bootstrap-" in url
name = "batch9-bootstrap-other-ready-" + uuid4().hex
admin = create_engine(url)
with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
    db.execute(text(f'CREATE DATABASE "{name}"'))
owned_url = make_url(url).set(database=name).render_as_string(hide_password=False)
engine = create_engine(owned_url)
try:
    Base.metadata.create_all(engine)
    with engine.begin() as db:
        db.execute(text("INSERT INTO ingestion_jobs(domain,status,dry_run,started_at,items_processed,items_created,items_updated) "
                        "VALUES ('audits','RUNNING',false,clock_timestamp(),0,0,0)"))
    env = {"PATH": os.environ["PATH"], "DATABASE_URL": owned_url,
           "PYTHONPATH": str(root / "backend"), "PYTHON_DOTENV_DISABLED": "1",
           "PYTHONDONTWRITEBYTECODE": "1", "JWT_SECRET_KEY": "batch9-other-ready-inert",
           "AUTO_SEEDER_ENABLED": "false", "AUTO_WARMUP_ENABLED": "false"}
    code = """import socket
connect = socket.socket.connect
def loopback(sock, address):
    assert isinstance(address,tuple) and address[:2]==('127.0.0.1',55492)
    return connect(sock,address)
socket.socket.connect=loopback
import asyncio,main
asyncio.run(main._startup_sequence())
print('ACTUAL_READY',main._app_ready.is_set())
"""
    command = [sys.executable, "-c", code]
    result = subprocess.run(command, cwd=root / "backend", env=env, capture_output=True, text=True, timeout=15)
    with engine.connect() as db:
        county_count = db.scalar(text("SELECT count(*) FROM entities WHERE type='COUNTY'"))
        bootstrap_jobs = db.scalar(text("SELECT count(*) FROM ingestion_jobs WHERE domain='bootstrap_reference_data'"))
    print(json.dumps({"generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      "command": command, "exit_code": result.returncode,
                      "stdout": result.stdout, "stderr": result.stderr,
                      "county_count": county_count, "bootstrap_jobs": bootstrap_jobs}, indent=2))
    assert result.returncode == 0 and "ACTUAL_READY True" in result.stdout
    assert county_count == 0 and bootstrap_jobs == 0
    print("REPRODUCED: non-budget deferral reports ready with no counties")
finally:
    engine.dispose()
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
        db.execute(text(f'DROP DATABASE "{name}"'))
    admin.dispose()
