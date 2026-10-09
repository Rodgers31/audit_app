"""r3b NEW attacks on SQLite (file DB in this directory): DB-copied entry forgery (native + dispatch-kind
claim), preimage hunt, tagged RUNNING rows, reconciliation strings. On SQLite continuous() is True with
no lock, so the entry digest is the ONLY barrier against a forged acknowledgement."""
import contextlib
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import create_engine, event, exc as sa_exc, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(*args, **kwargs):
    return "TEXT"


from common import (CALLS, HERE, TABLES, Base, Recorder, cli, dispose_all, environment, outcome, run, settings,
                    IngestionJob, IngestionStatus, SeedingDomainClaim)
from seeding import exclusion
from seeding.exclusion import DomainExecution, enter_domain, entry_digest, reserve

R = Recorder("new-sqlite")
environment("new-sqlite")
DBFILE = HERE / ("sqlite-new-" + uuid4().hex + ".db")
engine = create_engine(f"sqlite:///{DBFILE}")
Base.metadata.create_all(engine, tables=TABLES)
with engine.begin() as conn:
    conn.execute(text("CREATE TABLE inert_effects(id integer PRIMARY KEY AUTOINCREMENT, label text NOT NULL)"))
factory = sessionmaker(bind=engine)
cli.SessionLocal = factory


def state(identity):
    with engine.connect() as conn:
        row = conn.execute(text("SELECT entered_at IS NOT NULL, returned_at IS NOT NULL, released_at IS NOT NULL"
                                " FROM seeding_domain_claims WHERE id=:i"), {"i": identity.hex}).first()
    return None if row is None else [bool(x) for x in row]


def db_entry(identity):
    with engine.connect() as conn:
        return UUID(conn.scalar(text("SELECT entry_id FROM seeding_domain_claims WHERE id=:i"), {"i": identity.hex}))


def job(identity, domain, **values):
    now = datetime.now(timezone.utc)
    fields = dict(domain=domain, status=IngestionStatus.COMPLETED, dry_run=False, started_at=now, finished_at=now,
                  items_processed=1, items_created=1, items_updated=0, errors=[],
                  meta={"seeding_claim_id": str(identity)})
    fields.update(values)
    with factory.begin() as db:
        j = IngestionJob(**fields)
        db.add(j)
        db.flush()
        return j.id


def section(name):
    def wrap(fn):
        try:
            fn()
        except BaseException:
            R.harness_error(name)
        return fn
    return wrap


@section("SN1_native_forgery")
def _():
    e = enter_domain(factory, "adv_r3_a", False)
    jid = job(e.identity, "adv_r3_a")
    true_entry = e.entry
    e.close()  # process ended without acknowledging
    R.record("SN1_sqlite_claim_stores_digest_not_nonce", [True, False],
             [db_entry(e.identity) == entry_digest(true_entry), db_entry(e.identity) == true_entry])
    f = DomainExecution(factory, "adv_r3_a", e.identity)
    f.entered, f.entry = True, db_entry(e.identity)
    R.record("SN1_sqlite_native_db_copied_entry_refused", ["DomainOwnershipError", [True, False, False]],
             [outcome(f.acknowledge, jid), state(e.identity)])
    f.entry = true_entry
    R.record("SN1_sqlite_control_true_nonce_accepted", ["accepted", [True, True, True]],
             [outcome(f.acknowledge, jid), state(e.identity)])


@section("SN2_dispatch_kind_forgery")
def _():
    # Dispatch is PostgreSQL-only in production; craft an ENTERED dispatch claim directly to exercise the
    # dispatch-kind acknowledge comparison on SQLite.
    tok, cmd, gen, nonce = uuid4(), uuid4(), uuid4(), uuid4()
    with factory.begin() as db:
        assert reserve(db, "adv_r3_b", tok, cmd)
    with engine.begin() as conn:
        conn.execute(text("UPDATE seeding_domain_claims SET entered_at=acquired_at, entry_id=:e WHERE id=:i"),
                     {"e": entry_digest(nonce).hex, "i": tok.hex})
    jid = job(tok, "adv_r3_b")
    f = DomainExecution(factory, "adv_r3_b", tok, cmd, gen)
    f.entered, f.entry = True, db_entry(tok)
    R.record("SN2_sqlite_dispatch_kind_db_copied_entry_refused", ["DomainOwnershipError", [True, False, False]],
             [outcome(f.acknowledge, jid), state(tok)])
    f.entry = nonce
    R.record("SN2_sqlite_dispatch_kind_control_true_nonce_returns_not_releases", ["accepted", [True, True, False]],
             [outcome(f.acknowledge, jid), state(tok)])


@section("SN3_preimage")
def _():
    captured, statements = [], []
    real = exclusion.enter_domain

    def spy(factory_, domain, dry_run):
        r = real(factory_, domain, dry_run)
        captured.append(r.entry)
        return r

    @event.listens_for(engine, "before_cursor_execute")
    def cap(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement + " " + repr(parameters))
    logfile = HERE / "n3-sqlite-debug.log"
    logfile.write_text("")
    err = io.StringIO()
    exclusion.enter_domain = spy
    try:
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(err):
            code = run(["adv_r3_x"], cfg=settings(log_level="DEBUG", log_path=logfile))
    finally:
        exclusion.enter_domain = real
        event.remove(engine, "before_cursor_execute", cap)
    with engine.connect() as conn:
        dump = " ".join(str(list(r)) for t in ("seeding_domain_claims", "ingestion_jobs")
                        for r in conn.execute(text(f"SELECT * FROM {t}")))
    hay = "\n".join(statements) + logfile.read_text() + err.getvalue() + dump
    n = captured[0]
    forms = [str(n), n.hex, str(n.int), repr(n.bytes)]
    R.record("SN3_sqlite_raw_entry_nonce_never_leaves_process", [0, 1, [], True],
             [code, len(captured), [x for x in forms if x in hay or x.upper() in hay], entry_digest(n).hex in hay],
             statements=len(statements))


@section("SN4_tagged_running")
def _():
    exempt = {"nonexistent_uuid": {"seeding_claim_id": str(uuid4())}, "empty_string": {"seeding_claim_id": ""}}
    refusing = {"int": {"seeding_claim_id": 1}, "null": {"seeding_claim_id": None}, "no_tag": {"since": None}}
    for i, (name, meta) in enumerate(list(exempt.items()) + list(refusing.items())):
        domain = ["adv_r3_t1", "adv_r3_t2", "adv_r3_re", "adv_r3_nn", "adv_r3_ack"][i]
        jid = job(uuid4(), domain, status=IngestionStatus.RUNNING, finished_at=None, meta=meta)
        before = len(CALLS)
        code = run([domain])
        expect = [0, before + 1] if name in exempt else [1, before]
        R.record("SN4_sqlite_native_running_tag_" + name, expect, [code, len(CALLS)])


@section("SN5_reconciliation")
def _():
    for label, by, why in (("space", " ", "why"), ("empty", "op", ""), ("tab", "op", "\t"), ("newline", "\n", "why"),
                           ("nbsp", "op", " "), ("by_65", "o" * 65, "why"), ("text_4001", "op", "w" * 4001),
                           ("control_ok", "op", "why")):
        try:
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO seeding_domain_claims(id,domain,kind,acquired_at,entered_at,entry_id,released_at,reconciled_by,reconciliation)"
                                  " VALUES (:i,:d,'native','2026-10-09 00:00:00','2026-10-09 00:00:00',:e,'2026-10-09 00:00:01',:b,:w)"),
                             {"i": uuid4().hex, "d": "sn5_" + uuid4().hex[:8], "e": uuid4().hex, "b": by, "w": why})
            got = "accepted"
        except sa_exc.IntegrityError:
            got = "rejected"
        blank, over = by.strip() == "" or why.strip() == "", len(by) > 64 or len(why) > 4000
        R.record("SN5_sqlite_reconciliation_" + label, "rejected" if blank or over else "accepted", got)


s = R.summary()
engine.dispose()
dispose_all()
sys.exit(1 if s["failed"] else 0)
