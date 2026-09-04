"""Persist the Treasury bond register to ``debt_instruments``.

The register is a maturity and coupon profile, not a stock measure — it covers
~60% of CBK's published Treasury-bond total. Every row written here is
``publishable`` only because it traces to the CBK table it came from, and the
coverage ratio travels with it on the source document so no consumer can read
the sum as a debt total. See ``models.DebtInstrument`` for the full rule.

Rows the source cannot settle — six ISINs whose maturity is ambiguous, holding
~15% of face value — are never written. Their count and reasons are recorded on
the source document instead, so the omission is visible rather than inferred
from a total that looks slightly small.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List

from models import Country, DebtInstrument, DocumentType, SourceDocument
from sqlalchemy.orm import Session

logger = logging.getLogger("seeding.national_debt.instrument_writer")


def _get_or_create_source_document(
    session: Session, register: Dict[str, Any]
) -> SourceDocument:
    """The CBK bond table, as a source document a reader can open.

    The URL is the table itself, not a listing page — ``/provenance/verify``
    grades a homepage-only URL as unverifiable, and rightly.
    """
    url = register["source_url"]
    doc = (
        session.query(SourceDocument)
        .filter(SourceDocument.url == url)
        .first()
    )
    kenya = session.query(Country).filter(Country.iso_code == "KEN").first()
    if not kenya:
        raise ValueError("Kenya country not found. Run bootstrap first.")

    coverage = register.get("coverage") or {}
    meta = {
        "coverage": coverage,
        "withheld_isins": register.get("withheld_isins") or {},
        "tranche_rows": register.get("tranche_rows"),
        "as_of": register.get("as_of"),
        # Stated on the document itself so it cannot be separated from the
        # figures: this register is not a debt total.
        "not_a_stock_measure": (
            "Face values here describe WHEN debt falls due and at WHAT coupon. "
            "They cover roughly %s of CBK's published Treasury-bond stock and "
            "must not be summed into a debt total."
            % (
                f"{coverage['coverage_ratio']:.0%}"
                if coverage.get("coverage_ratio")
                else "an unmeasured share"
            )
        ),
    }

    if doc:
        doc.fetch_date = datetime.now(timezone.utc)
        doc.meta = {**(doc.meta or {}), **meta}
        return doc

    doc = SourceDocument(
        country_id=kenya.id,
        publisher="Central Bank of Kenya",
        title=register.get("source_title") or "CBK — Issues of Treasury Bonds",
        doc_type=DocumentType.LOAN,
        url=url,
        fetch_date=datetime.now(timezone.utc),
        meta=meta,
    )
    session.add(doc)
    session.flush()
    return doc


def write_bond_register(
    session: Session, register: Dict[str, Any]
) -> Dict[str, int]:
    """Upsert the register on (isin, maturity_date). Returns counts.

    Upsert rather than replace: the unique constraint is the natural key, and a
    re-run must not duplicate a security. Rows that disappear from CBK's table
    (a bond redeemed since the last run) are deleted, so the ladder does not
    keep drawing bars for debt that has been paid.
    """
    securities: List[Dict[str, Any]] = register.get("securities") or []
    if not securities:
        logger.warning("bond register empty; nothing written")
        return {"created": 0, "updated": 0, "deleted": 0}

    doc = _get_or_create_source_document(session, register)
    coverage = register.get("coverage") or {}

    seen: set[tuple[str, datetime]] = set()
    created = updated = 0

    for s in securities:
        maturity = datetime.fromisoformat(s["maturity_date"])
        key = (s["isin"], maturity)
        seen.add(key)

        row = (
            session.query(DebtInstrument)
            .filter(
                DebtInstrument.isin == s["isin"],
                DebtInstrument.maturity_date == maturity,
            )
            .first()
        )
        values = dict(
            issue_no=s["issue_no"],
            instrument_type=s["instrument_type"],
            face_value=Decimal(str(s["face_value_kes"])),
            unit="KES",
            coupon_rate=(
                Decimal(str(s["coupon_rate"])) if s.get("coupon_rate") is not None else None
            ),
            tenor_years=(
                Decimal(str(s["tenor_years"])) if s.get("tenor_years") is not None else None
            ),
            first_issued=(
                datetime.fromisoformat(s["first_issued"]) if s.get("first_issued") else None
            ),
            tranches=s.get("tranches") or 1,
            source_document_id=doc.id,
            # The register traces to a document a reader can open, at a URL
            # that is the table itself. That is what publishable asserts here.
            publishable=True,
            quarantine_reason=None,
            meta={
                "source": "cbk_treasury_bonds_table",
                "coverage_ratio": coverage.get("coverage_ratio"),
                "as_of": register.get("as_of"),
            },
        )

        if row is None:
            session.add(DebtInstrument(isin=s["isin"], maturity_date=maturity, **values))
            created += 1
        else:
            for k, v in values.items():
                setattr(row, k, v)
            updated += 1

    # Anything we hold that CBK no longer lists has matured or been bought
    # back. Leaving it would keep a redeemed bond on the maturity ladder.
    deleted = 0
    for row in session.query(DebtInstrument).all():
        if (row.isin, row.maturity_date) not in seen:
            session.delete(row)
            deleted += 1

    logger.info(
        "debt_instruments: %d created, %d updated, %d removed (no longer listed)",
        created, updated, deleted,
    )
    return {"created": created, "updated": updated, "deleted": deleted}
