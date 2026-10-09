"""Owned reproduction of the unchanged non-budget startup deferral gap."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from sqlalchemy import text
from models import Base

root = Path(__file__).resolve().parents[4]
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "backend/tests/batch9_bootstrap_fixture"))
from owned_database import owned_engine, owned_url

url = os.environ["DATABASE_URL"]
owned_url(url)
name = owned_url(url).database + "-o-" + uuid4().hex[:12]
admin = owned_engine(url)
with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
    db.execute(text(f'CREATE DATABASE "{name}"'))
database_url = owned_url(url).set(database=name).render_as_string(hide_password=False)
engine = owned_engine(database_url)
try:
    Base.metadata.create_all(engine)
    with engine.begin() as db:
        db.execute(text("INSERT INTO ingestion_jobs(domain,status,dry_run,started_at,items_processed,items_created,items_updated) "
                        "VALUES ('audits','RUNNING',false,clock_timestamp(),0,0,0)"))
    env = {"PATH": os.environ["PATH"], "DATABASE_URL": database_url,
           "BATCH9_BOOTSTRAP_OWNED_PORT": str(owned_url(url).port),
           "PYTHONPATH": str(root / "backend"), "PYTHON_DOTENV_DISABLED": "1",
           "PYTHONDONTWRITEBYTECODE": "1", "JWT_SECRET_KEY": "batch9-other-ready-inert",
           "AUTO_SEEDER_ENABLED": "false", "AUTO_WARMUP_ENABLED": "false"}
    code = """import os,socket
connect = socket.socket.connect
def loopback(sock, address):
    assert isinstance(address,tuple) and address[:2]==('127.0.0.1',int(os.environ['BATCH9_BOOTSTRAP_OWNED_PORT']))
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
