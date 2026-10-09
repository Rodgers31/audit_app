"""Explicit subprocess-only inert registry. Never part of product PYTHONPATH."""
import os
import time
from urllib.parse import urlsplit

if os.environ.get("BATCH9_RECONCILIATION_INERT_PROCESS") == "true":
    try:
        import socket
        # Fail any source/provider fetch; only the owned PostgreSQL socket is allowed.
        original_connect = socket.socket.connect
        parsed = urlsplit(os.environ["DATABASE_URL"])
        assert (parsed.scheme == "postgresql+psycopg2" and parsed.hostname == "127.0.0.1" and
                parsed.port is not None and parsed.path.startswith(("/batch9-reconciliation-", "/batch9-review-592-"))
                and not parsed.query and not parsed.fragment)
        def local_only(sock, address):
            if not isinstance(address, tuple) or address[:2] != ("127.0.0.1", parsed.port):
                raise RuntimeError("External transport blocked in inert fixture")
            return original_connect(sock, address)
        socket.socket.connect = local_only
        from sqlalchemy import text
        from database import SessionLocal
        from seeding.registries import REGISTRY, load_builtin_domains
        from seeding.types import DomainRunResult

        load_builtin_domains()
        # Import the actual native domain/scope first, then register one inert domain
        # for this isolated process. run_seed_command remains completely unchanged.
        REGISTRY._handlers.clear()

        def await_release():
            while True:
                with SessionLocal() as observation:
                    if observation.scalar(text("SELECT mode FROM batch9_control")) == "normal":
                        return
                time.sleep(0.05)

        def inert_audits(session, settings, context):
            with SessionLocal.begin() as observation:
                mode = observation.scalar(text("SELECT mode FROM batch9_control"))
                observation.execute(text("INSERT INTO batch9_markers(stage,job_id) VALUES ('entered',:job)"), {"job": context.job_id})
            if mode == "before":
                await_release()
            if mode == "failure":
                raise RuntimeError("Inert domain failure")
            session.execute(text("INSERT INTO batch9_effects(job_id) VALUES (:job)"), {"job": context.job_id})
            if mode == "after" and not context.dry_run:
                session.commit()
                with SessionLocal.begin() as observation:
                    observation.execute(text("INSERT INTO batch9_markers(stage,job_id) VALUES ('committed',:job)"), {"job": context.job_id})
                await_release()
            return DomainRunResult(domain="audits", dry_run=context.dry_run, items_processed=1, items_created=1)

        REGISTRY.register("audits", inert_audits)
    except BaseException:
        # sitecustomize errors otherwise let Python continue with real domains.
        os._exit(70)
