"""Review-owned in-memory reproduction; real CLI, inert registry, no sockets."""
import argparse
import json
import socket
from uuid import uuid4

socket.socket.connect = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("External socket forbidden"))
from sqlalchemy import create_engine, text, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from models import Base, SeedingDomainClaim
from seeding import cli
from seeding.config import SeedingSettings
from seeding.types import DomainRunResult
from seeding.exclusion import DomainExecution, dispatch_scope, reserve

@compiles(JSONB, "sqlite")
def compile_jsonb(*args, **kwargs):
    return "TEXT"

engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)
factory = sessionmaker(bind=engine)
with engine.begin() as conn:
    conn.execute(text("CREATE TABLE inert_effects (value integer)"))
retained = uuid4()
with factory.begin() as db:
    assert reserve(db, "audits", retained)

def inert_handler(session, settings, context):
    session.execute(text("INSERT INTO inert_effects VALUES (1)"))
    return DomainRunResult(domain="audits", dry_run=False, items_created=1)

class Registry:
    def domains(self):
        return ["audits"]
    def get(self, domain):
        return inert_handler

cli.SessionLocal = factory
cli.REGISTRY = Registry()
cli.load_builtin_domains = lambda: None
args = argparse.Namespace(domain=["audits"], all=False, since=None, dry_run=False)
settings = SeedingSettings(log_path=None, domain_timeout_seconds=30, total_timeout_seconds=0)

def snapshot(label, code):
    with factory() as db:
        result = {"label": label, "code": code,
            "effects": db.scalar(text("SELECT count(*) FROM inert_effects")),
            "active_claims": db.scalar(text("SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NULL"))}
        print(json.dumps(result))
        return result

positive = snapshot("plain CLI denies retained ownership", cli.run_seed_command(args, settings))
assert positive["code"] == 1 and positive["effects"] == 0 and positive["active_claims"] == 1
forged = DomainExecution(factory, "audits", uuid4())
forged.open()
with dispatch_scope(forged):
    result = snapshot("arbitrary scope commits before failed acknowledgement", cli.run_seed_command(args, settings))
assert result["code"] == 1 and result["effects"] == 1 and result["active_claims"] == 1
reused = DomainExecution(factory, "audits", retained)
reused.open()
with dispatch_scope(reused):
    result = snapshot("arbitrary scope reuses and clears retained native claim", cli.run_seed_command(args, settings))
assert result["code"] == 0 and result["effects"] == 2 and result["active_claims"] == 0
