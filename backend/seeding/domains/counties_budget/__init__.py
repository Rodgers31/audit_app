"""County budget seeding domain."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...config import SeedingSettings
from ...http_client import create_http_client
from ...registries import register_domain
from ...types import DomainRunContext, DomainRunResult
from . import fetcher, parser, writer

logger = logging.getLogger("seeding.counties_budget")


@register_domain("counties_budget")
def run(
    session: Session, settings: SeedingSettings, context: DomainRunContext
) -> DomainRunResult:
    started_at = datetime.now(timezone.utc)
    errors: list[str] = []

    with create_http_client(settings) as client:
        try:
            payload = fetcher.fetch_budget_payload(client, settings)
        except Exception as exc:  # pragma: no cover - network failure path
            logger.exception(
                "Failed to fetch budget payload", extra={"error": str(exc)}
            )
            return (
                DomainRunResult.empty(
                    domain="counties_budget",
                    dry_run=context.dry_run,
                    started_at=started_at,
                )
                .with_error(str(exc))
                .model_copy(update={"finished_at": datetime.now(timezone.utc)})
            )

    records = parser.parse_budget_payload(payload)
    stats = writer.persist_budget_records(session, records, settings, context)
    errors.extend(stats.errors)

    finished_at = datetime.now(timezone.utc)

    return DomainRunResult(
        domain="counties_budget",
        started_at=started_at,
        finished_at=finished_at,
        items_processed=stats.processed,
        items_created=stats.created,
        items_updated=stats.updated,
        dry_run=context.dry_run,
        errors=errors,
        metadata={
            "skipped": stats.skipped,
            "superseded": stats.superseded,
            "source_url": settings.budgets_dataset_url,
        },
    )


__all__ = ["run"]
