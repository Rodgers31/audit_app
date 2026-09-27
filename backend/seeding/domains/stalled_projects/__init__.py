"""Stalled projects seeder domain.

Source: the per-county "Stalled Projects" tables in the Controller of
Budget's County Governments Budget Implementation Review Report (CBIRR),
reported to COB by each county treasury. See ``fetcher.py`` and
``cob_parser.py``; issue #230 for why the previous fixture was removed.

Every run removes what remains of the invented fixture records. A run that
cannot read the newest edition refuses and leaves the previously ingested
edition in place.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...config import SeedingSettings
from ...http_client import create_http_client
from ...registries import register_domain
from ...types import DomainRunContext, DomainRunResult
from . import fetcher, writer

logger = logging.getLogger("seeding.stalled_projects")


def _edition_ref(edition: dict | None) -> dict | None:
    if not edition:
        return None
    return {
        k: edition.get(k)
        for k in ("wpdmdl", "url", "sha256", "server_fingerprint", "fiscal_year", "period", "as_of")
    }


@register_domain("stalled_projects")
def run(
    session: Session, settings: SeedingSettings, context: DomainRunContext
) -> DomainRunResult:
    started_at = datetime.now(timezone.utc)
    with create_http_client(settings) as client:
        result = fetcher.fetch(settings, client)

    metadata: dict = {"cbirr_listing_newest": result.listing_newest}
    errors: list[str] = []
    if result.ok:
        stats = writer.write(result.counties, result.edition, session, dry_run=context.dry_run)
        rows = stats["rows"]
        metadata.update(
            cbirr_ingested=_edition_ref(result.edition),
            cbirr_published=_edition_ref(result.edition),
            captions_found=result.edition.get("captions_found"),
            rows_parsed=sum(c["reconciliation"]["rows"] for c in result.counties),
            rows_written=rows,
            counties_written=stats["counties"],
            unmatched_counties=stats["unmatched"],
        )
        if stats["unmatched"]:
            errors.append(f"no county entity for {stats['unmatched']}")
        items_processed = metadata["rows_parsed"]
        items_updated = stats["counties"]
    else:
        # Refused: keep the previous COB edition, but never the invented rows.
        cleared = writer.clear_owned_keys(session, dry_run=context.dry_run, legacy_only=True)
        metadata.update(
            cbirr_published=_edition_ref(writer.published_edition(session)),
            refused_edition=_edition_ref(result.edition) if result.edition else None,
            captions_found=(result.edition or {}).get("captions_found"),
            rows_parsed=0,
            cleared_legacy_keys=cleared["keys"],
        )
        errors.append(f"refused ({result.reason}): {result.detail}")
        items_processed = 0
        items_updated = 0

    return DomainRunResult(
        domain="stalled_projects",
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        items_processed=items_processed,
        items_created=0,
        items_updated=items_updated,
        dry_run=context.dry_run,
        errors=errors,
        metadata=metadata,
    )
