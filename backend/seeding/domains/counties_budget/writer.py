"""Persistence logic for county budget records."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from decimal import Decimal
from typing import Iterable, List, Optional, Tuple

from models import (
    BudgetLine,
    DocumentStatus,
    DocumentType,
    Entity,
    FiscalPeriod,
    SourceDocument,
)
from sqlalchemy import and_, insert, select
from sqlalchemy.orm import Session

from ...config import SeedingSettings
from ...types import DomainRunContext
from ...utils import compute_hash
from .parser import BudgetRecord

logger = logging.getLogger("seeding.counties_budget.writer")


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
    record: BudgetRecord,
) -> SourceDocument:
    """Return the backing SourceDocument, creating or refreshing it as needed."""
    url = record.source_url or settings.budgets_dataset_url
    source = session.execute(
        select(SourceDocument).where(SourceDocument.url == url)
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)

    # April-2026 credibility: the Budget page /budget/overview endpoint
    # reads source.meta["data_quality"] to decide whether to flip the
    # badge from "estimated" → "official". That decision must not be
    # frozen the first time a SourceDocument is inserted — subsequent
    # seed runs that arrive with real COB data need to *upgrade* the
    # existing row. So we always re-evaluate meta and title.
    initial_meta: dict = {}
    if record.dataset_id:
        initial_meta["dataset_id"] = record.dataset_id
    if record.data_quality and record.data_quality != "unknown":
        initial_meta["data_quality"] = record.data_quality
    if record.source_label:
        initial_meta["source_label"] = record.source_label

    if source is None:
        source = SourceDocument(
            country_id=country_id,
            publisher="Controller of Budget",
            title=record.source_label or settings.dataset_title("budgets"),
            url=url,
            file_path=None,
            fetch_date=now,
            doc_type=DocumentType.BUDGET,
            md5=None,
            meta=initial_meta,
        )
        session.add(source)
        session.flush()
    else:
        meta = dict(source.meta or {})
        if record.dataset_id and "dataset_id" not in meta:
            meta["dataset_id"] = record.dataset_id
        # Always reflect the *latest* data_quality/source_label so a COB
        # re-seed promotes an older "estimated" fixture row to "official".
        if record.data_quality and record.data_quality != "unknown":
            meta["data_quality"] = record.data_quality
        if record.source_label:
            meta["source_label"] = record.source_label
            source.title = record.source_label
        source.meta = meta

    source.status = DocumentStatus.AVAILABLE
    source.last_seen_at = now
    return source


def _ensure_period(
    session: Session,
    country_id: int,
    record: BudgetRecord,
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


def _resolve_entity(
    session: Session, record: BudgetRecord
) -> Tuple[Optional[Entity], Optional[str]]:
    stmt = select(Entity).where(Entity.slug == record.entity_slug)
    entity = session.execute(stmt).scalar_one_or_none()
    if entity is None:
        message = f"Unknown entity slug '{record.entity_slug}'"
        logger.warning(message, extra={"entity_slug": record.entity_slug})
        return None, message
    return entity, None


def _record_hash(record: BudgetRecord, currency: str) -> str:
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
                str(record.actual_amount) if record.actual_amount is not None else None
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
    record: BudgetRecord,
    currency: str,
    source_document_id: int,
    record_hash: str,
) -> bool:
    updated = False

    for attr, value in (
        ("allocated_amount", record.allocated_amount),
        ("actual_spent", record.actual_amount),
        ("committed_amount", record.committed_amount),
        ("currency", currency),
        ("source_document_id", source_document_id),
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


def persist_budget_records(
    session: Session,
    records: Iterable[BudgetRecord],
    settings: SeedingSettings,
    context: DomainRunContext,
) -> PersistenceStats:
    """Upsert a batch of budget records.

    Performance-critical: previously this ran the SELECT-then-upsert
    sequence ONCE PER RECORD (4 round-trips × N records). Against a
    remote Supabase at ~150 ms RTT that blew past the per-domain 10-min
    budget on fixture-scale inputs. The rewrite preloads all lookups
    in four bulk queries and resolves per-record work in-memory, so
    total DB round-trips for N records are O(1) + a single final flush.
    """
    from ...utils import canonicalize_slug, normalize_fiscal_label

    stats = PersistenceStats()
    records = list(records)
    stats.processed = len(records)
    if not records:
        return stats

    # Re-canonicalise every incoming slug at the boundary. Fixtures and
    # partner exports occasionally carry slugs with apostrophes or stray
    # whitespace ("murang'a-county", "Muranga County"). Slugify here so
    # the rest of the pipeline only sees the DB's canonical form.
    for r in records:
        r.entity_slug = canonicalize_slug(r.entity_slug)

    # ── 1. Bulk-load entities ────────────────────────────────────
    entity_slugs = {r.entity_slug for r in records}
    entities_by_slug: dict[str, Entity] = {}
    if entity_slugs:
        rows = session.execute(
            select(Entity).where(Entity.slug.in_(entity_slugs))
        ).scalars().all()
        entities_by_slug = {e.slug: e for e in rows}

    # Drop records whose entity we can't resolve; surface once-each.
    resolvable: List[BudgetRecord] = []
    unknown_slugs_reported: set[str] = set()
    for record in records:
        if record.entity_slug in entities_by_slug:
            resolvable.append(record)
            continue
        stats.skipped += 1
        msg = f"Unknown entity slug '{record.entity_slug}'"
        stats.errors.append(msg)
        if record.entity_slug not in unknown_slugs_reported:
            logger.warning(msg, extra={"entity_slug": record.entity_slug})
            unknown_slugs_reported.add(record.entity_slug)

    if not resolvable:
        return stats

    now = datetime.now(timezone.utc)

    # ── 2. Bulk-load + touch source documents ────────────────────
    # SourceDocument is keyed by url. One query for everything we'll
    # reference; meta/title refreshes happen in-memory per-record so
    # the "latest record wins" semantics of the old code are preserved.
    urls = {
        (r.source_url or settings.budgets_dataset_url) for r in resolvable
    }
    existing_sources = {
        s.url: s
        for s in session.execute(
            select(SourceDocument).where(SourceDocument.url.in_(urls))
        )
        .scalars()
        .all()
    }
    sources_by_url: dict[str, SourceDocument] = {}
    for record in resolvable:
        url = record.source_url or settings.budgets_dataset_url
        source = sources_by_url.get(url) or existing_sources.get(url)

        if source is None:
            entity = entities_by_slug[record.entity_slug]
            initial_meta: dict = {}
            if record.dataset_id:
                initial_meta["dataset_id"] = record.dataset_id
            if record.data_quality and record.data_quality != "unknown":
                initial_meta["data_quality"] = record.data_quality
            if record.source_label:
                initial_meta["source_label"] = record.source_label
            source = SourceDocument(
                country_id=entity.country_id,
                publisher="Controller of Budget",
                title=record.source_label or settings.dataset_title("budgets"),
                url=url,
                file_path=None,
                fetch_date=now,
                doc_type=DocumentType.BUDGET,
                md5=None,
                meta=initial_meta,
            )
            session.add(source)
        else:
            meta = dict(source.meta or {})
            if record.dataset_id and "dataset_id" not in meta:
                meta["dataset_id"] = record.dataset_id
            # Latest-wins: re-seeds with real COB data should upgrade
            # a prior "estimated" fixture row to "official".
            if record.data_quality and record.data_quality != "unknown":
                meta["data_quality"] = record.data_quality
            if record.source_label:
                meta["source_label"] = record.source_label
                source.title = record.source_label
            source.meta = meta

        source.status = DocumentStatus.AVAILABLE
        source.last_seen_at = now
        sources_by_url[url] = source

    # ── 3. Bulk-load + ensure fiscal periods ─────────────────────
    # Compose the set of (country_id, canonical_label) pairs we need.
    period_keys: set[Tuple[int, str]] = set()
    for record in resolvable:
        entity = entities_by_slug[record.entity_slug]
        period_keys.add(
            (entity.country_id, normalize_fiscal_label(record.period_label))
        )

    existing_periods: dict[Tuple[int, str], FiscalPeriod] = {}
    if period_keys:
        country_ids = {cid for cid, _ in period_keys}
        labels = {lbl for _, lbl in period_keys}
        rows = session.execute(
            select(FiscalPeriod).where(
                FiscalPeriod.country_id.in_(country_ids),
                FiscalPeriod.label.in_(labels),
            )
        ).scalars().all()
        existing_periods = {(p.country_id, p.label): p for p in rows}

    periods_by_key: dict[Tuple[int, str], FiscalPeriod] = {}
    for record in resolvable:
        entity = entities_by_slug[record.entity_slug]
        canonical = normalize_fiscal_label(record.period_label)
        key = (entity.country_id, canonical)
        if key in periods_by_key:
            continue
        period = existing_periods.get(key)
        if period is None:
            period = FiscalPeriod(
                country_id=entity.country_id,
                label=canonical,
                start_date=datetime.combine(
                    record.start_date, time.min, tzinfo=timezone.utc
                ),
                end_date=datetime.combine(
                    record.end_date, time.max, tzinfo=timezone.utc
                ),
            )
            session.add(period)
        periods_by_key[key] = period

    # Flush so new SourceDocuments and FiscalPeriods get primary keys
    # before we reference them in BudgetLines below.
    session.flush()

    # ── 4. Bulk-load existing BudgetLines by (entity, period) ────
    # Over-selects if records only cover a subset of entity×period
    # combos, but typical run is ~47 counties × ~3 FYs × ~20 categories
    # ≈ a few thousand rows — trivial compared with what we avoid.
    entity_ids = {entities_by_slug[r.entity_slug].id for r in resolvable}
    period_ids = {
        periods_by_key[
            (
                entities_by_slug[r.entity_slug].country_id,
                normalize_fiscal_label(r.period_label),
            )
        ].id
        for r in resolvable
    }
    existing_lines: dict[Tuple[int, int, str, Optional[str]], BudgetLine] = {}
    if entity_ids and period_ids:
        rows = session.execute(
            select(BudgetLine).where(
                BudgetLine.entity_id.in_(entity_ids),
                BudgetLine.period_id.in_(period_ids),
            )
        ).scalars().all()
        existing_lines = {
            (l.entity_id, l.period_id, l.category, l.subcategory): l for l in rows
        }

    # ── 5. Resolve every record against the in-memory dicts ──────
    # New rows are buffered into `new_line_values` and emitted as a
    # single Core-level INSERT at the end of the pass. This replaces
    # the previous session.add()-per-row path whose implicit flush
    # issued one round-trip per row against Supabase — on a 1,880-row
    # fixture that was ~5 min just for the INSERTs. A single
    # INSERT ... VALUES (...), (...), (...) collapses that to one trip.
    new_line_values: List[dict] = []
    claimed_keys: set[Tuple[int, int, str, Optional[str]]] = set()

    for record in resolvable:
        entity = entities_by_slug[record.entity_slug]
        url = record.source_url or settings.budgets_dataset_url
        source = sources_by_url[url]
        canonical = normalize_fiscal_label(record.period_label)
        period = periods_by_key[(entity.country_id, canonical)]

        currency = record.currency or settings.budget_default_currency
        provenance_entry: dict[str, object] = {}
        if record.dataset_id:
            provenance_entry["dataset_id"] = record.dataset_id
        if context.job_id is not None:
            provenance_entry["ingestion_job_id"] = context.job_id
        if record.data_quality and record.data_quality != "unknown":
            provenance_entry["data_quality"] = record.data_quality
        if record.source_label:
            provenance_entry["source_label"] = record.source_label
        provenance_entry["ingested_at"] = datetime.now(timezone.utc).isoformat()

        record_hash = _record_hash(record, currency)
        key = (entity.id, period.id, record.category, record.subcategory)
        existing = existing_lines.get(key)

        if existing is None:
            # Guard against the same (entity, period, category, subcategory)
            # appearing twice in one batch — the DB's unique constraint
            # would otherwise kill the bulk INSERT mid-flight.
            if key in claimed_keys:
                continue
            claimed_keys.add(key)
            new_line_values.append(
                {
                    "entity_id": entity.id,
                    "period_id": period.id,
                    "category": record.category,
                    "subcategory": record.subcategory,
                    "currency": currency,
                    "allocated_amount": record.allocated_amount,
                    "actual_spent": record.actual_amount,
                    "committed_amount": record.committed_amount,
                    "source_document_id": source.id,
                    "notes": record.notes,
                    "provenance": [provenance_entry] if provenance_entry else [],
                    "source_hash": record_hash,
                }
            )
            stats.created += 1
        else:
            if _apply_line(existing, record, currency, source.id, record_hash):
                stats.updated += 1
            # Update notes independently — _apply_line skips None values
            # but we *do* want to overwrite stale notes with new ones.
            if record.notes and existing.notes != record.notes:
                existing.notes = record.notes
                stats.updated += 1

            if provenance_entry:
                provenance = list(existing.provenance or [])

                # Dedupe key intentionally excludes ingestion_job_id and
                # ingested_at so an idempotent re-seed (same dataset,
                # same quality, same source label, no changed values)
                # doesn't append a fresh entry and thereby mark the row
                # dirty. Before this trim every nightly run added an
                # entry per record → 1,880 UPDATE statements on a
                # no-change re-seed (~3 min over Frankfurt RTT).
                # The audit trail of "which job last touched the row"
                # is still on the IngestionJob row itself.
                def _dedupe_key(e: dict) -> tuple:
                    return (
                        e.get("dataset_id"),
                        e.get("data_quality"),
                        e.get("source_label"),
                    )

                new_key = _dedupe_key(provenance_entry)
                if not any(_dedupe_key(p) == new_key for p in provenance):
                    provenance.append(provenance_entry)
                    existing.provenance = provenance

    # ── 6. Bulk-INSERT all the new rows in one statement ─────────
    if new_line_values:
        session.execute(insert(BudgetLine), new_line_values)

    return stats


__all__ = ["PersistenceStats", "persist_budget_records"]
