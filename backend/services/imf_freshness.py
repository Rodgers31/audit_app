"""Freshness of an IMF check is distinct from a retained observation's age."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from models import IngestionJob, IngestionStatus, SeedingDomainClaim


def _utc(value: datetime) -> datetime:
    # IngestionJob stores UTC without an offset; cohort/claim columns use TZ.
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _receipt_tables_available(db: Session) -> bool:
    dialect = db.get_bind().dialect.name
    if dialect == 'postgresql':
        return bool(db.scalar(text(
            "SELECT to_regclass('ingestion_jobs') IS NOT NULL "
            "AND to_regclass('seeding_domain_claims') IS NOT NULL"
        )))
    if dialect == 'sqlite':
        return db.scalar(text(
            "SELECT count(*) FROM sqlite_master WHERE type='table' "
            "AND name IN ('ingestion_jobs', 'seeding_domain_claims')"
        )) == 2
    return False


def with_imf_check_freshness(db: Session, payload: dict, vintage: datetime) -> dict:
    """Overlay qualified check age on a copy, without invalidating numeric data.

    Only a normal returned native run can establish freshness. A metadata-only
    job, dispatch fixture or operator reconciliation cannot. Optional table
    absence is detected without executing a failing query in the caller's txn;
    database errors otherwise propagate rather than manufacturing a fresh check.
    """
    result = dict(payload)
    now, cohort = datetime.now(timezone.utc), _utc(vintage)
    result.update(vintage_age_days=(now - cohort).days,
                  last_successful_check_at=None, check_age_days=None,
                  freshness_basis='retained_acquisition',
                  stale=cohort > now or (now - cohort).days > 60)
    if cohort > now or not _receipt_tables_available(db):
        return result

    job, claim = IngestionJob, SeedingDomainClaim
    start_at, finish_at = job.started_at, job.finished_at
    if db.get_bind().dialect.name == 'postgresql':
        # Match native terminal_observation's TimestampWithoutTZ interpretation.
        # psycopg adapts aware job times through the session timezone on INSERT.
        zone = func.current_setting('TimeZone')
        start_at = func.timezone(zone, start_at)
        finish_at = func.timezone(zone, finish_at)
    # Select only receipt fields, not job metadata/records. The domain index
    # bounds candidate scope and the result cap bounds application work.
    receipts = db.execute(select(
        start_at.label('started_at'), finish_at.label('finished_at'), job.errors,
        job.meta['seeding_claim_id'].as_string().label('claim_id'),
        claim.id, claim.acquired_at, claim.entered_at,
        claim.returned_at, claim.released_at,
    ).join(claim, claim.job_id == job.id).where(
        job.domain == 'imf_weo', job.status == IngestionStatus.COMPLETED,
        job.dry_run.is_(False), job.finished_at.is_not(None),
        job.meta['source_mode'].as_string() == 'live',
        job.meta['imf_retained_vintages']['KEN'].as_string() == cohort.isoformat(),
        claim.domain == 'imf_weo', claim.kind == 'native',
        claim.entered_at.is_not(None), claim.entry_id.is_not(None),
        claim.returned_at.is_not(None), claim.released_at.is_not(None),
        claim.reconciled_by.is_(None),
    ).order_by(job.finished_at.desc(), job.id.desc()).limit(32)).all()
    for receipt in receipts:
        if receipt.claim_id != str(receipt.id) or type(receipt.errors) is not list or receipt.errors:
            continue
        start, finish, acquired, entered, returned, released = map(_utc, (
            receipt.started_at, receipt.finished_at, receipt.acquired_at,
            receipt.entered_at, receipt.returned_at, receipt.released_at,
        ))
        # Match native terminal qualification's five-second DB/app tolerance.
        # A future check cannot freshen data until its actual time has elapsed.
        tolerance = timedelta(seconds=5)
        if not (acquired <= entered <= start + tolerance
                and start <= finish <= now and finish <= returned + tolerance
                and returned <= released <= now
                and cohort <= finish):
            continue
        result.update(last_successful_check_at=finish.isoformat(),
                      check_age_days=(now - finish).days,
                      freshness_basis='qualified_live_check',
                      stale=(now - finish).days > 60)
        break
    return result
