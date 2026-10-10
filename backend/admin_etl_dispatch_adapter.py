"""One correlated dispatch invocation through the shared native ownership seam."""
import argparse
import sys
import logging
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from admin_etl_dispatch import SOURCE_DOMAINS, db_clock, enabled, fresh, mapped, selected_sources
from models import EtlDispatchCommand, EtlDispatchDomain, EtlDispatchWorker, IngestionJob, SeedingDomainClaim
from seeding.exclusion import DomainExecution, dispatch_scope


def ready_domains():
    """Import each bounded domain independently; one import cannot mask another."""
    from importlib import import_module
    from seeding.registries import REGISTRY
    try:
        # The actual CLI imports audit scope for every domain. Verify this
        # shared core before advertising any runnable mapping, including on a
        # cold process; a cached handler alone cannot prove CLI readiness.
        for module in ("seeding.cli", "seeding.config", "seeding.domains.audits.scope"):
            import_module(module)
    except Exception:
        logging.getLogger(__name__).warning("dispatch_core_import_unavailable")
        return set()
    domains = set()
    for source in selected_sources():
        domain = SOURCE_DOMAINS[source]
        try:
            import_module("seeding.domains." + domain)
        except Exception:
            logging.getLogger(__name__).warning("dispatch_domain_import_unavailable", extra={"domain": domain})
            continue
        if callable(REGISTRY.get(domain)):
            domains.add(domain)
    return domains


def supported_registry():
    return bool(ready_domains())


def execute(factory, engine, command_id, token, generation):
    if not enabled() or not all(isinstance(v, UUID) for v in (command_id, token, generation)) or not supported_registry():
        return 1
    with factory() as db:
        command = db.get(EtlDispatchCommand, command_id)
        if command is None or not mapped(command.source, command.domain) or command.domain not in ready_domains():
            return 1
        native_domain = command.domain
    execution = DomainExecution(factory, native_domain, token, command_id, generation)
    try:
        execution.open()
        with factory.begin() as db:
            worker = db.get(EtlDispatchWorker, 1, with_for_update=True)
            now = db_clock(db)
            domain = db.get(EtlDispatchDomain, native_domain, with_for_update=True)
            command = db.get(EtlDispatchCommand, command_id, with_for_update=True)
            ownership = db.get(SeedingDomainClaim, token, with_for_update=True)
            if not fresh(worker, now) or worker.generation != generation or command is None or not mapped(command.source, native_domain) or command.domain != native_domain or command.status != "running" or command.execution_started or command.claim_token != token or command.generation != generation or domain is None or domain.ready is not True or domain.command_id != command_id or domain.claim_token != token or ownership is None or ownership.domain != native_domain or ownership.kind != "dispatch" or ownership.command_id != command_id or ownership.returned_at is not None or ownership.released_at is not None:
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

        previous = cli.SessionLocal, cli.load_builtin_domains
        cli.SessionLocal = sessionmaker(bind=engine, class_=DispatchSession)
        # This dedicated invocation has one validated domain. Keep the actual
        # native CLI pipeline, but import only that domain at its loader seam.
        # A broken unrelated module cannot defeat a healthy readiness snapshot.
        def load_selected_domain():
            from importlib import import_module
            import_module("seeding.domains." + native_domain)
        cli.load_builtin_domains = load_selected_domain
        try:
            args = argparse.Namespace(domain=[SOURCE_DOMAINS[source]], all=False,
                since=None, dry_run=dry_run, audits_source_manifest=None, audits_observe_listing=False)
            # The CLI re-proves this exact claim/command/token/generation against
            # durable rows and consumes it once before any handler. CLI flags/env
            # cannot supply it, and a scope that never entered cannot acknowledge.
            with dispatch_scope(execution):
                return cli.run_seed_command(args, SeedingSettings(log_path=None))
        finally:
            cli.SessionLocal, cli.load_builtin_domains = previous
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
