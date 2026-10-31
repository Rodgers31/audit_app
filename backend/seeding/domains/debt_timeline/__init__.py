"""Debt timeline seeding domain.

Seeds historical public debt composition (external vs domestic by year)
from CBK Annual Reports and National Treasury Budget Policy Statements.
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

logger = logging.getLogger("seeding.debt_timeline")


@register_domain("debt_timeline")
def run(
    session: Session, settings: SeedingSettings, context: DomainRunContext
) -> DomainRunResult:
    started_at = datetime.now(timezone.utc)
    errors: list[str] = []

    with create_http_client(settings) as client:
        try:
            payload = fetcher.fetch_debt_timeline_payload(client, settings)
        except Exception as exc:
            logger.exception("Failed to fetch debt timeline payload")
            return DomainRunResult(
                domain="debt_timeline",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                items_processed=0,
                items_created=0,
                items_updated=0,
                errors=[f"Fetch failed: {exc}"],
            )

    try:
        records = parser.parse_debt_timeline_payload(payload)
    except Exception as exc:
        logger.exception("Failed to parse debt timeline payload")
        return DomainRunResult(
            domain="debt_timeline",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            items_processed=0,
            items_created=0,
            items_updated=0,
            errors=[f"Parse failed: {exc}"],
        )

    try:
        created, updated = writer.write_debt_timeline_records(
            session,
            records,
            payload.get("metadata", {}),
        )
    except Exception as exc:
        logger.exception("Failed to write debt timeline records")
        return DomainRunResult(
            domain="debt_timeline",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            items_processed=len(records),
            items_created=0,
            items_updated=0,
            errors=[f"Write failed: {exc}"],
        )

    finished_at = datetime.now(timezone.utc)
    logger.info(
        f"Debt timeline seeding complete: {created} created, {updated} updated "
        f"in {(finished_at - started_at).total_seconds():.1f}s"
    )

    return DomainRunResult(
        domain="debt_timeline",
        started_at=started_at,
        finished_at=finished_at,
        items_processed=len(records),
        items_created=created,
        items_updated=updated,
        errors=errors,
        metadata={"refresh_components": payload.get("metadata", {}).get("refresh_components", {})},
    )
