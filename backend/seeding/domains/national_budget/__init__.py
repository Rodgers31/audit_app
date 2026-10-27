"""National budget execution seeding domain.

Seeds national government budget execution data by sector from
Controller of Budget (CoB) Annual National Government Budget Implementation
Review Reports (NG-BIRR).
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

logger = logging.getLogger("seeding.national_budget")


@register_domain("national_budget")
def run(
    session: Session, settings: SeedingSettings, context: DomainRunContext
) -> DomainRunResult:
    started_at = datetime.now(timezone.utc)
    errors: list[str] = []

    with create_http_client(settings) as client:
        try:
            payload = fetcher.fetch_national_budget_payload(client, settings, session=session, context=context)
        except Exception as exc:
            logger.exception(
                "Failed to fetch national_budget payload",
                extra={"error": str(exc)},
            )
            return (
                DomainRunResult.empty(
                    domain="national_budget",
                    dry_run=context.dry_run,
                    started_at=started_at,
                )
                .with_error(str(exc))
                .model_copy(update={"finished_at": datetime.now(timezone.utc)})
            )

    records = parser.parse_national_budget_payload(payload)
    stats = writer.persist_national_budget_records(session, records, settings, context)
    errors.extend(stats.errors)

    finished_at = datetime.now(timezone.utc)

    return DomainRunResult(
        domain="national_budget",
        started_at=started_at,
        finished_at=finished_at,
        items_processed=stats.processed,
        items_created=stats.created,
        items_updated=stats.updated,
        dry_run=context.dry_run,
        errors=errors,
        metadata={
            "skipped": stats.skipped,
            "source_url": settings.national_budget_execution_dataset_url,
        },
    )
