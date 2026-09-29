"""Persistence logic for county budget records."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
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

#: For creating a document whose row declares no publisher. Never used to
#: correct an existing one (issue #276).
_DEFAULT_PUBLISHER = "Controller of Budget"


@dataclass
class PersistenceStats:
    processed: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    #: Rows removed because their document now files them under another period.
    superseded: int = 0
    errors: List[str] = field(default_factory=list)


def _correct_declared_publisher(source: SourceDocument, record: BudgetRecord) -> None:
    """Relabel an existing document whose publisher the row contradicts.

    Every budget document was created as "Controller of Budget" whatever its
    URL, and the refresh below rewrote title and meta but never the publisher,
    so a wrong label was permanent (issue #276). Only a declaration corrects a
    document: an undeclared row at the same URL must not reset it to the
    default on every run.
    """
    if record.publisher and source.publisher != record.publisher:
        logger.info(
            "Relabelled source document %s publisher %r -> %r",
            source.id, source.publisher, record.publisher,
        )
        source.publisher = record.publisher


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
            publisher=record.publisher or _DEFAULT_PUBLISHER,
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
        _correct_declared_publisher(source, record)

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
    """Resolve a county, tolerating COB PDF text-extraction artifacts.

    A cell reading "Taita Tav eta" slugified to `taita-tav-eta-county` and
    matched nothing, so that county's budget was dropped with a warning
    nobody read. See ``utils.resolve_entity_by_slug``.
    """
    from models import EntityType

    from ...utils import resolve_entity_by_slug

    entity, matched_by = resolve_entity_by_slug(
        session, record.entity_slug, entity_type=EntityType.COUNTY
    )
    if entity is None:
        message = f"Unknown entity slug '{record.entity_slug}'"
        logger.warning(message, extra={"entity_slug": record.entity_slug})
        return None, message
    if matched_by != "exact":
        # Never resolve silently: a fuzzy match is a parser defect upstream
        # that should be visible and fixable, not papered over.
        logger.warning(
            "Entity slug '%s' resolved to '%s' via %s match — the source "
            "PDF text is mangled; row kept, upstream parsing needs a look.",
            record.entity_slug,
            entity.slug,
            matched_by,
        )
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
        ("page_ref", record.page_ref),
    ):
        if value is None and record.data_quality != "official":
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


def _line_is_official(line: BudgetLine, source: SourceDocument) -> bool:
    """Whether the currently linked row claims a source-backed publication."""
    if isinstance(source.meta, dict) and source.meta.get("data_quality") == "official":
        return True
    provenance = line.provenance
    return bool(
        isinstance(provenance, list)
        and any(
            isinstance(entry, dict) and entry.get("data_quality") == "official"
            for entry in provenance
        )
    )


def _regressive_publication_error(
    session: Session,
    records: List[BudgetRecord],
    entities_by_slug: dict[str, Entity],
    default_url: str,
) -> Optional[str]:
    """Refuse a stale edition or fixture collision before any mutation.

    Same-date official corrections are permitted. A fallback fixture can fill
    a genuinely absent key, but cannot replace a key already backed by an
    official document. Reject the whole batch so its other rows and source
    metadata cannot be partly written when one key collides.
    """
    from ...utils import normalize_fiscal_label

    # A SourceDocument carries one quality badge. A mixed batch makes that
    # badge depend on row order, and can put modelled values under "official".
    qualities_by_url: dict[str, set[str]] = {}
    for record in records:
        qualities_by_url.setdefault(record.source_url or default_url, set()).add(
            record.data_quality
        )
    for url, qualities in qualities_by_url.items():
        if len(qualities) > 1:
            return f"Mixed county budget data quality for source document {url}"

    for record in records:
        canonical = normalize_fiscal_label(record.period_label)
        if " " not in canonical:
            year = int(canonical[2:6])
            if (record.start_date, record.end_date) != (
                date(year, 7, 1), date(year + 1, 6, 30)
            ):
                return f"Annual county budget dates disagree with {canonical}"

    official_urls = {
        r.source_url or default_url for r in records if r.data_quality == "official"
    }
    if official_urls:
        existing = session.execute(
            select(BudgetLine, FiscalPeriod, SourceDocument)
            .join(FiscalPeriod, BudgetLine.period_id == FiscalPeriod.id)
            .join(SourceDocument, BudgetLine.source_document_id == SourceDocument.id)
            .where(SourceDocument.url.in_(official_urls))
        ).all()
        newest_by_url_county: dict[tuple[str, int], date] = {}
        for line, period, source in existing:
            if not _line_is_official(line, source):
                continue
            key = (source.url, line.entity_id)
            current = newest_by_url_county.get(key)
            if current is None or period.end_date.date() > current:
                newest_by_url_county[key] = period.end_date.date()
        for record in records:
            if record.data_quality != "official":
                continue
            url = record.source_url or default_url
            current = newest_by_url_county.get(
                (url, entities_by_slug[record.entity_slug].id)
            )
            incoming = record.end_date
            if current is not None and incoming < current:
                return (
                    f"Older official county budget edition at {url}: "
                    f"incoming ends {incoming}, published edition ends {current}"
                )

        # A different document can target the same county, period and row.
        # Its earlier reporting cutoff must not replace the annual value.
        official_keys = {
            (entities_by_slug[r.entity_slug].id,
             normalize_fiscal_label(r.period_label), r.category, r.subcategory): r
            for r in records if r.data_quality == "official"
        }
        existing_keys = session.execute(
            select(BudgetLine, FiscalPeriod, SourceDocument)
            .join(FiscalPeriod, BudgetLine.period_id == FiscalPeriod.id)
            .join(SourceDocument, BudgetLine.source_document_id == SourceDocument.id)
            .where(
                BudgetLine.entity_id.in_({key[0] for key in official_keys}),
                FiscalPeriod.label.in_({key[1] for key in official_keys}),
            )
        ).all()
        for line, period, source in existing_keys:
            incoming_record = official_keys.get(
                (line.entity_id, period.label, line.category, line.subcategory)
            )
            if (
                incoming_record is not None
                and _line_is_official(line, source)
                and incoming_record.end_date < period.end_date.date()
            ):
                return (
                    "Older official county budget report would replace a "
                    f"newer source-backed row {line.id}"
                )

    nonofficial = [r for r in records if r.data_quality != "official"]
    if nonofficial:
        nonofficial_urls = {r.source_url or default_url for r in nonofficial}
        same_url_rows = session.execute(
            select(BudgetLine, SourceDocument)
            .join(SourceDocument, BudgetLine.source_document_id == SourceDocument.id)
            .where(SourceDocument.url.in_(nonofficial_urls))
        ).all()
        if any(_line_is_official(line, source) for line, source in same_url_rows):
            return (
                "Fixture or unverified county budget batch would change a "
                "source-backed document and withdraw its current revenue rows"
            )
        keys = {
            (
                entities_by_slug[r.entity_slug].id,
                normalize_fiscal_label(r.period_label),
                r.category,
                r.subcategory,
            )
            for r in nonofficial
        }
        existing = session.execute(
            select(BudgetLine, FiscalPeriod, SourceDocument)
            .join(FiscalPeriod, BudgetLine.period_id == FiscalPeriod.id)
            .join(SourceDocument, BudgetLine.source_document_id == SourceDocument.id)
            .where(
                BudgetLine.entity_id.in_({key[0] for key in keys}),
                FiscalPeriod.label.in_({key[1] for key in keys}),
            )
        ).all()
        for line, period, source in existing:
            key = (line.entity_id, period.label, line.category, line.subcategory)
            if key in keys and _line_is_official(line, source):
                return (
                    "Fixture or unverified county budget batch would replace "
                    f"source-backed row {line.id} ({period.label}, {line.category})"
                )
    return None


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
    #
    # The bulk preload above matches on EXACT slug only, which is a fast path,
    # not the resolution rule. `_resolve_entity` below was taught to tolerate
    # COB's text-extraction artifacts ("Taita Tav eta" -> taita-tav-eta-county)
    # but this path was not, so every Taita Taveta row was dropped here on
    # every run — with a warning nobody read, which is how it survived. A miss
    # now goes through the same tolerant resolver before anything is discarded.
    from models import EntityType

    from ...utils import resolve_entity_by_slug

    resolvable: List[BudgetRecord] = []
    unknown_slugs_reported: set[str] = set()
    artifact_slugs_reported: set[str] = set()
    for record in records:
        if record.entity_slug in entities_by_slug:
            resolvable.append(record)
            continue

        entity, matched_by = resolve_entity_by_slug(
            session, record.entity_slug, entity_type=EntityType.COUNTY
        )
        if entity is not None:
            # Key it by the ARTIFACT slug: every downstream lookup in this
            # function is entities_by_slug[record.entity_slug].
            entities_by_slug[record.entity_slug] = entity
            resolvable.append(record)
            if (
                matched_by != "exact"
                and record.entity_slug not in artifact_slugs_reported
            ):
                # Never resolve silently — a fuzzy match is a parser defect
                # upstream that should stay visible and fixable.
                logger.warning(
                    "county resolved via %s, not exact slug: %r -> %r",
                    matched_by,
                    record.entity_slug,
                    entity.slug,
                    extra={"entity_slug": record.entity_slug},
                )
                artifact_slugs_reported.add(record.entity_slug)
            continue

        stats.skipped += 1
        msg = f"Unknown entity slug '{record.entity_slug}'"
        stats.errors.append(msg)
        if record.entity_slug not in unknown_slugs_reported:
            logger.warning(msg, extra={"entity_slug": record.entity_slug})
            unknown_slugs_reported.add(record.entity_slug)

    if not resolvable:
        return stats

    regression = _regressive_publication_error(
        session, resolvable, entities_by_slug, settings.budgets_dataset_url
    )
    if regression:
        logger.warning(regression)
        stats.errors.append(regression)
        stats.skipped += len(resolvable)
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
                publisher=record.publisher or _DEFAULT_PUBLISHER,
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
            _correct_declared_publisher(source, record)

        source.status = DocumentStatus.AVAILABLE
        source.last_seen_at = now
        if record.artifact_sha256:
            source.meta = {**(source.meta or {}), "sha256": record.artifact_sha256}
        elif record.data_quality == "official" and "sha256" in (source.meta or {}):
            # A replacement at the same URL may no longer identify its bytes.
            # The old digest remains on historical row provenance, but cannot
            # describe this document's current values without a fresh assertion.
            meta = dict(source.meta)
            meta.pop("sha256")
            source.meta = meta
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
        if record.artifact_sha256:
            provenance_entry["artifact_sha256"] = record.artifact_sha256
        if record.page_ref:
            provenance_entry["page_ref"] = record.page_ref
        if record.revenue_coverage:
            provenance_entry["revenue_coverage"] = record.revenue_coverage
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
                    "page_ref": record.page_ref,
                    "provenance": [provenance_entry] if provenance_entry else [],
                    "source_hash": record_hash,
                }
            )
            stats.created += 1
        else:
            if _apply_line(existing, record, currency, source.id, record_hash):
                stats.updated += 1
            # Official replacements withdraw omitted notes just as they
            # withdraw omitted amounts/page references. Keeping the old note
            # could attach a superseded accounting basis to the new figures.
            if (
                record.notes or record.data_quality == "official"
            ) and existing.notes != record.notes:
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
                        e.get("artifact_sha256"),
                        e.get("page_ref"),
                        e.get("revenue_coverage"),
                    )

                new_key = _dedupe_key(provenance_entry)
                if not any(_dedupe_key(p) == new_key for p in provenance):
                    provenance.append(provenance_entry)
                    existing.provenance = provenance

    # ── 6. Bulk-INSERT all the new rows in one statement ─────────
    if new_line_values:
        session.execute(insert(BudgetLine), new_line_values)

    # ── 7. A document's rows live only in the periods it covers ───
    # The upsert key includes the period, so re-filing a document under the
    # right period INSERTS beside the old rows and never touches them. That is
    # what the CBIRR for the first nine months of FY2025/26 needs: every
    # edition before this fix was filed under FY2024/25 (the parser's fallback
    # year), and those 188 rows would otherwise go on answering for FY2024/25
    # beside the corrected FY2025/26 9M set.
    #
    # Scoped three ways so it can only ever remove a stale copy of what this
    # batch just wrote: the same source document, the same counties, and a
    # period this batch did not write for that document. A document this batch
    # wrote nothing for is untouched, so a parse that returned nothing deletes
    # nothing; and a fixture that spans several years keeps every year it
    # still asserts.
    stats.superseded += _remove_rows_filed_under_other_periods(
        session,
        [
            (
                sources_by_url[r.source_url or settings.budgets_dataset_url].id,
                entities_by_slug[r.entity_slug].id,
                periods_by_key[
                    (
                        entities_by_slug[r.entity_slug].country_id,
                        normalize_fiscal_label(r.period_label),
                    )
                ].id,
            )
            for r in resolvable
        ],
    )

    # ── 8. Revenue receipts: each parse is the whole set for its document ──
    # A county's receipts are published only when its table reconciles, so a
    # re-parse that refuses a county (a stricter parser, a corrected table)
    # or renames a stream must take the earlier rows with it — otherwise
    # they stay published from a parse the current code would not stand by.
    stats.superseded += _remove_revenue_receipts_not_reasserted(
        session,
        [
            (
                sources_by_url[r.source_url or settings.budgets_dataset_url].id,
                entities_by_slug[r.entity_slug].id,
                periods_by_key[
                    (
                        entities_by_slug[r.entity_slug].country_id,
                        normalize_fiscal_label(r.period_label),
                    )
                ].id,
                r.category,
                r.subcategory,
            )
            for r in resolvable
        ],
    )

    return stats


def _remove_revenue_receipts_not_reasserted(
    session: Session, written: List[Tuple[int, int, int, str, Optional[str]]]
) -> int:
    """Delete a document's revenue-receipts rows this batch did not write.

    Scoped to documents and counties the batch wrote anything for, so a run
    that wrote nothing removes nothing.
    """
    from services.county_budget import REVENUE_RECEIPTS_CATEGORY

    docs = {doc for doc, *_ in written}
    entities = {entity for _doc, entity, *_ in written}
    keep = {
        (doc, entity, period, sub)
        for doc, entity, period, category, sub in written
        if category == REVENUE_RECEIPTS_CATEGORY
    }
    if not docs:
        return 0
    stale = [
        line
        for line in session.execute(
            select(BudgetLine).where(
                BudgetLine.source_document_id.in_(docs),
                BudgetLine.entity_id.in_(entities),
                BudgetLine.category == REVENUE_RECEIPTS_CATEGORY,
            )
        )
        .scalars()
        .all()
        if (line.source_document_id, line.entity_id, line.period_id, line.subcategory)
        not in keep
    ]
    for line in stale:
        session.delete(line)
    if stale:
        logger.warning(
            "removed %d revenue-receipts row(s) this parse no longer yields "
            "(%d county(ies))",
            len(stale),
            len({line.entity_id for line in stale}),
        )
        session.flush()
    return len(stale)


def _remove_rows_filed_under_other_periods(
    session: Session, written: List[Tuple[int, int, int]]
) -> int:
    """Delete rows of each written document that sit outside its written periods.

    ``written`` is ``(source_document_id, entity_id, period_id)`` per record.
    Returns how many rows were removed, and logs each document's count.
    """
    periods_by_doc: dict[int, set[int]] = {}
    entities_by_doc: dict[int, set[int]] = {}
    for doc_id, entity_id, period_id in written:
        periods_by_doc.setdefault(doc_id, set()).add(period_id)
        entities_by_doc.setdefault(doc_id, set()).add(entity_id)

    removed = 0
    for doc_id, keep in periods_by_doc.items():
        stale = (
            session.execute(
                select(BudgetLine).where(
                    BudgetLine.source_document_id == doc_id,
                    BudgetLine.entity_id.in_(entities_by_doc[doc_id]),
                    BudgetLine.period_id.notin_(keep),
                )
            )
            .scalars()
            .all()
        )
        if not stale:
            continue
        logger.warning(
            "source document %s: removing %d budget line(s) filed under "
            "period(s) %s — this run files the document under %s",
            doc_id,
            len(stale),
            sorted({line.period_id for line in stale}),
            sorted(keep),
        )
        for line in stale:
            session.delete(line)
        removed += len(stale)
    if removed:
        session.flush()
    return removed


__all__ = ["PersistenceStats", "persist_budget_records"]
