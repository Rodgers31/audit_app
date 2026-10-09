"""Explicit inert subprocess registry; never part of product PYTHONPATH."""
import os

if os.environ.get("BATCH9_NATIVE_READINESS_INERT_PROCESS") == "true":
    try:
        import socket
        from urllib.parse import urlsplit

        urls = (
            "postgresql+psycopg2://batch9_readiness:batch9-inert-local@127.0.0.1:55495/batch9_native_readiness",
            "postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55485/batch7_etl_worker",
        )
        assert os.environ["DATABASE_URL"] in urls
        target = urlsplit(os.environ["DATABASE_URL"])
        original_connect = socket.socket.connect

        def local_only(sock, address):
            if not isinstance(address, tuple) or address[:2] != ("127.0.0.1", target.port):
                raise RuntimeError("External transport blocked in inert fixture")
            return original_connect(sock, address)

        socket.socket.connect = local_only
        from sqlalchemy import text
        from database import SessionLocal
        from seeding.registries import REGISTRY, load_builtin_domains
        from seeding.types import DomainRunResult

        # Same accepted process-fixture pattern: load actual domains first, then
        # replace only their handler registry. The real CLI is never replaced.
        load_builtin_domains()
        REGISTRY._handlers.clear()

        def inert_audits(session, settings, context):
            with SessionLocal.begin() as observation:
                observation.execute(text("INSERT INTO batch9_readiness_markers VALUES ('entered')"))
            session.execute(text("INSERT INTO batch9_readiness_effects VALUES (1)"))
            return DomainRunResult(domain="audits", dry_run=context.dry_run, items_created=1)

        REGISTRY.register("audits", inert_audits)
    except BaseException:
        # sitecustomize exceptions otherwise let Python continue into real work.
        os._exit(70)
