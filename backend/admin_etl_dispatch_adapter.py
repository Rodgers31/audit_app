"""One static source/domain invocation of the unchanged native seeding CLI."""
import argparse
import sys
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.orm import Session, sessionmaker

from admin_etl_dispatch import SOURCE_DOMAINS, db_clock, enabled, fresh
from models import EtlDispatchCommand, EtlDispatchDomain, EtlDispatchWorker, IngestionJob

DOMAIN_LOCK = 5540001


def supported_registry():
    from seeding.registries import REGISTRY, load_builtin_domains
    load_builtin_domains()
    return all(callable(REGISTRY.get(domain)) for domain in SOURCE_DOMAINS.values())


def execute(factory, engine, command_id, token, generation):
    if not enabled() or not supported_registry():
        return 1
    # Session lock prevents a duplicate adapter launch. The durable domain row
    # additionally survives lock-connection loss and supervisor/child death.
    with engine.connect() as lock:
        if not lock.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": DOMAIN_LOCK}):
            return 1
        try:
            with factory.begin() as db:
                now = db_clock(db)
                command = db.get(EtlDispatchCommand, command_id, with_for_update=True)
                domain = db.get(EtlDispatchDomain, "audits")
                worker = db.get(EtlDispatchWorker, 1)
                if not fresh(worker, now) or worker.generation != generation or command is None or command.status != "running" or command.execution_started or command.claim_token != token or command.generation != generation or domain is None or domain.command_id != command_id or domain.claim_token != token:
                    return 1
                source, dry_run = command.source, command.dry_run
                # Persist before work. An ambiguous commit is never permission
                # to execute again, even if a duplicate adapter is launched.
                command.execution_started = True
            from seeding import cli
            from seeding.config import SeedingSettings

            class DispatchSession(Session):
                pass

            @event.listens_for(DispatchSession, "before_flush")
            def correlate(session, context, instances):
                for row in session.new:
                    if isinstance(row, IngestionJob):
                        row.meta = {**(row.meta or {}), "dispatch_command_id": str(command_id), "dispatch_claim_token": str(token)}

            previous = cli.SessionLocal
            cli.SessionLocal = sessionmaker(bind=engine, class_=DispatchSession)
            try:
                args = argparse.Namespace(domain=[SOURCE_DOMAINS[source]], all=False,
                    since=None, dry_run=dry_run, audits_source_manifest=None, audits_observe_listing=False)
                return cli.run_seed_command(args, SeedingSettings(log_path=None))
            finally:
                cli.SessionLocal = previous
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": DOMAIN_LOCK})


def main():
    from database import SessionLocal, engine
    try:
        if len(sys.argv) != 4:
            return 1
        return execute(SessionLocal, engine, *(UUID(v) for v in sys.argv[1:]))
    except Exception:
        # Native runner diagnostics are not copied to command/browser responses.
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
