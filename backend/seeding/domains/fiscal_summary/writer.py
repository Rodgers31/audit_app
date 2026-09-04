"""Writer for fiscal summary records to database."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from models import Country, DocumentType, FiscalSummary, SourceDocument
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from .parser import FiscalSummaryRecord

logger = logging.getLogger("seeding.fiscal_summary.writer")


def _get_or_create_source_document(
    session: Session, metadata: dict[str, Any]
) -> SourceDocument:
    """Get or create source document for fiscal summary data."""
    title = metadata.get(
        "source", "National Treasury BPS & Controller of Budget Reports"
    )

    doc = (
        session.query(SourceDocument)
        .filter(
            SourceDocument.title == title,
            SourceDocument.doc_type == DocumentType.REPORT,
        )
        .first()
    )
    if doc:
        return doc

    kenya = session.query(Country).filter(Country.iso_code == "KEN").first()
    if not kenya:
        raise ValueError("Kenya country not found. Run bootstrap_data.py first.")

    doc = SourceDocument(
        country_id=kenya.id,
        publisher="National Treasury & Controller of Budget",
        title=title,
        url="https://www.treasury.go.ke/budget-policy-statement/",
        fetch_date=datetime.now(timezone.utc),
        doc_type=DocumentType.REPORT,
        meta={
            "notes": metadata.get("notes", ""),
            "units": metadata.get("units", "billions_kes"),
        },
    )
    session.add(doc)
    session.flush()
    return doc


def _raw_kes(value: Any) -> Any:
    """Normalise a money value to raw KES at the DB boundary.

    Parser records (and fixtures) carry the historical billions convention;
    the table stores raw KES with a declared ``unit`` column since the
    stage1 3a migration. No national fiscal aggregate legitimately sits
    between 1e6 and 1e9, so the scale test is unambiguous and idempotent.
    """
    if value is None:
        return None
    # A bool is an int in Python and would silently become 1e9 KES; NaN/inf
    # would poison the table. Both are parser bugs — fail closed, loudly.
    if isinstance(value, bool):
        raise ValueError(f"boolean is not a money value: {value!r}")
    v = float(value)
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError(f"non-finite money value: {value!r}")
    return v * 1e9 if v < 1_000_000 else v


def _budget_basis_meta(record) -> dict[str, Any]:
    """``metadata`` payload recording the budget basis and its receipt."""
    basis = getattr(record, "budget_basis", None)
    if not basis:
        return {}
    out: dict[str, Any] = {"budget_basis": basis}
    source = getattr(record, "budget_basis_source", None)
    if isinstance(source, dict):
        out["budget_basis_source"] = source
    # Stored in the existing JSONB column rather than a new one: this needs no
    # migration, so it cannot add to the production schema drift.
    redemption = getattr(record, "debt_redemption", None)
    if redemption is not None:
        out["debt_redemption_billion"] = redemption
    return out


def write_fiscal_summary_records(
    session: Session,
    records: list[FiscalSummaryRecord],
    metadata: dict[str, Any],
) -> tuple[int, int]:
    """Upsert fiscal summary records into the database (raw KES)."""
    created = 0
    updated = 0

    source_doc = _get_or_create_source_document(session, metadata)

    for record in records:
        existing = (
            session.query(FiscalSummary)
            .filter(FiscalSummary.fiscal_year == record.fiscal_year)
            .first()
        )

        fields = {
            # Money columns: converted to raw KES at this boundary.
            "appropriated_budget": _raw_kes(record.appropriated_budget),
            "total_revenue": _raw_kes(record.total_revenue),
            "tax_revenue": _raw_kes(record.tax_revenue),
            "non_tax_revenue": _raw_kes(record.non_tax_revenue),
            "total_borrowing": _raw_kes(record.total_borrowing),
            "borrowing_pct_of_budget": record.borrowing_pct_of_budget,
            "debt_service_cost": _raw_kes(record.debt_service_cost),
            "debt_service_per_shilling": record.debt_service_per_shilling,
            "debt_ceiling": _raw_kes(record.debt_ceiling),
            "actual_debt": _raw_kes(record.actual_debt),
            "debt_ceiling_usage_pct": record.debt_ceiling_usage_pct,
            "development_spending": _raw_kes(record.development_spending),
            "recurrent_spending": _raw_kes(record.recurrent_spending),
            "county_allocation": _raw_kes(record.county_allocation),
            "unit": "KES",
        }

        # Provenance for the budget figure. Persisted so the API can say
        # WHICH measure it is publishing — "no number without provenance"
        # applies to a number's definition, not only its value.
        basis_meta = _budget_basis_meta(record)
        if basis_meta:
            fields["meta"] = basis_meta
            page_ref = (basis_meta.get("budget_basis_source") or {}).get("page")
            if page_ref:
                fields["page_ref"] = str(page_ref)[:50]

        if existing:
            for key, val in fields.items():
                setattr(existing, key, val)
            existing.source_document_id = source_doc.id
            existing.updated_at = datetime.now(timezone.utc)
            updated += 1
        else:
            row = FiscalSummary(
                fiscal_year=record.fiscal_year,
                source_document_id=source_doc.id,
                **fields,
            )
            session.add(row)
            created += 1

    session.flush()
    logger.info(f"Fiscal summary: {created} created, {updated} updated")
    return created, updated
