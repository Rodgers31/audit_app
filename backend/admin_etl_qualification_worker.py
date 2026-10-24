"""One finite inline native invocation under the separate stdlib watchdog."""
import json
import os
import signal
import sys
import threading
import time

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from admin_etl_qualification import QualificationRefused, qualification
from admin_etl_dispatch import enabled
from admin_etl_dispatch_worker import (
    claim, close_readiness, finish, heartbeat, register_worker, retire_inactive_readiness,
)

QUEUE_SECONDS = 50


def bounded_engine(url):
    """Three connections: continuity lock, handler/finalizer and heartbeat."""
    engine = create_engine(url, pool_size=3, max_overflow=0, pool_timeout=2,
                           connect_args={"connect_timeout": 3})
    if engine.dialect.name != "postgresql":
        engine.dispose()
        raise QualificationRefused("PostgreSQL qualification required")

    @event.listens_for(engine, "begin")
    def transaction_limits(connection):
        connection.exec_driver_sql("SET LOCAL statement_timeout='2s'")
        connection.exec_driver_sql("SET LOCAL lock_timeout='500ms'")
        connection.exec_driver_sql("SET LOCAL idle_in_transaction_session_timeout='5s'")
        connection.exec_driver_sql("SET LOCAL max_parallel_workers_per_gather=0")
        connection.exec_driver_sql("SET LOCAL work_mem='64kB'")

    return engine


def serve(factory, engine, stop_requested=lambda: False):
    from admin_etl_dispatch_adapter import execute
    policy = qualification()
    if not enabled() or policy is None:
        raise QualificationRefused("Explicit qualification admission required")
    generation = register_worker(factory)
    stopped = threading.Event()

    def keep_lease():
        while not stopped.wait(5):
            try:
                if not heartbeat(factory, generation):
                    stopped.set()
            except Exception:
                stopped.set()

    keeper = threading.Thread(target=keep_lease, daemon=True)
    owned = None
    outcome = "no_intent"
    try:
        keeper.start()
        end = time.monotonic() + QUEUE_SECONDS
        while not stopped.is_set() and not stop_requested() and time.monotonic() < end:
            owned = claim(factory, generation)
            if owned is not None:
                break
            stopped.wait(.1)
        if owned is not None and not stopped.is_set() and not stop_requested():
            # Main-thread execution preserves the native SIGALRM boundary and
            # avoids a second heavy Python interpreter on the 512MiB host.
            code = execute(factory, engine, *owned, generation)
            recorded = finish(factory, generation, *owned, code)
            from models import EtlDispatchCommand
            with factory() as db:
                row = db.get(EtlDispatchCommand, owned[0])
                outcome = (row.status if recorded and row is not None
                           and row.status in ("completed", "failed") else "execution_unverified")
    finally:
        stopped.set()
        if keeper.ident is not None:
            keeper.join(timeout=6)
        if keeper.is_alive() or not close_readiness(factory, generation):
            raise QualificationRefused("Readiness closure unverified")
    return dict(status=outcome, generation=str(generation),
                command_id=str(owned[0]) if owned else None, readiness_closed=True)


def main():
    # A direct CLI invocation cannot silently lose the whole-process bound.
    if (sys.platform != "linux" or os.environ.get("ADMIN_ETL_QUALIFICATION_PARENT") != str(os.getppid())
            or os.getsid(0) != os.getpid() or os.getpgrp() != os.getpid()):
        return 1
    engine = None
    stop = False

    def request_stop(signum, frame):
        nonlocal stop
        stop = True

    prior = {s: signal.signal(s, request_stop) for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        # This module has no API lifespan, startup bootstrap or migration path.
        from database import DATABASE_URL
        engine = bounded_engine(DATABASE_URL)
        factory = sessionmaker(bind=engine)
        if len(sys.argv) == 3 and sys.argv[1] == "--retire-readiness":
            from uuid import UUID
            generation = UUID(sys.argv[2])
            if str(generation) != sys.argv[2] or generation.version != 4:
                raise QualificationRefused("Canonical generation required")
            retire_inactive_readiness(factory, generation)
            result = dict(status="readiness_retired", generation=str(generation),
                          command_id=None, readiness_closed=True)
        elif len(sys.argv) == 1:
            result = serve(factory, engine, lambda: stop)
        else:
            raise QualificationRefused("Unknown qualification operation")
        print(json.dumps(result, separators=(",", ":")), flush=True)
        return 0 if result["status"] in ("completed", "readiness_retired") else 1
    except BaseException:
        print('{"status":"execution_unverified"}', flush=True)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
        for sig, handler in prior.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit(main())
