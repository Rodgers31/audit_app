"""Explicit owned-process rehearsal seam; never add this directory to production."""
import os

try:
    from urllib.parse import urlsplit
    import socket
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    parsed = urlsplit(os.environ["DATABASE_URL"])
    if (os.environ.get("BATCH12_INERT_PROCESS") != "true" or
            parsed.scheme != "postgresql+psycopg2" or parsed.hostname != "127.0.0.1" or
            parsed.port not in (55496, 55560) or parsed.username != "postgres" or parsed.password is not None or
            parsed.query or parsed.fragment or
            parsed.path != "/" + os.environ["BATCH12_EXPECTED_DATABASE"] or
            not parsed.path.startswith("/batch9-reconciliation-") or
            os.environ.get("PYTHON_DOTENV_DISABLED") != "1"):
        raise RuntimeError("Owned fixture identity required")

    engine = create_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        with engine.connect() as connection:
            identity = connection.execute(text("SELECT current_database(), current_user, system_identifier::text FROM pg_control_system()")).one()
            nonce = connection.scalar(text("SELECT nonce FROM batch12_control"))
            if (tuple(identity) != (os.environ["BATCH12_EXPECTED_DATABASE"], "postgres", os.environ["BATCH12_EXPECTED_SYSTEM_ID"]) or
                    nonce != os.environ["BATCH12_EXPECTED_NONCE"]):
                raise RuntimeError("Owned fixture census mismatch")
    finally:
        engine.dispose()

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def permitted(address):
        return isinstance(address, tuple) and address[:2] == ("127.0.0.1", parsed.port)

    def local_connect(sock, address):
        if not permitted(address):
            raise RuntimeError("Fixture transport unavailable")
        return original_connect(sock, address)

    def local_connect_ex(sock, address):
        if not permitted(address):
            raise RuntimeError("Fixture transport unavailable")
        return original_connect_ex(sock, address)

    socket.socket.connect = local_connect
    socket.socket.connect_ex = local_connect_ex
    from database import SessionLocal
    from seeding.registries import REGISTRY, load_builtin_domains
    from seeding.types import DomainRunResult
    import json
    import subprocess
    import sys

    # Measure the real adapter's kernel return code without replacing its
    # launch arguments, process, native CLI or worker completion decision.
    original_popen = subprocess.Popen

    class ObservedPopen(original_popen):
        def poll(self):
            result = super().poll()
            args = self.args
            if (result is not None and isinstance(args, list) and len(args) == 6
                    and args[1:3] == ["-m", "admin_etl_dispatch_adapter"]
                    and not getattr(self, "batch12_exit_recorded", False)):
                with SessionLocal.begin() as observation:
                    observation.execute(text("INSERT INTO batch12_process_exit(pid, exit_code, observer_pid) VALUES (:pid, :code, :parent)"),
                                        {"pid": self.pid, "code": result, "parent": os.getpid()})
                self.batch12_exit_recorded = True
            return result

    subprocess.Popen = ObservedPopen

    load_builtin_domains()
    REGISTRY._handlers.clear()

    def inert_audits(session, settings, context):
        custody = {"ppid": os.getppid(), "pgid": os.getpgid(0), "uid": os.getuid(),
                   "argv": sys.argv, "optimized": sys.flags.optimize,
                   "birth": subprocess.check_output(["ps", "-p", str(os.getpid()), "-o", "lstart="], text=True).strip()}
        with SessionLocal.begin() as observation:
            mode = observation.scalar(text("SELECT mode FROM batch12_control"))
            observation.execute(text("INSERT INTO batch12_markers(job_id, pid, custody) VALUES (:job, :pid, CAST(:custody AS jsonb))"),
                                {"job": context.job_id, "pid": os.getpid(), "custody": json.dumps(custody)})
        if mode == "failure":
            raise RuntimeError("fixture-private-error")
        if mode != "normal":
            raise RuntimeError("Unknown owned fixture mode")
        session.execute(text("INSERT INTO batch12_effects(job_id) VALUES (:job)"), {"job": context.job_id})
        return DomainRunResult(domain="audits", dry_run=context.dry_run, items_processed=1, items_created=1)

    REGISTRY.register("audits", inert_audits)
except BaseException:
    # Python normally continues after a failed sitecustomize import. Refuse the
    # entire process before product entry, including under python -O.
    os._exit(70)
