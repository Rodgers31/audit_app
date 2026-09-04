"""National debt seeding domain."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...config import SeedingSettings
from ...http_client import create_http_client
from ...registries import register_domain
from ...types import DomainRunContext, DomainRunResult
from . import fetcher, instrument_writer, parser, writer

logger = logging.getLogger("seeding.national_debt")


@register_domain("national_debt")
def run(
    session: Session, settings: SeedingSettings, context: DomainRunContext
) -> DomainRunResult:
    """
    Execute national debt seeding domain.

    Fetches debt data from National Treasury bulletins and populates
    the loans table with government debt records.

    Args:
        session: Database session
        settings: Seeding configuration
        context: Domain execution context

    Returns:
        Result with metrics and errors
    """
    started_at = datetime.now(timezone.utc)
    errors: list[str] = []

    with create_http_client(settings) as client:
        try:
            payload = fetcher.fetch_debt_payload(client, settings)
        except Exception as exc:
            logger.exception("Failed to fetch debt payload", extra={"error": str(exc)})
            return DomainRunResult(
                domain="national_debt",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                items_processed=0,
                items_created=0,
                items_updated=0,
                errors=[f"Fetch failed: {exc}"],
            )

    try:
        records = parser.parse_debt_payload(payload)
    except Exception as exc:
        logger.exception("Failed to parse debt payload", extra={"error": str(exc)})
        return DomainRunResult(
            domain="national_debt",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            items_processed=0,
            items_created=0,
            items_updated=0,
            errors=[f"Parse failed: {exc}"],
        )

    try:
        created, updated = writer.write_debt_records(
            session,
            records,
            dataset_id="national-debt",
            job_id=context.job_id,
        )
    except Exception as exc:
        logger.exception("Failed to write debt records", extra={"error": str(exc)})
        return DomainRunResult(
            domain="national_debt",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            items_processed=len(records),
            items_created=0,
            items_updated=0,
            errors=[f"Write failed: {exc}"],
        )

    # ── Instrument register ───────────────────────────────────────
    # Written to its own table, never merged into `loans`. It is a maturity
    # and coupon profile covering ~60% of the published bond stock, so a row
    # here must not reach any code that sums a debt total.
    #
    # A failure to write it is NOT a failure of this domain: the loans and
    # timeline figures above stand on their own. It is recorded as an error on
    # the run so the absence is visible, and the maturity ladder renders its
    # own empty state rather than a partial one.
    register = payload.get("bond_register")
    if register:
        try:
            counts = instrument_writer.write_bond_register(session, register)
            logger.info(
                "Bond register: %d created, %d updated, %d removed "
                "(%d ISIN(s) withheld as ambiguous)",
                counts["created"], counts["updated"], counts["deleted"],
                len(register.get("withheld_isins") or {}),
            )
        except Exception as exc:
            logger.exception("Failed to write bond register")
            errors.append(f"Bond register write failed: {exc}")
    else:
        # Says which of the two it is: the fetch failed, or the coverage gate
        # quarantined the register. Both leave the ladder empty, and a reader
        # of the logs should not have to guess which.
        errors.append(
            "Bond register absent: CBK table fetch failed or coverage gate "
            "quarantined it (see earlier warnings)"
        )

    finished_at = datetime.now(timezone.utc)
    logger.info(
        f"National debt seeding complete: {created} created, {updated} updated in "
        f"{(finished_at - started_at).total_seconds():.1f}s"
    )

    return DomainRunResult(
        domain="national_debt",
        started_at=started_at,
        finished_at=finished_at,
        items_processed=len(records),
        items_created=created,
        items_updated=updated,
        errors=errors,
    )
