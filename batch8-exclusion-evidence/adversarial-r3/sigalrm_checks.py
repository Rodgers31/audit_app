"""Round-3 SIGALRM (per-domain / global budget) and re-entrancy checks, main thread, PostgreSQL."""
import os
import sys
import time
from uuid import uuid4

from common import (BEHAVIOR, CALLS, Recorder, Scenario, cli, dispose_all, environment, run, settings, text)
from seeding.exclusion import DomainOwnershipError, enter_domain
from seeding.types import DomainRunResult

os.environ["ADMIN_ETL_DISPATCH_ENABLED"] = "true"
import admin_etl_dispatch_adapter as adapter
from admin_etl_dispatch_worker import finish

R = Recorder("sigalrm")
environment("sigalrm")
LEAKED = []


def claims(sc, domain):
    with sc.engine.connect() as conn:
        return [list(r) for r in conn.execute(text(
            "SELECT entered_at IS NOT NULL, returned_at IS NOT NULL, released_at IS NOT NULL, job_id"
            " FROM seeding_domain_claims WHERE domain=:d ORDER BY acquired_at"), {"d": domain})]


def jobs(sc, domain):
    with sc.engine.connect() as conn:
        return [list(r) for r in conn.execute(text(
            "SELECT id, status::text, errors::text, metadata->>'seeding_claim_id' IS NOT NULL,"
            " coalesce(metadata->>'ownership_refused','') || coalesce(metadata->>'dropped_by_global_budget','')"
            " FROM ingestion_jobs WHERE domain=:d ORDER BY id"), {"d": domain})]


def sleeper(seconds=3, swallow=False, after=None):
    def behavior(session, s, ctx):
        try:
            time.sleep(seconds)
        except BaseException as exc:  # noqa: BLE001
            if not swallow:
                raise
            ctx_swallowed.append(type(exc).__name__)
        if after:
            after()
        session.execute(text("INSERT INTO inert_effects(label) VALUES ('sleeper')"))
        return DomainRunResult(domain="x", dry_run=ctx.dry_run, items_processed=1, items_created=1)
    return behavior


ctx_swallowed = []


def section(name):
    def wrap(fn):
        try:
            fn()
        except BaseException:
            R.harness_error(name)
        finally:
            for d in list(BEHAVIOR):
                BEHAVIOR.pop(d, None)
        return fn
    return wrap


@section("K1_domain_timeout")
def _():
    sc = Scenario("K1")
    BEHAVIOR["adv_r3_t1"] = sleeper(3)
    t = time.monotonic()
    code = run(["adv_r3_t1"], cfg=settings(domain_timeout_seconds=1))
    elapsed = time.monotonic() - t
    j = jobs(sc, "adv_r3_t1")
    c = claims(sc, "adv_r3_t1")
    R.record("K1_domain_timeout_fails_and_releases_once",
             [1, True, 1, "FAILED", True, [[True, True, True, j[0][0] if j else None]], 0],
             [code, elapsed < 2.5, len(j), j[0][1] if j else None, "budget" in (j[0][2] if j else ""), c, sc.effects()],
             elapsed=round(elapsed, 2), jobs=j)
    R.record("K1_next_run_after_timeout_owns_domain", 0, run(["adv_r3_t1"]))


@section("K2_global_budget")
def _():
    sc = Scenario("K2")
    BEHAVIOR["adv_r3_t1"] = sleeper(3)
    before = len(CALLS)
    t = time.monotonic()
    code = run(["adv_r3_t1", "adv_r3_t2"], cfg=settings(total_timeout_seconds=1))
    elapsed = time.monotonic() - t
    j1, j2 = jobs(sc, "adv_r3_t1"), jobs(sc, "adv_r3_t2")
    R.record("K2_global_stop_releases_inflight_once_and_records_drop",
             [1, True, [["FAILED", '["stopped: global seed budget exhausted"]', True]],
              [[True, True, True, j1[0][0] if j1 else None]], [["FAILED", False, "true"]], [], ["adv_r3_t1"]],
             [code, elapsed < 2.5, [x[1:4] for x in j1], claims(sc, "adv_r3_t1"),
              [[x[1], x[3], x[4]] for x in j2], claims(sc, "adv_r3_t2"), [d for d, _ in CALLS[before:]]],
             elapsed=round(elapsed, 2))
    # Global budget exhausted BEFORE the next domain starts (swallowing handler returns late).
    BEHAVIOR["adv_r3_t1"] = sleeper(3, swallow=True)
    sc = Scenario("K2b")
    ctx_swallowed.clear()
    code = run(["adv_r3_t1", "adv_r3_t2"], cfg=settings(total_timeout_seconds=1))
    j1, j2 = jobs(sc, "adv_r3_t1"), jobs(sc, "adv_r3_t2")
    R.record("K2b_global_swallowed_timeout_inflight_released_next_dropped",
             [1, ["DomainTimeoutError"], [["COMPLETED", True]], [[True, True, True, j1[0][0] if j1 else None]],
              [["FAILED", "true"]], []],
             [code, ctx_swallowed[:], [[x[1], x[3]] for x in j1], claims(sc, "adv_r3_t1"),
              [[x[1], x[4]] for x in j2], claims(sc, "adv_r3_t2")])


@section("K3_swallow")
def _():
    sc = Scenario("K3")
    ctx_swallowed.clear()
    BEHAVIOR["adv_r3_t1"] = sleeper(3, swallow=True)
    code = run(["adv_r3_t1"], cfg=settings(domain_timeout_seconds=1))
    j = jobs(sc, "adv_r3_t1")
    R.record("K3_handler_swallowing_timeout_returns_and_releases_once",
             [0, ["DomainTimeoutError"], ["COMPLETED"], [[True, True, True, j[0][0] if j else None]], 1],
             [code, ctx_swallowed[:], [x[1] for x in j], claims(sc, "adv_r3_t1"), sc.effects()],
             note="handler returned synchronously after swallowing; release follows the return")

    def raise_after():
        raise RuntimeError("after swallow")
    ctx_swallowed.clear()
    BEHAVIOR["adv_r3_t2"] = sleeper(3, swallow=True, after=raise_after)
    code = run(["adv_r3_t2"], cfg=settings(domain_timeout_seconds=1))
    j = jobs(sc, "adv_r3_t2")
    R.record("K3b_swallow_then_raise_fails_and_releases_once",
             [1, ["FAILED"], [[True, True, True, j[0][0] if j else None]]],
             [code, [x[1] for x in j], claims(sc, "adv_r3_t2")])


@section("K4_raise_ownership_error")
def _():
    sc = Scenario("K4")

    def boom(session, s, ctx):
        raise DomainOwnershipError("handler-raised ownership error")
    BEHAVIOR["adv_r3_t1"] = boom
    code = run(["adv_r3_t1"], cfg=settings(domain_timeout_seconds=1))
    j = jobs(sc, "adv_r3_t1")
    R.record("K4_handler_raising_DomainOwnershipError_fails_and_releases_once",
             [1, ["FAILED"], [[True, True, True, j[0][0] if j else None]], 0],
             [code, [x[1] for x in j], claims(sc, "adv_r3_t1"), sc.refused()])


@section("K5_reentrant_enter")
def _():
    sc = Scenario("K5")
    attempts = []

    def reenter_own(propagate):
        def behavior(session, s, ctx):
            try:
                LEAKED.append(enter_domain(cli.SessionLocal, "adv_r3_t1", ctx.dry_run))
                attempts.append("entered")
            except DomainOwnershipError:
                attempts.append("DomainOwnershipError")
                if propagate:
                    raise
            return DomainRunResult(domain="adv_r3_t1", dry_run=ctx.dry_run)
        return behavior
    BEHAVIOR["adv_r3_t1"] = reenter_own(True)
    code = run(["adv_r3_t1"], cfg=settings(domain_timeout_seconds=5))
    j = jobs(sc, "adv_r3_t1")
    R.record("K5_reentrant_enter_own_domain_refused_outer_fails_releases_once",
             [1, ["DomainOwnershipError"], ["FAILED"], [[True, True, True, j[0][0] if j else None]]],
             [code, attempts[:], [x[1] for x in j], claims(sc, "adv_r3_t1")])
    attempts.clear()
    BEHAVIOR["adv_r3_t1"] = reenter_own(False)
    code = run(["adv_r3_t1"], cfg=settings(domain_timeout_seconds=5))
    j = jobs(sc, "adv_r3_t1")
    R.record("K5b_reentrant_enter_own_domain_caught_outer_completes",
             [0, ["DomainOwnershipError"], 2, [True, True, True]],
             [code, attempts[:], len(claims(sc, "adv_r3_t1")), claims(sc, "adv_r3_t1")[-1][:3]])

    # Re-entrant enter for ANOTHER domain from inside a native handler.
    attempts.clear()

    def reenter_other(session, s, ctx):
        nested = enter_domain(cli.SessionLocal, "adv_r3_re", ctx.dry_run)
        LEAKED.append(nested)
        attempts.append("entered_other")
        return DomainRunResult(domain="adv_r3_t2", dry_run=ctx.dry_run)
    BEHAVIOR["adv_r3_t2"] = reenter_other
    code = run(["adv_r3_t2"], cfg=settings(domain_timeout_seconds=5))
    R.record("K5c_reentrant_enter_other_domain_outer_released_nested_retained",
             [0, ["entered_other"], [[True, True, True]], [[True, False, False, None]]],
             [code, attempts[:], [c[:3] for c in claims(sc, "adv_r3_t2")], claims(sc, "adv_r3_re")],
             note="nested native ownership taken by a handler is never acknowledged: retained (fail-closed strand)")
    for leaked in LEAKED:
        leaked.close()
    LEAKED.clear()
    R.record("K5d_nested_retained_claim_blocks_later_run", [1, 1], [run(["adv_r3_re"]), sc.refused("adv_r3_re")])


@section("K6_base_exception_escape")
def _():
    sc = Scenario("K6")

    def interrupt(session, s, ctx):
        raise KeyboardInterrupt()
    BEHAVIOR["adv_r3_t1"] = interrupt
    try:
        code = run(["adv_r3_t1"])
    except KeyboardInterrupt:
        code = "KeyboardInterrupt"
    j = jobs(sc, "adv_r3_t1")
    R.record("K6_keyboardinterrupt_escapes_claim_retained",
             ["KeyboardInterrupt", ["RUNNING"], [[True, False, False, None]]],
             [code, [x[1] for x in j], claims(sc, "adv_r3_t1")])
    BEHAVIOR.pop("adv_r3_t1")
    R.record("K6b_retained_after_escape_blocks_next", 1, run(["adv_r3_t1"]))


@section("K7_dispatch_timeouts")
def _():
    for label, env in (("domain", {"SEED_DOMAIN_TIMEOUT_SECONDS": "1", "SEED_TOTAL_TIMEOUT_SECONDS": "0"}),
                       ("global", {"SEED_DOMAIN_TIMEOUT_SECONDS": "600", "SEED_TOTAL_TIMEOUT_SECONDS": "1"})):
        sc = Scenario("K7_" + label)
        generation, command_id, token = sc.dispatch(execution_started=False)
        BEHAVIOR["audits"] = sleeper(3)
        os.environ.update(env)
        t = time.monotonic()
        try:
            code = adapter.execute(sc.factory, sc.engine, command_id, token, generation)
        finally:
            for k in env:
                os.environ.pop(k, None)
        elapsed = time.monotonic() - t
        j = jobs(sc, "audits")
        st_before = claims(sc, "audits")
        fin = finish(sc.factory, generation, command_id, token, code)
        with sc.engine.connect() as conn:
            cmd = list(conn.execute(text("SELECT status, job_id FROM etl_dispatch_commands WHERE id=:i"), {"i": command_id}).one())
        R.record("K7_dispatch_" + label + "_timeout_acknowledged_then_finish_releases_once",
                 [1, True, ["FAILED"], [[True, True, False, j[0][0] if j else None]], True, ["failed", j[0][0] if j else None],
                  [[True, True, True, j[0][0] if j else None]]],
                 [code, elapsed < 2.5, [x[1] for x in j], st_before, fin, cmd, claims(sc, "audits")],
                 elapsed=round(elapsed, 2))
        R.record("K7_dispatch_" + label + "_finish_twice_rejected", False,
                 finish(sc.factory, generation, command_id, token, code))


@section("K8_dispatch_reentrant")
def _():
    sc = Scenario("K8")
    generation, command_id, token = sc.dispatch(execution_started=False)
    attempts = []

    def behavior(session, s, ctx):
        for d in ("audits", "adv_r3_re"):
            try:
                LEAKED.append(enter_domain(cli.SessionLocal, d, ctx.dry_run))
                attempts.append(d + ":entered")
            except DomainOwnershipError:
                attempts.append(d + ":refused")
        raise DomainOwnershipError("propagate")
    BEHAVIOR["audits"] = behavior
    code = adapter.execute(sc.factory, sc.engine, command_id, token, generation)
    j = jobs(sc, "audits")
    st = claims(sc, "audits")
    fin = finish(sc.factory, generation, command_id, token, code)
    R.record("K8_dispatch_handler_reentry_refused_failed_then_released_once",
             [1, ["audits:refused", "adv_r3_re:refused"], ["FAILED"], [[True, True, False, j[0][0] if j else None]],
              True, [[True, True, True, j[0][0] if j else None]], []],
             [code, attempts, [x[1] for x in j], st, fin, claims(sc, "audits"), claims(sc, "adv_r3_re")])
    for leaked in LEAKED:
        leaked.close()
    LEAKED.clear()


s = R.summary()
dispose_all()
sys.exit(1 if s["failed"] else 0)
