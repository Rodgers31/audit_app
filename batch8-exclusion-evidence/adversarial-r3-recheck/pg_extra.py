"""Round-3 follow-ups: forged DB-copied entry on a real dispatch after lock loss; job-insert failure;
non-UTC session TimeZone controls; dry-run dispatch control."""
import os
import sys
from uuid import uuid4

from common import (BEHAVIOR, CALLS, Recorder, Scenario, admin, cli, dispose_all, environment, outcome, run,
                    text, URL, ENGINES)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from seeding import exclusion
from seeding.exclusion import DomainExecution
from seeding.types import DomainRunResult

os.environ["ADMIN_ETL_DISPATCH_ENABLED"] = "true"
import admin_etl_dispatch_adapter as adapter
from admin_etl_dispatch_worker import finish

R = Recorder("pg-extra")
environment("pg-extra")


def kill_own_lock(session, s, ctx):
    scope = exclusion._dispatch_scope.get()  # harness reads the adapter's own scope pid only
    with admin.begin() as conn:
        conn.execute(text("SELECT pg_terminate_backend(:p)"), {"p": scope.pid})
    session.execute(text("INSERT INTO inert_effects(label) VALUES ('audits')"))
    return DomainRunResult(domain="audits", dry_run=ctx.dry_run, items_processed=1, items_created=1)


def claim_state(sc, token):
    return sc.state(token)


for forge in (False, True):
    try:
        sc = Scenario("X1_" + str(forge))
        generation, command_id, token = sc.dispatch(execution_started=False)
        BEHAVIOR["audits"] = kill_own_lock
        code = adapter.execute(sc.factory, sc.engine, command_id, token, generation)
        BEHAVIOR.pop("audits", None)
        after_cli = sc.state(token)
        job_id = sc.scalar("SELECT id FROM ingestion_jobs WHERE metadata->>'dispatch_command_id'=:c", c=str(command_id))
        ack = None
        if forge:
            f = DomainExecution(sc.factory, "audits", token, command_id, generation)
            f.open()
            f.entered = True
            f.entry = sc.claim(token)["entry_id"]
            ack = outcome(f.acknowledge, job_id)
            f.close()
        fin = finish(sc.factory, generation, command_id, token, code)
        R.record("X1_dispatch_lockloss_" + ("forged_db_entry_ack" if forge else "control_no_forgery"),
                 [1, 1, [True, False, False], False, "interrupted", [True, False, False]],
                 [code, sc.effects(), after_cli, fin, sc.command(command_id)[0], sc.state(token)],
                 forged_ack=ack, command=sc.command(command_id),
                 repro=None if not forge else "adapter.execute with a handler that terminates the scope's lock backend -> CLI ack fails, claim entered/unreturned; "
                       "f=DomainExecution(factory,'audits',token,cmd,gen); f.open(); f.entered=True; f.entry=<claim.entry_id from DB>; f.acknowledge(job); finish(...,exit_code)")
    except Exception:
        R.harness_error("X1_" + str(forge))
        BEHAVIOR.pop("audits", None)

# X2: the RUNNING-observation insert fails (owned-schema trigger); no handler can start.
try:
    sc = Scenario("X2")
    with sc.engine.begin() as conn:
        conn.execute(text("""CREATE FUNCTION refuse_running() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.domain='adv_r3_x' AND NEW.status::text='RUNNING' THEN RAISE EXCEPTION 'harness refusal'; END IF;
            RETURN NEW; END $$"""))
        conn.execute(text("CREATE TRIGGER refuse_running BEFORE INSERT ON ingestion_jobs FOR EACH ROW EXECUTE FUNCTION refuse_running()"))
    before = len(CALLS)
    code = run(["adv_r3_x"])
    with sc.engine.connect() as conn:
        rows = [list(r) for r in conn.execute(text(
            "SELECT entered_at IS NOT NULL, returned_at IS NOT NULL, released_at IS NOT NULL FROM seeding_domain_claims WHERE domain='adv_r3_x'"))]
    R.record("X2_job_insert_failure_no_handler_claim_retained", [1, before, [[True, False, False]], 0, 0],
             [code, len(CALLS), rows, sc.refused("adv_r3_x"), sc.scalar("SELECT count(*) FROM ingestion_jobs WHERE domain='adv_r3_x'")],
             note="design-consistent fail-closed strand: no handler ran, yet the native claim stays retained and no ingestion_jobs row records the attempt")
except Exception:
    R.harness_error("X2")

# X3: non-UTC session TimeZone must not strand legitimate native/dispatch runs.
for tz in ("Pacific/Kiritimati", "America/Adak"):
    try:
        sc = Scenario("X3_" + tz.replace("/", "_"))
        tz_engine = create_engine(URL, connect_args={"options": f"-csearch_path={sc.schema} -ctimezone={tz}"}, poolclass=__import__("sqlalchemy.pool", fromlist=["NullPool"]).NullPool)
        ENGINES.append(tz_engine)
        tz_factory = sessionmaker(bind=tz_engine)
        cli.SessionLocal = tz_factory
        code = run(["adv_r3_y"])
        with tz_engine.connect() as conn:
            rows = [list(r) for r in conn.execute(text(
                "SELECT entered_at IS NOT NULL, returned_at IS NOT NULL, released_at IS NOT NULL FROM seeding_domain_claims WHERE domain='adv_r3_y'"))]
            server_tz = conn.scalar(text("SHOW TimeZone"))
        R.record("X3_native_non_utc_timezone_releases_" + tz, [0, [[True, True, True]], tz], [code, rows, server_tz])
        sc.factory = tz_factory
        sc.engine = tz_engine
        generation, command_id, token = sc.dispatch(execution_started=False)
        code = adapter.execute(tz_factory, tz_engine, command_id, token, generation)
        fin = finish(tz_factory, generation, command_id, token, code)
        R.record("X3_dispatch_non_utc_timezone_completes_" + tz, [0, True, "completed", [True, True, True]],
                 [code, fin, sc.command(command_id)[0], sc.state(token)])
    except Exception:
        R.harness_error("X3_" + tz)

# X4: dry-run dispatch positive control.
try:
    sc = Scenario("X4")
    generation, command_id, token = sc.dispatch(execution_started=False, dry_run=True)
    code = adapter.execute(sc.factory, sc.engine, command_id, token, generation)
    fin = finish(sc.factory, generation, command_id, token, code)
    R.record("X4_dry_run_dispatch_completes_and_rolls_back", [0, 0, True, "completed", [True, True, True]],
             [code, sc.effects(), fin, sc.command(command_id)[0], sc.state(token)])
except Exception:
    R.harness_error("X4")

s = R.summary()
dispose_all()
sys.exit(1 if s["failed"] else 0)
