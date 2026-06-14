"""IMF World Economic Outlook seeding domain.

Fetches a small bundle of Kenya-focused macro indicators from the IMF
DataMapper API and upserts them into ``imf_weo_observations``.

Powers ``/api/v1/debt/broader`` — the dashboard card that shows IMF's
general-government gross debt alongside CBK's central-government figure.

Runs as part of the nightly seeding pipeline. IMF only publishes a new
WEO vintage twice a year (April and October), so most nightly runs
produce zero diffs; the seeder is idempotent by ``(country, indicator,
year, vintage)``.
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

logger = logging.getLogger("seeding.imf_weo")


@register_domain("imf_weo")
def run(
    session: Session, settings: SeedingSettings, context: DomainRunContext
) -> DomainRunResult:
    started_at = datetime.now(timezone.utc)
    errors: list[str] = []

    with create_http_client(settings) as client:
        try:
            payload = fetcher.fetch_imf_weo(client, settings)
        except Exception as exc:
            # Swallow — IMF being down is not a reason to fail the
            # whole seeding run. Other indicators are independent.
            logger.warning("IMF WEO fetch failed: %s", exc)
            return (
                DomainRunResult.empty(
                    domain="imf_weo", dry_run=context.dry_run, started_at=started_at
                )
                .with_error(str(exc))
                .model_copy(update={"finished_at": datetime.now(timezone.utc)})
            )

    # Restrict to the countries we actually want in the DB. IMF's
    # DataMapper returns the global dataset regardless of URL filter,
    # which would otherwise flood us with ~200 countries and aggregate
    # codes (some of which exceed VARCHAR(3)).
    records = parser.parse_imf_weo(
        payload, vintage=started_at, only_countries=fetcher.COUNTRIES
    )
    stats = writer.persist_imf_weo(session, records, context)
    errors.extend(stats.errors)

    return DomainRunResult(
        domain="imf_weo",
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        items_processed=stats.processed,
        items_created=stats.created,
        items_updated=stats.updated,
        dry_run=context.dry_run,
        errors=errors,
        metadata={
            "skipped": stats.skipped,
            "indicators": list(fetcher.INDICATORS),
            "countries": list(fetcher.COUNTRIES),
        },
    )


__all__ = ["run"]
