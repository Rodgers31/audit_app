"""Writer for pending bills data to database.

Persists parsed PendingBillRecord objects to the loans table using
the PENDING_BILLS debt category, following the same pattern as
the national_debt writer.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import replace
from functools import wraps
from datetime import date, datetime, timezone
from decimal import Decimal

from models import DebtCategory, DocumentType, Entity, EntityType, Loan, SourceDocument
from services.publication_gate import (
    COUNTY_PENDING_BILLS_PUBLICATION,
    NATIONAL_PENDING_BILLS_PUBLICATION,
)
from sqlalchemy.orm import Session
from .parser import PendingBillRecord, require_pending_amount

logger = logging.getLogger("seeding.pending_bills.writer")


def _write_pending_bills(
    session: Session,
    records: list[PendingBillRecord],
    source_url: str | None = None,
    source_title: str | None = None,
    dry_run: bool = False,
    publication: str | None = None,
    publisher: str | None = None,
    county_table: dict | None = None,
) -> tuple[int, int]:
    """
    Write pending bills records to the loans table.

    ``county_table`` (county payloads only) is what the report says about the
    counties it gives no figure for — ``{"as_at", "table", "not_reported",
    "withheld"}`` — kept on the report's source document, because a county
    with no figure has no row to keep it on, and "not reported to the CoB at
    30 June 2026" is a different thing to tell a reader than a bare dash.

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

    if not isinstance(records, list):
        raise ValueError("Pending bills records must be a list")
    if not records:
        logger.info("No pending bills records to write")
        return created, updated

    # Each half of pending bills comes from ONE publication: the National
    # Government's from the Treasury BROP, the counties' from the Controller of
    # Budget's year-end CBIRR (#238). A payload writes only the side its
    # publication is the source for, and any other payload writes nothing. The
    # git fixture the fetcher falls back to carries invented figures on both
    # sides:
    #
    # * seven counties (Nairobi 98.7B, ...) under the same lender key the
    #   county rows use, so one failed fetch OVERWROTE the published figure
    #   (#238);
    # * eleven ministries and state corporations (405.4B) under lender keys the
    #   BROP never uses, so they were ADDED beside its two national lines and
    #   stayed there — 931.3B served against the 525.9B the BROP prints, the
    #   same bills counted twice (#265).
    if publication == NATIONAL_PENDING_BILLS_PUBLICATION:
        writes_county = False
    elif publication == COUNTY_PENDING_BILLS_PUBLICATION:
        writes_county = True
    else:
        logger.warning(
            "pending bills: not writing %d record(s) from a %s payload — "
            "national pending bills are read from the Treasury BROP and county "
            "pending bills from the Controller of Budget's year-end report only",
            len(records),
            publication or "fixture",
        )
        return created, updated
    if any(not isinstance(r, PendingBillRecord) for r in records):
        raise ValueError("Pending bills records must be PendingBillRecord objects")
    if any(
        not isinstance(r.entity_type, str) or not isinstance(r.category, str)
        for r in records
    ):
        raise ValueError("Pending bills entity type and category must be strings")
    off_side = [r for r in records if _is_county_record(r) != writes_county]
    if off_side:
        logger.warning(
            "pending bills: not writing %d %s record(s) from a %s payload — it "
            "is not the source for that side",
            len(off_side),
            "national" if writes_county else "county",
            publication,
        )
    records = [r for r in records if _is_county_record(r) == writes_county]
    if not records:
        return created, updated

    records = _validated_records(records, source_url, source_title, publisher)

    if writes_county:
        _require_forward_county_edition(session, records, county_table)
        # Resolve the whole county edition before creating its source or
        # retiring any prior figure. A skipped identity is not a missing row
        # in the publisher's table, and may not erase a known county amount.
        county_entities = []
        for record in records:
            if (record.entity_type or "").strip().lower() != "county":
                raise ValueError("County publication requires county entity types")
            entity = _get_or_create_entity(session, record.entity_name, "county")
            if entity is None:
                raise ValueError(f"Unresolved county identity: {record.entity_name}")
            county_entities.append(entity)
        if len({entity.id for entity in county_entities}) != len(county_entities):
            raise ValueError("County edition repeats a county identity")

    written: set[tuple[int, str]] = set()
    # Same URL/date does not identify a correction edition. Fingerprint this
    # whole batch so a partial same-day replacement cannot be added to rows
    # retained from an earlier parse (including same-URL reissues).
    publication_batch = hashlib.sha256(
        json.dumps(
            sorted(
                (
                    record.entity_name,
                    record.category,
                    record.fiscal_year,
                    str(record.total_pending),
                    record.as_at or "",
                    record.source_url or source_url or "",
                )
                for record in records
            ),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()

    # Get or create the source document
    source_doc = _get_or_create_source_document(
        session, source_url, source_title, publisher=publisher
    )
    if writes_county and source_doc is not None and not dry_run:
        source_doc.meta = {
            **(source_doc.meta if isinstance(source_doc.meta, dict) else {}),
            "county_payables": dict(county_table) if county_table else None,
        }

    for index, record in enumerate(records):
        entity = (
            county_entities[index]
            if writes_county
            else _get_or_create_entity(session, record.entity_name, record.entity_type)
        )
        if not entity:
            logger.warning(
                f"Could not resolve entity: {record.entity_name} "
                f"({record.entity_type}). Skipping."
            )
            continue

        # Build a deterministic lender name based on category
        lender_name = _build_lender_name(record)
        written.add((entity.id, lender_name))

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
            # Which publication this figure was read from — the BROP for a
            # national row, the CoB year-end report for a county row. Declared
            # by the fetcher, re-stamped on every write.
            "publication": publication,
            "publication_batch": publication_batch,
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
        # The day the figure is a stock on, the table and page it is printed
        # on, and what the report says about it — each read by the parser.
        if record.as_at:
            provenance["as_at"] = record.as_at
        if record.source_table:
            provenance["table"] = record.source_table
        if record.source_page:
            provenance["page"] = record.source_page
        if record.reader_notes:
            provenance["reader_notes"] = [dict(n) for n in record.reader_notes]
        if record.source_evidence and not dry_run:
            from ...pdf_evidence import bind_pdf_evidence
            provenance["source_evidence"] = bind_pdf_evidence(session, source_doc, record.source_evidence,
                identity={"entity_id": entity.id, "geography": entity.canonical_name if writes_county else "KEN",
                          "period": record.as_at, "unit": "KES", "basis": "actual",
                          "dimensions": {"lender": lender_name, "debt_category": "pending_bills"}},
                values={"outstanding": record.total_pending})

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

    if not dry_run and writes_county:
        editions = {r.fiscal_year for r in records}
        _retire_county_rows_not_written(
            session, written, editions.pop() if len(editions) == 1 else None
        )

    if not dry_run:
        session.flush()

    logger.info(
        f"Pending bills write complete: " f"{created} created, {updated} updated"
    )
    return created, updated


@wraps(_write_pending_bills)
def write_pending_bills(session: Session, *args, **kwargs) -> tuple[int, int]:
    """Keep an edition atomic even when the domain catches a write failure.

    Release the savepoint into the caller's transaction on success; never
    commit it here. A malformed late record cannot leave earlier rows dirty.
    """
    with session.begin_nested():
        return _write_pending_bills(session, *args, **kwargs)


def _validated_records(records, source_url, source_title, publisher):
    """Preflight the consumed batch before source, edition or loan mutation.

    Return normalized copies so direct callers cannot slip driver-specific
    representations through or have their own records partially modified.
    """
    for field, value in (
        ("source_url", source_url),
        ("source_title", source_title),
        ("publisher", publisher),
    ):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"Invalid pending bills {field}")
    validated = []
    for record in records:
        for field in ("entity_name", "entity_type", "category", "fiscal_year"):
            value = getattr(record, field)
            if not isinstance(value, str) or (
                field != "fiscal_year" and not value.strip()
            ):
                raise ValueError(f"Invalid pending bills {field}")
        for field in ("source_url", "source_title", "source_table", "notes"):
            value = getattr(record, field)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"Invalid pending bills {field}")
        if (
            record.source_url is not None
            and source_url is not None
            and record.source_url != source_url
        ):
            raise ValueError("Pending bills record and batch disagree on source URL")
        if record.as_at is not None:
            if not isinstance(record.as_at, str):
                raise ValueError("Pending bills require an ISO as-at date")
            try:
                day = date.fromisoformat(record.as_at)
            except ValueError as exc:
                raise ValueError("Invalid pending bills as-at date") from exc
            if day.isoformat() != record.as_at:
                raise ValueError("Pending bills require an ISO as-at date")
        if record.source_page is not None and (
            type(record.source_page) is not int or record.source_page <= 0
        ):
            raise ValueError("Invalid pending bills source page")
        if not isinstance(record.reader_notes, list) or any(
            not isinstance(n, dict) for n in record.reader_notes
        ):
            raise ValueError("Pending bills reader notes must be objects")
        amounts = {
            field: require_pending_amount(
                getattr(record, field), field, optional=field != "total_pending"
            )
            for field in ("total_pending", "eligible_pending", "ineligible_pending")
        }
        # Loan principal/outstanding are Numeric(15,2). Reject overflow before
        # mutation; optional provenance amounts must also serialize finitely.
        if amounts["total_pending"] > Decimal("9999999999999.99"):
            raise ValueError("Pending bills total exceeds monetary storage range")
        if any(
            value is not None and not math.isfinite(float(value))
            for value in amounts.values()
        ):
            raise ValueError("Pending bills amount exceeds finite publication range")
        validated.append(replace(record, **amounts))
    for field in ("fiscal_year", "as_at"):
        if len({getattr(r, field) for r in validated}) > 1:
            raise ValueError(f"Pending bills records mix {field}")
    if len({r.source_url or source_url for r in validated}) > 1:
        raise ValueError("Pending bills records mix source URLs")
    return validated


def _require_forward_county_edition(session, records, county_table):
    """Validate the report's stock date before touching documents or loan rows.

    Upload IDs and retrieval times are not edition dates. Reject the whole
    incoming table (so the domain records PARTIAL) instead of overwriting a
    subset and retiring current rows from the rest of the counties.
    """

    def as_day(value):
        if not isinstance(value, str):
            raise ValueError("County pending bills require an ISO as-at date")
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Invalid county pending-bills as-at date") from exc
        if parsed.isoformat() != value or (parsed.month, parsed.day) != (6, 30):
            raise ValueError(
                "County pending bills require the stated 30 June stock date"
            )
        return parsed

    dates = {as_day(record.as_at) for record in records}
    if len(dates) != 1:
        raise ValueError("County pending-bills records mix edition dates")
    incoming = dates.pop()
    if county_table is not None and not isinstance(county_table, dict):
        raise ValueError("County pending-bills table must be an object")
    if county_table is not None and as_day(county_table.get("as_at")) != incoming:
        raise ValueError(
            "County pending-bills table and records disagree on as-at date"
        )
    # Serialize county writers even when no loan rows exist yet. PostgreSQL
    # holds these locks through the writer's caller-owned transaction.
    session.query(Entity).filter(Entity.type == EntityType.COUNTY).order_by(
        Entity.id
    ).with_for_update().all()
    rows = (
        session.query(Loan)
        .join(Entity, Entity.id == Loan.entity_id)
        .filter(
            Entity.type == EntityType.COUNTY,
            Loan.debt_category == DebtCategory.PENDING_BILLS,
        )
        .all()
    )
    for row in rows:
        entries = (
            row.provenance if isinstance(row.provenance, list) else [row.provenance]
        )
        for entry in entries:
            if (
                isinstance(entry, dict)
                and entry.get("publication") == COUNTY_PENDING_BILLS_PUBLICATION
            ):
                if incoming < as_day(entry.get("as_at")):
                    raise ValueError(
                        f"Stale county edition {incoming}: published row {row.id} is dated {entry['as_at']}"
                    )


def _is_county_record(record: PendingBillRecord) -> bool:
    """A record about a county, however the payload spelled its category."""
    category = (record.category or "").strip().lower()
    entity_type = (record.entity_type or "").strip().lower()
    return category == "county" or entity_type == "county"


def _retire_county_rows_not_written(
    session: Session, written: set[tuple[int, str]], edition: str | None
) -> int:
    """Stop publishing every county row this write did not make.

    A county payload is the whole of one report's table, so a county row it
    did not write is not that report's figure. The upsert key is (entity,
    lender), so a county the report states is overwritten in place; one it
    does not — Nandi reported at 30 June 2025 and not at 30 June 2026, or a
    row the parser now withholds on a re-read of the SAME edition — would keep
    its old figure, stamped as current, and be served and summed beside
    everyone's new one. The row is kept (it was published once) but no longer
    declares a publication.
    """
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
        if not prov or prov.get("publication") != COUNTY_PENDING_BILLS_PUBLICATION:
            continue
        if (loan.entity_id, loan.lender) in written:
            continue
        loan.provenance = {
            **prov,
            "publication": None,
            "superseded_by_edition": edition,
        }
        retired += 1
    if retired:
        logger.warning(
            "pending bills: %d county row(s) are no longer published — the %s "
            "report does not state them",
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
    entity_type_enum = (
        type_mapping.get(entity_type.strip().lower())
        if isinstance(entity_type, str)
        else None
    )
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
    if entity_type_enum == EntityType.NATIONAL:
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
    if entity_type_enum == EntityType.COUNTY:
        entity = (
            session.query(Entity)
            .filter(
                Entity.type == EntityType.COUNTY,
                Entity.canonical_name.in_([name.strip(), f"{name.strip()} County"]),
            )
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
    BROP.
    """
    title = source_title or "COB Pending Bills Report"
    # The default names a NEW document only. Used to overwrite, it relabelled
    # the Treasury's BROP as the Controller of Budget's on any call that did not
    # declare a publisher (review of #262; #271 fixed the same defect in
    # revenue_by_source).
    declared = publisher

    doc = (
        session.query(SourceDocument)
        .filter(
            SourceDocument.title == title,
            SourceDocument.doc_type == DocumentType.REPORT,
        )
        .first()
    )
    if doc:
        if declared and doc.publisher != declared:
            doc.publisher = declared
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
        publisher=declared or "Office of the Controller of Budget (OCOB)",
        title=title,
        doc_type=DocumentType.REPORT,
        url=source_url,
        fetch_date=datetime.now(timezone.utc),
    )
    session.add(doc)
    session.flush()
    return doc
