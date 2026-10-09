"""Seeding ownership storage on SQLite + PostgreSQL DDL, at any installed SQLAlchemy.

Run with the declared minimum (2.0.23, owned/reused target install, Python 3.12)
and the current runtime (2.0.46, Python 3.13). No network, no PostgreSQL server:
SQLite in memory, PostgreSQL only as compiled DDL/statements. Exit 0 = all pass.
"""
import json
import platform
import sys
from uuid import UUID, uuid4

import sqlalchemy
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateIndex, CreateTable


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(*args, **kwargs):  # same shim as the existing SQLite fixtures
    return "TEXT"


from models import Base, IngestionJob, IngestionStatus, SeedingDomainClaim  # noqa: E402
from seeding.exclusion import DomainOwnershipError, entry_digest, reserve  # noqa: E402

results = []


def check(name, ok, **detail):
    results.append({"name": name, "passed": bool(ok), **detail})


engine = create_engine("sqlite://")
event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
Base.metadata.create_all(engine)
check("sqlite create_all", "seeding_domain_claims" in sqlalchemy.inspect(engine).get_table_names(),
      tables=len(sqlalchemy.inspect(engine).get_table_names()))
factory = sessionmaker(bind=engine)

first, second, entry = uuid4(), uuid4(), uuid4()
with factory.begin() as db:
    check("native reserve wins", reserve(db, "audits", first, entry=entry) is True)
with factory.begin() as db:
    check("second native reserve loses on partial unique index", reserve(db, "audits", second) is False)
with factory() as db:
    row = db.get(SeedingDomainClaim, first)
    check("uuid round trip; only the entry digest is stored", isinstance(row.id, UUID) and row.id == first
          and row.entry_id == entry_digest(entry) and row.entry_id != entry)
    check("native entered at acquisition", row.entered_at is not None and row.kind == "native")
with factory.begin() as db:
    job = IngestionJob(domain="audits", status=IngestionStatus.COMPLETED, dry_run=False, items_processed=0,
                       items_created=0, items_updated=0, errors=[], meta={})
    db.add(job)
    db.flush()
    db.execute(text("UPDATE seeding_domain_claims SET returned_at=entered_at, job_id=:job, released_at=entered_at"), {"job": job.id})
with factory.begin() as db:
    check("released domain can be reacquired", reserve(db, "audits", second) is True)
for name, columns, values in [
    ("native without entry", "kind,acquired_at", "'native','2026-01-01'"),
    ("entered without nonce", "kind,acquired_at,entered_at", "'native','2026-01-01','2026-01-01'"),
]:
    try:
        with engine.begin() as conn:
            conn.execute(text(f"INSERT INTO seeding_domain_claims(id,domain,{columns}) VALUES (:id,'other',{values})"),
                         {"id": uuid4().hex})
        check("sqlite rejects " + name, False)
    except IntegrityError as exc:
        check("sqlite rejects " + name, "ck_seeding_claim_entry" in str(exc) or "CHECK" in str(exc))
for name, by, why in [("blank operator", " ", "evidence"), ("blank evidence", "operator", "  ")]:
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE seeding_domain_claims SET released_at=entered_at, reconciled_by=:b, reconciliation=:w"
                              " WHERE released_at IS NULL"), {"b": by, "w": why})
        check("sqlite rejects " + name, False)
    except IntegrityError as exc:
        check("sqlite rejects " + name, "CHECK" in str(exc) or "ck_seeding_claim" in str(exc))
with engine.begin() as conn:
    conn.execute(text("UPDATE seeding_domain_claims SET released_at=entered_at, reconciled_by='operator',"
                      " reconciliation='writers stopped; effects reconciled' WHERE released_at IS NULL"))
check("sqlite accepts operator reconciliation", True)
for bad in [("audits", "not-a-uuid"), ("", uuid4()), ("x" * 101, uuid4()), (None, uuid4())]:
    try:
        with factory.begin() as db:
            reserve(db, *bad)
        check("malformed reserve rejected", False, input=repr(bad))
    except DomainOwnershipError:
        check("malformed reserve rejected", True, input=repr(bad)[:40])

dialect = postgresql.dialect()
ddl = str(CreateTable(SeedingDomainClaim.__table__).compile(dialect=dialect))
check("postgres native UUID DDL", "id UUID NOT NULL" in ddl and "entry_id UUID" in ddl)
index = next(i for i in SeedingDomainClaim.__table__.indexes if i.name == "uq_seeding_active_domain")
check("postgres partial unique index", "WHERE released_at IS NULL" in str(CreateIndex(index).compile(dialect=dialect)))
statement = postgresql.insert(SeedingDomainClaim).values(id=uuid4(), domain="audits", kind="native",
    acquired_at=sqlalchemy.func.now()).on_conflict_do_nothing().returning(SeedingDomainClaim.id)
check("postgres on conflict returning", "ON CONFLICT DO NOTHING RETURNING" in str(statement.compile(dialect=dialect)))

summary = {"python": platform.python_version(), "sqlalchemy": sqlalchemy.__version__,
           "sqlite": __import__("sqlite3").sqlite_version, "checks": len(results),
           "failed": [r for r in results if not r["passed"]]}
print(json.dumps(results, default=str))
print(json.dumps(summary))
sys.exit(1 if summary["failed"] or not results else 0)
