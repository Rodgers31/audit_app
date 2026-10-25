"""Persist national budget execution records to BudgetLine."""

from __future__ import annotations

import logging
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from decimal import Decimal
from typing import Iterable, Optional, Tuple

from models import (
    BudgetLine,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    Extraction,
    FiscalPeriod,
    SourceDocument,
)
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, load_only

from ...config import SeedingSettings
from ...types import DomainRunContext
from ...utils import compute_hash
from .parser import NationalBudgetRecord
from .sector_expenditure import EXPENDITURE_MEASURE

logger = logging.getLogger("seeding.national_budget.writer")


@dataclass
class PersistenceStats:
    processed: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    superseded: int = 0
    errors: list[str] = field(default_factory=list)


def _ensure_entity(
    session: Session, record: NationalBudgetRecord
) -> Tuple[Optional[Entity], Optional[str]]:
    """Find or create the national-government entity."""
    stmt = select(Entity).where(Entity.slug == record.entity_slug)
    entity = session.execute(stmt).scalar_one_or_none()
    if entity is None:
        # Try to create it — national-government may not exist yet
        from models import Country

        country = session.execute(
            select(Country).order_by(Country.id.asc())
        ).scalar_one_or_none()
        if country is None:
            msg = "No country found in database — run population seeder first"
            logger.error(msg)
            return None, msg

        entity = Entity(
            canonical_name=record.entity_name,
            slug=record.entity_slug,
            type=EntityType.NATIONAL,
            country_id=country.id,
        )
        session.add(entity)
        session.flush()
        logger.info(
            "Created entity '%s' (slug=%s)", record.entity_name, record.entity_slug
        )
    return entity, None


def _ensure_source_document(
    session: Session,
    country_id: int,
    settings: SeedingSettings,
    record: NationalBudgetRecord,
    *, sources_by_url: Optional[dict[str, SourceDocument]] = None,
) -> SourceDocument:
    url = record.source_url or settings.national_budget_execution_dataset_url
    source = sources_by_url.get(url) if sources_by_url is not None else None
    if source is None:
        source = session.execute(
            select(SourceDocument).options(load_only(SourceDocument.id)).where(SourceDocument.url == url)
        ).scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if source is None:
        source = SourceDocument(
            country_id=country_id,
            publisher="Controller of Budget",
            title=f"CoB Annual NG-BIRR {record.period_label}",
            url=url,
            file_path=None,
            fetch_date=now,
            doc_type=DocumentType.BUDGET,
            md5=None,
            # Registration/fixture parsing is not source acquisition. Match
            # bootstrap's unfetched status; only verified fetching can earn
            # AVAILABLE. Existing source evidence is left untouched below.
            status=DocumentStatus.FAILED,
            meta={"data_quality": record.data_quality or "official"},
        )
        session.add(source)
        session.flush()
    if sources_by_url is not None:
        sources_by_url[url] = source
    return source


def _ensure_period(
    session: Session,
    country_id: int,
    record: NationalBudgetRecord,
) -> FiscalPeriod:
    from ...utils import normalize_fiscal_label

    canonical = normalize_fiscal_label(record.period_label)
    stmt = select(FiscalPeriod).where(
        and_(
            FiscalPeriod.country_id == country_id,
            FiscalPeriod.label == canonical,
        )
    )
    period = session.execute(stmt).scalar_one_or_none()
    if period is None:
        period = FiscalPeriod(
            country_id=country_id,
            label=canonical,
            start_date=datetime.combine(
                record.start_date, time.min, tzinfo=timezone.utc
            ),
            end_date=datetime.combine(record.end_date, time.max, tzinfo=timezone.utc),
        )
        session.add(period)
        session.flush()
    return period


def _initialize_pdf_acquisition(session, source, originals, bound, initialized):
    """Initialize an unfetched registration from a real bound PDF acquisition.

    Existing acquisition history and operator archives belong to the document
    fetch/maintenance path. A fixture, exported JSON or local cached body has
    no authority here. A first acquisition reads retained bytes once, not once
    per financial cell; no publisher request or publication authority is added.
    """
    from urllib.parse import urlsplit
    from ...pdf_evidence import PdfCellEvidence
    from ...pdf_artifact import ARTIFACT_KEY
    from services.response_receipts import receipt_is_sealed

    for original, observation in zip(originals, bound):
        if not isinstance(original, PdfCellEvidence) or not isinstance(observation, dict):
            continue
        receipt = original.get("_response_receipt")
        reference = observation.get("receipt", {})
        if not isinstance(reference, dict):
            continue
        identity = reference.get("extraction_id")
        if (not receipt_is_sealed(receipt) or type(identity) is not int
                or identity in initialized):
            continue
        initialized.add(identity)
        if (source.status == DocumentStatus.ARCHIVED
                or any(getattr(source, field) is not None for field in
                       ("md5", "file_path", "content_type", "http_status", "last_verified_at"))):
            continue
        extraction = session.get(Extraction, identity)
        metadata = extraction.extracted_json if extraction is not None else None
        stored = metadata.get("response_receipt") if isinstance(metadata, dict) else None
        if (extraction is None or extraction.source_document_id != source.id
                or not isinstance(stored, dict) or stored != dict(receipt)
                or receipt._bound_source != [(source.id, source.country_id, source.publisher, source.url)]
                or reference.get("source_document_id") != source.id
                or reference.get("digest") != receipt.get("digest")
                or stored.get("digest") != receipt.get("digest")
                or type(stored.get("status")) is not int or stored["status"] != 200
                or stored.get("source_kind") != "pdf"
                or str(stored.get("content_type") or "").split(";")[0].strip().lower() != "application/pdf"
                or stored.get("request", {}).get("method") != "GET"
                or stored.get("request_url") != source.url
                or stored.get("byte_check", {}).get("status") != "matched"
                or stored.get("byte_check", {}).get("sha256") != stored.get("digest")):
            continue
        if session.get_bind().dialect.name == "postgresql":
            marker = SourceDocument.meta.has_key(ARTIFACT_KEY)
        elif session.get_bind().dialect.name == "sqlite":
            marker = func.json_type(SourceDocument.meta, "$."+ARTIFACT_KEY).isnot(None)
        else:
            continue
        if session.scalar(select(marker).where(SourceDocument.id == source.id)):
            # Project only marker presence, never the possibly large metadata.
            # An existing PDF binding belongs to the document maintainer.
            continue
        try:
            request = urlsplit(stored["request_url"])
            response = urlsplit(stored.get("response_url") or "")
            if (request.scheme != "https" or response.scheme != "https"
                    or request.username is not None or request.password is not None
                    or response.username is not None or response.password is not None
                    or (request.hostname or "").removeprefix("www.") !=
                       (response.hostname or "").removeprefix("www.")):
                continue
            acquired = datetime.fromisoformat(stored["acquired_at"])
            if acquired.utcoffset() is None:
                continue
            body = receipt._store.read(receipt["storage_key"])
            if (type(body) is not bytes or not 0 < len(body) <= 64*1024*1024
                    or len(body) != stored.get("byte_size")
                    or hashlib.sha256(body).hexdigest() != stored["digest"]
                    or not body.startswith(b"%PDF-") or not body[-2048:].rstrip().endswith(b"%%EOF")):
                continue
        except Exception:
            # Match receipt persistence's qualified-retention failure path.
            # Provider errors must not fabricate source acquisition fields.
            continue
        source.status = DocumentStatus.AVAILABLE
        source.http_status = 200
        source.content_type = "application/pdf"
        source.md5 = hashlib.md5(body, usedforsecurity=False).hexdigest()
        source.fetch_date = source.last_verified_at = source.last_seen_at = acquired


def _record_hash(record: NationalBudgetRecord, currency: str) -> str:
    return compute_hash(
        {
            "entity_slug": record.entity_slug,
            "period_label": record.period_label,
            "category": record.category,
            "subcategory": record.subcategory,
            "allocated": (
                str(record.allocated_amount)
                if record.allocated_amount is not None
                else None
            ),
            "actual": (
                str(record.actual_spent) if record.actual_spent is not None else None
            ),
            "committed": (
                str(record.committed_amount)
                if record.committed_amount is not None
                else None
            ),
            "currency": currency,
        }
    )


def _apply_line(
    line: BudgetLine,
    record: NationalBudgetRecord,
    currency: str,
    source_document_id: int,
    record_hash: str,
) -> bool:
    updated = False

    for attr, value in (
        ("allocated_amount", record.allocated_amount),
        ("actual_spent", record.actual_spent),
        ("committed_amount", record.committed_amount),
        ("currency", currency),
        ("source_document_id", source_document_id),
        ("notes", record.notes),
        ("page_ref", record.page_ref),
    ):
        if value is None:
            continue
        if isinstance(value, Decimal):
            current = getattr(line, attr)
            if current is None or current != value:
                setattr(line, attr, value)
                updated = True
        elif getattr(line, attr) != value:
            setattr(line, attr, value)
            updated = True

    if line.source_hash != record_hash:
        line.source_hash = record_hash
        updated = True

    return updated


def persist_national_budget_records(
    session: Session,
    records: Iterable[NationalBudgetRecord],
    settings: SeedingSettings,
    context: DomainRunContext,
) -> PersistenceStats:
    stats = PersistenceStats()
    # Invocation-local ORM identities never escape the caller's transaction.
    # A rollback or later run must resolve its sources from PostgreSQL again.
    sources_by_url: dict[str, SourceDocument] = {}
    initialized_acquisitions: set[int] = set()
    # (entity_id, period_id) pairs that received verified EXPENDITURE rows.
    expenditure_periods: set[tuple[int, int]] = set()

    for record in records:
        stats.processed += 1

        entity, error = _ensure_entity(session, record)
        if error:
            stats.errors.append(error)
            stats.skipped += 1
            continue
        assert entity is not None

        source = _ensure_source_document(session, entity.country_id, settings, record,
                                         sources_by_url=sources_by_url)
        period = _ensure_period(session, entity.country_id, record)

        # Match on entity + period + category + subcategory (natural key)
        stmt = select(BudgetLine).where(
            and_(
                BudgetLine.entity_id == entity.id,
                BudgetLine.period_id == period.id,
                BudgetLine.category == record.category,
                BudgetLine.subcategory == record.subcategory,
            )
        )
        existing = session.execute(stmt).scalar_one_or_none()

        currency = record.currency or settings.budget_default_currency
        provenance_entry: dict[str, object] = {
            "source": record.source or "CoB NG-BIRR",
            "data_quality": record.data_quality or "official",
        }
        if context.job_id is not None:
            provenance_entry["ingestion_job_id"] = context.job_id
        # Declared measure (and its evidence) travels with the row.
        provenance_entry.update({k:v for k,v in record.provenance_extra.items() if k != "_native_report_authority"})
        if record.provenance_extra.get("source_evidence"):
            from ...pdf_evidence import bind_pdf_evidence
            provenance_entry["source_evidence"] = bind_pdf_evidence(
                session, source, record.provenance_extra["source_evidence"],
                identity={"entity_id": entity.id, "geography": "KEN", "period": period.label,
                          "unit": currency, "basis": "actual", "dimensions": {
                              "category": record.category, "subcategory": record.subcategory,
                              "line_type": existing.line_type if existing else None}},
                values={"allocated_amount": record.allocated_amount, "actual_spent": record.actual_spent,
                        "committed_amount": record.committed_amount})
            _initialize_pdf_acquisition(session, source,
                record.provenance_extra["source_evidence"], provenance_entry["source_evidence"],
                initialized_acquisitions)
        from ...native_report_authority import persist_native_report
        persist_native_report(session, source, record.provenance_extra.get("_native_report_authority"),
            context=context, domain="national_budget")
        declares_measure = "measure" in record.provenance_extra
        if record.provenance_extra.get("measure") == EXPENDITURE_MEASURE:
            expenditure_periods.add((entity.id, period.id))

        record_hash = _record_hash(record, currency)

        if existing is None:
            line = BudgetLine(
                entity_id=entity.id,
                period_id=period.id,
                category=record.category,
                subcategory=record.subcategory,
                currency=currency,
                allocated_amount=record.allocated_amount,
                actual_spent=record.actual_spent,
                committed_amount=record.committed_amount,
                source_document_id=source.id,
                notes=record.notes,
                page_ref=record.page_ref,
                provenance=[provenance_entry] if provenance_entry else [],
                source_hash=record_hash,
            )
            session.add(line)
            stats.created += 1
            logger.debug(
                "Created BudgetLine: %s / %s / %s",
                record.entity_slug,
                record.period_label,
                record.category,
            )
        else:
            if _apply_line(existing, record, currency, source.id, record_hash):
                stats.updated += 1
                logger.debug(
                    "Updated BudgetLine: %s / %s / %s",
                    record.entity_slug,
                    record.period_label,
                    record.category,
                )

            if provenance_entry:
                provenance = list(existing.provenance or [])
                if declares_measure:
                    # One CURRENT declaration, and it is the last entry — the
                    # endpoint reads ``provenance[-1]["measure"]``. Older
                    # declarations (e.g. the exchequer proxy this row held
                    # before) are dropped rather than left to contradict it.
                    provenance = [
                        e
                        for e in provenance
                        if not (isinstance(e, dict) and "measure" in e)
                    ]
                    provenance.append(provenance_entry)
                    if provenance != list(existing.provenance or []):
                        existing.provenance = provenance
                elif provenance_entry not in provenance:
                    provenance.append(provenance_entry)
                    existing.provenance = provenance

    stats.superseded += _retire_superseded_lines(session, expenditure_periods)
    logger.info("national_budget_persistence_prepared", extra={
        "processed_records": stats.processed, "distinct_sources": len(sources_by_url),
        "error_count": len(stats.errors),
    })
    return stats


def current_measure(line: BudgetLine) -> Optional[str]:
    """The measure a row DECLARES — its last provenance entry's ``measure`` —
    or ``None`` when it declares nothing. Never inferred from the amounts or
    the notes."""
    provenance = line.provenance or []
    if not isinstance(provenance, list) or not provenance:
        return None
    last = provenance[-1]
    return last.get("measure") if isinstance(last, dict) else None


def _retire_superseded_lines(
    session: Session, periods: set[tuple[int, int]]
) -> int:
    """Delete rows in a period that now carries verified expenditure, when the
    row does not itself declare expenditure.

    Before #241 the annual FY 2025/26 report was parsed for Exchequer Issues
    and written under category/subcategory keys ("Education"/"Recurrent") that
    the expenditure rows ("Education"/"Recurrent & Development") do not
    overwrite. Left in place, every endpoint that sums a period's national
    lines (``_latest_national_period`` callers in main.py) would add the
    exchequer proxies on top of the expenditure totals. Only this domain
    writes national-government lines, and these rows are its own superseded
    output for the same report.
    """
    retired = 0
    for entity_id, period_id in periods:
        lines = session.execute(
            select(BudgetLine).where(
                and_(
                    BudgetLine.entity_id == entity_id,
                    BudgetLine.period_id == period_id,
                )
            )
        ).scalars()
        for line in list(lines):
            if current_measure(line) == EXPENDITURE_MEASURE:
                continue
            logger.info(
                "Retiring superseded BudgetLine %s (%s / %s, measure=%s)",
                line.id, line.category, line.subcategory, current_measure(line),
            )
            session.delete(line)
            retired += 1
    if retired:
        session.flush()
    return retired


__all__ = [
    "PersistenceStats",
    "current_measure",
    "persist_national_budget_records",
]
