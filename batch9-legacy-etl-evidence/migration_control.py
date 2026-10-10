"""Fresh real Alembic upgrade on a second database in our owned container."""
import hashlib
import os
from pathlib import Path
import subprocess

import psycopg2
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

root = Path(__file__).resolve().parents[1]
name = "batch9-legacy-etl-migration-af79"
url = "postgresql+psycopg2://batch9_legacy:batch9-inert-local@127.0.0.1:55491/" + name
assert os.environ["DATABASE_URL"] == url
print("control_sha256=" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
print(subprocess.check_output(["/usr/local/bin/docker", "inspect", "--format", "{{.Name}} {{.Config.Image}} {{.Image}}", "batch9-legacy-etl-af79-db"], text=True).strip())
admin = psycopg2.connect(host="127.0.0.1", port=55491, user="batch9_legacy", password="batch9-inert-local", dbname="postgres")
admin.autocommit = True
with admin.cursor() as cursor:
    cursor.execute("SELECT count(*) FROM pg_database WHERE datname=%s", (name,))
    assert cursor.fetchone()[0] == 0
    cursor.execute('CREATE DATABASE "batch9-legacy-etl-migration-af79"')
try:
    os.chdir(root / "backend")
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            print("server=" + connection.scalar(text("SELECT version()")))
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
            print("revision=" + revision)
            assert revision == "e572b8c9a001"
            index = connection.scalar(text("SELECT indexdef FROM pg_indexes WHERE indexname='uq_seeding_active_domain'"))
            print("index=" + index)
            assert "UNIQUE" in index and "released_at IS NULL" in index
            assert connection.scalar(text("SELECT count(*) FROM seeding_domain_claims")) == 0
    finally:
        engine.dispose()
finally:
    with admin.cursor() as cursor:
        cursor.execute('DROP DATABASE "batch9-legacy-etl-migration-af79"')
    admin.close()
    print("owned_migration_database_removed=true")
