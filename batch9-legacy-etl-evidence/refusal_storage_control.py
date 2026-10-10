"""Refusal stays visible when its optional observation cannot be persisted."""
import asyncio
import hashlib
from pathlib import Path
import sys
import tempfile

from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

from models import Base
from seeding.exclusion import DomainOwnershipError, enter_domain

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from etl.database_loader import DatabaseLoader


@compiles(JSONB, "sqlite")
def jsonb_sqlite(*args, **kwargs):
    return "TEXT"


print("control_sha256=" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
with tempfile.TemporaryDirectory(prefix="batch9-refusal-storage-") as directory:
    loader = DatabaseLoader("sqlite:///" + directory + "/owned.sqlite")
    Base.metadata.create_all(loader.engine)
    ownership = enter_domain(sessionmaker(bind=loader.engine), "audits", False)
    ownership.close()

    def fail_observation(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO ingestion_jobs"):
            raise OperationalError("inert refusal observation", {}, RuntimeError("inert unavailable storage"))

    event.listen(loader.engine, "before_cursor_execute", fail_observation)
    try:
        error = None
        try:
            asyncio.run(loader.ensure_country_exists())
        except Exception as exc:
            error = type(exc)
        print("refusal_exception=" + (error.__name__ if error else "none"))
    finally:
        event.remove(loader.engine, "before_cursor_execute", fail_observation)
    with loader.engine.connect() as conn:
        effects = conn.scalar(text("SELECT count(*) FROM countries"))
        claims = conn.scalar(text("SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NULL"))
    loader.engine.dispose()
    print(f"effects={effects}; retained={claims}")
    assert error is DomainOwnershipError and effects == 0 and claims == 1
