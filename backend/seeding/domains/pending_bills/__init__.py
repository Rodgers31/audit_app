"""Pending bills seeding domain.

Two halves, each from the one publication it is first printed in: the
National Government's two lines from the Treasury BROP, and every county's
trade payables at 30 June from the Controller of Budget's full-year County
Governments Budget Implementation Review Report (#238). Both land in the loans
table as PENDING_BILLS rows that declare their publication.
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

    The National Government's lines from the Treasury BROP, then every
    county's from the Controller of Budget's year-end report, into the loans
    table as PENDING_BILLS rows.

    Args:
        session: Database session
        settings: Seeding configuration
        context: Domain execution context

    Returns:
        Result with metrics and errors
    """
    started_at = datetime.now(timezone.utc)
    errors: list[str] = []

    # Independent halves: a national failure must not cost the counties their
    # run, nor the reverse.
    processed, created, updated = _seed_national(session, settings, context, errors)
    county_processed, county_created, county_updated = _seed_counties(
        session, settings, context, errors
    )

    return DomainRunResult(
        domain="pending_bills",
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        items_processed=processed + county_processed,
        items_created=created + county_created,
        items_updated=updated + county_updated,
        errors=errors,
    )


def _seed_national(
    session: Session,
    settings: SeedingSettings,
    context: DomainRunContext,
    errors: list[str],
) -> tuple[int, int, int]:
    """The National Government's two lines from the Treasury BROP."""
    with create_http_client(settings) as client:
        try:
            payload = fetcher.fetch_pending_bills_payload(client, settings)
        except Exception as exc:
            logger.exception(
                "Failed to fetch pending bills payload",
                extra={"error": str(exc)},
            )
            errors.append(f"Fetch failed: {exc}")
            return 0, 0, 0

    try:
        records = parser.parse_pending_bills_payload(payload)
    except Exception as exc:
        logger.exception(
            "Failed to parse pending bills payload",
            extra={"error": str(exc)},
        )
        errors.append(f"Parse failed: {exc}")
        _mark_live_run_partial("national_pending_bills_parse_failed", exc)
        return 0, 0, 0

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
        errors.append(f"Write failed: {exc}")
        _mark_live_run_partial("national_pending_bills_write_failed", exc)
        return len(records), 0, 0
    return len(records), created, updated


def _seed_counties(
    session: Session,
    settings: SeedingSettings,
    context: DomainRunContext,
    errors: list[str],
) -> tuple[int, int, int]:
    """County pending bills from the CoB's newest year-end report.

    A failure is appended to ``errors`` and, when the national half came from
    the BROP, turns the domain's freshness from LIVE to PARTIAL: a night that
    refreshed the national lines and not the 47 counties must not report the
    domain as fresh. The county rows already published stand either way.
    """
    from ...freshness import LIVE, mark_partial
    from ...freshness import get as fresh_get

    try:
        with create_http_client(settings) as client:
            payload = fetcher.fetch_county_payables_payload(client, settings)
    except Exception as exc:
        logger.exception("County pending bills: CoB year-end report not read")
        errors.append(f"County pending bills not read: {exc}")
        if fresh_get("pending_bills").get("mode") == LIVE:
            mark_partial(
                "pending_bills",
                reason="county_payables_unavailable",
                detail=str(exc)[:200],
            )
        return 0, 0, 0
    if payload is None:
        return 0, 0, 0

    try:
        county_records = parser.parse_pending_bills_payload(payload)
    except Exception as exc:
        logger.exception("County pending bills: parse failed")
        errors.append(f"County pending bills parse failed: {exc}")
        _mark_live_run_partial("county_payables_parse_failed", exc)
        return 0, 0, 0
    try:
        created, updated = writer.write_pending_bills(
            session=session,
            records=county_records,
            source_url=payload.get("source_url"),
            source_title=payload.get("source_title"),
            publication=payload.get("publication"),
            publisher=payload.get("publisher"),
            county_table=payload.get("county_table"),
            dry_run=context.dry_run,
        )
    except Exception as exc:
        logger.exception("County pending bills: write failed")
        errors.append(f"County pending bills write failed: {exc}")
        if fresh_get("pending_bills").get("mode") == LIVE:
            mark_partial(
                "pending_bills",
                reason="county_payables_write_failed",
                detail=str(exc)[:200],
            )
        return len(county_records), 0, 0
    logger.info(
        "County pending bills: %d counties from %s",
        len(county_records),
        payload.get("source_url"),
    )
    return len(county_records), created, updated


def _mark_live_run_partial(reason: str, exc: Exception) -> None:
    """A successful fetch cannot certify a refused parse or write as LIVE."""
    from ...freshness import LIVE, get, mark_partial

    if get("pending_bills").get("mode") == LIVE:
        mark_partial("pending_bills", reason=reason, detail=str(exc)[:200])
