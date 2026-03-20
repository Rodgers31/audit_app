"""Persist audit records."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from typing import Iterable, List, Optional, Tuple

from models import Audit, DocumentType, Entity, FiscalPeriod, Severity, SourceDocument
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ...config import SeedingSettings
from ...types import DomainRunContext
from .parser import AuditRecord

logger = logging.getLogger("seeding.audits.writer")


@dataclass
class PersistenceStats:
    processed: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)


def _ensure_source_document(
    session: Session,
    country_id: int,
    settings: SeedingSettings,
    record: AuditRecord,
) -> SourceDocument:
    url = record.source_url or settings.audits_dataset_url
    stmt = select(SourceDocument).where(SourceDocument.url == url)
    source = session.execute(stmt).scalar_one_or_none()
    if source is None:
        source = SourceDocument(
            country_id=country_id,
            publisher="Office of the Auditor-General",
            title=settings.dataset_title("audits"),
            url=url,
            file_path=None,
            fetch_date=datetime.now(timezone.utc),
            doc_type=DocumentType.AUDIT,
            md5=None,
            meta={"dataset_id": record.dataset_id, "reference": record.reference},
        )
        session.add(source)
        session.flush()
    return source


def _ensure_period(
    session: Session,
    country_id: int,
    record: AuditRecord,
) -> FiscalPeriod:
    stmt = select(FiscalPeriod).where(
        and_(
            FiscalPeriod.country_id == country_id,
            FiscalPeriod.label == record.period_label,
        )
    )
    period = session.execute(stmt).scalar_one_or_none()
    if period is None:
        period = FiscalPeriod(
            country_id=country_id,
            label=record.period_label,
            start_date=datetime.combine(
                record.start_date, time.min, tzinfo=timezone.utc
            ),
            end_date=datetime.combine(record.end_date, time.max, tzinfo=timezone.utc),
        )
        session.add(period)
        session.flush()
    return period


def _resolve_entity(
    session: Session, record: AuditRecord
) -> Tuple[Optional[Entity], Optional[str]]:
    stmt = select(Entity).where(Entity.slug == record.entity_slug)
    entity = session.execute(stmt).scalar_one_or_none()
    if entity is None:
        msg = f"Unknown entity slug '{record.entity_slug}'"
        logger.warning(msg, extra={"entity_slug": record.entity_slug})
        return None, msg
    return entity, None


def _parse_severity(value: str) -> Optional[Severity]:
    normalized = value.strip().upper().replace(" ", "_")
    try:
        return Severity[normalized]
    except KeyError:
        for member in Severity:
            if member.value.upper() == normalized:
                return member
        return None


def persist_audit_records(
    session: Session,
    records: Iterable[AuditRecord],
    settings: SeedingSettings,
    context: DomainRunContext,
) -> PersistenceStats:
    stats = PersistenceStats()

    for record in records:
        stats.processed += 1

        severity = _parse_severity(record.severity)
        if severity is None:
            msg = f"Unsupported severity '{record.severity}'"
            logger.warning(msg, extra={"entity_slug": record.entity_slug})
            stats.errors.append(msg)
            stats.skipped += 1
            continue

        entity, error = _resolve_entity(session, record)
        if error:
            stats.errors.append(error)
            stats.skipped += 1
            continue
        assert entity is not None

        source = _ensure_source_document(session, entity.country_id, settings, record)
        period = _ensure_period(session, entity.country_id, record)

        stmt = select(Audit).where(
            and_(
                Audit.entity_id == entity.id,
                Audit.period_id == period.id,
                Audit.finding_text == record.finding_text,
            )
        )
        existing = session.execute(stmt).scalar_one_or_none()

        # Build rich provenance with all available metadata
        prov_entry: dict = {}
        if record.dataset_id:
            prov_entry["dataset_id"] = record.dataset_id
        if record.reference:
            prov_entry["reference"] = record.reference
        if record.amount is not None:
            prov_entry["amount"] = record.amount
        if record.query_type:
            prov_entry["category"] = record.query_type
        if record.status:
            prov_entry["status"] = record.status
        if record.audit_year:
            prov_entry["audit_year"] = record.audit_year
        if record.source_url:
            prov_entry["source_url"] = record.source_url
        provenance = [prov_entry] if prov_entry else []

        # Parse audit_year as integer
        audit_year_int = None
        if record.audit_year is not None:
            try:
                audit_year_int = int(record.audit_year)
            except (ValueError, TypeError):
                pass

        if existing is None:
            audit = Audit(
                entity_id=entity.id,
                period_id=period.id,
                finding_text=record.finding_text,
                severity=severity,
                recommended_action=record.recommended_action,
                source_document_id=source.id,
                provenance=provenance,
                query_type=record.query_type,
                amount=record.amount,
                status=record.status,
                audit_year=audit_year_int,
                external_reference=record.reference,
            )
            session.add(audit)
            stats.created += 1
        else:
            updated = False
            if existing.severity != severity:
                existing.severity = severity
                updated = True
            if (
                record.recommended_action
                and existing.recommended_action != record.recommended_action
            ):
                existing.recommended_action = record.recommended_action
                updated = True
            if existing.source_document_id != source.id:
                existing.source_document_id = source.id
                updated = True
            # Always refresh provenance with rich data
            if provenance and existing.provenance != provenance:
                existing.provenance = provenance
                updated = True
            # Update new structured columns
            if record.query_type and existing.query_type != record.query_type:
                existing.query_type = record.query_type
                updated = True
            if record.amount is not None and existing.amount != record.amount:
                existing.amount = record.amount
                updated = True
            if record.status and existing.status != record.status:
                existing.status = record.status
                updated = True
            if audit_year_int is not None and existing.audit_year != audit_year_int:
                existing.audit_year = audit_year_int
                updated = True
            if record.reference and existing.external_reference != record.reference:
                existing.external_reference = record.reference
                updated = True
            if updated:
                stats.updated += 1

    return stats


__all__ = ["PersistenceStats", "persist_audit_records"]
__all__ = ["PersistenceStats", "persist_audit_records"]
