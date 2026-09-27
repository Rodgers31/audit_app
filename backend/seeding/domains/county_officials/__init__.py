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
    DEPUTIES_SOURCE_URL,
    EXTRACTOR_ID,
    PUBLISHER,
    SOURCE_URL,
    Governors,
    GovernorsError,
    parse_deputy_governors,
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


def _ensure_source_document(
    session: Session,
    country_id: int,
    url: str = SOURCE_URL,
    title: str = "Council of Governors — Current Governors",
):
    from models import SourceDocument

    doc = session.execute(
        select(SourceDocument).where(SourceDocument.url == url)
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if doc is None:
        doc = SourceDocument(
            country_id=country_id,
            title=title,
            url=url,
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


def _fetch_deputies(client):
    """(parsed deputies, None) or (None, (reason, detail))."""
    try:
        response = client.get(
            DEPUTIES_SOURCE_URL, headers=_HTML_HEADERS, raise_for_status=True
        )
        return parse_deputy_governors(response.text), None
    except GovernorsError as exc:
        return None, (f"cog_{exc.reason}", str(exc))
    except Exception as exc:  # noqa: BLE001 - network path
        return None, ("source_unreachable", f"{type(exc).__name__}: {exc}")


def _write_deputies(
    session: Session,
    country_id: int,
    entities: Dict[str, Entity],
    governors: Governors,
    deputies: Governors,
) -> List[str]:
    """Store each listed deputy with provenance, and REMOVE the stored deputy
    of any county the Council no longer lists. Keeping it would show last
    year's name for a seat that is now vacant.

    A deputy with the same name as the county's governor is dropped. That is
    what an elevation looks like while one page lags the other (Meru, 2024),
    and showing one person in both roles is wrong either way.
    """
    doc = _ensure_source_document(
        session,
        country_id,
        url=DEPUTIES_SOURCE_URL,
        title="Council of Governors — Current Deputy Governors",
    )
    provenance = {
        "source": PUBLISHER,
        "source_url": DEPUTIES_SOURCE_URL,
        "source_document_id": doc.id,
        "extractor": EXTRACTOR_ID,
        "fetched_at": doc.fetch_date.isoformat() if doc.fetch_date else None,
    }
    checks: List[str] = []
    for county_label, entity in entities.items():
        county = county_label.removesuffix(" County")
        name = deputies.by_county.get(county)
        if name and name == governors.by_county.get(county):
            checks.append(f"dropped: {county} lists {name} as governor and deputy")
            name = None
        meta = dict(entity.meta or {})
        if name:
            meta["deputy_governor"] = name
            meta["deputy_governor_provenance"] = provenance
        else:
            meta.pop("deputy_governor", None)
            meta.pop("deputy_governor_provenance", None)
        entity.meta = meta
        session.add(entity)
    session.flush()
    return checks


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
            # Deputies are fetched only once the governors have parsed, and
            # their failure never blocks the governors. See _write_deputies.
            deputies, deputies_failure = _fetch_deputies(client)
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

    if deputies is not None:
        deputy_checks = _write_deputies(
            session, country.id, entities, governors, deputies
        )
        metadata["deputies"] = len(deputies.by_county) - sum(
            1 for c in deputy_checks if c.startswith("dropped:")
        )
        metadata["deputy_checks"] = deputies.checks + deputy_checks
    else:
        reason, detail = deputies_failure
        metadata["deputies_quarantine_reason"] = reason
        # An error, so the job reads COMPLETED_WITH_ERRORS and the nightly
        # prints [WARN]. Stored deputies are left as the last good run wrote
        # them, with that run's fetched_at.
        errors.append(f"deputy governors not updated ({reason}): {detail}")
        logger.warning("deputy governors not updated (%s): %s", reason, detail)

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
