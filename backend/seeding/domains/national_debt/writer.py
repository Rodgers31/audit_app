"""Writer for National Treasury debt data to database."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from models import (
    DebtCategory,
    DocumentType,
    Entity,
    EntityType,
    Loan,
    SourceDocument,
)
from sqlalchemy import func
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from .parser import DebtRecord

logger = logging.getLogger("seeding.national_debt.writer")

#: For creating a document whose payload declares no publisher. Never used to
#: correct an existing one (issue #274).
_DEFAULT_PUBLISHER = "National Treasury of Kenya"


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
    doc = (
        session.query(SourceDocument)
        .filter(
            (
                # CBK's listing contains literal spaces while the existing
                # bulletin URL stores %20. They identify the same artifact.
                # Do not unquote reserved characters (e.g. %2F), which can
                # identify a different resource, or match by an edition title.
                func.replace(SourceDocument.url, " ", "%20")
                == record.source_url.replace(" ", "%20")
                if record.source_url
                else SourceDocument.title == record.source_title
            ),
            SourceDocument.doc_type == DocumentType.LOAN,
        )
        .order_by(SourceDocument.id)
        .first()
    )

    if doc:
        # The CBK bulletins were filed under the National Treasury default
        # because the fixture declared no publisher, and nothing here ever
        # looked at an existing document again (issue #274). Only a
        # declaration corrects one; the default is for creating a document, or
        # an undeclared row with the same title would reset it every run.
        if record.publisher and doc.publisher != record.publisher:
            logger.info(
                "Relabelled source document %s publisher %r -> %r",
                doc.id, doc.publisher, record.publisher,
            )
            doc.publisher = record.publisher
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
        publisher=record.publisher or _DEFAULT_PUBLISHER,
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


def drop_subsumed_stored_rows(session: Session, records: list[DebtRecord]) -> int:
    """Delete STORED rows that an incoming aggregate already counts.

    ``fetcher._drop_subsumed_rows`` keeps a subset row out of the payload, and
    PR #178 removed the 300Bn "Domestic Infrastructure & Green Bonds" row from
    the fixture. Neither reached the database: the upsert below only touches
    rows it is given, and ``reconcile_external_creditors`` only deletes
    EXTERNAL rows. So ``loans.id=382`` — last written 2026-02-21 — went on
    being summed into the headline, and production published 12,524Bn against
    the 12,224Bn #178 was meant to leave (issue #235).

    Same registry, same rule, applied to the table: a stored row is deleted
    only when its aggregate is in THIS run's records for the same entity and
    category. Without the aggregate present it is the only row there is, and
    deleting it would understate rather than correct. Runs in the caller's
    transaction, before the upsert.
    """
    from .fetcher import _SUBSUMED_ROWS

    def _key(lender: str | None) -> str:
        return " ".join((lender or "").lower().split())

    deleted = 0
    for rule in _SUBSUMED_ROWS:
        aggregates = {
            r.entity_name
            for r in records
            if _category_name(r.debt_category) == rule.category
            and rule.aggregate_marker in _key(r.lender)
        }
        for entity_name in aggregates:
            entity = (
                session.query(Entity)
                .filter(Entity.canonical_name == entity_name)
                .first()
            )
            if entity is None:
                continue
            for loan in (
                session.query(Loan)
                .filter(
                    Loan.entity_id == entity.id,
                    Loan.debt_category == _resolve_debt_category(rule.category),
                )
                .all()
            ):
                lender = _key(loan.lender)
                if rule.aggregate_marker in lender:
                    continue
                if not any(m in lender for m in rule.subset_markers):
                    continue
                logger.warning(
                    "Deleting stored loan #%s %r (KES %.1fBn): the incoming "
                    "aggregate already counts it — %s",
                    loan.id, loan.lender, float(loan.outstanding or 0) / 1e9,
                    rule.because,
                )
                session.delete(loan)
                deleted += 1
    if deleted:
        session.flush()
    return deleted


def _stored_terms(loan: Loan):
    """The interest declaration on a stored row's newest provenance entry."""
    from .interest_terms import TERMS_KEY

    entries = loan.provenance if isinstance(loan.provenance, list) else []
    latest = next((e for e in reversed(entries) if isinstance(e, dict)), None)
    return latest.get(TERMS_KEY) if latest else None


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
    drop_subsumed_stored_rows(session, records)

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
        if record.interest_terms is not None:
            from .interest_terms import TERMS_KEY

            # The API publishes a rate or an annual cost ONLY from this
            # declaration, read off the newest entry. See interest_terms.
            provenance_entry[TERMS_KEY] = record.interest_terms

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
                # A row whose figures are replaced from this record cites this
                # record's document. It used to keep whichever document it was
                # created under, so the CBK domestic rows went on citing a
                # document no payload names any more (issue #274).
                keeper.source_document_id != source_doc.id
                or keeper.outstanding != record.outstanding
                or keeper.principal != record.principal
                or keeper.issue_date != record.issue_date
                or keeper.maturity_date != record.maturity_date
                or keeper.debt_category is None
                # A new rate or declaration is churn too. Without this, a run
                # whose balances did not move appended no provenance entry, and
                # the row kept publishing whatever its last entry declared.
                or keeper.interest_rate != record.interest_rate
                or _stored_terms(keeper) != record.interest_terms
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
                keeper.source_document_id = source_doc.id
                resolved_cat = _resolve_debt_category(record.debt_category)
                if resolved_cat is not None:
                    keeper.debt_category = resolved_cat
                # Unconditional. ``if record.interest_rate is not None`` kept
                # the April-2025 fixture's 14.5%/16% on the domestic rows for
                # every run after the overlays took over their balances. The
                # run's rate is published or it is NULL; the stored one is
                # neither evidence nor a fallback.
                keeper.interest_rate = record.interest_rate

                # A NEW list. Appending to the loaded one and assigning it back
                # hands SQLAlchemy the same object, which a plain JSONB column
                # does not register as a change — and the API reads the
                # interest declaration off the newest entry.
                keeper.provenance = [*(keeper.provenance or []), provenance_entry]
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
                # NULL, not 0: ``or Decimal("0")`` published 0.00% and KES 0
                # annual cost on 45 of 48 production rows (issue #235).
                interest_rate=record.interest_rate,
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
