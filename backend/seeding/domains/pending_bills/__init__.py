"""Pending bills seeding domain.

Fetches pending bills data from the Controller of Budget (COB) reports
and populates the loans table with pending_bills category records.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...config import SeedingSettings
from ...http_client import create_http_client
from ...registries import register_domain
from ...types import DomainRunContext, DomainRunResult
from . import fetcher, parser, writer

logger = logging.getLogger("seeding.pending_bills")


@register_domain("pending_bills")
def run(
    session: Session, settings: SeedingSettings, context: DomainRunContext
) -> DomainRunResult:
    """
    Execute pending bills seeding domain.

    Fetches pending bills data from COB reports (via ETL extractor or
    fixture) and populates the loans table with PENDING_BILLS category.

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
            payload = fetcher.fetch_pending_bills_payload(client, settings)
        except Exception as exc:
            logger.exception(
                "Failed to fetch pending bills payload",
                extra={"error": str(exc)},
            )
            return DomainRunResult(
                domain="pending_bills",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                items_processed=0,
                items_created=0,
                items_updated=0,
                errors=[f"Fetch failed: {exc}"],
            )

    try:
        records = parser.parse_pending_bills_payload(payload)
    except Exception as exc:
        logger.exception(
            "Failed to parse pending bills payload",
            extra={"error": str(exc)},
        )
        return DomainRunResult(
            domain="pending_bills",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            items_processed=0,
            items_created=0,
            items_updated=0,
            errors=[f"Parse failed: {exc}"],
        )

    logger.info(f"Parsed {len(records)} pending bills records")

    try:
        created, updated = writer.write_pending_bills(
            session=session,
            records=records,
            source_url=payload.get("source_url"),
            source_title=payload.get("source_title"),
            publication=payload.get("publication"),
            publisher=payload.get("publisher"),
            dry_run=context.dry_run,
        )
    except Exception as exc:
        logger.exception(
            "Failed to write pending bills to DB",
            extra={"error": str(exc)},
        )
        return DomainRunResult(
            domain="pending_bills",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            items_processed=len(records),
            items_created=0,
            items_updated=0,
            errors=[f"Write failed: {exc}"],
        )

    return DomainRunResult(
        domain="pending_bills",
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        items_processed=len(records),
        items_created=created,
        items_updated=updated,
        errors=errors,
    )
