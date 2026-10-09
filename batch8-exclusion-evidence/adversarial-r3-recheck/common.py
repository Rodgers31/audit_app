"""Shared harness for round-3 RE-CHECK (r3b) adversarial execution. Reviewer-owned; inert only.

r3b adaptations vs adversarial-r3/common.py: schema prefix batch8_adversarial_r3b_, schema log
schemas-r3b.txt, every engine uses NullPool (no pooled connections survive a scenario).

Product code (seeding.exclusion, seeding.cli, admin_etl_dispatch_adapter,
admin_etl_dispatch_worker, models) runs unchanged. The harness replaces only:
cli.SessionLocal (owned schema factory), the registry's handler dict (inert
handlers) and load_builtin_domains (no real domain imports).
"""
import socket

_ALLOWED = ("127.0.0.1", 55485)
_orig_connect = socket.socket.connect


def _loopback_only(sock, address):
    if not (isinstance(address, tuple) and tuple(address[:2]) == _ALLOWED) and not (
            isinstance(address, (str, bytes))):  # AF_UNIX paths are local
        raise RuntimeError("Non-loopback transport blocked by reviewer harness: %r" % (address,))
    return _orig_connect(sock, address)


socket.socket.connect = _loopback_only

import json
import os
import platform
import threading
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import dotenv
dotenv.load_dotenv = lambda *a, **k: False
import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import seeding.domains.audits.scope  # noqa: F401  real package import first (registers real audits)
from seeding import cli, registries
from seeding.config import SeedingSettings
from seeding.types import DomainRunResult
from models import (Base, AdminAuditLog, EtlDispatchCommand, EtlDispatchDomain,
                    EtlDispatchWorker, IngestionJob, IngestionStatus, SeedingDomainClaim)
from seeding.exclusion import clock, reserve

HERE = Path(__file__).resolve().parent
URL = "postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55485/batch7_etl_worker"
assert os.environ.get("DATABASE_URL") == URL
SCHEMA_LOG = HERE / "schemas-r3b.txt"
TABLES = [AdminAuditLog.__table__, IngestionJob.__table__, EtlDispatchCommand.__table__,
          EtlDispatchDomain.__table__, EtlDispatchWorker.__table__, SeedingDomainClaim.__table__]

CALLS = []          # (domain, job_id) for every inert handler entry
BEHAVIOR = {}       # domain -> callable(session, settings, context) overriding the default
DOMAINS = ["audits", "adv_r3_x", "adv_r3_y", "adv_r3_a", "adv_r3_b", "adv_r3_nn",
           "adv_r3_t1", "adv_r3_t2", "adv_r3_ack", "adv_r3_re"]


def make_handler(domain):
    def handler(session, settings, context):
        CALLS.append((domain, context.job_id))
        behavior = BEHAVIOR.get(domain)
        if behavior is not None:
            return behavior(session, settings, context)
        session.execute(text("INSERT INTO inert_effects(label) VALUES (:d)"), {"d": domain})
        return DomainRunResult(domain=domain, dry_run=context.dry_run, items_processed=1, items_created=1)
    return handler


registries.REGISTRY._handlers = {d: make_handler(d) for d in DOMAINS}
registries.load_builtin_domains = lambda: None
cli.load_builtin_domains = lambda: None


class Recorder:
    def __init__(self, label):
        self.label = label
        self.path = HERE / f"results-{label}.jsonl"
        self.path.write_text("")
        self.results = []
        self.lock = threading.Lock()

    def record(self, name, expected, actual, **details):
        result = {"name": name, "expected": expected, "actual": actual,
                  "passed": expected == actual, **details}
        with self.lock:
            self.results.append(result)
            with self.path.open("a") as fh:
                fh.write(json.dumps(result, default=str) + "\n")
        print(("PASS " if result["passed"] else "FAIL ") + json.dumps(result, default=str), flush=True)
        return result["passed"]

    def harness_error(self, section):
        tb = traceback.format_exc()
        self.record(section + "__harness_error", "no harness error", tb.strip().splitlines()[-1],
                    harness_error=True, traceback=tb)

    def summary(self):
        s = {"label": self.label, "checks": len(self.results),
             "passed": sum(r["passed"] for r in self.results),
             "failed": sum(not r["passed"] for r in self.results),
             "harness_errors": sum(bool(r.get("harness_error")) for r in self.results)}
        print(json.dumps(s), flush=True)
        (HERE / f"summary-{self.label}.json").write_text(json.dumps(s, indent=2) + "\n")
        return s


admin = create_engine(URL, poolclass=NullPool)
ENGINES = [admin]


class Scenario:
    """One owned schema, its engine and factory; cli.SessionLocal points here."""

    def __init__(self, label):
        # Release pooled connections of all but the most recent prior scenario
        # (connections still checked out, e.g. an open lock, are unaffected).
        for old in ENGINES[1:-1]:
            old.dispose()
        self.schema = "batch8_adversarial_r3b_" + uuid4().hex
        with SCHEMA_LOG.open("a") as fh:
            fh.write(self.schema + " " + label + "\n")
        with admin.begin() as conn:
            conn.execute(text("CREATE SCHEMA " + self.schema))
        self.engine = create_engine(URL, connect_args={"options": "-csearch_path=" + self.schema},
                                    poolclass=NullPool)
        ENGINES.append(self.engine)
        self.factory = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine, tables=TABLES)
        with self.engine.begin() as conn:
            conn.execute(text("CREATE TABLE inert_effects(id bigserial PRIMARY KEY, label text NOT NULL)"))
        cli.SessionLocal = self.factory

    def activate(self):
        cli.SessionLocal = self.factory

    def scalar(self, sql, **params):
        with self.engine.connect() as conn:
            return conn.scalar(text(sql), params)

    def effects(self, domain=None):
        if domain is None:
            return self.scalar("SELECT count(*) FROM inert_effects")
        return self.scalar("SELECT count(*) FROM inert_effects WHERE label=:d", d=domain)

    def refused(self, domain=None):
        sql = "SELECT count(*) FROM ingestion_jobs WHERE metadata->>'ownership_refused'='true'"
        if domain:
            sql += " AND domain=:d"
            return self.scalar(sql, d=domain)
        return self.scalar(sql)

    def claim(self, identity):
        with self.engine.connect() as conn:
            row = conn.execute(text(
                "SELECT domain, kind, command_id, entered_at IS NOT NULL, entry_id, returned_at IS NOT NULL,"
                " released_at IS NOT NULL, job_id FROM seeding_domain_claims WHERE id=:i"), {"i": identity}).first()
        if row is None:
            return None
        return {"domain": row[0], "kind": row[1], "command_id": row[2], "entered": row[3],
                "entry_id": row[4], "returned": row[5], "released": row[6], "job_id": row[7]}

    def state(self, identity):
        c = self.claim(identity)
        return None if c is None else [c["entered"], c["returned"], c["released"]]

    def command(self, command_id):
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT status, outcome, execution_started, job_id FROM etl_dispatch_commands"
                                    " WHERE id=:i"), {"i": command_id}).first()
        return None if row is None else list(row)

    def native_claim(self, domain, entry=None):
        identity = uuid4()
        with self.factory.begin() as db:
            assert reserve(db, domain, identity, entry=entry)
        return identity

    def job(self, identity, domain="audits", **values):
        now = datetime.now(timezone.utc)
        fields = dict(domain=domain, status=IngestionStatus.COMPLETED, dry_run=False,
                      started_at=now, finished_at=now, items_processed=1, items_created=1,
                      items_updated=0, errors=[], meta={"seeding_claim_id": str(identity)})
        fields.update(values)
        with self.factory.begin() as db:
            job = IngestionJob(**fields)
            db.add(job)
            db.flush()
            return job.id

    def dispatch(self, execution_started=True, dry_run=False, worker=True, generation=None,
                 lease=timedelta(minutes=10), reserve_claim=True):
        generation = generation or uuid4()
        command_id, token = uuid4(), uuid4()
        with self.factory.begin() as db:
            now = clock(db)
            audit = AdminAuditLog(actor_id="inert", action="etl.trigger", payload={})
            db.add(audit)
            db.flush()
            if worker:
                existing = db.get(EtlDispatchWorker, 1)
                if existing is None:
                    db.add(EtlDispatchWorker(id=1, generation=generation, ready=True,
                                             last_seen_at=now, expires_at=now + lease))
            db.add(EtlDispatchCommand(id=command_id, actor_id="inert", idempotency_key=uuid4(),
                source="oag", domain="audits", dry_run=dry_run, generation=generation,
                claim_token=token, execution_started=execution_started, status="running", version=2,
                created_at=now, updated_at=now, started_at=now, audit_id=audit.id))
            db.flush()
            row = db.get(EtlDispatchDomain, "audits")
            if row is None:
                db.add(EtlDispatchDomain(domain="audits", command_id=command_id, claim_token=token))
            else:
                row.command_id, row.claim_token = command_id, token
            if reserve_claim:
                assert reserve(db, "audits", token, command_id)
        return generation, command_id, token


def settings(**overrides):
    values = dict(log_path=None, log_level="CRITICAL", total_timeout_seconds=0)
    values.update(overrides)
    return SeedingSettings(**values)


def run(domains=("audits",), dry=False, cfg=None):
    import argparse
    args = argparse.Namespace(domain=list(domains), all=False, since=None, dry_run=dry,
                              audits_source_manifest=None, audits_observe_listing=False)
    return cli.run_seed_command(args, cfg or settings())


def outcome(fn, *args, **kwargs):
    try:
        value = fn(*args, **kwargs)
        return "accepted" if value is None else value
    except Exception as exc:  # noqa: BLE001 - recorded
        return type(exc).__name__


def environment(label):
    import subprocess
    root = HERE.parents[1]
    info = {"label": label, "python": platform.python_version(), "sqlalchemy": sqlalchemy.__version__,
            "platform": platform.platform(),
            "head": subprocess.check_output(["/usr/bin/git", "rev-parse", "HEAD"], cwd=root, text=True,
                                            env={"PATH": "/usr/bin:/bin", "DEVELOPER_DIR": "/Library/Developer/CommandLineTools"}).strip()}
    with admin.connect() as conn:
        info["server"] = conn.scalar(text("SELECT version()"))
        info["database"] = conn.scalar(text("SELECT current_database()"))
        info["user"] = conn.scalar(text("SELECT current_user"))
    print(json.dumps(info), flush=True)
    (HERE / f"environment-{label}.json").write_text(json.dumps(info, indent=2) + "\n")
    return info


def dispose_all():
    for engine in ENGINES:
        engine.dispose()
