"""Population data seeding domain."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from models import Country
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import SeedingSettings
from ...http_client import create_http_client
from ...freshness import mark_live, mark_partial
from ...registries import register_domain
from ...types import DomainRunContext, DomainRunResult
from . import census_counties, fetcher, parser, writer

logger = logging.getLogger("seeding.population")


@register_domain("population")
def run(
    session: Session, settings: SeedingSettings, context: DomainRunContext
) -> DomainRunResult:
    started_at = datetime.now(timezone.utc)
    errors: list[str] = []

    with create_http_client(settings) as client:
        try:
            payload = fetcher.fetch_population_payload(client, settings)
        except Exception as exc:  # pragma: no cover - network failure path
            logger.exception(
                "Failed to fetch population payload", extra={"error": str(exc)}
            )
            return (
                DomainRunResult.empty(
                    domain="population",
                    dry_run=context.dry_run,
                    started_at=started_at,
                )
                .with_error(str(exc))
                .model_copy(update={"finished_at": datetime.now(timezone.utc)})
            )

    records = parser.parse_population_payload(payload)
    stats = writer.persist_population_records(session, records, context)

    errors.extend(stats.errors)

    # ── county populations, from the census itself ────────────────────
    # The fetcher above marked this domain `partial / no_live_county_source`,
    # which was true for as long as the county breakdown came from a fixture.
    # It no longer has to: KNBS publishes the count per county in Volume I of
    # the 2019 census, and census_counties reads it under gates the table
    # itself supplies. A failure here leaves the fetcher's marking standing —
    # the domain does not get to call itself live on a census it could not
    # read.
    census = census_counties.CensusLoadStats()
    if context.dry_run:
        logger.info("dry run — not fetching the census volume")
    else:
        country = session.execute(
            select(Country).where(Country.iso_code == "KEN")
        ).scalar_one_or_none()
        if country is None:
            errors.append("Kenya country row missing — run bootstrap first")
        else:
            with create_http_client(settings) as client:
                try:
                    census = census_counties.load_census_population(
                        session, client, settings, country_id=country.id
                    )
                except Exception as exc:  # noqa: BLE001 - never fail the run
                    logger.exception("census county population failed")
                    census.quarantine_reason = f"unhandled({type(exc).__name__})"
                    census.errors.append(str(exc))
            errors.extend(census.errors)

            if census.processed and not census.quarantine_reason:
                mark_live(
                    "population",
                    detail=(
                        f"{census.processed} county populations from the 2019 "
                        f"census (KNBS Volume I, Table 2.2)"
                        + (
                            f"; national series from World Bank SP.POP.*"
                            if payload
                            else ""
                        )
                    ),
                )
            elif census.quarantine_reason:
                mark_partial(
                    "population",
                    reason=f"census_{census.quarantine_reason}",
                    detail=(
                        "the county breakdown stays on the fixture: the census "
                        f"volume was refused ({census.quarantine_reason})"
                    ),
                )

    finished_at = datetime.now(timezone.utc)

    return DomainRunResult(
        domain="population",
        started_at=started_at,
        finished_at=finished_at,
        items_processed=stats.processed + census.processed,
        items_created=stats.created + census.created,
        items_updated=stats.updated + census.updated,
        dry_run=context.dry_run,
        errors=errors,
        metadata={
            "skipped": stats.skipped,
            "source_url": settings.population_dataset_url,
            "census_counties": {
                "processed": census.processed,
                "created": census.created,
                "updated": census.updated,
                "unchanged": census.skipped,
                "quarantine_reason": census.quarantine_reason,
                "source_url": census_counties.CENSUS_VOLUME_I_URL,
            },
        },
    )


__all__ = ["run"]
