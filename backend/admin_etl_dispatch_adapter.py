"""One correlated dispatch invocation through the shared native ownership seam."""
import argparse
import sys
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from admin_etl_dispatch import SOURCE_DOMAINS, db_clock, enabled, fresh
from models import EtlDispatchCommand, EtlDispatchDomain, EtlDispatchWorker, IngestionJob, SeedingDomainClaim
from seeding.exclusion import DomainExecution, dispatch_scope


def supported_registry():
    from seeding.registries import REGISTRY, load_builtin_domains
    load_builtin_domains()
    return all(callable(REGISTRY.get(domain)) for domain in SOURCE_DOMAINS.values())


def execute(factory, engine, command_id, token, generation):
    if not enabled() or not all(isinstance(v, UUID) for v in (command_id, token, generation)) or not supported_registry():
        return 1
    execution = DomainExecution(factory, "audits", token, command_id, generation)
    try:
        execution.open()
        with factory.begin() as db:
            worker = db.get(EtlDispatchWorker, 1, with_for_update=True)
            now = db_clock(db)
            domain = db.get(EtlDispatchDomain, "audits", with_for_update=True)
            command = db.get(EtlDispatchCommand, command_id, with_for_update=True)
            ownership = db.get(SeedingDomainClaim, token, with_for_update=True)
            if not fresh(worker, now) or worker.generation != generation or command is None or command.status != "running" or command.execution_started or command.claim_token != token or command.generation != generation or domain is None or domain.command_id != command_id or domain.claim_token != token or ownership is None or ownership.domain != "audits" or ownership.kind != "dispatch" or ownership.command_id != command_id or ownership.returned_at is not None or ownership.released_at is not None:
                return 1
            source, dry_run = command.source, command.dry_run
            # Persist the one-use execution decision before entering the CLI.
            # A lost commit acknowledgment is uncertainty, never permission to retry.
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
            # The CLI re-proves this exact claim/command/token/generation against
            # durable rows and consumes it once before any handler. CLI flags/env
            # cannot supply it, and a scope that never entered cannot acknowledge.
            with dispatch_scope(execution):
                return cli.run_seed_command(args, SeedingSettings(log_path=None))
        finally:
            cli.SessionLocal = previous
    except Exception:
        return 1
    finally:
        execution.close()


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
