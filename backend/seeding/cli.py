"""Command line interface for the seeding orchestration."""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence

from dotenv import load_dotenv

try:  # Avoid import-time cost if CLI unused
    from database import SessionLocal
except ImportError:  # pragma: no cover - defensive fallback
    SessionLocal = None  # type: ignore

from .config import SeedingSettings, get_settings
from .logging import configure_logging
from .registries import REGISTRY, load_builtin_domains
from .types import DomainRunContext, DomainRunResult


def _parse_since(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            msg = "--since must be ISO timestamp or YYYY-MM-DD"
            raise argparse.ArgumentTypeError(msg) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed


def _collect_domains(requested: Iterable[str], include_all: bool) -> Sequence[str]:
    available = REGISTRY.domains()
    if include_all:
        return available
    domains = list(dict.fromkeys(requested))
    unknown = [name for name in domains if name not in available]
    if unknown:
        raise ValueError(f"Unknown domain(s) requested: {', '.join(sorted(unknown))}")
    return domains


class DomainTimeoutError(RuntimeError):
    """Raised when a single domain handler exceeds its time budget."""


@contextmanager
def _domain_timeout(seconds: int) -> Iterator[None]:
    """Abort the wrapped block with DomainTimeoutError after `seconds`.

    Uses POSIX SIGALRM so the timeout actually kills Python-level work
    (including `time.sleep`, `httpx` connect/read, and pdfplumber between
    its Python frames). Three preconditions must hold to install the
    handler; if any fail we silently yield without a timeout so callers
    in unsupported contexts degrade gracefully:

      * `seconds > 0`
      * SIGALRM exists (POSIX only — Windows has no equivalent)
      * we are on the main thread (CPython's `signal.signal` raises
        ValueError otherwise, which would crash rather than degrade).

    The seeding CLI always runs in the main thread in CI; the main-
    thread guard is there for pytest and embedded-runner scenarios
    that invoke the CLI from a worker thread.

    Caveat: code stuck in a blocking C extension call that never yields
    to Python (e.g. some tabula JVM bridge calls) won't be interruptible
    until it returns. In practice SIGALRM catches most real-world stalls
    we've seen.
    """
    if (
        seconds <= 0
        or not hasattr(signal, "SIGALRM")
        or threading.current_thread() is not threading.main_thread()
    ):
        yield
        return

    def _handler(signum, frame):  # pragma: no cover - signal path
        raise DomainTimeoutError(
            f"domain exceeded {seconds}s budget; aborted by the CLI"
        )

    previous = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _ensure_db_sessionlocal() -> None:
    if SessionLocal is None:
        raise RuntimeError("SessionLocal could not be imported from database module")


def run_seed_command(args: argparse.Namespace, settings: SeedingSettings) -> int:
    logger = configure_logging(settings.log_level, settings.log_path)

    load_builtin_domains()

    try:
        domains = _collect_domains(args.domain or [], args.all)
    except ValueError as exc:
        logger.error("Domain validation failed", extra={"error": str(exc)})
        return 1

    if not domains:
        logger.warning("No domains registered - nothing to do")
        return 0

    since = _parse_since(args.since)
    dry_run = settings.dry_run_default if args.dry_run is None else args.dry_run

    status = 0

    for domain in domains:
        handler = REGISTRY.get(domain)
        if handler is None:
            logger.error(
                "Domain handler missing despite registry entry",
                extra={"domain": domain},
            )
            status = 1
            continue

        started_at = datetime.now(timezone.utc)
        result: Optional[DomainRunResult] = None
        job_id: Optional[int] = None

        _ensure_db_sessionlocal()
        assert SessionLocal is not None  # for type-checkers

        with SessionLocal() as session:
            try:
                # Create ingestion job record
                from models import IngestionJob, IngestionStatus

                job = IngestionJob(
                    domain=domain,
                    status=IngestionStatus.RUNNING,
                    dry_run=dry_run,
                    started_at=started_at,
                    items_processed=0,
                    items_created=0,
                    items_updated=0,
                    errors=[],
                    meta={"since": since.isoformat() if since else None},
                )
                session.add(job)
                session.flush()
                job_id = job.id
                # Commit the RUNNING record immediately so it survives a
                # later session.rollback() (e.g. on DomainTimeoutError or
                # any other handler exception). Without this commit the
                # job insert is inside the same transaction as the handler
                # work, so rollback erases it and error_session.get(…)
                # returns None, leaving no trace of the failed domain run.
                session.commit()

                context = DomainRunContext(since=since, dry_run=dry_run, job_id=job_id)

                # Per-domain timeout so one stuck domain (e.g. a stalled
                # PDF parse in counties_budget) can't take down the whole
                # `seed --all` run. Falls through to the except below,
                # which rolls back the session, marks the job FAILED,
                # and lets the outer loop move to the next domain.
                with _domain_timeout(settings.domain_timeout_seconds):
                    result = handler(session=session, settings=settings, context=context)

                # Update job with results
                job.finished_at = datetime.now(timezone.utc)
                job.items_processed = result.items_processed if result else 0
                job.items_created = result.items_created if result else 0
                job.items_updated = result.items_updated if result else 0
                job.errors = result.errors if result else []
                if result and result.metadata:
                    job.meta = dict(job.meta or {})
                    job.meta.update(result.metadata)

                if result and result.errors:
                    job.status = IngestionStatus.COMPLETED_WITH_ERRORS
                else:
                    job.status = IngestionStatus.COMPLETED

                if dry_run:
                    finished_at_dry = datetime.now(timezone.utc)
                    session.rollback()
                    logger.info(
                        "Dry run - rolled back all changes", extra={"domain": domain}
                    )
                    # The rollback above also undoes the in-flight job status
                    # update (job was committed as RUNNING before the handler
                    # ran). Persist the final status in a separate session so
                    # the record doesn't stay orphaned in RUNNING state.
                    if job_id:
                        final_status = (
                            IngestionStatus.COMPLETED_WITH_ERRORS
                            if result and result.errors
                            else IngestionStatus.COMPLETED
                        )
                        try:
                            with SessionLocal() as status_session:
                                dry_job = status_session.get(IngestionJob, job_id)
                                if dry_job:
                                    dry_job.status = final_status
                                    dry_job.finished_at = finished_at_dry
                                    dry_job.items_processed = (
                                        result.items_processed if result else 0
                                    )
                                    dry_job.items_created = (
                                        result.items_created if result else 0
                                    )
                                    dry_job.items_updated = (
                                        result.items_updated if result else 0
                                    )
                                    dry_job.errors = result.errors if result else []
                                    status_session.commit()
                        except Exception:  # pragma: no cover - best-effort
                            logger.warning(
                                "Failed to update dry-run job status",
                                extra={"domain": domain, "job_id": job_id},
                                exc_info=True,
                            )
                else:
                    session.commit()
                    logger.info(
                        "Committed changes", extra={"domain": domain, "job_id": job_id}
                    )

            except Exception as exc:  # pragma: no cover - requires integration tests
                session.rollback()
                logger.exception(
                    "Domain run failed", extra={"domain": domain, "error": str(exc)}
                )
                status = 1

                # Try to update job status even on failure
                if job_id:
                    try:
                        with SessionLocal() as error_session:
                            from models import IngestionJob, IngestionStatus

                            failed_job = error_session.get(IngestionJob, job_id)
                            if failed_job:
                                failed_job.status = IngestionStatus.FAILED
                                failed_job.finished_at = datetime.now(timezone.utc)
                                failed_job.errors = [str(exc)]
                                error_session.commit()
                    except Exception:  # pragma: no cover
                        pass

                result = DomainRunResult.empty(
                    domain=domain,
                    dry_run=dry_run,
                    started_at=started_at,
                ).with_error(str(exc))

        finished_at = datetime.now(timezone.utc)
        if result is None:
            result = DomainRunResult.empty(
                domain=domain,
                dry_run=dry_run,
                started_at=started_at,
                finished_at=finished_at,
            )
        else:
            result = result.model_copy(update={"finished_at": finished_at})

        logger.info("Domain run completed", extra=result.model_dump())

    return status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Database seeding utilities")
    subparsers = parser.add_subparsers(dest="command")

    seed_parser = subparsers.add_parser(
        "seed", help="Run seeding for one or more domains"
    )
    seed_parser.add_argument(
        "--domain", action="append", help="Domain to seed (repeatable)"
    )
    seed_parser.add_argument(
        "--all", action="store_true", help="Run every registered domain"
    )
    seed_parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Avoid committing database changes (overrides default)",
    )
    seed_parser.add_argument(
        "--since",
        help="ISO timestamp or YYYY-MM-DD to limit ingestion to recent records",
    )
    seed_parser.add_argument(
        "--config",
        type=Path,
        help="Optional path to .env file providing environment configuration",
    )

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "seed":
        parser.print_help()
        return 1

    if getattr(args, "config", None):
        load_dotenv(dotenv_path=args.config, override=True)
    else:
        load_dotenv(override=False)

    settings = get_settings()
    return run_seed_command(args, settings)


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
