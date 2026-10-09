"""Round-3 PostgreSQL execution checks (prior repros, forged scopes, entry, ack, finish, races, schema)."""
import sys
import threading
import time
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

from common import (BEHAVIOR, CALLS, Recorder, Scenario, admin, cli, dispose_all, environment,
                    outcome, run, settings, text, IngestionStatus, EtlDispatchCommand,
                    EtlDispatchDomain, EtlDispatchWorker, SeedingDomainClaim, URL)
from sqlalchemy import event, exc as sa_exc
from sqlalchemy.orm import Session, sessionmaker
from seeding.types import DomainRunResult
from seeding.exclusion import (DomainExecution, DomainOwnershipError, clock, dispatch_scope,
                               enter_domain, reserve, terminal_observation)
import os
os.environ["ADMIN_ETL_DISPATCH_ENABLED"] = "true"
import admin_etl_dispatch_adapter as adapter
from admin_etl_dispatch_worker import claim as worker_claim, finish, register_worker

R = Recorder("pg")
environment("pg")


def scoped_run(sc, scope, dry=False, do_open=True):
    try:
        if do_open:
            scope.open()
        with dispatch_scope(scope):
            return run(dry=dry)
    except Exception as exc:  # noqa: BLE001
        return type(exc).__name__
    finally:
        try:
            scope.close()
        except Exception:
            pass


def section(name):
    def wrap(fn):
        try:
            fn()
        except Exception:
            R.harness_error(name)
        return fn
    return wrap


# ---------------------------------------------------------------- A. prior repros
@section("A_prior_findings")
def _():
    sc = Scenario("A")
    retained = sc.native_claim("audits")
    calls, effects, refused = len(CALLS), sc.effects(), sc.refused()
    scope = DomainExecution(sc.factory, "audits", retained)
    code = scoped_run(sc, scope)
    R.record("A1_prior_finding1_uncorrelated_native_scope_cannot_run",
             [1, 0, effects, [True, False, False], refused + 1],
             [code, len(CALLS) - calls, sc.effects(), sc.state(retained), sc.refused()],
             repro="DomainExecution(factory,'audits',retained_native_id).open(); with dispatch_scope(e): cli.run_seed_command(...)")
    a = sc.native_claim("adv_r3_a")
    job = sc.job(a, "adv_r3_a")
    e = DomainExecution(sc.factory, "adv_r3_b", a)
    e.open()
    try:
        out = outcome(e.acknowledge, job)
    finally:
        e.close()
    R.record("A2_prior_finding2_wrong_domain_ack_cannot_release", ["DomainOwnershipError", [True, False, False]],
             [out, sc.state(a)], entered=e.entered)
    # Finding 2 variant: same object forced entered=True with a random entry nonce.
    e = DomainExecution(sc.factory, "adv_r3_b", a)
    e.open(); e.entered, e.entry = True, uuid4()
    try:
        out = outcome(e.acknowledge, job)
    finally:
        e.close()
    R.record("A2b_wrong_domain_forced_entered_random_nonce", ["DomainOwnershipError", [True, False, False]],
             [out, sc.state(a)])
    R.record("A3_retained_native_still_blocks_cli", [1, effects], [run(), sc.effects()])


# ------------------------------------------------- B. forged-scope matrix (dispatch)
@section("B_forged_scope_matrix")
def _():
    sc = Scenario("B")
    other = Scenario("B_other_engine")
    sc.activate()
    generation, command_id, token = sc.dispatch(execution_started=True)
    retained_native = sc.native_claim("adv_r3_x")
    base_calls, base_eff = len(CALLS), sc.effects()

    def variant(name, identity=token, cmd=command_id, gen=generation, domain="audits", dry=False,
                do_open=True, factory=None, mutate=None, scope=None):
        refused_before = sc.refused()
        if scope is None:
            scope = DomainExecution(factory or sc.factory, domain if isinstance(domain, str) else "audits",
                                    identity, cmd, gen)
            if not isinstance(domain, str):
                scope.domain = domain
        if mutate:
            mutate(scope)
        code = scoped_run(sc, scope, dry=dry, do_open=do_open)
        R.record("B_forged_" + name,
                 [1, base_calls, base_eff, [False, False, False], ["running", None, True, None], refused_before + 1],
                 [code, len(CALLS), sc.effects(), sc.state(token), sc.command(command_id), sc.refused()])

    for label, value in (("random", uuid4()), ("native_claim", retained_native), ("str", str(token)),
                         ("none", None), ("true", True), ("int", 1), ("nil_uuid", UUID(int=0))):
        variant("identity_" + label, identity=value)
    for label, value in (("none", None), ("random", uuid4()), ("str", str(command_id)), ("true", True),
                         ("token_as_cmd", token)):
        variant("command_id_" + label, cmd=value)
    for label, value in (("none", None), ("random", uuid4()), ("str", str(generation)), ("true", True),
                         ("false", False)):
        variant("generation_" + label, gen=value)
    variant("domain_other_str", domain="adv_r3_x")
    variant("domain_str_subclass_mismatch", mutate=lambda s: setattr(s, "domain", "AUDITS"))
    variant("dry_run_mismatch", dry=True)
    variant("never_opened_no_lock", do_open=False)
    variant("opened_then_closed", mutate=lambda s: (s.open(), s.close()), do_open=False)
    variant("other_engine_factory", factory=other.factory)
    variant("preset_entered_true", mutate=lambda s: setattr(s, "entered", True))
    variant("preset_entry_random", mutate=lambda s: setattr(s, "entry", uuid4()))
    variant("preset_entered_and_entry", mutate=lambda s: (setattr(s, "entered", True), setattr(s, "entry", uuid4())))
    variant("entered_truthy_int", mutate=lambda s: setattr(s, "entered", 1))

    class Sub(DomainExecution):
        pass
    variant("subclass_type", scope=Sub(sc.factory, "audits", token, command_id, generation))
    for label, value in (("namespace", SimpleNamespace(domain="audits", identity=token, command_id=command_id,
                                                         generation=generation, entered=False, entry=None,
                                                         engine=sc.engine, continuous=lambda: True)),
                         ("true", True), ("dict", {}), ("list", []), ("string", "audits")):
        refused_before = sc.refused()
        try:
            with dispatch_scope(value):
                code = run()
        except Exception as exc:  # noqa: BLE001
            code = type(exc).__name__
        R.record("B_forged_scope_shape_" + label, [1, base_calls, [False, False, False], refused_before + 1],
                 [code, len(CALLS), sc.state(token), sc.refused()])
    # Kind mismatch: the retained native claim's id with the real command/generation.
    variant("kind_native_claim_with_real_correlation", identity=retained_native)
    # Refused rows never carry a claim id and are never terminal observations.
    with sc.factory() as db:
        claim_row = db.get(SeedingDomainClaim, token)
        refused_ids = [r[0] for r in db.execute(text(
            "SELECT id FROM ingestion_jobs WHERE metadata->>'ownership_refused'='true'")).all()]
        observed = [terminal_observation(db, claim_row, j) is not None for j in refused_ids]
        statuses = {r[0] for r in db.execute(text(
            "SELECT status::text FROM ingestion_jobs WHERE metadata->>'ownership_refused'='true'")).all()}
        tagged = db.scalar(text("SELECT count(*) FROM ingestion_jobs WHERE metadata ? 'seeding_claim_id'"))
    R.record("B_refused_rows_never_terminal_observation", [False] * len(refused_ids), observed,
             refused_rows=len(refused_ids))
    R.record("B_refused_rows_failed_and_untagged", [{"FAILED"}, 0], [statuses, tagged])
    # Correct-value control (no adapter): entry is bound to correlation, and the
    # command was marked execution_started. Documented: whoever enters first.
    refused_before = sc.refused()
    scope = DomainExecution(sc.factory, "audits", token, command_id, generation)
    code = scoped_run(sc, scope)
    R.record("B_control_correct_correlation_enters_once", [0, base_calls + 1, [True, True, False], refused_before],
             [code, len(CALLS), sc.state(token), sc.refused()],
             note="scope with exact command/token/generation and execution_started=true enters without the adapter (design: one-use correlated entry)")
    # Reuse after legitimate entry: a new scope, the same scope, and the adapter.
    code = scoped_run(sc, DomainExecution(sc.factory, "audits", token, command_id, generation))
    R.record("B_reuse_after_entry_new_scope_refused", [1, base_calls + 1], [code, len(CALLS)])
    code = scoped_run(sc, scope)
    R.record("B_reuse_after_entry_same_scope_refused", [1, base_calls + 1], [code, len(CALLS)])
    entry_from_db = sc.claim(token)["entry_id"]
    s2 = DomainExecution(sc.factory, "audits", token, command_id, generation)
    s2.entry = entry_from_db
    R.record("B_reuse_with_db_copied_entry_cannot_reenter", [1, base_calls + 1], [scoped_run(sc, s2), len(CALLS)])
    R.record("B_adapter_after_entry_refused", [1, base_calls + 1],
             [adapter.execute(sc.factory, sc.engine, command_id, token, generation), len(CALLS)])
    R.record("B_finish_untagged_forged_entry_never_completes", [False, [True, True, False], "interrupted"],
             [finish(sc.factory, generation, command_id, token, 0), sc.state(token), sc.command(command_id)[0]],
             note="job written without the adapter's DispatchSession tags -> zero correlated observations")


# --------------------------------- B2. never-entered dispatch: finish releases, then entry refused
@section("B2_never_entered_finish")
def _():
    sc = Scenario("B2")
    generation, command_id, token = sc.dispatch(execution_started=True)
    R.record("B2_finish_releases_never_entered", [True, [False, False, True], ["failed", "failed", True, None]],
             [finish(sc.factory, generation, command_id, token, 0), sc.state(token), sc.command(command_id)])
    c = len(CALLS)
    R.record("B2_entry_after_finish_release_refused", [1, c, [False, False, True]],
             [scoped_run(sc, DomainExecution(sc.factory, "audits", token, command_id, generation)), len(CALLS),
              sc.state(token)])
    R.record("B2_native_runs_after_release", [0, 1], [run(), sc.effects("audits")])


# --------------------------------- D. entry after lease expiry / generation change etc.
@section("D_entry_preconditions")
def _():
    cases = ["lease_expired", "worker_not_ready", "worker_generation_changed", "worker_missing",
             "command_interrupted", "command_generation_other", "domain_row_unbound",
             "domain_row_other_token", "execution_not_started", "claim_released",
             "command_dry_run_true"]
    for case in cases:
        sc = Scenario("D_" + case)
        generation, command_id, token = sc.dispatch(execution_started=True)
        with sc.factory.begin() as db:
            now = clock(db)
            w = db.get(EtlDispatchWorker, 1)
            cmd = db.get(EtlDispatchCommand, command_id)
            row = db.get(EtlDispatchDomain, "audits")
            cl = db.get(SeedingDomainClaim, token)
            if case == "lease_expired":
                w.last_seen_at, w.expires_at = now - timedelta(seconds=40), now - timedelta(seconds=1)
            elif case == "worker_not_ready":
                w.ready = False
            elif case == "worker_generation_changed":
                w.generation = uuid4()
            elif case == "worker_missing":
                db.delete(w)
            elif case == "command_interrupted":
                cmd.status, cmd.outcome, cmd.finished_at, cmd.updated_at = "interrupted", "execution_unverified", now, now
            elif case == "command_generation_other":
                cmd.generation = uuid4()
            elif case == "domain_row_unbound":
                row.command_id = row.claim_token = None
            elif case == "domain_row_other_token":
                row.claim_token = uuid4()
            elif case == "execution_not_started":
                cmd.execution_started = False
            elif case == "claim_released":
                cl.released_at = now
            elif case == "command_dry_run_true":
                cmd.dry_run = True
        c = len(CALLS)
        code = scoped_run(sc, DomainExecution(sc.factory, "audits", token, command_id, generation))
        st = sc.state(token)
        R.record("D_entry_refused_" + case, [1, c, False], [code, len(CALLS), st[0] if st else None])
    # Stale-lease never-entered claim: finish interrupts and retains (no release on lease loss).
    sc = Scenario("D_stale_finish")
    generation, command_id, token = sc.dispatch(execution_started=True)
    with sc.factory.begin() as db:
        now = clock(db)
        w = db.get(EtlDispatchWorker, 1)
        w.last_seen_at, w.expires_at = now - timedelta(seconds=40), now - timedelta(seconds=1)
    R.record("D_finish_stale_lease_never_entered_retains", [False, [False, False, False], "interrupted"],
             [finish(sc.factory, generation, command_id, token, 1), sc.state(token), sc.command(command_id)[0]])


# --------------------------------- E. concurrent legitimate entries of one claim
class SerializedConnection:
    """Harness proxy: lets several threads share ONE lock-holding connection safely."""

    def __init__(self, conn):
        self._c, self._l = conn, threading.Lock()

    @property
    def closed(self):
        return self._c.closed

    @property
    def invalidated(self):
        return self._c.invalidated

    def scalar(self, *a, **k):
        with self._l:
            return self._c.scalar(*a, **k)

    def rollback(self):
        return self._c.rollback()

    def invalidate(self):
        return self._c.invalidate()

    def close(self):
        return self._c.close()


@section("E_concurrent_entries")
def _():
    for iteration in range(5):
        sc = Scenario(f"E{iteration}")
        generation, command_id, token = sc.dispatch(execution_started=True)
        shared = DomainExecution(sc.factory, "audits", token, command_id, generation)
        shared.open()
        shared.connection = SerializedConnection(shared.connection)
        barrier = threading.Barrier(4)
        outcomes = []

        def enter():
            barrier.wait()
            try:
                with dispatch_scope(shared):
                    enter_domain(sc.factory, "audits", False)
                outcomes.append("entered")
            except Exception as exc:  # noqa: BLE001
                outcomes.append(type(exc).__name__)
        threads = [threading.Thread(target=enter) for _ in range(4)]
        [t.start() for t in threads]
        [t.join(30) for t in threads]
        claim_row = sc.claim(token)
        shared.close()
        R.record(f"E_shared_scope_4_threads_one_entry_{iteration}", [1, True, str(shared.entry)],
                 [outcomes.count("entered"), claim_row["entered"], str(claim_row["entry_id"])],
                 outcomes=sorted(outcomes))
    # Two independent scopes with identical correlation (separate connections): lock + claim.
    for iteration in range(3):
        sc = Scenario(f"E_two_{iteration}")
        generation, command_id, token = sc.dispatch(execution_started=True)
        barrier = threading.Barrier(2)
        outcomes = []
        before = len(CALLS)

        def go():
            s = DomainExecution(sc.factory, "audits", token, command_id, generation)
            barrier.wait()
            try:
                s.open()
                with dispatch_scope(s):
                    enter_domain(sc.factory, "audits", False)
                outcomes.append("entered")
                time.sleep(0.3)
            except Exception as exc:  # noqa: BLE001
                outcomes.append(type(exc).__name__)
            finally:
                s.close()
        threads = [threading.Thread(target=go) for _ in range(2)]
        [t.start() for t in threads]
        [t.join(30) for t in threads]
        R.record(f"E_two_scopes_one_entry_{iteration}", [1, True], [outcomes.count("entered"), sc.claim(token)["entered"]],
                 outcomes=sorted(outcomes))
    # Two concurrent adapter launches for the same command (threads, separate connections).
    for iteration in range(3):
        sc = Scenario(f"E_adapter_{iteration}")
        generation, command_id, token = sc.dispatch(execution_started=False)
        BEHAVIOR["audits"] = lambda session, s, ctx: (time.sleep(0.3), session.execute(text(
            "INSERT INTO inert_effects(label) VALUES ('audits')")), DomainRunResult(
            domain="audits", dry_run=ctx.dry_run, items_processed=1, items_created=1))[-1]
        barrier = threading.Barrier(2)
        codes = []

        def launch():
            barrier.wait()
            codes.append(adapter.execute(sc.factory, sc.engine, command_id, token, generation))
        threads = [threading.Thread(target=launch) for _ in range(2)]
        [t.start() for t in threads]
        [t.join(60) for t in threads]
        BEHAVIOR.pop("audits", None)
        R.record(f"E_concurrent_adapters_one_runs_{iteration}", [[0, 1], 1, [True, True, False]],
                 [sorted(codes), sc.effects("audits"), sc.state(token)])
    cli.SessionLocal = sc.factory


# --------------------------------- F. finish vs entry races and correlation
@section("F_finish_races")
def _():
    bad = 0
    tallies = {"entered_then_interrupted": 0, "released_then_refused": 0, "other": 0}
    for iteration in range(8):
        sc = Scenario(f"F{iteration}")
        generation, command_id, token = sc.dispatch(execution_started=True)
        scope = DomainExecution(sc.factory, "audits", token, command_id, generation)
        scope.open()
        barrier = threading.Barrier(2)
        res = {}

        def enter():
            barrier.wait()
            time.sleep(0.002 * (iteration % 3))
            try:
                with dispatch_scope(scope):
                    enter_domain(sc.factory, "audits", False)
                res["enter"] = "entered"
            except Exception as exc:  # noqa: BLE001
                res["enter"] = type(exc).__name__

        def fin():
            barrier.wait()
            time.sleep(0.002 * ((iteration + 1) % 3))
            res["finish"] = outcome(finish, sc.factory, generation, command_id, token, 1)
        threads = [threading.Thread(target=enter), threading.Thread(target=fin)]
        [t.start() for t in threads]
        [t.join(30) for t in threads]
        scope.close()
        st, cmd = sc.state(token), sc.command(command_id)
        if res.get("enter") == "entered" and st == [True, False, False] and cmd[0] == "interrupted":
            tallies["entered_then_interrupted"] += 1
        elif res.get("enter") != "entered" and st == [False, False, True] and cmd[0] == "failed":
            tallies["released_then_refused"] += 1
        else:
            tallies["other"] += 1
        if st[0] and st[2] and not st[1]:
            bad += 1
        R.record(f"F_race_enter_vs_finish_{iteration}", False,
                 bool(st[0] and st[2] and not st[1]) or (res.get("enter") == "entered" and st[2]),
                 enter=res.get("enter"), finish=res.get("finish"), claim=st, command=cmd)
    R.record("F_race_no_inconsistent_outcome", 0, tallies["other"], tallies=tallies)

    # Stale generation argument / worker generation changed / other command's claim.
    sc = Scenario("F_corr")
    generation, command_id, token = sc.dispatch(execution_started=True)
    R.record("F_finish_wrong_generation_arg", [False, [False, False, False], "running"],
             [finish(sc.factory, uuid4(), command_id, token, 1), sc.state(token), sc.command(command_id)[0]])
    R.record("F_finish_wrong_token_arg", [False, [False, False, False], "running"],
             [finish(sc.factory, generation, command_id, uuid4(), 1), sc.state(token), sc.command(command_id)[0]])
    for value in (None, True, str(command_id), 0):
        out = outcome(finish, sc.factory, generation, value, token, 1)
        R.record("F_finish_bad_command_arg_" + repr(value), [True, [False, False, False], "running"],
                 [out is not True, sc.state(token), sc.command(command_id)[0]], finish=out)
    with sc.factory.begin() as db:
        db.get(EtlDispatchWorker, 1).generation = uuid4()
    R.record("F_finish_worker_generation_changed_retains", [False, [False, False, False], "interrupted"],
             [finish(sc.factory, generation, command_id, token, 1), sc.state(token), sc.command(command_id)[0]])

    # A domain row/command pointing at a claim token whose claim belongs to another command.
    sc = Scenario("F_other_cmd")
    generation, cmd_x, token_x = sc.dispatch(execution_started=True)
    with sc.factory.begin() as db:
        now = clock(db)
        from common import AdminAuditLog
        audit = AdminAuditLog(actor_id="inert", action="etl.trigger", payload={})
        db.add(audit); db.flush()
        cmd_y = uuid4()
        db.add(EtlDispatchCommand(id=cmd_y, actor_id="inert", idempotency_key=uuid4(), source="oag", domain="audits",
            dry_run=False, generation=generation, claim_token=token_x, execution_started=True, status="running",
            version=2, created_at=now, updated_at=now, started_at=now, audit_id=audit.id))
        db.flush()
        row = db.get(EtlDispatchDomain, "audits")
        row.command_id = cmd_y
    R.record("F_finish_claim_of_other_command_not_released", [False, [False, False, False], "interrupted", "running"],
             [finish(sc.factory, generation, cmd_y, token_x, 1), sc.state(token_x), sc.command(cmd_y)[0],
              sc.command(cmd_x)[0]])


# --------------------------------- F2. migrated Batch 7 claims (migration SQL verbatim)
MIGRATION_INSERT = """INSERT INTO seeding_domain_claims(id,domain,kind,command_id,acquired_at)
        SELECT d.claim_token,d.domain,'dispatch',d.command_id,c.started_at
        FROM etl_dispatch_domains d JOIN etl_dispatch_commands c ON c.id=d.command_id
        WHERE d.command_id IS NOT NULL"""


@section("F2_migrated_batch7")
def _():
    for label, started, with_jobs in (("started_with_completed_cli_job", True, True),
                                       ("started_no_job", True, False),
                                       ("not_started", False, False)):
        sc = Scenario("F2_" + label)
        generation, command_id, token = sc.dispatch(execution_started=started, reserve_claim=False)
        job_id = None
        if with_jobs:
            # The Batch 7 CLI ran and committed its observation/effects (no seeding_claim_id: pre-seam).
            sc.scalar("SELECT 1")
            job_id = sc.job(token, meta={"dispatch_command_id": str(command_id), "dispatch_claim_token": str(token)})
            with sc.engine.begin() as conn:
                conn.execute(text("INSERT INTO inert_effects(label) VALUES ('batch7_effect')"))
        with sc.engine.begin() as conn:
            conn.execute(text(MIGRATION_INSERT))
        before = sc.state(token)
        result = finish(sc.factory, generation, command_id, token, 0)
        after = sc.state(token)
        cmd = sc.command(command_id)
        expected_retained = started  # Batch 7 execution_started => CLI may have run: uncertain
        R.record("F2_migrated_" + label + "_finish",
                 [False, [False, False, False], "interrupted"] if expected_retained else [True, [False, False, True], "failed"],
                 [result, after, cmd[0]], before=before, command=cmd, batch7_job=job_id,
                 repro="Batch7 running command (execution_started=%s) + migration e572 INSERT; finish(factory, G, cmd, token, 0) under the still-fresh Batch 7 generation" % started)
        if expected_retained and after and after[2]:
            R.record("F2_migrated_" + label + "_native_unblocked_after_release", "blocked",
                     "runs" if run() == 0 else "blocked", effects=sc.effects())
    # Control: a new-code worker registration interrupts migrated running commands and retains claims.
    sc = Scenario("F2_register")
    generation, command_id, token = sc.dispatch(execution_started=True, reserve_claim=False,
                                                lease=timedelta(seconds=1))
    with sc.engine.begin() as conn:
        conn.execute(text(MIGRATION_INSERT))
    time.sleep(1.2)
    new_gen = register_worker(sc.factory)
    R.record("F2_register_worker_interrupts_migrated_retains", ["interrupted", [False, False, False], False],
             [sc.command(command_id)[0], sc.state(token), finish(sc.factory, new_gen, command_id, token, 0)])
    R.record("F2_register_worker_claim_blocked", None, worker_claim(sc.factory, new_gen))


# --------------------------------- G. acknowledgement
@section("G_ack")
def _():
    sc = Scenario("G")
    e = enter_domain(sc.factory, "adv_r3_ack", False)
    ident = e.identity
    good = sc.job(ident, "adv_r3_ack")
    other_claim = sc.native_claim("adv_r3_y")
    other_job = sc.job(other_claim, "adv_r3_y")
    now_bad = {}
    from datetime import datetime, timezone
    t = datetime.now(timezone.utc)
    now_bad["other_domain_job"] = sc.job(ident, "adv_r3_y")
    now_bad["running_job"] = sc.job(ident, "adv_r3_ack", status=IngestionStatus.RUNNING, finished_at=None)
    now_bad["pending_job"] = sc.job(ident, "adv_r3_ack", status=IngestionStatus.PENDING)
    now_bad["completed_with_error_list"] = sc.job(ident, "adv_r3_ack", errors=["x"])
    now_bad["errors_null"] = sc.job(ident, "adv_r3_ack", errors=None)
    now_bad["no_finished_at"] = sc.job(ident, "adv_r3_ack", status=IngestionStatus.FAILED, finished_at=None)
    now_bad["started_before_acquire"] = sc.job(ident, "adv_r3_ack", started_at=t - timedelta(minutes=5))
    now_bad["finished_in_future"] = sc.job(ident, "adv_r3_ack", finished_at=t + timedelta(minutes=5))
    now_bad["finish_before_start"] = sc.job(ident, "adv_r3_ack", started_at=t, finished_at=t - timedelta(seconds=30))
    now_bad["meta_claim_uuid_obj_upper"] = sc.job(ident, "adv_r3_ack", meta={"seeding_claim_id": str(ident).upper()})
    now_bad["meta_null"] = sc.job(ident, "adv_r3_ack", meta=None)
    now_bad["refused_row_shape"] = sc.job(ident, "adv_r3_ack", status=IngestionStatus.FAILED, items_processed=0,
                                          items_created=0, meta={"ownership_refused": True}, errors=["not run"])
    now_bad["negative_items"] = sc.job(ident, "adv_r3_ack", items_processed=-1)
    for label, jid in list(now_bad.items()) + [("other_claims_job", other_job), ("true", True), ("str", str(good)),
                                                ("float", float(good)), ("none", None), ("zero", 0), ("neg", -1),
                                                ("huge", 2 ** 31), ("missing", 10 ** 6)]:
        R.record("G_ack_rejects_" + label, ["DomainOwnershipError", [True, False, False]],
                 [outcome(e.acknowledge, jid), sc.state(ident)])
    saved = e.entry
    e.entry = uuid4()
    R.record("G_ack_rejects_wrong_entry_nonce", ["DomainOwnershipError", [True, False, False]],
             [outcome(e.acknowledge, good), sc.state(ident)])
    e.entry = str(saved)
    R.record("G_ack_rejects_entry_as_str", ["DomainOwnershipError", [True, False, False]],
             [outcome(e.acknowledge, good), sc.state(ident)])
    e.entry = saved
    e.command_id = uuid4()
    R.record("G_ack_rejects_native_with_command_id", ["DomainOwnershipError", [True, False, False]],
             [outcome(e.acknowledge, good), sc.state(ident)])
    e.command_id = None
    R.record("G_ack_valid_releases_once", ["accepted", [True, True, True], good],
             [outcome(e.acknowledge, good), sc.state(ident), sc.claim(ident)["job_id"]])
    R.record("G_ack_twice_rejected", ["DomainOwnershipError", good], [outcome(e.acknowledge, good), sc.claim(ident)["job_id"]])
    e.close()
    with sc.engine.begin() as conn:  # harness: the RUNNING probe row would (by design) block the next native run
        conn.execute(text("UPDATE ingestion_jobs SET status='FAILED', finished_at=now() WHERE id=:i"), {"i": now_bad["running_job"]})
    R.record("G_native_after_release_runs", 0, run(["adv_r3_ack"]))

    # Ack after pg_terminate_backend of the lock backend.
    e = enter_domain(sc.factory, "adv_r3_ack", False)
    job = sc.job(e.identity, "adv_r3_ack")
    with admin.begin() as conn:
        killed = conn.scalar(text("SELECT pg_terminate_backend(:p)"), {"p": e.pid})
    time.sleep(0.2)
    out = outcome(e.acknowledge, job)
    R.record("G_ack_after_lock_backend_terminated_rejected", [True, True, [True, False, False]],
             [killed, out != "accepted", sc.state(e.identity)], exception=out)
    close_out = outcome(e.close)
    R.record("G_close_after_termination_does_not_release", [True, False, False], sc.state(e.identity), close=close_out)
    c = len(CALLS)
    R.record("G_lockloss_blocks_next_native", [1, c], [run(["adv_r3_ack"]), len(CALLS)])
    # Forged object copying the entry nonce from the DB after lock loss.
    retained = e.identity
    entry = sc.claim(retained)["entry_id"]
    f = DomainExecution(sc.factory, "adv_r3_ack", retained)
    f.open()
    f.entered, f.entry = True, entry
    out = outcome(f.acknowledge, job)
    f.close()
    R.record("G_forged_db_copied_entry_cannot_release_lockloss_retained_claim",
             ["DomainOwnershipError", [True, False, False]], [out, sc.state(retained)],
             repro="enter_domain(); job; pg_terminate_backend(lock pid); ack fails (retained); "
                   "f=DomainExecution(factory,d,claim_id); f.open(); f.entered=True; f.entry=<claim.entry_id from DB>; f.acknowledge(job)")
    # Same forgery against a never-acknowledged retained native whose job is terminal (crash after finalize).
    ident2 = uuid4(); entry2 = uuid4()
    with sc.factory.begin() as db:
        ok = reserve(db, "adv_r3_y2", ident2, entry=entry2)
    job2 = sc.job(ident2, "adv_r3_y2")
    f = DomainExecution(sc.factory, "adv_r3_y2", ident2)
    f.open(); f.entered = True
    f.entry = sc.claim(ident2)["entry_id"]
    out = outcome(f.acknowledge, job2)
    f.close()
    R.record("G_forged_db_copied_entry_cannot_release_retained_native",
             ["DomainOwnershipError", [True, False, False]], [out, sc.state(ident2)], reserved=ok)

    # Dispatch acknowledgement: mismatched dry-run job, wrong domain job, and finish coherence.
    sc = Scenario("G_dispatch")
    generation, command_id, token = sc.dispatch(execution_started=True)
    s = DomainExecution(sc.factory, "audits", token, command_id, generation)
    s.open()
    with dispatch_scope(s):
        enter_domain(sc.factory, "audits", False)
    tags = {"seeding_claim_id": str(token), "dispatch_command_id": str(command_id), "dispatch_claim_token": str(token)}
    wrong_dom = sc.job(token, "adv_r3_x", meta=tags)
    R.record("G_dispatch_ack_wrong_domain_job_rejected", ["DomainOwnershipError", [True, False, False]],
             [outcome(s.acknowledge, wrong_dom), sc.state(token)])
    dry_job = sc.job(token, "audits", dry_run=True, meta=tags)
    ack = outcome(s.acknowledge, dry_job)
    fin = finish(sc.factory, generation, command_id, token, 0)
    R.record("G_dispatch_dry_run_mismatch_never_completes", [False, "interrupted", False],
             [fin, sc.command(command_id)[0], sc.state(token)[2]], ack=ack, observations="2 tagged jobs")
    s.close()

    sc = Scenario("G_dispatch2")
    generation, command_id, token = sc.dispatch(execution_started=True)
    s = DomainExecution(sc.factory, "audits", token, command_id, generation)
    s.open()
    with dispatch_scope(s):
        enter_domain(sc.factory, "audits", False)
    tags = {"seeding_claim_id": str(token), "dispatch_command_id": str(command_id), "dispatch_claim_token": str(token)}
    dry_job = sc.job(token, "audits", dry_run=True, meta=tags)
    ack = outcome(s.acknowledge, dry_job)
    fin = finish(sc.factory, generation, command_id, token, 0)
    R.record("G_dispatch_single_dry_run_mismatch_job_not_completed", [False, "interrupted", False],
             [fin, sc.command(command_id)[0], sc.state(token)[2]], ack=ack)
    s.close()


# --------------------------------- H. native/native concurrency
@section("H_native_concurrency")
def _():
    sc = Scenario("H")
    for iteration in range(5):
        barrier = threading.Barrier(4)
        got, errs = [], []

        def contend():
            barrier.wait()
            try:
                got.append(enter_domain(sc.factory, "adv_r3_nn", False))
            except Exception as exc:  # noqa: BLE001
                errs.append(type(exc).__name__)
        threads = [threading.Thread(target=contend) for _ in range(4)]
        [t.start() for t in threads]
        [t.join(30) for t in threads]
        active = sc.scalar("SELECT count(*) FROM seeding_domain_claims WHERE domain='adv_r3_nn' AND released_at IS NULL")
        R.record(f"H_enter_domain_4_threads_one_owner_{iteration}", [1, 1], [len(got), active], errors=sorted(errs))
        for g in got:
            j = sc.job(g.identity, "adv_r3_nn")
            g.acknowledge(j)
            g.close()
    for iteration in range(5):
        barrier = threading.Barrier(6)
        wins = []

        def raw():
            barrier.wait()
            with sc.factory.begin() as db:
                wins.append(reserve(db, f"adv_r3_raw{iteration}", uuid4()))
        threads = [threading.Thread(target=raw) for _ in range(6)]
        [t.start() for t in threads]
        [t.join(30) for t in threads]
        R.record(f"H_reserve_6_threads_one_true_{iteration}", 1, wins.count(True))
    barrier = threading.Barrier(6)
    wins = []

    def raw2():
        barrier.wait()
        with sc.factory.begin() as db:
            wins.append(reserve(db, "adv_r3_raw0", uuid4()))
    threads = [threading.Thread(target=raw2) for _ in range(6)]
    [t.start() for t in threads]
    [t.join(30) for t in threads]
    R.record("H_reserve_against_retained_zero_winners", 0, wins.count(True))
    # Real CLI in 4 threads with an overlapping handler.
    for iteration in range(3):
        BEHAVIOR["adv_r3_nn"] = lambda session, s, ctx: (time.sleep(0.4), session.execute(text(
            "INSERT INTO inert_effects(label) VALUES ('adv_r3_nn')")), DomainRunResult(
            domain="adv_r3_nn", dry_run=ctx.dry_run, items_processed=1, items_created=1))[-1]
        before_eff, before_ref = sc.effects("adv_r3_nn"), sc.refused("adv_r3_nn")
        barrier = threading.Barrier(4)
        codes = []

        def cli_run():
            barrier.wait()
            codes.append(run(["adv_r3_nn"]))
        threads = [threading.Thread(target=cli_run) for _ in range(4)]
        [t.start() for t in threads]
        [t.join(60) for t in threads]
        BEHAVIOR.pop("adv_r3_nn", None)
        R.record(f"H_cli_4_threads_one_runs_{iteration}", [[0, 1, 1, 1], before_eff + 1, before_ref + 3, 0],
                 [sorted(codes), sc.effects("adv_r3_nn"), sc.refused("adv_r3_nn"),
                  sc.scalar("SELECT count(*) FROM seeding_domain_claims WHERE domain='adv_r3_nn' AND released_at IS NULL")])


# --------------------------------- I. refused rows: not observation, not unblocking
@section("I_refused_rows")
def _():
    sc = Scenario("I")
    retained = sc.native_claim("audits")
    running = sc.job(retained, "audits", status=IngestionStatus.RUNNING, finished_at=None)
    for _ in range(3):
        run()
    R.record("I_refused_rows_leave_running_job_and_claim",
             ["RUNNING", [True, False, False], 3],
             [sc.scalar("SELECT status::text FROM ingestion_jobs WHERE id=:i", i=running), sc.state(retained), sc.refused("audits")])
    gen = None
    with sc.factory.begin() as db:
        now = clock(db)
        db.add(EtlDispatchWorker(id=1, generation=uuid4(), ready=False, last_seen_at=now - timedelta(minutes=5),
                                 expires_at=now - timedelta(minutes=4)))
    gen = register_worker(sc.factory)
    from common import AdminAuditLog
    with sc.factory.begin() as db:
        now = clock(db)
        audit = AdminAuditLog(actor_id="inert", action="etl.trigger", payload={})
        db.add(audit); db.flush()
        db.add(EtlDispatchCommand(id=uuid4(), actor_id="inert", idempotency_key=uuid4(), source="oag", domain="audits",
            dry_run=False, generation=gen, status="queued", version=1, created_at=now, updated_at=now, audit_id=audit.id))
    R.record("I_worker_claim_blocked_despite_refused_rows", None, worker_claim(sc.factory, gen))
    with sc.engine.begin() as conn:  # operator finalises the stale RUNNING job; the claim is still retained
        conn.execute(text("UPDATE ingestion_jobs SET status='FAILED', finished_at=now() WHERE id=:i"), {"i": running})
    R.record("I_worker_claim_blocked_by_retained_claim_without_running_job", [None, [True, False, False]],
             [worker_claim(sc.factory, gen), sc.state(retained)])
    # Refused rows (with the running job made terminal by an operator) still never acknowledge the claim.
    refused_id = sc.scalar("SELECT max(id) FROM ingestion_jobs WHERE metadata->>'ownership_refused'='true'")
    e = DomainExecution(sc.factory, "audits", retained)
    e.open(); e.entered, e.entry = True, uuid4()
    R.record("I_refused_row_ack_rejected", ["DomainOwnershipError", [True, False, False]],
             [outcome(e.acknowledge, refused_id), sc.state(retained)])
    e.close()

    # Dispatch: a tagged refused row (adapter-style session) never completes a command.
    for entered in (False, True):
        sc = Scenario("I_dispatch_" + str(entered))
        generation, command_id, token = sc.dispatch(execution_started=True)
        if entered:
            s = DomainExecution(sc.factory, "audits", token, command_id, generation)
            s.open()
            with dispatch_scope(s):
                enter_domain(sc.factory, "audits", False)
            s.close()

        class Tagged(Session):
            pass

        @event.listens_for(Tagged, "before_flush")
        def tag(session, context, instances):
            for row in session.new:
                if row.__class__.__name__ == "IngestionJob":
                    row.meta = {**(row.meta or {}), "dispatch_command_id": str(command_id), "dispatch_claim_token": str(token)}
        cli.SessionLocal = sessionmaker(bind=sc.engine, class_=Tagged)
        bogus = DomainExecution(sc.factory, "audits", token, command_id, uuid4())
        code = scoped_run(sc, bogus)
        cli.SessionLocal = sc.factory
        tagged = sc.scalar("SELECT count(*) FROM ingestion_jobs WHERE metadata->>'dispatch_command_id'=:c", c=str(command_id))
        fin = finish(sc.factory, generation, command_id, token, 0)
        cmd = sc.command(command_id)
        R.record(f"I_tagged_refused_row_entered_{entered}_never_completes",
                 [1, 1, "interrupted" if entered else "failed", None, [True, False, False] if entered else [False, False, True]],
                 [code, tagged, cmd[0], cmd[3], sc.state(token)], finish=fin)


# --------------------------------- J. schema CHECK probes (raw SQL)
@section("J_schema_checks")
def _():
    sc = Scenario("J")
    generation, command_id, token = sc.dispatch(execution_started=True, reserve_claim=False)
    job = sc.job(uuid4(), "adv_r3_j")
    cmds = []
    from common import AdminAuditLog
    with sc.factory.begin() as db:
        now = clock(db)
        for _ in range(20):
            audit = AdminAuditLog(actor_id="inert", action="etl.trigger", payload={})
            db.add(audit); db.flush()
            cid = uuid4()
            db.add(EtlDispatchCommand(id=cid, actor_id="inert", idempotency_key=uuid4(), source="oag", domain="audits",
                dry_run=False, generation=generation, status="queued", version=1, created_at=now, updated_at=now,
                audit_id=audit.id))
            cmds.append(cid)
    it = iter(cmds)
    base = "now()"

    def probe(name, expect, **cols):
        cols.setdefault("id", uuid4())
        cols.setdefault("domain", "adv_r3_j_" + uuid4().hex[:8])
        cols.setdefault("acquired_at", "T0")
        names = list(cols)
        values = []
        params = {}
        for n in names:
            v = cols[n]
            if isinstance(v, str) and v.startswith("T") and v[1:].lstrip("+-").isdigit():
                values.append(f"(timestamptz '2026-10-09 00:00:00+00' + interval '{int(v[1:])} seconds')")
            else:
                params[n] = v
                values.append(":" + n)
        sql = f"INSERT INTO seeding_domain_claims({','.join(names)}) VALUES ({','.join(values)})"
        try:
            with sc.engine.begin() as conn:
                conn.execute(text(sql), params)
            got = "accepted"
            detail = None
        except (sa_exc.IntegrityError, sa_exc.DataError) as exc:
            got = "rejected"
            detail = getattr(getattr(exc.orig, "diag", None), "constraint_name", None) or type(exc.orig).__name__
        R.record("J_" + name, expect, got, constraint=detail)

    E = uuid4
    probe("native_without_entry", "rejected", kind="native")
    probe("native_with_command", "rejected", kind="native", command_id=next(it), entered_at="T0", entry_id=E())
    probe("dispatch_without_command", "rejected", kind="dispatch")
    probe("kind_other", "rejected", kind="other", command_id=next(it))
    probe("kind_other_no_command", "rejected", kind="Native", entered_at="T0", entry_id=E())
    probe("entered_without_entry_id", "rejected", kind="native", entered_at="T0")
    probe("entry_id_without_entered", "rejected", kind="dispatch", command_id=next(it), entry_id=E())
    probe("entered_before_acquired", "rejected", kind="native", entered_at="T-1", entry_id=E())
    probe("returned_without_job", "rejected", kind="native", entered_at="T0", entry_id=E(), returned_at="T1")
    probe("job_without_returned", "rejected", kind="native", entered_at="T0", entry_id=E(), job_id=job)
    probe("returned_before_acquired", "rejected", kind="native", acquired_at="T5", entered_at="T5", entry_id=E(), returned_at="T1", job_id=job)
    probe("released_before_returned", "rejected", kind="native", entered_at="T0", entry_id=E(), returned_at="T5", job_id=job, released_at="T1")
    probe("dispatch_returned_without_entry", "rejected", kind="dispatch", command_id=next(it), returned_at="T1", job_id=job)
    probe("returned_before_entered", "rejected", kind="dispatch", command_id=next(it), entered_at="T5", entry_id=E(), returned_at="T2", job_id=job)
    probe("native_released_without_return_unreconciled", "rejected", kind="native", entered_at="T0", entry_id=E(), released_at="T1")
    probe("dispatch_entered_released_without_return_unreconciled", "rejected", kind="dispatch", command_id=next(it), entered_at="T0", entry_id=E(), released_at="T1")
    probe("control_dispatch_never_entered_released", "accepted", kind="dispatch", command_id=next(it), released_at="T1")
    probe("dispatch_never_entered_released_before_acquired", "rejected", kind="dispatch", command_id=next(it), acquired_at="T5", released_at="T1")
    probe("reconciled_without_release", "rejected", kind="native", entered_at="T0", entry_id=E(), reconciled_by="op", reconciliation="why")
    probe("reconciled_by_without_text", "rejected", kind="native", entered_at="T0", entry_id=E(), released_at="T1", reconciled_by="op")
    probe("reconciliation_without_by", "rejected", kind="native", entered_at="T0", entry_id=E(), released_at="T1", reconciliation="why")
    probe("reconciled_by_empty", "rejected", kind="native", entered_at="T0", entry_id=E(), released_at="T1", reconciled_by="", reconciliation="why")
    probe("reconciled_by_65", "rejected", kind="native", entered_at="T0", entry_id=E(), released_at="T1", reconciled_by="o" * 65, reconciliation="why")
    probe("reconciliation_4001", "rejected", kind="native", entered_at="T0", entry_id=E(), released_at="T1", reconciled_by="op", reconciliation="w" * 4001)
    probe("reconciliation_empty", "rejected", kind="native", entered_at="T0", entry_id=E(), released_at="T1", reconciled_by="op", reconciliation="")
    probe("control_native_operator_reconciled_release", "accepted", kind="native", entered_at="T0", entry_id=E(), released_at="T1", reconciled_by="op", reconciliation="why")
    probe("control_native_returned_released", "accepted", kind="native", entered_at="T0", entry_id=E(), returned_at="T1", job_id=job, released_at="T1")
    probe("job_id_zero", "rejected", kind="native", entered_at="T0", entry_id=E(), returned_at="T1", job_id=0)
    probe("job_id_negative", "rejected", kind="native", entered_at="T0", entry_id=E(), returned_at="T1", job_id=-5)
    probe("domain_empty", "rejected", kind="native", entered_at="T0", entry_id=E(), domain="")
    probe("domain_101", "rejected", kind="native", entered_at="T0", entry_id=E(), domain="d" * 101)
    probe("info_reconciled_by_blank_space_accepted", "accepted", kind="native", entered_at="T0", entry_id=E(), released_at="T1", reconciled_by=" ", reconciliation=" ")
    dup_entry = E()
    probe("control_first_entry", "accepted", kind="native", entered_at="T0", entry_id=dup_entry, domain="adv_r3_j_dupe1")
    probe("duplicate_entry_id", "rejected", kind="native", entered_at="T0", entry_id=dup_entry, domain="adv_r3_j_dupe2")
    probe("control_active_domain", "accepted", kind="native", entered_at="T0", entry_id=E(), domain="adv_r3_j_active")
    probe("second_active_same_domain", "rejected", kind="native", entered_at="T0", entry_id=E(), domain="adv_r3_j_active")
    shared_cmd = next(it)
    probe("control_dispatch_claim_cmd", "accepted", kind="dispatch", command_id=shared_cmd, domain="adv_r3_j_c1", released_at="T1")
    probe("second_claim_same_command", "rejected", kind="dispatch", command_id=shared_cmd, domain="adv_r3_j_c2")
    probe("native_entered_null_kind_case", "rejected", kind="NATIVE", entered_at=None, entry_id=None)
    # UPDATE hostile transitions on a real entered/returned native row.
    ident = sc.native_claim("adv_r3_j_upd", entry=uuid4())
    for name, sql in (("upd_unenter_native", "UPDATE seeding_domain_claims SET entered_at=NULL, entry_id=NULL WHERE id=:i"),
                      ("upd_release_native_without_return", "UPDATE seeding_domain_claims SET released_at=now() WHERE id=:i"),
                      ("upd_kind_to_dispatch_no_cmd", "UPDATE seeding_domain_claims SET kind='dispatch' WHERE id=:i")):
        try:
            with sc.engine.begin() as conn:
                conn.execute(text(sql), {"i": ident})
            got = "accepted"
        except (sa_exc.IntegrityError, sa_exc.DataError):
            got = "rejected"
        R.record("J_" + name, "rejected", got)


s = R.summary()
dispose_all()
sys.exit(1 if s["failed"] else 0)
