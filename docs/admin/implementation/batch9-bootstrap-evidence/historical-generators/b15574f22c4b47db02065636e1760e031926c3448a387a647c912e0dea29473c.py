"""Replay the held migration chain on an empty, owned PostgreSQL database."""
import hashlib
import os
from pathlib import Path
import platform
from uuid import uuid4

import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config

root = Path(__file__).resolve().parents[4]
original_url = os.environ["DATABASE_URL"]
assert "@127.0.0.1:55492/batch9-bootstrap-" in original_url
name = "batch9-bootstrap-migration-" + uuid4().hex
admin = create_engine(original_url)
owned_url = make_url(original_url).set(database=name).render_as_string(hide_password=False)
print("generator_sha256", hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
print("runtime", platform.python_version(), sqlalchemy.__version__, "database", name)
with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
    db.execute(text(f'CREATE DATABASE "{name}"'))
try:
    os.environ["DATABASE_URL"] = owned_url
    config = Config(str(root / "backend/alembic.ini"))
    config.set_main_option("script_location", str(root / "backend/alembic"))
    command.upgrade(config, "head")
    engine = create_engine(owned_url)
    with engine.connect() as db:
        revision = db.scalar(text("SELECT version_num FROM alembic_version"))
        assert revision == "e572b8c9a001", revision
        assert db.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid='seeding_domain_claims'::regclass")) is True
        assert db.scalar(text("SELECT count(*) FROM seeding_domain_claims")) == 0
        print("migration_head", revision, "claims_RLS", True, "claim_rows", 0)
    engine.dispose()
finally:
    os.environ["DATABASE_URL"] = original_url
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
        # Never terminate sessions: only this owned, fully closed database.
        db.execute(text(f'DROP DATABASE "{name}"'))
    admin.dispose()
    print("owned_database_removed", name)
