"""Owned subprocess-only handlers; CLI and bootstrap entrypoints stay real."""
import os

if os.environ.get("BATCH9_BOOTSTRAP_INERT") == "true":
    try:
        import socket
        import time
        from datetime import datetime, timezone

        url = os.environ["DATABASE_URL"]
        assert "@127.0.0.1:55492/batch9-bootstrap-" in url
        original_connect = socket.socket.connect

        def local_only(sock, address):
            if not isinstance(address, tuple) or address[:2] != ("127.0.0.1", 55492):
                raise RuntimeError("External transport blocked by bootstrap fixture")
            return original_connect(sock, address)

        socket.socket.connect = local_only
        from sqlalchemy import text
        from database import SessionLocal
        from seeding.registries import REGISTRY, load_builtin_domains
        from seeding.types import DomainRunResult

        load_builtin_domains()
        import seeding.domains.national_budget as budget

        def marker(stage, context=None, settings=None):
            with SessionLocal.begin() as db:
                db.execute(text("INSERT INTO batch9_markers(pid, stage, job_id, live_fetch, dry_run) "
                                "VALUES (:pid,:stage,:job,:live,:dry)"),
                           {"pid": os.getpid(), "stage": stage,
                            "job": context.job_id if context else None,
                            "live": settings.live_pdf_fetch_enabled if settings else None,
                            "dry": context.dry_run if context else None})

        def mode():
            with SessionLocal() as db:
                return db.scalar(text("SELECT mode FROM batch9_control"))

        def await_release():
            deadline = time.monotonic() + 30
            while mode() != "normal":
                if time.monotonic() >= deadline:
                    raise RuntimeError("Fixture gate was not released")
                time.sleep(0.05)

        def inert_budget(session, settings, context):
            initial = mode()
            marker("entered", context, settings)
            if initial == "before":
                await_release()
            # Real destructive budget mutation, with inert rows and no provider.
            session.execute(text("DELETE FROM budget_lines"))
            session.execute(text("INSERT INTO batch9_effects(pid) VALUES (:pid)"), {"pid": os.getpid()})
            if initial == "failure":
                raise RuntimeError("Owned budget handler failed after destructive write")
            if initial == "afterwrite":
                marker("written", context, settings)
                await_release()
            if initial == "aftercommit":
                session.commit()
                marker("committed", context, settings)
                await_release()
            return DomainRunResult(domain="national_budget", dry_run=context.dry_run,
                                   items_processed=1, items_created=1,
                                   errors=["Owned returned error"] if initial == "errors" else [],
                                   metadata={"owned_fixture": True})

        REGISTRY._handlers.clear()
        REGISTRY.register("national_budget", inert_budget)
        budget.run = inert_budget  # pinned baseline imports this alias directly

        # Observe the real outer transaction's commit/ack gap without replacing it.
        if os.environ.get("BATCH9_BOOTSTRAP_COMMIT_GATE") == "true":
            from sqlalchemy import event
            from sqlalchemy.orm import Session

            @event.listens_for(Session, "after_commit")
            def pause_outer_commit(session):
                if session.info.pop("batch9_outer_bootstrap", False):
                    marker("outer_committed")
                    await_release()

            @event.listens_for(Session, "before_commit")
            def observe_outer_commit(session):
                from models import IngestionJob
                if any(isinstance(row, IngestionJob) and row.domain == "bootstrap_reference_data"
                       for row in session.new):
                    session.info["batch9_outer_bootstrap"] = True

    except BaseException:
        # Python otherwise proceeds after a sitecustomize failure, possibly live.
        import traceback
        traceback.print_exc()
        os._exit(70)
