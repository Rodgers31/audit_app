"""Writer for National Treasury debt data to database."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from models import (
    DebtCategory,
    DocumentType,
    Entity,
    EntityType,
    Loan,
    SourceDocument,
)
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from .parser import DebtRecord

logger = logging.getLogger("seeding.national_debt.writer")


def _get_or_create_entity(
    session: Session, name: str, entity_type: str
) -> Entity | None:
    """Get or create entity by name and type."""
    # Map entity_type string to enum
    type_mapping = {
        "national": EntityType.NATIONAL,
        "county": EntityType.COUNTY,
        "ministry": EntityType.MINISTRY,
        "agency": EntityType.AGENCY,
    }

    entity_type_enum = type_mapping.get(entity_type.lower())
    if not entity_type_enum:
        logger.warning(f"Unknown entity type: {entity_type}")
        return None

    # Try to find existing entity
    entity = (
        session.query(Entity)
        .filter(Entity.canonical_name == name, Entity.type == entity_type_enum)
        .first()
    )

    if entity:
        return entity

    # For National Government, this should already exist from bootstrap
    logger.warning(
        f"Entity not found: {name} ({entity_type}). "
        f"Run bootstrap_data.py to create reference entities."
    )
    return None


def _get_or_create_source_document(
    session: Session, record: DebtRecord
) -> SourceDocument:
    """Get or create source document for the debt bulletin."""
    # Use source URL or title as unique identifier
    source_identifier = record.source_url or record.source_title or "Unknown Source"

    doc = (
        session.query(SourceDocument)
        .filter(
            SourceDocument.title == record.source_title,
            SourceDocument.doc_type == DocumentType.LOAN,
        )
        .first()
    )

    if doc:
        return doc

    # Get Kenya country ID (should exist from bootstrap)
    from models import Country

    kenya = session.query(Country).filter(Country.iso_code == "KEN").first()
    if not kenya:
        raise ValueError("Kenya country not found. Run bootstrap_data.py first.")

    # Create new source document
    logger.info(f"Creating source document: {record.source_title}")
    doc = SourceDocument(
        country_id=kenya.id,
        publisher=getattr(record, "publisher", None) or "National Treasury of Kenya",
        title=record.source_title or "National Treasury Debt Bulletin",
        doc_type=DocumentType.LOAN,
        url=record.source_url,
        fetch_date=datetime.now(timezone.utc),
    )
    session.add(doc)
    session.flush()
    return doc


def _resolve_debt_category(value: str | None):
    """Map a debt_category string to the DebtCategory enum, defaulting
    to ``OTHER`` for unknown values. Returns ``None`` when the input is
    falsy so callers can leave the column unset on existing rows."""
    if not value:
        return None
    from models import DebtCategory as _DC

    return {
        "external_multilateral": _DC.EXTERNAL_MULTILATERAL,
        "external_bilateral": _DC.EXTERNAL_BILATERAL,
        "external_commercial": _DC.EXTERNAL_COMMERCIAL,
        "domestic_bonds": _DC.DOMESTIC_BONDS,
        "domestic_bills": _DC.DOMESTIC_BILLS,
        "domestic_overdraft": _DC.DOMESTIC_OVERDRAFT,
        "pending_bills": _DC.PENDING_BILLS,
        "county_guaranteed": _DC.COUNTY_GUARANTEED,
    }.get(value, _DC.OTHER)


#: Categories a successful World Bank IDS creditor pull owns outright. Mirrors
#: fetcher._EXTERNAL_CATEGORIES. Records carry the string form; Loan rows carry
#: the DebtCategory enum, so both spellings are needed.
EXTERNAL_CATEGORIES = {
    "external_multilateral",
    "external_bilateral",
    "external_commercial",
}
EXTERNAL_CATEGORY_ENUMS = [
    DebtCategory.EXTERNAL_MULTILATERAL,
    DebtCategory.EXTERNAL_BILATERAL,
    DebtCategory.EXTERNAL_COMMERCIAL,
]


def _category_name(value) -> str:
    """The string form of a debt category, whether enum or plain string."""
    return getattr(value, "value", value) or ""


def reconcile_external_creditors(
    session: Session, records: list[DebtRecord]
) -> int:
    """Delete external loans this run no longer names, and return the count.

    ``_replace_external_loans`` only rebuilds the in-memory payload. The upsert
    below matches on ``(entity_id, lender)`` and removes duplicates of the SAME
    lender, never lenders that have gone away — so an existing database kept
    every old external row ("Eurobonds (2014, 2018, 2019, 2021, 2024 issues)",
    "Multilateral (World Bank / IDA / IBRD)", ...) and inserted the
    differently-named IDS rows beside them. The headline and the lender treemap
    then double-counted external debt.

    Runs in the caller's transaction, before the upsert, so either the whole
    replacement lands or none of it does.
    """
    incoming = {
        (r.entity_name, r.lender)
        for r in records
        if _category_name(r.debt_category) in EXTERNAL_CATEGORIES
    }
    if not incoming:
        # Nothing external in this run: not a replacement, so delete nothing.
        return 0

    entity_names = {name for name, _ in incoming}
    deleted = 0
    for entity_name in entity_names:
        entity = (
            session.query(Entity)
            .filter(Entity.canonical_name == entity_name)
            .first()
        )
        if entity is None:
            continue
        stale = (
            session.query(Loan)
            .filter(
                Loan.entity_id == entity.id,
                Loan.debt_category.in_(EXTERNAL_CATEGORY_ENUMS),
            )
            .all()
        )
        for loan in stale:
            if (entity_name, loan.lender) in incoming:
                continue
            logger.info(
                "Removing external loan no longer reported by the creditor "
                "pull: %s (%s)",
                loan.lender,
                loan.debt_category,
            )
            session.delete(loan)
            deleted += 1
    if deleted:
        session.flush()
    return deleted


def write_debt_records(
    session: Session, records: list[DebtRecord], dataset_id: str, job_id: int | None
) -> tuple[int, int]:
    """
    Persist debt records to database.

    Dedupe by ``(entity_id, lender)`` rather than the writer's older
    ``(entity_id, lender, issue_date)`` triple. National-debt loans
    are aggregate buckets (e.g. "Multilateral (World Bank / IDA /
    IBRD)") with synthetic issue dates that change as live overlays
    advance their data vintage. Keying on issue_date too caused every
    new vintage to insert a NEW row alongside the prior one, leaving
    a trail of stale zombies. We now find all rows for (entity,
    lender), update one in-place to the latest values, and DELETE any
    extras as a one-shot cleanup of pre-existing zombies. Safe because
    the national_debt domain enforces one row per lender bucket
    (verified against the fixture and both live overlays).

    Args:
        session: Database session
        records: Parsed debt records
        dataset_id: Dataset identifier for provenance
        job_id: Ingestion job ID for tracking

    Returns:
        Tuple of (created_count, updated_count)
    """
    created = 0
    updated = 0

    # Reconcile BEFORE the upsert: external rows the creditor pull no longer
    # names must go, or the replacement silently becomes an append.
    reconcile_external_creditors(session, records)

    for record in records:
        entity = _get_or_create_entity(session, record.entity_name, record.entity_type)
        if not entity:
            logger.warning(
                f"Skipping loan: could not resolve entity {record.entity_name}"
            )
            continue

        source_doc = _get_or_create_source_document(session, record)

        existing_loans = (
            session.query(Loan)
            .filter(
                Loan.entity_id == entity.id,
                Loan.lender == record.lender,
            )
            .order_by(Loan.id)
            .all()
        )

        provenance_entry = {
            "dataset_id": dataset_id,
            "ingestion_job_id": job_id,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }

        if existing_loans:
            keeper = existing_loans[0]
            zombies = existing_loans[1:]

            # Drop zombies BEFORE mutating the keeper. The Loan table
            # carries a UniqueConstraint(entity_id, lender, issue_date),
            # and SQLAlchemy's unit-of-work flushes UPDATEs ahead of
            # DELETEs — so updating keeper.issue_date to a value still
            # held by a not-yet-deleted zombie raises IntegrityError.
            # Explicit flush after the deletes guarantees the row is
            # gone before the keeper takes its date.
            if zombies:
                for zombie in zombies:
                    logger.info(
                        "Deleting zombie loan #%s (lender=%s, "
                        "issue_date=%s) consolidated into #%s",
                        zombie.id, zombie.lender, zombie.issue_date,
                        keeper.id,
                    )
                    session.delete(zombie)
                session.flush()

            # Counts toward `updated` only when something actually
            # shifted, so the metric still reflects real churn rather
            # than counting every no-op re-write.
            changed = (
                keeper.outstanding != record.outstanding
                or keeper.principal != record.principal
                or keeper.issue_date != record.issue_date
                or keeper.maturity_date != record.maturity_date
                or keeper.debt_category is None
            )
            if changed or zombies:
                logger.info(
                    "Updating loan: %s for %s (outstanding: %s → %s%s)",
                    record.lender,
                    record.entity_name,
                    keeper.outstanding,
                    record.outstanding,
                    f"; consolidated {len(zombies)} zombie row(s)" if zombies else "",
                )
                keeper.outstanding = record.outstanding
                keeper.principal = record.principal
                keeper.issue_date = record.issue_date
                keeper.maturity_date = record.maturity_date
                resolved_cat = _resolve_debt_category(record.debt_category)
                if resolved_cat is not None:
                    keeper.debt_category = resolved_cat
                if record.interest_rate is not None:
                    keeper.interest_rate = record.interest_rate

                provenance = keeper.provenance or []
                provenance.append(provenance_entry)
                keeper.provenance = provenance
                updated += 1
        else:
            logger.info(
                f"Creating loan: {record.lender} for {record.entity_name} "
                f"(principal: {record.principal}, outstanding: {record.outstanding})"
            )
            loan = Loan(
                entity_id=entity.id,
                lender=record.lender,
                debt_category=_resolve_debt_category(record.debt_category),
                principal=record.principal,
                outstanding=record.outstanding,
                interest_rate=record.interest_rate or Decimal("0"),
                issue_date=record.issue_date,
                maturity_date=record.maturity_date,
                currency=record.currency,
                source_document_id=source_doc.id,
                provenance=[provenance_entry],
            )
            session.add(loan)
            created += 1

    logger.info(f"Debt write complete: {created} created, {updated} updated")
    return created, updated
