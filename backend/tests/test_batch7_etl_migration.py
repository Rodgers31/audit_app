"""Real Alembic upgrade/downgrade on the owned PostgreSQL database only."""
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import inspect, text

from test_batch7_etl_postgres import pg, URL, post
from admin_etl_dispatch_worker import register_worker

pytestmark = pytest.mark.skipif(not URL, reason="Owned PostgreSQL required")
BACKEND = Path(__file__).resolve().parents[1]


def migrate(target, operation):
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHON_DOTENV_DISABLED": "1", "PYTHONPATH": str(BACKEND), "DATABASE_URL": URL}
    return subprocess.run([sys.executable, "-m", "alembic", operation, target],
        env=env, cwd=BACKEND, capture_output=True, text=True, timeout=15)


def test_empty_downgrade_upgrade_preserves_observations_and_adds_private_schema(pg):
    _, _, engine = pg
    before = [(col["name"], str(col["type"])) for col in inspect(engine).get_columns("ingestion_jobs")]
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO ingestion_jobs(domain,status,dry_run,started_at,items_processed,items_created,items_updated,errors,metadata) VALUES ('audits','PENDING',false,now(),0,0,0,'[]',jsonb_build_object('manual_trigger',true))"))
    result = migrate("d8f4a619b203", "downgrade")
    assert result.returncode == 0, result.stderr
    assert "etl_dispatch_commands" not in inspect(engine).get_table_names()
    result = migrate("head", "upgrade")
    assert result.returncode == 0, result.stderr
    assert before == [(col["name"], str(col["type"])) for col in inspect(engine).get_columns("ingestion_jobs")]
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT status::text FROM ingestion_jobs")) == "PENDING"
        assert conn.scalar(text("SELECT count(*) FROM etl_dispatch_commands")) == 0
        assert conn.scalar(text("SELECT count(*) FROM pg_class WHERE relname IN ('etl_dispatch_commands','etl_dispatch_worker','etl_dispatch_domains') AND relrowsecurity")) == 3


def test_downgrade_refuses_active_worker_and_accepted_history(pg):
    client, factory, engine = pg
    generation = register_worker(factory)
    result = migrate("d8f4a619b203", "downgrade")
    assert result.returncode != 0 and "Stop dedicated worker" in result.stderr
    assert post(client, generation).status_code == 202
    result = migrate("d8f4a619b203", "downgrade")
    assert result.returncode != 0 and "Dispatch history exists" in result.stderr
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "e572b8c9a001"
        assert conn.scalar(text("SELECT count(*) FROM etl_dispatch_commands")) == 1
