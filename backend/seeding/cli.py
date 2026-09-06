"""Command line interface for the seeding orchestration."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
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
from . import freshness

#: Module-level logger for helpers that run outside ``run_seed_command``'s
#: locally-configured one. ``configure_logging`` attaches handlers to the
#: "seeding" root, so records emitted here land in the same place.
logger = logging.getLogger("seeding")


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


class DomainTimeoutError(BaseException):
    """Raised when a single domain handler exceeds its time budget.

    Subclasses ``BaseException`` (not ``Exception``) on purpose. Domain
    fetchers wrap each upstream call in ``except Exception`` to fall back to a
    fixture; a plain-``Exception`` timeout would be caught there, treated as
    "this one item failed", and the domain would keep running. Since the
    SIGALRM is one-shot, the budget would then be silently lost and the run
    would overrun the CI step timeout (issues #105-#113). As a
    ``BaseException`` it bypasses those handlers and propagates to
    ``run_seed_command``'s own handler, which catches it explicitly — the same
    reason ``KeyboardInterrupt``/``SystemExit`` are not ``Exception``s.
    """


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


def _record_dropped_domains(names, total_budget: float, elapsed: float) -> None:
    """Leave an ingestion_jobs row for each domain the budget never reached.

    A domain that is never attempted used to write no row at all, so it was
    absent from the nightly's "--- Ingestion Job Results ---" summary AND
    invisible to ``check_ingestion_freshness``, which only judges domains that
    reported a run. On 2026-09-06 the 03:19 nightly stopped in
    ``pending_bills`` and silently dropped ``population``,
    ``revenue_by_source`` and ``stalled_projects``; the step's only red came
    from an unrelated bootstrap failure, and without it the run would have
    printed "All domains completed successfully."

    FAILED, not completed_with_errors: the workflow's exit-code check counts
    only ``status == 'failed'``, and a domain that did not run did not refresh.
    Best-effort — never mask the truncation itself by raising here.
    """
    if not names:
        return
    try:
        _ensure_db_sessionlocal()
        assert SessionLocal is not None
        now = datetime.now(timezone.utc)
        from models import IngestionJob, IngestionStatus

        with SessionLocal() as session:
            for name in names:
                session.add(
                    IngestionJob(
                        domain=name,
                        status=IngestionStatus.FAILED,
                        dry_run=False,
                        started_at=now,
                        finished_at=now,
                        items_processed=0,
                        items_created=0,
                        items_updated=0,
                        errors=[
                            f"not run: global seed budget of "
                            f"{total_budget:.0f}s was exhausted after "
                            f"{elapsed:.0f}s"
                        ],
                        meta={"dropped_by_global_budget": True},
                    )
                )
            session.commit()
    except Exception:  # pragma: no cover - best-effort bookkeeping
        logger.exception(
            "Could not record %d domain(s) dropped by the global budget: %s",
            len(names),
            ", ".join(names),
        )


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

    # Materialise so we can index / slice / len for "remaining domains"
    # reporting, regardless of what _collect_domains returned.
    domains = list(domains)

    # Global wall-clock budget for the whole `seed --all` run. The per-domain
    # SIGALRM guard below caps any single stuck domain, but it does nothing
    # about cumulative drift: enough slow-but-under-budget domains in a row
    # still blow past the CI step timeout, which SIGKILLs the process — failing
    # the step and skipping the downstream validation job. This deadline makes
    # the run stop itself cleanly first: we quit starting new domains once it
    # passes, and cap the in-flight domain's alarm at the time remaining.
    total_budget = settings.total_timeout_seconds
    loop_start = time.monotonic()
    deadline = loop_start + total_budget if total_budget > 0 else None

    for index, domain in enumerate(domains):
        if deadline is not None and time.monotonic() >= deadline:
            skipped = domains[index:]
            logger.warning(
                "Global seed budget of %ss exhausted after %.0fs; "
                "skipping %d remaining domain(s): %s",
                total_budget,
                time.monotonic() - loop_start,
                len(skipped),
                ", ".join(skipped),
                extra={"skipped_domains": skipped},
            )
            # A partial run is not a successful one. Recorded and non-zero so
            # the drop is named in the summary and reddens the step; the
            # validation job is kept running by seed.yml's `!cancelled()`
            # rather than by this run misreporting itself.
            _record_dropped_domains(
                skipped, total_budget, time.monotonic() - loop_start
            )
            status = 1
            break

        handler = REGISTRY.get(domain)
        if handler is None:
            logger.error(
                "Domain handler missing despite registry entry",
                extra={"domain": domain},
            )
            status = 1
            continue

        # Clear any provenance recorded by a previous domain so this run's
        # live-vs-fixture verdict cannot inherit a stale one.
        freshness.reset(domain)

        started_at = datetime.now(timezone.utc)
        result: Optional[DomainRunResult] = None
        job_id: Optional[int] = None
        # Set inside the try once we know the time left; referenced in the
        # except handler, so it must exist even if we fail before computing it.
        global_capped = False

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
                #
                # If a global budget is active, cap this domain's alarm at the
                # time remaining so the in-flight domain can't push the run past
                # the global deadline. `global_capped` records that the global
                # budget (not this domain's own budget) is the binding limit, so
                # a resulting timeout is treated as a clean stop, not a failure.
                domain_budget = settings.domain_timeout_seconds
                if deadline is not None:
                    remaining = int(deadline - time.monotonic())
                    if remaining < domain_budget:
                        domain_budget = max(1, remaining)
                        global_capped = True

                with _domain_timeout(domain_budget):
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

                # Record WHERE the data came from. A domain that silently
                # served a git-tracked fixture used to be indistinguishable
                # from one that reached the publisher and found nothing new —
                # that is how three domains stayed frozen for months while
                # the nightly reported [OK] (see seeding/freshness.py).
                provenance = freshness.get(domain)
                job.meta = dict(job.meta or {})
                job.meta["source_mode"] = provenance.get("mode")
                if provenance.get("reason"):
                    job.meta["source_fallback_reason"] = provenance["reason"]
                if provenance.get("detail"):
                    job.meta["source_detail"] = provenance["detail"]

                if result and result.errors:
                    job.status = IngestionStatus.COMPLETED_WITH_ERRORS
                elif provenance.get("mode") == freshness.FIXTURE:
                    # Not an error, but NOT a clean success either: nothing
                    # authoritative was ingested. Surfacing it as
                    # completed_with_errors makes the nightly print [WARN]
                    # instead of [OK] without failing the whole run.
                    job.status = IngestionStatus.COMPLETED_WITH_ERRORS
                    job.errors = list(job.errors or []) + [
                        f"served from fixture, not the publisher "
                        f"(reason={provenance.get('reason')})"
                    ]
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

            # DomainTimeoutError is a BaseException (so fetchers' ``except
            # Exception`` can't swallow it), so catch it explicitly alongside
            # Exception here — the handler below already branches on its type.
            except (DomainTimeoutError, Exception) as exc:
                session.rollback()

                # A DomainTimeoutError raised because the *global* budget capped
                # this domain's alarm is an expected, clean "out of time" stop —
                # not a domain failure. Record it as non-fatal so the CI step
                # stays green (and the validation job still runs), then stop the
                # loop. A timeout from the domain's *own* budget falls through to
                # the failure handling below, exactly as before.
                if global_capped and isinstance(exc, DomainTimeoutError):
                    logger.warning(
                        "Global seed budget exhausted during '%s' (%.0fs elapsed); "
                        "stopping run cleanly",
                        domain,
                        time.monotonic() - loop_start,
                    )
                    if job_id:
                        try:
                            with SessionLocal() as budget_session:
                                from models import IngestionJob, IngestionStatus

                                stopped_job = budget_session.get(IngestionJob, job_id)
                                if stopped_job:
                                    # FAILED, not completed_with_errors: this
                                    # domain did not refresh. As a [WARN] it
                                    # was not counted by the workflow's
                                    # exit-code check, so a truncated run
                                    # reported success.
                                    stopped_job.status = IngestionStatus.FAILED
                                    stopped_job.finished_at = datetime.now(timezone.utc)
                                    stopped_job.errors = [
                                        "stopped: global seed budget exhausted"
                                    ]
                                    budget_session.commit()
                        except Exception:  # pragma: no cover - best-effort
                            pass
                    _record_dropped_domains(
                        domains[index + 1 :],
                        total_budget,
                        time.monotonic() - loop_start,
                    )
                    status = 1
                    break

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
