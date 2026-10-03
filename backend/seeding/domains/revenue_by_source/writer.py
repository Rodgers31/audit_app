"""Persist revenue-by-source records."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

from models import Country, DocumentType, RevenueBySource, SourceDocument
from sqlalchemy import and_, select
from sqlalchemy.orm import Session
from services.response_receipts import persist_evidence

from ...config import SeedingSettings
from ...types import DomainRunContext
from .parser import RevenueBySourceRecord

logger = logging.getLogger("seeding.revenue_by_source.writer")

_DEFAULT_PUBLISHER = "Kenya Revenue Authority"
_DEFAULT_TITLE = "KRA Annual Revenue Performance Report"


@dataclass
class PersistenceStats:
    processed: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def _resolve_country_id(session: Session) -> Optional[int]:
    stmt = select(Country.id).order_by(Country.id.asc())
    return session.execute(stmt).scalar_one_or_none()


def _ensure_source_document(
    session: Session,
    country_id: int,
    settings: SeedingSettings,
    record: RevenueBySourceRecord,
) -> SourceDocument:
    url = record.source_url or settings.revenue_by_source_dataset_url
    # The row declares who published it. This was a literal "Kenya Revenue
    # Authority" / "KRA Annual Revenue Performance Report" for every URL, so
    # the World Bank headline totals were filed as a KRA report (issue #267;
    # the same defect as #232 in economic_indicators). Undeclared rows (the
    # fixture, which cites KRA press releases) keep the old default.
    publisher = record.publisher or _DEFAULT_PUBLISHER
    title = record.source_title or _DEFAULT_TITLE
    stmt = select(SourceDocument).where(SourceDocument.url == url)
    source = session.execute(stmt).scalar_one_or_none()
    if source is not None:
        # Only a declaration corrects an existing document; the default is
        # for creating one. Otherwise an undeclared row at the same URL would
        # reset a correct label on every run.
        if record.publisher and source.publisher != record.publisher:
            logger.info(
                "Relabelled source document %s publisher %r -> %r",
                source.id, source.publisher, record.publisher,
            )
            source.publisher = record.publisher
        if record.source_title and source.title != record.source_title:
            logger.info(
                "Relabelled source document %s title %r -> %r",
                source.id, source.title, record.source_title,
            )
            source.title = record.source_title
    if source is None:
        source = SourceDocument(
            country_id=country_id,
            publisher=publisher,
            title=title,
            url=url,
            file_path=None,
            fetch_date=datetime.now(timezone.utc),
            doc_type=DocumentType.REPORT,
            md5=None,
            meta={},
        )
        session.add(source)
        session.flush()
    return source


def _apply_updates(
    row: RevenueBySource,
    record: RevenueBySourceRecord,
    source_document_id: int,
) -> bool:
    # An unavailable observation cannot re-label a retained actual with a
    # fixture/projection's source. Explicit withdrawals are handled below.
    if row.amount_billion_kes is not None and record.amount_billion_kes is None and not record.metadata.get("absent_reason"):
        return False
    updated = False

    def _set(attr: str, value: object) -> None:
        nonlocal updated
        if getattr(row, attr) != value:
            setattr(row, attr, value)
            updated = True

    _set("category", record.category)
    if record.amount_billion_kes is not None or record.metadata.get("absent_reason"):
        _set("amount_billion_kes", record.amount_billion_kes)
    _set("target_billion_kes", record.target_billion_kes)
    _set("performance_pct", record.performance_pct)
    _set("share_of_total_pct", record.share_of_total_pct)
    _set("yoy_growth_pct", record.yoy_growth_pct)
    _set("source_document_id", source_document_id)
    if record.metadata:
        _set("meta", record.metadata)

    if updated:
        row.updated_at = datetime.now(timezone.utc)

    return updated


def persist_revenue_records(
    session: Session,
    records: Iterable[RevenueBySourceRecord],
    settings: SeedingSettings,
    context: DomainRunContext,
) -> PersistenceStats:
    stats = PersistenceStats()
    country_id = _resolve_country_id(session)
    if country_id is None:
        stats.errors.append("No country found in database — seed countries first")
        return stats

    for record in records:
        stats.processed += 1
        try:
            source = _ensure_source_document(session, country_id, settings, record)
            record.metadata["source_evidence"] = persist_evidence(session, source, record.metadata.get("source_evidence"))

            stmt = select(RevenueBySource).where(
                and_(
                    RevenueBySource.fiscal_year == record.fiscal_year,
                    RevenueBySource.revenue_type == record.revenue_type,
                )
            )
            existing = session.execute(stmt).scalar_one_or_none()

            if existing:
                if _apply_updates(existing, record, source.id):
                    stats.updated += 1
                    logger.debug(
                        "Updated revenue record",
                        extra={
                            "fiscal_year": record.fiscal_year,
                            "revenue_type": record.revenue_type,
                        },
                    )
                else:
                    stats.skipped += 1
            else:
                new_row = RevenueBySource(
                    fiscal_year=record.fiscal_year,
                    revenue_type=record.revenue_type,
                    category=record.category,
                    amount_billion_kes=record.amount_billion_kes,
                    target_billion_kes=record.target_billion_kes,
                    performance_pct=record.performance_pct,
                    share_of_total_pct=record.share_of_total_pct,
                    yoy_growth_pct=record.yoy_growth_pct,
                    source_document_id=source.id,
                    meta=record.metadata,
                )
                session.add(new_row)
                stats.created += 1
                logger.debug(
                    "Created revenue record",
                    extra={
                        "fiscal_year": record.fiscal_year,
                        "revenue_type": record.revenue_type,
                    },
                )

            if not context.dry_run:
                session.flush()

        except Exception as exc:
            msg = (
                f"Error persisting revenue record "
                f"{record.fiscal_year}/{record.revenue_type}: {exc}"
            )
            logger.warning(msg)
            stats.errors.append(msg)

    return stats
