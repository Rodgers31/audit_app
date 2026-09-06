"""Who currently governs each county, from the Council of Governors.

The governor on a county page came from ``enhanced_county_data.json``, typed
in once and 377 days old, and the frontend carried a second hardcoded list of
its own. Neither could notice an election. This domain reads the 47 names from
the body whose membership they are.

Nothing partial is written: the extractor refuses unless all 47 counties are
listed exactly once, because a page that lists 46 has changed shape rather
than a country having lost a county.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List

from models import Country, DocumentType, Entity, EntityType
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import SeedingSettings
from ...extractors.cog_governors import (
    EXTRACTOR_ID,
    PUBLISHER,
    SOURCE_URL,
    GovernorsError,
    parse_governors,
)
from ...freshness import mark_fixture, mark_live
from ...http_client import create_http_client
from ...registries import register_domain
from ...types import DomainRunContext, DomainRunResult

logger = logging.getLogger("seeding.county_officials")

#: cog.go.ke's CDN answers the seeder's default ``Accept: */*`` with a
#: challenge page; a browser-shaped pair of headers gets the real HTML, the
#: same accommodation the COB fetcher makes.
_HTML_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; KenyaAuditAppSeeder/1.0; "
        "+https://github.com/Rodgers31/audit_app-)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _ensure_source_document(session: Session, country_id: int):
    from models import SourceDocument

    doc = session.execute(
        select(SourceDocument).where(SourceDocument.url == SOURCE_URL)
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if doc is None:
        doc = SourceDocument(
            country_id=country_id,
            title="Council of Governors — Current Governors",
            url=SOURCE_URL,
            publisher=PUBLISHER,
            doc_type=DocumentType.REPORT,
            fetch_date=now,
            meta={"extractor": EXTRACTOR_ID},
        )
        session.add(doc)
    else:
        doc.fetch_date = now
    session.flush()
    return doc


@register_domain("county_officials")
def run(
    session: Session, settings: SeedingSettings, context: DomainRunContext
) -> DomainRunResult:
    started_at = datetime.now(timezone.utc)
    errors: List[str] = []
    metadata: Dict[str, object] = {"source_url": SOURCE_URL}

    country = session.execute(
        select(Country).where(Country.iso_code == "KEN")
    ).scalar_one_or_none()
    if country is None:
        return (
            DomainRunResult.empty(
                domain="county_officials",
                dry_run=context.dry_run,
                started_at=started_at,
            )
            .with_error("Kenya country row missing — run bootstrap first")
            .model_copy(update={"finished_at": datetime.now(timezone.utc)})
        )

    with create_http_client(settings) as client:
        try:
            response = client.get(
                SOURCE_URL, headers=_HTML_HEADERS, raise_for_status=True
            )
            governors = parse_governors(response.text)
        except GovernorsError as exc:
            # A shape change, not a network failure: record the reason and
            # leave every county's name as it was rather than writing part of
            # a list.
            mark_fixture(
                "county_officials", reason=f"cog_{exc.reason}", detail=str(exc)
            )
            metadata["quarantine_reason"] = exc.reason
            errors.append(str(exc))
            logger.warning("county officials quarantined: %s", exc)
            return DomainRunResult(
                domain="county_officials",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                items_processed=0,
                items_created=0,
                items_updated=0,
                dry_run=context.dry_run,
                errors=errors,
                metadata=metadata,
            )
        except Exception as exc:  # noqa: BLE001 - network path
            mark_fixture(
                "county_officials",
                reason="source_unreachable",
                detail=f"{type(exc).__name__}: {exc}",
            )
            metadata["quarantine_reason"] = "source_unreachable"
            errors.append(str(exc))
            logger.warning("Council of Governors unreachable: %s", exc)
            return DomainRunResult(
                domain="county_officials",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                items_processed=0,
                items_created=0,
                items_updated=0,
                dry_run=context.dry_run,
                errors=errors,
                metadata=metadata,
            )

    doc = _ensure_source_document(session, country.id)
    entities = {
        e.canonical_name: e
        for e in session.execute(
            select(Entity).where(Entity.type == EntityType.COUNTY)
        )
        .scalars()
        .all()
    }

    unresolved = [
        county
        for county in governors.by_county
        if f"{county} County" not in entities
    ]
    if unresolved:
        mark_fixture(
            "county_officials",
            reason="county_entities_unresolved",
            detail=f"{len(unresolved)} unmatched: {', '.join(sorted(unresolved))}",
        )
        metadata["quarantine_reason"] = "county_entities_unresolved"
        errors.append(f"{len(unresolved)} county/ies match no entity")
        return DomainRunResult(
            domain="county_officials",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            items_processed=0,
            items_created=0,
            items_updated=0,
            dry_run=context.dry_run,
            errors=errors,
            metadata=metadata,
        )

    updated = unchanged = 0
    for county, name in sorted(governors.by_county.items()):
        entity = entities[f"{county} County"]
        meta = dict(entity.meta or {})
        provenance = {
            "source": PUBLISHER,
            "source_url": SOURCE_URL,
            "source_document_id": doc.id,
            "extractor": EXTRACTOR_ID,
            "fetched_at": doc.fetch_date.isoformat() if doc.fetch_date else None,
        }
        if meta.get("governor") == name and meta.get("governor_provenance"):
            meta["governor_provenance"] = provenance
            unchanged += 1
        else:
            meta["governor"] = name
            meta["governor_provenance"] = provenance
            updated += 1
        entity.meta = meta
        session.add(entity)
    session.flush()

    mark_live(
        "county_officials",
        detail=(
            f"{len(governors.by_county)} governors from the Council of "
            f"Governors ({SOURCE_URL})"
        ),
    )
    for check in governors.checks:
        logger.info("Council of Governors check: %s", check)
    metadata.update(
        {
            "governors": len(governors.by_county),
            "checks": governors.checks,
            "source_document_id": doc.id,
        }
    )
    return DomainRunResult(
        domain="county_officials",
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        items_processed=len(governors.by_county),
        items_created=0,
        items_updated=updated,
        dry_run=context.dry_run,
        errors=errors,
        metadata=metadata,
    )


__all__ = ["run"]
