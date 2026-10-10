"""Fail closed before application imports; only fixture writers are inert."""
import os

if os.environ.get("BATCH11_BOOTSTRAP_INERT") == "1":
    try:
        import socket
        import sys
        from sqlalchemy.engine import make_url

        target = make_url(os.environ["DATABASE_URL"])
        if target.drivername == "sqlite":
            if not target.database or not os.path.basename(target.database).startswith(
                "batch11-bootstrap-"
            ):
                raise RuntimeError("Unowned SQLite target")
        elif not (
            target.host == "127.0.0.1"
            and target.database.startswith("batch11-bootstrap-")
            and target.username == "batch11_bootstrap"
            and target.password == "inert-local"
        ):
            raise RuntimeError("Unowned PostgreSQL target")
        connect = socket.socket.connect

        def local_only(sock, address):
            if not isinstance(address, tuple) or address[:2] != (
                "127.0.0.1",
                target.port,
            ):
                raise RuntimeError("Transport blocked by readiness fixture")
            return connect(sock, address)

        socket.socket.connect = local_only
        if target.drivername == "sqlite":
            from sqlalchemy.dialects.postgresql import JSONB
            from sqlalchemy.ext.compiler import compiles

            @compiles(JSONB, "sqlite")
            def sqlite_json(element, compiler, **kwargs):
                return "TEXT"

        from seeding.registries import REGISTRY, load_builtin_domains
        from seeding.types import DomainRunResult

        load_builtin_domains()

        def inert_budget(session, settings, context):
            return DomainRunResult(domain="national_budget", dry_run=context.dry_run)

        def inert_audits(session, settings, context):
            print("WRITER_ENTERED", flush=True)
            if sys.stdin.readline().strip() != "complete":
                raise RuntimeError("Owned writer barrier was not released")
            return DomainRunResult(domain="audits", dry_run=context.dry_run)

        REGISTRY._handlers.clear()
        REGISTRY.register("national_budget", inert_budget)
        REGISTRY.register("audits", inert_audits)
    except BaseException:
        import traceback

        traceback.print_exc()
        os._exit(70)
