"""Independent #582 normal native-first startup control, owned PostgreSQL only."""
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
import sqlalchemy
from models import Base

ROOT = Path(__file__).resolve().parents[4]
URL = os.environ["BATCH9_BOOTSTRAP_POSTGRES_URL"]
assert "@127.0.0.1:55492/batch9-bootstrap-" in URL
schema = "spec_" + uuid4().hex
admin = create_engine(URL)
owned_database = "batch9-bootstrap-spec-" + uuid4().hex
with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
    db.execute(text(f'CREATE DATABASE "{owned_database}"'))
owned_url = make_url(URL).set(database=owned_database)
owned_admin = create_engine(owned_url)
processes = []
report = {
    "python": platform.python_version(), "sqlalchemy": sqlalchemy.__version__,
    "command": sys.argv, "schema": schema, "owned_database": owned_database,
    "bootstrap_sha256": hashlib.sha256((ROOT / "backend/bootstrap.py").read_bytes()).hexdigest(),
    "control_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
}
with owned_admin.begin() as db:
    db.execute(text(f'CREATE SCHEMA "{schema}"'))
engine = create_engine(owned_url.update_query_dict({"options": f"-csearch_path={schema}"}))
Base.metadata.create_all(engine)

def scalar(sql):
    with engine.connect() as db:
        return db.scalar(text(sql))

with engine.begin() as db:
    db.execute(text("CREATE TABLE batch9_control(mode text NOT NULL)"))
    db.execute(text("INSERT INTO batch9_control VALUES ('before')"))
    db.execute(text("CREATE TABLE batch9_markers(pid integer,stage text,job_id integer,live_fetch boolean,dry_run boolean)"))
    db.execute(text("CREATE TABLE batch9_effects(pid integer)"))

try:
    with tempfile.TemporaryDirectory(prefix="batch9-bootstrap-spec-") as tmp:
        env = {
            "PATH": os.environ["PATH"], "DATABASE_URL": engine.url.render_as_string(hide_password=False),
            "BATCH9_BOOTSTRAP_INERT": "true", "PYTHON_DOTENV_DISABLED": "1", "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": f"{ROOT / 'backend/tests/batch9_bootstrap_fixture'}:{ROOT / 'backend'}",
            "AUTO_SEEDER_ENABLED": "false", "AUTO_WARMUP_ENABLED": "false", "ENABLE_ETL_SCHEDULER": "false",
            "SEED_STORAGE_PATH": tmp, "JWT_SECRET_KEY": "independent-spec-inert-secret",
        }
        native_command = [sys.executable, "-m", "seeding.cli", "seed", "--domain", "national_budget", "--no-dry-run"]
        with (Path(tmp) / "native.txt").open("w") as stream:
            native = subprocess.Popen(native_command, cwd=ROOT / "backend", env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(native)
        deadline = time.monotonic() + 15
        while scalar("SELECT count(*) FROM batch9_markers WHERE stage='entered'") != 1:
            if time.monotonic() > deadline:
                raise AssertionError("Native did not enter; " + (Path(tmp) / "native.txt").read_text())
            time.sleep(0.05)
        startup_command = [sys.executable, "-c", "import asyncio, main; asyncio.run(main._startup_sequence()); print('BOOTSTRAP_READY', main._app_ready.is_set())"]
        startup = subprocess.run(startup_command, cwd=ROOT / "backend", env=env, text=True, capture_output=True, timeout=15)
        report.update({
            "native_command": native_command, "startup_command": startup_command,
            "startup_exit_code": startup.returncode, "startup_stdout": startup.stdout, "startup_stderr": startup.stderr,
            "county_count_before_native_release": scalar("SELECT count(*) FROM entities WHERE type='COUNTY'"),
            "bootstrap_jobs_before_native_release": scalar("SELECT count(*) FROM ingestion_jobs WHERE domain='bootstrap_reference_data'"),
            "entered_handlers_before_native_release": scalar("SELECT count(*) FROM batch9_markers WHERE stage='entered'"),
        })
        with engine.begin() as db:
            db.execute(text("UPDATE batch9_control SET mode='normal'"))
        report["native_exit_code"] = native.wait(timeout=15)
        report["native_output"] = (Path(tmp) / "native.txt").read_text()
finally:
    for proc in processes:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
    engine.dispose()
    with owned_admin.begin() as db:
        db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    owned_admin.dispose()
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
        db.execute(text(f'DROP DATABASE "{owned_database}"'))
    admin.dispose()
print(json.dumps(report, indent=2))
assert report["startup_exit_code"] == 0
assert "BOOTSTRAP_READY True" in report["startup_stdout"]
assert report["county_count_before_native_release"] == 47, "Startup reported ready without the required county reference data"
assert report["entered_handlers_before_native_release"] == 1
