"""Replay the held migration chain on an empty, owned PostgreSQL database."""
import hashlib
import os
import sys
from pathlib import Path
import platform
from uuid import uuid4

import sqlalchemy
from sqlalchemy import text
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "backend/tests/batch9_bootstrap_fixture"))
from owned_database import owned_engine, owned_url

root = Path(__file__).resolve().parents[4]
original_url = os.environ["DATABASE_URL"]
owned_url(original_url)
name = owned_url(original_url).database + "-m-" + uuid4().hex[:12]
admin = owned_engine(original_url)
database_url = owned_url(original_url).set(database=name).render_as_string(hide_password=False)
print("generator_sha256", hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
print("runtime", platform.python_version(), sqlalchemy.__version__, "database", name)
with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
    db.execute(text(f'CREATE DATABASE "{name}"'))
try:
    os.environ["DATABASE_URL"] = database_url
    config = Config(str(root / "backend/alembic.ini"))
    config.set_main_option("script_location", str(root / "backend/alembic"))
    import sqlalchemy.engine.create as engine_create
    original_create = engine_create.create_engine
    engine_create.create_engine = lambda url, **kwargs: owned_engine(url, **kwargs)
    try:
        command.upgrade(config, "head")
    finally:
        engine_create.create_engine = original_create
    engine = owned_engine(database_url)
    with engine.connect() as db:
        expected_heads = set(ScriptDirectory.from_config(config).get_heads())
        revisions = set(db.scalars(text("SELECT version_num FROM alembic_version")))
        assert expected_heads and revisions == expected_heads, (revisions, expected_heads)
        assert db.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid='seeding_domain_claims'::regclass")) is True
        assert db.scalar(text("SELECT count(*) FROM seeding_domain_claims")) == 0
        print("migration_heads", sorted(revisions), "claims_RLS", True, "claim_rows", 0)
    engine.dispose()
finally:
    os.environ["DATABASE_URL"] = original_url
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
        # Never terminate sessions: only this owned, fully closed database.
        db.execute(text(f'DROP DATABASE "{name}"'))
    admin.dispose()
    print("owned_database_removed", name)
