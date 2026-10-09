"""Out-of-lane shared-native behavior when the essential index is missing."""
import argparse
import hashlib
from pathlib import Path
import tempfile

from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from models import Base
from seeding import cli, registries
import seeding.domains.audits.scope  # register actual domain before replacing registry
from seeding.config import SeedingSettings
from seeding.exclusion import enter_domain
from seeding.types import DomainRunResult


@compiles(JSONB, "sqlite")
def jsonb_sqlite(*args, **kwargs):
    return "TEXT"


print("control_sha256=" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
with tempfile.TemporaryDirectory(prefix="batch9-native-schema-") as directory:
    engine = create_engine("sqlite:///" + directory + "/owned.sqlite")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    owner = enter_domain(factory, "audits", False)
    owner.close()
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE inert_effects(n integer)"))
        conn.execute(text("DROP INDEX uq_seeding_active_domain"))
    def inert_handler(session, settings, context):
        session.execute(text("INSERT INTO inert_effects VALUES(1)"))
        return DomainRunResult(domain="audits", dry_run=False, items_created=1)
    cli.load_builtin_domains = lambda: None
    cli.SessionLocal = factory
    registries.REGISTRY._handlers = {"audits": inert_handler}
    result = cli.run_seed_command(argparse.Namespace(domain=["audits"], all=False,
        since=None, dry_run=False, audits_source_manifest=None,
        audits_observe_listing=False), SeedingSettings(log_path=None, total_timeout_seconds=0))
    with engine.connect() as conn:
        effects = conn.scalar(text("SELECT count(*) FROM inert_effects"))
        retained = conn.scalar(text("SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NULL"))
    engine.dispose()
    print(f"native_exit={result}; effects={effects}; retained={retained}")
    assert result == 0 and effects == 1 and retained == 1, "Expected concrete out-of-lane defect reproduction"
