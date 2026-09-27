"""Economic indicators seeding domain."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...config import SeedingSettings
from ...http_client import create_http_client
from ...registries import register_domain
from ...types import DomainRunContext, DomainRunResult
from . import fetcher, parser, writer

logger = logging.getLogger("seeding.economic_indicators")


@register_domain("economic_indicators")
def run(
    session: Session, settings: SeedingSettings, context: DomainRunContext
) -> DomainRunResult:
    started_at = datetime.now(timezone.utc)
    errors: list[str] = []

    with create_http_client(settings) as client:
        try:
            payload = fetcher.fetch_economic_payload(client, settings)
        except Exception as exc:  # pragma: no cover - network failure path
            logger.exception(
                "Failed to fetch economic payload", extra={"error": str(exc)}
            )
            return (
                DomainRunResult.empty(
                    domain="economic_indicators",
                    dry_run=context.dry_run,
                    started_at=started_at,
                )
                .with_error(str(exc))
                .model_copy(update={"finished_at": datetime.now(timezone.utc)})
            )

    records = parser.parse_economic_payload(payload.records)
    stats = writer.persist_economic_records(session, records, settings, context)
    errors.extend(payload.errors)
    errors.extend(stats.errors)
    session.flush()
    removed, sweep_errors = writer.remove_superseded_rows(session, payload.coverage)
    errors.extend(sweep_errors)

    finished_at = datetime.now(timezone.utc)

    return DomainRunResult(
        domain="economic_indicators",
        started_at=started_at,
        finished_at=finished_at,
        items_processed=stats.processed,
        items_created=stats.created,
        items_updated=stats.updated,
        dry_run=context.dry_run,
        errors=errors,
        metadata={
            "skipped": stats.skipped,
            "superseded_rows_removed": [
                {"indicator_type": k, "date": d, "value": v} for k, d, v in removed
            ],
            "source_url": settings.economic_indicators_dataset_url,
        },
    )


__all__ = ["run"]
