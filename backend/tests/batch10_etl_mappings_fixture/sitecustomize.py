"""Inert handlers only; real CLI/session/ownership/observation code stays intact."""
import os
import time

if os.getenv("BATCH10_MAPPINGS_INERT") == "true":
    try:
        import socket
        original = socket.socket.connect
        def local_only(sock, address):
            if not isinstance(address, tuple) or address[:2] != ("127.0.0.1", 55522):
                raise RuntimeError("Unowned transport refused")
            return original(sock, address)
        socket.socket.connect = local_only
        from batch10_etl_mappings_fixture.owned_postgres import URL
        if os.environ["DATABASE_URL"] != URL:
            raise ValueError("Wrong owned fixture target")
        from sqlalchemy import text
        from database import SessionLocal
        from seeding.registries import REGISTRY, load_builtin_domains
        from seeding.types import DomainRunResult
        load_builtin_domains()
        REGISTRY._handlers.clear()
        def make_handler(domain):
            def wait_release():
                deadline = time.monotonic() + 40
                while time.monotonic() < deadline:
                    with SessionLocal() as db:
                        if db.scalar(text("SELECT mode FROM batch10_control WHERE domain=:d"), {"d": domain}) == "normal":
                            return
                    time.sleep(.03)
                raise RuntimeError("Fixture barrier deadline")
            def run(session, settings, context):
                with SessionLocal.begin() as db:
                    mode = db.scalar(text("SELECT mode FROM batch10_control WHERE domain=:d"), {"d": domain})
                    db.execute(text("INSERT INTO batch10_markers VALUES (:d,'entered',:job)"), {"d": domain, "job": context.job_id})
                if mode == "before":
                    wait_release()
                if mode == "failure":
                    raise RuntimeError("Inert private handler failure")
                session.execute(text("INSERT INTO batch10_effects VALUES (:d,:job)"), {"d": domain, "job": context.job_id})
                if mode == "after" and not context.dry_run:
                    session.commit()
                    with SessionLocal.begin() as db:
                        db.execute(text("INSERT INTO batch10_markers VALUES (:d,'committed',:job)"), {"d": domain, "job": context.job_id})
                    wait_release()
                return DomainRunResult(domain=domain, dry_run=context.dry_run, items_processed=1, items_created=1)
            return run
        for name in ("audits", "fiscal_summary", "counties_budget", "population"):
            REGISTRY.register(name, make_handler(name))
    except BaseException:
        os._exit(70)
