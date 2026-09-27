"""Writer for pending bills data to database.

Persists parsed PendingBillRecord objects to the loans table using
the PENDING_BILLS debt category, following the same pattern as
the national_debt writer.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from models import DebtCategory, DocumentType, Entity, EntityType, Loan, SourceDocument
from services.publication_gate import PENDING_BILLS_PUBLICATION
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from .parser import PendingBillRecord

logger = logging.getLogger("seeding.pending_bills.writer")


def write_pending_bills(
    session: Session,
    records: list[PendingBillRecord],
    source_url: str | None = None,
    source_title: str | None = None,
    dry_run: bool = False,
    publication: str | None = None,
    publisher: str | None = None,
) -> tuple[int, int]:
    """
    Write pending bills records to the loans table.

    Each record becomes a Loan row with debt_category = PENDING_BILLS.
    Uses upsert logic: if a matching loan already exists (by entity +
    lender composite key), it gets updated; otherwise a new row is created.

    Args:
        session: DB session
        records: Parsed pending bill records
        source_url: Source document URL
        source_title: Source document title
        dry_run: If True, log but don't commit

    Returns:
        Tuple of (created_count, updated_count)
    """
    created = 0
    updated = 0

    if not records:
        logger.info("No pending bills records to write")
        return created, updated

    # Pending bills come from ONE publication, the Treasury BROP — para 18 for
    # the National Government, Table 10 for the counties. Any other payload
    # writes nothing. The git fixture the fetcher falls back to when the BROP
    # is unreachable carries invented figures on both sides:
    #
    # * seven counties (Nairobi 98.7B, ...) under the same lender key the BROP
    #   uses, so one failed fetch OVERWROTE the published figure (#238);
    # * eleven ministries and state corporations (405.4B) under lender keys the
    #   BROP never uses, so they were ADDED beside its two national lines and
    #   stayed there — 931.3B served against the 525.9B the BROP prints, the
    #   same bills counted twice (#265).
    if publication != PENDING_BILLS_PUBLICATION:
        logger.warning(
            "pending bills: not writing %d record(s) from a %s payload — "
            "pending bills are read from the Treasury BROP only",
            len(records),
            publication or "fixture",
        )
        return created, updated

    # Get or create the source document
    source_doc = _get_or_create_source_document(
        session, source_url, source_title, publisher=publisher
    )

    for record in records:
        entity = _get_or_create_entity(session, record.entity_name, record.entity_type)
        if not entity:
            logger.warning(
                f"Could not resolve entity: {record.entity_name} "
                f"({record.entity_type}). Skipping."
            )
            continue

        # Build a deterministic lender name based on category
        lender_name = _build_lender_name(record)

        # Look for existing loan with same entity + lender
        existing = (
            session.query(Loan)
            .filter(
                Loan.entity_id == entity.id,
                Loan.lender == lender_name,
                Loan.debt_category == DebtCategory.PENDING_BILLS,
            )
            .first()
        )

        provenance = {
            "source": "cob_pending_bills_etl",
            # Which publication this figure was read from — only the BROP
            # reaches here. Declared by the fetcher, re-stamped on every write.
            "publication": publication,
            "fiscal_year": record.fiscal_year,
            "category": record.category,
            "source_url": record.source_url or source_url,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        }
        if record.eligible_pending is not None:
            provenance["eligible_pending"] = float(record.eligible_pending)
        if record.ineligible_pending is not None:
            provenance["ineligible_pending"] = float(record.ineligible_pending)
        if record.notes:
            provenance["notes"] = record.notes

        if existing:
            if not dry_run:
                existing.principal = record.total_pending
                existing.outstanding = record.total_pending
                existing.provenance = provenance
                existing.updated_at = datetime.now(timezone.utc)
                if source_doc:
                    existing.source_document_id = source_doc.id
            updated += 1
            logger.debug(f"Updated: {lender_name} = {record.total_pending}")
        else:
            if not dry_run:
                loan = Loan(
                    entity_id=entity.id,
                    lender=lender_name,
                    debt_category=DebtCategory.PENDING_BILLS,
                    principal=record.total_pending,
                    outstanding=record.total_pending,
                    interest_rate=Decimal("0"),  # Pending bills carry no interest
                    issue_date=datetime.now(timezone.utc),
                    maturity_date=None,  # No maturity — these are overdue
                    currency="KES",
                    source_document_id=source_doc.id if source_doc else None,
                    provenance=provenance,
                )
                session.add(loan)
            created += 1
            logger.debug(f"Created: {lender_name} = {record.total_pending}")

    if not dry_run:
        _retire_counties_this_edition_does_not_report(session, records)

    if not dry_run:
        session.flush()

    logger.info(
        f"Pending bills write complete: " f"{created} created, {updated} updated"
    )
    return created, updated


def _is_county_record(record: PendingBillRecord) -> bool:
    """A record about a county, however the payload spelled its category."""
    category = (record.category or "").strip().lower()
    entity_type = (record.entity_type or "").strip().lower()
    return category == "county" or entity_type == "county"


def _retire_counties_this_edition_does_not_report(
    session: Session, records: list[PendingBillRecord]
) -> int:
    """Stop publishing a county's figure from an older BROP edition.

    The upsert key is (entity, lender), so a county the new edition reports is
    overwritten in place. A county it does NOT report — Narok submitted to one
    BROP and not the next — kept the previous edition's row, stamped as the
    BROP, and went on being served beside everyone's newer figure and summed
    into the county total. The row is kept (it is last year's publication) but
    no longer declares itself the current one.
    """
    editions = {r.fiscal_year for r in records if _is_county_record(r)}
    if len(editions) != 1:
        return 0
    edition = editions.pop()
    retired = 0
    rows = (
        session.query(Loan)
        .join(Entity, Entity.id == Loan.entity_id)
        .filter(
            Entity.type == EntityType.COUNTY,
            Loan.debt_category == DebtCategory.PENDING_BILLS,
        )
        .all()
    )
    for loan in rows:
        prov = loan.provenance if isinstance(loan.provenance, dict) else None
        if not prov or prov.get("publication") != PENDING_BILLS_PUBLICATION:
            continue
        if prov.get("fiscal_year") == edition:
            continue
        loan.provenance = {
            **prov,
            "publication": None,
            "superseded_by_edition": edition,
        }
        retired += 1
    if retired:
        logger.warning(
            "pending bills: %d county row(s) from an earlier BROP edition are "
            "no longer published — the %s edition does not report them",
            retired,
            edition,
        )
    return retired


def _build_lender_name(record: PendingBillRecord) -> str:
    """Build a descriptive lender name for the pending bill."""
    category_labels = {
        "mda": "Pending Bills — MDAs",
        "county": "Pending Bills — County Governments",
        "state_corporation": "Pending Bills — State Corporations",
    }
    base = category_labels.get(record.category, "Pending Bills")

    # If entity name is specific (not an aggregate), include it
    if record.entity_name and "all" not in record.entity_name.lower():
        return f"{base} ({record.entity_name})"
    return base


def _get_or_create_entity(
    session: Session, name: str, entity_type: str
) -> Entity | None:
    """Get or create entity by name and type."""
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

    entity = (
        session.query(Entity)
        .filter(Entity.canonical_name == name, Entity.type == entity_type_enum)
        .first()
    )
    if entity:
        return entity

    # For aggregate records, use "National Government" or "Kenya" entity
    if "national" in name.lower() or entity_type == "national":
        entity = (
            session.query(Entity)
            .filter(
                Entity.type == EntityType.NATIONAL,
            )
            .first()
        )
        if entity:
            return entity

    # For county aggregates, try generic county entity
    if entity_type == "county":
        entity = (
            session.query(Entity)
            .filter(Entity.canonical_name.ilike(f"%{name.split('—')[0].strip()}%"))
            .first()
        )
        if entity:
            return entity

    logger.warning(
        f"Entity not found: {name} ({entity_type}). "
        f"Run bootstrap_data.py to create reference entities."
    )
    return None


def _get_or_create_source_document(
    session: Session,
    source_url: str | None,
    source_title: str | None,
    publisher: str | None = None,
) -> SourceDocument | None:
    """Get or create the source document a pending-bills payload came from.

    ``publisher`` is the payload's own declaration. It used to be hardcoded to
    the Controller of Budget, which named the wrong office for the Treasury's
    BROP — the document every county figure is read from.
    """
    title = source_title or "COB Pending Bills Report"
    publisher = publisher or "Office of the Controller of Budget (OCOB)"

    doc = (
        session.query(SourceDocument)
        .filter(
            SourceDocument.title == title,
            SourceDocument.doc_type == DocumentType.REPORT,
        )
        .first()
    )
    if doc:
        if doc.publisher != publisher:
            doc.publisher = publisher
        if source_url and doc.url != source_url:
            doc.url = source_url
        return doc

    from models import Country

    kenya = session.query(Country).filter(Country.iso_code == "KEN").first()
    if not kenya:
        logger.warning("Kenya country record not found. Skipping source doc.")
        return None

    logger.info(f"Creating source document: {title}")
    doc = SourceDocument(
        country_id=kenya.id,
        publisher=publisher,
        title=title,
        doc_type=DocumentType.REPORT,
        url=source_url,
        fetch_date=datetime.now(timezone.utc),
    )
    session.add(doc)
    session.flush()
    return doc
