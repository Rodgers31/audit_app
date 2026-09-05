"""Layer 4 — load ``extractions`` rows into the ``audits`` fact table.

Every audit row written here carries the full provenance the schema was
built for and never had: ``extraction_id`` (the FK to the middle link),
``page_ref``, ``source_hash``, ``confidence_score``, ``basis`` — and
``publishable`` set by the one rule in ``services/publication_gate.py``,
not a second copy of it.

Keyed on ``extraction_id``: one extraction, one audit row, idempotent
re-runs. Amounts: ``audits.amount`` is set only when the paragraph
carries exactly one ``Kshs`` figure — a paragraph quoting a budget, an
actual and a variance has no single "amount involved", and picking one
by heuristic would be an editorial claim the source does not make. All
parsed amounts stay in ``provenance`` either way.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timezone
from typing import Optional

from models import (
    Audit,
    Entity,
    EntityType,
    Extraction,
    FigureBasis,
    FiscalPeriod,
    Severity,
    SourceDocument,
)
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ...config import SeedingSettings
from ...extractors.oag_blue_book import EXTRACTOR_ID, source_hash_of
from ...types import DomainRunContext
from ...utils import normalize_fiscal_label, slugify_entity
from .writer import PersistenceStats
import re

logger = logging.getLogger("seeding.audits.loader")

_SEVERITY_MAP = {
    "CRITICAL": Severity.CRITICAL,
    "WARNING": Severity.WARNING,
    "INFO": Severity.INFO,
}


#: "County Executive of Kilifi", "County Assembly of Nairobi City" — an
#: auditee that belongs to an EXISTING county, not a new MDA.
_COUNTY_ENTRY_RE = re.compile(
    r"^county\s+(?:executive|assembly|government)\s+of\s+(?P<county>.+)$", re.I
)


class CountyEntityUnresolved(RuntimeError):
    """A county auditee that does not map to a county row we already hold."""


def _county_entity(session: Session, name: str) -> Optional[Entity]:
    """The existing COUNTY entity a county auditee belongs to.

    ``None`` when ``name`` is not a county entry at all (a national vote).
    Raises ``CountyEntityUnresolved`` when it IS one but no county matches —
    the caller must skip, never create.

    Why this exists: the consolidated county volumes number their TOC 1..47,
    and _ensure_entity read those as national vote numbers. It slugified
    "County Executive of Kilifi" to `county-executive-of-kilifi`, missed the
    real `kilifi-county`, and created a MINISTRY with `vote: 3`. A run would
    have written ~94 mis-typed entities duplicating counties that already
    exist. Only the 600s timeout rolling the run back prevented it.
    """
    m = _COUNTY_ENTRY_RE.match((name or "").strip())
    if not m:
        return None

    from ...utils import resolve_entity_by_slug

    raw = m.group("county").strip()
    # "Taita/Taveta" slugifies fine; "Nairobi City" is the county the DB holds
    # as plain "Nairobi", so a trailing City is tried as an alias.
    for probe in (raw, re.sub(r"\s+city$", "", raw, flags=re.I)):
        entity, _how = resolve_entity_by_slug(
            session, slugify_entity(probe), entity_type=EntityType.COUNTY
        )
        if entity is not None:
            return entity

    raise CountyEntityUnresolved(
        f"{name!r} is a county auditee but {raw!r} matches no county entity"
    )


def _ensure_entity(
    session: Session, country_id: int, name: str, vote: Optional[int]
) -> Entity:
    """Resolve a Blue Book vote to an entity, creating it if new.

    Vote 1xxx are executive MDAs (ministries and state departments —
    the DB already types state departments as MINISTRY, e.g. "The State
    Department for Correctional Services"); vote 2xxx are constitutional
    commissions and independent offices.
    """
    county = _county_entity(session, name)
    if county is not None:
        return county

    slug = slugify_entity(name, county_suffix=False)
    entity = session.execute(
        select(Entity).where(Entity.slug == slug)
    ).scalar_one_or_none()
    if entity is not None:
        return entity
    etype = (
        EntityType.COMMISSION
        if vote is not None and vote >= 2000
        else EntityType.MINISTRY
    )
    entity = Entity(
        country_id=country_id,
        type=etype,
        canonical_name=name,
        slug=slug,
        meta={"vote": vote, "created_by": "seeding.audits.loader"},
    )
    session.add(entity)
    session.flush()
    logger.info("Created entity %s (%s, vote %s)", name, etype.value, vote)
    return entity


def _ensure_period(
    session: Session, country_id: int, fy_label: str
) -> FiscalPeriod:
    canonical = normalize_fiscal_label(fy_label)
    period = session.execute(
        select(FiscalPeriod).where(
            and_(
                FiscalPeriod.country_id == country_id,
                FiscalPeriod.label == canonical,
            )
        )
    ).scalar_one_or_none()
    if period is None:
        # canonical is "FY{Y1}/{Y2-short}"; Kenya FY runs 1 Jul → 30 Jun.
        y1 = int(canonical[2:6])
        period = FiscalPeriod(
            country_id=country_id,
            label=canonical,
            start_date=datetime.combine(
                datetime(y1, 7, 1).date(), time.min, tzinfo=timezone.utc
            ),
            end_date=datetime.combine(
                datetime(y1 + 1, 6, 30).date(), time.max, tzinfo=timezone.utc
            ),
        )
        session.add(period)
        session.flush()
    return period


def load_blue_book_extractions(
    session: Session,
    doc: SourceDocument,
    settings: SeedingSettings,
    context: DomainRunContext,
) -> PersistenceStats:
    """Extractions of ``doc`` → audit rows, provenance columns populated."""
    stats = PersistenceStats()
    # Lookup caches for this document. Scoped per call, not module-level, so
    # nothing leaks between documents or between runs.
    _entity_cache: dict = {}
    _period_cache: dict = {}

    extractions = (
        session.execute(
            select(Extraction).where(
                and_(
                    Extraction.source_document_id == doc.id,
                    Extraction.extractor == EXTRACTOR_ID,
                )
            )
        )
        .scalars()
        .all()
    )
    if not extractions:
        logger.info("No %s extractions for document %s", EXTRACTOR_ID, doc.id)
        return stats

    for ext in extractions:
        stats.processed += 1
        payload = ext.extracted_json or {}
        fy = payload.get("fiscal_year")
        name = payload.get("entity_name")
        text = payload.get("finding_text")
        sev = _SEVERITY_MAP.get(payload.get("severity", ""))
        if not (fy and name and text and sev):
            # An extraction the loader cannot attribute is left in
            # extractions (it IS the evidence) but produces no fact row.
            msg = (
                f"extraction {ext.id}: missing "
                f"{'fiscal_year' if not fy else 'entity/text/severity'}"
            )
            logger.warning("Skipping %s", msg)
            stats.errors.append(msg)
            stats.skipped += 1
            continue

        # Memoised per run. Every finding used to cost its own SELECT for the
        # entity and another for the period, and a consolidated county volume
        # carries ~1,500 findings against 47 entities and ONE fiscal year.
        # Measured at 221 ms per round-trip to the production database, that
        # is ~1,000s of lookups against a 600s domain budget — which is what
        # aborted the 2026-09-05 run, not OCR (only 4 pages of 701 qualify).
        try:
            ekey = (name, payload.get("vote"))
            if ekey in _entity_cache:
                entity = _entity_cache[ekey]
            else:
                entity = _ensure_entity(
                    session, doc.country_id, name, payload.get("vote")
                )
                _entity_cache[ekey] = entity
        except CountyEntityUnresolved as exc:
            # Never invent an entity for a finding: a public audit finding
            # filed against a county row we made up is worse than one absent.
            logger.warning("Skipping finding — %s", exc)
            stats.errors.append(str(exc))
            stats.skipped += 1
            continue
        if fy in _period_cache:
            period = _period_cache[fy]
        else:
            period = _ensure_period(session, doc.country_id, fy)
            _period_cache[fy] = period

        amounts = payload.get("amounts") or []
        amount = amounts[0] if len(amounts) == 1 else None
        vote = payload.get("vote")
        para = payload.get("paragraph_no")
        reference = f"OAG-BB-{fy}-V{vote}-P{para}"
        page_ref = f"p.{payload.get('pdf_page')}"

        prov_entry = {
            "source": "oag_blue_book",
            "reference": reference,
            "source_url": doc.url,
            "source_md5": doc.md5,
            "pdf_page": payload.get("pdf_page"),
            "printed_page": payload.get("printed_page"),
            "subreport": payload.get("subreport"),
            "opinion": payload.get("opinion"),
            "heading": payload.get("heading"),
            "sub_section": payload.get("sub_section"),
            "title": payload.get("title"),
            "amounts": amounts,
            "extraction_id": ext.id,
            "extraction_method": payload.get("extraction_method"),
        }

        existing = session.execute(
            select(Audit).where(Audit.extraction_id == ext.id)
        ).scalar_one_or_none()

        if context.dry_run:
            stats.created += 0 if existing else 1
            continue

        audit_year = int(fy.split("/")[0]) + 1 if "/" in fy else None
        if existing is None:
            session.add(
                Audit(
                    entity_id=entity.id,
                    period_id=period.id,
                    finding_text=text,
                    severity=sev,
                    recommended_action=None,
                    source_document_id=doc.id,
                    provenance=[prov_entry],
                    query_type=payload.get("subreport"),
                    amount=amount,
                    status="published_report",
                    audit_opinion=payload.get("opinion"),
                    audit_year=audit_year,
                    external_reference=reference,
                    extraction_id=ext.id,
                    page_ref=page_ref,
                    source_hash=source_hash_of(payload),
                    confidence_score=(
                        float(ext.confidence) if ext.confidence is not None else None
                    ),
                    basis=FigureBasis.ACTUAL,
                )
            )
            stats.created += 1
        else:
            changed = False
            for attr, value in (
                ("entity_id", entity.id),
                ("period_id", period.id),
                ("finding_text", text),
                ("severity", sev),
                ("amount", amount),
                ("page_ref", page_ref),
                ("source_hash", source_hash_of(payload)),
                ("audit_opinion", payload.get("opinion")),
                ("external_reference", reference),
            ):
                if getattr(existing, attr) != value:
                    setattr(existing, attr, value)
                    changed = True
            if existing.provenance != [prov_entry]:
                existing.provenance = [prov_entry]
                changed = True
            if changed:
                stats.updated += 1

    session.flush()

    # The gate's verdict, written by the gate itself — never recomputed here.
    if not context.dry_run:
        from services.publication_gate import backfill_publishable_audits

        backfill_publishable_audits(session)

    logger.info(
        "Loaded blue-book extractions for doc %s: %d created, %d updated, "
        "%d skipped",
        doc.id,
        stats.created,
        stats.updated,
        stats.skipped,
    )
    return stats


__all__ = ["load_blue_book_extractions"]
