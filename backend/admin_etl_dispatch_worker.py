"""Opt-in dedicated process; no application lifespan or API-replica consumer.

The domain row stays occupied after uncertain execution, even after process death.
Only a fresh fenced terminal receipt releases it. There is no automatic recovery
of uncertain effects or administrative unblock endpoint.
"""
from pathlib import Path
import subprocess
import sys
import threading
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert

from admin_etl_dispatch import SOURCE_DOMAINS, db_clock, enabled, fresh, mapped
from seeding.exclusion import reserve, unclaimed_running
from models import EtlDispatchCommand, EtlDispatchDomain, EtlDispatchWorker, IngestionJob, IngestionStatus, SeedingDomainClaim

LEASE_SECONDS = 30
HEARTBEAT_SECONDS = 5
OBSERVATION_CLOCK_SKEW_SECONDS = 5


def register_worker(factory):
    from admin_etl_dispatch_adapter import ready_domains
    ready = ready_domains()
    generation = uuid4()
    with factory.begin() as db:
        now = db_clock(db)
        db.execute(insert(EtlDispatchWorker).values(id=1, generation=generation,
            ready=False, last_seen_at=now, expires_at=now + timedelta(seconds=LEASE_SECONDS)).on_conflict_do_nothing())
        worker = db.scalar(select(EtlDispatchWorker).where(EtlDispatchWorker.id == 1).with_for_update())
        now = db_clock(db)
        if fresh(worker, now):
            raise RuntimeError("Dedicated consumer already owns the lease")
        # Restart/death before or after effects are equally uncertain. Fence every
        # old running command and keep each protected domain occupied.
        running = db.scalars(select(EtlDispatchCommand).where(EtlDispatchCommand.status == "running").with_for_update()).all()
        for command in running:
            interrupt(command, now)
        worker.generation = generation
        worker.ready = True
        worker.last_seen_at = now
        worker.expires_at = now + timedelta(seconds=LEASE_SECONDS)
        for name in sorted(set(SOURCE_DOMAINS.values())):
            db.execute(insert(EtlDispatchDomain).values(domain=name, ready=name in ready).on_conflict_do_nothing())
            db.get(EtlDispatchDomain, name, with_for_update=True).ready = name in ready
    return generation


def heartbeat(factory, generation):
    from admin_etl_dispatch_adapter import ready_domains
    ready = ready_domains()
    with factory.begin() as db:
        worker = db.scalar(select(EtlDispatchWorker).where(EtlDispatchWorker.id == 1).with_for_update())
        now = db_clock(db)
        if not fresh(worker, now) or worker.generation != generation:
            return False
        worker.last_seen_at = now
        worker.expires_at = now + timedelta(seconds=LEASE_SECONDS)
        for row in db.scalars(select(EtlDispatchDomain).with_for_update()):
            row.ready = row.domain in ready
    return True


def interrupt(command, now):
    command.status = "interrupted"
    command.finished_at = command.updated_at = now
    command.outcome = "execution_unverified"
    command.version += 1


def claim(factory, generation):
    with factory.begin() as db:
        worker = db.scalar(select(EtlDispatchWorker).where(EtlDispatchWorker.id == 1).with_for_update())
        now = db_clock(db)
        if not fresh(worker, now) or worker.generation != generation:
            return None
        domains = {row.domain: row for row in db.scalars(select(EtlDispatchDomain).order_by(EtlDispatchDomain.domain).with_for_update())}
        candidates = []
        for name, domain in domains.items():
            if domain.ready is not True or domain.command_id is not None or unclaimed_running(db, name):
                continue
            candidate = db.scalar(select(EtlDispatchCommand).where(EtlDispatchCommand.status == "queued", EtlDispatchCommand.domain == name).order_by(EtlDispatchCommand.created_at, EtlDispatchCommand.id).limit(1).with_for_update(skip_locked=True))
            if candidate is not None and mapped(candidate.source, name):
                candidates.append(candidate)
        command = None
        for candidate in sorted(candidates, key=lambda c: (c.created_at, c.id)):
            domain = domains.get(candidate.domain)
            token = uuid4()
            if reserve(db, candidate.domain, token, candidate.id):
                command = candidate
                break
        if command is None:
            return None
        command.status = "running"
        command.started_at = command.updated_at = now
        command.generation = generation
        command.claim_token = token
        command.version += 1
        domain.command_id, domain.claim_token = command.id, token
        return command.id, token


def finish(factory, generation, command_id, token, exit_code):
    with factory.begin() as db:
        worker = db.scalar(select(EtlDispatchWorker).where(EtlDispatchWorker.id == 1).with_for_update())
        now = db_clock(db)
        # Worker row serializes domain lookup with claim/adapter/CLI entry.
        command = db.get(EtlDispatchCommand, command_id)
        if command is None or not mapped(command.source, command.domain):
            return False
        domain = db.get(EtlDispatchDomain, command.domain, with_for_update=True)
        command = db.get(EtlDispatchCommand, command_id, with_for_update=True)
        if command is None or command.status != "running" or command.generation != generation or command.claim_token != token or domain is None or domain.command_id != command_id or domain.claim_token != token:
            return False
        if not fresh(worker, now) or worker.generation != generation:
            interrupt(command, now)
            return False
        ownership = db.get(SeedingDomainClaim, token, with_for_update=True)
        if (ownership is not None and ownership.kind == "dispatch" and ownership.domain == command.domain and ownership.command_id == command_id
                and ownership.entered_at is None and ownership.returned_at is None and ownership.released_at is None
                # Defence in depth: any correlated run observation other than an
                # ownership refusal means something ran; keep it uncertain.
                and db.scalar(select(IngestionJob.id).where(
                    IngestionJob.meta["dispatch_command_id"].astext == str(command_id),
                    IngestionJob.meta["dispatch_claim_token"].astext == str(token),
                    or_(func.jsonb_typeof(IngestionJob.meta["ownership_refused"]).is_distinct_from("boolean"),
                        IngestionJob.meta["ownership_refused"].astext.is_distinct_from("true"))).limit(1)) is None):
            # The CLI never entered, so no handler ran; entry re-proves this
            # running command and unreleased claim under these same row locks,
            # so nothing can enter after this. Free the domain, record failure.
            command.status = command.outcome = "failed"
            command.updated_at = command.finished_at = now
            command.version += 1
            ownership.released_at = now
            domain.command_id = domain.claim_token = None
            return True
        # Correlation comes from the adapter's actual CLI session insertion, never
        # a latest-ID guess or the child's exit code alone. Reads are bounded.
        # Native observations have timestamp-without-time-zone columns. Their
        # aware CLI values were cast using this database session's TimeZone;
        # let PostgreSQL recover that offset rather than guessing UTC in Python.
        observations = db.execute(select(IngestionJob,
            func.timezone(func.current_setting("TimeZone"), IngestionJob.started_at),
            func.timezone(func.current_setting("TimeZone"), IngestionJob.finished_at))
            .where(IngestionJob.meta["dispatch_command_id"].astext == str(command_id),
                IngestionJob.meta["dispatch_claim_token"].astext == str(token)).limit(2)).all()
        if not command.execution_started or len(observations) != 1 or type(exit_code) is not int:
            interrupt(command, now)
            return False
        job, observed_start, observed_finish = observations[0]
        if ownership is None or ownership.domain != command.domain or ownership.kind != "dispatch" or ownership.command_id != command_id or ownership.released_at is not None or ownership.returned_at is None or ownership.job_id != job.id:
            interrupt(command, now)
            return False
        tolerance = timedelta(seconds=OBSERVATION_CLOCK_SKEW_SECONDS)
        # Accepted OAG failure observations predating the native claim tag may
        # omit it. Exact durable claim/job acknowledgement above still applies;
        # an explicit bad tag, any completed job, and every new mapping refuse.
        tagged_claim = (type(job.meta) is dict and (
            job.meta.get("seeding_claim_id") == str(token) or (
                command.source == "oag" and "seeding_claim_id" not in job.meta
                and job.status in (IngestionStatus.FAILED, IngestionStatus.COMPLETED_WITH_ERRORS))))
        coherent = (job.domain == command.domain and job.dry_run == command.dry_run
            and tagged_claim
            and observed_start is not None and observed_finish is not None
            and command.started_at - tolerance <= observed_start <= observed_finish <= now + tolerance
            and all(type(value) is int and 0 <= value <= 2147483647 for value in (job.items_processed, job.items_created, job.items_updated))
            and job.status in (IngestionStatus.COMPLETED, IngestionStatus.COMPLETED_WITH_ERRORS, IngestionStatus.FAILED)
            and (job.status != IngestionStatus.COMPLETED or type(job.errors) is list and len(job.errors) == 0))
        if not coherent:
            interrupt(command, now)
            return False
        command.job_id = job.id
        completed = type(exit_code) is int and exit_code == 0 and job.status == IngestionStatus.COMPLETED
        command.status = command.outcome = "completed" if completed else "failed"
        command.updated_at = command.finished_at = now
        command.version += 1
        ownership.released_at = now
        domain.command_id = domain.claim_token = None
        return True


def stop_child(child):
    if child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def serve(factory):
    from admin_etl_dispatch_adapter import supported_registry
    if not enabled() or not supported_registry():
        raise RuntimeError("Dedicated dispatch is disabled or its mapping is unavailable")
    generation = register_worker(factory)
    stopped = threading.Event()

    def keep_lease():
        while not stopped.wait(HEARTBEAT_SECONDS):
            try:
                if not heartbeat(factory, generation):
                    stopped.set()
            except Exception:
                # Do not resurrect a lease or print database/runner diagnostics.
                stopped.set()

    keeper = threading.Thread(target=keep_lease, daemon=True)
    keeper.start()
    child = None
    try:
        while not stopped.is_set():
            claimed = claim(factory, generation)
            if claimed is None:
                stopped.wait(0.5)
                continue
            command_id, token = claimed
            # A fixed module and server-created IDs: the API never supplies code,
            # paths, source URLs or arbitrary native CLI arguments.
            child = subprocess.Popen([sys.executable, "-m", "admin_etl_dispatch_adapter", str(command_id), str(token), str(generation)],
                cwd=Path(__file__).resolve().parent, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            while child.poll() is None and not stopped.wait(0.1):
                pass
            if stopped.is_set() and child.poll() is None:
                stop_child(child)
            finish(factory, generation, command_id, token, child.returncode)
            child = None
    finally:
        stopped.set()
        if child is not None and child.poll() is None:
            stop_child(child)
        keeper.join(timeout=6)
        with factory.begin() as db:
            worker = db.scalar(select(EtlDispatchWorker).where(EtlDispatchWorker.id == 1).with_for_update())
            if worker.generation == generation:
                worker.ready = False
                for command in db.scalars(select(EtlDispatchCommand).where(EtlDispatchCommand.status == "running", EtlDispatchCommand.generation == generation).with_for_update()):
                    interrupt(command, db_clock(db))


def main():
    # Entry point deliberately separate from backend.main and its lifespan.
    if not enabled():
        print("Dedicated dispatch is disabled.", file=sys.stderr)
        return 1
    from database import SessionLocal
    try:
        serve(SessionLocal)
    except KeyboardInterrupt:
        return 0
    except Exception:
        print("Dedicated worker unavailable.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
