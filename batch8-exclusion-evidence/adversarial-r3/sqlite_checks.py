"""Round-3 SQLite (file DB) forgeries against the real CLI/ownership code. No PostgreSQL used here
except the common module's admin engine for environment identity."""
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(*args, **kwargs):
    return "TEXT"


from common import (BEHAVIOR, CALLS, HERE, TABLES, Base, Recorder, cli, dispose_all, environment, outcome, run,
                    AdminAuditLog, EtlDispatchCommand, EtlDispatchDomain, EtlDispatchWorker, IngestionJob,
                    IngestionStatus, SeedingDomainClaim)
from seeding.exclusion import DomainExecution, DomainOwnershipError, dispatch_scope, enter_domain, reserve
from seeding.types import DomainRunResult

R = Recorder("sqlite")
environment("sqlite")
DBFILE = HERE / ("sqlite-" + uuid4().hex + ".db")
engine = create_engine(f"sqlite:///{DBFILE}")
Base.metadata.create_all(engine, tables=TABLES)
with engine.begin() as conn:
    conn.execute(text("CREATE TABLE inert_effects(id integer PRIMARY KEY AUTOINCREMENT, label text NOT NULL)"))
factory = sessionmaker(bind=engine)
cli.SessionLocal = factory


def sq(sql, **p):
    with engine.connect() as conn:
        return conn.scalar(text(sql), p)


def state(identity):
    with engine.connect() as conn:
        row = conn.execute(text("SELECT entered_at IS NOT NULL, returned_at IS NOT NULL, released_at IS NOT NULL"
                                " FROM seeding_domain_claims WHERE id=:i"), {"i": identity.hex}).first()
    return None if row is None else [bool(x) for x in row]


def native(domain, entry=None):
    identity = uuid4()
    with factory.begin() as db:
        assert reserve(db, domain, identity, entry=entry)
    return identity


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


def effects():
    return sq("SELECT count(*) FROM inert_effects")


def scoped(scope, do_open=True, domains=("audits",)):
    try:
        if do_open:
            scope.open()
        with dispatch_scope(scope):
            return run(domains)
    except Exception as exc:  # noqa: BLE001
        return type(exc).__name__
    finally:
        scope.close()


try:
    R.record("S1_native_positive", [0, 1], [run(), effects()])
    retained = native("audits")
    R.record("S2_retained_native_excludes", [1, 1, [True, False, False]], [run(), effects(), state(retained)])
    base = len(CALLS)
    for label, scope in (("retained_native_id", DomainExecution(factory, "audits", retained)),
                         ("random_id", DomainExecution(factory, "audits", uuid4())),
                         ("random_correlation", DomainExecution(factory, "audits", uuid4(), uuid4(), uuid4())),
                         ("retained_with_fake_correlation", DomainExecution(factory, "audits", retained, uuid4(), uuid4()))):
        R.record("S3_forged_scope_" + label, [1, base, 1, [True, False, False]],
                 [scoped(scope), len(CALLS), effects(), state(retained)])
    for label, value in (("namespace", SimpleNamespace(domain="audits", entered=False, entry=None)), ("true", True)):
        try:
            with dispatch_scope(value):
                code = run()
        except Exception as exc:  # noqa: BLE001
            code = type(exc).__name__
        R.record("S3_forged_scope_shape_" + label, [1, base], [code, len(CALLS)])
    s = DomainExecution(factory, "audits", retained)
    s.entered, s.entry = True, uuid4()
    R.record("S3_forged_scope_preset_entered", [1, base], [scoped(s), len(CALLS)])

    # Dispatch rows on SQLite (dispatch is PostgreSQL-only in production; entry must still fail closed).
    sql_engine_free = native  # noqa
    with factory.begin() as db:
        db.execute(text("UPDATE seeding_domain_claims SET released_at=acquired_at, reconciled_by='reviewer',"
                        " reconciliation='harness: free audits for dispatch probe' WHERE id=:i"), {"i": retained.hex})
    gen, cmd, tok = uuid4(), uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    with factory.begin() as db:
        a = AdminAuditLog(actor_id="inert", action="etl.trigger", payload={})
        db.add(a); db.flush()
        db.add(EtlDispatchWorker(id=1, generation=gen, ready=True, last_seen_at=now - timedelta(seconds=1),
                                 expires_at=now + timedelta(minutes=10)))
        db.add(EtlDispatchCommand(id=cmd, actor_id="inert", idempotency_key=uuid4(), source="oag", domain="audits",
            dry_run=False, generation=gen, claim_token=tok, execution_started=True, status="running", version=2,
            created_at=now, updated_at=now, started_at=now, audit_id=a.id))
        db.flush()
        db.add(EtlDispatchDomain(domain="audits", command_id=cmd, claim_token=tok))
        assert reserve(db, "audits", tok, cmd)
    before = len(CALLS)
    code = scoped(DomainExecution(factory, "audits", tok, cmd, gen), do_open=False)
    R.record("S4_sqlite_exact_dispatch_correlation_no_lock", [1, before, [False, False, False]],
             [code, len(CALLS), state(tok)],
             note="expected fail-closed: dispatch is PostgreSQL-only; observed exception class is in the run log")

    # Forged acknowledgement with the entry nonce copied from the DB (retained native, terminal job).
    entry = uuid4()
    held = native("adv_r3_a", entry=entry)
    jid = job(held, "adv_r3_a")
    f = DomainExecution(factory, "adv_r3_a", held)
    f.open()
    f.entered = True
    f.entry = __import__("uuid").UUID(sq("SELECT entry_id FROM seeding_domain_claims WHERE id=:i", i=held.hex))
    out = outcome(f.acknowledge, jid)
    f.close()
    R.record("S5_sqlite_forged_db_copied_entry_cannot_release_retained", ["DomainOwnershipError", [True, False, False]],
             [out, state(held)],
             repro="reserve(db,'adv_r3_a',id,entry=E); terminal job; f=DomainExecution(factory,'adv_r3_a',id); f.entered=True; f.entry=<entry_id read from DB>; f.acknowledge(job)")
    held2 = native("adv_r3_b", entry=uuid4())
    jid2 = job(held2, "adv_r3_b")
    f = DomainExecution(factory, "adv_r3_y", held2)
    f.entered, f.entry = True, __import__("uuid").UUID(sq("SELECT entry_id FROM seeding_domain_claims WHERE id=:i", i=held2.hex))
    R.record("S6_sqlite_wrong_domain_ack_rejected", ["DomainOwnershipError", [True, False, False]],
             [outcome(f.acknowledge, jid2), state(held2)])
    f = DomainExecution(factory, "adv_r3_b", held2)
    f.entered, f.entry = True, uuid4()
    R.record("S6b_sqlite_random_nonce_ack_rejected", ["DomainOwnershipError", [True, False, False]],
             [outcome(f.acknowledge, jid2), state(held2)])
    f = DomainExecution(factory, "adv_r3_b", held2)
    R.record("S6c_sqlite_not_entered_ack_rejected", ["DomainOwnershipError", [True, False, False]],
             [outcome(f.acknowledge, jid2), state(held2)])

    # Native/native contention on a SQLite file (separate connections, threads).
    for iteration in range(3):
        barrier = threading.Barrier(4)
        got, errs = [], []

        def contend():
            barrier.wait()
            try:
                got.append(enter_domain(factory, "adv_r3_nn", False))
            except Exception as exc:  # noqa: BLE001
                errs.append(type(exc).__name__)
        ts = [threading.Thread(target=contend) for _ in range(4)]
        [t.start() for t in ts]
        [t.join(30) for t in ts]
        active = sq("SELECT count(*) FROM seeding_domain_claims WHERE domain='adv_r3_nn' AND released_at IS NULL")
        R.record(f"S7_sqlite_native_threads_at_most_one_owner_{iteration}", [True, 1 if got else 0],
                 [len(got) <= 1, active], winners=len(got), errors=sorted(errs))
        for g in got:
            g.acknowledge(job(g.identity, "adv_r3_nn"))
            g.close()
except Exception:
    R.harness_error("sqlite")

s = R.summary()
engine.dispose()
dispose_all()
sys.exit(1 if s["failed"] else 0)
