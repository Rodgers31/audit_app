"""Native claim/nonce/continuous-lock proof, matching the accepted CRA contract."""
from datetime import timedelta
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from models import IngestionJob, IngestionStatus, SeedingDomainClaim
from seeding.exclusion import DomainExecution, entry_digest
from seeding.county_borrowing_contract import CountyBorrowingRefused

TOLERANCE = timedelta(seconds=5)
NATIVE_META = frozenset({"since", "seeding_claim_id"})
DISPATCH_META = NATIVE_META | {"dispatch_command_id", "dispatch_claim_token"}


def execution_lock_key(domain):
    # Same derivation as seeding.exclusion.DomainExecution.key (asserted by test).
    return int.from_bytes(sha256(("seeding:" + domain).encode()).digest()[:8], "big") & ((1 << 63) - 1)


def require_ownership(session, context, lock=True):
    """Return the run's (job start, database now) after proving native ownership.

    ``lock=False`` is the pre-fetch check: it reads the claim without a row lock,
    so no lock is held across the network fetch; ``persist`` re-proves with it.
    """
    if type(context.job_id) is not int or context.job_id <= 0 or type(context.dry_run) is not bool:
        raise CountyBorrowingRefused("County borrowing requires an owned native ingestion observation")
    job = session.get(IngestionJob, context.job_id)
    if job is None or job.domain != "county_borrowing" or job.status != IngestionStatus.RUNNING or job.dry_run != context.dry_run or type(job.meta) is not dict:
        raise CountyBorrowingRefused("County borrowing requires an exact running native observation")
    token = job.meta.get("seeding_claim_id")
    try:
        if type(token) is not str or str(UUID(token)) != token:
            raise ValueError
        identity = UUID(token)
    except ValueError:
        raise CountyBorrowingRefused("County borrowing observation has no canonical ownership identity") from None
    claim = session.get(SeedingDomainClaim, identity, with_for_update=lock)
    if claim is None or claim.domain != "county_borrowing" or claim.entered_at is None or claim.released_at is not None or claim.returned_at is not None:
        raise CountyBorrowingRefused("County borrowing durable domain ownership is unavailable")
    since = job.meta.get("since")
    if claim.kind == "native":
        shape = claim.command_id is None and set(job.meta) == NATIVE_META
    elif claim.kind == "dispatch":
        shape = (claim.command_id is not None and set(job.meta) == DISPATCH_META
                 and job.meta.get("dispatch_command_id") == str(claim.command_id)
                 and job.meta.get("dispatch_claim_token") == token)
    else:
        shape = False
    if not shape or not (since is None or type(since) is str):
        raise CountyBorrowingRefused("County borrowing observation metadata differs from its native or dispatch owner")
    # Interpret the naive observation column in the session time zone, as the
    # shared terminal-observation check does, against the database clock.
    start, now = session.execute(select(
        func.timezone(func.current_setting("TimeZone"), IngestionJob.started_at), func.clock_timestamp())
        .where(IngestionJob.id == job.id)).one()
    if start is None or not max(claim.acquired_at, claim.entered_at) - TOLERANCE <= start <= now + TOLERANCE:
        raise CountyBorrowingRefused("County borrowing observation time is outside its durable ownership")
    execution = context.ownership
    if (type(execution) is not DomainExecution or execution.domain != "county_borrowing"
            or execution.identity != identity or execution.entered is not True
            or not isinstance(execution.entry, UUID)
            or entry_digest(execution.entry) != claim.entry_id
            or execution.command_id != claim.command_id
            or execution.engine is not session.get_bind()
            or type(execution.pid) is not int):
        raise CountyBorrowingRefused("County borrowing execution lock identity is unavailable")
    try:
        continuous = execution.continuous()
    except SQLAlchemyError:
        continuous = False
    if continuous is not True:
        raise CountyBorrowingRefused("County borrowing execution lock is no longer held by its runner")
    key = execution_lock_key("county_borrowing")
    held = session.scalar(text("""SELECT EXISTS (SELECT 1 FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid
        WHERE l.locktype='advisory' AND l.granted AND l.pid=:pid
        AND l.database=(SELECT oid FROM pg_database WHERE datname=current_database())
        AND l.classid=:high AND l.objid=:low AND l.objsubid=1
        AND a.xact_start IS NOT NULL AND a.xact_start <= :entered)"""),
        {"high": key >> 32, "low": key & 0xffffffff, "entered": claim.entered_at, "pid": execution.pid})
    if held is not True:
        raise CountyBorrowingRefused("County borrowing domain execution lock is not held; durable ownership retained")
    return start, now
