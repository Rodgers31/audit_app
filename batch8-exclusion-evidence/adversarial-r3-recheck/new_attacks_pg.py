"""r3b NEW attacks on the round-3 fixes (PostgreSQL, owned r3b schemas, NullPool engines).

N1 digest storage (adapted E check); N2 DB-copied entry forgery in every PG path, with true-nonce
positive controls; N3 preimage hunt (every SQL statement+params, DEBUG logs, SQLAlchemy echo, stderr,
full schema dump); N4 migrated Batch 7 matrix through finish()/register_worker() using the REAL
upgrade() function of e572b8c9a001 (not a copy) on pre-populated Batch 7 rows; N5 tagged RUNNING rows
for native entry and worker claim(); N6 reconciliation strings on models DDL and migration DDL;
N7 open() hardening (idle_in_transaction timeout, AUTOCOMMIT); N8 models/migration constraint parity.
Product code is unchanged; the harness only wraps functions to OBSERVE (capture nonces) and inserts rows.
"""
import contextlib
import importlib.util
import io
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from common import (BEHAVIOR, CALLS, HERE, Base, Recorder, Scenario, admin, cli, dispose_all, environment,
                    outcome, run, settings, text, AdminAuditLog, EtlDispatchCommand, EtlDispatchDomain,
                    EtlDispatchWorker, IngestionJob, IngestionStatus, SeedingDomainClaim, URL, ENGINES, TABLES)
from sqlalchemy import create_engine, event, exc as sa_exc
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from seeding import exclusion
from seeding.exclusion import (DomainExecution, DomainOwnershipError, clock, dispatch_scope, enter_domain,
                               entry_digest, reserve)
from seeding.types import DomainRunResult
import os
os.environ["ADMIN_ETL_DISPATCH_ENABLED"] = "true"
import admin_etl_dispatch_adapter as adapter
from admin_etl_dispatch_worker import claim as worker_claim, finish, register_worker

R = Recorder("new-pg")
environment("new-pg")
MIG_PATH = HERE.parents[1] / "backend/alembic/versions/e572b8c9a001_shared_seeding_exclusion.py"


def section(name):
    def wrap(fn):
        try:
            fn()
        except BaseException:
            R.harness_error(name)
        finally:
            BEHAVIOR.clear()
        return fn
    return wrap


def tags(cmd, tok, **extra):
    return {"dispatch_command_id": str(cmd), "dispatch_claim_token": str(tok), **extra}


def load_migration():
    spec = importlib.util.spec_from_file_location("mig_e572", MIG_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class OpShim:
    """Runs the migration's own op.execute(...) statements on one owned-schema connection."""

    def __init__(self, conn):
        self.conn = conn
        self.statements = 0

    def execute(self, clause):
        self.statements += 1
        self.conn.execute(clause)

    def get_bind(self):
        return self.conn


class MigScenario(Scenario):
    """Owned schema where seeding_domain_claims is created by the REAL upgrade() (after Batch 7 rows exist)."""

    def __init__(self, label):
        import common
        saved = common.TABLES
        common.TABLES = [t for t in TABLES if t.name != "seeding_domain_claims"]
        try:
            super().__init__(label)
        finally:
            common.TABLES = saved

    def upgrade(self):
        mod = load_migration()
        with self.engine.begin() as conn:
            mod.op = OpShim(conn)
            mod.upgrade()
            return mod.op.statements


def fresh_worker_with_queued(sc):
    with sc.factory.begin() as db:
        now = clock(db)
        if db.get(EtlDispatchWorker, 1) is None:
            db.add(EtlDispatchWorker(id=1, generation=uuid4(), ready=False, last_seen_at=now - timedelta(minutes=5),
                                     expires_at=now - timedelta(minutes=4)))
    gen = register_worker(sc.factory)
    with sc.factory.begin() as db:
        now = clock(db)
        audit = AdminAuditLog(actor_id="inert", action="etl.trigger", payload={})
        db.add(audit)
        db.flush()
        cid = uuid4()
        db.add(EtlDispatchCommand(id=cid, actor_id="inert", idempotency_key=uuid4(), source="oag", domain="audits",
                                  dry_run=False, generation=gen, status="queued", version=1, created_at=now,
                                  updated_at=now, audit_id=audit.id))
    return gen, cid


def running_row(sc, domain, meta):
    with sc.engine.begin() as conn:
        return conn.execute(text(
            "INSERT INTO ingestion_jobs(domain,status,dry_run,started_at,items_processed,items_created,items_updated,errors,metadata)"
            " VALUES (:d,'RUNNING',false,now(),0,0,0,'[]'::jsonb,CAST(:m AS jsonb)) RETURNING id"),
            {"d": domain, "m": __import__("json").dumps(meta)}).scalar()


# ------------------------------------------------------------------ N1 digest storage
@section("N1_digest_storage")
def _():
    sc = Scenario("N1")
    e = enter_domain(sc.factory, "adv_r3_x", False)
    row = sc.claim(e.identity)
    R.record("N1_native_claim_stores_digest_not_nonce", [True, False],
             [row["entry_id"] == entry_digest(e.entry), row["entry_id"] == e.entry])
    e.acknowledge(sc.job(e.identity, "adv_r3_x"))
    e.close()
    generation, command_id, token = sc.dispatch(execution_started=True)
    s = DomainExecution(sc.factory, "audits", token, command_id, generation)
    s.open()
    with dispatch_scope(s):
        enter_domain(sc.factory, "audits", False)
    row = sc.claim(token)
    R.record("N1_dispatch_claim_stores_digest_not_nonce (adapted E_shared_scope expectation)", [True, False],
             [row["entry_id"] == entry_digest(s.entry), row["entry_id"] == s.entry])
    s.close()


# ------------------------------------------------------------------ N2 DB-copied entry forgery, every PG path
@section("N2_forgery")
def _():
    # a. native, legit object alive and holding the lock: forger cannot even open (lock) -> and if it reuses
    #    the legit object's connection-less identity with DB entry it is refused.
    sc = Scenario("N2a")
    e = enter_domain(sc.factory, "adv_r3_x", False)
    job = sc.job(e.identity, "adv_r3_x")
    f = DomainExecution(sc.factory, "adv_r3_x", e.identity)
    opened = outcome(f.open)
    f.entered, f.entry = True, sc.claim(e.identity)["entry_id"]
    R.record("N2a_native_live_forger_cannot_open_and_db_entry_refused", ["DomainOwnershipError", "DomainOwnershipError", [True, False, False]],
             [opened, outcome(f.acknowledge, job), sc.state(e.identity)])
    # Same forger but piggy-backing on the legit object's lock connection (shares continuity).
    f2 = DomainExecution(sc.factory, "adv_r3_x", e.identity)
    f2.connection, f2.pid = e.connection, e.pid
    f2.entered, f2.entry = True, sc.claim(e.identity)["entry_id"]
    R.record("N2a_native_forger_sharing_live_lock_db_entry_refused", ["DomainOwnershipError", [True, False, False]],
             [outcome(f2.acknowledge, job), sc.state(e.identity)])
    f2.entry = UUID(int=sc.claim(e.identity)["entry_id"].int)  # equal value, different object
    R.record("N2a_native_forger_db_entry_reconstructed_refused", ["DomainOwnershipError", [True, False, False]],
             [outcome(f2.acknowledge, job), sc.state(e.identity)])
    f2.entry = e.entry  # positive control: the true nonce is accepted, so the digest is the only barrier
    R.record("N2a_control_true_nonce_accepted", ["accepted", [True, True, True]],
             [outcome(f2.acknowledge, job), sc.state(e.identity)])
    f2.connection = None
    e.close()

    # b. native retained after the legit process ended without ack (closed, lock released).
    sc = Scenario("N2b")
    e = enter_domain(sc.factory, "adv_r3_y", False)
    job = sc.job(e.identity, "adv_r3_y")
    true_entry = e.entry
    e.close()
    f = DomainExecution(sc.factory, "adv_r3_y", e.identity)
    f.open()
    f.entered, f.entry = True, sc.claim(e.identity)["entry_id"]
    R.record("N2b_native_closed_without_ack_db_entry_refused", ["DomainOwnershipError", [True, False, False]],
             [outcome(f.acknowledge, job), sc.state(e.identity)])
    for label, value in (("digest_of_db_entry", entry_digest(sc.claim(e.identity)["entry_id"])),
                         ("identity_as_entry", e.identity), ("nil", UUID(int=0)),
                         ("db_entry_str", str(sc.claim(e.identity)["entry_id"]))):
        f.entry = value
        R.record("N2b_native_entry_variant_refused_" + label, ["DomainOwnershipError", [True, False, False]],
                 [outcome(f.acknowledge, job), sc.state(e.identity)])
    f.entry = true_entry
    R.record("N2b_control_true_nonce_accepted_after_reopen", ["accepted", [True, True, True]],
             [outcome(f.acknowledge, job), sc.state(e.identity)])
    f.close()

    # c. dispatch entered, legit scope closed without ack (CLI died after entry): forge with DB entry.
    for forge in (True, False):
        sc = Scenario("N2c_" + str(forge))
        generation, command_id, token = sc.dispatch(execution_started=True)
        s = DomainExecution(sc.factory, "audits", token, command_id, generation)
        s.open()
        with dispatch_scope(s):
            enter_domain(sc.factory, "audits", False)
        job = sc.job(token, "audits", meta={"seeding_claim_id": str(token), **tags(command_id, token)})
        true_entry = s.entry
        s.close()
        f = DomainExecution(sc.factory, "audits", token, command_id, generation)
        f.open()
        f.entered = True
        f.entry = sc.claim(token)["entry_id"] if forge else true_entry
        ack = outcome(f.acknowledge, job)
        f.close()
        fin = finish(sc.factory, generation, command_id, token, 0)
        if forge:
            R.record("N2c_dispatch_closed_without_ack_db_entry_forgery_refused",
                     ["DomainOwnershipError", False, "interrupted", [True, False, False]],
                     [ack, fin, sc.command(command_id)[0], sc.state(token)])
        else:
            R.record("N2c_control_dispatch_true_nonce_ack_then_finish_completes",
                     ["accepted", True, "completed", [True, True, True]],
                     [ack, fin, sc.command(command_id)[0], sc.state(token)])

    # d. migrated entered claim (backfill entry_id=gen_random_uuid()): forge with that value.
    sc = MigScenario("N2d")
    generation, command_id, token = sc.dispatch(execution_started=True, reserve_claim=False)
    job = sc.job(token, "audits", meta={"seeding_claim_id": str(token), **tags(command_id, token)})
    sc.upgrade()
    f = DomainExecution(sc.factory, "audits", token, command_id, generation)
    f.open()
    f.entered, f.entry = True, sc.claim(token)["entry_id"]
    ack = outcome(f.acknowledge, job)
    f.close()
    R.record("N2d_migrated_entered_claim_db_entry_forgery_refused",
             ["DomainOwnershipError", [True, False, False], False, "interrupted"],
             [ack, sc.state(token), finish(sc.factory, generation, command_id, token, 0), sc.command(command_id)[0]])

    # e. forged dispatch scope trying to RE-ENTER an already entered claim with entry preset to the DB value
    sc = Scenario("N2e")
    generation, command_id, token = sc.dispatch(execution_started=True)
    s = DomainExecution(sc.factory, "audits", token, command_id, generation)
    s.open()
    with dispatch_scope(s):
        enter_domain(sc.factory, "audits", False)
    s.close()
    g = DomainExecution(sc.factory, "audits", token, command_id, generation)
    g.open()
    g.entry = sc.claim(token)["entry_id"]
    with dispatch_scope(g):
        r1 = outcome(enter_domain, sc.factory, "audits", False)
    g.entry = None
    with dispatch_scope(g):
        r2 = outcome(enter_domain, sc.factory, "audits", False)
    g.close()
    R.record("N2e_reentry_of_entered_dispatch_claim_refused", ["DomainOwnershipError", "DomainOwnershipError", [True, False, False]],
             [r1, r2, sc.state(token)])


# ------------------------------------------------------------------ N3 preimage hunt
@section("N3_preimage")
def _():
    captured = []
    real_enter, real_dispatch = exclusion.enter_domain, exclusion._enter_dispatch

    def spy_enter(factory, domain, dry_run):
        result = real_enter(factory, domain, dry_run)
        captured.append(result.entry)
        return result

    def spy_dispatch(factory, scope, domain, dry_run):
        result = real_dispatch(factory, scope, domain, dry_run)
        captured.append(result.entry)
        return result

    for mode in ("native", "dispatch"):
        sc = Scenario("N3_" + mode)
        statements = []

        @event.listens_for(sc.engine, "before_cursor_execute")
        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement + " " + repr(parameters))
        logfile = HERE / f"n3-{mode}-debug.log"
        logfile.write_text("")
        err = io.StringIO()
        captured.clear()
        exclusion.enter_domain, exclusion._enter_dispatch = spy_enter, spy_dispatch
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
        try:
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(err):
                if mode == "native":
                    code = run(["adv_r3_x"], cfg=settings(log_level="DEBUG", log_path=logfile))
                else:
                    generation, command_id, token = sc.dispatch(execution_started=False)
                    code = adapter.execute(sc.factory, sc.engine, command_id, token, generation)
                    fin = finish(sc.factory, generation, command_id, token, code)
        finally:
            exclusion.enter_domain, exclusion._enter_dispatch = real_enter, real_dispatch
            logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        with sc.engine.connect() as conn:
            tables = list(conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema=:s"),
                                       {"s": sc.schema}).scalars())
            dump = " ".join(str(r) for t in tables
                            for r in conn.execute(text(f'SELECT row_to_json(x)::text FROM "{t}" x')).scalars())
        haystack = "\n".join(statements) + logfile.read_text() + err.getvalue() + dump
        nonce = captured[0] if captured else None
        forms = [] if nonce is None else [str(nonce), nonce.hex, str(nonce.int), repr(nonce.bytes), nonce.bytes.hex()]
        hits = [f for f in forms if f in haystack or f.upper() in haystack]
        digest_seen = nonce is not None and (str(entry_digest(nonce)) in haystack or entry_digest(nonce).hex in haystack)
        R.record("N3_" + mode + "_raw_entry_nonce_never_leaves_process", [0, 1, [], True],
                 [code, len(set(captured)), hits, digest_seen], statements=len(statements), tables_dumped=tables,
                 log_bytes=len(logfile.read_text()), stderr_bytes=len(err.getvalue()),
                 note="digest_seen=True proves the capture channel sees the stored value (non-vacuous)")


# ------------------------------------------------------------------ N4 migrated Batch 7 matrix (real upgrade())
@section("N4_migrated_matrix")
def _():
    obs_kinds = {
        "none": None,
        "completed": dict(status=IngestionStatus.COMPLETED),
        "failed": dict(status=IngestionStatus.FAILED, errors=["boom"]),
        "running": dict(status=IngestionStatus.RUNNING, finished_at=None),
        "refused_true": dict(status=IngestionStatus.FAILED, errors=["not run"], items_processed=0, items_created=0,
                             extra={"ownership_refused": True}),
        "refused_false_value": dict(status=IngestionStatus.COMPLETED, extra={"ownership_refused": False}),
        "refused_json_null": dict(status=IngestionStatus.COMPLETED, extra={"ownership_refused": None}),
    }
    for started in (True, False):
        for kind, spec in obs_kinds.items():
            label = f"started_{started}_obs_{kind}"
            sc = MigScenario("N4_" + label)
            generation, command_id, token = sc.dispatch(execution_started=started, reserve_claim=False)
            if spec is not None:
                spec = dict(spec)
                extra = spec.pop("extra", {})
                sc.job(token, "audits", meta=tags(command_id, token, **extra), **spec)
            n = sc.upgrade()
            before = sc.state(token)
            fin = finish(sc.factory, generation, command_id, token, 0)
            after, cmd = sc.state(token), sc.command(command_id)[0]
            # Isolate the claim: an operator clears the legacy pointer and finalises any RUNNING row;
            # only the seeding claim may still exclude native entry.
            with sc.engine.begin() as conn:
                conn.execute(text("UPDATE etl_dispatch_domains SET command_id=NULL, claim_token=NULL"))
                conn.execute(text("UPDATE ingestion_jobs SET status='FAILED', finished_at=now() WHERE status='RUNNING'"))
            native = "runs" if run(["audits"]) == 0 else "blocked"
            ran_risk = started or kind in ("completed", "failed", "running", "refused_json_null")
            if kind == "refused_false_value" and not started:
                # Value-blind refusal filter: a key present with ANY value is treated as a refusal.
                expected = [[False, False, False], True, [False, False, True], "failed", "runs"]
            elif ran_risk:
                expected = [[started, False, False], False, [started, False, False], "interrupted", "blocked"]
            else:
                expected = [[False, False, False], True, [False, False, True], "failed", "runs"]
            R.record("N4_finish_" + label, expected, [before, fin, after, cmd, native], upgrade_statements=n)
    # register_worker() path (Batch 7 lease expired; new worker registers)
    for started in (True, False):
        for kind in ("none", "completed", "refused_true"):
            label = f"started_{started}_obs_{kind}"
            sc = MigScenario("N4r_" + label)
            generation, command_id, token = sc.dispatch(execution_started=started, reserve_claim=False,
                                                        lease=timedelta(seconds=1))
            if kind == "completed":
                sc.job(token, "audits", meta=tags(command_id, token))
            elif kind == "refused_true":
                sc.job(token, "audits", status=IngestionStatus.FAILED, errors=["not run"],
                       meta=tags(command_id, token, ownership_refused=True))
            sc.upgrade()
            time.sleep(1.2)
            new_gen = register_worker(sc.factory)
            fin_new = finish(sc.factory, new_gen, command_id, token, 0)
            fin_old = finish(sc.factory, generation, command_id, token, 0)
            R.record("N4_register_worker_" + label,
                     ["interrupted", [started, False, False], False, False, None],
                     [sc.command(command_id)[0], sc.state(token), fin_new, fin_old, worker_claim(sc.factory, new_gen)],
                     note="never-entered claim of an interrupted command has no runtime release path (operator only)")


# ------------------------------------------------------------------ N5 tagged RUNNING rows
@section("N5_tagged_running")
def _():
    def cases(sc, domain):
        released = uuid4()
        with sc.factory.begin() as db:
            assert reserve(db, domain, released, entry=uuid4())
        with sc.engine.begin() as conn:
            conn.execute(text("UPDATE seeding_domain_claims SET released_at=now(), reconciled_by='rev', reconciliation='harness' WHERE id=:i"), {"i": released})
        other = sc.native_claim("adv_r3_b")  # active claim of a DIFFERENT domain
        return {
            "released_claim": {"seeding_claim_id": str(released)},
            "active_other_domain_claim": {"seeding_claim_id": str(other)},
            "nonexistent_uuid": {"seeding_claim_id": str(uuid4())},
            "empty_string": {"seeding_claim_id": ""},
            "whitespace": {"seeding_claim_id": "   "},
            "not_a_uuid": {"seeding_claim_id": "x"},
            "int": {"seeding_claim_id": 123},
            "null": {"seeding_claim_id": None},
            "dict": {"seeding_claim_id": {"a": 1}},
            "list": {"seeding_claim_id": ["x"]},
            "bool": {"seeding_claim_id": True},
            "no_tag": {"since": None},
            "meta_array": ["seeding_claim_id"],
            "meta_string": "seeding_claim_id",
        }
    exempt = {"released_claim", "active_other_domain_claim", "nonexistent_uuid", "empty_string", "whitespace", "not_a_uuid"}
    names = list(cases(Scenario("N5_probe"), "adv_r3_x"))
    for name in names:
        sc = Scenario("N5_native_" + name)
        meta = cases(sc, "adv_r3_x")[name]
        running_row(sc, "adv_r3_x", meta)
        before = len(CALLS)
        code = run(["adv_r3_x"])
        R.record("N5_native_entry_running_tag_" + name, [0 if name in exempt else 1, before + (1 if name in exempt else 0)],
                 [code, len(CALLS)], classification="INTENDED per author (only untagged-str rows refuse)" if name in exempt else "fail-closed")
    # Active claim of the SAME domain tagged on the RUNNING row: the claim itself must still exclude.
    sc = Scenario("N5_native_active_same")
    held = sc.native_claim("adv_r3_x")
    running_row(sc, "adv_r3_x", {"seeding_claim_id": str(held)})
    R.record("N5_native_entry_running_tag_active_same_domain_claim", [1, [True, False, False]], [run(["adv_r3_x"]), sc.state(held)])
    # Worker claim() for audits.
    for name in names + ["active_same_domain_claim"]:
        sc = Scenario("N5_worker_" + name)
        gen, cid = fresh_worker_with_queued(sc)
        if name == "active_same_domain_claim":
            held = sc.native_claim("audits")
            meta = {"seeding_claim_id": str(held)}
        else:
            meta = cases(sc, "audits")[name]
        running_row(sc, "audits", meta)
        got = worker_claim(sc.factory, gen)
        expect_claim = name in exempt
        R.record("N5_worker_claim_running_tag_" + name, expect_claim, got is not None,
                 command_status=sc.command(cid)[0])


# ------------------------------------------------------------------ N6/N8 reconciliation strings + DDL parity
@section("N6_reconciliation")
def _():
    for ddl in ("models", "migration"):
        sc = Scenario("N6_" + ddl) if ddl == "models" else MigScenario("N6_" + ddl)
        if ddl == "migration":
            sc.upgrade()
        for label, by, why in (
                ("space_by", " ", "why"), ("space_text", "op", "   "), ("empty_by", "", "why"), ("empty_text", "op", ""),
                ("tab_text", "op", "\t"), ("newline_text", "op", "\n"), ("crlf_by", "\r\n", "why"),
                ("nbsp_text", "op", " "), ("ideographic_space_by", "　", "why"), ("zwsp_text", "op", "​"),
                ("by_64_multibyte", "é" * 64, "why"), ("by_65_multibyte", "é" * 65, "why"),
                ("text_4000", "op", "w" * 4000), ("text_4001", "op", "w" * 4001),
                ("text_4001_multibyte", "op", "é" * 4001), ("control_ok", "op", "why")):
            ident = uuid4()
            try:
                with sc.engine.begin() as conn:
                    conn.execute(text("INSERT INTO seeding_domain_claims(id,domain,kind,acquired_at,entered_at,entry_id,released_at,reconciled_by,reconciliation)"
                                      " VALUES (:i,:d,'native',now(),now(),:e,now(),:b,:w)"),
                                 {"i": ident, "d": "n6_" + uuid4().hex[:8], "e": uuid4(), "b": by, "w": why})
                got = "accepted"
            except (sa_exc.IntegrityError, sa_exc.DataError) as exc:
                got = "rejected:" + (getattr(getattr(exc.orig, "diag", None), "constraint_name", None) or type(exc.orig).__name__)
            blank = (by.strip() == "" or why.strip() == "")
            over = len(by) > 64 or len(why) > 4000
            expected = "rejected" if (blank or over) else "accepted"
            R.record(f"N6_{ddl}_reconciliation_{label}", expected, got.split(":")[0], detail=got,
                     python_isspace_blank=blank)
    # N8: constraint parity between models DDL and the migration DDL.
    a, b = Scenario("N8_models"), MigScenario("N8_migration")
    b.upgrade()

    def defs(sc):
        with sc.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT conname, pg_get_constraintdef(c.oid) FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid"
                " JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname=:s AND t.relname='seeding_domain_claims'"
                " AND contype='c' ORDER BY conname"), {"s": sc.schema}).all()
            idx = conn.execute(text("SELECT indexdef FROM pg_indexes WHERE schemaname=:s AND tablename='seeding_domain_claims' AND indexname='uq_seeding_active_domain'"), {"s": sc.schema}).scalar()
        return {k: v for k, v in rows}, idx.replace(sc.schema, "S")
    da, db_ = defs(a), defs(b)
    R.record("N8_models_vs_migration_check_constraints_identical", True, da[0] == db_[0],
             differing=sorted(k for k in set(da[0]) | set(db_[0]) if da[0].get(k) != db_[0].get(k)))
    R.record("N8_models_vs_migration_active_index_identical", True, da[1] == db_[1], models=da[1], migration=db_[1])


# ------------------------------------------------------------------ N7 open() hardening
@section("N7_open_hardening")
def _():
    sc = Scenario("N7")
    eng = create_engine(URL, poolclass=NullPool, connect_args={
        "options": f"-csearch_path={sc.schema} -cidle_in_transaction_session_timeout=300"})
    ENGINES.append(eng)
    fac = sessionmaker(bind=eng)
    # Control: the timeout is live for an ordinary idle transaction on this engine.
    killed = False
    with eng.connect() as conn:
        conn.execute(text("SELECT 1"))
        time.sleep(1.0)
        try:
            conn.execute(text("SELECT 1"))
        except sa_exc.DBAPIError:
            killed = True
    BEHAVIOR["adv_r3_t1"] = lambda s, st, ctx: (time.sleep(1.5), s.execute(text("INSERT INTO inert_effects(label) VALUES ('t1')")),
                                                 DomainRunResult(domain="adv_r3_t1", dry_run=ctx.dry_run, items_processed=1, items_created=1))[-1]
    cli.SessionLocal = fac
    code = run(["adv_r3_t1"])
    with eng.connect() as conn:
        rows = [list(r) for r in conn.execute(text("SELECT entered_at IS NOT NULL, returned_at IS NOT NULL, released_at IS NOT NULL FROM seeding_domain_claims WHERE domain='adv_r3_t1'"))]
    R.record("N7_idle_in_tx_timeout_300ms_does_not_strand_1500ms_native_run", [True, 0, [[True, True, True]]],
             [killed, code, rows], note="control killed=True proves the session timeout was live")
    BEHAVIOR.clear()
    cli.SessionLocal = sc.factory
    # AUTOCOMMIT engine: the xact lock evaporates immediately; open() must refuse, nothing reserved.
    auto = create_engine(URL, poolclass=NullPool, isolation_level="AUTOCOMMIT",
                         connect_args={"options": f"-csearch_path={sc.schema}"})
    ENGINES.append(auto)
    afac = sessionmaker(bind=auto)
    r = outcome(enter_domain, afac, "adv_r3_t2", False)
    n = sc.scalar("SELECT count(*) FROM seeding_domain_claims WHERE domain='adv_r3_t2'")
    R.record("N7_autocommit_engine_native_entry_refused_nothing_reserved", ["DomainOwnershipError", 0], [r, n])
    generation, command_id, token = sc.dispatch(execution_started=False)
    code = adapter.execute(afac, auto, command_id, token, generation)
    R.record("N7_autocommit_engine_adapter_refused_before_execution_started", [1, False, [False, False, False]],
             [code, sc.command(command_id)[2], sc.state(token)])
    # Lock held by another backend: open() refuses and leaves no lock/connection.
    holder = admin.connect()
    holder.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": DomainExecution(sc.factory, "adv_r3_t2", uuid4()).key})
    r = outcome(enter_domain, sc.factory, "adv_r3_t2", False)
    holder.rollback(); holder.close()
    R.record("N7_lock_held_elsewhere_entry_refused", ["DomainOwnershipError", 0],
             [r, sc.scalar("SELECT count(*) FROM seeding_domain_claims WHERE domain='adv_r3_t2'")])


s = R.summary()
dispose_all()
sys.exit(1 if s["failed"] else 0)
