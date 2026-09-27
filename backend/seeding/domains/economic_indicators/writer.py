"""Persist economic indicator records."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Set, Tuple

from models import Country, DocumentType, EconomicIndicator, Entity, SourceDocument
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ...config import SeedingSettings
from ...types import DomainRunContext
from .parser import EconomicIndicatorRecord

logger = logging.getLogger("seeding.economic_indicators.writer")

_DEFAULT_PUBLISHER = "Kenya National Bureau of Statistics"


@dataclass
class PersistenceStats:
    processed: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def _resolve_entity(
    session: Session, record: EconomicIndicatorRecord
) -> tuple[Optional[Entity], Optional[str]]:
    if record.entity_slug:
        stmt = select(Entity).where(Entity.slug == record.entity_slug)
        entity = session.execute(stmt).scalar_one_or_none()
        if entity:
            return entity, None
        msg = f"Unknown entity slug '{record.entity_slug}'"
        logger.warning(msg, extra={"entity_slug": record.entity_slug})
        return None, msg

    if record.entity_name:
        stmt = select(Entity).where(Entity.canonical_name == record.entity_name)
        entity = session.execute(stmt).scalar_one_or_none()
        if entity:
            return entity, None
        msg = f"Unknown entity name '{record.entity_name}'"
        logger.warning(msg, extra={"entity_name": record.entity_name})
        return None, msg

    return None, None


def _resolve_country_id(session: Session, entity: Optional[Entity]) -> Optional[int]:
    if entity:
        return entity.country_id
    stmt = select(Country.id).order_by(Country.id.asc())
    return session.execute(stmt).scalar_one_or_none()


def _ensure_source_document(
    session: Session,
    country_id: int,
    settings: SeedingSettings,
    record: EconomicIndicatorRecord,
) -> SourceDocument:
    url = record.source_url or settings.economic_indicators_dataset_url
    # The row declares who published it. This was a literal "Kenya National
    # Bureau of Statistics" for every URL, so each World Bank API document
    # was filed under KNBS (issue #232). Undeclared rows (the fixture) keep
    # the old default, which is what the fixture's own `source` text cites.
    publisher = (
        str(record.metadata.get("publisher") or "").strip()
        or _DEFAULT_PUBLISHER
    )
    stmt = select(SourceDocument).where(SourceDocument.url == url)
    source = session.execute(stmt).scalar_one_or_none()
    if source is not None and record.metadata.get("publisher"):
        if source.publisher != publisher:
            source.publisher = publisher
    if source is None:
        source = SourceDocument(
            country_id=country_id,
            publisher=publisher,
            title=settings.dataset_title("economic_indicators"),
            url=url,
            file_path=None,
            fetch_date=datetime.now(timezone.utc),
            doc_type=DocumentType.REPORT,
            md5=None,
            meta={"dataset_id": record.dataset_id} if record.dataset_id else {},
        )
        session.add(source)
        session.flush()
    return source


def _apply_updates(
    indicator: EconomicIndicator,
    record: EconomicIndicatorRecord,
    source_document_id: int,
) -> bool:
    updated = False

    def _set(attr: str, value: object) -> None:
        nonlocal updated
        if getattr(indicator, attr) != value:
            setattr(indicator, attr, value)
            updated = True

    _set("value", record.value)
    _set("unit", record.unit)
    _set("source_document_id", source_document_id)

    meta: Dict[str, object] = dict(indicator.meta or {})
    desired_meta = dict(record.metadata)
    if record.dataset_id:
        desired_meta.setdefault("dataset_id", record.dataset_id)
    if meta != desired_meta:
        indicator.meta = desired_meta
        updated = True

    return updated


def persist_economic_records(
    session: Session,
    records: Iterable[EconomicIndicatorRecord],
    settings: SeedingSettings,
    context: DomainRunContext,
) -> PersistenceStats:
    stats = PersistenceStats()

    for record in records:
        stats.processed += 1

        entity, entity_error = _resolve_entity(session, record)
        if entity_error:
            stats.errors.append(entity_error)
            stats.skipped += 1
            continue

        country_id = _resolve_country_id(session, entity)
        if country_id is None:
            msg = "Unable to resolve country for economic indicator"
            logger.error(msg)
            stats.errors.append(msg)
            stats.skipped += 1
            continue

        source = _ensure_source_document(session, country_id, settings, record)

        conditions = [
            EconomicIndicator.indicator_type == record.indicator_type,
            EconomicIndicator.indicator_date == record.indicator_date,
        ]
        if entity is None:
            conditions.append(EconomicIndicator.entity_id.is_(None))
        else:
            conditions.append(EconomicIndicator.entity_id == entity.id)

        stmt = select(EconomicIndicator).where(and_(*conditions))
        existing = session.execute(stmt).scalar_one_or_none()

        metadata = dict(record.metadata)
        if record.dataset_id:
            metadata.setdefault("dataset_id", record.dataset_id)

        if existing is None:
            indicator = EconomicIndicator(
                indicator_type=record.indicator_type,
                indicator_date=record.indicator_date,
                value=record.value,
                entity_id=entity.id if entity else None,
                unit=record.unit,
                source_document_id=source.id,
                meta=metadata,
            )
            session.add(indicator)
            stats.created += 1
        else:
            if _apply_updates(existing, record, source.id):
                stats.updated += 1

    return stats


#: A sweep that wants to delete more than this many rows of one type in one
#: run is more likely a malformed source than that many stale rows. The first
#: production run removes five in total (verified on a 2026-09-26 clone).
MAX_SUPERSEDED_PER_TYPE = 12


def remove_superseded_rows(
    session: Session, coverage: Dict[str, Set[str]]
) -> Tuple[List[Tuple[str, str, float]], List[str]]:
    """Delete national rows a live source has proven cannot be right.

    ``coverage`` is :attr:`..fetcher.EconomicPayload.coverage`: for each type
    a live source delivered THIS run, the dates it delivered. A national row
    of that type, inside the delivered span, at a date the source did not
    deliver, was written by something other than the owner — bootstrap's
    literal ``inflation_rate`` 2024-06-30 = 4.6, the fixture's 12-month 3.3
    filed in the annual-average series at 2025-01-31, or a CBK month that has
    since failed the cross-check.

    Returns ``(removed, errors)``: ``(type, date, value)`` per deleted row,
    and one error per type whose sweep was REFUSED for exceeding
    :data:`MAX_SUPERSEDED_PER_TYPE` — nothing of that type is deleted, and
    the refusal reaches the job row rather than a log line.

    An empty coverage (live sources down) deletes nothing: the sweep only
    ever acts on evidence gathered in the same run.
    """
    from .fetcher import superseded_by_live

    removed: List[Tuple[str, str, float]] = []
    errors: List[str] = []
    if not coverage:
        return removed, errors
    rows = session.execute(
        select(EconomicIndicator).where(
            EconomicIndicator.indicator_type.in_(sorted(coverage)),
            EconomicIndicator.entity_id.is_(None),
        )
    ).scalars()
    doomed: Dict[str, List[EconomicIndicator]] = {}
    for row in list(rows):
        day = row.indicator_date.date().isoformat()
        if superseded_by_live(row.indicator_type, day, coverage):
            doomed.setdefault(row.indicator_type, []).append(row)
    for kind, victims in sorted(doomed.items()):
        if len(victims) > MAX_SUPERSEDED_PER_TYPE:
            msg = (
                f"Refused to remove {len(victims)} superseded {kind} rows "
                f"(limit {MAX_SUPERSEDED_PER_TYPE}); the live source's coverage "
                "looks malformed"
            )
            logger.error(msg)
            errors.append(msg)
            continue
        for row in victims:
            day = row.indicator_date.date().isoformat()
            removed.append((kind, day, float(row.value)))
            logger.info("Removed superseded %s %s = %s", kind, day, row.value)
            session.delete(row)
    return removed, errors


__all__ = ["PersistenceStats", "persist_economic_records", "remove_superseded_rows"]
