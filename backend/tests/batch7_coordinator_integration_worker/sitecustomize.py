"""Subprocess-only inert domain; actual dedicated/native runner stays unchanged."""
import os
import time

if os.environ.get("BATCH7_COORDINATOR_INERT_WORKER") == "true":
    try:
        import socket
        from tests.ci_browser_database import browser_database_port
        database_port = browser_database_port(55483)
        original_connect = socket.socket.connect

        def local_only(sock, address):
            if not isinstance(address, tuple) or address[:2] != ("127.0.0.1", database_port):
                raise RuntimeError("External transport blocked in coordinator worker fixture")
            return original_connect(sock, address)

        socket.socket.connect = local_only
        assert os.environ["DATABASE_URL"] == f"postgresql+psycopg2://batch7_coordinator:batch7-inert-coordinator-local@127.0.0.1:{database_port}/batch7_coordinator"
        from sqlalchemy import text
        from database import SessionLocal
        from seeding.registries import REGISTRY, load_builtin_domains
        from seeding.types import DomainRunResult

        load_builtin_domains()
        REGISTRY._handlers.clear()

        def mode():
            with SessionLocal() as observation:
                return observation.scalar(text("SELECT mode FROM batch7_coordinator_control"))

        def inert_audits(session, settings, context):
            selected = mode()
            with SessionLocal.begin() as observation:
                observation.execute(text("INSERT INTO batch7_coordinator_markers(stage,job_id) VALUES ('entered',:job)"), {"job": context.job_id})
            while selected == "before" and mode() == "before":
                time.sleep(0.05)
            if selected == "failure":
                raise RuntimeError("Inert coordinator domain failure")
            session.execute(text("INSERT INTO batch7_coordinator_effects(job_id) VALUES (:job)"), {"job": context.job_id})
            if selected == "after" and not context.dry_run:
                session.commit()
                with SessionLocal.begin() as observation:
                    observation.execute(text("INSERT INTO batch7_coordinator_markers(stage,job_id) VALUES ('committed',:job)"), {"job": context.job_id})
                while mode() == "after":
                    time.sleep(0.05)
            return DomainRunResult(domain="audits", dry_run=context.dry_run, items_processed=1, items_created=1)

        REGISTRY.register("audits", inert_audits)
    except BaseException:
        # Python ordinarily suppresses a failed sitecustomize import; fail closed.
        os._exit(70)
